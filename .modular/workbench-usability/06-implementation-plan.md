# Implementation plan

## T1 — Trace projection

- **Module:** `trace-view`
- **Goal:** render bounded trace records incrementally.
- **Files allowed:** `frontend/geoint-src/components/trace-view.js`, its test.
- **Forbidden:** API, backend, map modules.
- **Acceptance:** a large buffer yields between frames; inactive Trace does not
  synchronously replace a large DOM node.

## T2 — Transport and dock integration

- **Module:** agent controller, dock layout, composition.
- **Files allowed:** `controllers/agent-controller.js`, `dock-layout.js`,
  `main.js`, narrow tests.
- **Acceptance:** SSE writes through `trace.append`; selecting/moving Trace
  activates only its view; clear uses the view contract.

## T3 — Non-modal feedback and action hierarchy

- **Module:** workspace composition/UI/style.
- **Files allowed:** `main.js`, `workspace-ui.js`, `geoint.css`, template only
  if a static explanatory label is needed.
- **Acceptance:** successful session creation reports managed workspace
  readiness in the status bar; action intent/API contracts remain unchanged;
  session and connector strips have distinct primary/secondary/destructive
  hierarchy.

## T4 — Verify

- **Tests:** component contract test, existing GEOINT JS suite, Vite build.
- **Architecture:** static import review confirms no controller-to-DOM trace
  write and no dock-to-trace import.
