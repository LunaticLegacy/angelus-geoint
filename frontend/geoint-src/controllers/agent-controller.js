import { api } from "../api.js";
import { byId, setRun } from "../dom.js";

const active = new Set(["running", "stopping", "force_stopping"]);

/** Adapt Angelus run transport into projector events without owning chat DOM. */
export function createAgent({ state, projector, requestScope }) {
  let stream = null, streamSession = "";
  const appendTrace = (value) => { const trace = byId("trace-log"); if (trace) trace.textContent += `${value}\n`; };
  function setState(value) { const next = String(value || "idle").toLowerCase(); setRun(next); projector.setRunState(next); }
  function close() { stream?.close(); stream = null; streamSession = ""; }
  function follow(id, token = requestScope.capture("agent-follow")) {
    close(); streamSession = id; stream = new EventSource(`/api/runs/${encodeURIComponent(id)}/events?cursor=0`);
    stream.onmessage = (event) => {
      if (state.sessionId() !== id || !requestScope.isCurrent(token)) return;
      try { const payload = JSON.parse(event.data); projector.applyEvent(payload); appendTrace(event.data); } catch { appendTrace(event.data); }
    };
    stream.onerror = () => {
      if (streamSession !== id || !requestScope.isCurrent(token)) return; close();
      api(`/api/runs/${encodeURIComponent(id)}/status`).then((run) => { if (requestScope.isCurrent(token)) setState(run.state); }).catch(() => { if (requestScope.isCurrent(token)) projector.applyEvent({ event: "error", message: "调查状态读取失败" }); });
    };
  }
  async function activateSession(contextSnapshot = null) {
    const token = requestScope.capture("agent-activate"), id = token.sessionId; close(); projector.reset(id);
    if (!id) return;
    const [history, run] = await Promise.all([api(`/api/sessions/${encodeURIComponent(id)}/messages?limit=200`), api(`/api/runs/${encodeURIComponent(id)}/status`)]);
    if (!requestScope.isCurrent(token)) return null;
    projector.hydrate(history.messages || []); projector.setContextSummary(contextSnapshot || {}); setState(run.state);
    if (active.has(String(run.state).toLowerCase())) follow(id, token);
    return run;
  }
  return {
    async run(message = byId("agent-prompt")?.value.trim()) {
      const token = requestScope.capture("agent-run"), id = token.sessionId, content = String(message || "").trim(); if (!id || !content) throw new Error("请选择会话并输入调查问题");
      const receipt = await api("/api/runs", { method: "POST", body: JSON.stringify({ session_id: id, message: content }) });
      if (!requestScope.isCurrent(token)) return null;
      projector.beginUserTurn(content); setState(receipt.state); follow(id); return receipt;
    },
    async stop() { const token = requestScope.capture("agent-stop"), id = token.sessionId; if (!id) throw new Error("请先选择会话"); const receipt = await api(`/api/runs/${encodeURIComponent(id)}/stop`, { method: "POST", body: JSON.stringify({ reason: "geoint_operator_requested" }) }); if (!requestScope.isCurrent(token)) return null; setState(receipt.state); return receipt; },
    async reconcile(contextSnapshot) { await activateSession(contextSnapshot); },
    dispose: close,
  };
}
