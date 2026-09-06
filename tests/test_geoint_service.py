from datetime import date

from angelus.geoint import GeoIntService, drought_level, drought_score


AOI = {
    "type": "Polygon",
    "coordinates": [[
        [107.95, 34.18],
        [108.20, 34.18],
        [108.20, 34.35],
        [107.95, 34.35],
        [107.95, 34.18],
    ]],
}


def test_drought_score_orders_drier_inputs_higher():
    mild = drought_score(-0.05, -0.10, -0.08)
    severe = drought_score(-0.30, -0.55, -0.40)
    assert 0.0 <= mild < severe <= 1.0
    assert drought_level(severe) in {"severe", "critical"}


def test_synthetic_analysis_is_explicit_and_bounded():
    service = GeoIntService(database_url=None)
    result = service.analyze_drought(
        aoi=AOI,
        start_date=date(2026, 7, 1),
        end_date=date(2026, 9, 2),
        grid_size=4,
    )
    assert result["analysis_mode"] == "prototype-synthetic"
    assert result["summary"]["cells"] == 16
    assert result["persistence"]["mode"] == "memory"
    assert all(
        0.0 <= feature["properties"]["drought_score"] <= 1.0
        for feature in result["feature_collection"]["features"]
    )


def test_indicator_input_is_not_labeled_synthetic():
    service = GeoIntService(database_url=None)
    sample = {
        "geometry": AOI,
        "ndvi_anomaly": -0.2,
        "rainfall_anomaly": -0.4,
        "soil_moisture_anomaly": -0.25,
        "confidence": 0.9,
    }
    result = service.analyze_drought(
        aoi=AOI,
        start_date=date(2026, 8, 1),
        end_date=date(2026, 8, 31),
        indicators=[sample],
    )
    assert result["analysis_mode"] == "indicator-input"
    assert result["feature_collection"]["features"][0]["properties"]["synthetic"] is False


def test_geoint_does_not_reuse_an_unrelated_database_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://unrelated/application")
    monkeypatch.delenv("ANGELUS_GEOINT_DATABASE_URL", raising=False)
    assert GeoIntService(database_url=None).database_url is None
