# Dependency graph

```text
GeoIntRuntime
 ├─ GeoAssetCatalog ─────┐
 ├─ DerivationService ───┼─ GeoIntToolProvider ─ Agent
 ├─ EvidenceStore ───────┤          │
 └─ DroughtKnowledgeBase ┘          └─ API ─ Frontend evidence panel/map adapter
```

Allowed arrows are downward from adapters to domain owners. `EvidenceStore` and `DroughtKnowledgeBase` have no imports from Agent, API, or frontend. The frontend has no direct filesystem or state-store dependency. There are no reverse or cyclic arrows.

`ConsoleProjectionService -> Session workspace -> ExecutionJournal` is a
separate read-only path used by the investigation panel. It does not depend on
GEOINT evidence, and GEOINT does not depend on it.
