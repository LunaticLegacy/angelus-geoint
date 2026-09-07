"""Safe Shapefile-bundle validation, inspection and managed conversion.

The browser uploads each member separately, while this adapter treats the
members as one atomic dataset.  Neither the upload manifest nor callers need
to expose an arbitrary filesystem path.
"""
from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
from typing import Any, Iterator


REQUIRED_SUFFIXES = frozenset({".shp", ".shx", ".dbf"})
OPTIONAL_SUFFIXES = frozenset({".prj", ".cpg"})
SHAPEFILE_SUFFIXES = REQUIRED_SUFFIXES | OPTIONAL_SUFFIXES
WEB_MERCATOR_LIMIT = 20_037_508.35


class ShapefileError(ValueError):
    """A user-safe failure while handling a managed Shapefile bundle."""


def _stem(name: str) -> str:
    return Path(name).stem.casefold()


def _extent_looks_like_web_mercator(extent: tuple[float, float, float, float] | None) -> bool:
    """Identify the unambiguous metre-scale Web Mercator export pattern.

    This is deliberately conservative.  A source is inferred only when both
    axes are far outside geographic longitude/latitude bounds yet remain
    inside Web Mercator's finite world extent.  Common projected data such as
    UTM (roughly 500,000 metre eastings) is left untouched and remains an
    explicit CRS problem rather than silently assigned EPSG:3857.
    """
    if extent is None or len(extent) != 4:
        return False
    min_x, max_x, min_y, max_y = extent
    values = (min_x, max_x, min_y, max_y)
    return (
        all(isinstance(value, (int, float)) and abs(value) <= WEB_MERCATOR_LIMIT for value in values)
        and max(abs(min_x), abs(max_x)) > 2_000_000
        and max(abs(min_y), abs(max_y)) > 1_000_000
    )


def _display_translation_options(layer: Any) -> dict[str, object]:
    """Choose a defensible display conversion without trusting a bad `.prj`.

    GeoJSON's interchange CRS is WGS84.  Some boundary exports omit `.prj`
    while retaining EPSG:3857 coordinates; others incorrectly label those
    metre coordinates as geographic.  Their bounds make that contradiction
    observable, so preserve the original only when it is not unambiguous.
    """
    if layer is None:
        return {}
    extent = layer.GetExtent(can_return_null=True)
    spatial_ref = layer.GetSpatialRef()
    if _extent_looks_like_web_mercator(extent):
        if spatial_ref is None or spatial_ref.IsGeographic():
            return {"srcSRS": "EPSG:3857", "dstSRS": "EPSG:4326"}
    if spatial_ref is not None:
        return {"dstSRS": "EPSG:4326"}
    return {}


def shapefile_groups(files: list[dict[str, Any]]) -> list[list[dict[str, Any]]]:
    """Return validated same-stem Shapefile member groups.

    ``files`` contains private managed paths supplied only by ingestion.  The
    group result retains those paths but is never serialized directly.
    """
    groups: dict[str, list[dict[str, Any]]] = {}
    for item in files:
        name = item.get("name")
        if not isinstance(name, str) or Path(name).suffix.lower() not in SHAPEFILE_SUFFIXES:
            continue
        groups.setdefault(_stem(name), []).append(item)
    result: list[list[dict[str, Any]]] = []
    for stem, members in groups.items():
        suffixes = [Path(str(item["name"])).suffix.lower() for item in members]
        duplicates = {suffix for suffix in suffixes if suffixes.count(suffix) > 1}
        missing = REQUIRED_SUFFIXES - set(suffixes)
        if duplicates:
            raise ShapefileError(f"Shapefile {stem} has duplicate members: {', '.join(sorted(duplicates))}")
        if missing:
            raise ShapefileError(f"Shapefile {stem} is missing required members: {', '.join(sorted(missing))}")
        result.append(sorted(members, key=lambda item: Path(str(item["name"])).suffix.lower()))
    return result


@contextmanager
def materialized_bundle(members: list[dict[str, Any]]) -> Iterator[Path]:
    """Yield a private directory whose sibling filenames satisfy OGR."""
    if not members:
        raise ShapefileError("Shapefile bundle is empty")
    stem = Path(str(members[0]["name"])).stem
    with TemporaryDirectory(prefix="angelus-shp-") as temporary:
        directory = Path(temporary)
        for item in members:
            source = item.get("path")
            if not isinstance(source, Path):
                raise ShapefileError("Shapefile member is unavailable")
            target = directory / f"{stem}{source.suffix.lower()}"
            try:
                shutil.copyfile(source, target)
            except OSError as exc:
                raise ShapefileError("Shapefile member could not be staged") from exc
        yield directory / f"{stem}.shp"


def inspect_shapefile(members: list[dict[str, Any]], *, dataset_id: str, name: str) -> dict[str, Any]:
    """Inspect one complete bundle through OGR without leaking its location."""
    try:
        from osgeo import ogr, osr
    except Exception as exc:  # pragma: no cover - deployment dependency
        raise ShapefileError("Shapefile reader is unavailable; install GDAL/OGR") from exc
    with materialized_bundle(members) as source:
        dataset = ogr.Open(str(source), 0)
        if dataset is None:
            raise ShapefileError("invalid or unreadable Shapefile")
        layer = dataset.GetLayer(0)
        if layer is None:
            raise ShapefileError("Shapefile has no readable layer")
        definition = layer.GetLayerDefn()
        extent = layer.GetExtent(can_return_null=True)
        spatial_ref = layer.GetSpatialRef()
        authority = None
        if spatial_ref is not None:
            spatial_ref.AutoIdentifyEPSG()
            code = spatial_ref.GetAuthorityCode(None)
            authority = f"EPSG:{code}" if code else spatial_ref.ExportToWkt()
        fields = [{"name": definition.GetFieldDefn(index).GetName(), "type": definition.GetFieldDefn(index).GetTypeName()} for index in range(definition.GetFieldCount())]
        geometry_name = ogr.GeometryTypeToName(layer.GetGeomType()) or "Unknown"
        bbox = list(extent) if extent is not None else None
        return {
            "dataset_id": dataset_id,
            "file_ids": [str(item["file_id"]) for item in members],
            "name": name,
            "format": "Shapefile",
            "geometry_types": [geometry_name],
            "fields": fields,
            "bands": [],
            "source_crs": {"authority": authority or "unknown", "origin": "prj" if authority else "missing", "status": "known" if authority else "unknown"},
            "extent": {"bbox": bbox, "crs": authority or "unknown"},
            "issues": [] if authority else [{"code": "missing_crs", "message": "Shapefile has no readable .prj CRS"}],
            "renderability": {"supported": True, "source_kind": "vector"},
            "provenance": {"original_format": "Shapefile"},
        }


def convert_shapefile_to_geojson(members: list[dict[str, Any]], target: Path) -> None:
    """Create a managed GeoJSON display copy from one validated package.

    A Shapefile without a ``.prj`` has no defensible source CRS.  Asking GDAL
    to reproject it in that state fails even though its geometry and DBF are
    perfectly readable.  Reproject only when OGR can identify a source SRS;
    otherwise preserve the coordinates and let the existing inspection warning
    make the uncertainty explicit to the operator.
    """
    try:
        from osgeo import gdal, ogr
    except Exception as exc:  # pragma: no cover - deployment dependency
        raise ShapefileError("Shapefile conversion requires GDAL/OGR") from exc
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = target.with_suffix(".partial.geojson")
    temporary.unlink(missing_ok=True)
    with materialized_bundle(members) as source:
        try:
            dataset = ogr.Open(str(source), 0)
            if dataset is None or dataset.GetLayerCount() < 1:
                raise ShapefileError("invalid or unreadable Shapefile")
            layer = dataset.GetLayer(0)
            options: dict[str, object] = {"format": "GeoJSON", **_display_translation_options(layer)}
            result = gdal.VectorTranslate(str(temporary), dataset, **options)
            dataset = None
            if result is None:
                raise ShapefileError("GDAL could not convert Shapefile to GeoJSON")
            result = None
            if not temporary.is_file() or temporary.stat().st_size == 0:
                raise ShapefileError("converted GeoJSON is unavailable")
            temporary.replace(target)
        except ShapefileError:
            temporary.unlink(missing_ok=True)
            raise
        except Exception as exc:
            temporary.unlink(missing_ok=True)
            raise ShapefileError("Shapefile could not be converted to GeoJSON") from exc
