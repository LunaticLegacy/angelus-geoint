# Problem — workbench usability pass

## Goal

Make the existing session-first GEOINT workbench understandable without
changing Angelus session, run, connector, context, or GEOINT HTTP contracts.

- A newly created session must acknowledge that its managed workspace is ready
  through the existing status bar, never a modal or browser alert.
- Session and connector action strips must express one primary action and keep
  destructive/secondary actions visually subordinate.
- Opening the Trace panel must not synchronously lay out an unbounded text
  node. Recent trace records must appear incrementally on animation frames.

## Non-goals

- No new API route, no server-side trace pagination, and no alteration to
  Angelus durable run/event semantics.
- No change to the default managed directory contract:
  `.angelus-state/sessions/<session_id>/workspace`.
- No redesign of the dock model or map runtime.

## Constraints

- `SessionService` remains the sole owner of workspace creation.
- `workspace-state` remains the sole owner of selected-session UI state.
- The status bar is the one non-modal global feedback surface.
- Trace records are a browser diagnostic projection, not durable context.
- Existing REST request/response payloads are protected.

## Risks

- Replacing the trace DOM from an event handler can still block the frame.
- A generic action renderer must not gain session-domain state.
- A UI message must not reveal a host filesystem path.
