import assert from "node:assert/strict";
import { createAgent, isDirectMapMutation, isEvidenceMutation } from "./agent-controller.js";

assert.equal(isDirectMapMutation({ type: "agent:tools_completed", data: { tool_calls: [{ name: "geoint_manage_map_layers", ok: true }] } }), true);
assert.equal(isDirectMapMutation({ type: "agent:tools_requested", data: { tool_calls: [{ name: "geoint_manage_map_layers" }] } }), false);
assert.equal(isDirectMapMutation({ type: "agent:tools_completed", data: { tool_calls: [{ name: "geoint_manage_map_layers", ok: false }] } }), false);
assert.equal(isEvidenceMutation({ type: "agent:tools_completed", data: { tool_calls: [{ name: "geoint_record_evidence", ok: true }] } }), true);
assert.equal(isEvidenceMutation({ type: "agent:tools_requested", data: { tool_calls: [{ name: "geoint_read_result" }] } }), false);

let request = null;
// Real AgentControlReceipt shape: session_id / execution_id / agent_id / action /
// target_agents / queued / steer_id (angelus/geoint/.../agent_control.py).
const receiptBody = { session_id: "session_demo", execution_id: "exec_1", agent_id: "all", action: "steer", target_agents: ["coordinator", "worker-a"], queued: true, steer_id: "steer-42" };
let reply = () => ({ ok: true, status: 200, statusText: "OK", text: async () => JSON.stringify(receiptBody) });
globalThis.fetch = async (url, options) => { request = { url, options }; return reply(); };

const projected = [];
const projector = { setRunState() {}, reset() {}, hydrate() {}, hydrateSteering() {}, setContextSummary() {}, beginUserTurn() {}, applyEvent(event) { projected.push(event); } };
const agent = createAgent({
  state: { sessionId: () => "session_demo" },
  projector,
  requestScope: { capture: () => ({ sessionId: "session_demo" }), isCurrent: () => true },
});
const receipt = await agent.steer("优先检查降水异常");
assert.equal(request.url, "/api/runs/session_demo/control");
assert.deepEqual(JSON.parse(request.options.body), { agent_id: "all", action: "steer", message: "优先检查降水异常" });
assert.equal(receipt.action, "steer");
assert.equal(request.options.method, "POST");
assert.ok(Object.keys(request.options.headers || {}).some((key) => key.toLowerCase() === "content-type"), "steer must declare a JSON content-type");
assert.deepEqual(receipt.target_agents, ["coordinator", "worker-a"]);
assert.equal(receipt.steer_id, "steer-42");
assert.equal(receipt.queued, true);

// The receipt is consumed immediately, so the queued card is visible before the
// SSE replay of the same steer_id arrives to fold onto it.
assert.deepEqual(projected, [{ type: "agent:control", agent: "operator", message: "优先检查降水异常", data: { action: "steer", agent_id: "all", target_agents: ["coordinator", "worker-a"], steer_id: "steer-42" } }]);

// 409: the run left the steerable window, so the operator gets the outcome and no card.
projected.length = 0;
reply = () => ({ ok: false, status: 409, statusText: "Conflict", text: async () => JSON.stringify({ detail: "Session has no active Agent control boundary" }) });
await assert.rejects(() => agent.steer("再补一条引导"), (error) => { assert.equal(error.message, "调查已不在可引导状态（可能已结束或正在切换），本次引导未发送。"); return true; });
assert.deepEqual(projected, []);

// Unrelated transport failures keep their own message.
reply = () => ({ ok: false, status: 500, statusText: "Server Error", text: async () => JSON.stringify({ detail: "后端拒绝了请求" }) });
await assert.rejects(() => agent.steer("再补一条引导"), /后端拒绝了请求/);
assert.deepEqual(projected, []);

// A superseded request must not paint a card into the session the operator left.
reply = () => ({ ok: true, status: 200, statusText: "OK", text: async () => JSON.stringify({ action: "steer", target_agents: ["coordinator"], queued: true, steer_id: "steer-stale" }) });
const staleAgent = createAgent({ state: { sessionId: () => "session_old" }, projector, requestScope: { capture: () => ({ sessionId: "session_old" }), isCurrent: () => false } });
assert.equal(await staleAgent.steer("过期引导"), null);
assert.deepEqual(projected, []);
console.log("Agent steering transport checks passed.");
