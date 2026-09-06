# Semantics

`EvidenceStore` is the canonical owner of statements that can be traced to session-bound source assets, a derivation result, and/or curated knowledge. It persists under the GEOINT runtime state root. A derivation record is idempotent per `(session_id, derivation_job_id)`.

An Agent claim requires at least one provenance reference: source assets, a derivation, or knowledge. Geometry is optional and is only a visualization aid; it does not alter the claim.

`DroughtKnowledgeBase` owns operational guidance only. Its bundled documents are immutable at runtime, carry source metadata, and do not make live drought findings. Search is deterministic lexical matching.

The evidence UI and map evidence layer consume API representations. Their lifecycle is refresh/replace; neither persists canonical evidence. Failure to load evidence leaves the map and investigation usable and displays an empty/error state.

The current Agent context is bounded working memory, not a chat transcript.
`ConsoleProjectionService` reconstructs the investigation transcript from every
immutable execution journal retained by the session.
