"""Durable local result store used when PostGIS is not configured."""

from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile
from typing import Any


class LocalResultStore:
    """Append-only bounded analysis archive inside Angelus-owned state."""

    def __init__(self, state_root: Path) -> None:
        self._path = state_root.resolve() / "analyses.json"

    def save(self, analysis: dict[str, Any]) -> None:
        document = self._read()
        existing = [item for item in document["analyses"] if item.get("id") != analysis.get("id")]
        document["analyses"] = [analysis, *existing][:200]
        self._write(document)

    def list(self, limit: int) -> list[dict[str, Any]]:
        return list(self._read()["analyses"][:limit])

    def get(self, analysis_id: str) -> dict[str, Any]:
        for analysis in self._read()["analyses"]:
            if analysis.get("id") == analysis_id:
                return analysis
        raise KeyError(analysis_id)

    def _read(self) -> dict[str, list[dict[str, Any]]]:
        if not self._path.is_file():
            return {"analyses": []}
        try:
            document = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise ValueError("local GEOINT analysis archive is unreadable") from exc
        if not isinstance(document, dict) or not isinstance(document.get("analyses"), list):
            raise ValueError("local GEOINT analysis archive has an unsupported format")
        return {"analyses": [item for item in document["analyses"] if isinstance(item, dict)]}

    def _write(self, document: dict[str, Any]) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=f".{self._path.name}.", dir=self._path.parent)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8") as file:
                json.dump(document, file, ensure_ascii=False, separators=(",", ":"))
                file.write("\n")
                file.flush()
                os.fsync(file.fileno())
            os.replace(temporary, self._path)
        except BaseException:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            raise


__all__ = ["LocalResultStore"]
