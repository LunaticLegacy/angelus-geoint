# `angelus/geoint/imports/` — Browser Import Boundary

This package owns the temporary, session-scoped browser-file lifecycle. It
never exposes a host path, creates catalogue identity directly from HTTP, or
adds OpenLayers layers.

| File | Ownership |
|---|---|
| `models.py` | File declarations, format whitelist and upload limits. |
| `storage.py` | Private managed bytes, SHA-256 and durable manifest snapshots. |
| `inspector.py` | Bounded GeoJSON/GeoTIFF validation and candidate metadata. |
| `preparer.py` | Controlled display-copy staging under catalogue-managed storage. |
| `service.py` | Import state transitions and idempotent catalogue/presentation publication. |

Currently enabled formats are GeoJSON and georeferenced GeoTIFF. Shapefile
ZIP, GeoPackage and CSV are intentionally absent from this package's public
capabilities until their safe conversion paths exist.
