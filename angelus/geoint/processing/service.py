from __future__ import annotations
from datetime import datetime, timezone
import json
from pathlib import Path
from typing import Any
import uuid

from ..assets import GeoAssetCatalog, CatalogError
from ..analysis.geometry import geometry_bbox

class DerivationService:
    """Small synchronous job service. It deliberately never writes source files."""
    def __init__(self, catalog: GeoAssetCatalog, derived_root: Path) -> None:
        self.catalog=catalog; self.root=derived_root.resolve(); self._jobs: dict[str,dict[str,Any]]={}
    def submit(self, *, session_id: str, operation: str, asset_ids: list[str], parameters: dict[str,Any]) -> dict[str,Any]:
        if operation not in {"aoi_clip","vector_statistics","landuse_statistics"}: raise CatalogError("不支持的派生任务")
        if not asset_ids or len(asset_ids)>20: raise CatalogError("派生任务必须指定 1–20 个资产")
        assets=[]
        for asset_id in asset_ids:
            asset=self.catalog.get_asset(asset_id,include_path=False)
            if session_id not in asset.get("sessions",[]): raise CatalogError("资产未绑定到当前会话")
            assets.append(asset)
        if operation=="aoi_clip": geometry_bbox(parameters.get("aoi") or {})
        job={"id":f"job_{uuid.uuid4().hex[:16]}","session_id":session_id,"operation":operation,"asset_ids":asset_ids,"parameters":parameters,"status":"running","created_at":datetime.now(timezone.utc).isoformat()}
        self._jobs[job["id"]]=job
        try:
            result=self._run(job,assets); job.update({"status":"complete","result":result,"finished_at":datetime.now(timezone.utc).isoformat()})
        except Exception as exc: job.update({"status":"failed","error":str(exc),"finished_at":datetime.now(timezone.utc).isoformat()})
        return self.get(job["id"])
    def _run(self, job:dict[str,Any], assets:list[dict[str,Any]]) -> dict[str,Any]:
        # A deterministic evidence manifest is useful even where GDAL is absent.
        result={"operation":job["operation"],"assets":[{"id":a["id"],"kind":a["kind"],"format":a["format"],"sha256":a.get("sha256")} for a in assets],"crs":{"vector_exchange":"EPSG:4326","raster_processing":"EPSG:32662","resampling":"nearest" if job["operation"]=="landuse_statistics" else None},"evidence_summary":"Derived from session-bound asset versions only."}
        if job["operation"]=="landuse_statistics":
            schemas=[a.get("category_schema",{}) for a in assets if a["kind"]=="land_use"]
            result["landuse"]={"schemas":schemas,"agricultural_exposure":None}
        path=self.root / f"{job['id']}.json"; path.parent.mkdir(parents=True,exist_ok=True); path.write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding="utf-8")
        result["derived_ref"]=str(path.relative_to(self.root.parent))
        return result
    def get(self, job_id:str)->dict[str,Any]:
        if job_id not in self._jobs: raise KeyError(job_id)
        return dict(self._jobs[job_id])
