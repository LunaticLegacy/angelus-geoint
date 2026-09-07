# Public contracts

## Evidence record

```json
{
  "id": "evidence_<opaque>", "session_id": "session_<opaque>",
  "kind": "derivation|agent_claim", "claim": "string", "indicator": "string|null",
  "confidence": 0.0, "source_asset_ids": ["asset_<opaque>"],
  "derivation_job_id": "job_<opaque>|null", "knowledge_ids": ["drought-..."],
  "geometry": {"type": "Point", "coordinates": []}, "created_at": "ISO-8601"
}
```

`GET /api/geoint/sessions/{session_id}/evidence` returns `{records, summary}` and `.../evidence/geojson` returns a FeatureCollection. `POST .../evidence` is not required for the browser: explicit claims are intentionally Agent-tool mediated.

`syncEvidenceLayer(map, featureCollection, {visible})` maintains a transient
`geoint-evidence` OpenLayers overlay. It is hidden by default; the evidence
panel's “在地图显示证据范围” checkbox calls `setEvidenceLayerVisible` and does
not modify a session Map Document layer.

## Knowledge

`GET /api/geoint/knowledge/search?q=&limit=` returns public result excerpts. `GET /api/geoint/knowledge/{id}` returns a public document. Agent tools are `geoint_search_drought_knowledge(query, limit)` and `geoint_read_drought_knowledge(document_id)`.

## Agent tools

- `geoint_read_result(job_id)` creates/returns the idempotent derivation evidence record.
- `geoint_record_evidence(claim, source_asset_ids?, derivation_job_id?, knowledge_ids?, indicator?, confidence?, geometry?)` validates every reference and creates a traceable claim.
- `geoint_list_evidence(limit?)` reads only the executing session's records.

## Investigation history paging

`GET /api/sessions/{session_id}/investigation-history?before=&limit=` is the
canonical transcript projection. It returns user submissions, completed Agent
rounds, and formatted tool calls from all retained execution attempts, plus a
chronological page with `next_cursor` and `has_more`. The investigation
controller owns the cursor and prepends older pages into the projector. The
chat component only requests the next page when its timeline reaches the top.
