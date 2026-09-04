"""Session-owned boundary that serializes replaceable execution attempts."""

from __future__ import annotations

import threading
import json
from collections.abc import Callable
from pathlib import Path
from typing import Generic, TypeVar

from llmfetcher.execution import ExecutionController

from ..execution_module import ExecutionAttempt, ExecutionSnapshot, ExecutionState


ResultT = TypeVar("ResultT")


class SessionExecutor(Generic[ResultT]):
    """Allocate replaceable attempts for one logical Session.

    Despite its historical module location, this is not a swarm registry and
    never owns another Session.  ``Session.execution`` owns exactly one of
    these objects, which retains the latest attempt for inspection/replay.
    """

    def __init__(self, session_id: str, root: Path) -> None:
        """Create an idle execution owner rooted in one Session directory.

        Args:
            session_id: Stable logical Session identifier written to attempts.
            root: Parent directory where attempt directories are created.
        """
        normalized = session_id.strip()
        if not normalized:
            raise ValueError("session_id must not be blank")
        # Normalized identity shared by synthetic idle snapshots and attempts.
        self.session_id = normalized
        # Session-owned durable parent; each attempt adds executions/<uuid>.
        self.root = root
        # Monotonic number that distinguishes retries within this process.
        self._attempt_number = 0
        # Latest attempt; retained after terminal completion for inspection.
        self._attempt: ExecutionAttempt[ResultT] | None = None
        # Serializes start/stop/snapshot against concurrent API callers.
        self._lock = threading.RLock()

    def start(self, operation: Callable[[ExecutionController], ResultT], *, before_start: Callable[[ExecutionAttempt[ResultT]], None] | None = None) -> ExecutionAttempt[ResultT]:
        """Start one operation in its attempt's non-daemon worker thread.

        Args:
            operation: Callable receiving this attempt's unique controller.

        Raises:
            RuntimeError: If a prior attempt remains live.
        """
        with self._lock:
            if self._attempt is not None and self._attempt.snapshot().state in {
                ExecutionState.RUNNING, ExecutionState.STOPPING, ExecutionState.FORCE_STOPPING,
            }:
                raise RuntimeError(f"Executor {self.session_id!r} already has a live attempt")
            self._attempt_number += 1
            self._attempt = ExecutionAttempt(self.session_id, self._attempt_number, self.root)
            if before_start is not None:
                before_start(self._attempt)
            self._attempt.start(operation)
            return self._attempt

    def request_stop(self, *, force: bool = False, reason: str = "user_requested") -> ExecutionSnapshot:
        """Signal cancellation and return the immediately visible state.

        Args:
            force: Also set the terminal I/O cancellation event when true.

        Returns:
            Updated execution snapshot. Terminal executors are unchanged.
        """
        with self._lock:
            return self._attempt.request_stop(force=force, reason=reason) if self._attempt else self.snapshot()

    def wait(self, timeout: float | None = None) -> bool:
        """Wait for operation exit without joining its worker thread.

        Args:
            timeout: Maximum seconds to wait; ``None`` waits indefinitely.

        Returns:
            ``True`` when no attempt exists or the current attempt is terminal.
        """
        with self._lock:
            return self._attempt.wait(timeout) if self._attempt else True

    def snapshot(self) -> ExecutionSnapshot:
        """Return current attempt snapshot or a synthetic Session-idle snapshot."""
        with self._lock:
            if self._attempt is not None:
                return self._attempt.snapshot()
            return self._recovered_snapshot() or ExecutionSnapshot(
                self.session_id, None, self._attempt_number, ExecutionState.IDLE, None, None, None,
            )

    def recovered_journal(self):
        """Return the latest durable journal after a host restart, if any."""
        manifest = self._latest_manifest()
        if manifest is None:
            return None
        from ..execution_module.journal import ExecutionJournal
        path, value = manifest
        execution_id = value.get("execution_id")
        if not isinstance(execution_id, str):
            return None
        return ExecutionJournal(path.parent / "execution.events.ndjson", execution_id)

    def _recovered_snapshot(self) -> ExecutionSnapshot | None:
        manifest = self._latest_manifest()
        if manifest is None:
            return None
        path, value = manifest
        try:
            state = ExecutionState(str(value["state"]))
            execution_id = str(value["execution_id"])
            attempt = int(value.get("attempt", 0))
        except (KeyError, TypeError, ValueError):
            return None
        started = value.get("started_at") if isinstance(value.get("started_at"), (int, float)) else None
        finished = value.get("finished_at") if isinstance(value.get("finished_at"), (int, float)) else None
        error = value.get("error") if isinstance(value.get("error"), str) else None
        # A process cannot safely resume an in-flight provider request. Surface
        # that fact explicitly rather than erasing it as an idle session.
        if state in {ExecutionState.RUNNING, ExecutionState.STOPPING, ExecutionState.FORCE_STOPPING}:
            return ExecutionSnapshot(self.session_id, execution_id, attempt, ExecutionState.INTERRUPTED, started, path.stat().st_mtime, "Host restarted before this execution reached a terminal state.")
        return ExecutionSnapshot(self.session_id, execution_id, attempt, state, started, finished, error)

    def _latest_manifest(self) -> tuple[Path, dict[str, object]] | None:
        executions = self.root / "executions"
        candidates = sorted(executions.glob("*/execution-manifest.json"), key=lambda item: item.stat().st_mtime_ns, reverse=True) if executions.is_dir() else []
        for path in candidates:
            try:
                value = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if isinstance(value, dict) and value.get("session_id") == self.session_id:
                return path, value
        return None

    @property
    def result(self) -> ResultT | None:
        """Return only the successful worker result of the latest attempt."""
        """Return the completed operation result, or ``None`` before success."""
        with self._lock:
            return self._attempt.result if self._attempt else None

    @property
    def attempt(self) -> ExecutionAttempt[ResultT] | None:
        """Return current/latest attempt identity without creating a new one."""
        with self._lock:
            return self._attempt
