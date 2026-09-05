# angelus/geoint/ — GEOINT Domain INDEX

This package owns the drought-investigation calculation and optional spatial
evidence persistence. It is deliberately independent of Angelus Session and
execution ownership; the HTTP adapter supplies an optional `session_id` only
as provenance on an analysis or observation.

| File | Responsibility |
|---|---|
| `service.py` | GEOINT application facade: composes assets, geometry selection, risk model, result persistence and optional PostGIS operations. |
| `geometry.py` | Dependency-light GeoJSON AOI validation, containment and representative-point selection. |
| `crs.py` | Server-owned WGS84 / Plate Carrée CRS convention used by every GEOINT input and analysis product. |
| `risk_model.py` | Versioned anomaly normalization, configurable weights, severity classes and summary calculations. |
| `prototype.py` | Explicit synthetic-only grid generator retained for compatibility tests. |
| `local_assets.py` | Immutable, checksum-pinned local `data/` GeoJSON indicator asset catalog and quality validation. |
| `local_results.py` | Durable bounded local analysis archive used when PostGIS is unavailable. |
| `presentation.py` | Strict Pydantic MapDocument v2 validation, v1 migration, authority-policy merge and session-scoped persistence. |
| `catalog/service.py` | Capability-style asset catalogue plus internal session-bound render path resolution. |
| `runtime.py` | Core-scoped composition for the one GEOINT service/catalogue/derivation/presentation graph shared by HTTP and Agent adapters. |
| `representation.py` | Strict asset-to-readable-map-source projection; unsupported formats are never advertised as XYZ. |
| `raster_presentation.py` | GDAL-backed, managed EPSG:3857 COG derivatives for browser rendering; original TIFFs are never overwritten. |
| `remote_download.py` | Bounded public HTTP(S) downloader with each redirect target validated before connection. |
| `imports/` | Session-bound browser upload lifecycle: managed bytes, bounded GeoJSON/GeoTIFF inspection, controlled display derivatives, catalogue publication and idempotent map-layer append. |
| `__init__.py` | Public domain-service exports. |

## Runtime boundary

- The mounted risk path uses only a registered local indicator asset; it
  writes asset metadata and results under `.angelus-state/geoint/` and marks
  output `local-asset-indicators`, never synthetic.
- The legacy `/drought/analyze` compatibility path may still produce
  explicitly marked `prototype-synthetic` output.
- `ANGELUS_GEOINT_DATABASE_URL`: PostGIS is used when reachable; an
  unavailable database never turns synthetic output into a
  claimed real observation.
- Exact geometry intersection intentionally requires PostGIS and returns a
  service-unavailable response if it is not configured.
