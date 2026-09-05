import assert from "node:assert/strict";
import { createSessionRequestScope } from "./session-request-scope.js";

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
console.log("Session request scope checks passed.");
