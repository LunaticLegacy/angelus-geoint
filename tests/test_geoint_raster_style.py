"""Display defaults for scientific rasters must never use raw sample values."""
from angelus.geoint import default_raster_render, effective_raster_render


def test_statistics_stretch_selects_independent_rgb_band_ranges():
    render = default_raster_render({
        "nodata": -9999,
        "bands": [
            {"statistics": [10, 110, 50, 8]},
            {"statistics": [20, 220, 60, 9]},
            {"statistics": [30, 330, 70, 10]},
        ],
    })
    assert render["mode"] == "rgb"
    assert render["bands"] == [1, 2, 3]
    assert render["range"] == {"min": 10.0, "max": 110.0, "method": "statistics"}
    assert render["band_ranges"] == [
        {"band": 1, "min": 10.0, "max": 110.0},
        {"band": 2, "min": 20.0, "max": 220.0},
        {"band": 3, "min": 30.0, "max": 330.0},
    ]
    assert render["nodata"] == -9999.0


def test_existing_user_range_wins_over_statistics_default():
    result = effective_raster_render(
        {"kind": "raster", "range": {"min": 0.2, "max": 0.8, "method": "manual"}},
        {"bands": [{"statistics": [0, 1, 0.5, 0.1]}]},
    )
    assert result["range"] == {"min": 0.2, "max": 0.8, "method": "manual"}
    assert result["band_ranges"] == [{"band": 1, "min": 0.0, "max": 1.0}]
