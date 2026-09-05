# Implementation plan

Source manager revision: PASS (acyclic, editor draft distinct from active selection). Scope: existing basemap backend/store/router, frontend panel/controller/main, new source-editor component, scoped CSS, related tests/docs and Vite output. Order: update validated contract/store/API; component editor and responsive manager; integration, tests, build. Forbidden: Angelus core and session APIs. Acceptance: create/edit custom XYZ, explicit CRS validation, conditional credentials, independent browse/apply, two-column wide and one-column narrow layout.

## Basemap extension — validated PASS before execution

1. Store/contracts: `angelus/geoint/basemaps.py`; strict validation, atomic restricted persistence, safe public snapshots; test in `tests/test_geoint_basemaps.py` without core.
2. Tile transport + API: `angelus/geoint/tianditu_tiles.py`, `angelus/api/geoint_basemaps.py`, composition `angelus/api/__init__.py`, tab catalogue `angelus/api/geoint.py`; verify fixed host, bounded responses and sanitized errors with mocks.
3. Map adapter: `frontend/geoint-src/basemap-map.js`, integrate `map.js`; preserve view and geoint layers.
4. Component/controller: new `components/basemap-panel.js`, `controllers/basemap-controller.js`; compose in `main.js`, register default in `components/dock-layout.js`; component CSS imported into Vite. Test via production build and independent JS tests where practical.
5. Verify and document: test files, `docs/basemaps.md`, `.modular/07-implementation-verification.md`, generated Vite assets allowed. Angelus core APIs/session state and all unrelated files forbidden.

Scope clarification before final integration: `package.json` may register the new JS test; `frontend/templates/geoint.html` may remove the nonfunctional satellite placeholder and version the generated CSS. No new dependency edge. PASS.

Adversarial review: ownership unique; directed graph acyclic; UI receives snapshots only; fixed-host fetch cannot consume user URLs; failures remain local to feature. All modules can be replaced at their listed public boundaries. Architecture status: PASS.

1. `workspace-state` — add state and DOM/action rendering modules; scope
   `frontend/geoint-src/{state,dom,components}`; verify no fetch imports in UI.
2. Controllers — add session, connector, context and agent controllers under
   `frontend/geoint-src/controllers`; verify existing request paths/payloads.
3. Composition — replace `main.js`, wire intents and selection changes; scope
   `frontend/geoint-src/main.js`; verify all server-declared controls bind.
4. Build — run Vite and inspect bundle for no Leaflet/CDN references.

Completed: 1–3.  `main.js` composes controllers only; it does not contain
session/profile/connector transport logic.

5. `workspace-shell` — move session selection into the persistent header and
   establish responsive slate/blue-violet tokens; scope `geoint.html` and
   `geoint.css`; acceptance: the header selector becomes canonical at runtime
   and mobile avoids three competing columns. Completed.

6. `workspace-shell` and `layer-panel` — convert the desktop shell to a left
   context rail, map canvas and lower workbench; add the layers navigation
   entry and relocate the component host. Scope `geoint.html`, `geoint.css`,
   `api/geoint.py`; acceptance: the layer panel has one host under its tab and
   the right rail no longer constrains map width.

7. `workbench-resizer` and shell forms — add bounded pointer resizing and
   responsive session/connector grids; scope `geoint-src/components`,
   `geoint-src/main.js`, `geoint.html`, `geoint.css`; tests: Vite build and
   static dependency checks.

8. `workspace-shell` — restore a three-column, map-centered desktop shell;
   remove the retired resizer module and make the investigation panel a
   chat-shaped workbench. Scope `geoint.css`, `main.js`, `components`; verify
   the map has the central column and no resizer module remains.

9. `dock-layout` — create persistent left/right/bottom tab groups and native
   drag/drop, mount existing panels into those groups, and add reset. Scope
   `components/dock-layout.js`, `main.js`, `geoint.css`. Completed: drops alter
  only zone/order metadata; the central map remains mounted.

10. `investigation-event-projector` — normalize durable history plus the
    existing run events into immutable conversation snapshots; scope
    `geoint-src/conversation`; acceptance: a final round replaces its stream
    draft and tool batches merge by call ID.

11. `tool-result-renderer` and `investigation-chat` — render generic safe
    tool cards and a Markdown conversation timeline; scope
    `geoint-src/components`, `geoint.css`; acceptance: no renderer branches
    on a tool name and all raw model Markdown remains sanitized.

12. `agent-controller` and composition — pass parsed SSE events to the
    projector, hydrate history on session changes, and mount the chat; scope
    `controllers/agent-controller.js`, `main.js`; tests: Vite build and
    projector contract checks.

13. `bottom-dock-resizer` — add a bounded, persistent horizontal splitter for
    the bottom Dock; scope `geoint-src/components`, `main.js`, `geoint.css`;
    acceptance: it changes only `--bottom-height` and refreshes the map.
