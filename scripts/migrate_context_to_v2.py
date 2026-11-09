"""Promote legacy inline ``context.json`` checkpoints to the v2 SQLite layout.

Old Angelus checkpoints are single JSON documents that inline the whole
transcript under ``{"compress_threshold": ..., "messages": [...]}``.  The
upgraded ``llmfetcher`` ``ContextHandlerLinear.load`` recognises only the v2
SQLite pointer (``{"storage": "sqlite", "database": ...}``) and returns
``False`` for those documents, so an un-migrated Session would silently read
as an empty history.

This script is the operator entry point for the one-way migration.  It scans a
state root for ``context.json`` pointers and reports every checkpoint in three
buckets:

* already current (v2 SQLite pointer) - untouched,
* legacy JSON with rows - promoted (or reported as planned in a dry run),
* unreadable / undecodable - left untouched and counted as a failure.

It defaults to a dry run.  Nothing is written unless ``--apply`` is passed, and
every promoted checkpoint keeps an untouched ``context.json.legacy.bak`` copy
next to it.  A non-zero exit status means at least one checkpoint could not be
migrated, so the command is safe to use as a deployment gate.

Examples:
    Inspect a state root without writing anything::

        python scripts/migrate_context_to_v2.py ~/.angelus

    Promote every legacy checkpoint::

        python scripts/migrate_context_to_v2.py --apply ~/.angelus
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
from pathlib import Path
import sys

if __package__ in {None, ""}:  # Allow ``python scripts/migrate_context_to_v2.py``.
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from angelus.modules.application_module.legacy_context import (  # noqa: E402
    LegacyContextError,
    PromotionOutcome,
    checkpoint_format,
    promote_checkpoint,
)

#: Bucket labels reported per checkpoint.
STATUS_CURRENT = "current"
STATUS_PROMOTED = "promoted"
STATUS_PLANNED = "planned"
STATUS_EMPTY = "empty"
STATUS_UNREADABLE = "unreadable"
STATUS_FAILED = "failed"

#: Statuses that leave an undecodable checkpoint behind.
_FAILURE_STATUSES = frozenset({STATUS_UNREADABLE, STATUS_FAILED})


@dataclass(frozen=True)
class MigrationReport:
    """Aggregated outcome of scanning one state root.

    Attributes:
        outcomes: One outcome per discovered checkpoint, in path order.
        applied: Whether the run wrote changes or only reported them.
    """

    outcomes: tuple[PromotionOutcome, ...]
    applied: bool

    def count(self, status: str) -> int:
        """Return how many checkpoints ended in one status bucket.

        Args:
            status: Status label to count.

        Returns:
            Number of outcomes carrying ``status``.
        """
        return sum(1 for outcome in self.outcomes if outcome.status == status)

    @property
    def failures(self) -> tuple[PromotionOutcome, ...]:
        """Return every checkpoint that could not be read or migrated."""
        return tuple(o for o in self.outcomes if o.status in _FAILURE_STATUSES)

    @property
    def migrated(self) -> int:
        """Return the number of newly promoted checkpoints."""
        return self.count(STATUS_PROMOTED) + self.count(STATUS_PLANNED)

    @property
    def preserved_rows(self) -> int:
        """Return rows kept under an explicit marker across all checkpoints."""
        return sum(outcome.preserved_rows for outcome in self.outcomes)

    @property
    def ok(self) -> bool:
        """Return whether every discovered checkpoint is safe to run on."""
        return not self.failures


def discover_checkpoints(state_root: Path) -> tuple[Path, ...]:
    """Collect every ``context.json`` pointer beneath a state root.

    Args:
        state_root: Angelus state directory, or one specific pointer file.

    Returns:
        Sorted checkpoint paths.  A missing root yields no paths.

    Raises:
        FileNotFoundError: If ``state_root`` exists but is not a directory.
    """
    if state_root.is_file():
        return (state_root,)
    if not state_root.exists():
        return ()
    if not state_root.is_dir():
        raise FileNotFoundError(f"not a directory: {state_root}")
    return tuple(sorted(state_root.rglob("context.json")))


def migrate(state_root: Path, *, apply: bool = False) -> MigrationReport:
    """Promote every legacy checkpoint beneath ``state_root``.

    Each checkpoint is classified first so the caller always learns what
    happened to it; an unreadable or undecodable checkpoint never aborts the
    run, it is reported and counted as a failure instead.

    Args:
        state_root: Angelus state directory, or one specific pointer file.
        apply: When ``False`` (default) nothing is written.

    Returns:
        Report covering every discovered checkpoint.

    Raises:
        FileNotFoundError: If ``state_root`` exists but is not a directory.
    """
    outcomes: list[PromotionOutcome] = []
    for path in discover_checkpoints(state_root):
        if checkpoint_format(path) == "missing":
            continue
        try:
            outcomes.append(promote_checkpoint(path, apply=apply))
        except (LegacyContextError, OSError, ValueError) as exc:
            # Never stop the sweep on one bad checkpoint: the operator needs to
            # see every remaining file, and the bad one is left untouched.
            outcomes.append(
                PromotionOutcome(
                    path=path,
                    status=STATUS_FAILED,
                    detail=f"{type(exc).__name__}: {exc}",
                )
            )
    return MigrationReport(outcomes=tuple(outcomes), applied=apply)


def render(report: MigrationReport, *, state_root: Path) -> str:
    """Render one human-readable migration report.

    Args:
        report: Aggregated scan outcome.
        state_root: Root that was scanned, echoed in the header.

    Returns:
        Multi-line report safe to print verbatim.
    """
    mode = "APPLY" if report.applied else "DRY RUN (pass --apply to write changes)"
    lines = [f"context checkpoint migration [{mode}]", f"state root: {state_root}", ""]
    if not report.outcomes:
        lines.append("no context.json checkpoints found")
        return "\n".join(lines)
    for outcome in report.outcomes:
        detail = f" - {outcome.detail}" if outcome.detail else ""
        counts = ""
        if outcome.items:
            counts = f" ({outcome.items} items"
            counts += f", {outcome.preserved_rows} preserved)" if outcome.preserved_rows else ")"
        backup = f" backup={outcome.backup_path}" if outcome.backup_path else ""
        lines.append(f"[{outcome.status}] {outcome.path}{counts}{backup}{detail}")
    lines.extend([
        "",
        f"current (already v2): {report.count(STATUS_CURRENT)}",
        f"{'promoted' if report.applied else 'would promote'}: {report.migrated}",
        f"empty legacy: {report.count(STATUS_EMPTY)}",
        f"failures: {len(report.failures)}",
        f"rows preserved under an explicit marker: {report.preserved_rows}",
    ])
    if not report.applied and report.count(STATUS_PLANNED):
        lines.append("")
        lines.append("nothing written; re-run with --apply to promote these checkpoints")
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    """Parse arguments, run the sweep, and print the report.

    Args:
        argv: Optional argument vector; defaults to ``sys.argv[1:]``.

    Returns:
        ``0`` when every checkpoint is usable, ``1`` when one needs attention.
    """
    parser = argparse.ArgumentParser(
        description="Promote legacy inline context.json checkpoints to the v2 SQLite layout.",
    )
    parser.add_argument("state_root", type=Path, help="Angelus state directory or one context.json")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="write the v2 pointer and keep a context.json.legacy.bak copy (default: dry run)",
    )
    parser.add_argument("--json", action="store_true", help="print the report as JSON")
    arguments = parser.parse_args(argv)

    try:
        report = migrate(arguments.state_root, apply=arguments.apply)
    except FileNotFoundError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if arguments.json:
        print(json.dumps({
            "applied": report.applied,
            "ok": report.ok,
            "current": report.count(STATUS_CURRENT),
            "migrated": report.migrated,
            "empty": report.count(STATUS_EMPTY),
            "failures": [
                {"path": str(outcome.path), "status": outcome.status, "detail": outcome.detail}
                for outcome in report.failures
            ],
            "preserved_rows": report.preserved_rows,
            "checkpoints": [
                {
                    "path": str(outcome.path),
                    "status": outcome.status,
                    "items": outcome.items,
                    "preserved_rows": outcome.preserved_rows,
                    "backup_path": str(outcome.backup_path) if outcome.backup_path else None,
                    "detail": outcome.detail,
                }
                for outcome in report.outcomes
            ],
        }, ensure_ascii=False, indent=2))
    else:
        print(render(report, state_root=arguments.state_root))
    return 0 if report.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
