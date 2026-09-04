"""Non-negotiable coordinate-reference-system convention for GEOINT data."""

from __future__ import annotations


GEOGRAPHIC_CRS = "EPSG:4326"
PROJECTED_CRS = "EPSG:32662"
PROJECTED_CRS_NAME = "WGS 84 / Plate Carree"


def crs_convention() -> dict[str, str]:
    """Return the server-owned CRS contract exposed to every GEOINT client."""
    return {
        "geographic_crs": GEOGRAPHIC_CRS,
        "geographic_name": "WGS 84",
        "projected_crs": PROJECTED_CRS,
        "projected_name": PROJECTED_CRS_NAME,
        "vector_interchange": GEOGRAPHIC_CRS,
        "raster_analysis": PROJECTED_CRS,
        "categorical_resampling": "nearest",
    }


__all__ = ["GEOGRAPHIC_CRS", "PROJECTED_CRS", "PROJECTED_CRS_NAME", "crs_convention"]
