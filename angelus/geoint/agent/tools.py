"""Session-scoped GEOINT tools with bounded direct map operations."""
from __future__ import annotations
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse
from uuid import uuid4

from llmfetcher import Tool, ToolParameter, ToolSchema
from ..assets import CatalogError, RemoteDownloadError, download_public_dataset
from ..mapping import PresentationError, effective_vector_render, layer_record

from ...modules.tool_module import ToolCategory, ToolDefinition, ToolPolicy
from ...modules.tool_module.tool_registry import ToolProviderRegistration
if TYPE_CHECKING:
    from ...core import AngelusCore

def _schema(*p: ToolParameter) -> ToolSchema: return ToolSchema(properties=list(p))

class GeoIntToolProvider:
    def __init__(self, core: "AngelusCore") -> None:
        self.runtime = core.geoint_runtime
        self.catalog = self.runtime.catalog
        self.derivations = self.runtime.derivations
        self.downloads = self.runtime.downloads
        self.presentation = self.runtime.presentation
        self.evidence = self.runtime.evidence
        self.knowledge = self.runtime.knowledge
    def materialize(self, session: object, policy: ToolPolicy, role: str) -> list[Tool]:
        if role not in {"coordinator","worker"}: return []
        session_id=getattr(getattr(session,"execution",None),"session_id",None)
        if not isinstance(session_id,str): return []
        tools=[]
        if policy.allows("geoint","geoint_list_assets"): tools.append(Tool("geoint_list_assets","List only GEOINT assets bound to this session.",_schema(),lambda **k:self.list_assets(session_id)))
        if policy.allows("geoint","geoint_describe_asset"): tools.append(Tool("geoint_describe_asset","Describe one session-bound GEOINT asset without revealing host paths.",_schema(ToolParameter("asset_id",description="Bound GEOINT asset ID")),lambda **k:self.describe(session_id,k.get("asset_id"))))
        if policy.allows("geoint","geoint_query_assets"): tools.append(Tool("geoint_query_assets","Query session-bound GEOINT assets by kind, tag, time or bounding box.",_schema(ToolParameter("kind",description="Optional asset kind",required=False,default=""),ToolParameter("tag",description="Optional tag",required=False,default=""),ToolParameter("bbox",type="array",description="Optional [minx,miny,maxx,maxy]",required=False,default=[])),lambda **k:self.query(session_id,**k)))
        if policy.allows("geoint","geoint_submit_derivation"): tools.append(Tool("geoint_submit_derivation","Submit a bounded derivation using asset IDs only; never accepts paths.",_schema(ToolParameter("operation",description="aoi_clip, vector_statistics, or landuse_statistics"),ToolParameter("asset_ids",type="array",description="Bound asset IDs"),ToolParameter("parameters",type="object",description="Operation parameters",required=False,default={})),lambda **k:self.submit(session_id,**k)))
        if policy.allows("geoint","geoint_get_job"): tools.append(Tool("geoint_get_job","Read a GEOINT derivation job belonging to this session.",_schema(ToolParameter("job_id",description="Job ID")),lambda **k:self.get_job(session_id,k.get("job_id"))))
        if policy.allows("geoint","geoint_read_result"): tools.append(Tool("geoint_read_result","Read a completed GEOINT result belonging to this session.",_schema(ToolParameter("job_id",description="Job ID")),lambda **k:self.read_result(session_id,k.get("job_id"))))
        if policy.allows("geoint","geoint_record_evidence"): tools.append(Tool("geoint_record_evidence","Record a traceable GEOINT evidence claim using session asset IDs, a completed job ID, and/or curated knowledge IDs; never accepts paths.",_schema(ToolParameter("claim",description="Evidence claim, with limitations where relevant"),ToolParameter("source_asset_ids",type="array",description="Optional session-bound source asset IDs",required=False,default=[]),ToolParameter("derivation_job_id",description="Optional completed job ID in this session",required=False,default=""),ToolParameter("knowledge_ids",type="array",description="Optional curated drought knowledge document IDs",required=False,default=[]),ToolParameter("indicator",description="Optional indicator label",required=False,default=""),ToolParameter("confidence",type="number",description="0 to 1 confidence",required=False,default=0.5),ToolParameter("geometry",type="object",description="Optional GeoJSON Point, Polygon, or MultiPolygon",required=False,default=None)),lambda **k:self.record_evidence(session_id,**k)))
        if policy.allows("geoint","geoint_list_evidence"): tools.append(Tool("geoint_list_evidence","List traceable GEOINT evidence recorded for this session only.",_schema(ToolParameter("limit",type="integer",description="Maximum records",required=False,default=20)),lambda **k:self.list_evidence(session_id,k.get("limit",20))))
        if policy.allows("geoint","geoint_search_drought_knowledge"): tools.append(Tool("geoint_search_drought_knowledge","Search the bundled, curated drought-analysis guidance. It is reference material, not live evidence.",_schema(ToolParameter("query",description="Drought-analysis question or terms"),ToolParameter("limit",type="integer",description="Maximum documents",required=False,default=5)),lambda **k:self.search_knowledge(k.get("query"),k.get("limit",5))))
        if policy.allows("geoint","geoint_read_drought_knowledge"): tools.append(Tool("geoint_read_drought_knowledge","Read one bundled drought-reference document by ID.",_schema(ToolParameter("document_id",description="Knowledge document ID")),lambda **k:self.read_knowledge(k.get("document_id"))))
        if policy.allows("geoint","geoint_fetch_remote_dataset"): tools.append(Tool("geoint_fetch_remote_dataset","Download a public HTTP(S) geospatial dataset into Angelus-owned storage and bind it to this session.",_schema(ToolParameter("url",description="Public HTTP(S) dataset URL"),ToolParameter("kind",description="boundary, land_use, rainfall, raw_imagery, or auxiliary")),lambda **k:self.fetch_remote(session_id,k.get("url"),k.get("kind"))))
        if policy.allows("geoint","geoint_discover_public_sources"): tools.append(Tool("geoint_discover_public_sources","List public geographic data catalogues the Agent can query and fetch from.",_schema(ToolParameter("topic",description="Optional topic such as boundaries, imagery, land_use, or rainfall",required=False,default="")),lambda **k:self.discover_sources(k.get("topic"))))
        if policy.allows("geoint","geoint_describe_map"): tools.append(Tool("geoint_describe_map","Read this Session's declarative map presentation.",_schema(),lambda **k:self.describe_map(session_id)))
        if policy.allows("geoint","geoint_manage_map_layers"): tools.append(Tool("geoint_manage_map_layers","Directly modify this Session's map layers. Add requires a Session-bound asset ID; remove/reorder use current layer IDs; set_vector_style changes only a vector layer's stroke, fill, and fill opacity.",_schema(ToolParameter("operation",description="add, remove, reorder, or set_vector_style"),ToolParameter("asset_id",description="For add: Session-bound GEOINT asset ID",required=False,default=""),ToolParameter("layer_id",description="For remove or set_vector_style: current map layer ID",required=False,default=""),ToolParameter("ordered_layer_ids",type="array",description="For reorder: every current layer ID, highest rendering order first",required=False,default=[]),ToolParameter("title",description="For add: optional display title",required=False,default=""),ToolParameter("group_id",description="For add: optional existing map group ID",required=False,default=""),ToolParameter("stroke_color",description="For set_vector_style: optional #RRGGBB boundary colour",required=False,default=""),ToolParameter("fill_color",description="For set_vector_style: optional #RRGGBB polygon fill colour",required=False,default=""),ToolParameter("fill_opacity",type="number",description="For set_vector_style: optional polygon fill opacity from 0 to 1",required=False,default=None)),lambda **k:self.manage_map_layers(session_id,**k)))
        return tools
    def _asset(self, session_id:str, asset_id:object)->dict[str,Any]:
        if not isinstance(asset_id,str): raise CatalogError("asset_id must be a string")
        asset=self.catalog.get_asset(asset_id,include_path=False)
        if session_id not in asset.get("sessions",[]): raise CatalogError("asset is not bound to this session")
        return asset
    def list_assets(self,session_id:str)->str: return json.dumps({"assets":self.catalog.list_assets(session_id,include_path=False)},ensure_ascii=False)
    def describe_map(self, session_id: str) -> str: return json.dumps(self.presentation.get(session_id), ensure_ascii=False)
    def manage_map_layers(self, session_id: str, operation: object, asset_id: object = "", layer_id: object = "", ordered_layer_ids: object = None, title: object = "", group_id: object = "", stroke_color: object = "", fill_color: object = "", fill_opacity: object = None, **_: object) -> str:
        """Directly apply one bounded Agent map-layer operation, never a path edit.

        This is intentionally narrow:
        asset binding, IDs, group membership and full reordering are all
        checked here before Pydantic validates the resulting document.
        """
        if operation not in {"add", "remove", "reorder", "set_vector_style"}:
            raise CatalogError("operation must be add, remove, reorder, or set_vector_style")
        document = self.presentation.get(session_id)
        effective = document["effective"]
        proposal = {
            "viewport": effective["viewport"],
            "groups": effective["groups"],
            "layers": [{**layer, "source": {}} for layer in effective["layers"]],
            "removed_layer_ids": list(document["agent_proposal"].get("removed_layer_ids", [])),
        }
        if operation == "add":
            asset = self._asset(session_id, asset_id)
            if not isinstance(group_id, str):
                raise CatalogError("group_id must be a string")
            resolved_group = group_id or None
            known_groups = {group["id"] for group in proposal["groups"]}
            if resolved_group is not None and resolved_group not in known_groups:
                raise CatalogError("group_id is not part of the current map")
            if any(layer["asset_id"] == asset["id"] for layer in proposal["layers"]):
                raise CatalogError("asset is already present in the current map")
            user_removed = set(document["user_overrides"].get("removed_layer_ids", []))
            agent_removed = set(document["agent_proposal"].get("removed_layer_ids", []))
            removed_asset_ids = {
                layer["asset_id"]
                for layer in [*document["user_overrides"].get("layers", []), *document["agent_proposal"].get("layers", [])]
                if layer.get("id") in (user_removed | agent_removed)
            }
            if asset["id"] in removed_asset_ids:
                raise CatalogError("asset has an explicitly removed map layer; respect the current session map decision")
            if not isinstance(title, str) or len(title) > 160:
                raise CatalogError("title must be a string of at most 160 characters")
            layer_id = f"layer_agent_{uuid4().hex}"
            try:
                proposal["layers"].append(layer_record(asset, layer_id=layer_id, title=title, group_id=resolved_group, z_index=max((layer["z_index"] for layer in proposal["layers"]), default=0) + 1))
            except ValueError as exc:
                raise CatalogError(str(exc)) from exc
        elif operation == "remove":
            if not isinstance(layer_id, str) or not layer_id:
                raise CatalogError("layer_id is required for remove")
            if not any(layer["id"] == layer_id for layer in proposal["layers"]):
                raise CatalogError("layer_id is not part of the current map")
            proposal["layers"] = [layer for layer in proposal["layers"] if layer["id"] != layer_id]
            proposal["removed_layer_ids"] = list(dict.fromkeys([*proposal["removed_layer_ids"], layer_id]))
        elif operation == "reorder":
            if not isinstance(ordered_layer_ids, list) or not all(isinstance(item, str) for item in ordered_layer_ids):
                raise CatalogError("ordered_layer_ids must be an array of layer IDs")
            current_ids = [layer["id"] for layer in proposal["layers"]]
            if len(ordered_layer_ids) != len(current_ids) or set(ordered_layer_ids) != set(current_ids):
                raise CatalogError("ordered_layer_ids must contain every current layer ID exactly once")
            z_indices = {identifier: len(ordered_layer_ids) - index for index, identifier in enumerate(ordered_layer_ids)}
            proposal["layers"] = [{**layer, "z_index": z_indices[layer["id"]]} for layer in proposal["layers"]]
        else:
            if not isinstance(layer_id, str) or not layer_id:
                raise CatalogError("layer_id is required for set_vector_style")
            index = next((index for index, layer in enumerate(proposal["layers"]) if layer["id"] == layer_id), None)
            if index is None:
                raise CatalogError("layer_id is not part of the current map")
            layer = proposal["layers"][index]
            if self._asset(session_id, layer["asset_id"]).get("format") != "GeoJSON":
                raise CatalogError("set_vector_style is supported only for GeoJSON vector layers")
            render = effective_vector_render(layer.get("render"))
            for field, value in (("stroke_color", stroke_color), ("fill_color", fill_color)):
                if value == "":
                    continue
                if not isinstance(value, str):
                    raise CatalogError(f"{field} must be a #RRGGBB string")
                render[field] = value
            if fill_opacity is not None:
                if isinstance(fill_opacity, bool) or not isinstance(fill_opacity, (int, float)):
                    raise CatalogError("fill_opacity must be a number between 0 and 1")
                render["fill_opacity"] = fill_opacity
            proposal["layers"][index] = {**layer, "render": render}
        try:
            result = self.presentation.put(session_id, proposal)
        except PresentationError as exc:
            raise CatalogError(str(exc)) from exc
        return json.dumps({"operation": operation, "map_presentation": result["user_overrides"], "effective_layers": [{key: layer[key] for key in ("id", "asset_id", "title", "z_index", "visible", "render")} for layer in result["effective"]["layers"]], "conflicts": result["conflicts"], "note": "This directly changed the current session map; source assets were not deleted."}, ensure_ascii=False)
    def describe(self,session_id:str,asset_id:object)->str: return json.dumps(self._asset(session_id,asset_id),ensure_ascii=False)
    def query(self,session_id:str,kind:object="",tag:object="",bbox:object=None,**_:object)->str:
        items=self.catalog.list_assets(session_id,include_path=False)
        if isinstance(kind,str) and kind: items=[a for a in items if a.get("kind")==kind]
        if isinstance(tag,str) and tag: items=[a for a in items if tag in a.get("tags",[])]
        if bbox:
            if not isinstance(bbox,list) or len(bbox)!=4: raise CatalogError("bbox must contain four numbers")
            items=[a for a in items if self._intersects(a.get("metadata",{}).get("bbox"),bbox)]
        return json.dumps({"assets":items},ensure_ascii=False)
    @staticmethod
    def _intersects(left:object,right:list[object])->bool:
        if not isinstance(left,list) or len(left)!=4: return False
        try: a,b,c,d=map(float,left); w,s,e,n=map(float,right); return a<=e and c>=w and b<=n and d>=s
        except (TypeError,ValueError): return False
    def submit(self,session_id:str,operation:object,asset_ids:object,parameters:object=None,**_:object)->str:
        if not isinstance(operation,str) or not isinstance(asset_ids,list) or not all(isinstance(x,str) for x in asset_ids) or not isinstance(parameters,dict): raise CatalogError("invalid derivation arguments")
        self._reject_paths(parameters)
        return json.dumps(self.derivations.submit(session_id=session_id,operation=operation,asset_ids=asset_ids,parameters=parameters),ensure_ascii=False)
    @staticmethod
    def _reject_paths(value: object, key: str = "") -> None:
        """Keep the Agent contract ID-and-parameter based, never path based."""
        if "path" in key.lower() or "directory" in key.lower():
            raise CatalogError("host paths and directories are not accepted")
        if isinstance(value, str) and (value.startswith("/") or value.startswith("~")):
            raise CatalogError("host paths and directories are not accepted")
        if isinstance(value, dict):
            for child_key, child in value.items():
                if not isinstance(child_key,str): raise CatalogError("invalid parameter key")
                GeoIntToolProvider._reject_paths(child,child_key)
        elif isinstance(value,list):
            for child in value: GeoIntToolProvider._reject_paths(child,key)
    def get_job(self,session_id:str,job_id:object)->str:
        if not isinstance(job_id,str): raise CatalogError("job_id must be a string")
        job=self.derivations.get(job_id)
        if job.get("session_id")!=session_id: raise CatalogError("job is not owned by this session")
        return json.dumps({k:v for k,v in job.items() if k!="result"},ensure_ascii=False)
    def read_result(self,session_id:str,job_id:object)->str:
        if not isinstance(job_id,str): raise CatalogError("job_id must be a string")
        job=self.derivations.get(job_id)
        if job.get("session_id")!=session_id: raise CatalogError("job is not owned by this session")
        evidence = self.evidence.record_derivation(session_id, job) if job.get("status") == "complete" else None
        return json.dumps({"status":job.get("status"),"result":job.get("result"),"error":job.get("error"),"evidence":evidence},ensure_ascii=False)
    def record_evidence(self, session_id: str, claim: object, source_asset_ids: object = None, derivation_job_id: object = "", knowledge_ids: object = None, indicator: object = "", confidence: object = 0.5, geometry: object = None, **_: object) -> str:
        asset_ids = [] if source_asset_ids is None else source_asset_ids
        if not isinstance(asset_ids, list): raise CatalogError("source_asset_ids must be an array")
        for asset_id in asset_ids: self._asset(session_id, asset_id)
        job_id = derivation_job_id or None
        if job_id is not None:
            if not isinstance(job_id, str): raise CatalogError("derivation_job_id must be a string")
            try: job = self.derivations.get(job_id)
            except KeyError as exc: raise CatalogError("unknown derivation job") from exc
            if job.get("session_id") != session_id or job.get("status") != "complete": raise CatalogError("derivation job must be completed and owned by this session")
        refs = [] if knowledge_ids is None else knowledge_ids
        if not isinstance(refs, list) or not all(isinstance(item, str) for item in refs) or not self.knowledge.exists_many(refs): raise CatalogError("knowledge_ids contain an unknown document")
        try:
            record = self.evidence.record_claim(session_id=session_id, claim=claim, source_asset_ids=asset_ids, derivation_job_id=job_id, knowledge_ids=refs, indicator=indicator or None, confidence=confidence, geometry=geometry)
        except ValueError as exc: raise CatalogError(str(exc)) from exc
        return json.dumps({"evidence": record, "note": "Recorded as session-scoped, traceable evidence; this does not itself prove causality."}, ensure_ascii=False)
    def list_evidence(self, session_id: str, limit: object = 20) -> str:
        try: return json.dumps({"records": self.evidence.list(session_id, int(limit)), "summary": self.evidence.summary(session_id)}, ensure_ascii=False)
        except (TypeError, ValueError) as exc: raise CatalogError("limit must be an integer") from exc
    def search_knowledge(self, query: object, limit: object = 5) -> str:
        try: return json.dumps({"documents": self.knowledge.search(query, int(limit)), "note": "Curated operational reference material; cite it alongside actual session evidence."}, ensure_ascii=False)
        except (TypeError, ValueError, KeyError) as exc: raise CatalogError(str(exc)) from exc
    def read_knowledge(self, document_id: object) -> str:
        try: return json.dumps(self.knowledge.read(document_id), ensure_ascii=False)
        except KeyError as exc: raise CatalogError("unknown drought knowledge document") from exc
    def fetch_remote(self, session_id: str, url: object, kind: object) -> str:
        if not isinstance(url,str) or not isinstance(kind,str): raise CatalogError("url and kind must be strings")
        try:
            downloaded = download_public_dataset(url, self.catalog.managed_root)
            display_name = Path(urlparse(downloaded.final_url).path).name or "remote-dataset"
            asset = self.catalog.register_downloaded_remote_asset(
                url=downloaded.final_url, downloaded_path=downloaded.path,
                display_name=display_name, sha256=downloaded.sha256,
                size_bytes=downloaded.size_bytes, kind=kind, session_id=session_id,
                metadata={"content_type": downloaded.content_type},
            )
        except (RemoteDownloadError, CatalogError) as exc:
            raise CatalogError(str(exc)) from None
        return json.dumps({"asset":asset,"downloaded_bytes":downloaded.size_bytes,"note":"The downloaded copy is Angelus-owned and bound to this session."},ensure_ascii=False)
    @staticmethod
    def discover_sources(topic: object = "") -> str:
        if not isinstance(topic,str): raise CatalogError("topic must be a string")
        sources=[
            {"name":"OpenStreetMap Overpass","topics":["boundaries","land_use","features"],"url":"https://overpass-api.de/api/interpreter","notes":"Use an Overpass query bounded by the AOI."},
            {"name":"Microsoft Planetary Computer STAC","topics":["imagery","land_use","raster"],"url":"https://planetarycomputer.microsoft.com/api/stac/v1","notes":"Query STAC collections and fetch returned public assets."},
            {"name":"Copernicus Data Space STAC","topics":["imagery","raster"],"url":"https://catalogue.dataspace.copernicus.eu/stac","notes":"Some collections may require an account; do not send credentials through GEOINT tools."},
        ]
        needle=topic.lower().strip(); selected=[item for item in sources if not needle or needle in " ".join(item["topics"])]
        return json.dumps({"sources":selected,"safety":"Only fetch public URLs. Private/local addresses, redirects to them, and payloads over 50 MiB are rejected."},ensure_ascii=False)

def geoint_tool_registration(core: "AngelusCore") -> ToolProviderRegistration:
    names=("geoint_list_assets","geoint_describe_asset","geoint_query_assets","geoint_submit_derivation","geoint_get_job","geoint_read_result","geoint_record_evidence","geoint_list_evidence","geoint_search_drought_knowledge","geoint_read_drought_knowledge","geoint_fetch_remote_dataset","geoint_discover_public_sources","geoint_describe_map","geoint_manage_map_layers")
    titles=("列出会话资产","描述资产","检索资产","提交派生任务","读取任务","读取结果","记录证据","列出证据","检索干旱知识","读取干旱知识","抓取公开地理数据","发现公开地理数据源","读取地图呈现","直接管理地图图层")
    return ToolProviderRegistration("geoint",GeoIntToolProvider(core),(ToolCategory("geoint","GEOINT 数据","读取会话绑定的 GEOINT 资产并提交受限派生任务。"),),tuple(ToolDefinition(n,"geoint",t,"无路径访问的会话 GEOINT 能力。","geoint",frozenset({"coordinator","worker"})) for n,t in zip(names,titles)))
