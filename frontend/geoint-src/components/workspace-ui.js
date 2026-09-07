import { byId } from "../dom.js";

export function renderActions(actions, onAction) {
  const groups = { header: "header-actions", map: "map-actions", agent: "agent-actions", trace: "trace-actions", session: "session-actions", context: "context-actions", connector: "connector-actions" };
  Object.values(groups).forEach((id) => byId(id)?.replaceChildren());
  actions.forEach((action) => {
    if (action.group === "agent" && action.id === "agent.run") return;
    const host = byId(groups[action.group]); if (!host) return;
    const button = document.createElement("button"); button.type = "button"; button.className = action.style || "secondary"; button.dataset.action = action.id; button.textContent = action.label;
    button.onclick = async () => {
      button.disabled = true;
      try { await onAction(action.id); }
      catch (error) {
        const message = error instanceof Error ? error.message : String(error);
        byId("status-text").textContent = `操作失败：${message}`;
      } finally { button.disabled = false; }
    };
    host.append(button);
  });
}
export function renderTabs(tabs) {
  const host = byId("workspace-tabs"); host.replaceChildren();
  const selected = document.querySelector(".tab-panel.active")?.dataset.panel || tabs[0]?.id;
  tabs.forEach((tab) => { const button = document.createElement("button"); button.className = `tab${tab.id === selected ? " active" : ""}`; button.textContent = tab.label; button.onclick = () => { document.querySelectorAll(".tab").forEach((x) => x.classList.toggle("active", x === button)); document.querySelectorAll(".tab-panel").forEach((x) => x.classList.toggle("active", x.dataset.panel === tab.id)); }; host.append(button); });
}
export function renderSessions(sessions, state) {
  const select = byId("session-select"), prior = state.sessionId(); state.setSessions(sessions); select.replaceChildren(new Option("不使用 Agent 会话", ""));
  sessions.forEach((item) => select.add(new Option(`${item.name} · ${item.state}`, item.id)));
  select.value = [...select.options].some((x) => x.value === prior) ? prior : ""; state.selectSession(select.value); showSession(state);
}
export function showSession(state) {
  const id = state.sessionId(), option = byId("session-select").selectedOptions[0], session = state.session();
  byId("session-detail-name").textContent = id ? option.textContent : "未选择";
  byId("session-detail-id").textContent = id || "—";
  const workspace = byId("session-detail-workspace");
  if (workspace) workspace.textContent = session?.project_path || "—";
  const connector = state.connectors().find((item) => item.id === state.profile()?.effective?.connector_id);
  let binding = byId("session-detail-connector");
  if (!binding && workspace?.parentElement) {
    const label = document.createElement("span"); label.className = "session-connector-label"; label.textContent = "已绑定连接器";
    binding = document.createElement("strong"); binding.id = "session-detail-connector";
    const openButton = byId("open-session-workspace");
    workspace.parentElement.insertBefore(label, openButton); workspace.parentElement.insertBefore(binding, openButton);
  }
  if (binding) binding.textContent = connector ? connectorLabel(connector) : (id ? "未绑定连接器" : "—");
}
export function connectorLabel(connector, duplicates = 1) {
  const suffix = duplicates > 1 ? ` · 重名 ${connector.id.slice(-6)}` : "";
  return `${connector.name} · ${connector.provider}/${connector.model || "未设置模型"}${connector.has_api_key ? "" : " · 无密钥"}${suffix}`;
}
export function setConnectorStatus(text, tone = "") {
  const status = byId("connector-status"); if (!status) return;
  status.textContent = text; status.className = `connector-status${tone ? ` ${tone}` : ""}`;
}
export function renderConnectors(connectors, state) {
  const select = byId("connector-select"), old = select.value;
  const counts = connectors.reduce((result, item) => {
    const key = item.name.trim().toLocaleLowerCase(); result.set(key, (result.get(key) || 0) + 1); return result;
  }, new Map());
  const boundId = state?.profile()?.effective?.connector_id || "";
  select.replaceChildren(new Option("选择一个已有连接器", ""));
  connectors.forEach((item) => select.add(new Option(connectorLabel(item, counts.get(item.name.trim().toLocaleLowerCase())), item.id)));
  const preferred = boundId || old;
  select.value = [...select.options].some((x) => x.value === preferred) ? preferred : "";
  const bound = connectors.find((item) => item.id === boundId);
  if (bound) setConnectorStatus(`当前会话已绑定：${connectorLabel(bound, counts.get(bound.name.trim().toLocaleLowerCase()))}`, "ok");
  else if (state?.sessionId()) setConnectorStatus("当前会话尚未绑定连接器。选择已有连接器后点击“绑定已有连接器”，或保存新连接器并自动绑定。", "warn");
  else setConnectorStatus("选择会话后检查可用连接器。");
}
