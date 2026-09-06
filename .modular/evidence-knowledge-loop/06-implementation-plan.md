# Implementation plan

1. Implement `EvidenceStore` and `DroughtKnowledgeBase`, compose both in `GeoIntRuntime`.
2. Add session-scoped evidence and read-only knowledge HTTP endpoints.
3. Extend GEOINT Agent tools with provenance validation, idempotent derivation evidence, explicit claims, and knowledge retrieval.
4. Add evidence panel refresh/rendering and optional GeoJSON map overlay.
5. Verify session isolation, tool behavior, API surfaces, and frontend build.
6. Restore the full durable transcript incrementally from all session attempt
   journals after reload, preserving the newest-page performance boundary.
