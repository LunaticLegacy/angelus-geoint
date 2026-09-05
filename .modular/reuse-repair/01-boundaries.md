# Boundaries

- `geoint-runtime` owns the one core-scoped GeoIntService, GeoAssetCatalog, DerivationService and MapPresentationStore. API and ToolProvider consume it; neither creates durable GEOINT stores.
- `catalog` owns asset identity, binding and internal location resolution for both granted and Angelus-managed copies. It does not expose a path in public DTOs.
- `presentation` owns map-document lock, atomic persistence, and source/representation-neutral layer documents. It does not construct HTTP URLs.
- `representation-projection` owns catalog asset-to-readable source descriptors. API only adapts it; map core consumes descriptors rather than inferring strings.
- `safe-http-download` owns address validation on every URL before connection, redirect policy and bounded streaming. It does not write catalog records.
- `api-client` owns structured error normalization. `session-request-scope` owns selected-session staleness guards. UI controllers consume both.

No module owns another module's state. Runtime deletes affect GEOINT only; catalog replacement preserves internal location contract; UI replaces receive same normalized error / guard interfaces.
