"""Versioned, explainable drought anomaly scoring primitives."""

from __future__ import annotations

import math
from typing import Any


DEFAULT_DROUGHT_WEIGHTS = {"vegetation": 0.45, "rainfall": 0.35, "soil_moisture": 0.20}


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    return max(low, min(high, float(value)))


def normalize_weights(weights: dict[str, float] | None = None) -> dict[str, float]:
    candidate = {**DEFAULT_DROUGHT_WEIGHTS, **(weights or {})}
    expected = tuple(DEFAULT_DROUGHT_WEIGHTS)
    if any(not math.isfinite(float(candidate[key])) or float(candidate[key]) < 0 for key in expected):
        raise ValueError("drought weights must be finite non-negative values")
    total = sum(float(candidate[key]) for key in expected)
    if total <= 0:
        raise ValueError("at least one drought weight must be positive")
    return {key: float(candidate[key]) / total for key in expected}


def drought_score(ndvi_anomaly: float, rainfall_anomaly: float, soil_moisture_anomaly: float, *, weights: dict[str, float] | None = None) -> float:
    """Convert normalized negative anomalies into a 0..1 drought-stress score."""
    ndvi = clamp(-float(ndvi_anomaly) / 0.35)
    rain = clamp(-float(rainfall_anomaly) / 0.60)
    soil = clamp(-float(soil_moisture_anomaly) / 0.45)
    model_weights = normalize_weights(weights)
    return round(model_weights["vegetation"] * ndvi + model_weights["rainfall"] * rain + model_weights["soil_moisture"] * soil, 4)


def drought_level(score: float) -> str:
    if score >= 0.75:
        return "critical"
    if score >= 0.55:
        return "severe"
    if score >= 0.35:
        return "moderate"
    if score >= 0.15:
        return "watch"
    return "normal"


def indicator_features(indicators: list[dict[str, Any]], *, weights: dict[str, float] | None = None) -> list[dict[str, Any]]:
    features: list[dict[str, Any]] = []
    for index, item in enumerate(indicators):
        geometry = item.get("geometry")
        if not isinstance(geometry, dict):
            raise ValueError(f"indicator sample {index} is missing geometry")
        score = drought_score(float(item["ndvi_anomaly"]), float(item["rainfall_anomaly"]), float(item["soil_moisture_anomaly"]), weights=weights)
        features.append({"type": "Feature", "id": item.get("id") or f"sample-{index}", "geometry": geometry, "properties": {
            "ndvi_anomaly": float(item["ndvi_anomaly"]), "rainfall_anomaly": float(item["rainfall_anomaly"]), "soil_moisture_anomaly": float(item["soil_moisture_anomaly"]),
            "drought_score": score, "drought_level": drought_level(score), "confidence": clamp(float(item.get("confidence", 1.0))), "synthetic": False, **dict(item.get("properties") or {}),
        }})
    return features


def summarize(features: list[dict[str, Any]]) -> dict[str, Any]:
    scores = [float(feature["properties"]["drought_score"]) for feature in features]
    counts: dict[str, int] = {}
    for feature in features:
        level = str(feature["properties"]["drought_level"])
        counts[level] = counts.get(level, 0) + 1
    high = sum(counts.get(level, 0) for level in ("severe", "critical"))
    return {"cells": len(features), "mean_score": round(sum(scores) / len(scores), 4) if scores else 0.0, "max_score": round(max(scores), 4) if scores else 0.0, "high_risk_ratio": round(high / len(features), 4) if features else 0.0, "dominant_level": max(counts, key=counts.get) if counts else "unknown", "level_counts": counts}


__all__ = ["DEFAULT_DROUGHT_WEIGHTS", "clamp", "drought_level", "drought_score", "indicator_features", "normalize_weights", "summarize"]
