"""Private managed-byte store and manifest operations for browser imports."""
from __future__ import annotations

from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
from threading import RLock
from typing import Any
import uuid

from ...modules.settings_module.json_store import write_json
from .models import FileDeclaration, ImportContractError, MAX_FILE_BYTES, validate_declarations


class ImportStorageError(ValueError):
    pass


class UploadSink:
    """A capability to stream bytes into one declared managed upload only."""
    def __init__(self, path: Path, maximum: int) -> None:
        self._path, self._maximum, self._written, self._hash = path, maximum, 0, sha256()
        self._file = path.open("wb")

    def write(self, chunk: bytes) -> None:
        self._written += len(chunk)
        if self._written > self._maximum:
            raise ImportStorageError("uploaded file exceeds its declared size")
        self._hash.update(chunk); self._file.write(chunk)

    def close(self) -> tuple[int, str]:
        self._file.flush(); os.fsync(self._file.fileno()); self._file.close()
        return self._written, self._hash.hexdigest()

    def abort(self) -> None:
        if not self._file.closed: self._file.close()
        self._path.unlink(missing_ok=True)


class ImportStorage:
    """Own session-scoped import manifests and unconfirmed original bytes."""
    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self._lock = RLock()

    @staticmethod
    def _safe_id(value: str) -> str:
        if not value or len(value) > 100 or "/" in value or "\\" in value:
            raise ImportStorageError("invalid import identifier")
        return value

    def _directory(self, session_id: str, import_id: str) -> Path:
        return self.root / self._safe_id(session_id) / self._safe_id(import_id)

    def _manifest_path(self, session_id: str, import_id: str) -> Path:
        return self._directory(session_id, import_id) / "manifest.json"

    def _read(self, session_id: str, import_id: str) -> dict[str, Any]:
        path = self._manifest_path(session_id, import_id)
        try: value = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError as exc: raise KeyError(import_id) from exc
        except (OSError, json.JSONDecodeError) as exc: raise ImportStorageError("import manifest is unreadable") from exc
        if not isinstance(value, dict) or value.get("session_id") != session_id:
            raise KeyError(import_id)
        return value

    @staticmethod
    def _public(value: dict[str, Any]) -> dict[str, Any]:
        result = {key: value[key] for key in ("import_id", "session_id", "status", "revision", "client_request_id", "files", "candidates", "assets", "layers", "warnings", "error") if key in value}
        return result

    def create(self, session_id: str, files: object, client_request_id: str | None) -> dict[str, Any]:
        declarations = validate_declarations(files)
        if client_request_id is not None and (not isinstance(client_request_id, str) or len(client_request_id) > 100):
            raise ImportContractError("invalid client request id")
        with self._lock:
            if client_request_id:
                session_dir = self.root / self._safe_id(session_id)
                if session_dir.exists():
                    for manifest_path in session_dir.glob("*/manifest.json"):
                        try:
                            previous = json.loads(manifest_path.read_text(encoding="utf-8"))
                            if previous.get("client_request_id") == client_request_id:
                                return self._public(previous)
                        except (OSError, json.JSONDecodeError):
                            continue
            import_id = f"import_{uuid.uuid4().hex[:16]}"; directory = self._directory(session_id, import_id)
            directory.mkdir(parents=True, mode=0o700); os.chmod(directory, 0o700)
            manifest = {"schema_version": 1, "import_id": import_id, "session_id": session_id, "client_request_id": client_request_id, "status": "receiving", "revision": 1, "files": [{"file_id": item.file_id, "name": item.name, "size_bytes": item.size_bytes, "received_bytes": 0, "sha256": None, "status": "pending"} for item in declarations], "candidates": [], "assets": [], "layers": [], "warnings": []}
            write_json(self._manifest_path(session_id, import_id), manifest)
            return self._public(manifest)

    def snapshot(self, session_id: str, import_id: str) -> dict[str, Any]:
        with self._lock: return self._public(self._read(session_id, import_id))

    def list(self, session_id: str) -> list[dict[str, Any]]:
        directory = self.root / self._safe_id(session_id)
        if not directory.exists(): return []
        with self._lock:
            snapshots = []
            for path in directory.glob("*/manifest.json"):
                try: snapshots.append(self._public(self._read(session_id, path.parent.name)))
                except (KeyError, ImportStorageError): continue
            return sorted(snapshots, key=lambda item: item["import_id"], reverse=True)

    def open_upload(self, session_id: str, import_id: str, file_id: str) -> tuple[UploadSink, dict[str, Any]]:
        with self._lock:
            manifest = self._read(session_id, import_id)
            if manifest["status"] != "receiving": raise ImportStorageError("import is no longer accepting files")
            record = next((item for item in manifest["files"] if item["file_id"] == file_id), None)
            if not record: raise KeyError(file_id)
            if record["status"] == "uploaded": raise ImportStorageError("file was already uploaded")
            path = self._directory(session_id, import_id) / f"{file_id}{Path(str(record['name'])).suffix.lower()}"
            return UploadSink(path, min(MAX_FILE_BYTES, int(record["size_bytes"]))), dict(record)

    def seal_upload(self, session_id: str, import_id: str, file_id: str, received: int, digest: str) -> dict[str, Any]:
        with self._lock:
            manifest = self._read(session_id, import_id); record = next((item for item in manifest["files"] if item["file_id"] == file_id), None)
            if not record: raise KeyError(file_id)
            if received != record["size_bytes"]:
                raise ImportStorageError("uploaded file length does not match its declaration")
            record.update({"received_bytes": received, "sha256": digest, "status": "uploaded"}); manifest["revision"] += 1
            write_json(self._manifest_path(session_id, import_id), manifest); return self._public(manifest)

    def all_uploaded(self, session_id: str, import_id: str) -> bool:
        with self._lock: return all(item.get("status") == "uploaded" for item in self._read(session_id, import_id)["files"])

    def file_path(self, session_id: str, import_id: str, file_id: str) -> Path:
        with self._lock:
            manifest = self._read(session_id, import_id)
            record = next((item for item in manifest["files"] if item.get("file_id") == file_id and item.get("status") == "uploaded"), None)
            if not record:
                raise ImportStorageError("uploaded source is unavailable")
            return self._directory(session_id, import_id) / f"{file_id}{Path(str(record['name'])).suffix.lower()}"

    def update(self, session_id: str, import_id: str, **changes: Any) -> dict[str, Any]:
        with self._lock:
            manifest = self._read(session_id, import_id); manifest.update(changes); manifest["revision"] += 1
            write_json(self._manifest_path(session_id, import_id), manifest); return self._public(manifest)

    def discard_session(self, session_id: str) -> None:
        """Remove only this module's private bytes after Session deletion begins."""
        with self._lock:
            directory = self.root / self._safe_id(session_id)
            if directory.exists(): shutil.rmtree(directory)
