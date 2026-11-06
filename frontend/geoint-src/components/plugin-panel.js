import { api } from "../api.js";
import { escapeHtml } from "../dom.js";

/** Chinese labels for the four lifecycle states GET /api/plugins/status projects. */
const STATE_LABELS = new Map([
  ["error", "错误"],
  ["discovered", "待注册"],
  ["inactive", "已注册未加载"],
  ["active", "运行中"],
]);

/** The single lifecycle transition the backend exposes for each state. */
const STATE_ACTIONS = new Map([
  ["error", "rescan"],
  ["discovered", "register"],
  ["inactive", "load"],
  ["active", "unload"],
]);

/** Compact button captions for the action ids this panel may offer. */
const ACTION_LABELS = new Map([
  ["rescan", "重新扫描"],
  ["register", "注册"],
  ["load", "加载"],
  ["unload", "卸载"],
  ["settings", "设置"],
]);

const TRUE_WORDS = new Set(["on", "true", "1", "checked", "yes"]);
const FALSE_WORDS = new Set(["off", "false", "0", "unchecked", "no", ""]);

/** Reuse one Chinese label per lifecycle state; anything else is "未知". */
export function pluginStateLabel(state) {
  return STATE_LABELS.get(String(state ?? "")) ?? "未知";
}

/**
 * List the actions the UI may offer for one plugin status.
 *
 * Args:
 *   status: One plugin projection from GET /api/plugins/status.
 *
 * Returns:
 *   Action ids derived only from real backend state: an errored package can
 *   only be re-scanned, discovery results can only be registered, an inactive
 *   record can only be loaded, and an active one can only be unloaded. Settings
 *   are appended solely for registered, non-error records whose manifest
 *   declared `settings_enabled`, because that is exactly when
 *   GET /api/plugins/{id}/settings answers instead of 404.
 */
export function pluginActions(status) {
  const state = String(status?.state ?? "");
  const primary = STATE_ACTIONS.get(state);
  const actions = primary ? [primary] : [];
  if (status?.settings_available === true && status?.registered === true && state !== "error") actions.push("settings");
  return actions;
}

/** Format one {action,scope} permission; malformed values render as "". */
export function formatPermission(permission) {
  const action = typeof permission?.action === "string" ? permission.action.trim() : "";
  const scope = typeof permission?.scope === "string" ? permission.scope.trim() : "";
  return action && scope ? `${action} (${scope})` : "";
}

/** Durable identity for URL construction: the record id, else the manifest name. */
function pluginIdentity(status) {
  const id = typeof status?.id === "string" ? status.id.trim() : "";
  const name = typeof status?.name === "string" ? status.name.trim() : "";
  return id || name;
}

/** Human label for a card: declared display_name, else manifest name, else id. */
function pluginDisplayName(status) {
  const display = String(status?.display_name ?? "").trim();
  return display || String(status?.name ?? "").trim() || pluginIdentity(status);
}

/** Render the per-state action buttons; pluginActions() decides the set. */
function renderActions(status) {
  const buttons = pluginActions(status).map((action) => `<button type="button" class="plugin-action secondary" data-plugin-action="${escapeHtml(action)}">${escapeHtml(ACTION_LABELS.get(action) ?? action)}</button>`);
  return buttons.length ? `<div class="plugin-actions">${buttons.join("")}</div>` : "";
}

/** Render one requested permission list inside a collapsible block. */
function renderPermissions(status) {
  const requested = Array.isArray(status?.permissions_requested) ? status.permissions_requested : [];
  const items = requested.map(formatPermission).filter(Boolean);
  if (!items.length) return "";
  const rows = items.map((item) => `<span class="plugin-permission">${escapeHtml(item)}</span>`).join("");
  return `<details class="plugin-details plugin-permissions-details"><summary><span>声明的权限</span><span>${escapeHtml(items.length)}</span></summary><div class="plugin-permissions">${rows}</div></details>`;
}

/**
 * Render the plugin list as compact single-column cards.
 *
 * Args:
 *   plugins: Plugin projections from GET /api/plugins/status.
 *
 * Returns:
 *   Escaped HTML. Manifest names, versions, and backend error strings are
 *   package-authored text, so every interpolation passes through escapeHtml().
 *   Each card carries data-plugin-id (record id, else manifest name) and
 *   data-state so the mount handler can resolve the click back to one status.
 */
export function renderPluginList(plugins) {
  if (!Array.isArray(plugins) || !plugins.length) return `<p class="plugin-empty">未发现插件</p>`;
  return plugins.map((status) => {
    const id = pluginIdentity(status);
    const name = String(status?.name ?? "").trim();
    const display = pluginDisplayName(status);
    const state = String(status?.state ?? "");
    const version = String(status?.version ?? "").trim();
    const error = state === "error" ? String(status?.error ?? "").trim() : "";
    const meta = [name && name !== display ? name : "", version ? `v${version}` : ""].filter(Boolean).join(" · ");
    return `<article class="plugin-card" role="listitem" data-plugin-id="${escapeHtml(id)}" data-state="${escapeHtml(state)}"><div class="plugin-card-head"><strong class="plugin-name">${escapeHtml(display)}</strong><span class="plugin-state" data-state="${escapeHtml(state)}">${escapeHtml(pluginStateLabel(state))}</span></div>${meta ? `<p class="plugin-meta">${escapeHtml(meta)}</p>` : ""}${error ? `<p class="plugin-error" role="alert">${escapeHtml(error)}</p>` : ""}${renderPermissions(status)}${renderActions(status)}<div class="plugin-settings" hidden></div></article>`;
  }).join("");
}

/** Numeric min/max/step attributes; integers step by one, numbers accept any. */
function numberAttributes(field) {
  const parts = [`step="${String(field?.type ?? "") === "integer" ? "1" : "any"}"`];
  if (Number.isFinite(field?.minimum)) parts.push(`min="${escapeHtml(field.minimum)}"`);
  if (Number.isFinite(field?.maximum)) parts.push(`max="${escapeHtml(field.maximum)}"`);
  return parts.join(" ");
}

/** Build the input control for one declared setting field. */
function settingControl(field, value) {
  const key = escapeHtml(field.key);
  const placeholder = String(field?.placeholder ?? "").trim();
  const placeholderAttribute = placeholder ? ` placeholder="${escapeHtml(placeholder)}"` : "";
  const type = String(field?.type ?? "");
  if (type === "boolean") return `<input type="checkbox" data-setting-key="${key}" data-setting-type="boolean"${value === true ? " checked" : ""} />`;
  if (type === "integer" || type === "number") {
    const current = value === null || value === undefined ? "" : String(value);
    return `<input type="number" data-setting-key="${key}" data-setting-type="${escapeHtml(type)}" value="${escapeHtml(current)}" ${numberAttributes(field)}${placeholderAttribute} />`;
  }
  if (type === "string" && String(field?.format ?? "") === "textarea") return `<textarea rows="3" data-setting-key="${key}" data-setting-type="string" data-setting-format="textarea"${placeholderAttribute}>${escapeHtml(value ?? "")}</textarea>`;
  return `<input type="text" data-setting-key="${key}" data-setting-type="string" value="${escapeHtml(value ?? "")}"${placeholderAttribute} />`;
}

/**
 * Render one settings field as a compact labelled row.
 *
 * Args:
 *   field: Schema field metadata as returned by the backend.
 *   value: Current persisted value, or the declared default.
 *
 * Returns:
 *   Escaped HTML for exactly one field.
 */
function renderSettingField(field, value) {
  const title = String(field?.title ?? "").trim() || field.key;
  const description = String(field?.description ?? "").trim();
  const choices = Array.isArray(field?.enum) && field.enum.length ? field.enum.map(String).join("、") : "";
  const hints = [description, choices ? `可选值：${choices}` : ""].filter(Boolean).join(" ");
  return `<label class="field plugin-setting-field" data-setting-field="${escapeHtml(field.key)}"><span>${escapeHtml(title)}</span>${settingControl(field, value)}${hints ? `<small class="plugin-setting-hint">${escapeHtml(hints)}</small>` : ""}</label>`;
}

/**
 * Render the whole settings form for one plugin schema.
 *
 * Args:
 *   schema: Object keyed by setting key of {key,type,title,description,
 *     required,default,enum,minimum,maximum,format,placeholder,visible_if,
 *     sensitive} field metadata.
 *   values: Persisted settings object from GET /settings.
 *
 * Returns:
 *   Escaped HTML, or an empty string when nothing is renderable. Sensitive
 *   fields and unknown scalar types are skipped entirely so a later PUT can
 *   never echo a secret or guess at a type coercion the backend would reject.
 */
export function renderSettingsForm(schema, values = {}) {
  if (!schema || typeof schema !== "object") return "";
  const current = values && typeof values === "object" ? values : {};
  const fields = [];
  for (const [schemaKey, raw] of Object.entries(schema)) {
    if (!raw || typeof raw !== "object" || raw.sensitive === true) continue;
    const type = String(raw.type ?? "");
    if (!["boolean", "integer", "number", "string"].includes(type)) continue;
    const key = String(raw.key ?? "").trim() || String(schemaKey);
    const declared = { ...raw, key };
    fields.push(renderSettingField(declared, Object.hasOwn(current, schemaKey) ? current[schemaKey] : raw.default));
  }
  return fields.join("");
}

/** Throw the panel's Chinese validation error for one setting key. */
function invalidValue(key, reason) {
  throw new Error(`插件设置 ${key || "字段"} ${reason}`);
}

/** Coerce a checkbox-like raw value into a boolean. */
function coerceBoolean(key, raw) {
  if (typeof raw === "boolean") return raw;
  if (raw === null || raw === undefined) return false;
  if (typeof raw === "object") invalidValue(key, "的取值必须是布尔值。");
  const text = String(raw).trim().toLowerCase();
  if (TRUE_WORDS.has(text)) return true;
  if (FALSE_WORDS.has(text)) return false;
  invalidValue(key, "的取值必须是布尔值。");
}

/**
 * Coerce one raw form value into the typed scalar the backend requires.
 *
 * This is the last line of defence before PUT /settings: the backend rejects
 * wrong types, out-of-range values, and unknown enum options with a 422, so the
 * panel refuses to send them in the first place.
 *
 * Args:
 *   field: Declared schema field for this key.
 *   raw: Raw control value (string, number, boolean, null).
 *
 * Returns:
 *   Boolean, integer, number, or trimmed string.
 *
 * Raises:
 *   Error: With a Chinese message naming the field and the violated rule.
 */
export function coerceSettingValue(field, raw) {
  const key = String(field?.key ?? "").trim();
  const type = String(field?.type ?? "");
  if (type === "boolean") return coerceBoolean(key, raw);
  if (type === "integer" || type === "number") {
    if (typeof raw === "boolean" || raw === null || raw === undefined) invalidValue(key, "不能为空。");
    if (typeof raw === "string" && !raw.trim()) invalidValue(key, "不能为空。");
    const value = Number(raw);
    if (!Number.isFinite(value)) invalidValue(key, "必须是数字。");
    if (type === "integer" && !Number.isInteger(value)) invalidValue(key, "必须是整数。");
    if (field.minimum !== null && field.minimum !== undefined && value < field.minimum) invalidValue(key, `不能小于 ${field.minimum}。`);
    if (field.maximum !== null && field.maximum !== undefined && value > field.maximum) invalidValue(key, `不能大于 ${field.maximum}。`);
    return value;
  }
  if (type === "string") {
    const value = String(raw ?? "").trim();
    if (field.required === true && !value) invalidValue(key, "不能为空。");
    if (Array.isArray(field.enum) && field.enum.length && !field.enum.includes(value)) invalidValue(key, `必须是以下选项之一：${field.enum.map(String).join("、")}。`);
    return value;
  }
  return invalidValue(key, "的类型不受支持。");
}

/**
 * Mount the plugin configuration panel for the narrow left dock column.
 *
 * Only documented endpoints are called: GET /api/plugins/status for the list,
 * POST /api/plugins/rescan, POST /api/plugins/discovered/{name}/register,
 * POST /api/plugins/{id}/load, POST /api/plugins/{id}/unload, and
 * GET/PUT /api/plugins/{id}/settings. Code execution and permission grants are
 * always explicit in the request body, and unload additionally asks the user.
 * Every failure is rendered in the panel and mirrored through onStatus so a
 * rejected write can never look like success.
 *
 * Args:
 *   root: Panel host element inside the plugins tab.
 *   options.onStatus: Callback for the shell status bar messages.
 *
 * Returns:
 *   `refresh()` handle used by the dock tab lifecycle.
 */
export function mountPluginPanel(root, { onStatus = () => {} } = {}) {
  let plugins = [], loading = false;
  const settingsCache = new Map();
  if (!root) return { refresh() {} };
  root.innerHTML = `<div class="section-title compact"><div><span class="eyebrow">PLUGIN DECK</span><h3>插件</h3></div><div class="action-group"><button type="button" class="plugin-rescan secondary">重新扫描</button></div></div><p class="fineprint">插件来自受信任的插件目录。注册只登记校验过的清单，加载会执行插件入口代码并授予其声明的权限，卸载保留安装包与已保存设置。</p><div class="plugin-error" role="alert" hidden></div><div class="plugin-list" role="list" aria-live="polite"><p class="plugin-empty">尚未读取插件状态</p></div>`;
  const list = root.querySelector(".plugin-list");
  const errorBox = root.querySelector(".plugin-error");
  const rescanButton = root.querySelector(".plugin-rescan");
  const setError = (message = "") => { errorBox.textContent = message; errorBox.hidden = !message; };
  const fail = (message) => { setError(message); onStatus(message); };

  function setBusy(busy) {
    loading = busy;
    root.setAttribute("aria-busy", busy ? "true" : "false");
    root.classList.toggle("plugin-loading", busy);
    for (const button of root.querySelectorAll("button")) button.disabled = busy;
  }

  function renderList() {
    settingsCache.clear();
    list.innerHTML = renderPluginList(plugins);
    if (loading) for (const button of list.querySelectorAll("button")) button.disabled = true;
  }

  async function run(task) {
    if (loading) return null;
    setBusy(true);
    try { return await task(); }
    finally { setBusy(false); }
  }

  async function fetchStatus() {
    try {
      const payload = await api("/api/plugins/status");
      plugins = Array.isArray(payload?.plugins) ? payload.plugins : [];
    } catch (caught) {
      plugins = [];
      renderList();
      fail(`插件状态读取失败：${caught.message}`);
      return null;
    }
    renderList();
    return plugins;
  }

  function refresh() {
    return run(fetchStatus);
  }

  async function runAction(task, failure) {
    return run(async () => {
      setError("");
      let message = "";
      try {
        message = await task();
      } catch (caught) {
        fail(`${failure}：${caught.message}`);
        return false;
      }
      await fetchStatus();
      if (message) onStatus(message);
      return true;
    });
  }

  async function openSettings(card, status) {
    const id = pluginIdentity(status);
    const host = card.querySelector(".plugin-settings");
    if (!id || !host) { fail("插件设置读取失败：缺少插件标识。"); return; }
    await run(async () => {
      setError("");
      try {
        const payload = await api(`/api/plugins/${encodeURIComponent(id)}/settings`);
        const schema = payload?.settings_schema && typeof payload.settings_schema === "object" ? payload.settings_schema : {};
        const values = payload?.settings && typeof payload.settings === "object" ? payload.settings : {};
        const name = String(payload?.name ?? status?.name ?? "").trim() || pluginDisplayName(status);
        const form = renderSettingsForm(schema, values);
        settingsCache.set(id, { name, schema });
        host.innerHTML = form
          ? `<div class="plugin-settings-form">${form}</div><div class="plugin-settings-footer"><button type="button" class="plugin-save primary" data-plugin-save="settings">保存</button></div>`
          : `<p class="plugin-empty">该插件没有可配置的设置项</p>`;
        host.hidden = false;
      } catch (caught) {
        host.hidden = true;
        host.innerHTML = "";
        fail(`插件设置读取失败：${caught.message}`);
      }
    });
  }

  async function saveSettings(card) {
    const id = String(card?.dataset.pluginId ?? "");
    const host = card?.querySelector(".plugin-settings");
    const cached = settingsCache.get(id);
    if (!id || !host || !cached) return;
    const controls = [...host.querySelectorAll("[data-setting-key]")];
    if (!controls.length) return;
    const values = {};
    try {
      for (const control of controls) {
        const key = String(control.dataset.settingKey ?? "");
        const field = cached.schema[key] || { key, type: "" };
        values[key] = coerceSettingValue(field, control.type === "checkbox" ? control.checked : control.value);
      }
    } catch (caught) {
      fail(`插件设置未保存：${caught.message}`);
      return;
    }
    const saved = await runAction(async () => {
      await api(`/api/plugins/${encodeURIComponent(id)}/settings`, { method: "PUT", body: JSON.stringify(values) });
      return `插件“${cached.name}”的设置已保存。`;
    }, "插件设置保存失败");
    if (!saved) return;
    // Re-read the persisted projection so the reopened form shows what the
    // backend actually stored instead of the pre-save draft.
    const nextCard = [...list.querySelectorAll("[data-plugin-id]")].find((item) => item.dataset.pluginId === id);
    const nextStatus = plugins.find((item) => pluginIdentity(item) === id);
    if (nextCard && nextStatus) await openSettings(nextCard, nextStatus);
  }

  function handleAction(button, card) {
    const status = plugins.find((item) => pluginIdentity(item) === String(card?.dataset.pluginId ?? ""));
    if (!status) { fail("插件操作失败：该插件已不在当前列表中。"); return; }
    const action = String(button.dataset.pluginAction ?? "");
    const id = pluginIdentity(status);
    const display = pluginDisplayName(status);
    if (action === "rescan") {
      runAction(async () => { await api("/api/plugins/rescan", { method: "POST" }); return "插件目录已重新扫描。"; }, "插件扫描失败");
      return;
    }
    if (action === "register") {
      const name = String(status.name ?? "").trim();
      if (!name) { fail("插件注册失败：缺少清单名称。"); return; }
      runAction(async () => {
        await api(`/api/plugins/discovered/${encodeURIComponent(name)}/register`, { method: "POST", body: JSON.stringify({ confirm: true }) });
        return `插件“${display}”已注册。`;
      }, "插件注册失败");
      return;
    }
    if (action === "load") {
      if (!id) { fail("插件加载失败：缺少插件标识。"); return; }
      runAction(async () => {
        await api(`/api/plugins/${encodeURIComponent(id)}/load`, { method: "POST", body: JSON.stringify({ confirm: true, grant_permissions: true }) });
        return `插件“${display}”已加载。`;
      }, "插件加载失败");
      return;
    }
    if (action === "unload") {
      if (!id) { fail("插件卸载失败：缺少插件标识。"); return; }
      if (!globalThis.confirm(`卸载插件“${display}”？卸载后可再次加载，已保存的设置会保留。`)) return;
      runAction(async () => {
        await api(`/api/plugins/${encodeURIComponent(id)}/unload`, { method: "POST", body: JSON.stringify({ confirm: true }) });
        return `插件“${display}”已卸载。`;
      }, "插件卸载失败");
      return;
    }
    if (action === "settings") openSettings(card, status);
  }

  rescanButton.addEventListener("click", () => {
    runAction(async () => { await api("/api/plugins/rescan", { method: "POST" }); return "插件目录已重新扫描。"; }, "插件扫描失败");
  });
  list.addEventListener("click", (event) => {
    const target = event.target;
    const save = target?.closest?.("[data-plugin-save]");
    if (save) { saveSettings(save.closest("[data-plugin-id]")); return; }
    const button = target?.closest?.("[data-plugin-action]");
    if (!button) return;
    handleAction(button, button.closest("[data-plugin-id]"));
  });

  return { refresh };
}
