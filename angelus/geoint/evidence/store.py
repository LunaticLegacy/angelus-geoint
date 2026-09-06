"""Durable evidence ledger independent of Agent, HTTP, and map adapters."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any
from uuid import uuid4

from ...modules.settings_module.json_store import read_json, write_json


class EvidenceError(ValueError):
    """Raised when an evidence record violates its public provenance contract."""


class EvidenceStore:
    """Own the canonical session-scoped evidence ledger.

    The store never resolves asset paths or queries a map. Callers supply
    already-authorized opaque identifiers, which keeps this record format
    portable and safe to return through HTTP and Agent tools.
    """

    def __init__(self, root: Path) -> None:
        self.root = root.resolve()
        self.path = self.root / "records.json"
        self._lock = RLock()

    def _load(self) -> list[dict[str, Any]]:
        data = read_json(self.path, {"schema_version": 1, "records": []})
        if not isinstance(data, dict) or not isinstance(data.get("records"), list):
            raise EvidenceError("evidence ledger is unreadable")
        return [dict(record) for record in data["records"] if isinstance(record, dict)]

    def _save(self, records: list[dict[str, Any]]) -> None:
        write_json(self.path, {"schema_version": 1, "records": records})

    @staticmethod
    def _session_id(value: object) -> str:
        if not isinstance(value, str) or not value or len(value) > 100 or "/" in value or "\\" in value:
            raise EvidenceError("invalid session identifier")
        return value

    @staticmethod
    def _ids(value: object, field: str) -> list[str]:
        if value is None:
            return []
        if not isinstance(value, list) or not all(isinstance(item, str) and item and len(item) <= 160 for item in value):
            raise EvidenceError(f"{field} must be an array of identifiers")
        return list(dict.fromkeys(value))

    @staticmethod
    def _geometry(value: object) -> dict[str, Any] | None:
        if value is None:
            return None
        if not isinstance(value, dict) or value.get("type") not in {"Point", "Polygon", "MultiPolygon"} or not isinstance(value.get("coordinates"), list):
            raise EvidenceError("geometry must be GeoJSON Point, Polygon, or MultiPolygon")
        return value

    @staticmethod
    def _public(record: dict[str, Any]) -> dict[str, Any]:
        return {key: record.get(key) for key in (
            "id", "session_id", "kind", "claim", "indicator", "confidence",
            "source_asset_ids", "derivation_job_id", "knowledge_ids", "geometry", "created_at",
        )}

    def list(self, session_id: str, limit: int = 100) -> list[dict[str, Any]]:
        session_id = self._session_id(session_id)
        bounded = max(1, min(int(limit), 500))
        with self._lock:
            records = [record for record in self._load() if record.get("session_id") == session_id]
        return [self._public(record) for record in reversed(records[-bounded:])]

    def summary(self, session_id: str) -> dict[str, Any]:
        records = self.list(session_id, 500)
        assets = {identifier for record in records for identifier in record["source_asset_ids"]}
        jobs = {record["derivation_job_id"] for record in records if record.get("derivation_job_id")}
        return {"evidence_count": len(records), "asset_count": len(assets), "derivation_count": len(jobs), "status": "已记录" if records else "尚无证据", "risk_score": None, "risk_level": "证据待综合" if records else "尚未运行"}

    def record_derivation(self, session_id: str, job: dict[str, Any]) -> dict[str, Any]:
        session_id = self._session_id(session_id)
        job_id = job.get("id")
        if not isinstance(job_id, str) or not job_id:
            raise EvidenceError("derivation job id is required")
        if job.get("session_id") != session_id:
            raise EvidenceError("derivation job is not owned by this session")
        if job.get("status") != "complete":
            raise EvidenceError("only completed derivations can be recorded as evidence")
        result = job.get("result") if isinstance(job.get("result"), dict) else {}
        claim = result.get("evidence_summary")
        if not isinstance(claim, str) or not claim.strip():
            claim = f"Completed {job.get('operation', 'GEOINT')} derivation using session-bound asset versions."
        with self._lock:
            records = self._load()
            prior = next((item for item in records if item.get("session_id") == session_id and item.get("derivation_job_id") == job_id and item.get("kind") == "derivation"), None)
            if prior is not None:
                return self._public(prior)
            record = self._record(session_id, "derivation", claim, job.get("operation"), 0.8, job.get("asset_ids"), job_id, [], None)
            records.append(record); self._save(records)
        return self._public(record)

    def record_claim(self, *, session_id: str, claim: object, indicator: object = None, confidence: object = 0.5, source_asset_ids: object = None, derivation_job_id: object = None, knowledge_ids: object = None, geometry: object = None) -> dict[str, Any]:
        session_id = self._session_id(session_id)
        if not isinstance(claim, str) or not claim.strip() or len(claim) > 2000:
            raise EvidenceError("claim must be a non-empty string of at most 2000 characters")
        if indicator is not None and (not isinstance(indicator, str) or len(indicator) > 160):
            raise EvidenceError("indicator must be a string of at most 160 characters")
        if not isinstance(confidence, (int, float)) or not 0 <= float(confidence) <= 1:
            raise EvidenceError("confidence must be between 0 and 1")
        assets = self._ids(source_asset_ids, "source_asset_ids")
        knowledge = self._ids(knowledge_ids, "knowledge_ids")
        if derivation_job_id is not None and (not isinstance(derivation_job_id, str) or not derivation_job_id):
            raise EvidenceError("derivation_job_id must be an identifier")
        if not assets and not derivation_job_id and not knowledge:
            raise EvidenceError("evidence needs a source asset, derivation job, or knowledge reference")
        record = self._record(session_id, "agent_claim", claim.strip(), indicator.strip() if isinstance(indicator, str) else None, float(confidence), assets, derivation_job_id, knowledge, self._geometry(geometry))
        with self._lock:
            records = self._load(); records.append(record); self._save(records)
        return self._public(record)

    def _record(self, session_id: str, kind: str, claim: str, indicator: object, confidence: float, asset_ids: object, job_id: object, knowledge_ids: list[str], geometry: dict[str, Any] | None) -> dict[str, Any]:
        return {"id": f"evidence_{uuid4().hex[:16]}", "session_id": session_id, "kind": kind, "claim": claim.strip(), "indicator": indicator if isinstance(indicator, str) else None, "confidence": confidence, "source_asset_ids": self._ids(asset_ids, "source_asset_ids"), "derivation_job_id": job_id if isinstance(job_id, str) else None, "knowledge_ids": knowledge_ids, "geometry": geometry, "created_at": datetime.now(timezone.utc).isoformat()}

    def geojson(self, session_id: str) -> dict[str, Any]:
        features = []
        for record in self.list(session_id, 500):
            if record["geometry"] is None:
                continue
            properties = {key: value for key, value in record.items() if key not in {"geometry", "session_id"}}
            features.append({"type": "Feature", "id": record["id"], "geometry": record["geometry"], "properties": properties})
        return {"type": "FeatureCollection", "features": features}
