# Problem

Restore Angelus controls lost during the OpenLayers entry-point migration.
The existing Angelus HTTP contracts (`/api/sessions`, `/api/runs`, connectors,
run profiles and context routes) are protected and must not change.  The
frontend must retain local OpenLayers and must not reintroduce Leaflet/CDN.

Non-goals: changing Angelus backend ownership, adding new server routes, or
restoring the historic monolithic browser controller.  Risks are stale UI
state, accidental credential display, and coupling UI controls to OpenLayers.

## Layout revision

Redesign the workspace shell around the selected Angelus session. The selection
is currently buried in the investigation tab even though connector, context and
run controls require it. Replace the green system with cool slate surfaces and
blue-violet interaction accents while preserving element IDs and REST contracts.

## Workspace composition revision

The permanent right rail competes with the map and keeps low-frequency setup
information visible. Move the workbench below the map on desktop, retain a
narrow left context rail, and make layer controls a first-class navigable
workbench component. The GEOINT UI tab catalogue may add a `layers` entry; no
Angelus core route or data contract changes.

## Density and resize revision

Connector and session forms waste horizontal capacity in the lower workbench.
Use responsive form grids while retaining their labels and IDs. Add a shell-only
resizer between map and workbench, persist its height locally, and notify the
map runtime to recalculate its viewport after dragging.

## Map-centered revision

The map must remain the central primary canvas. Replace the top-map/bottom-
workbench split with left navigation, center map, and right investigation
workbench. Retire the map-height resizer because it belongs to the superseded
vertical composition. Keep layer controls inside the right-side navigation.

## Dock layout phase 1

Implement draggable panel tabs across left, right and bottom dock zones,
ordering within a zone, local persistence and reset. MapViewport remains fixed
in the center. Floating/resizable windows are an explicit phase-2 non-goal.

## Map-edge resizing

Add horizontal splitters at the left and right edges of the fixed central map.
They own only shell widths (`--left-width`, `--right-width`) and persist
bounded pixel values locally; the bottom dock follows the central width.

## Investigation chat revision

Replace the static investigation summary with a durable chat timeline.  It
must consume the existing session-message projection and run SSE feed without
changing Angelus API contracts.  Markdown stays sanitized.  Tool output is
rendered from a tool-agnostic envelope, with names retained only as optional
audit metadata; no GEOINT or tool-name-specific renderer is permitted.

## Session and connector feedback revision

Make the saved run profile visibly authoritative in the workbench. A session
must show the connector identified by its effective `connector_id`; connector
forms may preflight duplicate labels but durable stores remain the final
authority and reject normalized duplicate names. Permission saves need a
panel-local result that is not overwritten by unrelated workspace refresh
feedback. No new endpoint, persistence store, or credential-read path is
introduced.
