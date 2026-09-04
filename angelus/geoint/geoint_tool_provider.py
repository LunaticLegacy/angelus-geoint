"""Read-only, session-scoped GEOINT tools for Angelus Agents."""
from __future__ import annotations
import json
import hashlib
import ipaddress
from pathlib import Path
import socket
from typing import TYPE_CHECKING, Any
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from llmfetcher import Tool, ToolParameter, ToolSchema
from .catalog import GeoAssetCatalog, CatalogError
from .processing import DerivationService
from .presentation import MapPresentationStore, PresentationError

from ..modules.tool_module import ToolCategory, ToolDefinition, ToolPolicy
from ..modules.tool_module.tool_registry import ToolProviderRegistration
if TYPE_CHECKING:
    from ..core import AngelusCore

def _schema(*p: ToolParameter) -> ToolSchema: return ToolSchema(properties=list(p))

class GeoIntToolProvider:
    def __init__(self, core: "AngelusCore") -> None:
        self.catalog=GeoAssetCatalog(core.state_root / "geoint" / "catalog")
        self.derivations=DerivationService(self.catalog, core.state_root / "geoint" / "derived")
        self.downloads=(core.state_root / "geoint" / "downloads").resolve()
        self.presentation=MapPresentationStore(core.state_root)
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
        if policy.allows("geoint","geoint_fetch_remote_dataset"): tools.append(Tool("geoint_fetch_remote_dataset","Download a public HTTP(S) geospatial dataset into Angelus-owned storage and bind it to this session.",_schema(ToolParameter("url",description="Public HTTP(S) dataset URL"),ToolParameter("kind",description="boundary, land_use, rainfall, raw_imagery, or auxiliary")),lambda **k:self.fetch_remote(session_id,k.get("url"),k.get("kind"))))
        if policy.allows("geoint","geoint_discover_public_sources"): tools.append(Tool("geoint_discover_public_sources","List public geographic data catalogues the Agent can query and fetch from.",_schema(ToolParameter("topic",description="Optional topic such as boundaries, imagery, land_use, or rainfall",required=False,default="")),lambda **k:self.discover_sources(k.get("topic"))))
        if policy.allows("geoint","geoint_describe_map"): tools.append(Tool("geoint_describe_map","Read this Session's declarative map presentation.",_schema(),lambda **k:self.describe_map(session_id)))
        if policy.allows("geoint","geoint_propose_map_presentation"): tools.append(Tool("geoint_propose_map_presentation","Store a bounded map-presentation proposal; no URLs, paths, or executable content.",_schema(ToolParameter("presentation",type="object",description="Map presentation object")),lambda **k:self.propose_map(session_id,k.get("presentation"))))
        return tools
    def _asset(self, session_id:str, asset_id:object)->dict[str,Any]:
        if not isinstance(asset_id,str): raise CatalogError("asset_id must be a string")
        asset=self.catalog.get_asset(asset_id,include_path=False)
        if session_id not in asset.get("sessions",[]): raise CatalogError("asset is not bound to this session")
        return asset
    def list_assets(self,session_id:str)->str: return json.dumps({"assets":self.catalog.list_assets(session_id,include_path=False)},ensure_ascii=False)
    def describe_map(self, session_id: str) -> str: return json.dumps(self.presentation.get(session_id), ensure_ascii=False)
    def propose_map(self, session_id: str, presentation: object) -> str:
        if not isinstance(presentation, dict): raise CatalogError("presentation must be an object")
        self._reject_paths(presentation)
        try: return json.dumps({"proposal": self.presentation.propose(session_id, presentation)}, ensure_ascii=False)
        except PresentationError as exc: raise CatalogError(str(exc)) from exc
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
        return json.dumps({"status":job.get("status"),"result":job.get("result"),"error":job.get("error")},ensure_ascii=False)
    def fetch_remote(self, session_id: str, url: object, kind: object) -> str:
        if not isinstance(url,str) or not isinstance(kind,str): raise CatalogError("url and kind must be strings")
        parsed=urlparse(url)
        if parsed.scheme not in {"http","https"} or not parsed.hostname: raise CatalogError("only public HTTP(S) URLs are allowed")
        try: addresses={item[4][0] for item in socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme=="https" else 80), type=socket.SOCK_STREAM)}
            
        except OSError as exc: raise CatalogError("cannot resolve remote dataset host") from exc
        for address in addresses:
            ip=ipaddress.ip_address(address)
            if not ip.is_global: raise CatalogError("private, local, or reserved network addresses are not allowed")
        request=Request(url,headers={"User-Agent":"Angelus-GEOINT/1.0","Accept":"application/geo+json,application/json,image/tiff,application/octet-stream,*/*"})
        try:
            with urlopen(request,timeout=30) as response:
                final=urlparse(response.url)
                if final.scheme not in {"http","https"}: raise CatalogError("redirected to an unsupported URL")
                if not final.hostname: raise CatalogError("redirected to an invalid URL")
                try: redirected={item[4][0] for item in socket.getaddrinfo(final.hostname, final.port or (443 if final.scheme=="https" else 80), type=socket.SOCK_STREAM)}
                except OSError as exc: raise CatalogError("cannot resolve redirected dataset host") from exc
                if any(not ipaddress.ip_address(address).is_global for address in redirected): raise CatalogError("redirected to a private, local, or reserved address")
                length=response.headers.get("Content-Length")
                if length and int(length)>50*1024*1024: raise CatalogError("remote dataset exceeds 50 MiB limit")
                self.downloads.mkdir(parents=True,exist_ok=True); suffix=Path(final.path).suffix.lower() or ".bin"; name=f"remote_{hashlib.sha256(url.encode()).hexdigest()[:16]}{suffix}"; target=self.downloads/name; digest=hashlib.sha256(); total=0
                with target.open("wb") as output:
                    while chunk:=response.read(1024*1024):
                        total+=len(chunk)
                        if total>50*1024*1024: output.close(); target.unlink(missing_ok=True); raise CatalogError("remote dataset exceeds 50 MiB limit")
                        digest.update(chunk); output.write(chunk)
        except CatalogError: raise
        except Exception as exc: raise CatalogError("remote dataset download failed") from exc
        asset=self.catalog.register_remote_asset(url=url,local_name=name,sha256=digest.hexdigest(),size_bytes=total,kind=kind,session_id=session_id,metadata={"content_type":response.headers.get("Content-Type","")})
        return json.dumps({"asset":asset,"downloaded_bytes":total,"note":"The downloaded copy is Angelus-owned and bound to this session."},ensure_ascii=False)
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
    names=("geoint_list_assets","geoint_describe_asset","geoint_query_assets","geoint_submit_derivation","geoint_get_job","geoint_read_result","geoint_fetch_remote_dataset","geoint_discover_public_sources","geoint_describe_map","geoint_propose_map_presentation")
    titles=("列出会话资产","描述资产","检索资产","提交派生任务","读取任务","读取结果","抓取公开地理数据","发现公开地理数据源","读取地图呈现","提议地图呈现")
    return ToolProviderRegistration("geoint",GeoIntToolProvider(core),(ToolCategory("geoint","GEOINT 数据","读取会话绑定的 GEOINT 资产并提交受限派生任务。"),),tuple(ToolDefinition(n,"geoint",t,"无路径访问的会话 GEOINT 能力。","geoint",frozenset({"coordinator","worker"})) for n,t in zip(names,titles)))
