"""Bounded, public-only HTTP(S) downloads for GEOINT managed assets.

This module deliberately does not know about sessions or catalogue records.  It
only materializes a verified response in a caller-owned directory.  The caller
then asks :class:`GeoAssetCatalog` to adopt that file, which keeps network IO,
asset authorization, and persistence as separate concerns.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import ipaddress
import os
from pathlib import Path
import socket
import tempfile
from typing import Callable, Protocol
from urllib.error import HTTPError
from urllib.parse import urljoin, urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


class RemoteDownloadError(ValueError):
    """The requested remote resource is not safe or cannot be materialized."""


class _Opener(Protocol):
    def open(self, request: Request, timeout: float): ...


Resolver = Callable[..., list[tuple]]


class _NoRedirect(HTTPRedirectHandler):
    """Expose redirects to the bounded loop below instead of following them."""

    def redirect_request(self, request, fp, code, msg, headers, newurl):  # type: ignore[no-untyped-def]
        return None


@dataclass(frozen=True)
class DownloadedRemoteAsset:
    """A temporary managed-file candidate, not yet an authorized catalogue asset."""

    path: Path
    requested_url: str
    final_url: str
    sha256: str
    size_bytes: int
    content_type: str


def validate_public_http_url(url: str, *, resolver: Resolver = socket.getaddrinfo) -> None:
    """Validate one concrete request target before opening a connection.

    Every redirect is fed through this same function.  This prevents the
    previous implementation's behaviour of connecting first and only then
    discovering that a redirect had reached a local address.
    """
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise RemoteDownloadError("only public HTTP(S) URLs are allowed")
    if parsed.username is not None or parsed.password is not None:
        raise RemoteDownloadError("URLs with embedded credentials are not allowed")
    try:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
    except ValueError as exc:
        raise RemoteDownloadError("remote dataset URL has an invalid port") from exc
    try:
        literal = ipaddress.ip_address(parsed.hostname)
    except ValueError:
        literal = None
    if literal is not None:
        addresses = {str(literal)}
    else:
        try:
            addresses = {item[4][0] for item in resolver(parsed.hostname, port, type=socket.SOCK_STREAM)}
        except OSError as exc:
            raise RemoteDownloadError("cannot resolve remote dataset host") from exc
    if not addresses:
        raise RemoteDownloadError("remote dataset host did not resolve")
    try:
        if any(not ipaddress.ip_address(address).is_global for address in addresses):
            raise RemoteDownloadError("private, local, or reserved network addresses are not allowed")
    except ValueError as exc:
        raise RemoteDownloadError("remote dataset host returned an invalid address") from exc


def _header(response: object, name: str) -> str:
    headers = getattr(response, "headers", None)
    value = headers.get(name, "") if headers is not None else ""
    return str(value or "")


def _redirect_target(error: HTTPError, current_url: str) -> str | None:
    if error.code not in {301, 302, 303, 307, 308}:
        return None
    location = _header(error, "Location")
    return urljoin(current_url, location) if location else None


def download_public_dataset(
    url: str,
    destination_dir: Path,
    *,
    max_bytes: int = 50 * 1024 * 1024,
    timeout_seconds: float = 30,
    max_redirects: int = 3,
    resolver: Resolver = socket.getaddrinfo,
    opener: _Opener | None = None,
) -> DownloadedRemoteAsset:
    """Download a public HTTP(S) resource with explicit redirect validation.

    The result path is created in ``destination_dir`` so adoption can use an
    atomic rename rather than copying a user-owned source.  Callers must remove
    it if they decide not to register the result.
    """
    if not (1 <= max_bytes <= 1024 * 1024 * 1024):
        raise RemoteDownloadError("remote dataset size limit is invalid")
    if not (1 <= timeout_seconds <= 300):
        raise RemoteDownloadError("remote dataset timeout is invalid")
    if not (0 <= max_redirects <= 8):
        raise RemoteDownloadError("remote dataset redirect limit is invalid")
    destination_dir = destination_dir.resolve()
    destination_dir.mkdir(parents=True, exist_ok=True)
    current_url = url
    request_opener = opener or build_opener(_NoRedirect())

    for redirect_count in range(max_redirects + 1):
        validate_public_http_url(current_url, resolver=resolver)
        request = Request(
            current_url,
            headers={
                "User-Agent": "Angelus-GEOINT/1.0",
                "Accept": "application/geo+json,application/json,image/tiff,application/octet-stream,*/*",
            },
        )
        try:
            response = request_opener.open(request, timeout=timeout_seconds)
        except HTTPError as exc:
            target = _redirect_target(exc, current_url)
            try:
                exc.close()
            except Exception:
                pass
            if target is None:
                raise RemoteDownloadError("remote dataset request failed") from exc
            if redirect_count >= max_redirects:
                raise RemoteDownloadError("remote dataset exceeded redirect limit") from exc
            current_url = target
            continue
        except Exception as exc:
            raise RemoteDownloadError("remote dataset download failed") from exc

        try:
            final_url = str(getattr(response, "url", current_url) or current_url)
            # A custom opener can still surface a final URL. Validate it before
            # reading any bytes, and reject implicit redirects from transports.
            if final_url != current_url:
                validate_public_http_url(final_url, resolver=resolver)
            length = _header(response, "Content-Length")
            if length:
                try:
                    if int(length) > max_bytes:
                        raise RemoteDownloadError("remote dataset exceeds size limit")
                except ValueError as exc:
                    raise RemoteDownloadError("remote dataset has an invalid content length") from exc
            fd, temporary_name = tempfile.mkstemp(prefix=".remote-", suffix=".part", dir=destination_dir)
            target = Path(temporary_name)
            digest = hashlib.sha256()
            total = 0
            try:
                with os.fdopen(fd, "wb") as output:
                    while chunk := response.read(1024 * 1024):
                        total += len(chunk)
                        if total > max_bytes:
                            raise RemoteDownloadError("remote dataset exceeds size limit")
                        digest.update(chunk)
                        output.write(chunk)
                    output.flush()
                    os.fsync(output.fileno())
            except BaseException:
                target.unlink(missing_ok=True)
                raise
            return DownloadedRemoteAsset(
                path=target,
                requested_url=url,
                final_url=final_url,
                sha256=digest.hexdigest(),
                size_bytes=total,
                content_type=_header(response, "Content-Type"),
            )
        finally:
            try:
                response.close()
            except Exception:
                pass

    raise AssertionError("redirect loop exhausted unexpectedly")
