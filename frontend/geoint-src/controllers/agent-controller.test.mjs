import assert from "node:assert/strict";
import { createAgent, isDirectMapMutation } from "./agent-controller.js";

assert.equal(isDirectMapMutation({ type: "agent:tools_completed", data: { tool_calls: [{ name: "geoint_manage_map_layers", ok: true }] } }), true);
assert.equal(isDirectMapMutation({ type: "agent:tools_requested", data: { tool_calls: [{ name: "geoint_manage_map_layers" }] } }), false);
assert.equal(isDirectMapMutation({ type: "agent:tools_completed", data: { tool_calls: [{ name: "geoint_manage_map_layers", ok: false }] } }), false);

let request;
globalThis.fetch = async (url, options) => {
  request = { url, options };
  return { ok: true, status: 200, statusText: "OK", text: async () => JSON.stringify({ action: "steer", targets: ["coordinator"] }) };
};

const agent = createAgent({
  state: { sessionId: () => "session_demo" },
  projector: { setRunState() {}, reset() {}, hydrate() {}, setContextSummary() {}, applyEvent() {}, beginUserTurn() {} },
  requestScope: { capture: () => ({ sessionId: "session_demo" }), isCurrent: () => true },
});
const receipt = await agent.steer("优先检查降水异常");
assert.equal(request.url, "/api/runs/session_demo/control");
assert.deepEqual(JSON.parse(request.options.body), { agent_id: "all", action: "steer", message: "优先检查降水异常" });
assert.equal(receipt.action, "steer");
console.log("Agent steering transport checks passed.");
