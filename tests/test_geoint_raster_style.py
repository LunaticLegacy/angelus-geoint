"""Display defaults for scientific rasters must never use raw sample values."""
from angelus.geoint import default_raster_render, effective_raster_render


def test_statistics_stretch_selects_independent_rgb_band_ranges():
    render = default_raster_render({
        "nodata": -9999,
        "bands": [
            {"statistics": [10, 110, 50, 8], "color_interpretation": "Red"},
            {"statistics": [20, 220, 60, 9], "color_interpretation": "Green"},
            {"statistics": [30, 330, 70, 10], "color_interpretation": "Blue"},
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


def test_multiband_scientific_stack_defaults_to_first_band_and_nearest_cells():
    render = default_raster_render({
        "bands": [
            {"statistics": [0.39, 0.44, 0.41, 0.01], "color_interpretation": "Gray"},
            {"statistics": [0.45, 0.51, 0.48, 0.01], "color_interpretation": "Undefined"},
            {"statistics": [0.86, 0.96, 0.91, 0.02], "color_interpretation": "Undefined"},
        ],
        "raster_size": [15, 17],
    })
    assert render["mode"] == "single_band"
    assert render["bands"] == [1]
    assert render["resampling"] == "nearest"
    assert render["interpolate"] is False


def test_existing_user_range_wins_over_statistics_default():
    result = effective_raster_render(
        {"kind": "raster", "range": {"min": 0.2, "max": 0.8, "method": "manual"}},
        {"bands": [{"statistics": [0, 1, 0.5, 0.1]}]},
    )
    assert result["range"] == {"min": 0.2, "max": 0.8, "method": "manual"}
    assert result["band_ranges"] == [{"band": 1, "min": 0.0, "max": 1.0}]
