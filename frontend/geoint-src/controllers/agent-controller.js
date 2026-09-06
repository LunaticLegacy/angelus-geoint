import { api } from "../api.js";
import { byId, setRun } from "../dom.js";

const active = new Set(["running", "stopping", "force_stopping"]);
const mapMutationTools = new Set(["geoint_manage_map_layers"]);
const evidenceMutationTools = new Set(["geoint_read_result", "geoint_record_evidence"]);

/** True only after a successful direct GEOINT map operation has completed. */
export function isDirectMapMutation(event) {
  if (event?.type !== "agent:tools_completed") return false;
  const calls = Array.isArray(event?.data?.tool_calls) ? event.data.tool_calls : [];
  return calls.some((call) => mapMutationTools.has(call?.name) && call?.ok !== false);
}

export function isEvidenceMutation(event) {
  if (event?.type !== "agent:tools_completed") return false;
  const calls = Array.isArray(event?.data?.tool_calls) ? event.data.tool_calls : [];
  return calls.some((call) => evidenceMutationTools.has(call?.name) && call?.ok !== false);
}

/** Adapt Angelus run transport into projector events without owning chat DOM. */
export function createAgent({ state, projector, requestScope, trace = { append() {} }, onMapChanged = () => {}, onEvidenceChanged = () => {} }) {
  let stream = null, streamSession = "", historyCursor = null, historyHasMore = false, historyLoading = false;
  const appendTrace = (value) => trace.append(value);
  function setState(value) { const next = String(value || "idle").toLowerCase(); setRun(next); projector.setRunState(next); }
  function close() { stream?.close(); stream = null; streamSession = ""; }
  function follow(id, token = requestScope.capture("agent-follow"), cursor = 0) {
    close(); streamSession = id; stream = new EventSource(`/api/runs/${encodeURIComponent(id)}/events?cursor=${Math.max(0, Number(cursor) || 0)}`);
    stream.onmessage = (event) => {
      if (state.sessionId() !== id || !requestScope.isCurrent(token)) return;
      try {
        const payload = JSON.parse(event.data); projector.applyEvent(payload); appendTrace(event.data);
        // A tool action is durable before this event is emitted. Refresh only
        // after successful completion, never while a call is merely proposed.
        if (isDirectMapMutation(payload)) Promise.resolve(onMapChanged()).catch(() => {});
        if (isEvidenceMutation(payload)) Promise.resolve(onEvidenceChanged()).catch(() => {});
      } catch { appendTrace(event.data); }
    };
    stream.onerror = () => {
      if (streamSession !== id || !requestScope.isCurrent(token)) return; close();
      api(`/api/runs/${encodeURIComponent(id)}/status`).then((run) => { if (requestScope.isCurrent(token)) setState(run.state); }).catch(() => { if (requestScope.isCurrent(token)) projector.applyEvent({ event: "error", message: "调查状态读取失败" }); });
    };
  }
  async function activateSession(contextSnapshot = null) {
    const token = requestScope.capture("agent-activate"), id = token.sessionId; close(); projector.reset(id);
    if (!id) return;
    const [history, run] = await Promise.all([api(`/api/sessions/${encodeURIComponent(id)}/investigation-history?limit=200`), api(`/api/runs/${encodeURIComponent(id)}/status`)]);
    if (!requestScope.isCurrent(token)) return null;
    historyCursor = history.next_cursor ?? null; historyHasMore = Boolean(history.has_more && historyCursor !== null);
    projector.hydrate(history.messages || []); projector.setContextSummary(contextSnapshot || {}); setState(run.state);
    if (active.has(String(run.state).toLowerCase())) follow(id, token, history.current_attempt_events);
    return run;
  }
  return {
    async run(message = byId("agent-prompt")?.value.trim()) {
      const token = requestScope.capture("agent-run"), id = token.sessionId, content = String(message || "").trim(); if (!id || !content) throw new Error("请选择会话并输入调查问题");
      const receipt = await api("/api/runs", { method: "POST", body: JSON.stringify({ session_id: id, message: content }) });
      if (!requestScope.isCurrent(token)) return null;
      projector.beginUserTurn(content); setState(receipt.state); follow(id); return receipt;
    },
    async steer(message) {
      const token = requestScope.capture("agent-steer"), id = token.sessionId, content = String(message || "").trim();
      if (!id || !content) throw new Error("请选择正在运行的会话并输入调查引导");
      const receipt = await api(`/api/runs/${encodeURIComponent(id)}/control`, {
        method: "POST", body: JSON.stringify({ agent_id: "all", action: "steer", message: content }),
      });
      if (!requestScope.isCurrent(token)) return null;
      return receipt;
    },
    async stop() { const token = requestScope.capture("agent-stop"), id = token.sessionId; if (!id) throw new Error("请先选择会话"); const receipt = await api(`/api/runs/${encodeURIComponent(id)}/stop`, { method: "POST", body: JSON.stringify({ reason: "geoint_operator_requested" }) }); if (!requestScope.isCurrent(token)) return null; setState(receipt.state); return receipt; },
    async loadOlderHistory() {
      if (historyLoading || !historyHasMore || historyCursor === null) return { has_more: historyHasMore };
      const token = requestScope.capture("agent-history"), id = token.sessionId, cursor = historyCursor;
      if (!id) return { has_more: false };
      historyLoading = true;
      try {
        const page = await api(`/api/sessions/${encodeURIComponent(id)}/investigation-history?before=${encodeURIComponent(cursor)}&limit=200`);
        if (!requestScope.isCurrent(token)) return { has_more: false };
        historyCursor = page.next_cursor ?? null; historyHasMore = Boolean(page.has_more && historyCursor !== null);
        projector.prependHistory(page.messages || []);
        return { has_more: historyHasMore, loaded: Array.isArray(page.messages) ? page.messages.length : 0 };
      } finally { historyLoading = false; }
    },
    hasOlderHistory: () => historyHasMore,
    async reconcile(contextSnapshot) { await activateSession(contextSnapshot); },
    dispose: close,
  };
}
