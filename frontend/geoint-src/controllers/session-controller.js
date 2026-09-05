import { api } from "../api.js";
import { byId } from "../dom.js";
import { renderSessions, showSession } from "../components/workspace-ui.js";
import { renderToolPermissions } from "../components/tool-permissions.js";
export function createSessions({ state, sources, requestScope }) {
  async function refresh() { const data = await api(sources.sessions); renderSessions(data.sessions || [], state); return data.sessions || []; }
  function renderPermissions(catalog, policy) {
    renderToolPermissions(byId('tool-permission-list'), catalog, policy, (next) => {
      let settings;
      try { settings = JSON.parse(byId('session-profile').value); }
      catch { byId('status-text').textContent = '请先修正运行档案 JSON，再修改工具权限。'; return; }
      settings.tool_permissions = next;
      byId('session-profile').value = JSON.stringify(settings, null, 2);
      renderPermissions(catalog, next);
      byId('status-text').textContent = '工具权限已修改，请点击“保存运行档案”；下次启动 Agent 时生效。';
    });
  }
  async function loadProfile() {
    const request = requestScope.capture("session-profile"), id = request.sessionId; showSession(state);
    const host = byId('tool-permission-list'); host.textContent = id ? '正在加载工具权限…' : '选择会话后读取可用工具。';
    if (!id) { state.setProfile(null); byId('session-profile').value = ''; return null; }
    try {
      const [profile, catalog] = await Promise.all([api(`/api/sessions/${encodeURIComponent(id)}/run-profile`), api('/api/tool-registry')]);
      if (!requestScope.isCurrent(request)) return null;
      state.setProfile(profile); byId('session-profile').value = JSON.stringify(profile.effective || {}, null, 2);
      renderPermissions(catalog, profile.effective?.tool_permissions || {}); return profile;
    } catch (error) {
      if (!requestScope.isCurrent(request)) return null;
      host.textContent = `工具权限加载失败：${error.message}`;
      throw error;
    }
  }
  return { refresh, loadProfile, async create() { const name = byId("new-session-name").value.trim(); if (!name) throw new Error("请输入会话名称"); const item = await api("/api/sessions", { method: "POST", body: JSON.stringify({ name }) }); byId("new-session-name").value = ""; await refresh(); byId("session-select").value = item.id; requestScope.select(item.id); showSession(state); return item; }, async remove() { const id = state.sessionId(); if (!id || byId("session-delete-confirmation").value !== id) throw new Error("删除确认必须精确等于当前会话 ID"); await api(`/api/sessions/${encodeURIComponent(id)}`, { method: "DELETE", body: JSON.stringify({ confirmation: id }) }); requestScope.select(""); await refresh(); }, async saveProfile() { const request = requestScope.capture("session-profile-save"), id = request.sessionId; if (!id) throw new Error("请先选择会话"); let settings; try { settings = JSON.parse(byId("session-profile").value); } catch { throw new Error("运行档案必须是有效 JSON"); } const profile = await api(`/api/sessions/${encodeURIComponent(id)}/run-profile`, { method: "PUT", body: JSON.stringify({ settings }) }); if (!requestScope.isCurrent(request)) return null; state.setProfile(profile); byId("session-profile").value = JSON.stringify(profile.effective || {}, null, 2); return profile; } };
}
