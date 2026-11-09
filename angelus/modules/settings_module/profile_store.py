"""One canonical run-profile implementation for global and session settings."""

from __future__ import annotations

from collections.abc import Callable, Mapping
import math
from pathlib import Path
import threading
from typing import Any, Protocol

from .json_store import read_json, write_json
from llmfetcher.context_handlers import DEFAULT_CONTEXT_HANDLER


DEFAULT_RUN_PROFILE: dict[str, Any] = {
    "system_prompt": "You are a helpful, precise assistant.\nAfter each checkpoint, DO NOT re-call the tool called `set_task_plan` for task updation.",
    "temperature": 0.4,
    "thinking_mode": "auto",
    "reasoning_effort": "auto",
    "max_tokens": 32768,
    "max_rounds": 0,
    "max_retries": 3,
    "request_timeout_seconds": 60.0,
    # A new Session inherits the service's host network; an operator opts into
    # the isolated sandbox explicitly through a per-Session override.
    "shell_network_mode": "host_network",
    "max_context_threshold": 262144,
    "compaction_output_max_tokens": 16384,
    "context_keep_recent": 0,
    "tool_result_context_limit": 0,
    "context_handler": DEFAULT_CONTEXT_HANDLER,
    "context_handler_settings": {},
    "context_block_order": {},
    "max_swarm_agents": 4,
    "agent_overrides": {},
    "session_memory_search_sessions": [],
    "session_memory_read_sessions": [],
    "session_artifact_search_sessions": [],
    "session_artifact_open_sessions": [],
    # Only grants a default Tool provider actually registers. Plugin grants are
    # never listed: a Plugin becomes grantable only after an operator loads it,
    # and the saved grants of an unloaded Plugin are retained per key.
    "tool_permissions": {
        "categories": {
            "context_version": True, "session_memory": True, "notes": True, "vision": True, "file_discovery": True,
            "project_retrieval": True, "file_write": True, "shell": True, "planning": True, "mcp": True,
        },
        "tools": {
            "file_list": True, "file_read": True, "file_search": True, "file_write": True,
            "inspect_agent_context": True, "search_agent_archive": True, "read_agent_archive": True,
            "edit_agent_context": True, "restore_agent_context": True,
            "search_session_memory": True, "read_session_memory": True,
            "search_session_artifacts": True, "open_session_artifact": True,
            "create_session_handoff": True, "read_session_handoff": True,
            "note_list": True, "note_search": True, "note_read": True, "note_create": True, "note_update": True, "note_delete": True,
            "view_image": True,
            "shell": True,
            "set_task_plan": True, "update_task_status": True, "read_task_plan": True,
            "mcp": True,
        },
    },
}

# Accepted only so an explicit migration can read old documents. New profile
# writes never add these connector-owned fields unless a legacy caller submits
# them unchanged.
LEGACY_CONNECTOR_FIELDS = {"connector_id", "provider", "model", "api_url"}

#: Every Plugin-owned grant key is namespaced with this prefix.  Pruning keeps
#: the whole prefix because, once its provider has left the registry, an
#: unloaded Plugin is indistinguishable from one that no longer exists; an
#: operator's earlier grant must survive a temporary unload.
PLUGIN_PERMISSION_PREFIX = "plugin."

#: Pre-registry Plugin label that ``ToolPolicy`` still honours for the same
#: reason as the prefix above.
LEGACY_PLUGIN_CATEGORY = "plugin"

#: Grant keys ``ToolPolicy`` migrates to current registry IDs at Agent
#: construction.  They stay accepted input because the canonical replacement is
#: only known to the tool module, so pruning here would delete a real grant.
#: Mirrors ``tool_module.tool_policy._LEGACY_TOOL_IDS``; a test asserts parity
#: instead of importing it, because settings must not depend on that module.
LEGACY_TOOL_GRANT_IDS = frozenset({
    "plan_upsert",
    "plan_read",
    "dynamic_add_connection",
    "dynamic_remove_connection",
    "dynamic_set_mapper",
    "dynamic_set_router",
})

#: Pre-registry category label that ``ToolPolicy`` maps to ``context_version``.
LEGACY_CATEGORY_GRANT_IDS = frozenset({"context"})

#: Grants that deliberately have no concrete ``ToolDefinition``: the MCP bridge
#: creates one Tool per server Tool at Session runtime, so no registry ID can be
#: listed for it and the persisted default grant must not be pruned away.
POLICY_ONLY_TOOL_GRANT_IDS = frozenset({"mcp"})


class _CatalogToolLike(Protocol):
    """Structural view of one registered Tool definition."""

    id: str


class _CatalogCategoryLike(Protocol):
    """Structural view of one registered Tool category."""

    id: str
    tools: tuple[_CatalogToolLike, ...]


class ToolCatalogLike(Protocol):
    """Structural view of the read-only Tool catalog a caller may bind.

    Only these attributes are read.  ``settings_module`` intentionally does not
    import ``tool_module``: persisted settings must stay usable without the
    registry implementation, and a Protocol keeps the coupling structural.
    """

    categories: tuple[_CatalogCategoryLike, ...]


class RunProfileStore:
    """Persist global defaults and sparse per-session overrides.

    A profile is configuration for a future attempt, never mutable execution
    state.  ``effective`` merges the global document and a session override;
    execution creation will later freeze that result into its attempt snapshot.
    """

    def __init__(
        self,
        state_root: Path,
        *,
        tool_catalog: Callable[[], ToolCatalogLike] | None = None,
    ) -> None:
        """Store defaults under ``settings`` and overrides under each Session.

        Args:
            state_root: Angelus-owned root; never an arbitrary project path.
            tool_catalog: Optional reader for the live Tool catalog.  Tool
                providers are registered after this store exists and Plugins
                change them at runtime, so a callable is held instead of a
                snapshot.  ``None`` keeps the legacy behaviour of accepting any
                grant key; see :meth:`bind_tool_catalog`.
        """
        # Base directory used to derive every Session-local override path.
        self._root = state_root
        # Sole durable global-default document.
        self._global_path = state_root / "settings" / "global-run-profile.json"
        # Serializes read/validate/write and effective-profile merge operations.
        self._lock = threading.RLock()
        # Optional live catalog reader; ``None`` disables grant pruning.
        self._tool_catalog: Callable[[], ToolCatalogLike] | None = tool_catalog

    def bind_tool_catalog(self, tool_catalog: Callable[[], ToolCatalogLike] | None) -> None:
        """Attach or detach the live Tool catalog reader used by cross-checks.

        Idempotent: the newest binding wins, and ``None`` restores the legacy
        tolerant merge.  Binding a reader rather than a catalog snapshot keeps
        this store free of ``tool_module`` imports while still following Plugin
        load/unload and registry revision changes.

        Args:
            tool_catalog: Zero-argument callable returning a catalog-like
                object, or ``None`` to disable grant pruning.
        """
        with self._lock:
            self._tool_catalog = tool_catalog

    def global_profile(self) -> dict[str, Any]:
        """Return the complete global default profile with omitted fields filled."""
        with self._lock:
            return self._validated(self._read(self._global_path), partial=False)

    def replace_global(self, values: Mapping[str, Any]) -> dict[str, Any]:
        """Validate and atomically replace global defaults.

        Args:
            values: Complete supported profile fields; unknown fields fail.
        """
        with self._lock:
            profile = self._validated(values, partial=False)
            write_json(self._global_path, {"schema_version": 2, "settings": profile})
            return profile

    def session_profile(self, session_id: str) -> dict[str, Any]:
        """Return effective settings and whether this Session has an override.

        Global values are copied first, then the Session's local values win.
        No disk state is changed by this read operation.
        """
        with self._lock:
            global_profile = self._validated(self._read(self._global_path), partial=False)
            override_path = self._session_path(session_id)
            override = self._validated(self._read(override_path), partial=True)
            return {
                "scope": "session",
                "inherits_default": not override_path.exists(),
                "effective": {**global_profile, **override},
            }

    def replace_session(self, session_id: str, values: Mapping[str, Any]) -> dict[str, Any]:
        """Replace a Session override with validated complete future-run values.

        This intentionally stores a full profile rather than a patch: a saved
        Session stays stable if a later version changes global defaults.
        """
        with self._lock:
            # A complete override makes its meaning independent of later UI
            # field additions; inherit is the explicit way back to global.
            override = self._validated(values, partial=False)
            write_json(self._session_path(session_id), {"schema_version": 2, "settings": override})
            return {"scope": "session", "inherits_default": False, "effective": override}

    def clear_session(self, session_id: str) -> dict[str, Any]:
        """Remove override file so the Session again resolves global defaults.

        Missing files are already equivalent to inheritance and are accepted.
        """
        with self._lock:
            path = self._session_path(session_id)
            try:
                path.unlink()
            except FileNotFoundError:
                pass
        return self.session_profile(session_id)

    def effective(self, session_id: str) -> dict[str, Any]:
        """Return resolved values that execution creation will snapshot later."""
        return dict(self.session_profile(session_id)["effective"])

    def connector_references(self, connector_id: str, session_ids: tuple[str, ...]) -> tuple[str, ...]:
        """Return profile scopes whose effective setting references a connector.

        The result includes inherited global references, because those still
        become invalid when a connector disappears.
        """
        references: list[str] = []
        if self.global_profile().get("connector_id") == connector_id:
            references.append("global")
        for session_id in session_ids:
            if self.effective(session_id).get("connector_id") == connector_id:
                references.append(session_id)
        return tuple(references)

    def _read(self, path: Path) -> Mapping[str, Any]:
        """Decode one optional profile envelope, rejecting malformed documents."""
        document = read_json(path, {"schema_version": 1, "settings": {}})
        if not isinstance(document, dict) or document.get("schema_version") not in {1, 2}:
            raise ValueError(f"unsupported run profile: {path}")
        settings = document.get("settings")
        if not isinstance(settings, dict):
            raise ValueError(f"invalid run profile: {path}")
        return settings

    def _session_path(self, session_id: str) -> Path:
        """Resolve a validated Session-local path without allowing traversal."""
        if not session_id or "/" in session_id or "\\" in session_id:
            raise ValueError("invalid session_id")
        return self._root / "sessions" / session_id / "run-profile.json"

    def _validated(self, values: Mapping[str, Any], *, partial: bool) -> dict[str, Any]:
        """Normalize supported fields and reject unknown or ill-typed settings.

        Args:
            values: Candidate profile object from a store/API caller.
            partial: When true, omit defaults for a sparse override read.

        Returns:
            A new JSON-safe profile mapping; input is never modified.

        Raises:
            ValueError: If a field is unknown, missing required shape, or out
                of supported numeric range.
        """
        if not isinstance(values, Mapping):
            raise ValueError("run profile must be an object")
        unknown = set(values) - (set(DEFAULT_RUN_PROFILE) | LEGACY_CONNECTOR_FIELDS)
        if unknown:
            raise ValueError(f"unknown run-profile fields: {', '.join(sorted(unknown))}")
        result: dict[str, Any] = {} if partial else dict(DEFAULT_RUN_PROFILE)
        for key, value in values.items():
            if key in LEGACY_CONNECTOR_FIELDS | {"system_prompt"}:
                if not isinstance(value, str):
                    raise ValueError(f"{key} must be a string")
                result[key] = value
            elif key == "temperature":
                if not isinstance(value, (int, float)) or isinstance(value, bool) or not 0 <= value <= 2:
                    raise ValueError("temperature must be between 0 and 2")
                result[key] = float(value)
            elif key == "thinking_mode":
                if value not in {"auto", "on", "off"}:
                    raise ValueError("thinking_mode must be auto, on, or off")
                result[key] = value
            elif key == "reasoning_effort":
                if value not in {"auto", "low", "medium", "high"}:
                    raise ValueError("reasoning_effort must be auto, low, medium, or high")
                result[key] = value
            elif key == "request_timeout_seconds":
                if (
                    not isinstance(value, (int, float))
                    or isinstance(value, bool)
                    or not math.isfinite(value)
                    or not 1 <= value <= 3600
                ):
                    raise ValueError("request_timeout_seconds must be between 1 and 3600")
                result[key] = float(value)
            elif key == "shell_network_mode":
                # The accepted vocabulary mirrors
                # ``tool_module.session_sandbox._NETWORK_MODES``. It is spelled
                # out here instead of imported because settings must not depend
                # on the OS sandbox implementation, and a persisted profile
                # outlives either module.
                if value not in {"isolated", "host_network"}:
                    raise ValueError("shell_network_mode must be isolated or host_network")
                result[key] = value
            elif key in {"max_tokens", "max_retries", "max_context_threshold", "compaction_output_max_tokens", "context_keep_recent", "tool_result_context_limit", "max_swarm_agents", "max_rounds"}:
                if not isinstance(value, int) or isinstance(value, bool) or value < 0:
                    raise ValueError(f"{key} must be a non-negative integer")
                if key in {"max_tokens", "compaction_output_max_tokens"} and value < 1:
                    raise ValueError(f"{key} must be at least 1")
                result[key] = value
            elif key == "agent_overrides":
                if not isinstance(value, dict):
                    raise ValueError("agent_overrides must be an object")
                overrides: dict[str, dict[str, int]] = {}
                allowed = {"max_rounds", "max_tokens", "max_context_threshold"}
                for name, override in value.items():
                    if not isinstance(name, str) or not name.strip():
                        raise ValueError("agent_overrides names must be non-empty strings")
                    if not isinstance(override, dict):
                        raise ValueError(f"agent_overrides[{name}] must be an object")
                    unknown_override = set(override) - allowed
                    if unknown_override:
                        raise ValueError(
                            f"unknown agent override fields for {name}: {', '.join(sorted(unknown_override))}"
                        )
                    normalized: dict[str, int] = {}
                    for override_key, override_value in override.items():
                        if (
                            not isinstance(override_value, int)
                            or isinstance(override_value, bool)
                            or override_value < 0
                        ):
                            raise ValueError(f"{override_key} override for {name} must be a non-negative integer")
                        if override_key == "max_tokens" and override_value < 1:
                            raise ValueError(f"max_tokens override for {name} must be at least 1")
                        if override_key == "max_context_threshold" and override_value < 1024:
                            raise ValueError(f"max_context_threshold override for {name} must be at least 1024")
                        normalized[override_key] = override_value
                    overrides[name.strip()] = normalized
                result[key] = overrides
            elif key == "context_handler":
                # Keep unknown IDs readable so a newer handler can be added
                # without making an existing profile impossible to edit.
                if not isinstance(value, str) or not value.strip():
                    raise ValueError("context_handler must be a non-empty string")
                result[key] = value.strip()
            elif key == "context_handler_settings":
                if not isinstance(value, dict):
                    raise ValueError("context_handler_settings must be an object")
                normalized: dict[str, dict[str, Any]] = {}
                for handler, settings in value.items():
                    if not isinstance(handler, str) or not handler.strip() or not isinstance(settings, dict):
                        raise ValueError("context_handler_settings must map handler names to objects")
                    normalized[handler.strip()] = dict(settings)
                result[key] = normalized
            elif key == "context_block_order":
                if not isinstance(value, dict):
                    raise ValueError("context_block_order must be an object")
                normalized_order: dict[str, int] = {}
                for source, priority in value.items():
                    if not isinstance(source, str) or not source.strip():
                        raise ValueError("context_block_order sources must be non-empty strings")
                    if isinstance(priority, bool) or not isinstance(priority, int):
                        raise ValueError("context_block_order priorities must be integers")
                    # Existence is deliberately not checked: a plugin provider
                    # may be absent on this machine while its saved position
                    # remains valid for a later run.
                    normalized_order[source.strip()] = priority
                result[key] = normalized_order
            elif key.endswith("_sessions"):
                if not isinstance(value, list) or not all(isinstance(item, str) and item for item in value):
                    raise ValueError(f"{key} must be a list of session IDs")
                result[key] = list(dict.fromkeys(value))
            elif key == "tool_permissions":
                if not isinstance(value, dict):
                    raise ValueError("tool_permissions must be an object")
                default_permissions = DEFAULT_RUN_PROFILE["tool_permissions"]
                submitted_categories = value.get("categories", {})
                submitted_tools = value.get("tools", {})
                if not isinstance(submitted_categories, dict) or not isinstance(submitted_tools, dict):
                    raise ValueError("tool_permissions categories and tools must be objects")
                # New restored capabilities are on by default even for an old
                # saved `{categories:{}, tools:{}}`; an explicit false remains
                # authoritative and therefore still supports least privilege.
                granted: dict[str, dict[str, Any]] = {
                    "categories": {**default_permissions["categories"], **submitted_categories},
                    "tools": {**default_permissions["tools"], **submitted_tools},
                }
                # Cross-check against what providers really registered.  Such a
                # stale key already grants nothing at run time, but persisting
                # it would keep a UI switch alive for a capability that is gone.
                registered = self._registered_grants()
                result[key] = granted if registered is None else _prune_grants(granted, *registered)
        return result

    def _registered_grants(self) -> tuple[frozenset[str], frozenset[str]] | None:
        """Return the category and Tool IDs the live registry knows.

        Returns:
            ``(category_ids, tool_ids)``, or ``None`` when no reader is bound,
            the reader fails, or the catalog is still empty.  An empty catalog
            means no provider registered yet; pruning against it would delete
            every grant, so it is treated the same as an unbound store.

        Notes:
            Reading a profile must never fail because a Tool provider is broken,
            so every catalog error degrades to the legacy tolerant behaviour.
        """
        reader = self._tool_catalog
        if reader is None:
            return None
        try:
            categories = tuple(getattr(reader(), "categories", ()) or ())
            category_ids = frozenset(item.id for item in categories)
            tool_ids = frozenset(
                tool.id
                for item in categories
                for tool in getattr(item, "tools", ()) or ()
            )
        except Exception:  # A settings read may never fail on registry state.
            return None
        if not category_ids:
            return None
        return category_ids, tool_ids


def _prune_grants(
    granted: Mapping[str, Mapping[str, Any]],
    category_ids: frozenset[str],
    tool_ids: frozenset[str],
) -> dict[str, dict[str, Any]]:
    """Keep only grant keys that can still mean something.

    Unknown non-Plugin keys are discarded instead of rejected or marked: the
    settings UI only submits keys it learned from ``GET /api/tool-registry``, so
    an unknown key is stale state or a client bug rather than operator intent.
    ``PUT`` also replaces the complete profile, so rejecting would turn one
    stale key into a permanent 422 for every later save of that scope.

    Args:
        granted: Merged ``categories``/``tools`` grant maps.
        category_ids: Category IDs currently registered by Tool providers.
        tool_ids: Tool IDs currently registered by Tool providers.

    Returns:
        New grant maps; input maps, keys, and values are never modified.
    """
    categories = {
        name: enabled
        for name, enabled in granted.get("categories", {}).items()
        if isinstance(name, str)
        and (
            name in category_ids
            or name in LEGACY_CATEGORY_GRANT_IDS
            or name == LEGACY_PLUGIN_CATEGORY
            or name.startswith(PLUGIN_PERMISSION_PREFIX)
        )
    }
    tools = {
        name: enabled
        for name, enabled in granted.get("tools", {}).items()
        if isinstance(name, str)
        and (
            name in tool_ids
            or name in LEGACY_TOOL_GRANT_IDS
            or name in POLICY_ONLY_TOOL_GRANT_IDS
            or name.startswith(PLUGIN_PERMISSION_PREFIX)
        )
    }
    return {"categories": categories, "tools": tools}
