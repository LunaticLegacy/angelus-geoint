# Implementation verification

PASS

## Session and connector feedback revision

PASS. `ConnectorStore` and `SessionService` reject trimmed/casefolded duplicate
labels; their regression tests pass. The frontend builds a binding display only
from the effective session profile and safe connector metadata. Permission
saves retain panel-local result text, so a later generic workspace refresh does
not masquerade as a successful permission save. `npm run test:geoint`,
`npm run build:geoint`, and `.venv/bin/python -m unittest
tests.test_settings_service tests.test_workspace_service tests.test_geoint_shapefile`
pass. Full Tauri packaging remains environment-blocked because this virtual
environment lacks PyInstaller.

Shapefile projection compatibility: PASS. Tests cover missing-PRJ metre-scale
coordinates converting into longitude/latitude and legacy vector projection
selection; the complete GEOINT frontend suite and Vite build pass.

- Vite production build succeeds.
- `workspace-ui` imports no API client; all HTTP imports are confined to
  controllers or map-core.
- `map-core` imports no controller or Angelus state module.
- The restored controls use unchanged `/api/sessions`, `/api/runs`,
  `/api/connectors`, run-profile and context routes.
- The template still contains the stable control IDs; no Leaflet or CDN script
  is mounted.
- The Vite build succeeds after the shell revision; the old panel-local session
  selector is removed at runtime and the header selector is canonical.
- The desktop shell renders the map above the workbench, with a left context
  rail. `layers` is supplied by the GEOINT navigation catalogue and has a
  single component host; its component remains map-engine independent.
- The map-centered revision removes the splitter. The chat composer delegates
  send actions and Cmd/Ctrl+Enter to the existing Agent controller.
- Dock-layout build passes: panel tabs support cross-zone docking and insertion
  before another tab; the layout persists locally while MapViewport is never a
  draggable panel.
- Map-edge resizer build passes: left/right splitters persist bounded shell
  widths, support keyboard adjustment, and invoke only the injected map-size
  callback after a drag.
# Basemap extension — 2026-09-05

Source manager revision: Architecture PASS; automated implementation checks PASS. Added independently replaceable structured source-editor and panel→editor edge; backend update preserves identity and selection. 14 GEOINT tests / 23 subtests, JS suite and production build pass. Conditional credential view, independent browse/apply, component-width responsive CSS delivered. Live provider/visual browser validation remains outstanding. No generic token proxy, GCJ-02/BD09 conversion or arbitrary WMTS support claimed.

Architecture: PASS. Implementation: PASS (automated checks; live-provider and visual checks remain).

- Modules: basemap-store, tianditu-tiles, basemap-api, basemap-map, basemap-controller, basemap-panel. Controller uses injected map/view contracts; component has no network or OpenLayers dependency. Store has no UI/core-session dependency. Approved edges match architecture.yaml; no cycles or session API changes.
- 13 GEOINT pytest tests and 19 validation subtests passed, including 5 new basemap test cases. In-process TestClient required sandbox escalation (thread portal blocked inside sandbox); upstream requests mocked.
- `npm run test:geoint` passed: existing conversation projection plus map adapter/controller preservation, labels, attribution escaping, coordinate bounds, error deduplication, and mutation order.
- `npm run build:geoint` passed; existing bundle-size warning remains. Generated static assets rebuilt; map stylesheet version updated.
- Delivered OSM default, paired TianDiTu presets with write-only Key, validated public HTTPS XYZ import/delete, persisted workspace selection, dockable component and coordinate positioning.
- Remaining checks: no user TianDiTu Key supplied, so live-provider authorization/network not tested; no browser visual automation available. Baidu/GCJ-02 and arbitrary WMTS not implemented. Configuration file permissions restrict access but do not encrypt the Key.
