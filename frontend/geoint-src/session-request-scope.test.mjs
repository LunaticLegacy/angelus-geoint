import assert from "node:assert/strict";
import { createSessionRequestScope } from "./session-request-scope.js";
import { createWorkspaceState } from "./state.js";

let selected = "session-a";
const state = { sessionId: () => selected, selectSession: (value) => { selected = value || ""; } };
const scope = createSessionRequestScope(state);

const firstContext = scope.capture("context");
const secondContext = scope.capture("context");
assert.equal(scope.isCurrent(firstContext), false, "newer context refresh supersedes older response");
assert.equal(scope.isCurrent(secondContext), true);

scope.select("session-b");
assert.equal(scope.isCurrent(secondContext), false, "a response cannot survive a session switch");
const sessionB = scope.capture("map");
scope.select("session-a");
assert.equal(scope.isCurrent(sessionB), false, "A -> B -> A still invalidates B work");

const directA = scope.capture("profile");
selected = "session-b"; // Defensive detection for legacy callers that have not migrated yet.
assert.equal(scope.isCurrent(directA), false);

const storage = new Map();
globalThis.localStorage = { getItem: (key) => storage.get(key) || null, setItem: (key, value) => storage.set(key, value), removeItem: (key) => storage.delete(key) };
const workspace = createWorkspaceState();
workspace.setSessions([{ id: "session-a", name: "A" }]);
assert.deepEqual(workspace.sessions(), [{ id: "session-a", name: "A" }], "session preflight can read the cached session list");
console.log("Session request scope checks passed.");
