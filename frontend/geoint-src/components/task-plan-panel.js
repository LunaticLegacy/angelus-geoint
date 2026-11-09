import { api } from "../api.js";
import { planTasks, renderPlanDocument } from "./task-plan-view.js";

/** Build the documented plan URL, including the owning Agent selector. */
export function planPath(sessionId, { suffix = "", agent = "coordinator" } = {}) {
  return `/api/sessions/${encodeURIComponent(sessionId)}/plan${suffix}?agent=${encodeURIComponent(agent)}`;
}

/**
 * Mount the durable task-plan panel for one Agent.
 *
 * The console owns every plan transition: this panel only reads
 * `GET /plan`, replaces a whole plan with `PUT /plan`, and moves one leaf with
 * `PATCH /plan/tasks/{task_id}`.  All three are documented HTTP interfaces, so
 * no control here is decorative; failures are rendered instead of swallowed.
 *
 * Args:
 *   root: Panel host element (already present in the template).
 *   options.onStatus: Callback for the shell status bar messages.
 *
 * Returns:
 *   `setSession(id)` / `refresh()` handles used by the session lifecycle.
 */
export function mountPlanPanel(root, { onStatus = () => {}, agent = "coordinator" } = {}) {
  let sessionId = "", loading = false;
  if (!root) return { setSession() {}, refresh() {} };
  root.innerHTML = `<div class="section-title compact"><div><span class="eyebrow">DURABLE PLAN</span><h3>任务与计划</h3></div><div class="action-group"><button type="button" class="plan-refresh secondary">刷新计划</button></div></div><p class="fineprint">计划由 Agent 写入并持久化到会话状态。这里展示协调者（coordinator）的目标与递归任务树；叶子任务可直接切换状态，整份计划可用 JSON 覆盖提交。</p><div class="plan-error" role="alert" hidden></div><div class="plan-summary-host" aria-live="polite"></div><details class="agent-details plan-editor"><summary><span>替换整份计划（JSON）</span><span>高级</span></summary><label class="field"><span>计划 JSON（goal 必填，summary 与 tasks 可选）</span><textarea class="plan-json" rows="10" placeholder='{"goal":"…","summary":"…","tasks":[]}'></textarea></label><div class="plan-editor-footer"><button type="button" class="plan-replace primary">保存计划</button></div></details>`;
  const host = root.querySelector(".plan-summary-host");
  const error = root.querySelector(".plan-error");
  const json = root.querySelector(".plan-json");
  const refreshButton = root.querySelector(".plan-refresh");
  const replaceButton = root.querySelector(".plan-replace");
  const setError = (message = "") => { error.textContent = message; error.hidden = !message; };

  function fillEditor(plan) {
    if (document.activeElement === json) return;
    json.value = JSON.stringify({ goal: plan?.goal || "", summary: plan?.summary || "", tasks: planTasks(plan) }, null, 2);
  }

  async function load() {
    if (!sessionId) {
      host.innerHTML = `<p class="empty">尚未选择会话。</p>`;
      json.value = "";
      setError("");
      return null;
    }
    loading = true;
    setError("");
    try {
      const plan = await api(planPath(sessionId, { agent }));
      host.innerHTML = renderPlanDocument(plan, { agent });
      fillEditor(plan);
      return plan;
    } catch (caught) {
      host.innerHTML = `<p class="empty">任务计划读取失败。</p>`;
      setError(`任务计划读取失败：${caught.message}`);
      return null;
    } finally {
      loading = false;
    }
  }

  async function changeStatus(select) {
    const status = select.value, previous = select.dataset.status, taskId = select.dataset.taskId;
    if (!sessionId || !taskId || status === previous) return;
    select.disabled = true;
    try {
      await api(planPath(sessionId, { suffix: `/tasks/${encodeURIComponent(taskId)}`, agent }), { method: "PATCH", body: JSON.stringify({ status }) });
      onStatus("任务状态已更新。");
      await load();
    } catch (caught) {
      select.value = previous;
      setError(`任务状态更新失败：${caught.message}`);
      onStatus(`任务状态更新失败：${caught.message}`);
    } finally {
      select.disabled = false;
    }
  }

  async function replacePlan() {
    if (!sessionId || loading) return;
    let payload;
    try { payload = JSON.parse(json.value); }
    catch (caught) { setError(`计划 JSON 解析失败：${caught.message}`); return; }
    if (!payload || typeof payload !== "object" || typeof payload.goal !== "string" || !payload.goal.trim()) {
      setError("计划 JSON 必须包含非空 goal 字段。");
      return;
    }
    if (payload.tasks !== undefined && !Array.isArray(payload.tasks)) {
      setError("计划 JSON 的 tasks 必须是数组。");
      return;
    }
    replaceButton.disabled = true;
    setError("");
    try {
      await api(planPath(sessionId, { agent }), {
        method: "PUT",
        body: JSON.stringify({ goal: payload.goal, summary: typeof payload.summary === "string" ? payload.summary : "", tasks: payload.tasks || [] }),
      });
      onStatus("任务计划已保存。");
      await load();
    } catch (caught) {
      setError(`计划保存失败：${caught.message}`);
      onStatus(`计划保存失败：${caught.message}`);
    } finally {
      replaceButton.disabled = false;
    }
  }

  host.addEventListener("change", (event) => {
    const select = event.target.closest?.(".task-state-select");
    if (select) changeStatus(select);
  });
  refreshButton.addEventListener("click", () => { load(); });
  replaceButton.addEventListener("click", replacePlan);

  return {
    setSession(nextSessionId) { sessionId = nextSessionId || ""; return load(); },
    refresh() { return load(); },
  };
}
