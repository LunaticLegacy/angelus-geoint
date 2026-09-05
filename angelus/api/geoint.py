"FastAPI adapter for the session-bound GEOINT data catalogue and analysis UI."

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from ..geoint import PostGISUnavailable
from ..geoint.catalog import CatalogError, DirectoryDialogUnavailable, SourceNotAuthorized
from ..geoint.presentation import PresentationError
from ..geoint.representation import map_representation
from ..geoint.raster_style import effective_raster_render
from ..geoint.runtime import GeoIntRuntime


router = APIRouter(prefix="/api/geoint", tags=["geoint"])


def _runtime(request: Request) -> GeoIntRuntime:
    """Resolve the GEOINT bounded context owned by this Angelus host."""
    core = getattr(request.app.state, "angelus_core", None)
    runtime = getattr(core, "geoint_runtime", None)
    if not isinstance(runtime, GeoIntRuntime):
        raise RuntimeError("Angelus GEOINT runtime is not configured")
    return runtime


@router.get("/ui")
def geoint_ui() -> dict[str, Any]:
    """Return the GEOINT workbench's server-owned action catalogue.

    The browser deliberately does not carry a hard-coded button inventory.
    It renders only these declared actions and resolves their input from the
    current GEOINT workspace.  ``client`` actions are bounded map operations;
    ``request`` actions are backed by a documented HTTP interface.
    """
    return {
        "title": "GEOINT 数据分析",
        "actions": [
            {"id": "workspace.refresh", "label": "刷新工作区", "group": "header", "kind": "client", "style": "secondary"},
            {"id": "analysis.derive", "label": "运行空间分析", "hint": "已绑定资产 · AOI", "group": "analysis", "kind": "request", "method": "POST", "href": "/api/geoint/catalog/derivations", "style": "primary"},
            {"id": "catalog.choose_directory", "label": "选择数据目录", "hint": "授权只读扫描", "group": "asset", "kind": "request", "method": "POST", "href": "/api/geoint/catalog/directory-dialog", "style": "secondary"},
            {"id": "aoi.draw", "label": "绘制 AOI", "group": "aoi", "kind": "client", "style": "secondary"},
            {"id": "aoi.viewport", "label": "视口设为 AOI", "group": "aoi", "kind": "client", "style": "secondary"},
            {"id": "aoi.clear", "label": "清除 AOI", "group": "aoi", "kind": "client", "style": "danger"},
            {"id": "map.fit_aoi", "label": "定位 AOI", "group": "map", "kind": "client", "style": "secondary"},
            {"id": "agent.run", "label": "发起证据调查", "group": "agent", "kind": "request", "method": "POST", "href": "/api/runs", "style": "primary"},
            {"id": "agent.stop", "label": "停止调查", "group": "agent", "kind": "request", "method": "POST", "href": "/api/runs/{session_id}/stop", "style": "danger"},
            {"id": "trace.clear", "label": "清空追踪", "group": "trace", "kind": "client", "style": "secondary"},
            {"id": "session.create", "label": "创建会话", "group": "session", "kind": "request", "method": "POST", "href": "/api/sessions", "style": "primary"},
            {"id": "session.delete", "label": "删除会话", "group": "session", "kind": "request", "method": "DELETE", "href": "/api/sessions/{session_id}", "style": "danger"},
            {"id": "session.profile.load", "label": "读取运行档案", "group": "session", "kind": "client", "style": "secondary"},
            {"id": "session.profile.save", "label": "保存运行档案", "group": "session", "kind": "request", "method": "PUT", "href": "/api/sessions/{session_id}/run-profile", "style": "secondary"},
            {"id": "context.refresh", "label": "读取上下文", "group": "context", "kind": "client", "style": "secondary"},
            {"id": "context.export", "label": "导出上下文包", "group": "context", "kind": "request", "method": "GET", "href": "/api/sessions/{session_id}/agents/{agent}/context/export", "style": "secondary"},
            {"id": "context.import", "label": "导入上下文包", "group": "context", "kind": "request", "method": "POST", "href": "/api/sessions/{session_id}/agents/{agent}/context/import", "style": "primary"},
            {"id": "connector.refresh", "label": "刷新连接器", "group": "connector", "kind": "client", "style": "secondary"},
            {"id": "connector.create", "label": "保存并绑定会话", "group": "connector", "kind": "request", "method": "POST", "href": "/api/connectors", "style": "primary"},
            {"id": "connector.bind", "label": "绑定已有连接器", "group": "connector", "kind": "request", "method": "PUT", "href": "/api/sessions/{session_id}/run-profile", "style": "secondary"},
        ],
        "tabs": [
            {"id": "layers", "label": "图层"},
            {"id": "evidence", "label": "证据"},
            {"id": "agent", "label": "调查"},
            {"id": "trace", "label": "追踪"},
            {"id": "session", "label": "会话"},
            {"id": "context", "label": "上下文"},
            {"id": "connector", "label": "连接器"},
            {"id": "basemap", "label": "底图与定位"},
        ],
        "sources": {
            "health": "/api/geoint/health",
            "sessions": "/api/sessions",
            "observations": "/api/geoint/observations?limit=200",
            "connectors": "/api/connectors",
            "providers": "/api/providers",
            "catalog_assets": "/api/geoint/catalog/assets",
        },
    }


class ObservationRequest(BaseModel):
    source: str = Field(min_length=1, max_length=200)
    indicator: str = Field(min_length=1, max_length=200)
    geometry: dict[str, Any] | None = None
    value: float | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    session_id: str | None = Field(default=None, max_length=80)
    analysis_id: str | None = None
    properties: dict[str, Any] = Field(default_factory=dict)


class IntersectionRequest(BaseModel):
    left: dict[str, Any]
    right: dict[str, Any]


class ScanRequest(BaseModel):
    source_id: str = Field(min_length=1, max_length=80)
    max_files: int = Field(default=5000, ge=1, le=20000)
    max_depth: int = Field(default=12, ge=0, le=32)
    max_file_bytes: int = Field(default=4 * 1024 ** 3, ge=1, le=16 * 1024 ** 3)
    timeout_seconds: float = Field(default=30, ge=1, le=300)

class CatalogAssetRequest(BaseModel):
    scan_id: str = Field(min_length=1, max_length=80)
    candidate_id: str = Field(min_length=1, max_length=80)
    kind: str
    name: str | None = Field(default=None, max_length=160)
    metadata: dict[str, Any] = Field(default_factory=dict)
    category_schema: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list, max_length=40)

class CatalogAssetPatch(BaseModel):
    name: str | None = Field(default=None, max_length=160)
    metadata: dict[str, Any] | None = None
    category_schema: dict[str, Any] | None = None
    tags: list[str] | None = None

class DerivationRequest(BaseModel):
    session_id: str = Field(min_length=1, max_length=80)
    operation: str
    asset_ids: list[str] = Field(min_length=1, max_length=20)
    parameters: dict[str, Any] = Field(default_factory=dict)

class MapPresentationRequest(BaseModel):
    """The store performs strict nested validation; this preserves 422 errors."""
    model_config = {"extra": "allow"}

class ImportCreateRequest(BaseModel):
    files: list[dict[str, Any]]
    client_request_id: str | None = Field(default=None, max_length=100)

class ImportRevisionRequest(BaseModel):
    expected_revision: int = Field(ge=1)

class ImportCommitRequest(ImportRevisionRequest):
    datasets: list[dict[str, Any]]
    add_to_map: bool = True

def _catalog_error(exc: Exception) -> HTTPException:
    if isinstance(exc, DirectoryDialogUnavailable): return HTTPException(503, str(exc))
    if isinstance(exc, (CatalogError, SourceNotAuthorized)): return HTTPException(422, str(exc))
    if isinstance(exc, KeyError): return HTTPException(404, "Unknown GEOINT catalog resource")
    return HTTPException(500, str(exc))

def _presentation(session_id: str, runtime: GeoIntRuntime) -> dict[str, Any]:
    document = runtime.presentation.get(session_id)
    # ``source`` is a read-only server projection; no persisted client value is trusted.
    for layer in document["effective"]["layers"]:
        # Resolving the path also upgrades legacy GeoTIFF records to their
        # managed EPSG:3857 COG display derivative before we publish metadata.
        asset, _ = runtime.catalog.bound_path(session_id, layer["asset_id"])
        layer["source"] = map_representation(asset, asset_id=layer["asset_id"])
        if asset.get("format") == "GeoTIFF":
            layer["render"] = effective_raster_render(layer.get("render"), asset.get("metadata"))
    return document

def _imports(runtime: GeoIntRuntime):
    if runtime.imports is None:
        raise HTTPException(503, "GEOINT import service is not configured")
    return runtime.imports

def _import_error(exc: Exception) -> HTTPException:
    from ..geoint.imports import ImportError
    if isinstance(exc, ImportError):
        message = str(exc)
        return HTTPException(409 if "revision conflict" in message or "cannot" in message or "must be" in message else 422, message)
    return HTTPException(500, "GEOINT import failed")

@router.get("/sessions/{session_id}/imports/capabilities")
def import_capabilities(session_id: str, runtime: GeoIntRuntime = Depends(_runtime)) -> dict[str, Any]:
    try: return _imports(runtime).capabilities(session_id)
    except Exception as exc: raise _import_error(exc) from exc

@router.get("/sessions/{session_id}/imports")
def list_imports(session_id: str, runtime: GeoIntRuntime = Depends(_runtime)) -> dict[str, Any]:
    try: return {"imports": _imports(runtime).list(session_id)}
    except Exception as exc: raise _import_error(exc) from exc

@router.post("/sessions/{session_id}/imports", status_code=201)
def create_import(session_id: str, payload: ImportCreateRequest, runtime: GeoIntRuntime = Depends(_runtime)) -> dict[str, Any]:
    try: return _imports(runtime).create(session_id, payload.files, payload.client_request_id)
    except Exception as exc: raise _import_error(exc) from exc

@router.get("/sessions/{session_id}/imports/{import_id}")
def get_import(session_id: str, import_id: str, runtime: GeoIntRuntime = Depends(_runtime)) -> dict[str, Any]:
    try: return _imports(runtime).get(session_id, import_id)
    except Exception as exc: raise _import_error(exc) from exc

@router.put("/sessions/{session_id}/imports/{import_id}/files/{file_id}")
async def upload_import_file(session_id: str, import_id: str, file_id: str, request: Request, runtime: GeoIntRuntime = Depends(_runtime)) -> dict[str, Any]:
    if request.headers.get("content-type", "application/octet-stream").split(";", 1)[0].strip().lower() != "application/octet-stream":
        raise HTTPException(415, "upload content type must be application/octet-stream")
    try:
        sink, _ = _imports(runtime).open_upload(session_id, import_id, file_id)
        try:
            async for chunk in request.stream():
                if chunk: sink.write(chunk)
            received, digest = sink.close()
        except Exception:
            sink.abort(); raise
        return _imports(runtime).seal_upload(session_id, import_id, file_id, received, digest)
    except HTTPException: raise
    except Exception as exc: raise _import_error(exc) from exc

@router.post("/sessions/{session_id}/imports/{import_id}/inspect")
def inspect_import(session_id: str, import_id: str, payload: ImportRevisionRequest, runtime: GeoIntRuntime = Depends(_runtime)) -> dict[str, Any]:
    try: return _imports(runtime).inspect(session_id, import_id, payload.expected_revision)
    except Exception as exc: raise _import_error(exc) from exc

@router.post("/sessions/{session_id}/imports/{import_id}/commit")
def commit_import(session_id: str, import_id: str, payload: ImportCommitRequest, runtime: GeoIntRuntime = Depends(_runtime)) -> dict[str, Any]:
    try: return _imports(runtime).commit(session_id, import_id, payload.expected_revision, payload.datasets, payload.add_to_map)
    except Exception as exc: raise _import_error(exc) from exc

@router.get("/sessions/{session_id}/map-presentation")
def get_map_presentation(session_id: str, runtime: GeoIntRuntime = Depends(_runtime)) -> dict[str, Any]:
    try: return _presentation(session_id, runtime)
    except (PresentationError, CatalogError, SourceNotAuthorized) as exc: raise HTTPException(422, str(exc)) from exc

@router.put("/sessions/{session_id}/map-presentation")
def put_map_presentation(session_id: str, payload: MapPresentationRequest, runtime: GeoIntRuntime = Depends(_runtime)) -> dict[str, Any]:
    try:
        runtime.presentation.put(session_id, payload.model_dump(exclude_none=False))
        return _presentation(session_id, runtime)
    except (PresentationError, CatalogError, SourceNotAuthorized) as exc: raise HTTPException(422, str(exc)) from exc


@router.get("/health")
def geoint_health(runtime: GeoIntRuntime = Depends(_runtime)) -> dict[str, Any]:
    """Report PostGIS reachability without exposing credentials."""
    return runtime.service.health()


@router.post("/catalog/directory-dialog", status_code=201)
def choose_catalog_directory(runtime: GeoIntRuntime = Depends(_runtime)) -> dict[str, Any]:
    """Open a local native picker; deliberately no arbitrary-path fallback."""
    try: return runtime.catalog.choose_directory()
    except Exception as exc: raise _catalog_error(exc) from exc

@router.post("/catalog/scans", status_code=201)
def scan_catalog_source(payload: ScanRequest, runtime: GeoIntRuntime = Depends(_runtime)) -> dict[str, Any]:
    try: return runtime.catalog.scan(**payload.model_dump())
    except Exception as exc: raise _catalog_error(exc) from exc

@router.get("/catalog/scans/{scan_id}")
def get_catalog_scan(scan_id: str, runtime: GeoIntRuntime = Depends(_runtime)) -> dict[str, Any]:
    try: return runtime.catalog.get_scan(scan_id)
    except Exception as exc: raise _catalog_error(exc) from exc

@router.post("/catalog/assets", status_code=201)
def register_catalog_asset(payload: CatalogAssetRequest, runtime: GeoIntRuntime = Depends(_runtime)) -> dict[str, Any]:
    try: return runtime.catalog.register_asset(**payload.model_dump())
    except Exception as exc: raise _catalog_error(exc) from exc

@router.get("/catalog/assets")
def list_catalog_assets(session_id: str | None = Query(default=None, max_length=80), runtime: GeoIntRuntime = Depends(_runtime)) -> dict[str, Any]:
    try: return {"assets": runtime.catalog.list_assets(session_id)}
    except Exception as exc: raise _catalog_error(exc) from exc

@router.get("/catalog/assets/{asset_id}")
def get_catalog_asset(asset_id: str, runtime: GeoIntRuntime = Depends(_runtime)) -> dict[str, Any]:
    try: return runtime.catalog.get_asset(asset_id)
    except Exception as exc: raise _catalog_error(exc) from exc

def _bound_asset(runtime: GeoIntRuntime, session_id: str, asset_id: str) -> dict[str, Any]:
    try: return runtime.catalog.bound_asset(session_id, asset_id)
    except Exception as exc: raise _catalog_error(exc) from exc

@router.get("/catalog/assets/{asset_id}/render")
def render_catalog_asset(asset_id: str, session_id: str = Query(min_length=1, max_length=80), runtime: GeoIntRuntime = Depends(_runtime)):
    """Serve only a session-bound asset; host paths never enter the response."""
    try:
        asset, path = runtime.catalog.bound_path(session_id, asset_id)
        fmt = asset.get("format")
        if fmt == "GeoJSON":
            # GeoJSON is already a controlled vector representation.
            return JSONResponse(json.loads(path.read_text(encoding="utf-8")))
        if fmt == "GeoTIFF":
            return FileResponse(path, media_type="image/tiff", headers={"Accept-Ranges": "bytes", "Cache-Control": "private, max-age=60"})
        raise CatalogError("asset format is not directly renderable")
    except Exception as exc: raise _catalog_error(exc) from exc

@router.get("/catalog/assets/{asset_id}/tiles/{z}/{x}/{y}")
def catalog_asset_tile(asset_id: str, z: int, x: int, y: int, session_id: str = Query(min_length=1, max_length=80), runtime: GeoIntRuntime = Depends(_runtime)):
    # The authorization check is intentionally before capability negotiation.
    _bound_asset(runtime, session_id, asset_id)
    if min(z, x, y) < 0: raise HTTPException(422, "invalid tile coordinate")
    raise HTTPException(501, "XYZ tile generation is not configured for this asset")

@router.get("/catalog/assets/{asset_id}/attributes")
def catalog_asset_attributes(asset_id: str, session_id: str = Query(min_length=1, max_length=80), offset: int = Query(0, ge=0), limit: int = Query(100, ge=1, le=500), runtime: GeoIntRuntime = Depends(_runtime)) -> dict[str, Any]:
    try:
        asset, path = runtime.catalog.bound_path(session_id, asset_id)
        if asset.get("format") != "GeoJSON": raise CatalogError("attributes are available only for vector assets")
        data = json.loads(path.read_text(encoding="utf-8")); features = data.get("features", [])
        if not isinstance(features, list): raise CatalogError("invalid GeoJSON feature collection")
        fields = asset.get("metadata", {}).get("fields", [])
        rows = [{"id": offset + n, "properties": item.get("properties", {})} for n, item in enumerate(features[offset:offset + limit]) if isinstance(item, dict)]
        return {"fields": fields, "offset": offset, "limit": limit, "total": len(features), "rows": rows}
    except Exception as exc: raise _catalog_error(exc) from exc

@router.get("/catalog/assets/{asset_id}/identify")
def catalog_asset_identify(asset_id: str, lon: float, lat: float, session_id: str = Query(min_length=1, max_length=80), runtime: GeoIntRuntime = Depends(_runtime)) -> dict[str, Any]:
    try:
        asset, path = runtime.catalog.bound_path(session_id, asset_id)
        if asset.get("format") != "GeoJSON": return {"kind": "raster", "value": None, "message": "raster identify requires a configured raster reader"}
        data = json.loads(path.read_text(encoding="utf-8")); hits=[]
        # Bounding-box selection is deliberately conservative and dependency-free.
        for n, item in enumerate(data.get("features", [])):
            geometry = item.get("geometry", {}) if isinstance(item, dict) else {}
            coordinates = geometry.get("coordinates", []) if isinstance(geometry, dict) else []
            points=[]
            def walk(v):
                if isinstance(v, list) and len(v) >= 2 and isinstance(v[0], (int, float)): points.append(v)
                elif isinstance(v, list):
                    for child in v: walk(child)
            walk(coordinates)
            if points and min(p[0] for p in points) <= lon <= max(p[0] for p in points) and min(p[1] for p in points) <= lat <= max(p[1] for p in points): hits.append({"id": n, "properties": item.get("properties", {})})
        return {"kind": "vector", "features": hits[:20]}
    except Exception as exc: raise _catalog_error(exc) from exc

@router.patch("/catalog/assets/{asset_id}")
def patch_catalog_asset(asset_id: str, payload: CatalogAssetPatch, runtime: GeoIntRuntime = Depends(_runtime)) -> dict[str, Any]:
    changes={key:value for key,value in payload.model_dump().items() if value is not None}
    try: return runtime.catalog.patch_asset(asset_id,changes)
    except Exception as exc: raise _catalog_error(exc) from exc

@router.delete("/catalog/assets/{asset_id}", status_code=204)
def unregister_catalog_asset(asset_id: str, runtime: GeoIntRuntime = Depends(_runtime)):
    try: runtime.catalog.unregister(asset_id)
    except Exception as exc: raise _catalog_error(exc) from exc

@router.post("/catalog/assets/{asset_id}/sessions/{session_id}")
def bind_catalog_asset(asset_id: str, session_id: str, runtime: GeoIntRuntime = Depends(_runtime)) -> dict[str, Any]:
    try: return runtime.catalog.bind(asset_id,session_id)
    except Exception as exc: raise _catalog_error(exc) from exc

@router.delete("/catalog/assets/{asset_id}/sessions/{session_id}")
def unbind_catalog_asset(asset_id: str, session_id: str, runtime: GeoIntRuntime = Depends(_runtime)) -> dict[str, Any]:
    try: return runtime.catalog.unbind(asset_id,session_id)
    except Exception as exc: raise _catalog_error(exc) from exc

@router.post("/catalog/derivations", status_code=201)
def submit_derivation(payload: DerivationRequest, runtime: GeoIntRuntime = Depends(_runtime)) -> dict[str, Any]:
    try:
        return runtime.derivations.submit(**payload.model_dump())
    except Exception as exc: raise _catalog_error(exc) from exc

@router.get("/catalog/derivations/{job_id}")
def get_derivation(job_id: str, runtime: GeoIntRuntime = Depends(_runtime)) -> dict[str, Any]:
    try:
        return runtime.derivations.get(job_id)
    except Exception as exc: raise _catalog_error(exc) from exc


@router.post("/bootstrap")
def bootstrap_postgis(runtime: GeoIntRuntime = Depends(_runtime)) -> dict[str, Any]:
    """Create the minimal GEOINT schema in the configured PostGIS database."""
    try:
        return runtime.service.bootstrap()
    except PostGISUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/analyses")
def list_analyses(limit: int = Query(default=25, ge=1, le=100), runtime: GeoIntRuntime = Depends(_runtime)) -> dict[str, Any]:
    return {"analyses": runtime.service.list_analyses(limit)}


@router.get("/analyses/{analysis_id}")
def get_analysis(analysis_id: str, runtime: GeoIntRuntime = Depends(_runtime)) -> dict[str, Any]:
    try:
        return runtime.service.get_analysis(analysis_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown GEOINT analysis") from exc


@router.post("/observations", status_code=201)
def add_observation(payload: ObservationRequest, runtime: GeoIntRuntime = Depends(_runtime)) -> dict[str, Any]:
    return runtime.service.add_observation(**payload.model_dump())


@router.get("/observations")
def list_observations(limit: int = Query(default=200, ge=1, le=1000), runtime: GeoIntRuntime = Depends(_runtime)) -> dict[str, Any]:
    return runtime.service.list_observations(limit)


@router.post("/spatial/intersection")
def spatial_intersection(payload: IntersectionRequest, runtime: GeoIntRuntime = Depends(_runtime)) -> dict[str, Any]:
    try:
        return runtime.service.intersection(payload.left, payload.right)
    except PostGISUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/layers")
def list_layers() -> dict[str, Any]:
    """Advertise stable map and evidence surfaces."""
    return {
        "layers": [
            {"id": "aoi", "title": "AOI", "kind": "vector", "source": "client"},
            {"id": "observations", "title": "Evidence observations", "kind": "vector", "source": "/api/geoint/observations"},
        ]
    }


__all__ = ["router"]
