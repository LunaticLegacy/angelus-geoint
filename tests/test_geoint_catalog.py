"""Security and lifecycle tests for the generalized GEOINT data catalogue."""
from __future__ import annotations

import json

import pytest

from angelus.geoint import GeoAssetCatalog, SourceNotAuthorized


class Picker:
    def __init__(self, path): self.path = path
    def choose_directory(self): return str(self.path)


def test_scan_register_bind_and_unregister_never_modifies_source(tmp_path):
    source = tmp_path / "external"; source.mkdir()
    dataset = source / "boundary.geojson"
    original = json.dumps({"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [108, 34]}, "properties": {"observed_date": "2026-08-01"}}]})
    dataset.write_text(original, encoding="utf-8")
    catalog = GeoAssetCatalog(tmp_path / "state", picker=Picker(source))
    grant = catalog.choose_directory(); scan = catalog.scan(grant["source_id"])
    candidate = scan["candidates"][0]
    asset = catalog.register_asset(scan_id=scan["id"], candidate_id=candidate["id"], kind="boundary")
    catalog.bind(asset["id"], "session-a")
    assert catalog.list_assets("session-a", include_path=False)[0]["id"] == asset["id"]
    catalog.unregister(asset["id"])
    assert dataset.read_text(encoding="utf-8") == original
    assert catalog.list_assets() == []


def test_symlink_escape_is_not_a_scan_candidate(tmp_path):
    root = tmp_path / "root"; root.mkdir()
    outside = tmp_path / "outside.geojson"; outside.write_text("{}", encoding="utf-8")
    (root / "escape.geojson").symlink_to(outside)
    catalog = GeoAssetCatalog(tmp_path / "state", picker=Picker(root))
    scan = catalog.scan(catalog.choose_directory()["source_id"])
    assert not scan["candidates"]
    assert scan["skipped"][0]["reason"] == "symlink escapes authorized root"


def test_unknown_source_cannot_be_scanned(tmp_path):
    with pytest.raises(SourceNotAuthorized):
        GeoAssetCatalog(tmp_path / "state", picker=Picker(tmp_path)).scan("source_missing")


def test_bound_geojson_render_returns_features(tmp_path):
    """Exercise the HTTP adapter, not just catalogue registration."""
    from types import SimpleNamespace
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from angelus.api.geoint import router, _runtime

    payload = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"name": "边界"},
         "geometry": {"type": "Point", "coordinates": [108, 34]}}
    ]}
    path = tmp_path / "boundary.geojson"
    path.write_text(json.dumps(payload), encoding="utf-8")

    def bound_path(session_id, asset_id):
        assert (session_id, asset_id) == ("session-test", "asset-test")
        return {"format": "GeoJSON"}, path

    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[_runtime] = lambda: SimpleNamespace(
        catalog=SimpleNamespace(bound_path=bound_path))
    with TestClient(app) as client:
        response = client.get("/api/geoint/catalog/assets/asset-test/render",
                              params={"session_id": "session-test"})
    assert response.status_code == 200
    assert response.json() == payload
