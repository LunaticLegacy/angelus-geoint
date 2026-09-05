# Semantics

`workspace-state` is the sole in-memory owner of selected session and cached
profile/connector metadata.  API responses replace state; no controller
mutates another controller's private state.  `agent-controller` closes a prior
EventSource before opening another and treats stream failure as terminal UI
reconciliation.  Connector API keys are DOM input only and cleared after POST.
Map state is owned exclusively by `map-core`; Angelus controls consume session
IDs and never access OpenLayers objects.

`investigation-event-projector` is the canonical owner of transient chat
nodes. It replaces a streaming draft with the durable `agent:round` node,
merges tool lifecycle records by `round` and `call_id`, and emits immutable
snapshots to subscribers. It receives ordinary JSON messages/events only.
`investigation-chat` owns no conversation state: it redraws projector
snapshots, safely renders Markdown, and preserves reading position unless the
reader follows the latest item. `tool-result-renderer` accepts only normalized
tool envelopes and recursively redacts sensitive keys before creating DOM.
