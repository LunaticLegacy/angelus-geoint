import { api } from "../api.js";
import { byId } from "../dom.js";
import { renderSessions, showSession } from "../components/workspace-ui.js";
import { renderToolPermissions } from "../components/tool-permissions.js";
export function createSessions({ state, sources, requestScope }) {
  async function refresh() { const data = await api(sources.sessions); renderSessions(data.sessions || [], state); return data.sessions || []; }
  function setPermissionFeedback(text = "", tone = "") {
    const section = byId("tool-permission-list")?.closest(".tool-permissions"); if (!section) return;
    let feedback = byId("tool-permission-feedback");
    if (!feedback) {
      feedback = document.createElement("p"); feedback.id = "tool-permission-feedback"; feedback.setAttribute("aria-live", "polite");
      section.append(feedback);
    }
    feedback.className = `setting-feedback${tone ? ` ${tone}` : ""}`; feedback.textContent = text;
  }
  function updateProfileDraft(change) {
    let settings;
    try { settings = JSON.parse(byId('session-profile').value); }
    catch {
      const message = '请先修正运行档案 JSON，再修改此设置。'; byId('status-text').textContent = message; setPermissionFeedback(message, 'error'); return null;
    }
    change(settings); byId('session-profile').value = JSON.stringify(settings, null, 2);
    return settings;
  }
  async function saveNetworkMode(mode, previous) {
    const request = requestScope.capture('shell-network-mode'), id = request.sessionId;
    const settings = updateProfileDraft((draft) => { draft.shell_network_mode = mode; });
    if (!settings || !id) return false;
    byId('status-text').textContent = '正在保存 Shell 网络设置…';
    try {
      const profile = await api(`/api/sessions/${encodeURIComponent(id)}/run-profile`, { method: 'PUT', body: JSON.stringify({ settings }) });
      if (!requestScope.isCurrent(request)) return false;
      state.setProfile(profile); byId('session-profile').value = JSON.stringify(profile.effective || {}, null, 2);
      byId('status-text').textContent = 'Shell 网络设置已保存；下一次启动 Agent 时生效。';
      return true;
    } catch (error) {
      byId('status-text').textContent = `Shell 网络设置保存失败：${error.message}`;
      return previous === mode;
    }
  }
  function renderShellNetworkMode(mode) {
    const permissions = byId('tool-permission-list')?.closest('.tool-permissions'); if (!permissions) return;
    let section = permissions.parentElement?.querySelector('.shell-network-settings');
    if (!section) {
      section = document.createElement('section'); section.className = 'shell-network-settings';
      section.innerHTML = '<span class="eyebrow">SHELL SANDBOX</span><label class="field"><span>Shell 网络</span><select id="shell-network-mode"><option value="host_network">联网（继承 Angelus 服务网络，默认）</option><option value="isolated">隔离（断网）</option></select></label><p class="fineprint">联网模式只移除 Shell 自己的网络隔离；仅当 Angelus 服务本身有公网出口时才能联网。文件系统仍只限当前会话工作空间；设置会立即保存并于下一次启动 Agent 生效。</p>';
      permissions.after(section);
      section.querySelector('select').onchange = async (event) => {
        const next = String(event.target.value || 'isolated');
        const select = event.target, prior = mode; select.disabled = true;
        if (!await saveNetworkMode(next, prior)) select.value = prior;
        select.disabled = !state.sessionId();
      };
    }
    const select = section.querySelector('select'); select.value = mode === 'isolated' ? 'isolated' : 'host_network';
    select.disabled = !state.sessionId();
  }
  async function savePermissions(catalog, next, previous) {
    const request = requestScope.capture('tool-permissions'), id = request.sessionId;
    const settings = updateProfileDraft((draft) => { draft.tool_permissions = next; });
    if (!settings || !id) return false;
    byId('tool-permission-list').querySelectorAll('input').forEach((input) => { input.disabled = true; });
    byId('status-text').textContent = '正在保存工具权限…'; setPermissionFeedback('正在保存工具权限…');
    try {
      const profile = await api(`/api/sessions/${encodeURIComponent(id)}/run-profile`, { method: 'PUT', body: JSON.stringify({ settings }) });
      if (!requestScope.isCurrent(request)) return false;
      state.setProfile(profile);
      byId('session-profile').value = JSON.stringify(profile.effective || {}, null, 2);
      renderPermissions(catalog, profile.effective?.tool_permissions || {});
      const message = '工具权限已保存；下一次启动 Agent 时生效。';
      byId('status-text').textContent = message; setPermissionFeedback(message, 'ok');
      return true;
    } catch (error) {
      if (!requestScope.isCurrent(request)) return false;
      const effective = state.profile()?.effective || {};
      byId('session-profile').value = JSON.stringify(effective, null, 2);
      renderPermissions(catalog, previous);
      const message = `工具权限保存失败：${error.message}`;
      byId('status-text').textContent = message; setPermissionFeedback(message, 'error');
      return false;
    }
  }
  function renderPermissions(catalog, policy) {
    renderToolPermissions(byId('tool-permission-list'), catalog, policy, (next) => {
      void savePermissions(catalog, next, policy);
    });
  }
  // The registry changes whenever plugins are loaded or removed, so the session tab
  // needs a re-read.  It cannot reuse loadProfile(): that path writes the server
  // profile back into #session-profile and would silently discard the JSON draft the
  // user is still editing.  A refresh only re-renders the checkbox list.
  async function refreshCatalog() {
    const request = requestScope.capture('tool-registry-refresh'), id = request.sessionId, button = byId('tool-permissions-refresh');
    if (!id) {
      if (button) button.disabled = true;
      const message = '请先选择会话后再刷新工具集。';
      byId('status-text').textContent = message; setPermissionFeedback(message); return null;
    }
    if (button) button.disabled = true;
    try {
      const catalog = await api('/api/tool-registry');
      if (!requestScope.isCurrent(request)) return null;
      renderPermissions(catalog, state.profile()?.effective?.tool_permissions || {});
      const groups = catalog.categories || [], total = groups.reduce((sum, group) => sum + (group.tools || []).length, 0);
      const message = `工具集已刷新：${groups.length} 个类别、${total} 个工具。`;
      byId('status-text').textContent = message; setPermissionFeedback(message, 'ok');
      return catalog;
    } catch (error) {
      if (!requestScope.isCurrent(request)) return null;
      // Deliberately keep the list already on screen: a failed refresh must not wipe
      // the checkboxes the user was reading, and it must not reject into the caller.
      setPermissionFeedback(`工具集刷新失败：${error.message}`, 'error');
      return null;
    } finally { if (button) button.disabled = !state.sessionId(); }
  }
  // The button lives in the 会话 tab markup, so the owning controller wires it.  It is
  // bound lazily because this module is also imported by bare-node tests with no DOM.
  function syncCatalogRefreshButton() {
    const button = byId('tool-permissions-refresh'); if (!button) return;
    if (!button.onclick) button.onclick = () => { void refreshCatalog(); };
    button.disabled = !state.sessionId();
  }
  async function loadProfile() {
    const request = requestScope.capture("session-profile"), id = request.sessionId; showSession(state);
    syncCatalogRefreshButton();
    const host = byId('tool-permission-list'); host.textContent = id ? '正在加载工具权限…' : '选择会话后读取可用工具。';
    if (!id) { state.setProfile(null); byId('session-profile').value = ''; setPermissionFeedback(''); renderShellNetworkMode('isolated'); return null; }
    try {
      const [profile, catalog] = await Promise.all([api(`/api/sessions/${encodeURIComponent(id)}/run-profile`), api('/api/tool-registry')]);
      if (!requestScope.isCurrent(request)) return null;
      state.setProfile(profile); byId('session-profile').value = JSON.stringify(profile.effective || {}, null, 2);
      renderPermissions(catalog, profile.effective?.tool_permissions || {});
      setPermissionFeedback('已载入当前会话已保存的工具权限。');
      renderShellNetworkMode(profile.effective?.shell_network_mode || 'isolated'); return profile;
    } catch (error) {
      if (!requestScope.isCurrent(request)) return null;
      host.textContent = `工具权限加载失败：${error.message}`;
      throw error;
    }
  }
  return { refresh, loadProfile, refreshCatalog, async create() {
    const name = byId("new-session-name").value.trim(); if (!name) throw new Error("请输入会话名称");
    const existing = state.sessions().find((item) => item.name.trim().toLocaleLowerCase() === name.toLocaleLowerCase());
    if (existing) throw new Error(`会话“${existing.name}”已存在；请直接选择它或换一个名称。`);
    const item = await api("/api/sessions", { method: "POST", body: JSON.stringify({ name }) }); byId("new-session-name").value = "";
    await refresh(); byId("session-select").value = item.id; requestScope.select(item.id); showSession(state); return item;
  }, async remove() { const id = state.sessionId(); if (!id || byId("session-delete-confirmation").value !== id) throw new Error("删除确认必须精确等于当前会话 ID"); await api(`/api/sessions/${encodeURIComponent(id)}`, { method: "DELETE", body: JSON.stringify({ confirmation: id }) }); requestScope.select(""); await refresh(); }, async saveProfile() { const request = requestScope.capture("session-profile-save"), id = request.sessionId; if (!id) throw new Error("请先选择会话"); let settings; try { settings = JSON.parse(byId("session-profile").value); } catch { throw new Error("运行档案必须是有效 JSON"); } const profile = await api(`/api/sessions/${encodeURIComponent(id)}/run-profile`, { method: "PUT", body: JSON.stringify({ settings }) }); if (!requestScope.isCurrent(request)) return null; state.setProfile(profile); byId("session-profile").value = JSON.stringify(profile.effective || {}, null, 2); showSession(state); return profile; } };
}
