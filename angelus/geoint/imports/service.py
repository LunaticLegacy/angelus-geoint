"""Import lifecycle and controlled publication coordinator."""
from __future__ import annotations

from pathlib import Path
from threading import RLock
from typing import Any, Callable

from ..catalog import GeoAssetCatalog
from ..presentation import MapPresentationStore
from ..raster_style import default_raster_render
from .inspector import InspectionError, inspect_dataset
from .models import ImportContractError
from .preparer import PreparationError, prepare_display_copy
from .storage import ImportStorage, ImportStorageError


class ImportError(ValueError):
    pass


class ImportService:
    """Own state transitions; callers never see a managed filesystem path."""
    def __init__(self, root: Path, catalog: GeoAssetCatalog, presentation: MapPresentationStore, session_exists: Callable[[str], object]) -> None:
        self.storage, self.catalog, self.presentation, self._session_exists = ImportStorage(root), catalog, presentation, session_exists
        self._lock = RLock()

    def _guard(self, session_id: str) -> None:
        try: self._session_exists(session_id)
        except Exception as exc: raise ImportError("unknown session") from exc

    def capabilities(self, session_id: str) -> dict[str, Any]:
        self._guard(session_id)
        return {"formats": [{"id": "geojson", "label": "GeoJSON", "enabled": True}, {"id": "geotiff", "label": "GeoTIFF / COG", "enabled": True}, {"id": "shapefile_zip", "label": "Shapefile ZIP", "enabled": False, "reason": "safe converter is not installed"}, {"id": "gpkg", "label": "GeoPackage", "enabled": False, "reason": "safe converter is not installed"}, {"id": "csv", "label": "CSV coordinates", "enabled": False, "reason": "CSV mapping is not implemented"}], "limits": {"max_files": 16, "max_file_bytes": 512 * 1024 * 1024, "max_total_bytes": 1024 * 1024 * 1024}}

    def create(self, session_id: str, files: object, client_request_id: str | None) -> dict[str, Any]:
        self._guard(session_id)
        try: return self.storage.create(session_id, files, client_request_id)
        except (ImportContractError, ImportStorageError) as exc: raise ImportError(str(exc)) from exc

    def open_upload(self, session_id: str, import_id: str, file_id: str):
        self._guard(session_id)
        try: return self.storage.open_upload(session_id, import_id, file_id)
        except (ImportStorageError, KeyError) as exc: raise ImportError(str(exc)) from exc

    def seal_upload(self, session_id: str, import_id: str, file_id: str, received: int, digest: str) -> dict[str, Any]:
        try: return self.storage.seal_upload(session_id, import_id, file_id, received, digest)
        except (ImportStorageError, KeyError) as exc: raise ImportError(str(exc)) from exc

    def inspect(self, session_id: str, import_id: str, expected_revision: int) -> dict[str, Any]:
        self._guard(session_id)
        with self._lock:
            snapshot = self.storage.snapshot(session_id, import_id)
            if snapshot["revision"] != expected_revision: raise ImportError("import revision conflict")
            if snapshot["status"] not in {"receiving", "awaiting_confirmation"}: raise ImportError("import cannot be inspected in its current state")
            if not self.storage.all_uploaded(session_id, import_id): raise ImportError("all declared files must be uploaded before inspection")
            candidates = []
            for item in snapshot["files"]:
                try: candidates.append(inspect_dataset(self.storage.file_path(session_id, import_id, item["file_id"]), item["name"], item["file_id"]))
                except InspectionError as exc: raise ImportError(f"{item['name']}: {exc}") from exc
            return self.storage.update(session_id, import_id, status="awaiting_confirmation", candidates=candidates, error=None)

    def commit(self, session_id: str, import_id: str, expected_revision: int, datasets: object, add_to_map: bool = True) -> dict[str, Any]:
        self._guard(session_id)
        with self._lock:
            snapshot = self.storage.snapshot(session_id, import_id)
            if snapshot["status"] == "completed": return snapshot
            if snapshot["revision"] != expected_revision: raise ImportError("import revision conflict")
            if snapshot["status"] != "awaiting_confirmation": raise ImportError("import must be inspected before publication")
            if not isinstance(datasets, list) or not datasets: raise ImportError("choose at least one inspected dataset")
            candidates = {item["dataset_id"]: item for item in snapshot["candidates"]}
            entries, layers = [], []
            selected_ids: set[str] = set()
            for selection in datasets:
                if not isinstance(selection, dict) or not isinstance(selection.get("dataset_id"), str): raise ImportError("invalid dataset selection")
                if selection["dataset_id"] in selected_ids: raise ImportError("dataset may be selected only once")
                selected_ids.add(selection["dataset_id"])
                candidate = candidates.get(selection["dataset_id"])
                if not candidate: raise ImportError("dataset was not found in this import")
                entry_id = candidate["dataset_id"]
                title = selection.get("title") if isinstance(selection.get("title"), str) else candidate["name"]
                try:
                    prepared = prepare_display_copy(self.storage.file_path(session_id, import_id, candidate["file_id"]), self.catalog.managed_root, import_id, entry_id, candidate["name"])
                except PreparationError as exc: raise ImportError(str(exc)) from exc
                entries.append({"entry_id": entry_id, "path": prepared, "name": candidate["name"], "title": title, "kind": "auxiliary"})
            try: assets = self.catalog.register_managed_batch(session_id=session_id, import_id=import_id, entries=entries)
            except Exception as exc: raise ImportError(str(exc)) from exc
            if add_to_map:
                for asset in assets:
                    suffix = Path(asset["name"]).suffix.lower(); raster = asset.get("format") == "GeoTIFF"
                    entry_id = next(item["entry_id"] for item in entries if item["title"] == asset["name"] or item["name"] == asset["name"])
                    render = default_raster_render(asset.get("metadata")) if raster else {"kind": "vector", "mode": "single"}
                    layers.append({"id": f"layer_{import_id.removeprefix('import_')}_{entry_id.removeprefix('dataset_')}", "asset_id": asset["id"], "title": asset["name"], "group_id": None, "visible": True, "opacity": 1, "z_index": 100, "min_zoom": None, "max_zoom": None, "render": render, "attribute_view": {"enabled": not raster}})
                try: self.presentation.append_user_layers(session_id, import_id, layers)
                except Exception as exc: raise ImportError(f"map publication failed: {exc}") from exc
            return self.storage.update(session_id, import_id, status="completed", assets=assets, layers=layers, error=None)

    def get(self, session_id: str, import_id: str) -> dict[str, Any]:
        self._guard(session_id)
        try: return self.storage.snapshot(session_id, import_id)
        except KeyError as exc: raise ImportError("unknown import") from exc

    def list(self, session_id: str) -> list[dict[str, Any]]:
        self._guard(session_id); return self.storage.list(session_id)

    def discard_session(self, session_id: str) -> None:
        """Participate in Angelus's confirmed Session deletion lifecycle."""
        with self._lock:
            self.catalog.unbind_session(session_id)
            self.storage.discard_session(session_id)
