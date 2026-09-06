"""Dependency-light GeoJSON geometry validation and AOI selection helpers."""

from __future__ import annotations

from typing import Any, Iterator


def walk_coordinates(value: Any) -> Iterator[tuple[float, float]]:
    if isinstance(value, (list, tuple)):
        if len(value) >= 2 and all(isinstance(item, (int, float)) for item in value[:2]):
            yield float(value[0]), float(value[1])
            return
        for item in value:
            yield from walk_coordinates(item)


def geometry_bbox(geometry: dict[str, Any]) -> tuple[float, float, float, float]:
    """Return a GeoJSON Polygon/MultiPolygon bounding box after shape checks."""
    if geometry.get("type") not in {"Polygon", "MultiPolygon"}:
        raise ValueError("AOI must be a GeoJSON Polygon or MultiPolygon")
    points = tuple(walk_coordinates(geometry.get("coordinates")))
    if not points:
        raise ValueError("AOI geometry contains no coordinates")
    xs = [point[0] for point in points]
    ys = [point[1] for point in points]
    return min(xs), min(ys), max(xs), max(ys)


def rectangle(minx: float, miny: float, maxx: float, maxy: float) -> dict[str, Any]:
    return {"type": "Polygon", "coordinates": [[[minx, miny], [maxx, miny], [maxx, maxy], [minx, maxy], [minx, miny]]]}


def _point_in_ring(point: tuple[float, float], ring: list[Any]) -> bool:
    x, y = point
    inside = False
    coordinates = [item for item in ring if isinstance(item, (list, tuple)) and len(item) >= 2]
    if len(coordinates) < 3:
        return False
    previous = coordinates[-1]
    for current in coordinates:
        x1, y1 = float(previous[0]), float(previous[1])
        x2, y2 = float(current[0]), float(current[1])
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
        previous = current
    return inside


def geometry_contains_point(geometry: dict[str, Any], point: tuple[float, float]) -> bool:
    if geometry.get("type") == "Polygon":
        polygons = [geometry.get("coordinates", [])]
    elif geometry.get("type") == "MultiPolygon":
        polygons = geometry.get("coordinates", [])
    else:
        raise ValueError("AOI must be a GeoJSON Polygon or MultiPolygon")
    for polygon in polygons:
        if polygon and _point_in_ring(point, polygon[0]) and not any(_point_in_ring(point, hole) for hole in polygon[1:]):
            return True
    return False


def geometry_representative_point(geometry: dict[str, Any]) -> tuple[float, float]:
    if geometry.get("type") == "Point":
        coordinates = geometry.get("coordinates", [])
        if len(coordinates) >= 2:
            return float(coordinates[0]), float(coordinates[1])
    points = tuple(walk_coordinates(geometry.get("coordinates")))
    if not points:
        raise ValueError("feature geometry contains no coordinates")
    return sum(point[0] for point in points) / len(points), sum(point[1] for point in points) / len(points)


__all__ = ["geometry_bbox", "geometry_contains_point", "geometry_representative_point", "rectangle", "walk_coordinates"]
