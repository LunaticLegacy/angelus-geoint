const terminalStates = new Set(["completed", "failed", "stopped", "interrupted"]);

const text = (value) => String(value ?? "");
const object = (value) => value && typeof value === "object" && !Array.isArray(value) ? value : {};
const callsFrom = (data) => Array.isArray(data?.tool_calls) ? data.tool_calls : [];
const keyFor = (agent, round) => `${agent || "coordinator"}:${round ?? ""}`;

function toolCall(call, status = "running") {
  return {
    call_id: text(call?.call_id || call?.id || ""),
    tool_name: text(call?.name || "tool"),
    status: call?.ok === false ? "error" : status,
    input: call?.args ?? call?.arguments ?? {},
    output: call?.result ?? call?.output,
    duration_ms: Number.isFinite(Number(call?.duration_ms)) ? Number(call.duration_ms) : null,
  };
}

function cloneNodes(nodes) {
  return nodes.map((node) => Array.isArray(node.tools) ? { ...node, tools: node.tools.map((tool) => ({ ...tool })) } : { ...node });
}

/** Project durable history and transient Agent events into tool-neutral chat nodes. */
export function createInvestigationEventProjector() {
  let nodes = [], listeners = new Set(), sessionId = "", runState = "idle";
  const drafts = new Map(), batches = new Map();

  function notify() {
    const snapshot = { session_id: sessionId, run_state: runState, nodes: cloneNodes(nodes) };
    listeners.forEach((listener) => listener(snapshot));
  }
  function append(node) { nodes = [...nodes, node]; return node; }
  function removeById(id) { nodes = nodes.filter((node) => node.id !== id); }
  function findBatch(agent, round) { return batches.get(keyFor(agent, round)); }

  function ensureBatch(agent, round, calls) {
    const key = keyFor(agent, round), existing = findBatch(agent, round);
    if (existing) {
      const current = new Map(existing.tools.map((call) => [call.call_id, call]));
      calls.forEach((call, index) => {
        const next = toolCall(call, "running");
        const id = next.call_id || `call_${index}`;
        current.set(id, { ...(current.get(id) || {}), ...next, call_id: id });
      });
      existing.tools = [...current.values()];
      return existing;
    }
    const batch = append({ id: `tools:${key}:${nodes.length}`, type: "tool_batch", agent, round, tools: calls.map((call, index) => ({ ...toolCall(call), call_id: text(call?.call_id || `call_${index}`) })) });
    batches.set(key, batch);
    return batch;
  }

  function updateTools(agent, round, calls) {
    const batch = ensureBatch(agent, round, calls);
    const next = new Map(batch.tools.map((call) => [call.call_id, call]));
    calls.forEach((call, index) => {
      const value = toolCall(call, call?.ok === false ? "error" : "success");
      const id = value.call_id || `call_${index}`;
      next.set(id, { ...(next.get(id) || {}), ...value, call_id: id });
    });
    batch.tools = [...next.values()];
  }

  function reset(nextSessionId = "") { sessionId = nextSessionId; runState = "idle"; nodes = []; drafts.clear(); batches.clear(); notify(); }
  function hydrate(messages = []) {
    nodes = (Array.isArray(messages) ? messages : []).flatMap((message, index) => {
      const role = text(message?.role || "assistant");
      const base = { id: `history:${message?.timeline ?? index}`, type: role === "user" ? "user_message" : "assistant_message", role, content: text(message?.content), reasoning: text(message?.reasoning), created_at: message?.created_at ?? null, usage: message?.usage ?? null, duration_ms: message?.round_duration_ms ?? message?.model_duration_ms ?? null };
      const tools = Array.isArray(message?.tools) ? message.tools : [];
      return tools.length ? [base, { id: `history-tools:${message?.timeline ?? index}`, type: "tool_batch", agent: "coordinator", round: message?.timeline ?? index, tools: tools.map((call, callIndex) => ({ ...toolCall(call, call?.result === undefined ? "running" : "success"), call_id: text(call?.call_id || `history_${callIndex}`) })) }] : [base];
    });
    drafts.clear(); batches.clear(); notify();
  }
  function setContextSummary(context = {}) {
    const stats = object(context?.stats), messages = Number(stats.messages) || 0, characters = Number(stats.characters) || 0;
    nodes = nodes.filter((node) => node.type !== "context_summary");
    if (sessionId) nodes = [{ id: `context:${sessionId}`, type: "context_summary", messages, characters }, ...nodes];
    notify();
  }
  function beginUserTurn(content) { append({ id: `user:${Date.now()}`, type: "user_message", role: "user", content: text(content), reasoning: "" }); notify(); }
  function setRunState(nextState) { runState = text(nextState || "idle").toLowerCase(); notify(); }

  function applyEvent(event) {
    const type = text(event?.type), data = object(event?.data), agent = text(event?.agent || "coordinator"), round = data.round ?? "";
    if (type === "agent:stream_delta") {
      const key = keyFor(agent, round); let draft = drafts.get(key);
      if (!draft) { draft = append({ id: `draft:${key}`, type: "assistant_draft", role: "assistant", agent, round, content: "", reasoning: "" }); drafts.set(key, draft); }
      if (data.channel === "reasoning") draft.reasoning += text(data.delta); else draft.content += text(data.delta);
    } else if (type === "agent:tools_requested") {
      ensureBatch(agent, round, callsFrom(data));
    } else if (type === "agent:tools_completed") {
      updateTools(agent, round, callsFrom(data));
    } else if (type === "agent:round") {
      const key = keyFor(agent, round), draft = drafts.get(key);
      if (draft) { removeById(draft.id); drafts.delete(key); }
      const content = text(data.assistant_content), reasoning = text(data.reasoning_content), calls = callsFrom(data);
      if (calls.length && !findBatch(agent, round)) updateTools(agent, round, calls);
      if (content || reasoning || calls.length) append({ id: `round:${key}:${nodes.length}`, type: "assistant_message", role: "assistant", agent, round, content, reasoning, usage: data.round_usage ?? null, duration_ms: data.model_duration_ms ?? null, created_at: event?.timestamp ?? null });
    } else if (event?.event === "error") {
      append({ id: `error:${Date.now()}`, type: "system_status", status: "error", content: text(event?.message || "调查运行失败") });
    } else if (type === "agent:complete" || event?.event === "done") {
      runState = "completed";
    } else if (event?.event === "stopped") {
      runState = "stopped";
    }
    if (terminalStates.has(runState)) drafts.clear();
    notify();
  }

  return { reset, hydrate, setContextSummary, beginUserTurn, applyEvent, setRunState, subscribe(listener) { listeners.add(listener); listener({ session_id: sessionId, run_state: runState, nodes: cloneNodes(nodes) }); return () => listeners.delete(listener); } };
}
