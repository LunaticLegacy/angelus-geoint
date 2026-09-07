"""Evidence/knowledge loop tests: provenance, session isolation, and tools."""
from __future__ import annotations

import json
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory

from angelus.core import AngelusCore
from angelus.geoint import GeoIntToolProvider
from angelus.modules.tool_module import ToolPolicy


def _asset(core: AngelusCore, session_id: str) -> dict:
    catalog = core.geoint_runtime.catalog
    catalog.managed_root.mkdir(parents=True, exist_ok=True)
    payload = b'{"type":"FeatureCollection","features":[]}'
    path = catalog.managed_root / f"{session_id}.geojson"
    path.write_bytes(payload)
    return catalog.register_downloaded_remote_asset(
        url="https://data.example.test/source.geojson", downloaded_path=path,
        display_name="source.geojson", sha256=sha256(payload).hexdigest(), size_bytes=len(payload),
        kind="boundary", session_id=session_id,
    )


def test_evidence_is_session_scoped_and_derivations_are_idempotent():
    with TemporaryDirectory() as directory:
        core = AngelusCore(state_root=Path(directory) / "state")
        core.session_service.create("session_one", "One")
        core.session_service.create("session_two", "Two")
        asset = _asset(core, "session_one")
        job = core.geoint_runtime.derivations.submit(session_id="session_one", operation="vector_statistics", asset_ids=[asset["id"]], parameters={})
        first = core.geoint_runtime.evidence.record_derivation("session_one", job)
        second = core.geoint_runtime.evidence.record_derivation("session_one", job)
        assert first["id"] == second["id"]
        assert len(core.geoint_runtime.evidence.list("session_one")) == 1
        assert core.geoint_runtime.evidence.list("session_two") == []


def test_agent_tools_can_record_traceable_claim_and_search_knowledge():
    with TemporaryDirectory() as directory:
        core = AngelusCore(state_root=Path(directory) / "state")
        core.session_service.create("session_evidence", "Evidence")
        session = core.sessions.get("session_evidence")
        asset = _asset(core, "session_evidence")
        provider = GeoIntToolProvider(core)
        names = {"geoint_record_evidence", "geoint_list_evidence", "geoint_search_drought_knowledge", "geoint_read_drought_knowledge"}
        tools = provider.materialize(session, ToolPolicy(frozenset({"geoint"}), frozenset(names)), "coordinator")
        by_name = {tool.name: tool for tool in tools}
        result = json.loads(by_name["geoint_record_evidence"].handler(
            claim="植被异常需要与降水共同解释。", source_asset_ids=[asset["id"]],
            knowledge_ids=["drought-indicator-triangulation"], confidence=0.6,
        ))
        assert result["evidence"]["source_asset_ids"] == [asset["id"]]
        assert json.loads(by_name["geoint_list_evidence"].handler(limit=10))["summary"]["evidence_count"] == 1
        documents = json.loads(by_name["geoint_search_drought_knowledge"].handler(query="NDVI 干旱", limit=5))["documents"]
        assert documents
        assert json.loads(by_name["geoint_read_drought_knowledge"].handler(document_id=documents[0]["id"]))["content"]
