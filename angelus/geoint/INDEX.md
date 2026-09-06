# angelus/geoint/ — GEOINT Domain INDEX

This package owns the drought-investigation calculation and optional spatial
evidence persistence. It is deliberately independent of Angelus Session and
execution ownership; the HTTP adapter supplies an optional `session_id` only
as provenance on an analysis or observation.

| Package | Responsibility |
|---|---|
| `analysis/` | Drought service/model, GeoJSON geometry, CRS convention, local assets/results and synthetic compatibility generator. |
| `assets/` | Capability-style catalogue and bounded public HTTP(S) materialization. |
| `mapping/` | Basemaps, strict session MapDocument, layer factory, source projection, raster display derivative/style and TianDiTu proxy. |
| `ingestion/` | Session-bound browser upload lifecycle, managed bytes, inspection, display preparation and publication. `shapefile.py` validates complete same-stem SHP bundles and converts them to managed GeoJSON. |
| `processing/` | Bounded asset-backed derivations. |
| `agent/` | Session-scoped, path-free GEOINT Agent tool provider. |
| `runtime/` | Composition root for the service/catalogue/derivation/presentation/import graph. |
| `__init__.py` | Stable public facade; external callers import public GEOINT services from `angelus.geoint`. |

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

## Import boundary

- Uploads are copied to session-scoped managed storage before inspection.
- GeoJSON and GeoTIFF each create one import candidate. Shapefile is a single
  candidate formed from same-stem `.shp`, `.shx`, `.dbf` members; `.prj` and
  `.cpg` are optional.
- SHP inspection and conversion require GDAL/OGR. The UI capability endpoint
  reports that prerequisite instead of accepting a partial/unsupported bundle.
- A converted Shapefile becomes a managed GeoJSON map asset with lineage
  `original_format=Shapefile`; original upload locations remain private.
