"""Regression tests for bounded context checkpoint persistence."""
from __future__ import annotations

import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest

from angelus.modules.application_module.legacy_context import (
    BACKUP_SUFFIX,
    PRESERVED_ROW_PREFIX,
    checkpoint_format,
    decode_legacy_checkpoint,
    promote_checkpoint,
    read_checkpoint,
)
from llmfetcher.context_handlers.linear import ContextHandlerLinear, read_persisted_context_page


class _NoopCompactor:
    """Minimal compactor placeholder because this test does not compact."""


def _write_legacy_checkpoint(path: Path, rows: list[dict[str, object]]) -> None:
    """Write a pre-2.0 inline checkpoint document.

    Args:
        path: Target ``context.json`` path.
        rows: Legacy ``messages`` rows to inline.

    Returns:
        ``None`` after writing the retired ``{compress_threshold, messages}``
        layout.
    """
    document = {"compress_threshold": 40000, "messages": rows}
    path.write_text(json.dumps(document), encoding="utf-8")


def _load_migration_script():
    """Import ``scripts/migrate_context_to_v2.py`` as a module.

    The script is not part of the ``angelus`` package, so it is loaded by path
    and registered in ``sys.modules`` first (dataclasses need it there).

    Returns:
        The imported migration script module.
    """
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "migrate_context_to_v2.py"
    spec = importlib.util.spec_from_file_location("migrate_context_to_v2", script)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class PagedContextStorageTests(unittest.TestCase):
    """Verify the durable reader returns bounded newest-first windows."""

    def test_save_load_and_page_without_full_context(self) -> None:
        """Store 205 entries then restore and page the newest 200 entries.

        Returns:
            ``None`` after asserting chronological pages and a SQLite pointer.
        """
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.json"
            writer = ContextHandlerLinear(_NoopCompactor())
            for number in range(205):
                writer.add_user_message(f"message-{number}")
            self.assertTrue(writer.save(path))
            # The v2 checkpoint is a SQLite pointer (no ``schema_version``
            # field any more): rows live in the sidecar database, so the
            # pointer reports storage kind, database name and the round.
            pointer = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual("sqlite", pointer["storage"])
            self.assertEqual("context.json.sqlite3", pointer["database"])
            self.assertEqual(205, pointer["round"])
            self.assertEqual(205, pointer["message_count"])
            reader = ContextHandlerLinear(_NoopCompactor())
            self.assertTrue(reader.load(path))
            self.assertEqual(200, len(reader.messages))
            newest, cursor, total = read_persisted_context_page(path)
            self.assertEqual(205, total)
            self.assertEqual(200, len(newest))
            self.assertEqual(6, newest[0].timeline)
            self.assertEqual(205, newest[-1].timeline)
            self.assertEqual(6, cursor)
            oldest, cursor, total = read_persisted_context_page(path, before_timeline=cursor)
            self.assertEqual(205, total)
            self.assertEqual([1, 2, 3, 4, 5], [entry.timeline for entry in oldest])
            self.assertIsNone(cursor)


class LegacyContextCompatibilityTests(unittest.TestCase):
    """Verify pre-2.0 checkpoints stay readable and never lose history."""

    def test_read_checkpoint_decodes_legacy_rows_without_loss(self) -> None:
        """A legacy inline checkpoint reads back every row through the pager.

        Returns:
            ``None`` after asserting rows, reasoning and preserved content.
        """
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.json"
            _write_legacy_checkpoint(
                path,
                [
                    {"timeline": 1, "role": "user", "content": "hello legacy"},
                    {
                        "timeline": 2,
                        "role": "assistant",
                        "content": "hi there",
                        "content_reasoning": "thinking",
                        "usage": {"input": 5, "output": 3, "total": 8},
                    },
                    {"timeline": 3, "role": "system", "content": "system note"},
                ],
            )
            # The upgraded load() returns False for a legacy document: that is
            # exactly the silent-history-loss trap this layer exists to fix.
            self.assertEqual("legacy-json", checkpoint_format(path))
            self.assertFalse(ContextHandlerLinear(_NoopCompactor()).load(path))

            decoded = read_checkpoint(path)
            assert decoded is not None
            self.assertEqual([1, 2, 3], [item.timeline for item in decoded.items])
            self.assertEqual("hello legacy", decoded.items[0].content)
            self.assertEqual("hi there", decoded.items[1].content)
            self.assertEqual("thinking", decoded.items[1].reasoning)
            # The system row has no v2 kind, so it is kept with an explicit
            # marker instead of being dropped.
            self.assertIn(PRESERVED_ROW_PREFIX.format(role="system"), decoded.items[2].content)
            self.assertIn("system note", decoded.items[2].content)
            self.assertEqual((3,), decoded.preserved_rows)

    def test_promote_checkpoint_backs_up_and_writes_v2_pointer(self) -> None:
        """``--apply`` semantics: backup the original, then write a v2 pointer.

        Returns:
            ``None`` after asserting the backup, the promoted pointer and that
            the promoted checkpoint still serves the full history.
        """
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.json"
            _write_legacy_checkpoint(
                path,
                [
                    {"timeline": 1, "role": "user", "content": "first"},
                    {"timeline": 2, "role": "assistant", "content": "second"},
                ],
            )
            original = path.read_text(encoding="utf-8")

            dry = promote_checkpoint(path, apply=False)
            self.assertEqual("planned", dry.status)
            self.assertEqual(2, dry.items)
            self.assertEqual(original, path.read_text(encoding="utf-8"))  # untouched
            self.assertFalse(path.with_name(path.name + BACKUP_SUFFIX).exists())

            applied = promote_checkpoint(path, apply=True)
            self.assertEqual("promoted", applied.status)
            backup = path.with_name(path.name + BACKUP_SUFFIX)
            self.assertEqual(backup, applied.backup_path)
            # The untouched original is preserved verbatim as the backup.
            self.assertEqual(original, backup.read_text(encoding="utf-8"))
            pointer = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual("sqlite", pointer["storage"])
            self.assertEqual("context.json.sqlite3", pointer["database"])
            # The promoted checkpoint reads as current v2 and keeps both rows.
            self.assertEqual("v2-sqlite", checkpoint_format(path))
            reread = read_checkpoint(path)
            assert reread is not None
            self.assertEqual([1, 2], [item.timeline for item in reread.items])
            self.assertEqual(["first", "second"], [item.content for item in reread.items])
            # Idempotent: promoting again is a no-op that reports "current".
            again = promote_checkpoint(path, apply=True)
            self.assertEqual("current", again.status)

    def test_promote_checkpoint_leaves_unreadable_document_untouched(self) -> None:
        """A non-checkpoint file is reported unreadable and never rewritten.

        Returns:
            ``None`` after asserting the file bytes and status are unchanged.
        """
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.json"
            path.write_text("{ not valid json", encoding="utf-8")
            before = path.read_bytes()
            self.assertEqual("unreadable", checkpoint_format(path))
            outcome = promote_checkpoint(path, apply=True)
            self.assertEqual("unreadable", outcome.status)
            self.assertEqual(before, path.read_bytes())
            self.assertFalse(path.with_name(path.name + BACKUP_SUFFIX).exists())

    def test_promote_empty_legacy_checkpoint_reports_empty(self) -> None:
        """A legacy document with no rows is ``empty`` and left as-is.

        Returns:
            ``None`` after asserting no promotion happens for empty history.
        """
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.json"
            _write_legacy_checkpoint(path, [])
            before = path.read_text(encoding="utf-8")
            outcome = promote_checkpoint(path, apply=True)
            self.assertEqual("empty", outcome.status)
            self.assertEqual(before, path.read_text(encoding="utf-8"))
            self.assertEqual("legacy-json", checkpoint_format(path))

    def test_decode_legacy_checkpoint_preserves_unrepresentable_roles(self) -> None:
        """``system``/``tool``/unknown roles are counted, never dropped.

        Returns:
            ``None`` after asserting preserved timelines and row text.
        """
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "context.json"
            _write_legacy_checkpoint(
                path,
                [
                    {"timeline": 1, "role": "user", "content": "u"},
                    {"timeline": 2, "role": "system", "content": "s"},
                    {"timeline": 3, "role": "tool", "content": "t"},
                    {"timeline": 4, "role": "moderator", "content": "m"},
                    {"timeline": 5, "role": "assistant", "content": "a"},
                ],
            )
            decoded = decode_legacy_checkpoint(path)
            self.assertEqual(5, len(decoded.items))
            self.assertEqual((2, 3, 4), decoded.preserved_rows)
            self.assertIn("s", decoded.items[1].content)
            self.assertIn("t", decoded.items[2].content)
            self.assertIn("m", decoded.items[3].content)


class MigrationScriptTests(unittest.TestCase):
    """Verify ``scripts/migrate_context_to_v2.py`` dry-run and apply modes."""

    def test_migrate_dry_run_then_apply_over_state_root(self) -> None:
        """Dry run reports planned counts and writes nothing; apply promotes.

        Returns:
            ``None`` after asserting the three-way report and backups.
        """
        script = _load_migration_script()
        with tempfile.TemporaryDirectory() as directory:
            state_root = Path(directory)
            legacy_dir = state_root / "sessions" / "demo" / "agents" / "coordinator"
            legacy_dir.mkdir(parents=True)
            legacy_path = legacy_dir / "context.json"
            _write_legacy_checkpoint(
                legacy_path,
                [
                    {"timeline": 1, "role": "user", "content": "a"},
                    {"timeline": 2, "role": "system", "content": "b"},
                ],
            )
            # A current v2 pointer distinguishes the "current" bucket.
            current_dir = state_root / "sessions" / "other" / "agents" / "coordinator"
            current_dir.mkdir(parents=True)
            current_path = current_dir / "context.json"
            writer = ContextHandlerLinear(_NoopCompactor())
            writer.add_user_message("already v2")
            self.assertTrue(writer.save(current_path))

            dry = script.migrate(state_root, apply=False)
            self.assertTrue(dry.ok)
            self.assertEqual(1, dry.count(script.STATUS_PLANNED))
            self.assertEqual(1, dry.count(script.STATUS_CURRENT))
            # Nothing written during the dry run.
            self.assertFalse(legacy_path.with_name(legacy_path.name + BACKUP_SUFFIX).exists())
            self.assertEqual("legacy-json", checkpoint_format(legacy_path))

            applied = script.migrate(state_root, apply=True)
            self.assertTrue(applied.ok)
            self.assertEqual(1, applied.count(script.STATUS_PROMOTED))
            self.assertEqual(1, applied.count(script.STATUS_CURRENT))
            self.assertEqual(1, applied.preserved_rows)
            self.assertTrue(legacy_path.with_name(legacy_path.name + BACKUP_SUFFIX).exists())
            self.assertEqual("v2-sqlite", checkpoint_format(legacy_path))
            # The already-v2 checkpoint is left byte-identical.
            self.assertEqual("v2-sqlite", checkpoint_format(current_path))

    def test_migrate_reports_failure_without_aborting_sweep(self) -> None:
        """One unreadable checkpoint is reported, the sweep still completes.

        Returns:
            ``None`` after asserting ``ok`` is False but the good checkpoint is
            still promoted.
        """
        script = _load_migration_script()
        with tempfile.TemporaryDirectory() as directory:
            state_root = Path(directory)
            bad_dir = state_root / "sessions" / "broken" / "agents" / "coordinator"
            bad_dir.mkdir(parents=True)
            (bad_dir / "context.json").write_text("{ not json", encoding="utf-8")
            good_dir = state_root / "sessions" / "good" / "agents" / "coordinator"
            good_dir.mkdir(parents=True)
            _write_legacy_checkpoint(good_dir / "context.json", [{"timeline": 1, "role": "user", "content": "ok"}])

            report = script.migrate(state_root, apply=True)
            self.assertFalse(report.ok)
            self.assertEqual(1, report.count(script.STATUS_UNREADABLE))
            self.assertEqual(1, report.count(script.STATUS_PROMOTED))
            self.assertEqual("v2-sqlite", checkpoint_format(good_dir / "context.json"))

    def test_migrate_missing_root_is_not_a_failure(self) -> None:
        """A non-existent state root yields an empty, successful report.

        Returns:
            ``None`` after asserting no outcome and no error.
        """
        script = _load_migration_script()
        with tempfile.TemporaryDirectory() as directory:
            missing = Path(directory) / "does-not-exist"
            report = script.migrate(missing, apply=False)
            self.assertTrue(report.ok)
            self.assertEqual(0, len(report.outcomes))
