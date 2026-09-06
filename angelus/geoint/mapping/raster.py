"""Create browser-safe raster representations without changing user inputs."""
from __future__ import annotations

import os
from pathlib import Path


class RasterPresentationError(ValueError):
    """Raised when a validated raster cannot be prepared for the map."""


def prepare_web_raster(source: Path, target: Path) -> None:
    """Reproject a GeoTIFF into a tiled EPSG:3857 COG display derivative.

    OpenLayers can only combine a GeoTIFF with the main map when it can resolve
    its projection. User supplied TIFFs frequently contain a custom WKT (or a
    local projected CRS) rather than a resolvable EPSG code. The original file
    remains untouched and Angelus produces a managed web representation.
    """
    try:
        from osgeo import gdal, osr  # type: ignore
    except Exception as exc:  # pragma: no cover - environment dependent
        raise RasterPresentationError("GeoTIFF display conversion requires GDAL") from exc

    source = source.resolve(strict=True)
    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    temporary = target.with_suffix(".partial.tif")
    temporary.unlink(missing_ok=True)
    try:
        options = gdal.WarpOptions(
            format="COG",
            dstSRS="EPSG:3857",
            resampleAlg="near",
            creationOptions=["COMPRESS=DEFLATE", "BIGTIFF=IF_SAFER", "OVERVIEWS=AUTO"],
        )
        dataset = gdal.Warp(str(temporary), str(source), options=options)
        if dataset is None:
            raise RasterPresentationError("GDAL could not create a map display raster")
        dataset = None

        result = gdal.Open(str(temporary), gdal.GA_ReadOnly)
        if result is None:
            raise RasterPresentationError("generated map display raster is unreadable")
        reference = osr.SpatialReference(wkt=result.GetProjectionRef() or "")
        reference.AutoIdentifyEPSG()
        authority, code = reference.GetAuthorityName(None), reference.GetAuthorityCode(None)
        result = None
        if authority != "EPSG" or code != "3857":
            raise RasterPresentationError("generated map display raster is not EPSG:3857")
        os.replace(temporary, target)
        os.chmod(target, 0o600)
    except RasterPresentationError:
        temporary.unlink(missing_ok=True)
        raise
    except Exception as exc:
        temporary.unlink(missing_ok=True)
        raise RasterPresentationError("GeoTIFF could not be reprojected for map display") from exc


__all__ = ["RasterPresentationError", "prepare_web_raster"]
