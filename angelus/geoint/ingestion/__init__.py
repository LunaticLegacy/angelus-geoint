"""Managed browser ingestion and format-specific adapters."""

from .service import ImportError, ImportService

SUPPORTED_FORMATS = ("GeoJSON", "Shapefile", "FileGDB", "GeoTIFF", "ENVI")

__all__ = ["ImportError", "ImportService", "SUPPORTED_FORMATS"]
