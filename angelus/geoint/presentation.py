"""Durable, validated Session map-presentation state."""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any


class PresentationError(ValueError):
    pass


class MapPresentationStore:
    """Persist only declarative, Session-owned map presentation settings."""
    def __init__(self, state_root: Path) -> None:
        self._root = state_root / "sessions"

    def get(self, session_id: str) -> dict[str, Any]:
        path = self._path(session_id)
        if not path.exists():
            return {"version": 1, "agent_proposal": {"groups": [], "layers": [], "viewport": None}, "user_overrides": {"groups": [], "layers": [], "viewport": None}, "effective": {"groups": [], "layers": [], "viewport": None}}
        try:
            return self._document(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError) as exc:
            raise PresentationError("invalid persisted map presentation") from exc

    def put(self, session_id: str, value: dict[str, Any]) -> dict[str, Any]:
        value = {"version": 1, "agent_proposal": self.get(session_id).get("agent_proposal", self._blank()), "user_overrides": self._validate(value)}
        path = self._path(session_id); path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
        return self._document(value)

    def propose(self, session_id: str, value: dict[str, Any]) -> dict[str, Any]:
        current = self.get(session_id)
        path = self._path(session_id); path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"version": 1, "agent_proposal": self._validate(value), "user_overrides": current["user_overrides"]}, ensure_ascii=False, indent=2), encoding="utf-8")
        return self.get(session_id)

    @staticmethod
    def _blank() -> dict[str, Any]: return {"groups": [], "layers": [], "viewport": None}

    def _document(self, value: object) -> dict[str, Any]:
        if not isinstance(value, dict): raise PresentationError("presentation must be an object")
        proposal = self._validate(value.get("agent_proposal", self._blank()))
        overrides = self._validate(value.get("user_overrides", value if "layers" in value else self._blank()))
        return {"version": 1, "agent_proposal": proposal, "user_overrides": overrides, "effective": self._merge(proposal, overrides)}

    @staticmethod
    def _merge(proposal: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
        by_id = {item.get("id"): item for item in proposal["layers"]}
        for item in overrides["layers"]: by_id[item.get("id")] = {**by_id.get(item.get("id"), {}), **item}
        return {"groups": overrides["groups"] or proposal["groups"], "layers": list(by_id.values()), "viewport": overrides["viewport"] or proposal["viewport"]}

    def _path(self, session_id: str) -> Path:
        if not session_id or "/" in session_id or "\\" in session_id:
            raise PresentationError("invalid session id")
        return self._root / session_id / "map-presentation.json"

    @staticmethod
    def _validate(value: object) -> dict[str, Any]:
        if not isinstance(value, dict): raise PresentationError("presentation must be an object")
        groups, layers = value.get("groups", []), value.get("layers", [])
        if not isinstance(groups, list) or not isinstance(layers, list): raise PresentationError("groups and layers must be arrays")
        for group in groups:
            if not isinstance(group, dict) or not isinstance(group.get("id"), str) or not isinstance(group.get("visible", True), bool): raise PresentationError("invalid layer group")
        for layer in layers:
            if not isinstance(layer, dict) or not isinstance(layer.get("id"), str) or not isinstance(layer.get("source_kind"), str): raise PresentationError("invalid layer")
            if not isinstance(layer.get("visible", True), bool): raise PresentationError("layer visibility must be boolean")
            opacity = layer.get("opacity", 1)
            if not isinstance(opacity, (int, float)) or not 0 <= opacity <= 1: raise PresentationError("opacity must be between 0 and 1")
            if not isinstance(layer.get("z_index", 0), int): raise PresentationError("z_index must be an integer")
        return {"version": 1, "groups": groups, "layers": layers, "viewport": value.get("viewport")}
