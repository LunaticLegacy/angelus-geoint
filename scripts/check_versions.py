"""Check that Angelus distribution manifests match its runtime version."""
from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
from dataclasses import dataclass
import json
from pathlib import Path
import re
import sys
import tomllib


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

PACKAGE_JSON = Path("package.json")
TAURI_CONF = Path("src-tauri") / "tauri.conf.json"
CARGO_MANIFEST = Path("src-tauri") / "Cargo.toml"
CARGO_LOCK = Path("src-tauri") / "Cargo.lock"
LOCKED_CRATE = "angelus-desktop"

JSON_WHITESPACE = " \t\r\n"
JSON_STRING = re.compile(r'"(?:[^"\\]|\\.)*"')


def npm_version(pepit: str) -> str:
    """Convert the supported PEP 440 release-candidate form to SemVer.

    Args:
        pepit: Angelus PEP 440 version value.

    Returns:
        Equivalent SemVer string used by npm, Cargo, and Tauri.

    Raises:
        ValueError: If the version uses a prerelease form this checker cannot
            map without ambiguity.
    """
    match = re.fullmatch(r"(\d+\.\d+\.\d+)(?:rc(\d+))?", pepit)
    if match is None:
        raise ValueError(f"unsupported Angelus version: {pepit}")
    return match.group(1) if match.group(2) is None else f"{match.group(1)}-rc.{match.group(2)}"


def expected_versions() -> tuple[str, str]:
    """Return the SemVer and four-part Windows Installer versions Angelus expects.

    Returns:
        Pair of ``(semver, wix)`` strings derived from the runtime version.
    """
    from angelus._version import ANGELUS_VERSION

    return npm_version(ANGELUS_VERSION), ANGELUS_VERSION.split("rc", 1)[0] + ".0"


def _json_value(relative: Path, keys: Sequence[str]) -> str | None:
    """Read a nested string out of a JSON document under the project root.

    Args:
        relative: Path of the JSON document, relative to the project root.
        keys: Key path to descend through.

    Returns:
        The string held at that key path, or None when any step is absent.
    """
    node: object = json.loads((ROOT / relative).read_text(encoding="utf-8"))
    for key in keys:
        if not isinstance(node, dict):
            return None
        node = node.get(key)
    return node if isinstance(node, str) else None


def _skip_whitespace(text: str, index: int) -> int:
    """Advance an offset past JSON whitespace.

    Args:
        text: Full JSON document.
        index: Offset to start from.

    Returns:
        Offset of the next non-whitespace character.
    """
    while index < len(text) and text[index] in JSON_WHITESPACE:
        index += 1
    return index


def _skip_json_value(text: str, index: int) -> int:
    """Return the offset just past the JSON value starting at ``index``.

    Args:
        text: Full JSON document.
        index: Offset of the value's first character.

    Returns:
        Offset immediately after that value.

    Raises:
        ValueError: If the value is unbalanced or unterminated.
    """
    character = text[index]
    if character == '"':
        return JSON_STRING.match(text, index).end()
    if character in "{[":
        depth = 0
        while index < len(text):
            character = text[index]
            if character == '"':
                index = JSON_STRING.match(text, index).end()
                continue
            if character in "{[":
                depth += 1
            elif character in "}]":
                depth -= 1
                if depth == 0:
                    return index + 1
            index += 1
        raise ValueError("unbalanced JSON value")
    index += 1
    while index < len(text) and text[index] not in ",}]" + JSON_WHITESPACE:
        index += 1
    return index


def _json_value_span(text: str, keys: Sequence[str]) -> tuple[int, int]:
    """Locate a nested JSON value without re-serialising the document.

    Round-tripping through :mod:`json` would reformat the deliberately compact
    arrays these manifests contain (``"icon": ["a", "b"]``), so the value is
    located in the raw text and replaced in place: every other byte survives.

    Args:
        text: Full JSON document.
        keys: Key path to descend through.

    Returns:
        ``(start, end)`` offsets of the raw value.

    Raises:
        LookupError: If any step of the key path is missing or not an object.
    """
    if not keys:
        raise LookupError("a JSON key path is required")
    position = _skip_whitespace(text, 0)
    value_start = value_end = 0
    for key in keys:
        if position >= len(text) or text[position] != "{":
            raise LookupError(f"{key}: parent value is not an object")
        position = _skip_whitespace(text, position + 1)
        while True:
            match = JSON_STRING.match(text, position)
            if match is None:
                raise LookupError(f"{key}: key not found in object")
            name = json.loads(match.group(0))
            cursor = _skip_whitespace(text, match.end())
            if cursor >= len(text) or text[cursor] != ":":
                raise LookupError(f"{key}: expected ':' after key {name!r}")
            value_start = _skip_whitespace(text, cursor + 1)
            value_end = _skip_json_value(text, value_start)
            if name == key:
                break
            cursor = _skip_whitespace(text, value_end)
            if cursor < len(text) and text[cursor] == ",":
                position = _skip_whitespace(text, cursor + 1)
                continue
            raise LookupError(f"{key}: key not found in object")
        position = value_start
    return value_start, value_end


def _write_json_value(relative: Path, keys: Sequence[str], value: str) -> None:
    """Replace one nested JSON string, leaving the rest of the file untouched.

    Args:
        relative: Path of the JSON document, relative to the project root.
        keys: Key path to descend through; intermediate objects must exist.
        value: Replacement string.

    Raises:
        LookupError: If the key path is missing or does not hold a string.
    """
    path = ROOT / relative
    text = path.read_text(encoding="utf-8")
    start, end = _json_value_span(text, keys)
    if text[start] != '"':
        raise LookupError(f"{relative}: {'.'.join(keys)} is not a string")
    path.write_text(text[:start] + json.dumps(value) + text[end:], encoding="utf-8")


def _table_bounds(text: str, header: str, start: int = 0) -> tuple[int, int]:
    """Locate the body of one TOML table.

    Args:
        text: Full TOML document.
        header: Table header exactly as written, including brackets.
        start: Offset to begin searching from.

    Returns:
        ``(body_start, body_end)`` character offsets, or ``(-1, -1)`` when the
        header does not occur again.
    """
    match = re.compile(r"^" + re.escape(header) + r"[ \t]*$", re.MULTILINE).search(text, start)
    if match is None:
        return -1, -1
    following = re.compile(r"^\[", re.MULTILINE).search(text, match.end())
    return match.end(), (following.start() if following else len(text))


def _replace_table_version(text: str, body: tuple[int, int], version: str) -> str:
    """Rewrite the first ``version`` key inside a TOML table body.

    Args:
        text: Full TOML document.
        body: ``(body_start, body_end)`` offsets from :func:`_table_bounds`.
        version: Replacement version string.

    Returns:
        The document with that one key replaced.

    Raises:
        LookupError: If the selected table declares no ``version`` key.
    """
    start, end = body
    if start < 0:
        raise LookupError("selected TOML table does not exist")
    replaced, count = re.subn(
        r'^version\s*=\s*"[^"]*"',
        f'version = "{version}"',
        text[start:end],
        count=1,
        flags=re.MULTILINE,
    )
    if count != 1:
        raise LookupError("selected TOML table declares no version key")
    return text[:start] + replaced + text[end:]


def _cargo_manifest_version() -> str | None:
    """Return the ``[package]`` version declared by ``src-tauri/Cargo.toml``.

    Returns:
        Declared version, or None when the manifest has no package table.
    """
    document = tomllib.loads((ROOT / CARGO_MANIFEST).read_text(encoding="utf-8"))
    return document.get("package", {}).get("version")


def _cargo_lock_version() -> str | None:
    """Return the resolved version of the desktop crate in ``Cargo.lock``.

    Returns:
        Locked version, or None when the crate has no lock entry.
    """
    document = tomllib.loads((ROOT / CARGO_LOCK).read_text(encoding="utf-8"))
    for package in document.get("package", []):
        if package.get("name") == LOCKED_CRATE:
            return package.get("version")
    return None


def _write_cargo_manifest_version(version: str) -> None:
    """Rewrite ``[package] version`` in ``src-tauri/Cargo.toml``.

    Args:
        version: Replacement version string.
    """
    path = ROOT / CARGO_MANIFEST
    text = path.read_text(encoding="utf-8")
    updated = _replace_table_version(text, _table_bounds(text, "[package]"), version)
    path.write_text(updated, encoding="utf-8")


def _write_cargo_lock_version(version: str) -> None:
    """Rewrite the locked version of the desktop crate in ``Cargo.lock``.

    Only the ``angelus-desktop`` entry is touched: every other version in the
    lockfile is resolved by Cargo and must not be rewritten by hand.

    Args:
        version: Replacement version string.

    Raises:
        LookupError: If the lockfile has no ``angelus-desktop`` package entry.
    """
    path = ROOT / CARGO_LOCK
    text = path.read_text(encoding="utf-8")
    position = 0
    while True:
        body = _table_bounds(text, "[[package]]", position)
        if body[0] < 0:
            raise LookupError(f"{CARGO_LOCK} has no {LOCKED_CRATE} package entry")
        entry = text[body[0]:body[1]]
        if re.search(r'^name\s*=\s*"' + re.escape(LOCKED_CRATE) + r'"\s*$', entry, re.MULTILINE):
            path.write_text(_replace_table_version(text, body, version), encoding="utf-8")
            return
        position = body[1]


@dataclass(frozen=True)
class VersionTarget:
    """One manifest slot that must repeat Angelus's public version.

    Attributes:
        label: Human-readable name used in reports.
        expected: Version the slot must hold.
        read: Callable returning the slot's current value.
        write: Callable storing a new value in the slot.
    """

    label: str
    expected: str
    read: Callable[[], str | None]
    write: Callable[[str], None]


def version_targets() -> list[VersionTarget]:
    """Return every manifest slot that has to mirror Angelus's version.

    Returns:
        Targets in report order, covering npm, Tauri, WiX, Cargo, and the
        lockfile entry that Cargo would otherwise regenerate inconsistently.
    """
    semver, wix = expected_versions()
    return [
        VersionTarget(
            label="package.json version",
            expected=semver,
            read=lambda: _json_value(PACKAGE_JSON, ("version",)),
            write=lambda version: _write_json_value(PACKAGE_JSON, ("version",), version),
        ),
        VersionTarget(
            label="tauri.conf.json version",
            expected=semver,
            read=lambda: _json_value(TAURI_CONF, ("version",)),
            write=lambda version: _write_json_value(TAURI_CONF, ("version",), version),
        ),
        VersionTarget(
            label="Tauri WiX version",
            expected=wix,
            read=lambda: _json_value(TAURI_CONF, ("bundle", "windows", "wix", "version")),
            write=lambda version: _write_json_value(
                TAURI_CONF, ("bundle", "windows", "wix", "version"), version
            ),
        ),
        VersionTarget(
            label="Cargo.toml version",
            expected=semver,
            read=_cargo_manifest_version,
            write=_write_cargo_manifest_version,
        ),
        VersionTarget(
            label="Cargo.lock version",
            expected=semver,
            read=_cargo_lock_version,
            write=_write_cargo_lock_version,
        ),
    ]


def check_versions() -> list[str]:
    """Return one mismatch description for every stale version manifest.

    Returns:
        Empty list when all independent package manifests match Angelus.
    """
    pyproject = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    errors: list[str] = []
    if pyproject.get("project", {}).get("dynamic") != ["version"]:
        errors.append("pyproject.toml must read Angelus version dynamically")
    for target in version_targets():
        current = target.read()
        if current != target.expected:
            errors.append(f"{target.label} differs from Angelus version ({current} != {target.expected})")
    return errors


def apply_fixes() -> list[str]:
    """Rewrite every drifting manifest slot.

    Returns:
        Labels of the slots that were rewritten, in report order.
    """
    rewritten: list[str] = []
    for target in version_targets():
        if target.read() != target.expected:
            target.write(target.expected)
            rewritten.append(target.label)
    return rewritten


def main(argv: Sequence[str] | None = None) -> int:
    """Print version drift and return a conventional process status.

    Args:
        argv: Command-line arguments; defaults to ``sys.argv[1:]``.

    Returns:
        Zero when every manifest is aligned, otherwise one. Reporting is the
        default because the desktop manifests keep their own release train
        until that is decided; only ``--fix`` writes anything.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--fix",
        action="store_true",
        help="rewrite drifting manifests (package.json, tauri.conf.json, Cargo.toml, Cargo.lock)",
    )
    arguments = parser.parse_args(argv)
    if arguments.fix:
        rewritten = apply_fixes()
        print("Rewrote: " + ", ".join(rewritten) if rewritten else "Nothing to rewrite.")
    errors = check_versions()
    for error in errors:
        print(error)
    if not errors:
        print("All manifests match Angelus version.")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
