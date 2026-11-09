"""Backend contracts for the steer control entry point and its projection fold.

The suite covers two layers that were previously untested:

* the thin HTTP adapter in :mod:`angelus.api.runs`, driven through a real
  ``AngelusCore`` with ``TestClient`` (404 / 409 / 422 mapping plus the text-only
  image guard and the wire defaults);
* the pure projection fold that turns ``agent:control`` /
  ``agent:steer_applied`` journal facts into durable steering records.

Neither layer needs a live LLM call, so no test here starts a real run and no
test stubs the code under test: the HTTP tests exercise the real route and the
real ``execution_service.control`` refusal path, and the fold tests call the real
static helpers with real journal-shaped events.  The successful 200 steering
path is deliberately left to a future integration test, because it needs a live
Agent graph.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from angelus.api import include_api_routes
from angelus.api.runs import AgentControlRequest, _status_wire
from angelus.core import AngelusCore
from angelus.modules.console_module.projection_service.service import ConsoleProjectionService
from angelus.modules.execution_module import ExecutionSnapshot, ExecutionState

# The exact detail string the frontend uses to split "no run yet" from every
# other 409 cause, so it is pinned verbatim instead of matched loosely.
_NO_BOUNDARY_DETAIL = "Session has no active Agent control boundary"
_IMAGE_DETAIL = "Image steering is not supported; send images with a new run request instead"
_SESSION_ID = "session-steer"
_MISSING_SESSION_ID = "session-missing"

# Wire-level states the run projection treats as "a boundary can accept control".
_ACTIVE_STATES = (
    ExecutionState.QUEUED,
    ExecutionState.PREPARING,
    ExecutionState.MATERIALIZING_TOOLS,
    ExecutionState.CONNECTING_MCP,
    ExecutionState.MATERIALIZING_SWARM,
    ExecutionState.LOADING_CONTEXT,
    ExecutionState.RUNNING,
    ExecutionState.STOPPING,
    ExecutionState.FORCE_STOPPING,
)

_TERMINAL_STATES = (
    ExecutionState.IDLE,
    ExecutionState.COMPLETED,
    ExecutionState.STOPPED,
    ExecutionState.INTERRUPTED,
    ExecutionState.FAILED,
)


def _client(tmp_path: Path) -> tuple[TestClient, FastAPI, AngelusCore]:
    """Return an HTTP client over one real core holding one idle Session."""
    core = AngelusCore(state_root=tmp_path / "state")
    core.session_service.create(_SESSION_ID, "Steer")
    app = FastAPI()
    include_api_routes(app, core)
    return TestClient(app), app, core


def _session_exists(core: AngelusCore, session_id: str) -> bool:
    """Return whether ``session_id`` is registered, without raising."""
    try:
        core.sessions.get(session_id)
    except KeyError:
        return False
    return True


def _snapshot(state: ExecutionState, *, execution_id: str | None = None) -> ExecutionSnapshot:
    """Return a real immutable snapshot in ``state`` for projection assertions."""
    return ExecutionSnapshot(
        session_id="session-wire",
        execution_id=execution_id,
        attempt=2,
        state=state,
        started_at=None,
        finished_at=None,
        error=None,
    )


def _journal_event(
    event_type: str,
    data: Any,
    *,
    agent: str = "",
    message: str = "",
    timestamp: float | None = 1.0,
) -> dict[str, Any]:
    """Return one event shaped exactly like ``ExecutionJournal.append`` output."""
    return {
        "event_id": f"event-{event_type}-{timestamp}",
        "execution_id": "execution-1",
        "type": event_type,
        "timestamp": timestamp,
        "agent": agent,
        "message": message,
        "usage": {"input": 0, "output": 0, "total": 0, "cached": 0, "reasoning": 0},
        "duration_ms": None,
        "data": data,
    }


def _control_event(
    *,
    steer_id: Any = "s1",
    targets: Any = None,
    agent_id: Any = "all",
    action: str = "steer",
    message: str = "Check the north wall.",
    timestamp: float | None = 1.0,
) -> dict[str, Any]:
    """Return one ``agent:control`` steer fact with overridable malformed fields."""
    data: dict[str, Any] = {
        "agent_id": agent_id,
        "action": action,
        "target_agents": ["a", "b"] if targets is None else targets,
        "reason": "user_requested",
    }
    if steer_id is not None:
        data["steer_id"] = steer_id
    return _journal_event("agent:control", data, agent=str(agent_id), message=message, timestamp=timestamp)


def _applied_event(agent: str, steer_ids: Any, *, timestamp: float = 2.0) -> dict[str, Any]:
    """Return one ``agent:steer_applied`` fact for ``agent``."""
    return _journal_event("agent:steer_applied", {"steer_ids": steer_ids}, agent=agent, timestamp=timestamp)


def _fold(events: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Fold events through the production reducer and return its public records."""
    records: dict[str, dict[str, object]] = {}
    for event in events:
        ConsoleProjectionService._reduce_steering_event(records, event)
    return ConsoleProjectionService._steering_records(records)


# ---------------------------------------------------------------------------
# A. HTTP routing layer
# ---------------------------------------------------------------------------


def test_steer_unknown_session_returns_404(tmp_path):
    """A control command for an unregistered Session is a missing resource."""
    client, _app, core = _client(tmp_path)
    assert not _session_exists(core, _MISSING_SESSION_ID)

    response = client.post(
        f"/api/runs/{_MISSING_SESSION_ID}/control",
        json={"action": "steer", "message": "x"},
    )

    assert response.status_code == 404, response.text
    assert response.json() == {"detail": "Unknown session"}
    # Still unknown: the route must not have created or half-registered it.
    assert not _session_exists(core, _MISSING_SESSION_ID)


def test_steer_without_active_run_returns_409_with_pinned_detail(tmp_path):
    """An existing Session with no live Agent boundary answers 409, not 200."""
    client, _app, core = _client(tmp_path)
    session = core.sessions.get(_SESSION_ID)
    # Preconditions: the Session is registered, its attempt is idle, and no
    # Agent control view has been published for a live run.
    assert session.execution is not None
    assert session.execution.snapshot().state is ExecutionState.IDLE
    assert session.run_control is None

    response = client.post(
        f"/api/runs/{_SESSION_ID}/control",
        json={"action": "steer", "message": "Focus on the harbour."},
    )

    assert response.status_code == 409, response.text
    assert response.json() == {"detail": _NO_BOUNDARY_DETAIL}
    # A refused command must not fabricate a boundary or start an attempt.
    assert session.run_control is None
    assert session.execution.snapshot().state is ExecutionState.IDLE


def test_steer_without_boundary_rejects_every_action_the_same_way(tmp_path):
    """stop / force_stop are refused identically while no run is live."""
    client, _app, _core = _client(tmp_path)

    for action in ("stop", "force_stop"):
        response = client.post(
            f"/api/runs/{_SESSION_ID}/control",
            json={"action": action, "reason": "user_requested"},
        )
        assert response.status_code == 409, (action, response.text)
        assert response.json() == {"detail": _NO_BOUNDARY_DETAIL}


def test_steer_images_are_rejected_with_422_before_the_service_runs(tmp_path, monkeypatch):
    """Steering stays text-only: an attached image never reaches the service."""
    client, _app, core = _client(tmp_path)
    calls: list[tuple[object, ...]] = []

    def _record_call(*args: object, **_kwargs: object) -> object:
        """Record any service invocation, then make the mistake visible."""
        calls.append(args)
        raise AssertionError("execution_service.control must not run for image steering")

    monkeypatch.setattr(core.execution_service, "control", _record_call)

    response = client.post(
        f"/api/runs/{_SESSION_ID}/control",
        json={
            "action": "steer",
            "message": "Look at this.",
            "images": [{"attachment_id": "a" * 64, "media_type": "image/png"}],
        },
    )

    assert response.status_code == 422, response.text
    assert response.json() == {"detail": _IMAGE_DETAIL}
    assert calls == []


def test_steer_images_are_rejected_before_the_unknown_session_check(tmp_path):
    """The image guard precedes Session lookup, so 422 wins over the 404 path."""
    client, _app, core = _client(tmp_path)

    response = client.post(
        f"/api/runs/{_MISSING_SESSION_ID}/control",
        json={
            "action": "steer",
            "message": "Look at this.",
            "images": [{"attachment_id": "b" * 64, "media_type": "image/jpeg"}],
        },
    )

    assert response.status_code == 422, response.text
    assert response.json() == {"detail": _IMAGE_DETAIL}
    assert not _session_exists(core, _MISSING_SESSION_ID)


def test_control_request_defaults_are_broadcast_steer(tmp_path):
    """An omitted scope/action/reason means broadcast steer by user request."""
    request = AgentControlRequest()

    assert request.agent_id == "all"
    assert request.action == "steer"
    assert request.reason == "user_requested"
    assert request.message == ""
    assert request.images == []

    # The same defaults must survive the HTTP layer, so read the generated
    # OpenAPI schema rather than trusting the dataclass alone.
    _client_instance, app, _core = _client(tmp_path)
    properties = app.openapi()["components"]["schemas"]["AgentControlRequest"]["properties"]
    assert properties["agent_id"]["default"] == "all"
    assert properties["action"]["default"] == "steer"
    assert properties["reason"]["default"] == "user_requested"
    assert properties["message"]["default"] == ""


def test_control_defaults_are_accepted_by_the_route(tmp_path):
    """A body with no agent_id/action passes validation and reaches the 409 guard."""
    client, _app, _core = _client(tmp_path)

    response = client.post(f"/api/runs/{_SESSION_ID}/control", json={"message": "Continue."})

    # A defaulted request is valid input, so the only possible refusal here is
    # the missing Agent boundary (409) - never a 422 validation error.
    assert response.status_code == 409, response.text
    assert response.json() == {"detail": _NO_BOUNDARY_DETAIL}


def test_invalid_action_on_idle_session_reports_the_boundary_409_first(tmp_path):
    """Documents the current precedence: boundary check runs before action check.

    ``ExecutionService.control`` resolves the active boundary before it
    validates ``action``, so an idle Session answers 409 for a nonsense action
    too.  This test pins that order so a future reordering is a visible change.
    """
    client, _app, _core = _client(tmp_path)

    response = client.post(
        f"/api/runs/{_SESSION_ID}/control",
        json={"action": "kick", "message": "x"},
    )

    assert response.status_code == 409, response.text
    assert response.json() == {"detail": _NO_BOUNDARY_DETAIL}


@pytest.mark.parametrize("state", _ACTIVE_STATES)
def test_status_wire_marks_active_states_active(state):
    """Every pre-terminal lifecycle state reports ``active: true``."""
    wire = _status_wire(_snapshot(state))

    assert wire["state"] == state.value
    assert wire["status"] == state.value
    assert wire["active"] is True


@pytest.mark.parametrize("state", _TERMINAL_STATES)
def test_status_wire_marks_terminal_states_inactive(state):
    """Idle and every terminal state report ``active: false``."""
    wire = _status_wire(_snapshot(state))

    assert wire["state"] == state.value
    assert wire["status"] == state.value
    assert wire["active"] is False


def test_status_wire_active_set_covers_every_lifecycle_state():
    """Guard against a new lifecycle state silently defaulting to inactive."""
    covered = set(_ACTIVE_STATES) | set(_TERMINAL_STATES)

    assert covered == set(ExecutionState)


def test_status_wire_uses_execution_id_and_falls_back_to_session_id():
    """``run_id`` is the attempt identity when known, else the Session identity."""
    synthetic = _status_wire(_snapshot(ExecutionState.IDLE, execution_id=None))
    real = _status_wire(_snapshot(ExecutionState.RUNNING, execution_id="execution-9"))

    assert synthetic["run_id"] == "session-wire"
    assert real["run_id"] == "execution-9"
    assert real["session_id"] == "session-wire"
    assert real["started_at"] is None
    assert real["error"] is None


def test_status_endpoint_wire_shape_for_idle_session(tmp_path):
    """The status route exposes the documented keys with concrete types."""
    client, _app, _core = _client(tmp_path)

    response = client.get(f"/api/runs/{_SESSION_ID}/status")

    assert response.status_code == 200, response.text
    body = response.json()
    for key in (
        "run_id", "session_id", "status", "state", "active",
        "started_at", "finished_at", "error", "execution_id", "attempt",
    ):
        assert key in body, f"missing status key {key!r} in {body!r}"
    assert body["run_id"] == _SESSION_ID
    assert body["session_id"] == _SESSION_ID
    assert body["state"] == "idle"
    assert body["status"] == "idle"
    assert body["active"] is False
    assert body["execution_id"] is None
    assert isinstance(body["attempt"], int)
    assert body["started_at"] is None
    assert body["finished_at"] is None
    assert body["error"] is None


def test_status_endpoint_unknown_session_returns_404(tmp_path):
    """Status for an unregistered Session is a missing resource, not synthetic idle."""
    client, _app, _core = _client(tmp_path)

    response = client.get(f"/api/runs/{_MISSING_SESSION_ID}/status")

    assert response.status_code == 404, response.text
    assert response.json() == {"detail": "Unknown session"}


# ---------------------------------------------------------------------------
# B. Projection fold
# ---------------------------------------------------------------------------


def test_control_steer_folds_into_one_record_with_every_recipient():
    """One steer accepted by two Agents yields one record listing both."""
    records = _fold([
        _control_event(steer_id="s1", targets=["a", "b"], message="Check the north wall."),
        _applied_event("a", ["s1"]),
        _applied_event("b", ["s1"]),
    ])

    assert len(records) == 1
    record = records[0]
    assert record["id"] == "s1"
    assert record["text"] == "Check the north wall."
    assert record["scope"] == "all"
    assert record["recipients"] == ["a", "b"]
    assert record["applied_agents"] == ["a", "b"]
    assert record["submitted_at"] == 1.0


def test_repeated_applied_events_do_not_duplicate_agents():
    """Re-delivery of the same applied fact is idempotent."""
    records = _fold([
        _control_event(steer_id="s1", targets=["a", "b"]),
        _applied_event("a", ["s1"]),
        _applied_event("a", ["s1"]),
        _applied_event("a", ["s1", "s1"]),
        _applied_event("b", ["s1"]),
    ])

    assert len(records) == 1
    assert records[0]["applied_agents"] == ["a", "b"]


def test_control_event_without_steer_id_is_ignored():
    """A steer fact missing its identity cannot be tracked and is dropped."""
    records = _fold([
        _control_event(steer_id=None),
        _applied_event("a", ["s1"]),
    ])

    assert records == []


def test_control_event_with_non_list_targets_is_ignored():
    """Malformed recipient lists are dropped instead of aborting the fold."""
    records = _fold([
        _control_event(steer_id="s1", targets="a"),
        _control_event(steer_id="s2", targets={"a": True}),
        _control_event(steer_id="s3", targets=7),
    ])

    assert records == []


def test_control_event_filters_non_string_recipients():
    """Only string recipient identities survive into a record."""
    records = _fold([_control_event(steer_id="s1", targets=["a", 3, None, "b"])])

    assert len(records) == 1
    assert records[0]["recipients"] == ["a", "b"]
    assert records[0]["applied_agents"] == []


def test_control_event_scope_defaults_to_all_for_non_string_agent_id():
    """A non-string ``agent_id`` cannot become a scope and falls back to ``all``."""
    records = _fold([_control_event(steer_id="s1", targets=["a"], agent_id=5)])

    assert len(records) == 1
    assert records[0]["scope"] == "all"


def test_control_event_scope_keeps_a_concrete_agent_id():
    """A targeted steer keeps the concrete Agent identity as its scope."""
    records = _fold([_control_event(steer_id="s1", targets=["a"], agent_id="a")])

    assert len(records) == 1
    assert records[0]["scope"] == "a"


def test_non_steer_control_actions_are_not_steering_records():
    """Stop facts share the ``agent:control`` type but are not steering records."""
    records = _fold([
        _control_event(action="stop", steer_id="s1"),
        _control_event(action="force_stop", steer_id="s2"),
    ])

    assert records == []


def test_applied_event_with_unknown_steer_id_is_ignored():
    """An applied fact for an untracked steer never raises ``KeyError``."""
    records = _fold([
        _control_event(steer_id="s1", targets=["a"]),
        _applied_event("a", ["s1", "s-does-not-exist"]),
        _applied_event("ghost", ["s-does-not-exist"]),
    ])

    assert len(records) == 1
    assert records[0]["applied_agents"] == ["a"]


def test_applied_event_with_malformed_payload_is_ignored():
    """A non-list ``steer_ids`` or a missing payload cannot touch a record."""
    records = _fold([
        _control_event(steer_id="s1", targets=["a"]),
        _journal_event("agent:steer_applied", {"steer_ids": "s1"}, agent="a"),
        _journal_event("agent:steer_applied", {}, agent="a"),
        # A non-string envelope Agent is ignored as well.
        _journal_event("agent:steer_applied", {"steer_ids": ["s1"]}, agent=None),
    ])

    assert len(records) == 1
    assert records[0]["applied_agents"] == []


def test_blank_agent_identity_is_recorded_verbatim():
    """Current behaviour: an empty ``agent`` string counts as a real recipient.

    ``_reduce_steering_event`` only checks ``isinstance(agent, str)``, so a
    blank Agent field is stored as ``""`` in ``applied_agents``.  This is
    documented here (and reported to the owner) rather than hidden: callers must
    keep the envelope ``agent`` populated for ``agent:steer_applied`` facts.
    """
    records = _fold([
        _control_event(steer_id="s1", targets=["a"]),
        # Blank envelope Agent, exactly as lifecycle callers leave it.
        _journal_event("agent:steer_applied", {"steer_ids": ["s1"]}, agent=""),
    ])

    assert len(records) == 1
    assert records[0]["applied_agents"] == [""]


def test_non_dict_event_data_is_ignored():
    """Events whose ``data`` is not an object are skipped, not fatal."""
    records = _fold([
        _journal_event("agent:control", ["not", "a", "dict"]),
        _journal_event("agent:steer_applied", "nope"),
        _control_event(steer_id="s1", targets=["a"]),
        _applied_event("a", ["s1"]),
    ])

    assert len(records) == 1
    assert records[0]["applied_agents"] == ["a"]


def test_steering_records_are_ordered_by_submitted_at():
    """The projection is chronological regardless of fold arrival order."""
    late = _control_event(steer_id="s-late", targets=["a"], timestamp=30.0)
    early = _control_event(steer_id="s-early", targets=["a"], timestamp=10.0)
    middle = _control_event(steer_id="s-middle", targets=["a"], timestamp=20.0)

    records = _fold([late, middle, early])

    assert [record["id"] for record in records] == ["s-early", "s-middle", "s-late"]
    assert [record["submitted_at"] for record in records] == [10.0, 20.0, 30.0]


def test_steering_records_treat_missing_timestamp_as_zero():
    """A record without a timestamp sorts first instead of breaking the sort."""
    no_timestamp = _control_event(steer_id="s-none", targets=["a"], timestamp=None)
    stamped = _control_event(steer_id="s-stamped", targets=["a"], timestamp=5.0)

    records = _fold([stamped, no_timestamp])

    assert [record["id"] for record in records] == ["s-none", "s-stamped"]


def test_steering_records_are_detached_copies():
    """Mutating a returned record never reaches the internal record map."""
    records: dict[str, dict[str, object]] = {}
    ConsoleProjectionService._reduce_steering_event(
        records, _control_event(steer_id="s1", targets=["a", "b"])
    )
    ConsoleProjectionService._reduce_steering_event(records, _applied_event("a", ["s1"]))

    first = ConsoleProjectionService._steering_records(records)
    assert first[0]["applied_agents"] == ["a"]
    first[0]["applied_agents"].append("intruder")  # type: ignore[union-attr]
    first[0]["recipients"].append("intruder")  # type: ignore[union-attr]
    first[0]["text"] = "overwritten"

    second = ConsoleProjectionService._steering_records(records)

    assert second[0]["applied_agents"] == ["a"]
    assert second[0]["recipients"] == ["a", "b"]
    assert second[0]["text"] == "Check the north wall."
