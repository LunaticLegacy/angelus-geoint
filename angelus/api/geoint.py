"FastAPI adapter for the session-bound GEOINT data catalogue and analysis UI."

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from ..geoint import GeoIntService, PostGISUnavailable
from ..geoint.catalog import CatalogError, DirectoryDialogUnavailable, SourceNotAuthorized
from ..geoint.presentation import MapPresentationStore, PresentationError


router = APIRouter(prefix="/api/geoint", tags=["geoint"])
service = GeoIntService(state_root=Path.cwd() / ".angelus-state" / "geoint")
presentation_store = MapPresentationStore(Path.cwd() / ".angelus-state")


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
            {"id": "evidence", "label": "证据"},
            {"id": "agent", "label": "调查"},
            {"id": "trace", "label": "追踪"},
            {"id": "session", "label": "会话"},
            {"id": "context", "label": "上下文"},
            {"id": "connector", "label": "连接器"},
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
    groups: list[dict[str, Any]] = Field(default_factory=list)
    layers: list[dict[str, Any]] = Field(default_factory=list)
    viewport: dict[str, Any] | None = None

def _catalog_error(exc: Exception) -> HTTPException:
    if isinstance(exc, DirectoryDialogUnavailable): return HTTPException(503, str(exc))
    if isinstance(exc, (CatalogError, SourceNotAuthorized)): return HTTPException(422, str(exc))
    if isinstance(exc, KeyError): return HTTPException(404, "Unknown GEOINT catalog resource")
    return HTTPException(500, str(exc))

@router.get("/sessions/{session_id}/map-presentation")
def get_map_presentation(session_id: str) -> dict[str, Any]:
    try: return presentation_store.get(session_id)
    except PresentationError as exc: raise HTTPException(422, str(exc)) from exc

@router.put("/sessions/{session_id}/map-presentation")
def put_map_presentation(session_id: str, payload: MapPresentationRequest) -> dict[str, Any]:
    try: return presentation_store.put(session_id, payload.model_dump())
    except PresentationError as exc: raise HTTPException(422, str(exc)) from exc


@router.get("/health")
def geoint_health() -> dict[str, Any]:
    """Report PostGIS reachability without exposing credentials."""
    return service.health()


@router.post("/catalog/directory-dialog", status_code=201)
def choose_catalog_directory() -> dict[str, Any]:
    """Open a local native picker; deliberately no arbitrary-path fallback."""
    try: return service._require_catalog().choose_directory()
    except Exception as exc: raise _catalog_error(exc) from exc

@router.post("/catalog/scans", status_code=201)
def scan_catalog_source(payload: ScanRequest) -> dict[str, Any]:
    try: return service._require_catalog().scan(**payload.model_dump())
    except Exception as exc: raise _catalog_error(exc) from exc

@router.get("/catalog/scans/{scan_id}")
def get_catalog_scan(scan_id: str) -> dict[str, Any]:
    try: return service._require_catalog().get_scan(scan_id)
    except Exception as exc: raise _catalog_error(exc) from exc

@router.post("/catalog/assets", status_code=201)
def register_catalog_asset(payload: CatalogAssetRequest) -> dict[str, Any]:
    try: return service._require_catalog().register_asset(**payload.model_dump())
    except Exception as exc: raise _catalog_error(exc) from exc

@router.get("/catalog/assets")
def list_catalog_assets(session_id: str | None = Query(default=None, max_length=80)) -> dict[str, Any]:
    try: return {"assets": service._require_catalog().list_assets(session_id)}
    except Exception as exc: raise _catalog_error(exc) from exc

@router.get("/catalog/assets/{asset_id}")
def get_catalog_asset(asset_id: str) -> dict[str, Any]:
    try: return service._require_catalog().get_asset(asset_id)
    except Exception as exc: raise _catalog_error(exc) from exc

@router.patch("/catalog/assets/{asset_id}")
def patch_catalog_asset(asset_id: str, payload: CatalogAssetPatch) -> dict[str, Any]:
    changes={key:value for key,value in payload.model_dump().items() if value is not None}
    try: return service._require_catalog().patch_asset(asset_id,changes)
    except Exception as exc: raise _catalog_error(exc) from exc

@router.delete("/catalog/assets/{asset_id}", status_code=204)
def unregister_catalog_asset(asset_id: str):
    try: service._require_catalog().unregister(asset_id)
    except Exception as exc: raise _catalog_error(exc) from exc

@router.post("/catalog/assets/{asset_id}/sessions/{session_id}")
def bind_catalog_asset(asset_id: str, session_id: str) -> dict[str, Any]:
    try: return service._require_catalog().bind(asset_id,session_id)
    except Exception as exc: raise _catalog_error(exc) from exc

@router.delete("/catalog/assets/{asset_id}/sessions/{session_id}")
def unbind_catalog_asset(asset_id: str, session_id: str) -> dict[str, Any]:
    try: return service._require_catalog().unbind(asset_id,session_id)
    except Exception as exc: raise _catalog_error(exc) from exc

@router.post("/catalog/derivations", status_code=201)
def submit_derivation(payload: DerivationRequest) -> dict[str, Any]:
    try:
        if service.derivations is None: raise CatalogError("GEOINT derivation service is not configured")
        return service.derivations.submit(**payload.model_dump())
    except Exception as exc: raise _catalog_error(exc) from exc

@router.get("/catalog/derivations/{job_id}")
def get_derivation(job_id: str) -> dict[str, Any]:
    try:
        if service.derivations is None: raise KeyError(job_id)
        return service.derivations.get(job_id)
    except Exception as exc: raise _catalog_error(exc) from exc


@router.post("/bootstrap")
def bootstrap_postgis() -> dict[str, Any]:
    """Create the minimal GEOINT schema in the configured PostGIS database."""
    try:
        return service.bootstrap()
    except PostGISUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@router.get("/analyses")
def list_analyses(limit: int = Query(default=25, ge=1, le=100)) -> dict[str, Any]:
    return {"analyses": service.list_analyses(limit)}


@router.get("/analyses/{analysis_id}")
def get_analysis(analysis_id: str) -> dict[str, Any]:
    try:
        return service.get_analysis(analysis_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail="Unknown GEOINT analysis") from exc


@router.post("/observations", status_code=201)
def add_observation(payload: ObservationRequest) -> dict[str, Any]:
    return service.add_observation(**payload.model_dump())


@router.get("/observations")
def list_observations(limit: int = Query(default=200, ge=1, le=1000)) -> dict[str, Any]:
    return service.list_observations(limit)


@router.post("/spatial/intersection")
def spatial_intersection(payload: IntersectionRequest) -> dict[str, Any]:
    try:
        return service.intersection(payload.left, payload.right)
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


__all__ = ["router", "service"]
