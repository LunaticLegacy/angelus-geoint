# Architecture validation

PASS

The graph is acyclic; state has one owner.  The transport layer owns no domain
state, UI does not call persistence, and controllers exchange only session IDs
and JSON contracts.  The map cannot learn agent protocol.  Each controller can
be unit-tested with a fake API/state and removed without breaking unrelated
panels.  No public backend contract is added.

Layout revision: PASS. Moving the existing `session-select` DOM node to the
shell header leaves controller contracts intact. CSS token changes own no state
and cannot introduce a map/controller dependency.

Composition revision: PASS. `layer-panel` emits a save intent to composition;
it has no map-core import. The GeoINT UI catalogue owns only navigation labels,
not canonical map or session state. Moving the workbench below the map changes
no controller dependency.

Density and resize revision: PASS. Form grids own no state. The resizer has one
owned CSS variable and calls a narrow map viewport callback; it does not import
map data, a controller or the session store.

Map-centered revision: PASS. Removing the resizer removes state rather than
moving it. The center map remains owned by `map-core`; the right chat workbench
does not import it and communicates through existing asset/map-document APIs.

Investigation chat revision: PASS. The projector owns conversation projection,
the controller owns the SSE connection, and the chat owns DOM only. The generic
tool renderer does not know GEOINT or tool identities and no module gains a
map dependency. Removing the chat disables only the investigation panel;
replacing it preserves controller and projector contracts.

Implementation verification: PASS. The projector contract test covers streaming
draft replacement and tool-call reconciliation. Vite builds the investigation
chat with its existing sanitized Markdown dependency. Static import review
found no tool-name routing and no chat-to-map dependency.

Bottom Dock resizing: PASS. The resizer owns one shell CSS value and a narrow
map viewport callback; it neither reads dock placement nor imports panel or
map implementation.

Session/connector feedback revision: PASS. Binding remains uniquely owned by
the session run profile. Duplicate validation is defense in depth: browser
preflight improves feedback, while durable stores enforce the invariant under
multiple clients. Local permission feedback owns presentation only and does
not change profile or request ownership.

Shapefile projection compatibility: PASS. CRS inference is constrained to an
unambiguous Web Mercator extent and lives in the ingestion adapter; map-core
only supplies a backward-compatible reader for already-created display files.
No persistence or UI module becomes a CRS authority.
