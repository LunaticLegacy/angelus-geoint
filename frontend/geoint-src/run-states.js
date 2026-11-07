/**
 * Run states that still own a live Agent control boundary.
 *
 * This set mirrors the admission check in ``execution_service``: steering a run
 * outside it is answered with 409, so the UI must never promise steering there.
 * It lives in one module because the controller, the projector and the chat
 * panel each need the same answer — three copies drift apart silently.
 */
export const ACTIVE_RUN_STATES = new Set(["running", "stopping", "force_stopping"]);

/** Normalise transport state casing/whitespace once so every caller agrees. */
export const isActiveRun = (state) => ACTIVE_RUN_STATES.has(String(state ?? "").trim().toLowerCase());

/** Steering admission currently equals the active boundary, kept named apart for intent. */
export const isSteerable = (state) => isActiveRun(state);
