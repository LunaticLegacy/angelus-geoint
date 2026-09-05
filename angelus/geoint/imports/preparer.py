"""Prepare a controlled display copy without altering an uploaded original."""
from __future__ import annotations

from hashlib import sha256
import os
from pathlib import Path
import shutil

from ..raster_presentation import RasterPresentationError, prepare_web_raster


class PreparationError(ValueError):
    pass


def prepare_display_copy(source: Path, managed_root: Path, import_id: str, entry_id: str, name: str) -> Path:
    """Prepare a catalogue-owned display copy without mutating user data."""
    suffix = source.suffix.lower(); target_dir = managed_root / ".import-staging" / import_id
    target_dir.mkdir(parents=True, exist_ok=True, mode=0o700); os.chmod(target_dir, 0o700)
    target = target_dir / f"{entry_id}{suffix}"
    if suffix in {".tif", ".tiff"}:
        try:
            prepare_web_raster(source, target)
        except RasterPresentationError as exc:
            raise PreparationError(str(exc)) from exc
    else:
        shutil.copyfile(source, target); os.chmod(target, 0o600)
        if source.stat().st_size != target.stat().st_size:
            target.unlink(missing_ok=True); raise PreparationError("display copy integrity verification failed")
    return target
