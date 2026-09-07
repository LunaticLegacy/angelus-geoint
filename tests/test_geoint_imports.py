"""End-to-end contract tests for session-bound browser data imports."""
from __future__ import annotations

import importlib.util
import json

import pytest

from fastapi import FastAPI
from fastapi.testclient import TestClient

from angelus.api import include_api_routes
from angelus.core import AngelusCore


def _client(tmp_path):
    core = AngelusCore(state_root=tmp_path / "state")
    core.session_service.create("session-import-a", "Import A")
    core.session_service.create("session-import-b", "Import B")
    app = FastAPI(); include_api_routes(app, core)
    return TestClient(app)


def _geojson() -> bytes:
    return json.dumps({"type": "FeatureCollection", "features": [{"type": "Feature", "geometry": {"type": "Point", "coordinates": [108.95, 34.27]}, "properties": {"site": "demo"}}]}, separators=(",", ":")).encode()


def test_browser_import_publishes_a_bound_map_layer_and_is_idempotent(tmp_path):
    client, content = _client(tmp_path), _geojson()
    created = client.post("/api/geoint/sessions/session-import-a/imports", json={"files": [{"name": "points.geojson", "size_bytes": len(content)}], "client_request_id": "client-request-1"})
    assert created.status_code == 201
    duplicate = client.post("/api/geoint/sessions/session-import-a/imports", json={"files": [{"name": "points.geojson", "size_bytes": len(content)}], "client_request_id": "client-request-1"})
    assert duplicate.json()["import_id"] == created.json()["import_id"]
    item = created.json(); file_id = item["files"][0]["file_id"]
    uploaded = client.put(f"/api/geoint/sessions/session-import-a/imports/{item['import_id']}/files/{file_id}", content=content, headers={"content-type": "application/octet-stream"})
    assert uploaded.status_code == 200
    inspected = client.post(f"/api/geoint/sessions/session-import-a/imports/{item['import_id']}/inspect", json={"expected_revision": uploaded.json()["revision"]})
    assert inspected.status_code == 200
    committed = client.post(f"/api/geoint/sessions/session-import-a/imports/{item['import_id']}/commit", json={"expected_revision": inspected.json()["revision"], "datasets": [{"dataset_id": inspected.json()["candidates"][0]["dataset_id"]}], "add_to_map": True})
    assert committed.status_code == 200
    assert committed.json()["status"] == "completed"
    asset_id = committed.json()["assets"][0]["id"]
    document = client.get("/api/geoint/sessions/session-import-a/map-presentation").json()
    assert document["effective"]["layers"][0]["asset_id"] == asset_id
    assert document["effective"]["layers"][0]["source"]["kind"] == "vector"
    replay = client.post(f"/api/geoint/sessions/session-import-a/imports/{item['import_id']}/commit", json={"expected_revision": committed.json()["revision"], "datasets": [], "add_to_map": True})
    assert replay.status_code == 200
    assert len(client.get("/api/geoint/sessions/session-import-a/map-presentation").json()["effective"]["layers"]) == 1


def test_import_rejects_cross_session_file_read_and_unsupported_name(tmp_path):
    client, content = _client(tmp_path), _geojson()
    rejected = client.post("/api/geoint/sessions/session-import-a/imports", json={"files": [{"name": "../../host.txt", "size_bytes": 1}]})
    assert rejected.status_code == 422
    created = client.post("/api/geoint/sessions/session-import-a/imports", json={"files": [{"name": "points.geojson", "size_bytes": len(content)}]}).json()
    response = client.get(f"/api/geoint/sessions/session-import-b/imports/{created['import_id']}")
    assert response.status_code in {404, 422}


@pytest.mark.skipif(importlib.util.find_spec("osgeo") is None, reason="GDAL/OGR is optional")
def test_georeferenced_geotiff_is_inspected_as_a_raster_candidate(tmp_path):
    from osgeo import gdal, osr

    path = tmp_path / "source.tif"
    dataset = gdal.GetDriverByName("GTiff").Create(str(path), 1, 1, 1, gdal.GDT_Byte)
    spatial_ref = osr.SpatialReference(); spatial_ref.ImportFromEPSG(4326)
    dataset.SetProjection(spatial_ref.ExportToWkt()); dataset.SetGeoTransform((108.0, 0.1, 0, 34.1, 0, -0.1)); dataset.GetRasterBand(1).Fill(1); dataset = None
    content, client = path.read_bytes(), _client(tmp_path)
    created = client.post("/api/geoint/sessions/session-import-a/imports", json={"files": [{"name": "source.tif", "size_bytes": len(content)}]}).json()
    uploaded = client.put(f"/api/geoint/sessions/session-import-a/imports/{created['import_id']}/files/{created['files'][0]['file_id']}", content=content, headers={"content-type": "application/octet-stream"}).json()
    inspected = client.post(f"/api/geoint/sessions/session-import-a/imports/{created['import_id']}/inspect", json={"expected_revision": uploaded["revision"]})
    assert inspected.status_code == 200
    candidate = inspected.json()["candidates"][0]
    assert candidate["format"] == "GeoTIFF"
    assert candidate["bands"][0]["index"] == 1


def test_session_deletion_revokes_import_bindings_and_private_manifests(tmp_path):
    client, content = _client(tmp_path), _geojson()
    created = client.post("/api/geoint/sessions/session-import-a/imports", json={"files": [{"name": "points.geojson", "size_bytes": len(content)}]}).json()
    uploaded = client.put(f"/api/geoint/sessions/session-import-a/imports/{created['import_id']}/files/{created['files'][0]['file_id']}", content=content, headers={"content-type": "application/octet-stream"}).json()
    inspected = client.post(f"/api/geoint/sessions/session-import-a/imports/{created['import_id']}/inspect", json={"expected_revision": uploaded["revision"]}).json()
    client.post(f"/api/geoint/sessions/session-import-a/imports/{created['import_id']}/commit", json={"expected_revision": inspected["revision"], "datasets": [{"dataset_id": inspected["candidates"][0]["dataset_id"]}]}).raise_for_status()
    deleted = client.request("DELETE", "/api/sessions/session-import-a", json={"confirmation": "session-import-a"})
    assert deleted.status_code == 200
    assert client.app.state.angelus_core.geoint_runtime.catalog.list_assets("session-import-a") == []
    assert client.get(f"/api/geoint/sessions/session-import-a/imports/{created['import_id']}").status_code in {404, 422}
