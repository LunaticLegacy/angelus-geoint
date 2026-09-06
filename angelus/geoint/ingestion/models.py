"""Pure import DTO validation and fixed server-side limits."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

MAX_FILES = 16
MAX_FILE_BYTES = 512 * 1024 * 1024
MAX_TOTAL_BYTES = 1024 * 1024 * 1024
SUPPORTED_SUFFIXES = {
    ".geojson": "GeoJSON", ".json": "GeoJSON", ".tif": "GeoTIFF", ".tiff": "GeoTIFF",
    # Shapefile is a package.  Its complete bundle is validated by the
    # inspector after all individually declared members have arrived.
    ".shp": "Shapefile", ".shx": "Shapefile", ".dbf": "Shapefile", ".prj": "Shapefile", ".cpg": "Shapefile",
}
_SAFE_NAME = re.compile(r"^[^/\\\x00-\x1f]{1,160}$")


class ImportContractError(ValueError):
    """An invalid public import request; its message is safe for the UI."""


@dataclass(frozen=True)
class FileDeclaration:
    file_id: str
    name: str
    size_bytes: int

    @classmethod
    def from_input(cls, value: dict[str, Any], file_id: str) -> "FileDeclaration":
        name, size = value.get("name"), value.get("size_bytes")
        if not isinstance(name, str) or not _SAFE_NAME.fullmatch(name) or name in {".", ".."}:
            raise ImportContractError("invalid upload file name")
        if not isinstance(size, int) or isinstance(size, bool) or not 0 <= size <= MAX_FILE_BYTES:
            raise ImportContractError("upload file size is outside the allowed limit")
        if Path(name).suffix.lower() not in SUPPORTED_SUFFIXES:
            raise ImportContractError("only GeoJSON, GeoTIFF, and Shapefile members are supported")
        return cls(file_id=file_id, name=name, size_bytes=size)


def validate_declarations(values: object) -> list[FileDeclaration]:
    if not isinstance(values, list) or not values or len(values) > MAX_FILES:
        raise ImportContractError("upload requires between 1 and 16 files")
    declarations = [FileDeclaration.from_input(value, f"file_{index + 1:02d}") for index, value in enumerate(values) if isinstance(value, dict)]
    if len(declarations) != len(values) or sum(item.size_bytes for item in declarations) > MAX_TOTAL_BYTES:
        raise ImportContractError("upload file declarations exceed the allowed total")
    return declarations
