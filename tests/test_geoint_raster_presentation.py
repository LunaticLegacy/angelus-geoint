"""Regression tests for browser-safe GeoTIFF map representations."""
from __future__ import annotations

import importlib.util

import pytest

if importlib.util.find_spec("osgeo") is None:
    pytest.skip("GDAL/OGR is optional", allow_module_level=True)

from osgeo import gdal, osr

from angelus.geoint import GeoAssetCatalog, prepare_web_raster


def test_web_raster_derivative_is_tiled_epsg_3857_cog(tmp_path):
    source, target = tmp_path / "source.tif", tmp_path / "display.tif"
    dataset = gdal.GetDriverByName("GTiff").Create(str(source), 4, 4, 1, gdal.GDT_Byte)
    reference = osr.SpatialReference(); reference.ImportFromEPSG(4326)
    dataset.SetProjection(reference.ExportToWkt())
    dataset.SetGeoTransform((108.0, 0.1, 0, 34.1, 0, -0.1))
    dataset.GetRasterBand(1).Fill(1)
    dataset = None

    prepare_web_raster(source, target)

    output = gdal.Open(str(target), gdal.GA_ReadOnly)
    display_reference = osr.SpatialReference(wkt=output.GetProjectionRef())
    display_reference.AutoIdentifyEPSG()
    assert display_reference.GetAuthorityCode(None) == "3857"
    assert output.GetRasterBand(1).GetBlockSize()[1] > 1


def test_catalog_upgrades_legacy_geotiff_on_first_render_request(tmp_path):
    source = tmp_path / "source.tif"
    dataset = gdal.GetDriverByName("GTiff").Create(str(source), 4, 4, 1, gdal.GDT_Byte)
    reference = osr.SpatialReference(); reference.ImportFromEPSG(4326)
    dataset.SetProjection(reference.ExportToWkt())
    dataset.SetGeoTransform((108.0, 0.1, 0, 34.1, 0, -0.1))
    dataset.GetRasterBand(1).Fill(1)
    dataset = None

    catalog = GeoAssetCatalog(tmp_path / "catalog")
    catalog.managed_root.mkdir(parents=True)
    original = catalog.managed_root / "legacy.tif"
    original.write_bytes(source.read_bytes())
    catalog._save({"schema_version": 2, "sources": [], "scans": [], "jobs": [], "assets": [{
        "id": "asset_legacy", "format": "GeoTIFF", "sessions": ["session-a"],
        "storage": {"kind": "managed", "relative_path": "legacy.tif"}, "metadata": {},
        "metadata_version": 1,
    }]})

    asset, display = catalog.bound_path("session-a", "asset_legacy")

    assert original.exists()
    assert display != original
    assert asset["metadata"]["crs"] == "EPSG:3857"
    assert "rendering" not in asset
