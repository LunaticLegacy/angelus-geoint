# Module boundaries

| Module | Semantic role | Owns | May depend on | Must not know |
|---|---|---|---|---|
| `geoint.evidence` | Provenance ledger | session evidence records and GeoJSON projection | JSON persistence primitives | Agent runtime, FastAPI, OpenLayers |
| `geoint.knowledge` | Curated drought reference corpus | bundled documents and lexical retrieval | standard library | sessions, assets, map state |
| `console.projection` | Durable transcript projection | execution-journal to investigation-history projection | session workspace, journal reader | browser DOM or GEOINT domain state |
| `geoint.agent.tools` | Capability adapter | validation and tool-to-domain translation | evidence, knowledge, catalog, derivations | persistence layout and browser DOM |
| `api.geoint` | HTTP adapter | request/response mapping | runtime public services | UI layout and internal persistence |
| `frontend/evidence-*` | Evidence projection | DOM/map layer lifecycle only | REST endpoints, OpenLayers | canonical evidence or knowledge state |

Delete tests: removing evidence only disables evidence listing/recording; removing knowledge only disables knowledge tools; neither removes import, catalog, derivation, or map-document behavior. Each owner exposes domain dictionaries/GeoJSON, so implementations can be replaced without changing consumers.
