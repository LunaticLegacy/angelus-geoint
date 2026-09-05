import { api } from "../api.js";
import { byId } from "../dom.js";
import { renderConnectors } from "../components/workspace-ui.js";
export function createConnectors({ state, sources }) {
  async function refresh() {
    const [items, providers] = await Promise.all([api(sources.connectors), api(sources.providers)]);
    state.setConnectors(items.connectors || []); renderConnectors(state.connectors());
    const select = byId("connector-provider"); select.replaceChildren(); (providers.providers || ["openai"]).forEach((value) => select.add(new Option(value, value)));
    return state.connectors();
  }
  async function bind(connectorId) {
    const sessionId = state.sessionId(), connector = state.connectors().find((item) => item.id === connectorId);
    if (!sessionId || !connector?.has_api_key) throw new Error("请选择带 API Key 的连接器和会话");
    const old = state.profile()?.effective || {}, settings = { ...old, connector_id: connector.id, provider: connector.provider, model: connector.model, api_url: connector.api_url };
    const profile = await api(`/api/sessions/${encodeURIComponent(sessionId)}/run-profile`, { method: "PUT", body: JSON.stringify({ settings }) }); state.setProfile(profile); byId("session-profile").value = JSON.stringify(profile.effective || {}, null, 2);
  }
  return { refresh, bind, async createAndBind() {
    const name = byId("connector-name").value.trim(), provider = byId("connector-provider").value, model = byId("connector-model").value.trim(), apiUrl = byId("connector-api-url").value.trim(), apiKey = byId("connector-api-key").value;
    if (!state.sessionId() || !name || !provider || !model || !apiKey) throw new Error("会话、名称、Provider、模型和 API Key 均为必填项");
    const connector = await api("/api/connectors", { method: "POST", body: JSON.stringify({ name, provider, model, api_url: apiUrl, api_key: apiKey }) });
    byId("connector-api-key").value = ""; byId("connector-name").value = ""; await refresh(); await bind(connector.id);
  } };
}
