"""Local source grants, bounded scans and durable asset registrations."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import tempfile
from time import monotonic
from typing import Any, Protocol
import uuid


class CatalogError(ValueError): pass
class SourceNotAuthorized(CatalogError): pass
class DirectoryDialogUnavailable(CatalogError): pass


class DirectoryPicker(Protocol):
    def choose_directory(self) -> str | None: ...


class SystemDirectoryPicker:
    """The only code path which may turn a user gesture into a source root."""
    def choose_directory(self) -> str | None:
        try:
            import tkinter as tk
            from tkinter import filedialog
            root = tk.Tk(); root.withdraw(); root.attributes("-topmost", True)
            try: return filedialog.askdirectory(parent=root, mustexist=True) or None
            finally: root.destroy()
        except Exception as exc:
            raise DirectoryDialogUnavailable("目录对话框不可用：需要本机可交互图形桌面环境") from exc


def _now() -> str: return datetime.now(timezone.utc).isoformat()
def _write(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".catalog-", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(value, f, ensure_ascii=False, indent=2, sort_keys=True); f.write("\n")
            f.flush(); os.fsync(f.fileno())
        os.replace(tmp, path)
    except BaseException:
        try: os.unlink(tmp)
        except FileNotFoundError: pass
        raise


class GeoAssetCatalog:
    """Persistent metadata directory with capability-style source IDs."""
    extensions = {".geojson": "GeoJSON", ".json": "GeoJSON", ".shp": "Shapefile", ".tif": "GeoTIFF", ".tiff": "GeoTIFF", ".hdr": "ENVI"}

    def __init__(self, state_root: Path, *, picker: DirectoryPicker | None = None) -> None:
        self.root = state_root.resolve(); self.path = self.root / "catalog.json"
        self.picker = picker or SystemDirectoryPicker()

    def _doc(self) -> dict[str, Any]:
        if not self.path.exists(): return {"schema_version": 2, "sources": [], "scans": [], "assets": [], "jobs": []}
        try: d = json.loads(self.path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc: raise CatalogError("GEOINT 数据目录不可读取") from exc
        if not isinstance(d, dict) or d.get("schema_version") != 2: raise CatalogError("GEOINT 数据目录格式不受支持")
        for key in ("sources", "scans", "assets", "jobs"): d.setdefault(key, [])
        return d
    def _save(self, d: dict[str, Any]) -> None: _write(self.path, d)

    def choose_directory(self) -> dict[str, Any]:
        selected = self.picker.choose_directory()
        if not selected: raise CatalogError("未选择目录")
        root = Path(selected).resolve(strict=True)
        if not root.is_dir(): raise CatalogError("所选路径不是目录")
        d = self._doc()
        # Re-selecting a root renews the existing grant instead of widening it.
        item = next((x for x in d["sources"] if x.get("root") == str(root)), None)
        if item is None:
            item = {"id": f"source_{uuid.uuid4().hex[:16]}", "root": str(root), "created_at": _now()}; d["sources"].append(item)
        item["last_selected_at"] = _now(); self._save(d)
        return {"source_id": item["id"], "name": root.name or str(root), "granted_at": item["last_selected_at"]}

    def _source(self, d: dict[str, Any], source_id: str) -> tuple[dict[str, Any], Path]:
        source = next((x for x in d["sources"] if x.get("id") == source_id), None)
        if source is None: raise SourceNotAuthorized("未知或未授权的数据源")
        try: root = Path(str(source["root"])).resolve(strict=True)
        except OSError as exc: raise SourceNotAuthorized("已授权的数据源不再可用") from exc
        if not root.is_dir(): raise SourceNotAuthorized("已授权的数据源不是目录")
        return source, root

    @staticmethod
    def _under(root: Path, entry: Path) -> bool:
        """Reject symlinks whose fully resolved target escapes the grant."""
        try: target = entry.resolve(strict=True); target.relative_to(root)
        except (OSError, ValueError): return False
        return True

    def scan(self, source_id: str, *, max_files: int = 5000, max_depth: int = 12, max_file_bytes: int = 4 * 1024**3, timeout_seconds: float = 30) -> dict[str, Any]:
        if not (1 <= max_files <= 20000 and 0 <= max_depth <= 32 and 1 <= max_file_bytes <= 16 * 1024**3 and 1 <= timeout_seconds <= 300): raise CatalogError("扫描限额不在允许范围内")
        d = self._doc(); _, root = self._source(d, source_id); started = monotonic(); candidates=[]; skipped=[]
        # os.walk does not follow links. Resolve every candidate too, guarding link escapes.
        for base, dirs, files in os.walk(root, followlinks=False):
            current = Path(base); depth = len(current.relative_to(root).parts)
            dirs[:] = [name for name in dirs if self._under(root, current / name) and len((current / name).relative_to(root).parts) <= max_depth]
            if current.suffix.lower() == ".gdb":
                dirs[:] = []
                if self._under(root, current): candidates.append(self._candidate(current, root, "FileGDB"))
                continue
            if depth > max_depth: continue
            for name in files:
                if monotonic() - started > timeout_seconds: break
                p = current / name
                if not self._under(root, p): skipped.append({"name": name, "reason": "symlink escapes authorized root"}); continue
                fmt = self.extensions.get(p.suffix.lower())
                if not fmt: continue
                try: size = p.stat().st_size
                except OSError: continue
                if size > max_file_bytes: skipped.append({"name": p.name, "reason": "file size limit"}); continue
                candidates.append(self._candidate(p, root, fmt))
                if len(candidates) >= max_files: break
            if monotonic() - started > timeout_seconds or len(candidates) >= max_files: break
        scan = {"id": f"scan_{uuid.uuid4().hex[:16]}", "source_id": source_id, "status": "complete", "started_at": _now(), "finished_at": _now(), "limits": {"max_files": max_files, "max_depth": max_depth, "max_file_bytes": max_file_bytes, "timeout_seconds": timeout_seconds}, "candidates": candidates, "skipped": skipped[:100], "truncated": len(candidates) >= max_files or monotonic()-started > timeout_seconds}
        d["scans"] = [scan, *d["scans"]][:100]; self._save(d); return self.public_scan(scan)

    def _candidate(self, path: Path, root: Path, fmt: str) -> dict[str, Any]:
        relative = str(path.relative_to(root)); meta = self._metadata(path, fmt)
        return {"id": f"candidate_{uuid.uuid4().hex[:12]}", "relative_path": relative, "name": path.name, "format": fmt, "size_bytes": path.stat().st_size if path.is_file() else None, "sha256": self._digest(path) if path.is_file() else None, "metadata": meta}
    def _digest(self, path: Path) -> str:
        h=hashlib.sha256()
        with path.open("rb") as f:
            for block in iter(lambda: f.read(1024*1024), b""): h.update(block)
        return h.hexdigest()
    def _metadata(self, path: Path, fmt: str) -> dict[str, Any]:
        # GDAL is optional so a useful catalogue still works in desktop builds without it.
        base={"layers": [], "crs": None, "bbox": None, "fields": [], "bands": [], "time_candidates": []}
        if fmt == "GeoJSON":
            try:
                value=json.loads(path.read_text(encoding="utf-8")); features=value.get("features", []) if isinstance(value,dict) else []
                props=features[0].get("properties", {}) if features and isinstance(features[0],dict) else {}
                fields=sorted(props) if isinstance(props,dict) else []
                coords=[]
                def collect(value: object) -> None:
                    if isinstance(value,list) and len(value)>=2 and isinstance(value[0],(int,float)) and isinstance(value[1],(int,float)): coords.append((float(value[0]),float(value[1])))
                    elif isinstance(value,list):
                        for child in value: collect(child)
                for feature in features:
                    if isinstance(feature,dict) and isinstance(feature.get("geometry"),dict): collect(feature["geometry"].get("coordinates"))
                bbox=[min(x for x,_ in coords),min(y for _,y in coords),max(x for x,_ in coords),max(y for _,y in coords)] if coords else None
                time_fields=[field for field in fields if any(token in field.lower() for token in ("date","time","timestamp","日期","时间"))]
                base.update({"layers": [{"name": path.stem, "feature_count": len(features)}], "crs": "EPSG:4326", "bbox":bbox, "fields": fields, "time_candidates":time_fields})
            except Exception: base["issues"]=["GeoJSON metadata unavailable"]
        try:
            from osgeo import gdal, ogr  # type: ignore
            ds = gdal.OpenEx(str(path), gdal.OF_VECTOR | gdal.OF_RASTER)
            if ds:
                if ds.RasterCount: base["bands"]=[{"index": n+1} for n in range(ds.RasterCount)]; base["crs"] = ds.GetProjectionRef() or base["crs"]
                else:
                    layers=[]
                    for n in range(ds.GetLayerCount()):
                        layer=ds.GetLayerByIndex(n); definition=layer.GetLayerDefn()
                        layers.append({"name": layer.GetName(), "feature_count": layer.GetFeatureCount()}); base["fields"] = [definition.GetFieldDefn(i).GetName() for i in range(definition.GetFieldCount())]
                    base["layers"] = layers
        except Exception: pass
        base["capabilities"] = {
            "render": (["raster_single_band", "raster_rgb", "classified"] if base["bands"] else ["vector"]),
            "attributes": bool(base["fields"]), "identify": True,
            "statistics": bool(base["bands"]), "time": bool(base["time_candidates"]), "editable": False,
        }
        return base

    def get_scan(self, scan_id: str) -> dict[str, Any]:
        scan=next((x for x in self._doc()["scans"] if x.get("id")==scan_id),None)
        if not scan: raise KeyError(scan_id)
        return self.public_scan(scan)
    @staticmethod
    def public_scan(scan: dict[str, Any]) -> dict[str, Any]: return dict(scan)

    def register_asset(self, *, scan_id: str, candidate_id: str, kind: str, name: str | None = None, metadata: dict[str, Any] | None = None, category_schema: dict[str, Any] | None = None, tags: list[str] | None = None) -> dict[str, Any]:
        allowed={"boundary", "land_use", "rainfall", "raw_imagery", "auxiliary", "drought_indicator"}
        if kind not in allowed: raise CatalogError("不支持的资产类型")
        d=self._doc(); scan=next((x for x in d["scans"] if x.get("id")==scan_id),None)
        if not scan: raise KeyError(scan_id)
        candidate=next((x for x in scan["candidates"] if x.get("id")==candidate_id),None)
        if not candidate: raise KeyError(candidate_id)
        source, root=self._source(d, scan["source_id"]); path=(root/candidate["relative_path"])
        if not self._under(root,path): raise SourceNotAuthorized("候选文件已越出授权目录")
        asset={"id":f"asset_{uuid.uuid4().hex[:16]}","name":(name or candidate["name"]).strip(),"kind":kind,"source_id":source["id"],"source_relative_path":candidate["relative_path"],"format":candidate["format"],"sha256":candidate.get("sha256"),"scanned_at":scan["finished_at"],"metadata":{**candidate.get("metadata",{}),**(metadata or {})},"category_schema":category_schema or {},"tags":sorted(set(tags or [])),"metadata_version":1,"lineage":{"scan_id":scan_id,"candidate_id":candidate_id},"registered_at":_now(),"sessions":[]}
        d["assets"].append(asset); self._save(d); return self.public_asset(asset, include_path=True)

    def register_remote_asset(self, *, url: str, local_name: str, sha256: str, size_bytes: int, kind: str, session_id: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        """Register an Agent-downloaded, project-owned copy without a host path."""
        allowed={"boundary", "land_use", "rainfall", "raw_imagery", "auxiliary", "drought_indicator"}
        if kind not in allowed or not session_id: raise CatalogError("invalid remote asset registration")
        suffix=Path(local_name).suffix.lower(); fmt=self.extensions.get(suffix, "Remote dataset")
        d=self._doc(); asset={"id":f"asset_{uuid.uuid4().hex[:16]}","name":local_name,"kind":kind,"format":fmt,"sha256":sha256,"size_bytes":size_bytes,"metadata":dict(metadata or {}),"category_schema":{},"tags":["remote"],"metadata_version":1,"lineage":{"remote_url":url,"acquisition":"agent-public-http"},"registered_at":_now(),"sessions":[session_id]}
        d["assets"].append(asset); self._save(d); return self.public_asset(asset,include_path=False)

    def list_assets(self, session_id: str | None = None, *, include_path: bool = True) -> list[dict[str, Any]]:
        items=self._doc()["assets"]
        if session_id is not None: items=[a for a in items if session_id in a.get("sessions",[])]
        return [self.public_asset(a,include_path=include_path) for a in items]
    def get_asset(self, asset_id: str, *, include_path: bool = True) -> dict[str, Any]:
        asset=next((a for a in self._doc()["assets"] if a.get("id")==asset_id),None)
        if not asset: raise KeyError(asset_id)
        return self.public_asset(asset,include_path=include_path)
    @staticmethod
    def public_asset(asset: dict[str, Any], *, include_path: bool) -> dict[str, Any]:
        out=dict(asset)
        if not include_path: out.pop("source_relative_path",None); out.pop("source_id",None)
        return out
    def patch_asset(self, asset_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        allowed={"name","metadata","category_schema","tags"}; unknown=set(changes)-allowed
        if unknown: raise CatalogError("只能修改业务元数据、分类 schema、名称或标签")
        d=self._doc(); asset=next((a for a in d["assets"] if a.get("id")==asset_id),None)
        if not asset: raise KeyError(asset_id)
        for key,value in changes.items():
            if key=="name" and (not isinstance(value,str) or not value.strip()): raise CatalogError("资产名称不能为空")
            asset[key]=value.strip() if key=="name" else value
        asset["metadata_version"]=int(asset.get("metadata_version",0))+1; asset["updated_at"]=_now(); self._save(d); return self.public_asset(asset,include_path=True)
    def unregister(self, asset_id: str) -> None:
        d=self._doc(); before=len(d["assets"]); d["assets"]=[a for a in d["assets"] if a.get("id")!=asset_id]
        if len(d["assets"])==before: raise KeyError(asset_id)
        self._save(d)
    def bind(self, asset_id: str, session_id: str) -> dict[str, Any]: return self._set_binding(asset_id,session_id,True)
    def unbind(self, asset_id: str, session_id: str) -> dict[str, Any]: return self._set_binding(asset_id,session_id,False)
    def _set_binding(self, asset_id: str, session_id: str, value: bool) -> dict[str, Any]:
        if not session_id or len(session_id)>80: raise CatalogError("无效会话 ID")
        d=self._doc(); asset=next((a for a in d["assets"] if a.get("id")==asset_id),None)
        if not asset: raise KeyError(asset_id)
        current=set(asset.get("sessions",[])); current.add(session_id) if value else current.discard(session_id); asset["sessions"]=sorted(current); self._save(d); return self.public_asset(asset,include_path=True)
