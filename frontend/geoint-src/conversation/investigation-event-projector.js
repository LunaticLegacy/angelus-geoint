const terminalStates = new Set(["completed", "failed", "stopped", "interrupted"]);

const text = (value) => String(value ?? "");
const object = (value) => value && typeof value === "object" && !Array.isArray(value) ? value : {};
const callsFrom = (data) => Array.isArray(data?.tool_calls) ? data.tool_calls : [];
const keyFor = (agent, round) => `${agent || "coordinator"}:${round ?? ""}`;

/** FNV-1a keeps a steer_id-less journal record addressable across replays without a hash dependency. */
function fnv1a(value) {
  let hash = 0x811c9dc5;
  for (let index = 0; index < value.length; index += 1) { hash ^= value.charCodeAt(index); hash = Math.imul(hash, 0x01000193) >>> 0; }
  return hash.toString(16).padStart(8, "0");
}
/** Steer node key: the real steer_id when present, else a deterministic digest of (agent, text, targets). */
const steerIdFor = (steerId, agent, content, targets) => text(steerId) ? `steer:${text(steerId)}` : `steer:legacy:${fnv1a([agent, content, ...(Array.isArray(targets) ? targets.map(text).sort() : [])].join("\u0000"))}`;

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
  /** Replace a same-id node in place: a replayed event must update the card, not reorder the timeline. */
  function upsert(node) { const index = nodes.findIndex((existing) => existing.id === node.id); if (index < 0) return append(node); nodes = nodes.map((existing, position) => position === index ? { ...node } : existing); return nodes[index]; }
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
      const toolNode = { id: `history-tools:${message?.timeline ?? index}`, type: "tool_batch", agent: "coordinator", round: message?.timeline ?? index, tools: tools.map((call, callIndex) => ({ ...toolCall(call, call?.result === undefined ? "running" : "success"), call_id: text(call?.call_id || `history_${callIndex}`) })) };
      return tools.length ? (base.content || base.reasoning ? [base, toolNode] : [toolNode]) : [base];
    });
    drafts.clear(); batches.clear(); notify();
  }
  /**
   * Fold durable steering records into the transcript.
   *
   * Steering is a fact of the current (or most recent) run only, so the records
   * are appended after the hydrated messages instead of being sorted into older
   * rounds: that keeps the order the operator actually saw, and the cost of the
   * trade-off is only that a guide from an older run would sit at the tail.
   * Records arrive ordered by ``submitted_at``; every node goes through upsert so
   * the SSE replay of the same steer_id folds onto the same card.
   */
  function hydrateSteering(records = []) {
    const ordered = (Array.isArray(records) ? records : []).filter((record) => record && typeof record === "object").sort((left, right) => (Number(left?.submitted_at) || 0) - (Number(right?.submitted_at) || 0));
    ordered.forEach((record) => {
      const appliedAgents = Array.isArray(record?.applied_agents) ? record.applied_agents.map(text).filter(Boolean) : [];
      const recipients = Array.isArray(record?.recipients) ? record.recipients.map(text) : [];
      const content = text(record?.text), id = steerIdFor(record?.id, text(record?.scope || "operator"), content, recipients);
      const existing = nodes.find((node) => node.id === id), applied = Array.isArray(existing?.applied) ? existing.applied : [];
      const landed = appliedAgents.length > 0 || existing?.type === "steer_applied";
      upsert({ id, type: landed ? "steer_applied" : "steer_queued", agent: appliedAgents[0] || text(record?.scope || "operator"), round: "", content, targets: recipients.length ? recipients : (Array.isArray(existing?.targets) ? existing.targets : []), applied: appliedAgents.reduce((all, name) => all.includes(name) ? all : [...all, name], applied) });
    });
    notify();
  }
  function prependHistory(messages = []) {
    const known = new Set(nodes.map((node) => node.id));
    const older = (Array.isArray(messages) ? messages : []).flatMap((message, index) => {
      const role = text(message?.role || "assistant");
      const timeline = message?.timeline ?? `older-${index}`;
      const base = { id: `history:${timeline}`, type: role === "user" ? "user_message" : "assistant_message", role, content: text(message?.content), reasoning: text(message?.reasoning), created_at: message?.created_at ?? null, usage: message?.usage ?? null, duration_ms: message?.round_duration_ms ?? message?.model_duration_ms ?? null };
      const tools = Array.isArray(message?.tools) ? message.tools : [];
      const toolNode = { id: `history-tools:${timeline}`, type: "tool_batch", agent: "coordinator", round: timeline, tools: tools.map((call, callIndex) => ({ ...toolCall(call, call?.result === undefined ? "running" : "success"), call_id: text(call?.call_id || `history_${callIndex}`) })) };
      return tools.length ? (base.content || base.reasoning ? [base, toolNode] : [toolNode]) : [base];
    }).filter((node) => !known.has(node.id));
    const context = nodes.filter((node) => node.type === "context_summary");
    const rest = nodes.filter((node) => node.type !== "context_summary");
    nodes = [...context, ...older, ...rest]; notify();
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
    } else if (type === "agent:control" && data.action === "steer") {
      const targets = Array.isArray(data.target_agents) ? data.target_agents.map(text) : [], content = text(event?.message), id = steerIdFor(data.steer_id, agent, content, targets);
      const existing = nodes.find((node) => node.id === id);
      // A replay of the control record must never downgrade a steer that already landed.
      upsert({ id, type: existing?.type === "steer_applied" ? "steer_applied" : "steer_queued", agent, content, targets, applied: Array.isArray(existing?.applied) ? existing.applied : [] });
    } else if (type === "agent:steer_applied") {
      const messages = Array.isArray(data.messages) ? data.messages.map(text).filter(Boolean) : [], steerIds = Array.isArray(data.steer_ids) ? data.steer_ids : [];
      // ``messages`` and ``steer_ids`` are index-aligned in the journal, so each
      // applied guide updates the queued card the operator is already looking at.
      messages.forEach((content, index) => {
        const id = steerIdFor(steerIds[index], agent, content, []), existing = nodes.find((node) => node.id === id), applied = Array.isArray(existing?.applied) ? existing.applied : [];
        upsert({ id, type: "steer_applied", agent, round, content, targets: Array.isArray(existing?.targets) ? existing.targets : [], applied: applied.includes(agent) ? applied : [...applied, agent] });
      });
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

  return { reset, hydrate, hydrateSteering, prependHistory, setContextSummary, beginUserTurn, applyEvent, setRunState, subscribe(listener) { listeners.add(listener); listener({ session_id: sessionId, run_state: runState, nodes: cloneNodes(nodes) }); return () => listeners.delete(listener); } };
}
