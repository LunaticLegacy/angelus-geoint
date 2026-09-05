"""Construct safe, source-free map layer records from catalog assets.

Both browser imports and Agent actions use this one factory.  The browser never
receives a storage path: :mod:`presentation` later materializes a controlled
render endpoint from ``asset_id``.
"""
from __future__ import annotations

from typing import Any

from .raster_style import default_raster_render


def layer_record(
    asset: dict[str, Any],
    *,
    layer_id: str,
    title: str | None = None,
    group_id: str | None = None,
    z_index: int = 100,
) -> dict[str, Any]:
    """Return the shared editable map-layer shape for one supported asset."""
    raster = asset.get("format") == "GeoTIFF"
    if not raster and asset.get("format") != "GeoJSON":
        raise ValueError("asset format has no configured map layer")
    display_title = title if isinstance(title, str) and title.strip() else asset.get("name")
    if not isinstance(display_title, str) or not display_title.strip():
        display_title = str(asset.get("id", "untitled layer"))
    return {
        "id": layer_id,
        "asset_id": asset["id"],
        "title": display_title.strip(),
        "group_id": group_id,
        "visible": True,
        "opacity": 1,
        "z_index": z_index,
        "min_zoom": None,
        "max_zoom": None,
        "render": default_raster_render(asset.get("metadata")) if raster else {"kind": "vector", "mode": "single"},
        "attribute_view": {"enabled": not raster},
    }


__all__ = ["layer_record"]
