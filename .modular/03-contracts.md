# Contracts

Source manager extension: PUT `/api/geoint/basemaps/{source_id}` updates custom XYZ configuration, preserving ID/selection; builtins reject update. XYZ accepts explicit `geographic_crs: EPSG:4326`, `tile_grid: XYZ` alongside `projection: EPSG:3857`; defaults migrate existing config. Unsupported coordinate declarations reject, never silently reproject. Editor emits `update(id, config)`; configured-source browsing does not change map until Apply. TianDiTu credentials shown only for the selected TianDiTu preset.

## Basemap extension

GET `/api/geoint/basemaps` -> `{selected_id, has_tianditu_key, sources}`. Source descriptors contain id/name/kind/tiles/attribution/min_zoom/max_zoom/enabled/builtin. Never expose TianDiTu key.
POST same path accepts strict `{name,url,attribution,projection:'EPSG:3857',min_zoom,max_zoom}` public HTTPS XYZ; unsupported coordinate grids and URL schemes rejected. DELETE `/{id}` removes custom only and selects OSM if necessary.
PUT `/selection` accepts `{source_id}`; PUT `/tianditu-key` accepts write-only `{key}` (empty clears and resets selected TDT to OSM).
GET `/tianditu/{layer}/{z}/{x}/{y}` proxies only vec/cva/img/cia fixed official host, validates grid; no redirects. Network failures become sanitized 502 errors.
Settings are local workspace-wide, separate from session MapDocument. Atomic mode-0600 persistence. No automatic geocoder or Baidu support.
`createBasemapMap(map)` -> `{select(source), locate(lon,lat,zoom)}`; `mountBasemapPanel(host, intents)` -> `{render(snapshot),status(text)}`. Controller uses these replaceable contracts.

`tool-permissions.renderToolPermissions(host, catalog, policy, onChange)` renders
registered categories and tools, emitting a complete permission draft. The
session controller updates the profile JSON draft; the existing Save profile
action persists it. Category selection toggles all contained tools. Late profile
responses are ignored after a newer selection.

Desktop layout: the right Dock spans both workspace rows; the bottom Dock
occupies only the map column. Bottom tabs are outside the scrolling panel body.

`api(path, options) -> Promise<object>` is transport-only.

`workspace-state`: `selectSession(id)`, `setProfile(profile)`,
`setConnectors(connectors)`, `snapshot()`.

Controllers expose intent methods: `sessions.refresh/create/remove/loadProfile/saveProfile`,
`connectors.refresh/createAndBind/bind`, `context.refresh/export/import`, and
`agent.run/stop/reconcile`.  They accept DOM-independent values or a state
snapshot and return promises. Existing Angelus REST payloads are unchanged.

`workspace-shell` consumes stable element IDs only. On desktop it presents a
session header, map canvas, layer rail and investigation rail; at narrow widths
it presents map then workbench in one column.

`layer-panel` receives an effective map document plus a `save(layerId, patch)`
callback. It never calls the map engine or creates a server source URL.

`chat-composer` delegates send actions and Cmd/Ctrl+Enter to an injected
callback; it does not create an Agent run itself.

`investigation-event-projector` exposes `reset(sessionId)`,
`hydrate(messages)`, `setContextSummary(context)`, `beginUserTurn(content)`, `applyEvent(event)`,
`setRunState(state)` and `subscribe(listener)`. Its listener receives a
snapshot of domain nodes only; callers never receive DOM or EventSource state.

`investigation-chat.mount({projector, onSend, onStop})` owns the Agent panel
markup. `onSend(content)` and `onStop()` are asynchronous intent callbacks.

`tool-result-renderer.render(envelope)` accepts
`{call_id, tool_name, status, input, output, duration_ms}` and returns a DOM
element. It derives only generic summaries and must never route by
`tool_name`.

`dock-layout.mount(panels)` receives `{id, title, element}` descriptors and
persists only zone/order/active-tab state. It exposes `reset()` and calls an
injected `onLayoutChange` callback after a successful drop.

`map-edge-resizers` accepts the workspace, map host and resize callback. It
sets only width CSS variables and does not receive a panel descriptor.

`bottom-dock-resizer` accepts the workspace, bottom Dock host and resize
callback. It sets only `--bottom-height`, persists a bounded pixel height, and
does not receive a panel descriptor.
