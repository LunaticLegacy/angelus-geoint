"""Bounded, dependency-light inspection for currently supported upload types."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import SUPPORTED_SUFFIXES


class InspectionError(ValueError):
    pass


def _coordinates(value: object, output: list[tuple[float, float]], limit: int = 200_000) -> None:
    if len(output) >= limit: return
    if isinstance(value, list) and len(value) >= 2 and isinstance(value[0], (int, float)) and isinstance(value[1], (int, float)):
        output.append((float(value[0]), float(value[1])))
    elif isinstance(value, list):
        for child in value: _coordinates(child, output, limit)


def inspect_dataset(path: Path, name: str, file_id: str) -> dict[str, Any]:
    suffix = path.suffix.lower(); fmt = SUPPORTED_SUFFIXES.get(suffix)
    if fmt is None: raise InspectionError("unsupported upload format")
    candidate: dict[str, Any] = {"dataset_id": f"dataset_{file_id}", "file_id": file_id, "name": name, "format": fmt, "geometry_types": [], "fields": [], "bands": [], "source_crs": {"authority": "EPSG:4326", "origin": "format_default", "status": "known"}, "extent": {"bbox": None, "crs": "EPSG:4326"}, "issues": [], "renderability": {"supported": True, "source_kind": "vector" if fmt == "GeoJSON" else "cog"}}
    if fmt == "GeoJSON":
        if path.stat().st_size > 20 * 1024 * 1024: raise InspectionError("GeoJSON display representation exceeds 20 MiB")
        try: value = json.loads(path.read_text(encoding="utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc: raise InspectionError("invalid GeoJSON") from exc
        if not isinstance(value, dict) or value.get("type") != "FeatureCollection" or not isinstance(value.get("features"), list):
            raise InspectionError("GeoJSON must be a FeatureCollection")
        features = value["features"]
        if len(features) > 50_000: raise InspectionError("GeoJSON feature count exceeds 50,000")
        points: list[tuple[float, float]] = []; geometry_types: set[str] = set(); fields: set[str] = set()
        for feature in features:
            if not isinstance(feature, dict): continue
            geometry = feature.get("geometry")
            if isinstance(geometry, dict):
                if isinstance(geometry.get("type"), str): geometry_types.add(geometry["type"])
                _coordinates(geometry.get("coordinates"), points)
            if isinstance(feature.get("properties"), dict): fields.update(str(key) for key in feature["properties"] if len(str(key)) <= 120)
        candidate["geometry_types"], candidate["fields"] = sorted(geometry_types), [{"name": field, "type": "unknown"} for field in sorted(fields)]
        if points:
            if any(abs(x) > 180 or abs(y) > 90 for x, y in points):
                raise InspectionError("GeoJSON coordinates are outside RFC 7946 longitude/latitude bounds")
            candidate["extent"]["bbox"] = [min(x for x, _ in points), min(y for _, y in points), max(x for x, _ in points), max(y for _, y in points)]
        elif features:
            candidate["issues"].append({"code": "missing_geometry", "message": "features have no readable geometry"})
    else:
        try:
            from osgeo import gdal
            dataset = gdal.Open(str(path), gdal.GA_ReadOnly)
        except Exception as exc: raise InspectionError("GeoTIFF reader is unavailable") from exc
        if dataset is None: raise InspectionError("invalid or unreadable GeoTIFF")
        projection = dataset.GetProjectionRef() or ""
        if not projection.strip(): raise InspectionError("GeoTIFF has no embedded CRS")
        transform = dataset.GetGeoTransform(can_return_null=True)
        if transform is None: raise InspectionError("GeoTIFF has no georeferencing transform")
        width, height = dataset.RasterXSize, dataset.RasterYSize
        corners = [(transform[0] + px * transform[1] + py * transform[2], transform[3] + px * transform[4] + py * transform[5]) for px, py in ((0, 0), (width, 0), (0, height), (width, height))]
        candidate["source_crs"] = {"authority": projection, "origin": "embedded", "status": "known"}
        candidate["extent"] = {"bbox": [min(x for x, _ in corners), min(y for _, y in corners), max(x for x, _ in corners), max(y for _, y in corners)], "crs": projection}
        candidate["bands"] = [{"index": index + 1, "nodata": dataset.GetRasterBand(index + 1).GetNoDataValue()} for index in range(dataset.RasterCount)]
    return candidate
