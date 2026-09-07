# Boundaries

2026-09-05 source manager revision: `basemap-source-editor` owns structured XYZ form drafts and emits add/update intents; no transport or map imports. `basemap-panel` owns source browsing (distinct from active map source) and conditionally mounts provider settings. Existing store remains sole persisted owner.

## Basemap extension (2026-09-05)

- `basemap-store` owns workspace-wide validated source configuration and private TianDiTu key; no UI/core session dependencies. Replace with another store preserving snapshot/mutation contracts.
- `tianditu-tiles` owns fixed-host tile fetching, size/time/type checks; no arbitrary URL or persistence knowledge.
- `basemap-api` translates requests to store/tile operations; no canonical state. Removing it disables only basemap configuration.
- `basemap-map` owns the basemap group and coordinate positioning through injected map instance; no API/DOM/session knowledge. Never changes analytical layers.
- `basemap-controller` owns loading/mutation sequencing; injected view/map intents and HTTP client only.
- `basemap-panel` owns component DOM/form drafts and emits intents; no transport, persistence, or OpenLayers imports. Dock moves the same mounted element.

- `api-client`: owns HTTP serialization/error conversion; knows paths only.
- `workspace-state`: owns selected session, cached profile and connectors.
- `session-controller`: owns session selection, creation, deletion and profile refresh.
- `connector-controller`: owns connector form submission and session binding; never stores API keys after submission.
- `context-controller`: owns context read/export/import UI.
- `agent-controller`: owns run/stop requests and event-stream lifecycle.
- `investigation-event-projector`: owns the canonical in-browser projection of
  durable messages and Agent lifecycle events into conversation nodes; it must
  not own an EventSource or DOM.
- `investigation-chat`: owns the investigation timeline DOM, follow-scroll and
  prompt affordances; it emits run intents but never performs transport.
- `tool-result-renderer`: owns safe, tool-agnostic projection of one normalized
  tool envelope; it must not inspect a tool name to select a presentation.
- `workspace-ui`: owns buttons, tabs and DOM rendering; emits domain intents.
- `workspace-shell`: owns responsive layout, color tokens and visual hierarchy;
  it must not own session state or make HTTP calls.
- `layer-panel`: owns rendering and persistence intents for the MapDocument
  layer controls; it is displayed through the workspace navigation.
- `chat-composer`: owns prompt submit affordances and keyboard handling; it
  delegates the run intent to `agent-controller`.
- `dock-layout`: owns panel placement, active tabs, tab drag/drop and local
  layout persistence; it must not own a panel's business state.
- `map-edge-resizers`: owns horizontal shell splitter input and locally stored
  left/right widths; it must not own map or dock content state.
- `bottom-dock-resizer`: owns the bottom Dock height splitter and its local
  preference; it must not own the Dock layout, panel content or map state.

The former `workbench-resizer` is retired by the map-centered shell.
- `map-core`: owns only OpenLayers map/layer lifecycle.

Controllers may depend on `api-client`, state and DOM helpers; `map-core` is
forbidden from depending on any Angelus controller.  Deleting a controller
only disables its matching panel, not the map or another panel.  Controllers
are replaceable when their public intent methods remain unchanged.

Session/connector feedback revision: `workspace-state.profile.effective` is
the sole frontend representation of a session binding. `workspace-ui` may
project that state into labels, while `connector-controller` alone publishes a
binding through the existing run-profile contract. `ConnectorStore` owns
connector label uniqueness; `SessionService` owns session/workspace label
uniqueness. Neither persistence owner knows DOM state.
