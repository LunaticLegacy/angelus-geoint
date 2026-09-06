"""Workspace-wide basemap configuration, separate from scientific map documents."""
from __future__ import annotations

import ipaddress
import json
import re
from pathlib import Path
from threading import RLock
from typing import Literal
from urllib.parse import urlsplit, parse_qsl
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

from ...modules.settings_module.json_store import write_json


class XYZConfig(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    name: str = Field(min_length=1, max_length=80)
    url: str = Field(min_length=1, max_length=2048)
    attribution: str = Field(min_length=1, max_length=300)
    projection: Literal["EPSG:3857"] = "EPSG:3857"
    geographic_crs: Literal["EPSG:4326"] = "EPSG:4326"
    tile_grid: Literal["XYZ"] = "XYZ"
    min_zoom: int = Field(default=0, ge=0, le=22)
    max_zoom: int = Field(default=19, ge=0, le=22)

    @model_validator(mode="after")
    def validate_source(self):
        if not self.name.strip() or not self.attribution.strip():
            raise ValueError("名称与来源署名不能为空")
        if self.min_zoom > self.max_zoom:
            raise ValueError("最小缩放级别不能大于最大级别")
        url = urlsplit(self.url)
        if (url.scheme != "https" or not url.hostname or url.username or url.password
                or url.fragment or url.port not in (None, 443)
                or re.search(r"[\s\\<>]", self.url)):
            raise ValueError("仅支持不含凭据的公开 HTTPS XYZ 地址")
        host = url.hostname.lower()
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal")) or "." not in host:
            raise ValueError("不支持本地地址")
        try:
            address = ipaddress.ip_address(host)
        except ValueError:
            address = None
        if address is not None and not address.is_global:
            raise ValueError("不支持私有网络地址")
        if any(host == domain or host.endswith("." + domain) for domain in ("baidu.com", "bdimg.com", "autonavi.com", "amap.com")):
            raise ValueError("该服务需要专用坐标适配，不能作为标准 XYZ 导入")
        if any(k.lower() in {"key", "tk", "token", "access_token", "api_key", "apikey"} for k, _ in parse_qsl(url.query)):
            raise ValueError("自定义 XYZ 仅支持公开源；天地图请使用专用 Key 设置")
        if set(re.findall(r"\{[^{}]*\}", self.url)) != {"{x}", "{y}", "{z}"}:
            raise ValueError("地址必须包含且仅包含 {z}、{x}、{y} 模板变量")
        if "{" in url.netloc or "}" in url.netloc:
            raise ValueError("域名不能包含模板变量")
        remainder = self.url.replace("{x}", "").replace("{y}", "").replace("{z}", "")
        if "{" in remainder or "}" in remainder:
            raise ValueError("模板括号无效")
        return self


class BasemapStore:
    def __init__(self, path: Path):
        self.path = path
        self._lock = RLock()
        self._data = {"selected_id": "osm", "key": "", "custom": {}}
        if path.exists():
            data = json.loads(path.read_text())
            data["custom"] = {k: XYZConfig.model_validate(v).model_dump() for k, v in data["custom"].items()}
            self._data = data

    def snapshot(self):
        with self._lock:
            sources = [{"id": "osm", "name": "OpenStreetMap", "kind": "osm", "tiles": [], "attribution": "© OpenStreetMap contributors", "min_zoom": 0, "max_zoom": 19, "enabled": True, "builtin": True}]
            for variant, name, layers in [("vector", "天地图 · 矢量与注记", ["vec", "cva"]), ("imagery", "天地图 · 影像与注记", ["img", "cia"])]:
                sources.append({"id": f"tianditu-{variant}", "name": name, "kind": "xyz", "tiles": [f"/api/geoint/basemaps/tianditu/{layer}/{{z}}/{{x}}/{{y}}" for layer in layers], "attribution": "© 天地图", "min_zoom": 1, "max_zoom": 18, "enabled": bool(self._data["key"]), "builtin": True})
            for id_, config in self._data["custom"].items():
                sources.append({**config, "id": id_, "kind": "xyz", "tiles": [config["url"]], "enabled": True, "builtin": False})
            sources[0].update(geographic_crs="EPSG:4326", projection="EPSG:3857", tile_grid="XYZ")
            for source in sources[1:3]:
                source.update(geographic_crs="以服务元数据为准（不可仅由 _w 推断）", projection="EPSG:3857", tile_grid="WMTS · w")
            return {"selected_id": self._data["selected_id"], "has_tianditu_key": bool(self._data["key"]), "sources": sources}

    def _commit(self, data):
        write_json(self.path, data)
        self._data = data
        return self.snapshot()

    def add(self, config: XYZConfig):
        with self._lock:
            if len(self._data["custom"]) >= 30:
                raise ValueError("最多保存 30 个自定义源")
            return self._commit({**self._data, "custom": {**self._data["custom"], f"xyz-{uuid4().hex}": config.model_dump()}})

    def select(self, source_id: str):
        with self._lock:
            if not any(s["id"] == source_id and s["enabled"] for s in self.snapshot()["sources"]):
                raise ValueError("地图源不存在或尚未配置 Key")
            return self._commit({**self._data, "selected_id": source_id})

    def update(self, source_id: str, config: XYZConfig):
        with self._lock:
            if source_id not in self._data["custom"]:
                raise ValueError("只能编辑已保存的自定义地图源")
            return self._commit({**self._data, "custom": {**self._data["custom"], source_id: config.model_dump()}})

    def delete(self, source_id: str):
        with self._lock:
            if source_id not in self._data["custom"]:
                raise ValueError("只能删除已保存的自定义地图源")
            custom = {k: v for k, v in self._data["custom"].items() if k != source_id}
            return self._commit({**self._data, "custom": custom, "selected_id": "osm" if self._data["selected_id"] == source_id else self._data["selected_id"]})

    def set_key(self, key: str):
        with self._lock:
            if key and not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", key):
                raise ValueError("Key 格式无效")
            selected = self._data["selected_id"]
            return self._commit({**self._data, "key": key, "selected_id": "osm" if not key and selected.startswith("tianditu-") else selected})

    def tianditu_key(self):
        with self._lock:
            return self._data["key"]
