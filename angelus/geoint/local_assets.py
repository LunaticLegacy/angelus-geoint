"""Local, versioned GEOINT indicator assets for the offline analysis path."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any
import uuid


class LocalAssetError(ValueError):
    """Raised when a local data asset is unsafe or cannot feed the risk model."""


REQUIRED_INDICATORS = ("ndvi_anomaly", "rainfall_anomaly", "soil_moisture_anomaly")


def _atomic_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as file:
            json.dump(payload, file, ensure_ascii=False, indent=2, sort_keys=True)
            file.write("\n")
            file.flush()
            os.fsync(file.fileno())
        os.replace(temporary, path)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def _feature_collection(path: Path) -> dict[str, Any]:
    try:
        document = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise LocalAssetError(f"cannot read GeoJSON asset: {path.name}") from exc
    if document.get("type") != "FeatureCollection" or not isinstance(document.get("features"), list):
        raise LocalAssetError("local asset must be a GeoJSON FeatureCollection")
    return document


def validate_indicator_features(features: list[Any]) -> dict[str, Any]:
    """Validate the small, explicit feature contract accepted by the prototype."""
    errors: list[str] = []
    geometry_types: set[str] = set()
    for index, feature in enumerate(features):
        if not isinstance(feature, dict) or feature.get("type") != "Feature":
            errors.append(f"feature {index} is not a GeoJSON Feature")
            continue
        geometry = feature.get("geometry")
        if not isinstance(geometry, dict) or not geometry.get("type"):
            errors.append(f"feature {index} has no geometry")
        else:
            geometry_types.add(str(geometry["type"]))
        properties = feature.get("properties")
        if not isinstance(properties, dict):
            errors.append(f"feature {index} has no properties object")
            continue
        for indicator in REQUIRED_INDICATORS:
            try:
                float(properties[indicator])
            except (KeyError, TypeError, ValueError):
                errors.append(f"feature {index} has invalid {indicator}")
    if not features:
        errors.append("asset has no features")
    if errors:
        preview = "; ".join(errors[:8])
        suffix = " …" if len(errors) > 8 else ""
        raise LocalAssetError(f"indicator asset validation failed: {preview}{suffix}")
    return {"valid_features": len(features), "geometry_types": sorted(geometry_types), "issues": []}


class LocalAssetCatalog:
    """Catalog assets rooted in the project-owned ``data/`` directory only."""

    def __init__(self, state_root: Path, data_root: Path | None = None) -> None:
        self._state_root = state_root.resolve()
        self._data_root = (data_root or (Path.cwd() / "data")).resolve()
        self._path = self._state_root / "assets.json"

    @property
    def data_root(self) -> Path:
        return self._data_root

    def list(self) -> list[dict[str, Any]]:
        return list(self._read().get("assets", []))

    def get(self, asset_id: str) -> dict[str, Any]:
        for asset in self.list():
            if asset.get("id") == asset_id:
                return asset
        raise KeyError(asset_id)

    def register_indicator_geojson(self, *, name: str, relative_path: str) -> dict[str, Any]:
        candidate = (self._data_root / relative_path).resolve()
        if candidate != self._data_root and self._data_root not in candidate.parents:
            raise LocalAssetError("asset path must stay inside the project data directory")
        if candidate.suffix.lower() not in {".geojson", ".json"}:
            raise LocalAssetError("local indicator assets must be .geojson or .json files")
        if not candidate.is_file():
            raise LocalAssetError(f"asset file does not exist: data/{relative_path}")
        document = _feature_collection(candidate)
        quality = validate_indicator_features(document["features"])
        digest = hashlib.sha256(candidate.read_bytes()).hexdigest()
        record = {
            "id": f"asset_{uuid.uuid4().hex[:12]}",
            "name": name.strip(),
            "kind": "drought_indicator_geojson",
            "relative_path": str(candidate.relative_to(self._data_root)),
            "sha256": digest,
            "registered_at": datetime.now(timezone.utc).isoformat(),
            "quality": quality,
        }
        document_state = self._read()
        document_state["assets"] = [*document_state["assets"], record]
        _atomic_json(self._path, document_state)
        return record

    def read_indicator_features(self, asset_id: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        asset = self.get(asset_id)
        if asset.get("kind") != "drought_indicator_geojson":
            raise LocalAssetError("asset is not an indicator GeoJSON dataset")
        path = (self._data_root / str(asset["relative_path"])).resolve()
        if self._data_root not in path.parents or not path.is_file():
            raise LocalAssetError("registered asset is no longer available under data/")
        current_digest = hashlib.sha256(path.read_bytes()).hexdigest()
        if current_digest != asset.get("sha256"):
            raise LocalAssetError("asset file changed after registration; register it again to create a new version")
        return asset, list(_feature_collection(path)["features"])

    def _read(self) -> dict[str, Any]:
        if not self._path.is_file():
            return {"schema_version": 1, "assets": []}
        try:
            document = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise LocalAssetError("local GEOINT asset catalog is unreadable") from exc
        if document.get("schema_version") != 1 or not isinstance(document.get("assets"), list):
            raise LocalAssetError("local GEOINT asset catalog has an unsupported format")
        return document


__all__ = ["LocalAssetCatalog", "LocalAssetError", "REQUIRED_INDICATORS", "validate_indicator_features"]
