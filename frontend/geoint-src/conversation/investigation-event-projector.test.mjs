import assert from "node:assert/strict";
import { createInvestigationEventProjector } from "./investigation-event-projector.js";

const projector = createInvestigationEventProjector();
let latest = null;
projector.subscribe((snapshot) => { latest = snapshot; });
projector.reset("session-a");
projector.setContextSummary({ stats: { messages: 12, characters: 3456 } });
assert.deepEqual(latest.nodes[0], { id: "context:session-a", type: "context_summary", messages: 12, characters: 3456 });
projector.beginUserTurn("检查干旱证据");
projector.applyEvent({ type: "agent:stream_delta", agent: "coordinator", data: { round: 1, channel: "content", delta: "正在" } });
projector.applyEvent({ type: "agent:stream_delta", agent: "coordinator", data: { round: 1, channel: "content", delta: "分析。" } });
assert.equal(latest.nodes.filter((node) => node.type === "assistant_draft").length, 1);
assert.equal(latest.nodes.at(-1).content, "正在分析。");

projector.applyEvent({ type: "agent:tools_requested", agent: "coordinator", data: { round: 1, tool_calls: [{ call_id: "c1", name: "any_tool", args: { area: "陕西" } }] } });
projector.applyEvent({ type: "agent:tools_completed", agent: "coordinator", data: { round: 1, tool_calls: [{ call_id: "c1", name: "any_tool", args: { area: "陕西" }, ok: true, result: { records: 2 }, duration_ms: 123 }] } });
const batch = latest.nodes.find((node) => node.type === "tool_batch");
assert.equal(batch.tools[0].status, "success");
assert.deepEqual(batch.tools[0].output, { records: 2 });

projector.applyEvent({ type: "agent:round", agent: "coordinator", data: { round: 1, assistant_content: "**结论**：存在干旱信号。", reasoning_content: "核对数据。" } });
assert.equal(latest.nodes.filter((node) => node.type === "assistant_draft").length, 0);
assert.equal(latest.nodes.filter((node) => node.type === "assistant_message").at(-1).content, "**结论**：存在干旱信号。");
assert.equal(latest.nodes.filter((node) => node.type === "tool_batch").length, 1);

projector.applyEvent({ type: "agent:control", agent: "all", message: "优先核验降水异常", data: { action: "steer", target_agents: ["coordinator", "worker-a"] } });
const queued = latest.nodes.at(-1);
assert.deepEqual(queued, { id: queued.id, type: "steer_queued", agent: "all", content: "优先核验降水异常", targets: ["coordinator", "worker-a"], applied: [] });

projector.applyEvent({ type: "agent:steer_applied", agent: "coordinator", data: { round: 2, messages: ["优先核验降水异常"] } });
assert.deepEqual(latest.nodes.at(-1), { id: latest.nodes.at(-1).id, type: "steer_applied", agent: "coordinator", round: 2, content: "优先核验降水异常", targets: [], applied: ["coordinator"] });

projector.hydrate([{ role: "assistant", timeline: 201, content: "newest" }]);
projector.prependHistory([{ role: "user", timeline: 1, content: "oldest" }]);
assert.deepEqual(latest.nodes.filter((node) => node.type === "user_message").map((node) => node.content), ["oldest"]);
assert.equal(latest.nodes.at(-1).content, "newest");

// ---- Appended coverage: steering cards must be idempotent, mergeable and hydratable ----
projector.reset("session-steer");
assert.equal(latest.nodes.length, 0);

const steerEvent = () => ({ type: "agent:control", agent: "all", message: "优先核验降水异常", data: { action: "steer", agent_id: "all", target_agents: ["coordinator", "worker-a"], steer_id: "steer-1" } });
projector.applyEvent(steerEvent());
projector.applyEvent(steerEvent());
assert.equal(latest.nodes.filter((node) => node.type === "steer_queued").length, 1);
assert.deepEqual(latest.nodes.at(-1), { id: "steer:steer-1", type: "steer_queued", agent: "all", content: "优先核验降水异常", targets: ["coordinator", "worker-a"], applied: [] });

projector.applyEvent({ type: "agent:steer_applied", agent: "worker-a", data: { round: 3, messages: ["优先核验降水异常"], steer_ids: ["steer-1"] } });
assert.equal(latest.nodes.length, 1);
assert.deepEqual(latest.nodes[0], { id: "steer:steer-1", type: "steer_applied", agent: "worker-a", round: 3, content: "优先核验降水异常", targets: ["coordinator", "worker-a"], applied: ["worker-a"] });
// A second agent landing on the same steer accumulates instead of adding a card.
projector.applyEvent({ type: "agent:steer_applied", agent: "coordinator", data: { round: 3, messages: ["优先核验降水异常"], steer_ids: ["steer-1"] } });
assert.equal(latest.nodes.length, 1);
assert.deepEqual(latest.nodes[0].applied, ["worker-a", "coordinator"]);
// Replaying the control record must not downgrade a card that already landed.
projector.applyEvent(steerEvent());
assert.equal(latest.nodes.length, 1);
assert.equal(latest.nodes[0].type, "steer_applied");
assert.deepEqual(latest.nodes[0].applied, ["worker-a", "coordinator"]);

// Legacy journal records carry no steer_id: the fallback key must still be stable.
projector.reset("session-legacy");
const legacyEvent = () => ({ type: "agent:control", agent: "all", message: "补充范围", data: { action: "steer", target_agents: ["worker-b", "coordinator"] } });
projector.applyEvent(legacyEvent());
const legacyId = latest.nodes.at(-1).id;
assert.match(legacyId, /^steer:legacy:[0-9a-f]{8}$/);
projector.applyEvent(legacyEvent());
assert.equal(latest.nodes.length, 1);
// The digest sorts targets, so a reordered broadcast list is the same steer.
projector.applyEvent({ type: "agent:control", agent: "all", message: "补充范围", data: { action: "steer", target_agents: ["coordinator", "worker-b"] } });
assert.equal(latest.nodes.length, 1);
assert.equal(latest.nodes[0].id, legacyId);

// Hydration backfills durable steering, and the SSE replay folds onto the same ids.
projector.reset("session-hydrate");
projector.hydrate([{ role: "user", timeline: 1, content: "检查干旱" }]);
projector.hydrateSteering([
  { id: "steer-b", text: "先核验降水", scope: "all", recipients: ["coordinator"], applied_agents: [], submitted_at: 200 },
  { id: "steer-a", text: "补充范围", scope: "worker-a", recipients: ["worker-a"], applied_agents: ["worker-a"], submitted_at: 100 },
]);
assert.deepEqual(latest.nodes.map((node) => node.type), ["user_message", "steer_applied", "steer_queued"]);
assert.deepEqual(latest.nodes[1], { id: "steer:steer-a", type: "steer_applied", agent: "worker-a", round: "", content: "补充范围", targets: ["worker-a"], applied: ["worker-a"] });
assert.deepEqual(latest.nodes[2], { id: "steer:steer-b", type: "steer_queued", agent: "all", round: "", content: "先核验降水", targets: ["coordinator"], applied: [] });
projector.applyEvent({ type: "agent:control", agent: "all", message: "先核验降水", data: { action: "steer", target_agents: ["coordinator"], steer_id: "steer-b" } });
assert.equal(latest.nodes.length, 3);
projector.applyEvent({ type: "agent:steer_applied", agent: "coordinator", data: { round: 4, messages: ["先核验降水"], steer_ids: ["steer-b"] } });
assert.equal(latest.nodes.length, 3);
assert.equal(latest.nodes[2].type, "steer_applied");
assert.deepEqual(latest.nodes[2].applied, ["coordinator"]);

console.log("Investigation projector checks passed.");
