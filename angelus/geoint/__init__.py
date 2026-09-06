"""Stable, short public interface for Angelus GEOINT.

Application code imports public services from this facade.  Implementation
packages remain semantic and independently testable under ``analysis``,
``assets``, ``mapping``, ``ingestion``, ``processing``, ``agent`` and
``runtime``.
"""

from .agent import GeoIntToolProvider, geoint_tool_registration
from .analysis import GeoIntError, GeoIntService, LocalAssetError, PostGISUnavailable, crs_convention, drought_level, drought_score
from .assets import CatalogError, DirectoryDialogUnavailable, GeoAssetCatalog, RemoteDownloadError, SourceNotAuthorized, download_public_dataset
from .ingestion import ImportError, ImportService
from .mapping import BasemapStore, MapPresentationStore, NoRedirect, PresentationError, RasterPresentationError, XYZConfig, default_raster_render, effective_raster_render, fetch_tile, layer_record, map_representation, prepare_web_raster
from .processing import DerivationService
from .runtime import GeoIntRuntime

__all__ = ["BasemapStore", "CatalogError", "DerivationService", "DirectoryDialogUnavailable", "GeoAssetCatalog", "GeoIntError", "GeoIntRuntime", "GeoIntService", "GeoIntToolProvider", "ImportError", "ImportService", "LocalAssetError", "MapPresentationStore", "NoRedirect", "PostGISUnavailable", "PresentationError", "RasterPresentationError", "RemoteDownloadError", "SourceNotAuthorized", "XYZConfig", "crs_convention", "default_raster_render", "download_public_dataset", "drought_level", "drought_score", "effective_raster_render", "fetch_tile", "geoint_tool_registration", "layer_record", "map_representation", "prepare_web_raster"]
