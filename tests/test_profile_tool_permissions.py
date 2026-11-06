"""Contract tests for cross-validating run-profile tool grants against the registry."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from angelus.api import include_api_routes
from angelus.core import AngelusCore
from angelus.modules.settings_module.profile_store import (
    DEFAULT_RUN_PROFILE,
    LEGACY_TOOL_GRANT_IDS,
    POLICY_ONLY_TOOL_GRANT_IDS,
    RunProfileStore,
)
from angelus.modules.tool_module.tool_policy import _LEGACY_TOOL_IDS


@dataclass(frozen=True)
class _Tool:
    """Minimal Tool definition stand-in exposing the read attribute."""

    id: str


@dataclass(frozen=True)
class _Category:
    """Minimal catalog category stand-in exposing ID and Tools."""

    id: str
    tools: tuple[_Tool, ...] = ()


@dataclass(frozen=True)
class _Catalog:
    """Minimal catalog stand-in accepted by the structural Protocol."""

    categories: tuple[_Category, ...]


def _small_catalog() -> _Catalog:
    """Return a catalog whose only registered family is ``shell``."""
    return _Catalog((_Category("shell", (_Tool("shell"),)),))


def _bound_store(tmp_path: Path) -> RunProfileStore:
    """Return a store bound to a catalog that knows only ``shell``."""
    return RunProfileStore(tmp_path / "state", tool_catalog=_small_catalog)


def test_unknown_non_plugin_grants_are_dropped(tmp_path):
    """A stale category or Tool key is discarded instead of persisted."""
    store = _bound_store(tmp_path)
    saved = store.replace_global({
        "tool_permissions": {
            "categories": {"shell": True, "ctf_missing_category": True},
            "tools": {"shell": True, "ctf_create": True, "ctf_delete": True, "ctf_index": True},
        },
    })["tool_permissions"]
    assert saved["categories"] == {"shell": True}
    assert saved["tools"] == {"shell": True, "mcp": True}
    # The pruned document is what a later read returns, so the UI can no longer
    # offer a switch for a capability that has no provider.
    assert store.global_profile()["tool_permissions"] == saved


def test_unloaded_plugin_grants_survive_pruning(tmp_path):
    """``plugin.*`` keys stay even though no Plugin provider is registered."""
    store = _bound_store(tmp_path)
    submitted = {
        "categories": {"shell": True, "plugin.ghost.tools": True, "plugin": True},
        "tools": {"shell": True, "plugin.ghost.tools.echo": True},
    }
    saved = store.replace_global({"tool_permissions": submitted})["tool_permissions"]
    # Defaults are still merged in; the asserted keys are the submitted ones.
    assert saved["categories"] == submitted["categories"]
    assert saved["tools"] | submitted["tools"] == saved["tools"]
    # A reload from disk applies the same tolerance.
    assert store.global_profile()["tool_permissions"] == saved


def test_default_profile_has_no_orphan_grants(tmp_path):
    """Every default grant exists in the real registry (drift guard)."""
    core = AngelusCore(state_root=tmp_path / "state")
    catalog = core.tool_registry.catalog()
    registered_categories = {category.id for category in catalog.categories}
    registered_tools = {tool.id for category in catalog.categories for tool in category.tools}
    grants = DEFAULT_RUN_PROFILE["tool_permissions"]
    assert not {"ctf_create", "ctf_delete", "ctf_index"} & set(grants["tools"])
    assert set(grants["categories"]) <= registered_categories
    assert set(grants["tools"]) - registered_tools == set(POLICY_ONLY_TOOL_GRANT_IDS)


def test_legacy_grant_ids_mirror_tool_policy():
    """The local tolerance list cannot drift from ``ToolPolicy`` migration."""
    assert LEGACY_TOOL_GRANT_IDS == frozenset(_LEGACY_TOOL_IDS)


def test_legacy_document_with_alias_grants_stays_savable(tmp_path):
    """An old on-disk document is readable and re-savable after pruning."""
    state = tmp_path / "state"
    path = state / "settings" / "global-run-profile.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "schema_version": 1,
        "settings": {
            "tool_permissions": {
                "categories": {"context": True, "shell": True, "gone": True},
                "tools": {"plan_upsert": True, "plan_read": True, "ctf_create": True},
            },
        },
    }), encoding="utf-8")
    store = RunProfileStore(state, tool_catalog=_small_catalog)
    profile = store.global_profile()
    grants = profile["tool_permissions"]
    assert grants["categories"] == {"context": True, "shell": True}
    # Legacy aliases survive so ``ToolPolicy`` can still migrate them.
    assert {"plan_upsert", "plan_read", "mcp"} <= set(grants["tools"])
    assert "ctf_create" not in grants["tools"] and "gone" not in grants["categories"]
    # Saving the already-pruned effective profile must not raise a 422.
    assert store.replace_global(profile)["tool_permissions"] == grants


def test_empty_catalog_and_broken_reader_keep_legacy_tolerance(tmp_path):
    """Pruning never deletes every grant or fails because a provider broke."""
    submitted = {"categories": {"note_list": True, "ghost_category": True}, "tools": {"ghost_tool": True}}
    expected = {
        "categories": {**DEFAULT_RUN_PROFILE["tool_permissions"]["categories"], **submitted["categories"]},
        "tools": {**DEFAULT_RUN_PROFILE["tool_permissions"]["tools"], **submitted["tools"]},
    }
    # No provider has registered yet: pruning would delete every default grant.
    empty = RunProfileStore(tmp_path / "empty", tool_catalog=lambda: _Catalog(()))
    assert empty.replace_global({"tool_permissions": submitted})["tool_permissions"] == expected

    def _broken() -> _Catalog:
        raise RuntimeError("registry unavailable")

    broken = RunProfileStore(tmp_path / "broken", tool_catalog=_broken)
    assert broken.replace_global({"tool_permissions": submitted})["tool_permissions"] == expected


def test_binding_is_replaceable_and_detachable(tmp_path):
    """Binding follows registry changes; reads prune, bound writes persist."""
    store = RunProfileStore(tmp_path / "state")
    submitted = {"categories": {"plugin.ghost": True}, "tools": {"ghost_tool": True}}
    # Unbound: the legacy tolerant merge keeps any key.
    assert store.replace_global({"tool_permissions": submitted})["tool_permissions"]["tools"]["ghost_tool"] is True
    # Binding prunes on read, but a read never rewrites the durable document.
    store.bind_tool_catalog(_small_catalog)
    assert "ghost_tool" not in store.global_profile()["tool_permissions"]["tools"]
    store.bind_tool_catalog(None)
    assert store.global_profile()["tool_permissions"]["tools"]["ghost_tool"] is True
    # A bound save persists the pruned result, so detaching cannot bring it back.
    store.bind_tool_catalog(_small_catalog)
    store.replace_global(store.global_profile())
    store.bind_tool_catalog(None)
    assert "ghost_tool" not in store.global_profile()["tool_permissions"]["tools"]


def _client(tmp_path: Path) -> tuple[TestClient, AngelusCore]:
    """Build an HTTP client over one real core and one existing Session."""
    core = AngelusCore(state_root=tmp_path / "state")
    core.session_service.create("session-grants", "Grants")
    app = FastAPI()
    include_api_routes(app, core)
    return TestClient(app), core


def test_http_global_profile_put_prunes_unknown_grants(tmp_path):
    """The settings API binds the live registry before writing a profile."""
    client, _ = _client(tmp_path)
    response = client.put("/api/settings/run-profile", json={
        "settings": {
            "tool_permissions": {
                "categories": {"shell": True, "ghost_category": True, "plugin.ghost.tools": True},
                "tools": {"shell": True, "ghost_tool": True, "plugin.ghost.tools.echo": True},
            },
        },
    })
    assert response.status_code == 200, response.text
    grants = response.json()["effective"]["tool_permissions"]
    assert "ghost_category" not in grants["categories"]
    assert "ghost_tool" not in grants["tools"]
    assert grants["categories"]["shell"] is True
    assert grants["categories"]["plugin.ghost.tools"] is True
    assert grants["tools"]["plugin.ghost.tools.echo"] is True
    # Reads converge on the same pruned document.
    assert client.get("/api/settings/run-profile").json()["effective"]["tool_permissions"] == grants


def test_http_session_profile_put_keeps_plugin_and_rejects_unknown_session(tmp_path):
    """Session saves prune stale keys, tolerate Plugins, and keep 404 semantics."""
    client, _ = _client(tmp_path)
    response = client.put("/api/sessions/session-grants/run-profile", json={
        "settings": {
            "tool_permissions": {
                "categories": {"notes": True, "ghost_category": True, "plugin.ghost.tools": True},
                "tools": {"note_list": True, "ctf_create": True, "plugin.ghost.tools.echo": True},
            },
        },
    })
    assert response.status_code == 200, response.text
    grants = response.json()["effective"]["tool_permissions"]
    assert "ghost_category" not in grants["categories"]
    assert "ctf_create" not in grants["tools"]
    assert grants["categories"]["plugin.ghost.tools"] is True
    assert grants["tools"]["plugin.ghost.tools.echo"] is True
    missing = client.put("/api/sessions/ghost-session/run-profile", json={"settings": {}})
    assert missing.status_code == 404
    invalid = client.put("/api/settings/run-profile", json={"settings": {"temperature": 9}})
    assert invalid.status_code == 422
    assert pytest.approx(0.4) == DEFAULT_RUN_PROFILE["temperature"]
