"""Regression coverage for phase-one External Agent Hub contracts and routes."""

from __future__ import annotations

import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import cast
import unittest
from dataclasses import dataclass

from llmfetcher.context_handlers.linear import ContextHandlerLinear, read_persisted_context_page

from angelus.api.external_agent_hub import create_external_agent, delete_external_agent, discover_external_agent_processes, external_agent_health, get_external_agent
from angelus.core import AngelusCore
from angelus.modules.external_agent_hub_module import (
    ContextMessage,
    ContextPackage,
    ContextToolCall,
    ExternalAgentAdapterRegistry,
    ExternalAgentCapability,
    ExternalAgentDefinition,
    ExternalAgentHealth,
    ExternalAgentHubService,
    ExternalAgentProcessDiscovery,
    ExternalAgentSession,
    ExternalAgentHubStore,
)


class FakeCodexAdapter:
    """Deterministic adapter used to verify the Hub base contract."""

    @property
    def kind(self) -> str:
        """Return the protocol kind owned by this fake adapter.

        Returns:
            Codex App Server adapter identifier.
        """
        return "codex_app_server"

    def health(self, definition: ExternalAgentDefinition) -> ExternalAgentHealth:
        """Return a deterministic healthy projection.

        Args:
            definition: Configured external Agent being probed.

        Returns:
            Healthy observation for the configured definition.
        """
        return ExternalAgentHealth(definition.id, "codex_app_server", "healthy", "reachable")

    def discover_capabilities(self, definition: ExternalAgentDefinition) -> tuple[ExternalAgentCapability, ...]:
        """Return one non-executing capability declaration.

        Args:
            definition: Configured external Agent being inspected.

        Returns:
            One test capability declaration.
        """
        return (ExternalAgentCapability("thread", "Thread inspection", "Read a remote thread without dispatching work.", "tool"),)

    def discover_sessions(self, definition: ExternalAgentDefinition, limit: int) -> tuple[ExternalAgentSession, ...]:
        """Return one bounded remote thread summary.

        Args:
            definition: Configured external Agent being inspected.
            limit: Maximum requested summary count.

        Returns:
            One summary when the requested bound permits it.
        """
        if limit < 1:
            return ()
        return (ExternalAgentSession(definition.id, "thread-1", "First thread", "idle", 1_700_000_000_000),)


@dataclass(frozen=True)
class CoreState:
    """Minimal FastAPI-like state object for direct route contract tests."""

    angelus_core: AngelusCore


@dataclass(frozen=True)
class ApplicationContext:
    """Minimal application object exposing the route's required state field."""

    state: CoreState


@dataclass(frozen=True)
class RequestContext:
    """Minimal request object exposing the route's required app property."""

    app: ApplicationContext


class _NoopCompactor:
    """Stand-in compactor so tests can read a checkpoint without LLM calls."""


def _configured_core(root: Path) -> AngelusCore:
    """Build one Session whose coordinator Agent owns a real context checkpoint.

    The helper is safe to call twice with the same ``root``: that models a host
    restart, where the connector and Session already exist durably and only the
    in-memory Agents are rebuilt.

    Args:
        root: Temporary state root receiving connector, Session, and context.

    Returns:
        Core whose ``demo`` Session has a materialized ``coordinator`` Agent.
    """
    core = AngelusCore(state_root=root)
    # A restart reopens the same state root, so reuse the connector recorded by
    # the first build instead of failing the catalog's duplicate-name check.
    existing = core.connectors.list()
    connector_id = existing[0].id if existing else core.connectors.create({
        "name": "round-trip",
        "provider": "openai",
        "model": "round-trip-model",
        "api_key": "sk-round-trip",
    }).id
    if not core.sessions.exists("demo"):
        core.session_service.create("demo", "Demo")
    core.run_profiles.replace_session("demo", {"connector_id": connector_id})
    core.session_service.ensure_coordinator("demo")
    return core


def _checkpoint_path(root: Path) -> Path:
    """Return the durable coordinator context pointer beneath a state root.

    Args:
        root: Temporary state root used to build the Session.

    Returns:
        Path of the coordinator's ``context.json`` pointer file.
    """
    return root / "sessions" / "demo" / "agents" / "coordinator" / "context.json"


class ExternalAgentHubTests(unittest.TestCase):
    """Assert persistence, adapter isolation, and HTTP response boundaries."""

    def test_store_persists_definitions_and_service_reports_adapter_state(self) -> None:
        """Definitions survive a store reload and use registered adapters.

        Returns:
            ``None`` after validating durable definitions and adapter results.
        """
        with TemporaryDirectory() as directory:
            root = Path(directory)
            adapters = ExternalAgentAdapterRegistry()
            adapters.register(FakeCodexAdapter())
            service = ExternalAgentHubService(ExternalAgentHubStore(root), adapters)
            created = service.create(ExternalAgentDefinition(
                "codex-local", "Local Codex", "codex_app_server", "unix:///tmp/codex.sock", "codex-connector", True, "Local development runtime.",
            ))
            self.assertEqual("codex-local", created.id)
            restored = ExternalAgentHubService(ExternalAgentHubStore(root), adapters)
            self.assertEqual("Local Codex", restored.get("codex-local").title)
            self.assertEqual("healthy", restored.health("codex-local").status)
            self.assertEqual("thread", restored.capabilities("codex-local")[0].id)
            self.assertEqual("thread-1", restored.sessions("codex-local", 5)[0].external_id)

    def test_unimplemented_adapter_reports_unsupported_without_network_io(self) -> None:
        """Unregistered protocols have explicit non-success health states.

        Returns:
            ``None`` after asserting no protocol fallback is attempted.
        """
        with TemporaryDirectory() as directory:
            service = ExternalAgentHubService(ExternalAgentHubStore(Path(directory)), ExternalAgentAdapterRegistry())
            service.create(ExternalAgentDefinition("coze-bot", "Coze Bot", "coze"))
            health = service.health("coze-bot")
            self.assertEqual("unsupported", health.status)
            self.assertEqual((), service.capabilities("coze-bot"))

    def test_core_registers_inert_vendor_adapters_without_dispatching_work(self) -> None:
        """Core exposes vendor adapter health without starting a remote run.

        Returns:
            ``None`` after confirming an unconfigured Coze adapter is explicit.
        """
        with TemporaryDirectory() as directory:
            core = AngelusCore(state_root=Path(directory))
            core.external_agent_hub.create(ExternalAgentDefinition("coze-local", "Coze", "coze"))
            health = core.external_agent_hub.health("coze-local")
            self.assertEqual("unavailable", health.status)
            self.assertIn("not configured", health.message)

    def test_route_functions_project_crud_and_health_without_connector_secrets(self) -> None:
        """Route functions persist metadata and expose no secret field.

        Returns:
            ``None`` after exercising CRUD and unsupported health routes.
        """
        with TemporaryDirectory() as directory:
            request = RequestContext(ApplicationContext(CoreState(AngelusCore(state_root=Path(directory)))))
            body = {
                "id": "codex-local",
                "title": "Local Codex",
                "adapter_kind": "codex_app_server",
                "endpoint": "unix:///tmp/codex.sock",
                "connector_id": "codex-connector",
                "description": "Local runtime",
            }
            response = create_external_agent(request, body)
            self.assertNotIn("api_key", str(response))
            self.assertEqual("unavailable", external_agent_health("codex-local", request)["health"]["status"])
            delete_external_agent("codex-local", request)
            with self.assertRaises(Exception):
                get_external_agent("codex-local", request)

    def test_process_discovery_returns_bounded_non_attachable_candidates(self) -> None:
        """Known procfs commands become safe user-confirmed Hub candidates.

        Returns:
            ``None`` after confirming discovery exposes no attach control and
            redacts obvious command-line credentials.
        """
        with TemporaryDirectory() as directory:
            proc_root = Path(directory)
            process = proc_root / "417"
            process.mkdir()
            (process / "cmdline").write_bytes(b"/usr/local/bin/codex\0--token\0very-secret\0")
            candidates = ExternalAgentProcessDiscovery(proc_root).discover()
            self.assertEqual(1, len(candidates))
            self.assertEqual("codex_app_server", candidates[0].adapter_kind)
            self.assertFalse(candidates[0].attachable)
            self.assertNotIn("very-secret", candidates[0].command)
            self.assertEqual("stdio://", candidates[0].endpoint)

    def test_discovery_route_returns_ephemeral_candidate_projections(self) -> None:
        """The discovery route projects candidates without writing Hub state.

        Returns:
            ``None`` after confirming the route returns a candidate collection
            and does not create a durable Hub definition.
        """
        with TemporaryDirectory() as directory:
            request = RequestContext(ApplicationContext(CoreState(AngelusCore(state_root=Path(directory)))))
            response = discover_external_agent_processes(request)
            self.assertIn("candidates", response)
            self.assertEqual((), request.app.state.angelus_core.external_agent_hub.list())

    def test_import_package_persists_typed_items_and_round_trips_to_export(self) -> None:
        """An imported package survives save, reload, paged read, and export.

        Returns:
            ``None`` after asserting the import reaches durable storage as typed
            context items instead of a legacy message dict.
        """
        with TemporaryDirectory() as directory:
            root = Path(directory)
            core = _configured_core(root)
            package = ContextPackage(
                format_version=1,
                source="external-test",
                source_session_id="thread-1",
                source_agent="assistant",
                messages=(
                    ContextMessage(sequence=1, role="user", content="imported question"),
                    ContextMessage(
                        sequence=2,
                        role="assistant",
                        content="imported answer",
                        reasoning="imported reasoning",
                        tool_calls=(ContextToolCall("shell", "{}", "ok"),),
                    ),
                ),
            )

            result = core.context_exchange_service.append_package("demo", "coordinator", package)

            self.assertEqual("import", result.direction)
            self.assertEqual(2, result.accepted_messages)
            self.assertEqual(0, result.rejected_messages)

            checkpoint = _checkpoint_path(root)
            self.assertTrue(checkpoint.is_file())
            # New API writes the SQLite pointer layout, so the round counter and
            # item count are the durable proof that both records were persisted.
            pointer = json.loads(checkpoint.read_text(encoding="utf-8"))
            self.assertEqual("sqlite", pointer["storage"])
            self.assertEqual("context.json.sqlite3", pointer["database"])
            self.assertEqual(2, pointer["round"])
            self.assertEqual(2, pointer["message_count"])

            reloaded = ContextHandlerLinear(_NoopCompactor())
            self.assertTrue(reloaded.load(checkpoint))
            self.assertEqual(
                ["UserContextItem", "AssistantContextItem"],
                [type(item).__name__ for item in reloaded.messages],
            )
            self.assertEqual(
                ["imported question", "imported answer"],
                [item.content for item in reloaded.messages],
            )
            self.assertEqual("imported reasoning", reloaded.messages[1].reasoning)

            page, cursor, total = read_persisted_context_page(checkpoint)
            self.assertEqual(2, total)
            self.assertEqual([1, 2], [item.timeline for item in page])
            self.assertIsNone(cursor)

            exported, next_cursor, has_more = core.context_exchange_service.export_page(
                "demo", "coordinator", None, 50,
            )
            self.assertEqual(["user", "assistant"], [item.role for item in exported.messages])
            self.assertEqual(
                ["imported question", "imported answer"],
                [item.content for item in exported.messages],
            )
            self.assertIsNone(next_cursor)
            self.assertFalse(has_more)

    def test_import_counts_unrepresentable_roles_as_rejected_without_dropping_history(self) -> None:
        """Roles with no durable item equivalent are counted, never dropped silently.

        Returns:
            ``None`` after asserting system/tool/unknown roles raise the rejected
            count while representable history still persists.
        """
        with TemporaryDirectory() as directory:
            root = Path(directory)
            core = _configured_core(root)
            package = ContextPackage(
                format_version=1,
                source="external-test",
                source_session_id="thread-1",
                source_agent="assistant",
                messages=(
                    ContextMessage(sequence=1, role="system", content="system prompt"),
                    ContextMessage(sequence=2, role="user", content="kept question"),
                    ContextMessage(sequence=3, role="tool", content="tool transcript"),
                    # Out-of-vocabulary roles must be rejected, not coerced.
                    ContextMessage(sequence=4, role=cast("ContextRole", "moderator"), content="odd role"),
                    ContextMessage(sequence=5, role="assistant", content="kept answer"),
                ),
            )

            result = core.context_exchange_service.append_package("demo", "coordinator", package)

            self.assertEqual(2, result.accepted_messages)
            self.assertEqual(3, result.rejected_messages)

            pointer = json.loads(_checkpoint_path(root).read_text(encoding="utf-8"))
            self.assertEqual(2, pointer["message_count"])
            page, _, total = read_persisted_context_page(_checkpoint_path(root))
            self.assertEqual(2, total)
            self.assertEqual(
                ["kept question", "kept answer"],
                [item.content for item in page],
            )

    def test_repeated_import_appends_after_reload_instead_of_overwriting(self) -> None:
        """A later import continues the saved timeline rather than resetting it.

        Returns:
            ``None`` after asserting earlier imported history is still readable
            from a freshly constructed handler.
        """
        with TemporaryDirectory() as directory:
            root = Path(directory)
            core = _configured_core(root)
            core.context_exchange_service.append_package("demo", "coordinator", ContextPackage(
                format_version=1,
                source="external-test",
                source_session_id="thread-1",
                source_agent="assistant",
                messages=(
                    ContextMessage(sequence=1, role="user", content="first user"),
                    ContextMessage(sequence=2, role="assistant", content="first assistant"),
                ),
            ))

            # A host restart rebuilds the Agent without running it, so the second
            # import must rehydrate the checkpoint before appending to it.
            restarted = _configured_core(Path(directory))
            result = restarted.context_exchange_service.append_package(
                "demo", "coordinator", ContextPackage(
                    format_version=1,
                    source="external-test",
                    source_session_id="thread-1",
                    source_agent="assistant",
                    messages=(ContextMessage(sequence=3, role="user", content="second user"),),
                ),
            )

            self.assertEqual(1, result.accepted_messages)
            page, _, total = read_persisted_context_page(_checkpoint_path(root))
            self.assertEqual(3, total)
            self.assertEqual(
                ["first user", "first assistant", "second user"],
                [item.content for item in page],
            )
            self.assertEqual([1, 2, 3], [item.timeline for item in page])


if __name__ == "__main__":
    unittest.main()
