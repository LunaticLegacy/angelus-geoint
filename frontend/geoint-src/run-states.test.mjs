import assert from "node:assert/strict";
import { ACTIVE_RUN_STATES, isActiveRun, isSteerable } from "./run-states.js";

// These three states mirror the admission check in execution_service: steering
// outside them answers 409, so a drift here re-opens the window the UI must avoid.
assert.deepEqual([...ACTIVE_RUN_STATES].sort(), ["force_stopping", "running", "stopping"]);

const steerable = [["running", true], ["RUNNING", true], ["  Running  ", true], ["stopping", true], ["\tForce_Stopping\n", true]];
const notSteerable = [["completed", false], ["failed", false], ["stopped", false], ["interrupted", false], ["starting", false], ["idle", false], ["", false], ["   ", false], ["runnning", false], ["stop", false], ["unknown", false]];
for (const [value, expected] of [...steerable, ...notSteerable]) {
  assert.equal(isActiveRun(value), expected, `isActiveRun(${JSON.stringify(value)})`);
  assert.equal(isSteerable(value), expected, `isSteerable(${JSON.stringify(value)})`);
}

// Missing or non-string transport values must never be treated as live.
for (const value of [null, undefined, 0, 1, true, false, {}, [], { state: "running" }]) {
  assert.equal(isActiveRun(value), false, `isActiveRun(${JSON.stringify(value)})`);
  assert.equal(isSteerable(value), false, `isSteerable(${JSON.stringify(value)})`);
}

console.log("Run state admission checks passed.");
