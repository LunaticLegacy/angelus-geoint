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
assert.deepEqual(queued, { id: queued.id, type: "steer_queued", agent: "all", content: "优先核验降水异常", targets: ["coordinator", "worker-a"] });

projector.applyEvent({ type: "agent:steer_applied", agent: "coordinator", data: { round: 2, messages: ["优先核验降水异常"] } });
assert.deepEqual(latest.nodes.at(-1), { id: latest.nodes.at(-1).id, type: "steer_applied", agent: "coordinator", round: 2, content: "优先核验降水异常" });

projector.hydrate([{ role: "assistant", timeline: 201, content: "newest" }]);
projector.prependHistory([{ role: "user", timeline: 1, content: "oldest" }]);
assert.deepEqual(latest.nodes.filter((node) => node.type === "user_message").map((node) => node.content), ["oldest"]);
assert.equal(latest.nodes.at(-1).content, "newest");
