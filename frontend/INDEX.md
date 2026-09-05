# frontend/ — Workbench INDEX

The workbench is a static browser client served by `angelus/api/__init__.py`.
It must treat a selected `session_id` as the identity for all new Phase-1
operations. Browser localStorage is only UI selection/theme state, never
Session/Agent/credential authority.

| Path | Responsibility |
|---|---|
| [`templates/INDEX.md`](templates/INDEX.md) | SPA HTML shell and dialog/control IDs. |
| [`static/INDEX.md`](static/INDEX.md) | Runtime controller, styles and render components. |
| `geoint-src/` | Vite/OpenLayers modular source: API adapter, map factory and layer-panel component. |

`/` serves the sole GEOINT drought workbench. The former standalone Angelus
runtime SPA is not mounted; GEOINT reuses Session/run APIs only to hand an
evidence package to an existing Angelus Session. Its visible actions and tabs
are declared by `/api/geoint/ui`, rather than being authored in the HTML.
The GEOINT page owns Session creation/deletion, future-run profile editing and
per-Agent durable-context inspection, credential-redacted export and idle-only
import through the existing Session APIs.

Its map is built locally from `geoint-src/` into `static/geoint-dist/`; it has
no Leaflet CDN dependency.  The map-presentation endpoint returns a v2
effective document, whose source URLs are read-only server projections of
session-bound asset IDs. `api.js` normalizes HTTP validation errors and the
session-request scope prevents stale selected-session responses from mutating
controllers or map layers. The modular import controller accepts browser
`File` objects only while uploading; it publishes through the session-scoped
import API and refreshes the MapDocument rather than injecting Blob URLs into
OpenLayers. In the Tauri desktop shell, `native-import-bridge.js` instead
receives path-free progress and inspection snapshots: the Rust shell owns OS
drag paths and streams bytes to the same loopback API.
An import always belongs to a selected Angelus session: the import panel
disables file selection and points to the canonical selector while none is
selected, rather than presenting a drop target that will silently reject data.

## Current Boundary

Session selection, creation/deletion, message reads, connector settings and
run-profile writes target Phase-1 APIs. Inspector, MCP, plugin and graph UI
code still contains legacy requests and is intentionally not a reliable
capability surface until Session projections replace it.

The global External Agent Hub dialog uses `/api/external-agents` to configure
adapter definitions and inspect health, declared capabilities, remote session
summaries, and capability-gated readable context descriptors. A selected
external context can be previewed as a credential-redacted portable package;
unsupported adapters surface their domain error rather than an empty result.

The Hub can explicitly scan local known Agent processes and show ephemeral
candidate cards. Scanning neither attaches to nor persists a discovered
process; a separate user action creates any durable definition.

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
