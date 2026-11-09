"""Keep pytest's session basetemp usable on locked-down Windows profiles.

``_pytest.tmpdir.TempPathFactory.getbasetemp`` creates ``pytest-of-<user>``
inside ``tempfile.gettempdir()`` and then *scans* it (``make_numbered_dir``).
On some Windows profiles that directory carries an ACL that denies listing, so
the scan raises ``PermissionError [WinError 5]`` and every ``tmp_path`` test
fails during setup instead of at its own assertion.

This hook runs before ``_pytest.tmpdir.pytest_configure`` builds the factory and
only intervenes when that exact directory is genuinely unusable, so POSIX and
CI behaviour is unchanged.  An explicit ``--basetemp`` always wins.
"""
from __future__ import annotations

import getpass
import os
import tempfile
from pathlib import Path

import pytest

# Repository-local fallback; already excluded by .gitignore (``.pytest-tmp*/``).
_FALLBACK_BASETEMP = Path(__file__).resolve().parent / ".pytest-tmp"


def _usable(directory: Path) -> bool:
    """Return whether pytest could enumerate and extend a temp directory.

    Args:
        directory: Directory pytest is about to list and add a child to.

    Returns:
        ``True`` when the directory can be listed and a child directory can be
        created and removed there; ``False`` on any permission or I/O failure.
    """
    try:
        with os.scandir(directory) as entries:
            for _ in entries:
                break
        probe = directory / f".pytest-probe-{os.getpid()}"
        probe.mkdir()
        probe.rmdir()
    except OSError:
        return False
    return True


def _basetemp_root_usable() -> bool:
    """Return whether pytest's default basetemp location is workable.

    Mirrors ``TempPathFactory.getbasetemp``: the session directory is numbered
    inside ``<temproot>/pytest-of-<user>``.  A not-yet-created session root is
    fine because pytest creates it before scanning, so only existing
    directories are probed.

    Returns:
        ``True`` when the platform temp root and any existing pytest session
        root can be listed and extended.
    """
    raw_root = os.environ.get("PYTEST_DEBUG_TEMPROOT") or tempfile.gettempdir()
    try:
        temproot = Path(raw_root).resolve()
    except OSError:
        return False
    if not _usable(temproot):
        return False
    user = getpass.getuser() or "unknown"
    for candidate in (temproot / f"pytest-of-{user}", temproot / "pytest-of-unknown"):
        if candidate.is_dir() and not _usable(candidate):
            return False
    return True


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config: pytest.Config) -> None:
    """Point ``--basetemp`` at a writable root when the platform temp is not.

    Args:
        config: Active pytest configuration; ``config.option.basetemp`` is read
            by ``_pytest.tmpdir`` immediately after this hook.

    Returns:
        None. The option is only rewritten when the default root is unusable.
    """
    if config.option.basetemp:
        # An explicit selection is the operator's decision; never override it.
        return
    if _basetemp_root_usable():
        return
    _FALLBACK_BASETEMP.mkdir(exist_ok=True)
    config.option.basetemp = str(_FALLBACK_BASETEMP)
