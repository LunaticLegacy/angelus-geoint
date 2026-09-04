"""Explicitly synthetic-only output used to exercise the GEOINT UI."""

from __future__ import annotations

import math
from typing import Any

from .geometry import geometry_bbox, rectangle
from .risk_model import clamp, drought_level, drought_score


def synthetic_features(aoi: dict[str, Any], grid_size: int) -> list[dict[str, Any]]:
    minx, miny, maxx, maxy = geometry_bbox(aoi)
    cols = rows = max(2, min(int(grid_size), 10))
    dx, dy = (maxx - minx) / cols, (maxy - miny) / rows
    features: list[dict[str, Any]] = []
    for row in range(rows):
        for col in range(cols):
            cell_minx, cell_miny = minx + col * dx, miny + row * dy
            phase = (math.sin((row + 1) * 1.71 + (col + 1) * 0.83 + minx * 0.03) + math.cos((row + 1) * 0.57 - (col + 1) * 1.39 + miny * 0.05)) / 2.0
            dry = clamp((phase + 1.0) / 2.0)
            ndvi, rain, soil = round(-(0.04 + dry * 0.34), 4), round(-(0.08 + dry * 0.58), 4), round(-(0.05 + dry * 0.44), 4)
            score = drought_score(ndvi, rain, soil)
            features.append({"type": "Feature", "id": f"cell-{row}-{col}", "geometry": rectangle(cell_minx, cell_miny, cell_minx + dx, cell_miny + dy), "properties": {
                "row": row, "col": col, "ndvi_anomaly": ndvi, "rainfall_anomaly": rain, "soil_moisture_anomaly": soil,
                "drought_score": score, "drought_level": drought_level(score), "confidence": 0.35, "synthetic": True,
            }})
    return features


__all__ = ["synthetic_features"]
