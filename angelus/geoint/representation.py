"""Read-only projection from a bound catalog asset to a map source contract."""
from __future__ import annotations

from typing import Any

from .catalog import CatalogError


def map_representation(asset: dict[str, Any], *, asset_id: str) -> dict[str, Any]:
    """Return only a source that the mounted API can actually serve.

    This deliberately does not infer XYZ from an unknown file extension: the
    XYZ endpoint is not a general tile service yet.  Consumers therefore share
    one capability decision instead of manufacturing incompatible URLs.
    """
    fmt = asset.get("format")
    if fmt == "GeoJSON":
        kind = "vector"
    elif fmt == "GeoTIFF":
        kind = "cog"
    else:
        raise CatalogError("asset format has no configured map representation")
    metadata = asset.get("metadata") if isinstance(asset.get("metadata"), dict) else {}
    return {
        "kind": kind,
        "asset_id": asset_id,
        "url": f"/api/geoint/catalog/assets/{asset_id}/render",
        "projection": metadata.get("crs") or "EPSG:4326",
        "extent": metadata.get("bbox"),
    }


__all__ = ["map_representation"]
