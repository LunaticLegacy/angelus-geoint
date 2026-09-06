# Architecture validation

PASS

- `trace-view` has exclusive ownership of trace buffer and scheduling; the
  Agent controller owns only SSE transport.
- Dock layout reports generic active IDs and does not acquire trace knowledge.
- Composition is the only place that joins generic callbacks to a concrete
  trace panel.
- The feedback uses the pre-existing status bar; no global notification state
  or API contract is introduced.
- CSS selectors use `data-action` and cannot mutate domain state.
- Every changed module can be replaced behind its stated contract and no new
  dependency cycle is introduced.
