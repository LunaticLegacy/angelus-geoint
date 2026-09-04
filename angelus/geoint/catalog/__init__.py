"""Authorized, read-only catalogue for locally selected GEOINT sources.

The catalogue stores registrations in Angelus state; it never writes to a
selected source directory and never accepts a filesystem path from an API
caller after the directory-picker grant has been made.
"""

from .service import (
    CatalogError, DirectoryDialogUnavailable, GeoAssetCatalog,
    SourceNotAuthorized, SystemDirectoryPicker,
)

__all__ = ["CatalogError", "DirectoryDialogUnavailable", "GeoAssetCatalog", "SourceNotAuthorized", "SystemDirectoryPicker"]
