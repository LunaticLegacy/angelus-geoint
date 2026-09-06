# Boundaries

## `trace-view`

- **Semantic role:** bounded, incremental browser projection of runtime trace
  records.
- **Owns:** in-memory trace record buffer, render generation and frame
  scheduling.
- **Public surface:** `append(value)`, `clear()`, `setActive(active)`.
- **Allowed dependencies:** DOM only.
- **Forbidden dependencies:** API client, Agent controller, dock internals,
  workspace state, map runtime.
- **Must not know:** SSE payload schema, session IDs, run lifecycle, server
  persistence.
- **Replaceability:** another virtualized trace renderer can preserve the
  three-method surface.

## `agent-controller`

- **Semantic role:** run transport and SSE lifecycle.
- **Change:** emits raw trace text through injected `trace.append`; it no
  longer writes a DOM node.
- **Must not know:** buffering, panel visibility or trace markup.

## `dock-layout`

- **Semantic role:** panel location and active tab persistence.
- **Change:** invokes an injected `onActivePanelsChange(activeIds)` callback
  after render. It never imports or special-cases Trace.

## `workspace composition` (`main.js`)

- **Semantic role:** wires independent module contracts.
- **Owns:** mapping the active panel set to `trace-view.setActive`, and
  status-bar wording for completed session creation.
- **Must not own:** trace buffering, session creation, dock layout state.

## `workspace-ui` and stylesheet

- **Semantic role:** stateless action-button projection and visual hierarchy.
- **Owns:** `data-action` markup and appearance only.
- **Must not know:** API paths, domain state, or session filesystem paths.
