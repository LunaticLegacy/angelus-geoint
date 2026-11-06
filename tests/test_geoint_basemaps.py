import stat
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from angelus.api.geoint_basemaps import router
from angelus.geoint import BasemapStore, NoRedirect


class BasemapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "basemaps.json"
        self.store = BasemapStore(self.path)
        app = FastAPI()
        app.state.basemaps = self.store
        app.include_router(router)
        self.client = TestClient(app)
        self.config = {"name": "Example", "url": "https://tiles.example.com/{z}/{x}/{y}.png", "attribution": "© Example"}

    def test_defaults_and_roundtrip(self):
        self.assertEqual(self.client.get("/api/geoint/basemaps").json()["selected_id"], "osm")
        response = self.client.post("/api/geoint/basemaps", json=self.config)
        self.assertEqual(response.status_code, 200)
        id_ = response.json()["sources"][-1]["id"]
        self.assertEqual(self.client.put("/api/geoint/basemaps/selection", json={"source_id": id_}).status_code, 200)
        restored = BasemapStore(self.path)
        self.assertEqual(restored.snapshot()["selected_id"], id_)
        self.assertTrue(self.path.is_file())
        self.assertIn(id_, self.path.read_text(encoding="utf-8"))
        if sys.platform != "win32":
            # The 0600 mode on POSIX comes from tempfile.mkstemp + os.replace;
            # Windows has no POSIX permission bits to assert here.
            self.assertEqual(stat.S_IMODE(self.path.stat().st_mode), 0o600)
        self.assertEqual(self.client.delete(f"/api/geoint/basemaps/{id_}").json()["selected_id"], "osm")
        self.assertEqual(self.client.delete("/api/geoint/basemaps/osm").status_code, 400)

    def test_key_is_private_and_clear_resets_selection(self):
        key = "a" * 32
        result = self.client.put("/api/geoint/basemaps/tianditu-key", json={"key": key})
        self.assertEqual(result.status_code, 200)
        self.assertNotIn(key, result.text)
        self.assertTrue(result.json()["has_tianditu_key"])
        result = self.client.put("/api/geoint/basemaps/selection", json={"source_id": "tianditu-imagery"})
        self.assertEqual(result.status_code, 200)
        tdt = next(s for s in result.json()["sources"] if s["id"] == "tianditu-imagery")
        self.assertEqual(len(tdt["tiles"]), 2)
        self.assertTrue(all(url.startswith("/api/geoint/basemaps/tianditu/") for url in tdt["tiles"]))
        self.assertEqual(BasemapStore(self.path).tianditu_key(), key)
        self.assertEqual(self.client.put("/api/geoint/basemaps/tianditu-key", json={"key": ""}).json()["selected_id"], "osm")
        self.assertEqual(self.client.put("/api/geoint/basemaps/selection", json={"source_id": "tianditu-vector"}).status_code, 400)

    def test_invalid_configs(self):
        invalid = [
            {"url": "file:///etc/passwd"}, {"url": "javascript:alert(1)"},
            {"url": "http://example.com/{z}/{x}/{y}"},
            {"url": "https://user:password@example.com/{z}/{x}/{y}"},
            {"url": "https://127.0.0.1/{z}/{x}/{y}"},
            {"url": "https://localhost/{z}/{x}/{y}"},
            {"url": "https://tiles.example.com/{z}/{x}/{y}?token=secret"},
            {"url": "https://tiles.example.com/{z}/{x}/{y}/{evil}"},
            {"url": "https://tiles.example.com/{z}/{x}/{y}/{"},
            {"url": "https://tiles.example.com/{z}/{x}"},
            {"url": "https://map.baidu.com/{z}/{x}/{y}"},
            {"projection": "BD09"}, {"projection": "EPSG:4326"},
            {"name": "  "}, {"attribution": ""}, {"min_zoom": 10, "max_zoom": 5},
            {"min_zoom": True}, {"source_id": "osm"}, {"key": "secret"},
        ]
        for override in invalid:
            with self.subTest(override=override):
                self.assertEqual(self.client.post("/api/geoint/basemaps", json={**self.config, **override}).status_code, 422)

    @patch("angelus.geoint.mapping.tianditu.build_opener")
    def test_tile_validation_and_transport(self, opener):
        self.store.set_key("a" * 32)
        for suffix in ("vec/19/0/0", "vec/2/4/0", "vec/2/-1/0", "other/2/0/0", "vec/0/0/0"):
            self.assertEqual(self.client.get("/api/geoint/basemaps/tianditu/" + suffix).status_code, 400)
        opener.assert_not_called()
        upstream = MagicMock()
        upstream.read.return_value = b"\x89PNG\r\n\x1a\nexample"
        opener.return_value.open.return_value.__enter__.return_value = upstream
        result = self.client.get("/api/geoint/basemaps/tianditu/vec/3/2/1")
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.headers["content-type"], "image/png")
        request = opener.return_value.open.call_args.args[0]
        self.assertTrue(request.full_url.startswith("https://t0.tianditu.gov.cn/vec_w/wmts?"))
        self.assertIn("TILECOL=2", request.full_url)
        upstream.read.return_value = b"<xml>bad key</xml>"
        self.assertEqual(self.client.get("/api/geoint/basemaps/tianditu/vec/3/2/1").status_code, 502)
        upstream.read.return_value = b"x" * (2 * 1024 * 1024 + 1)
        self.assertEqual(self.client.get("/api/geoint/basemaps/tianditu/vec/3/2/1").status_code, 502)
        opener.return_value.open.side_effect = OSError("URL includes secret " + "a" * 32)
        result = self.client.get("/api/geoint/basemaps/tianditu/vec/3/2/1")
        self.assertEqual(result.status_code, 502)
        self.assertNotIn("a" * 32, result.text)
        self.assertIsNone(NoRedirect().redirect_request(None, None, 302, None, None, "https://evil.example.com"))

    def test_missing_key_never_fetches(self):
        with patch("angelus.geoint.mapping.tianditu.build_opener") as opener:
            self.assertEqual(self.client.get("/api/geoint/basemaps/tianditu/vec/3/2/1").status_code, 400)
            opener.assert_not_called()

    def test_edit_preserves_identity_and_explicit_crs(self):
        value = self.client.post("/api/geoint/basemaps", json=self.config).json()
        id_ = value["sources"][-1]["id"]
        self.store.select(id_)
        config = {**self.config, "name": "Updated", "geographic_crs": "EPSG:4326", "tile_grid": "XYZ"}
        response = self.client.put(f"/api/geoint/basemaps/{id_}", json=config)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["selected_id"], id_)
        self.assertEqual(response.json()["sources"][-1]["name"], "Updated")
        self.assertEqual(BasemapStore(self.path).snapshot()["sources"][-1]["geographic_crs"], "EPSG:4326")
        self.assertEqual(self.client.put("/api/geoint/basemaps/osm", json=config).status_code, 400)
        for key, bad in [("geographic_crs", "GCJ-02"), ("geographic_crs", "EPSG:4490"), ("projection", "EPSG:4326"), ("tile_grid", "TMS")]:
            with self.subTest(key=key, bad=bad):
                self.assertEqual(self.client.put(f"/api/geoint/basemaps/{id_}", json={**config, key: bad}).status_code, 422)


if __name__ == "__main__":
    unittest.main()
