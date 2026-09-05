"""Local source grants, bounded scans and durable asset registrations."""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
from time import monotonic
from typing import Any, Protocol
import uuid

from ...modules.settings_module.json_store import write_json


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
    """Use Angelus's one atomic JSON publication primitive."""
    write_json(path, value)


class GeoAssetCatalog:
    """Persistent metadata directory with capability-style source IDs."""
    extensions = {".geojson": "GeoJSON", ".json": "GeoJSON", ".shp": "Shapefile", ".tif": "GeoTIFF", ".tiff": "GeoTIFF", ".hdr": "ENVI"}

    def __init__(self, state_root: Path, *, picker: DirectoryPicker | None = None) -> None:
        self.root = state_root.resolve(); self.path = self.root / "catalog.json"
        # This directory is Angelus-owned.  It is deliberately a sibling of the
        # catalogue, so the Agent downloader and the catalogue can use one
        # durable locator without ever persisting a host path in an asset.
        self.managed_root = (self.root.parent / "downloads").resolve()
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
        base={"layers": [], "crs": None, "bbox": None, "fields": [], "geometry_types": [], "bands": [], "nodata": None, "statistics": [], "time_candidates": [], "render_source_kinds": []}
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
                geometry_types=sorted({str(feature.get("geometry", {}).get("type")) for feature in features if isinstance(feature,dict) and isinstance(feature.get("geometry"),dict) and feature["geometry"].get("type")})
                base.update({"layers": [{"name": path.stem, "feature_count": len(features)}], "crs": "EPSG:4326", "bbox":bbox, "fields": fields, "geometry_types":geometry_types, "time_candidates":time_fields, "render_source_kinds":["vector"]})
            except Exception: base["issues"]=["GeoJSON metadata unavailable"]
        try:
            from osgeo import gdal, ogr  # type: ignore
            ds = gdal.OpenEx(str(path), gdal.OF_VECTOR | gdal.OF_RASTER)
            if ds:
                if ds.RasterCount:
                    base["bands"]=[{"index": n+1, "nodata": ds.GetRasterBand(n+1).GetNoDataValue(), "statistics": ds.GetRasterBand(n+1).GetStatistics(True, True)} for n in range(ds.RasterCount)]
                    base["nodata"] = base["bands"][0]["nodata"]; base["statistics"] = base["bands"][0]["statistics"] or []; base["render_source_kinds"]=["cog", "xyz"]
                    base["crs"] = ds.GetProjectionRef() or base["crs"]
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
        if not base["render_source_kinds"]: base["render_source_kinds"] = ["cog", "xyz"] if base["bands"] else ["vector"]
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

    def _managed_path(self, relative_path: str) -> Path:
        """Resolve an internal managed filename without accepting path traversal."""
        if not relative_path or Path(relative_path).name != relative_path:
            raise CatalogError("invalid managed asset filename")
        try:
            path = (self.managed_root / relative_path).resolve(strict=True)
            path.relative_to(self.managed_root)
        except (OSError, ValueError) as exc:
            raise CatalogError("managed asset copy is unavailable") from exc
        if not path.is_file():
            raise CatalogError("managed asset copy is unavailable")
        return path

    @staticmethod
    def _safe_remote_suffix(name: str) -> str:
        suffix = Path(name).suffix.lower()
        if not suffix or len(suffix) > 16 or not suffix[1:].isalnum():
            return ".bin"
        return suffix

    def _register_managed_remote_file(
        self,
        *,
        url: str,
        local_name: str,
        stored_name: str,
        sha256: str,
        size_bytes: int,
        kind: str,
        session_id: str,
        metadata: dict[str, Any] | None,
        asset_id: str | None = None,
    ) -> dict[str, Any]:
        """Register a verified file already stored below ``managed_root``."""
        allowed={"boundary", "land_use", "rainfall", "raw_imagery", "auxiliary", "drought_indicator"}
        if kind not in allowed or not session_id: raise CatalogError("invalid remote asset registration")
        if not isinstance(url, str) or not url:
            raise CatalogError("invalid remote asset URL")
        path = self._managed_path(stored_name)
        if path.stat().st_size != size_bytes or self._digest(path) != sha256:
            raise CatalogError("managed asset copy failed integrity verification")
        suffix = self._safe_remote_suffix(local_name)
        fmt=self.extensions.get(suffix, "Remote dataset")
        asset_id = asset_id or f"asset_{uuid.uuid4().hex[:16]}"
        computed_metadata = self._metadata(path, fmt)
        # The caller may add acquisition details such as content type but may
        # not remove the actual file-derived capabilities.
        combined_metadata = {**computed_metadata, **dict(metadata or {})}
        d=self._doc(); asset={"id":asset_id,"name":local_name,"kind":kind,"format":fmt,"sha256":sha256,"size_bytes":size_bytes,"metadata":combined_metadata,"category_schema":{},"tags":["remote"],"metadata_version":1,"lineage":{"remote_url":url,"acquisition":"agent-public-http"},"storage":{"kind":"managed","relative_path":stored_name},"registered_at":_now(),"sessions":[session_id]}
        d["assets"].append(asset); self._save(d); return self.public_asset(asset,include_path=False)

    def register_remote_asset(self, *, url: str, local_name: str, sha256: str, size_bytes: int, kind: str, session_id: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
        """Register an Agent-downloaded, project-owned copy without a host path.

        ``local_name`` is a managed filename, not a caller-provided filesystem
        path.  This preserves the existing Agent-facing method while making
        its resulting asset renderable through :meth:`bound_path`.
        """
        return self._register_managed_remote_file(
            url=url, local_name=local_name, stored_name=local_name,
            sha256=sha256, size_bytes=size_bytes, kind=kind,
            session_id=session_id, metadata=metadata,
        )

    def register_downloaded_remote_asset(
        self,
        *,
        url: str,
        downloaded_path: Path,
        display_name: str,
        sha256: str,
        size_bytes: int,
        kind: str,
        session_id: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Adopt a temporary file made by ``download_public_dataset``.

        The temporary file must already be beneath ``managed_root``.  This
        guarantees an atomic same-filesystem rename and prevents this internal
        convenience method from becoming a generic host-file import path.
        """
        try:
            temporary = downloaded_path.resolve(strict=True)
            temporary.relative_to(self.managed_root)
        except (OSError, ValueError) as exc:
            raise CatalogError("download is not in managed GEOINT storage") from exc
        if not temporary.is_file():
            raise CatalogError("download is not a file")
        asset_id = f"asset_{uuid.uuid4().hex[:16]}"
        stored_name = f"remote_{asset_id.removeprefix('asset_')}{self._safe_remote_suffix(display_name)}"
        self.managed_root.mkdir(parents=True, exist_ok=True)
        target = self.managed_root / stored_name
        try:
            os.replace(temporary, target)
            return self._register_managed_remote_file(
                url=url, local_name=display_name, stored_name=stored_name,
                sha256=sha256, size_bytes=size_bytes, kind=kind,
                session_id=session_id, metadata=metadata, asset_id=asset_id,
            )
        except BaseException:
            target.unlink(missing_ok=True)
            raise

    def register_managed_batch(self, *, session_id: str, import_id: str, entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Adopt import-service owned files as session-bound catalogue assets.

        ``entries`` is intentionally internal: paths are accepted only after
        proving they live below the catalogue's managed root.  HTTP callers
        and Agent tools still only ever address an asset ID.
        """
        if not session_id or not import_id or not entries:
            raise CatalogError("invalid managed import batch")
        allowed = {"boundary", "land_use", "rainfall", "raw_imagery", "auxiliary", "drought_indicator"}
        self.managed_root.mkdir(parents=True, exist_ok=True)
        document = self._doc()
        existing = {asset.get("lineage", {}).get("import_entry_id"): asset for asset in document["assets"] if isinstance(asset.get("lineage"), dict) and asset.get("lineage", {}).get("import_id") == import_id}
        public: list[dict[str, Any]] = []
        for entry in entries:
            entry_id, staged = entry.get("entry_id"), entry.get("path")
            if not isinstance(entry_id, str) or not isinstance(staged, Path):
                raise CatalogError("invalid managed import entry")
            if entry_id in existing:
                public.append(self.public_asset(existing[entry_id], include_path=False)); continue
            kind = entry.get("kind", "auxiliary")
            if kind not in allowed:
                raise CatalogError("unsupported import asset type")
            try:
                source = staged.resolve(strict=True); source.relative_to(self.managed_root)
            except (OSError, ValueError) as exc:
                raise CatalogError("managed import file is unavailable") from exc
            suffix = self._safe_remote_suffix(str(entry.get("name") or source.name))
            asset_id = f"asset_{uuid.uuid4().hex[:16]}"
            stored_name = f"import_{asset_id.removeprefix('asset_')}{suffix}"
            target = self.managed_root / stored_name
            os.replace(source, target)
            fmt = self.extensions.get(suffix)
            if fmt not in {"GeoJSON", "GeoTIFF"}:
                target.unlink(missing_ok=True)
                raise CatalogError("import has no configured map representation")
            metadata = self._metadata(target, fmt)
            asset = {
                "id": asset_id, "name": str(entry.get("title") or entry.get("name") or target.name).strip()[:160],
                "kind": kind, "format": fmt, "sha256": self._digest(target), "size_bytes": target.stat().st_size,
                "metadata": metadata, "category_schema": {}, "tags": ["import"], "metadata_version": 1,
                "lineage": {"acquisition": "browser-import", "import_id": import_id, "import_entry_id": entry_id},
                "storage": {"kind": "managed", "relative_path": stored_name}, "registered_at": _now(), "sessions": [session_id],
            }
            document["assets"].append(asset); public.append(self.public_asset(asset, include_path=False))
        self._save(document)
        return public

    def list_assets(self, session_id: str | None = None, *, include_path: bool = True) -> list[dict[str, Any]]:
        items=self._doc()["assets"]
        if session_id is not None: items=[a for a in items if session_id in a.get("sessions",[])]
        return [self.public_asset(a,include_path=include_path) for a in items]
    def get_asset(self, asset_id: str, *, include_path: bool = True) -> dict[str, Any]:
        asset=next((a for a in self._doc()["assets"] if a.get("id")==asset_id),None)
        if not asset: raise KeyError(asset_id)
        return self.public_asset(asset,include_path=include_path)
    def bound_asset(self, session_id: str, asset_id: str) -> dict[str, Any]:
        """Return public metadata only after checking the session capability."""
        asset = next((a for a in self._doc()["assets"] if a.get("id") == asset_id), None)
        if not asset: raise KeyError(asset_id)
        if session_id not in asset.get("sessions", []): raise SourceNotAuthorized("asset is not bound to this session")
        return self.public_asset(asset, include_path=False)
    def bound_path(self, session_id: str, asset_id: str) -> tuple[dict[str, Any], Path]:
        """Internal render helper; paths never leave this catalogue module."""
        public = self.bound_asset(session_id, asset_id)
        raw = next(a for a in self._doc()["assets"] if a.get("id") == asset_id)
        storage = raw.get("storage")
        if isinstance(storage, dict) and storage.get("kind") == "managed":
            relative = storage.get("relative_path")
            if not isinstance(relative, str):
                raise CatalogError("managed asset record is invalid")
            return public, self._managed_path(relative)
        if "source_id" not in raw or "source_relative_path" not in raw:
            raise CatalogError("asset has no local renderable copy")
        _, root = self._source(self._doc(), str(raw["source_id"]))
        path = root / str(raw["source_relative_path"])
        if not self._under(root, path): raise SourceNotAuthorized("asset path is outside its source grant")
        return public, path
    @staticmethod
    def public_asset(asset: dict[str, Any], *, include_path: bool) -> dict[str, Any]:
        out=dict(asset)
        # Managed filenames and acquisition URLs are internal lineage.  The
        # front end and Agents work through asset IDs plus controlled routes.
        out.pop("storage", None)
        lineage = out.get("lineage")
        if isinstance(lineage, dict):
            lineage = dict(lineage)
            lineage.pop("remote_url", None)
            out["lineage"] = lineage
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
    def unbind_session(self, session_id: str) -> None:
        """Revoke one deleted Session's capability without touching user files."""
        d = self._doc(); changed = False
        for asset in d["assets"]:
            sessions = set(asset.get("sessions", []))
            if session_id in sessions:
                sessions.remove(session_id); asset["sessions"] = sorted(sessions); changed = True
        if changed: self._save(d)
    def _set_binding(self, asset_id: str, session_id: str, value: bool) -> dict[str, Any]:
        if not session_id or len(session_id)>80: raise CatalogError("无效会话 ID")
        d=self._doc(); asset=next((a for a in d["assets"] if a.get("id")==asset_id),None)
        if not asset: raise KeyError(asset_id)
        current=set(asset.get("sessions",[])); current.add(session_id) if value else current.discard(session_id); asset["sessions"]=sorted(current); self._save(d); return self.public_asset(asset,include_path=True)
