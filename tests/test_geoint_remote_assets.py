"""Managed remote GEOINT asset and SSRF redirect regression tests."""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
from urllib.error import HTTPError
import unittest

from angelus.geoint import CatalogError, GeoAssetCatalog, SourceNotAuthorized
from angelus.geoint.assets.remote import (
    RemoteDownloadError,
    download_public_dataset,
    validate_public_http_url,
)


def _public_resolver(host: str, port: int, **_: object) -> list[tuple]:
    return [(None, None, None, None, ("8.8.8.8", port))]


def _private_resolver(host: str, port: int, **_: object) -> list[tuple]:
    return [(None, None, None, None, ("127.0.0.1", port))]


class _Response:
    def __init__(self, payload: bytes, url: str) -> None:
        self._body = BytesIO(payload)
        self.url = url
        self.headers = {"Content-Length": str(len(payload)), "Content-Type": "application/geo+json"}

    def read(self, size: int) -> bytes:
        return self._body.read(size)

    def close(self) -> None:
        self._body.close()


class _SuccessOpener:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload
        self.calls: list[str] = []

    def open(self, request, timeout: float):  # type: ignore[no-untyped-def]
        self.calls.append(request.full_url)
        return _Response(self.payload, request.full_url)


class _PrivateRedirectOpener:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def open(self, request, timeout: float):  # type: ignore[no-untyped-def]
        self.calls.append(request.full_url)
        raise HTTPError(
            request.full_url, 302, "Found",
            {"Location": "http://127.0.0.1/metadata"}, None,
        )


class RemoteAssetTests(unittest.TestCase):
    def test_public_url_validation_rejects_private_resolution(self) -> None:
        with self.assertRaises(RemoteDownloadError):
            validate_public_http_url("https://data.example.test/a.geojson", resolver=_private_resolver)

    def test_private_redirect_is_rejected_before_a_second_request(self) -> None:
        with self.subTest("redirect target is never opened"):
            import tempfile
            with tempfile.TemporaryDirectory() as temporary:
                opener = _PrivateRedirectOpener()
                with self.assertRaises(RemoteDownloadError):
                    download_public_dataset(
                        "https://data.example.test/a.geojson", Path(temporary),
                        resolver=_public_resolver, opener=opener,
                    )
                self.assertEqual(opener.calls, ["https://data.example.test/a.geojson"])

    def test_downloaded_asset_uses_managed_locator_without_disclosing_it(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            catalog = GeoAssetCatalog(root / "state" / "catalog")
            payload = b'{"type":"FeatureCollection","features":[]}'
            result = download_public_dataset(
                "https://data.example.test/boundary.geojson", catalog.managed_root,
                resolver=_public_resolver, opener=_SuccessOpener(payload),
            )
            asset = catalog.register_downloaded_remote_asset(
                url=result.final_url, downloaded_path=result.path,
                display_name="boundary.geojson", sha256=result.sha256,
                size_bytes=result.size_bytes, kind="boundary", session_id="session-a",
                metadata={"content_type": result.content_type},
            )
            self.assertNotIn("storage", asset)
            self.assertNotIn("remote_url", asset.get("lineage", {}))
            public, path = catalog.bound_path("session-a", asset["id"])
            self.assertEqual(path.read_bytes(), payload)
            self.assertNotIn("storage", public)
            with self.assertRaises(SourceNotAuthorized):
                catalog.bound_path("session-b", asset["id"])

    def test_managed_registration_rejects_name_traversal(self) -> None:
        import tempfile
        with tempfile.TemporaryDirectory() as temporary:
            catalog = GeoAssetCatalog(Path(temporary) / "state" / "catalog")
            catalog.managed_root.mkdir(parents=True)
            (catalog.managed_root / "remote.geojson").write_text("{}", encoding="utf-8")
            with self.assertRaises(CatalogError):
                catalog.register_remote_asset(
                    url="https://data.example.test/a.geojson", local_name="../remote.geojson",
                    sha256="0" * 64, size_bytes=0, kind="boundary", session_id="session-a",
                )


if __name__ == "__main__":  # pragma: no cover
    unittest.main()
