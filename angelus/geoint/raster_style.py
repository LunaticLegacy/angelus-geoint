"""Safe, metadata-derived defaults for browser raster presentation.

This module deliberately only derives a display proposal.  It never reads a
host path and it never changes the analytical source data.  A user supplied
layer render configuration still wins over these defaults.
"""
from __future__ import annotations

from math import isfinite
from typing import Any


def _number(value: object) -> float | None:
    """Return a finite number, refusing bools and malformed metadata."""
    if isinstance(value, bool):
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if isfinite(number) else None


def _band_range(band: object) -> dict[str, float] | None:
    if not isinstance(band, dict):
        return None
    statistics = band.get("statistics")
    if not isinstance(statistics, (list, tuple)) or len(statistics) < 2:
        return None
    minimum, maximum = _number(statistics[0]), _number(statistics[1])
    if minimum is None or maximum is None or maximum <= minimum:
        return None
    return {"min": minimum, "max": maximum}


def default_raster_render(metadata: object) -> dict[str, Any]:
    """Produce a stable statistics stretch for a raster metadata record.

    One-band inputs render as greyscale; three or more bands use the first
    three bands as RGB.  Each selected band receives an independent range,
    which avoids one wide-band channel washing out the other two.  If GDAL
    cannot establish a useful range, the frontend still asks OpenLayers to
    normalize from GeoTIFF metadata/type bounds rather than using raw values.
    """
    metadata = metadata if isinstance(metadata, dict) else {}
    bands = metadata.get("bands") if isinstance(metadata.get("bands"), list) else []
    band_count = len(bands)
    selected = [1, 2, 3] if band_count >= 3 else [1]
    ranges: list[dict[str, float | int]] = []
    for index in selected:
        value = _band_range(bands[index - 1] if index <= band_count else None)
        if value is not None:
            ranges.append({"band": index, **value})

    first_range = ranges[0] if ranges else None
    nodata = _number(metadata.get("nodata"))
    render: dict[str, Any] = {
        "kind": "raster",
        "mode": "rgb" if len(selected) == 3 else "single_band",
        "bands": selected,
        "range": {
            "min": first_range["min"] if first_range else None,
            "max": first_range["max"] if first_range else None,
            "method": "statistics",
        },
        "band_ranges": ranges,
        "nodata": nodata,
        "resampling": "linear",
        "interpolate": True,
    }
    return render


def effective_raster_render(render: object, metadata: object) -> dict[str, Any]:
    """Merge an editable render record over safe statistics-derived defaults."""
    defaults = default_raster_render(metadata)
    if not isinstance(render, dict):
        return defaults
    effective = {**defaults, **render}
    requested_range = render.get("range")
    if isinstance(requested_range, dict):
        effective["range"] = {**defaults["range"], **requested_range}
    # Existing documents created before v2 raster display options must receive
    # the derived ranges.  An explicit empty list remains an intentional user
    # choice only when the caller also supplied a render range.
    if "band_ranges" not in render:
        effective["band_ranges"] = defaults["band_ranges"]
    return effective


__all__ = ["default_raster_render", "effective_raster_render"]
