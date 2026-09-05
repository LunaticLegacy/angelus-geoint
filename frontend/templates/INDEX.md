# frontend/templates/ — SPA Shell INDEX

| File | Responsibility |
|---|---|
| `index.html` | Historic standalone Angelus runtime UI; retained as source but no longer mounted. |
| `geoint.html` | Sole mounted GEOINT shell. Its map entry is the locally built Vite/OpenLayers bundle at `static/geoint-dist/main.js`, with no Leaflet CDN. |
| `external_agents.html` | Historic External Agent Hub shell; its backend route is not mounted in Phase 1. |

The IDs in `index.html` are the contract consumed by `static/app.js`. A cache
version change on the script reference is required whenever controller behavior
changes incompatibly with a previously served browser copy.

<!-- BEGIN GENERATED SYMBOL MAP -->

## Function Map

| Source | Function / method | Input types | Output type | Semantics |
|---|---|---|---|---|
| — | — | `None` | `None` | 本索引范围不直接拥有可执行函数；沿 Route Map 进入下级索引。 |

## Class Map

| Source | Class | Constructor / field input types | Base(s) | Semantics |
|---|---|---|---|---|
| — | — | `None` | `object` | 本索引范围不直接声明类；沿 Route Map 进入下级索引。 |

<!-- END GENERATED SYMBOL MAP -->
