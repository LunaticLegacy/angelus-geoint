import { byId } from "../dom.js";

export function renderActions(actions, onAction) {
  const groups = { header: "header-actions", map: "map-actions", agent: "agent-actions", trace: "trace-actions", session: "session-actions", context: "context-actions", connector: "connector-actions" };
  Object.values(groups).forEach((id) => byId(id)?.replaceChildren());
  actions.forEach((action) => {
    if (action.group === "agent" && action.id === "agent.run") return;
    const host = byId(groups[action.group]); if (!host) return;
    const button = document.createElement("button"); button.type = "button"; button.className = action.style || "secondary"; button.dataset.action = action.id; button.textContent = action.label;
    button.onclick = async () => { button.disabled = true; try { await onAction(action.id); } finally { button.disabled = false; } };
    host.append(button);
  });
}
export function renderTabs(tabs) {
  const host = byId("workspace-tabs"); host.replaceChildren();
  const selected = document.querySelector(".tab-panel.active")?.dataset.panel || tabs[0]?.id;
  tabs.forEach((tab) => { const button = document.createElement("button"); button.className = `tab${tab.id === selected ? " active" : ""}`; button.textContent = tab.label; button.onclick = () => { document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("active", x === button)); document.querySelectorAll(".tab-panel").forEach((x) => x.classList.toggle("active", x.dataset.panel === tab.id)); }; host.append(button); });
}
export function renderSessions(sessions, state) {
  const select = byId("session-select"), prior = state.sessionId(); select.replaceChildren(new Option("不使用 Agent 会话", ""));
  sessions.forEach((item) => select.add(new Option(`${item.name} · ${item.state}`, item.id)));
  select.value = [...select.options].some((x) => x.value === prior) ? prior : ""; state.selectSession(select.value); showSession(state);
}
export function showSession(state) { const id = state.sessionId(), option = byId("session-select").selectedOptions[0]; byId("session-detail-name").textContent = id ? option.textContent : "未选择"; byId("session-detail-id").textContent = id || "—"; }
export function renderConnectors(connectors) { const select = byId("connector-select"), old = select.value; select.replaceChildren(new Option("选择一个已有连接器", "")); connectors.forEach((item) => select.add(new Option(`${item.name} · ${item.provider}/${item.model || "未设置模型"}${item.has_api_key ? "" : " · 无密钥"}`, item.id))); select.value = [...select.options].some((x) => x.value === old) ? old : ""; }
