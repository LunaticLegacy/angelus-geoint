"""Offline AOI-to-risk closure tests using a user-supplied local GeoJSON asset."""

from datetime import date
import json

from angelus.geoint import GeoIntService


def test_registered_local_asset_runs_only_units_inside_aoi(tmp_path):
    data_root = tmp_path / "data"
    data_root.mkdir()
    asset_path = data_root / "indicators.geojson"
    asset_path.write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "id": "inside", "geometry": {"type": "Point", "coordinates": [108.0, 34.2]}, "properties": {"ndvi_anomaly": -0.2, "rainfall_anomaly": -0.4, "soil_moisture_anomaly": -0.25, "confidence": 0.9}},
        {"type": "Feature", "id": "outside", "geometry": {"type": "Point", "coordinates": [109.0, 35.2]}, "properties": {"ndvi_anomaly": -0.3, "rainfall_anomaly": -0.5, "soil_moisture_anomaly": -0.3}},
    ]}), encoding="utf-8")
    service = GeoIntService(state_root=tmp_path / "state", data_root=data_root)
    asset = service.register_local_indicator_asset(name="本地指标", relative_path="indicators.geojson")
    result = service.analyze_local_asset(
        asset_id=asset["id"],
        aoi={"type": "Polygon", "coordinates": [[[107.9, 34.1], [108.1, 34.1], [108.1, 34.3], [107.9, 34.3], [107.9, 34.1]]]},
        start_date=date(2026, 7, 1),
        end_date=date(2026, 8, 1),
    )
    assert result["analysis_mode"] == "local-asset-indicators"
    assert result["evidence"]["source_units"] == 2
    assert result["evidence"]["units_in_aoi"] == 1
    assert result["feature_collection"]["features"][0]["id"] == "inside"
    assert result["feature_collection"]["features"][0]["properties"]["synthetic"] is False
    restored = GeoIntService(state_root=tmp_path / "state", data_root=data_root)
    assert restored.get_analysis(result["id"])["evidence"]["asset_id"] == asset["id"]
