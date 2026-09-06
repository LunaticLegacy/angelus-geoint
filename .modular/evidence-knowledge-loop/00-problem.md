# GEOINT evidence and drought-knowledge loop

## Goal

Make completed GEOINT derivations and explicit Agent claims durable, session-scoped evidence that is visible in the Evidence panel, available to the Agent by stable IDs, and optionally spatially rendered on the map. Add a small curated drought-reference knowledge base and bounded Agent search/read tools.

## Non-goals

- No vector database, external embedding service, web crawler, or automatic scientific conclusion scoring.
- No change to the legacy PostGIS observation endpoint or source-file access rules.
- No claim that a result is scientifically valid merely because it is recorded.

## Constraints and risks

- All records must be scoped to the current Angelus session and must not disclose host paths.
- Agent inputs may reference only session-bound asset IDs, derivation job IDs, knowledge IDs, and optional GeoJSON geometry.
- The UI is a projection of server-owned state; it must not become an evidence store.
- Rebuilt investigation panels must page durable transcript history rather than
  treating the newest API page as the complete conversation.
- This is a competition-ready, low-operational-overhead knowledge base: curated local references with lexical retrieval.
