"""Versioned, declarative map documents owned by one Angelus Session."""
from __future__ import annotations

import json
from copy import deepcopy
from math import isfinite
from pathlib import Path
import re
from threading import Lock, RLock
from typing import Any, Callable, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from ..modules.settings_module.json_store import write_json


class PresentationError(ValueError): pass


class _Strict(BaseModel): model_config = ConfigDict(extra="forbid")
class Authority(_Strict): agent_policy: Literal["user_override", "agent_override", "confirm_each"] = "user_override"
class Viewport(_Strict):
    projection: Literal["EPSG:3857"] = "EPSG:3857"
    center: tuple[float, float] = (108.95, 34.27)
    zoom: float = Field(default=7, ge=0, le=28)
    rotation: float = 0
class Group(_Strict):
    id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    title: str = Field(min_length=1, max_length=160)
    visible: bool = True
    expanded: bool = True
    z_index: int = Field(default=0, ge=-100000, le=100000)
class Layer(_Strict):
    id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9_-]+$")
    asset_id: str = Field(min_length=1, max_length=100, pattern=r"^asset_[A-Za-z0-9_-]+$")
    title: str = Field(min_length=1, max_length=160)
    group_id: str | None = Field(default=None, max_length=100)
    source: dict[str, Any] = Field(default_factory=dict)
    visible: bool = True
    opacity: float = Field(default=1, ge=0, le=1)
    z_index: int = Field(default=0, ge=-100000, le=100000)
    min_zoom: float | None = Field(default=None, ge=0, le=28)
    max_zoom: float | None = Field(default=None, ge=0, le=28)
    render: dict[str, Any] = Field(default_factory=dict)
    attribute_view: dict[str, Any] = Field(default_factory=dict)
    @field_validator("source")
    @classmethod
    def source_is_server_generated(cls, value: dict[str, Any]) -> dict[str, Any]:
        if value: raise ValueError("source is server generated and cannot be supplied")
        return value
    @field_validator("render")
    @classmethod
    def raster_render_is_bounded(cls, value: dict[str, Any]) -> dict[str, Any]:
        """Accept only declarative, bounded category and ignore settings.

        The values become WebGL expressions in the browser.  Validating this
        small contract here prevents a persisted map document from becoming an
        arbitrary rendering-program input while still permitting vector style
        records owned by other GEOINT features.
        """
        if not isinstance(value, dict) or value.get("kind") != "raster":
            return value
        allowed = {"kind", "mode", "bands", "range", "band_ranges", "color_ramp", "nodata", "resampling", "interpolate", "classification", "ignore_values"}
        unknown = set(value) - allowed
        if unknown:
            raise ValueError("unsupported raster render fields: " + ", ".join(sorted(unknown)))
        if value.get("mode", "single_band") not in {"single_band", "rgb", "classified"}:
            raise ValueError("unsupported raster render mode")
        bands = value.get("bands", [1])
        if not isinstance(bands, list) or not bands or len(bands) > 32 or any(isinstance(item, bool) or not isinstance(item, int) or not 1 <= item <= 64 for item in bands):
            raise ValueError("raster bands must be 1..64 integer values")
        if value.get("mode") == "classified" and len(bands) != 1:
            raise ValueError("classified raster rendering requires exactly one band")
        if value.get("resampling", "linear") not in {"nearest", "linear"}:
            raise ValueError("unsupported raster resampling")
        def number(item: object) -> bool:
            return not isinstance(item, bool) and isinstance(item, (int, float)) and isfinite(float(item))
        range_value = value.get("range")
        if range_value is not None:
            if not isinstance(range_value, dict) or set(range_value) - {"min", "max", "method"}:
                raise ValueError("invalid raster range")
            if range_value.get("method", "statistics") not in {"manual", "statistics", "percentile"}:
                raise ValueError("invalid raster range method")
            minimum, maximum = range_value.get("min"), range_value.get("max")
            if minimum is not None and not number(minimum) or maximum is not None and not number(maximum):
                raise ValueError("raster range bounds must be finite numbers")
            if number(minimum) and number(maximum) and float(maximum) <= float(minimum):
                raise ValueError("raster range maximum must exceed minimum")
        band_ranges = value.get("band_ranges", [])
        if not isinstance(band_ranges, list) or len(band_ranges) > 32:
            raise ValueError("band_ranges must contain at most 32 records")
        seen_bands: set[int] = set()
        for entry in band_ranges:
            if not isinstance(entry, dict) or set(entry) != {"band", "min", "max"}:
                raise ValueError("invalid band range")
            band, minimum, maximum = entry.get("band"), entry.get("min"), entry.get("max")
            if isinstance(band, bool) or not isinstance(band, int) or band not in bands or band in seen_bands:
                raise ValueError("band range must refer to one selected band")
            if not number(minimum) or not number(maximum) or float(maximum) <= float(minimum):
                raise ValueError("band range maximum must exceed its finite minimum")
            seen_bands.add(band)
        if value.get("nodata") is not None and not number(value["nodata"]):
            raise ValueError("raster nodata must be a finite number or null")
        if "interpolate" in value and not isinstance(value["interpolate"], bool):
            raise ValueError("raster interpolate must be boolean")
        ignored = value.get("ignore_values", [])
        if not isinstance(ignored, list) or len(ignored) > 128 or any(not number(item) for item in ignored):
            raise ValueError("ignore_values must contain at most 128 finite numeric values")
        if len(set(float(item) for item in ignored)) != len(ignored):
            raise ValueError("ignore_values must not contain duplicates")
        classes = value.get("classification", [])
        if classes is not None:
            if not isinstance(classes, list) or len(classes) > 128:
                raise ValueError("classification must contain at most 128 values")
            seen: set[float] = set()
            for entry in classes:
                if not isinstance(entry, dict) or set(entry) - {"value", "label", "color", "opacity"}:
                    raise ValueError("invalid raster classification entry")
                category = entry.get("value")
                if not number(category) or float(category) in seen:
                    raise ValueError("classification values must be unique finite numbers")
                seen.add(float(category))
                if not isinstance(entry.get("label", ""), str) or len(entry.get("label", "")) > 80:
                    raise ValueError("classification label must be at most 80 characters")
                if not isinstance(entry.get("color"), str) or not re.fullmatch(r"#[0-9A-Fa-f]{6}", entry["color"]):
                    raise ValueError("classification color must be a #RRGGBB value")
                if "opacity" in entry and (not number(entry["opacity"]) or not 0 <= float(entry["opacity"]) <= 1):
                    raise ValueError("classification opacity must be between 0 and 1")
        return value
class EditableDocument(_Strict):
    authority: Authority = Field(default_factory=Authority)
    viewport: Viewport = Field(default_factory=Viewport)
    groups: list[Group] = Field(default_factory=list)
    layers: list[Layer] = Field(default_factory=list)


class MapPresentationStore:
    """Persist v2 documents and derive a read-only effective projection."""
    def __init__(self, state_root: Path, asset_lookup: Callable[[str, str], dict[str, Any]] | None = None) -> None:
        self._root, self._asset_lookup = state_root / "sessions", asset_lookup
        self._locks: dict[str, RLock] = {}
        self._locks_guard = Lock()

    def get(self, session_id: str) -> dict[str, Any]:
        with self._session_lock(session_id):
            return self._get_locked(session_id)

    def _get_locked(self, session_id: str) -> dict[str, Any]:
        path = self._path(session_id)
        try: raw = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError: return self._document({"schema_version": 2})
        except (OSError, json.JSONDecodeError) as exc: raise PresentationError("invalid persisted map presentation") from exc
        return self._document(self._migrate(raw))

    def put(self, session_id: str, value: dict[str, Any]) -> dict[str, Any]:
        with self._session_lock(session_id):
            current, editable = self._get_locked(session_id), self._editable(value)
            self._validate_assets(session_id, editable)
            self._write(session_id, {"schema_version": 2, "authority": editable["authority"], "agent_proposal": current["agent_proposal"], "user_overrides": editable})
            return self._get_locked(session_id)

    def propose(self, session_id: str, value: dict[str, Any]) -> dict[str, Any]:
        with self._session_lock(session_id):
            current, proposal = self._get_locked(session_id), self._editable(value)
            self._validate_assets(session_id, proposal)
            self._write(session_id, {"schema_version": 2, "authority": current["authority"], "agent_proposal": proposal, "user_overrides": current["user_overrides"]})
            return self._get_locked(session_id)

    def append_user_layers(self, session_id: str, operation_id: str, layers: list[dict[str, Any]]) -> dict[str, Any]:
        """Atomically publish user-created layers without replacing a map document.

        Import publication is an append operation, not a ``PUT`` replay.  The
        durable operation id makes a retry safe after a browser/network
        interruption and preserves edits made after an earlier import.
        """
        if not operation_id or len(operation_id) > 100 or any(ch in operation_id for ch in "/\\"):
            raise PresentationError("invalid map publication operation")
        with self._session_lock(session_id):
            path = self._path(session_id)
            try:
                raw = self._migrate(json.loads(path.read_text(encoding="utf-8")))
            except FileNotFoundError:
                raw = self._migrate({"schema_version": 2})
            except (OSError, json.JSONDecodeError) as exc:
                raise PresentationError("invalid persisted map presentation") from exc
            published = raw.get("published_operations", [])
            if not isinstance(published, list):
                raise PresentationError("invalid map publication ledger")
            if operation_id in published:
                return self._get_locked(session_id)
            overrides = self._editable(raw.get("user_overrides", {}))
            additions = self._editable({"layers": layers})["layers"]
            existing = {layer["id"] for layer in overrides["layers"]}
            if existing.intersection(layer["id"] for layer in additions):
                raise PresentationError("import layer ID already exists")
            self._validate_assets(session_id, {**overrides, "layers": additions})
            overrides["layers"].extend(additions)
            raw["schema_version"] = 2
            raw["authority"] = Authority.model_validate(raw.get("authority", {})).model_dump()
            raw["agent_proposal"] = self._editable(raw.get("agent_proposal", {}))
            raw["user_overrides"] = overrides
            raw["published_operations"] = [*published, operation_id][-200:]
            self._write(session_id, raw)
            return self._get_locked(session_id)

    def _write(self, session_id: str, value: dict[str, Any]) -> None:
        write_json(self._path(session_id), value)

    def _session_lock(self, session_id: str) -> RLock:
        # Validate before adding a lock entry so hostile input cannot grow the
        # lock registry indefinitely.
        self._path(session_id)
        with self._locks_guard:
            return self._locks.setdefault(session_id, RLock())

    def _document(self, value: dict[str, Any]) -> dict[str, Any]:
        try:
            authority = Authority.model_validate(value.get("authority", {})).model_dump()
            proposal, overrides = self._editable(value.get("agent_proposal", {})), self._editable(value.get("user_overrides", {}))
        except ValidationError as exc: raise PresentationError(str(exc)) from exc
        effective, conflicts = self._merge(proposal, overrides, authority["agent_policy"])
        return {"schema_version": 2, "authority": authority, "agent_proposal": proposal, "user_overrides": overrides, "effective": effective, "conflicts": conflicts}

    def _editable(self, value: object) -> dict[str, Any]:
        if not isinstance(value, dict): raise PresentationError("map document must be an object")
        forbidden = set(value) - {"authority", "viewport", "groups", "layers"}
        if forbidden: raise PresentationError("unsupported writable fields: " + ", ".join(sorted(forbidden)))
        try: result = EditableDocument.model_validate(value).model_dump(mode="json")
        except ValidationError as exc: raise PresentationError(str(exc)) from exc
        if len({x["id"] for x in result["groups"]}) != len(result["groups"]): raise PresentationError("group IDs must be unique")
        if len({x["id"] for x in result["layers"]}) != len(result["layers"]): raise PresentationError("layer IDs must be unique")
        groups = {x["id"] for x in result["groups"]}
        for layer in result["layers"]:
            if layer["group_id"] is not None and layer["group_id"] not in groups: raise PresentationError("layer references an unknown group")
            if layer["min_zoom"] is not None and layer["max_zoom"] is not None and layer["min_zoom"] > layer["max_zoom"]: raise PresentationError("min_zoom must not exceed max_zoom")
        return result

    def _validate_assets(self, session_id: str, document: dict[str, Any]) -> None:
        if not self._asset_lookup: return
        for layer in document["layers"]:
            try: self._asset_lookup(session_id, layer["asset_id"])
            except Exception as exc: raise PresentationError("layer asset is not bound to this session") from exc

    @staticmethod
    def _merge(proposal: dict[str, Any], overrides: dict[str, Any], policy: str) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        effective, conflicts = deepcopy(proposal), []
        # An imported/user-created layer that the Agent has never proposed is
        # not a conflicting field and must survive ``agent_override``.
        if policy == "agent_override":
            known = {layer["id"] for layer in effective["layers"]}
            effective["layers"].extend(deepcopy(layer) for layer in overrides["layers"] if layer["id"] not in known)
            return effective, conflicts
        if overrides["groups"]: effective["groups"] = deepcopy(overrides["groups"])
        if overrides["viewport"] != Viewport().model_dump(mode="json"): effective["viewport"] = deepcopy(overrides["viewport"])
        by_id = {x["id"]: x for x in effective["layers"]}
        for layer in overrides["layers"]:
            agent = by_id.get(layer["id"])
            if policy == "confirm_each" and agent and agent != layer:
                conflicts.append({"layer_id": layer["id"], "agent": agent, "user": layer}); continue
            by_id[layer["id"]] = {**(agent or {}), **layer}
        effective["layers"] = list(by_id.values())
        return effective, conflicts

    @staticmethod
    def _migrate(value: object) -> dict[str, Any]:
        if not isinstance(value, dict): raise PresentationError("presentation must be an object")
        if value.get("schema_version") == 2: return value
        def convert(old: object) -> dict[str, Any]:
            old = old if isinstance(old, dict) else {}; layers = []
            for item in old.get("layers", []) if isinstance(old.get("layers", []), list) else []:
                if not isinstance(item, dict): continue
                asset = item.get("asset_id") or item.get("source_id")
                if not isinstance(asset, str) or not asset.startswith("asset_"): continue
                layers.append({"id": item.get("id", asset), "asset_id": asset, "title": item.get("title", asset), "group_id": item.get("group_id"), "visible": item.get("visible", True), "opacity": item.get("opacity", 1), "z_index": item.get("z_index", 0), "min_zoom": item.get("min_zoom"), "max_zoom": item.get("max_zoom"), "render": item.get("render", {}), "attribute_view": item.get("attribute_view", {})})
            return {"groups": old.get("groups", []), "layers": layers, "viewport": old.get("viewport") or {}}
        return {"schema_version": 2, "authority": {"agent_policy": "user_override"}, "agent_proposal": convert(value.get("agent_proposal", value)), "user_overrides": convert(value.get("user_overrides", {}))}

    def _path(self, session_id: str) -> Path:
        if not session_id or "/" in session_id or "\\" in session_id: raise PresentationError("invalid session id")
        return self._root / session_id / "map-presentation.json"
