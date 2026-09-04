"""Stable GEOINT domain primitives (legacy modules remain import-compatible)."""
from ..geometry import geometry_bbox, geometry_contains_point, geometry_representative_point
from ..crs import crs_convention
from ..service import GeoIntError
__all__=["GeoIntError","crs_convention","geometry_bbox","geometry_contains_point","geometry_representative_point"]
