"""Read-side compatibility for pre-2.0 linear context checkpoints.

Angelus stores one durable pointer per Agent at
``<state>/agents/<agent>/context.json``.  Checkpoints written before the
llmfetcher ContextItem upgrade are single JSON documents that inline the whole
transcript under ``{"compress_threshold": ..., "messages": [...]}`` and describe
rows with the retired ``LLMContext`` field names (``content_reasoning``,
``tool_calls[].call``, ``usage`` as a plain mapping, ...).

The upgraded ``ContextHandlerLinear.load`` recognises only the v2 SQLite
pointer (``{"storage": "sqlite", "database": ...}``) and returns ``False`` for
those legacy documents instead of migrating them.  Without a compatibility
layer every old Session would therefore *appear* to have an empty history,
which is exactly the silent historical-data loss this module exists to prevent.

Two read-only guarantees are implemented here:

* :func:`read_checkpoint` decodes either layout, so a caller can always see the
  full history that exists on disk.
* :func:`decode_legacy_checkpoint` never discards a row.  Rows that have no
  direct v2 equivalent (``system`` / ``tool`` / unknown roles) are preserved
  verbatim as marked user items and reported by timeline, so the loss is
  visible rather than silent.

Promotion to v2 is an explicit, backed-up, fail-closed operation
(:func:`promote_checkpoint`); nothing here rewrites a checkpoint as a side
effect of reading it.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
import json
from pathlib import Path
import shutil
from typing import Any, cast

from llmfetcher.context_handlers.linear import ContextHandlerLinear, read_persisted_context_page
from llmfetcher.context_handlers.linear.paging import is_sqlite_context_pointer
from llmfetcher.llm_types import (
    AssistantContextItem,
    ContextItem,
    ContextItemId,
    JsonObject,
    TokenUsage,
    ToolCallRecord,
    ToolResultId,
    ToolResultRecord,
    UserContextItem,
)

#: Exact command an operator runs to promote every legacy checkpoint.
MIGRATION_COMMAND = "python scripts/migrate_context_to_v2.py --apply <state-root>"

#: Suffix of the untouched copy kept next to a promoted checkpoint.
BACKUP_SUFFIX = ".legacy.bak"

#: Marker prefixed to legacy rows that v2 has no dedicated item kind for.
PRESERVED_ROW_PREFIX = "[legacy {role} row preserved] "

_FORMAT_V2 = "v2-sqlite"
_FORMAT_LEGACY = "legacy-json"
_FORMAT_MISSING = "missing"
_FORMAT_UNREADABLE = "unreadable"


class LegacyContextError(ValueError):
    """Raised when a checkpoint cannot be decoded or promoted without loss."""


class _NoCompactor:
    """Placeholder compaction fetcher; decoding and promotion never compact."""


@dataclass(frozen=True)
class DecodedCheckpoint:
    """One checkpoint decoded into the current context item union.

    Attributes:
        items: Chronological items, newest last.
        tool_results: Historical tool results keyed by result id value.
        round: Highest timeline seen, used as the handler round counter.
        compress_threshold: Persisted budget, or ``None`` when absent.
        preserved_rows: Timelines that had no direct v2 kind and were kept as
            marked text.  Always reported so the caller can surface them.
    """

    items: tuple[ContextItem, ...]
    tool_results: dict[str, ToolResultRecord]
    round: int
    compress_threshold: int | None
    preserved_rows: tuple[int, ...] = ()

    @property
    def is_empty(self) -> bool:
        """Return whether the checkpoint holds no recoverable record."""
        return not self.items


@dataclass(frozen=True)
class PromotionOutcome:
    """Result of inspecting or promoting one checkpoint.

    Attributes:
        path: The checkpoint that was inspected.
        status: ``"current"`` (already v2), ``"planned"`` (dry run),
            ``"promoted"``, ``"empty"`` (legacy without rows), or
            ``"unreadable"`` (not a checkpoint at all).
        items: Number of decoded items.
        preserved_rows: Number of rows kept with an explicit marker.
        backup_path: Copy of the original legacy document, when promoted.
        detail: Human-readable explanation safe to print in a report.
    """

    path: Path
    status: str
    items: int = 0
    preserved_rows: int = 0
    backup_path: Path | None = None
    detail: str = ""


def checkpoint_format(path: str | Path) -> str:
    """Classify one checkpoint file without migrating it.

    Args:
        path: Candidate ``context.json`` path.

    Returns:
        ``"v2-sqlite"``, ``"legacy-json"``, ``"missing"`` or ``"unreadable"``.
    """
    target = Path(path)
    if not target.is_file():
        return _FORMAT_MISSING
    try:
        payload = _read_json(target)
    except (OSError, ValueError):
        return _FORMAT_UNREADABLE
    if is_sqlite_context_pointer(payload):
        return _FORMAT_V2
    if is_legacy_checkpoint(payload):
        return _FORMAT_LEGACY
    return _FORMAT_UNREADABLE


def is_legacy_checkpoint(payload: object) -> bool:
    """Return whether a parsed checkpoint is the retired inline layout.

    Args:
        payload: Object decoded from a checkpoint document.

    Returns:
        ``True`` only for a mapping that inlines a ``messages`` list and does
        not declare the v2 SQLite storage marker.
    """
    return (
        isinstance(payload, Mapping)
        and not is_sqlite_context_pointer(payload)
        and isinstance(payload.get("messages"), list)
    )


def read_checkpoint(path: str | Path) -> DecodedCheckpoint | None:
    """Decode either checkpoint layout into current context items.

    This is the read-direction compatibility entry point: callers that used to
    rely on ``ContextHandlerLinear.load`` can read v2 and legacy checkpoints
    with one call, so a pre-2.0 Session never projects as "empty history".

    Args:
        path: ``context.json`` pointer path.

    Returns:
        Decoded checkpoint, or ``None`` when the file is missing or is not a
        recognisable checkpoint.

    Raises:
        LegacyContextError: If a recognised checkpoint cannot be decoded.
    """
    layout = checkpoint_format(path)
    if layout == _FORMAT_MISSING:
        return None
    if layout == _FORMAT_LEGACY:
        return decode_legacy_checkpoint(path)
    if layout != _FORMAT_V2:
        return None
    return _read_v2_checkpoint(Path(path))


def decode_legacy_checkpoint(path: str | Path) -> DecodedCheckpoint:
    """Decode one inline (pre-2.0) checkpoint without modifying it.

    Args:
        path: Legacy ``context.json`` document.

    Returns:
        Every row as a context item, with tool results separated out.

    Raises:
        LegacyContextError: If the document is not a legacy checkpoint, or a
            row is so malformed that even its text cannot be recovered.
    """
    target = Path(path)
    try:
        payload = _read_json(target)
    except (OSError, ValueError) as exc:
        raise LegacyContextError(f"cannot read legacy checkpoint {target}: {exc}") from exc
    if not is_legacy_checkpoint(payload):
        raise LegacyContextError(f"{target} is not a legacy inline checkpoint")
    document = cast(Mapping[str, Any], payload)
    rows = cast(Sequence[object], document.get("messages") or ())
    threshold = document.get("compress_threshold")
    compress_threshold = threshold if isinstance(threshold, int) and not isinstance(threshold, bool) else None

    items: list[ContextItem] = []
    tool_results: dict[str, ToolResultRecord] = {}
    preserved: list[int] = []
    timeline = 0
    for index, row in enumerate(rows):
        if not isinstance(row, Mapping):
            raise LegacyContextError(
                f"{target}: row {index} is not an object; refusing to drop it silently"
            )
        item, carried_results, was_preserved = _decode_row(row, index, timeline)
        timeline = item.timeline
        items.append(item)
        tool_results.update(carried_results)
        if was_preserved:
            preserved.append(item.timeline)
    return DecodedCheckpoint(
        items=tuple(items),
        tool_results=tool_results,
        round=timeline,
        compress_threshold=compress_threshold,
        preserved_rows=tuple(preserved),
    )


def promote_checkpoint(path: str | Path, *, apply: bool = False) -> PromotionOutcome:
    """Promote one legacy checkpoint to the v2 SQLite layout.

    Args:
        path: ``context.json`` pointer path.
        apply: When ``False`` (default) nothing is written; the outcome only
            reports what would happen.

    Returns:
        Outcome describing the promotion, including the backup location.

    Raises:
        LegacyContextError: If promotion was requested but the checkpoint
            cannot be decoded or persisted.  The original document is left
            untouched whenever the write fails.
    """
    target = Path(path)
    layout = checkpoint_format(target)
    if layout == _FORMAT_MISSING:
        return PromotionOutcome(path=target, status="missing", detail="checkpoint does not exist")
    if layout == _FORMAT_V2:
        return PromotionOutcome(path=target, status="current", detail="already a v2 SQLite pointer")
    if layout != _FORMAT_LEGACY:
        return PromotionOutcome(
            path=target,
            status="unreadable",
            detail="not a recognisable context checkpoint; left untouched",
        )

    decoded = decode_legacy_checkpoint(target)
    if decoded.is_empty:
        return PromotionOutcome(
            path=target,
            status="empty",
            detail="legacy checkpoint holds no rows; nothing to promote",
        )
    if not apply:
        return PromotionOutcome(
            path=target,
            status="planned",
            items=len(decoded.items),
            preserved_rows=len(decoded.preserved_rows),
            detail="dry run; pass --apply to write the v2 pointer",
        )

    backup = target.with_name(target.name + BACKUP_SUFFIX)
    if not backup.exists():
        shutil.copy2(target, backup)
    handler = ContextHandlerLinear(_NoCompactor())
    handler.messages = list(decoded.items)
    handler.tool_results = dict(decoded.tool_results)
    handler._round = decoded.round
    if not handler.save(target):
        raise LegacyContextError(
            f"cannot persist promoted checkpoint {target}: {handler.last_save_error}; "
            f"original preserved at {backup}"
        )
    return PromotionOutcome(
        path=target,
        status="promoted",
        items=len(decoded.items),
        preserved_rows=len(decoded.preserved_rows),
        backup_path=backup,
        detail="v2 SQLite pointer written; original kept as the backup document",
    )


def _read_v2_checkpoint(target: Path) -> DecodedCheckpoint:
    """Read every active v2 row through the durable pager.

    Args:
        target: v2 SQLite pointer path.

    Returns:
        Decoded checkpoint ordered oldest first.

    Raises:
        LegacyContextError: If a stored row cannot be decoded.
    """
    document = cast(Mapping[str, Any], _read_json(target))
    items: list[ContextItem] = []
    before: int | None = None
    total = 0
    while True:
        try:
            page, next_before, total = read_persisted_context_page(
                target, before_timeline=before, limit=200
            )
        except (OSError, ValueError, TypeError) as exc:
            raise LegacyContextError(f"cannot read v2 checkpoint {target}: {exc}") from exc
        items.extend(page)
        if next_before is None:
            break
        before = next_before
    items.sort(key=lambda item: item.timeline)
    saved_round = document.get("round")
    round_value = saved_round if isinstance(saved_round, int) and not isinstance(saved_round, bool) else (
        items[-1].timeline if items else 0
    )
    threshold = document.get("compress_threshold")
    compress_threshold = threshold if isinstance(threshold, int) and not isinstance(threshold, bool) else None
    return DecodedCheckpoint(
        items=tuple(items),
        tool_results={},
        round=round_value,
        compress_threshold=compress_threshold,
    )


def _decode_row(
    row: Mapping[str, object],
    index: int,
    previous_timeline: int,
) -> tuple[ContextItem, dict[str, ToolResultRecord], bool]:
    """Decode one legacy row without losing its text.

    Args:
        row: Raw persisted row.
        index: Zero-based position, used for a deterministic identity.
        previous_timeline: Timeline of the previous item, kept monotonic.

    Returns:
        The decoded item, any tool results it referenced, and whether the row
        had to be preserved under an explicit marker instead of a native kind.
    """
    raw_timeline = row.get("timeline")
    timeline = raw_timeline if isinstance(raw_timeline, int) and not isinstance(raw_timeline, bool) else None
    timeline = previous_timeline + 1 if timeline is None else max(timeline, previous_timeline + 1)
    role = row.get("role")
    content = row.get("content")
    text = content if isinstance(content, str) else ("" if content is None else str(content))
    reasoning = _legacy_reasoning(row)

    if role == "assistant":
        calls, results = _legacy_tool_calls(row.get("tool_calls"), index)
        return (
            AssistantContextItem(
                item_id=_item_id(index, "a"),
                timeline=timeline,
                content=text,
                reasoning=reasoning,
                tool_calls=calls,
                usage=_legacy_usage(row.get("usage")),
                model_duration_ms=_optional_int(row.get("model_duration_ms")),
                round_duration_ms=_optional_int(row.get("round_duration_ms")),
                created_at=_optional_float(row.get("created_at")),
            ),
            results,
            False,
        )

    normalized_role = role if isinstance(role, str) and role else "unknown"
    preserved = normalized_role != "user"
    suffix = f"\n[reasoning] {reasoning}" if reasoning else ""
    if preserved:
        text = PRESERVED_ROW_PREFIX.format(role=normalized_role) + text + suffix
    return (
        UserContextItem(
            item_id=_item_id(index, "u"),
            timeline=timeline,
            content=text,
            images=(),
        ),
        {},
        preserved,
    )


def _legacy_tool_calls(
    raw: object,
    index: int,
) -> tuple[tuple[ToolCallRecord, ...], dict[str, ToolResultRecord]]:
    """Convert retired ``ToolInfo`` rows into call records plus stored results.

    Args:
        raw: Persisted ``tool_calls`` value.
        index: Row index used to build stable identities.

    Returns:
        Call records for the assistant item and the result records they point
        at.  A tool result is only created when the legacy row actually stored
        output or images, so an unanswered call stays unanswered.
    """
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes)):
        return (), {}
    calls: list[ToolCallRecord] = []
    results: dict[str, ToolResultRecord] = {}
    for position, entry in enumerate(raw):
        if not isinstance(entry, Mapping):
            continue
        call_raw = entry.get("call")
        call = cast(Mapping[str, object], call_raw) if isinstance(call_raw, Mapping) else {}
        name = call.get("name") or entry.get("name") or "unknown"
        call_id = call.get("call_id") or entry.get("call_id") or f"legacy-{index}-{position}"
        arguments = call.get("arguments")
        call_arguments: JsonObject = (
            cast(JsonObject, dict(arguments)) if isinstance(arguments, Mapping) else {}
        )
        output = entry.get("result")
        output_text = output if isinstance(output, str) else ("" if output is None else str(output))
        images = entry.get("images")
        has_images = isinstance(images, Sequence) and not isinstance(images, (str, bytes)) and bool(images)
        result_id: ToolResultId | None = None
        if output_text or has_images:
            result_id = ToolResultId(value=f"legacy-result-{index}-{position}")
            results[result_id.value] = ToolResultRecord(
                result_id=result_id,
                call_id=str(call_id),
                tool_name=str(name),
                output=output_text,
                images=(),
                ok=None,
                duration_ms=None,
                created_at=None,
            )
        calls.append(
            ToolCallRecord(
                call_id=str(call_id),
                name=str(name),
                arguments=call_arguments,
                result_id=result_id,
            )
        )
    return tuple(calls), results


def _legacy_usage(raw: object) -> TokenUsage:
    """Map the retired usage mapping onto :class:`TokenUsage`.

    Args:
        raw: Persisted ``usage`` value, a mapping with short key names.

    Returns:
        Token usage with zero defaults for every absent field.
    """
    if not isinstance(raw, Mapping):
        return TokenUsage()

    def pick(*names: str) -> int:
        for name in names:
            value = raw.get(name)
            if isinstance(value, int) and not isinstance(value, bool):
                return value
        return 0

    return TokenUsage(
        input_tokens=pick("input", "input_tokens"),
        output_tokens=pick("output", "output_tokens"),
        total_tokens=pick("total", "total_tokens"),
        cached_tokens=pick("cached", "cached_tokens"),
        reasoning_tokens=pick("reasoning", "reasoning_tokens"),
    )


def _legacy_reasoning(row: Mapping[str, object]) -> str:
    """Return the persisted reasoning text under any retired field name.

    Args:
        row: Raw persisted row.

    Returns:
        Reasoning text, empty when the row carried none.
    """
    for name in ("content_reasoning", "reasoning_content", "reasoning"):
        value = row.get(name)
        if isinstance(value, str):
            return value
    return ""


def _item_id(index: int, kind: str) -> ContextItemId:
    """Return a deterministic identity for a decoded row.

    Args:
        index: Zero-based row position.
        kind: One-letter item kind marker.

    Returns:
        Stable item id so repeated decodes of the same file agree.
    """
    return ContextItemId(value=f"legacy-{kind}-{index}")


def _optional_int(value: object) -> int | None:
    """Return a non-boolean integer when the value is one.

    Args:
        value: Untrusted persisted value.

    Returns:
        Integer value or ``None``.
    """
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _optional_float(value: object) -> float | None:
    """Return a finite float when the value is numeric.

    Args:
        value: Untrusted persisted value.

    Returns:
        Float value or ``None``.
    """
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    return None


def _read_json(path: Path) -> object:
    """Read one JSON document.

    Args:
        path: Existing file path.

    Returns:
        Decoded JSON value.

    Raises:
        OSError: If the file cannot be read.
        ValueError: If the document is not valid JSON.
    """
    return json.loads(path.read_text(encoding="utf-8"))


__all__ = [
    "BACKUP_SUFFIX",
    "DecodedCheckpoint",
    "LegacyContextError",
    "MIGRATION_COMMAND",
    "PRESERVED_ROW_PREFIX",
    "PromotionOutcome",
    "checkpoint_format",
    "decode_legacy_checkpoint",
    "is_legacy_checkpoint",
    "promote_checkpoint",
    "read_checkpoint",
]
