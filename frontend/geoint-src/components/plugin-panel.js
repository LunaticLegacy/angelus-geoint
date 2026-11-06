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
 *   Declared panels and themes come from the same projection, so a card never
 *   needs a second round-trip to discover what the plugin offers.
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
    return `<article class="plugin-card" role="listitem" data-plugin-id="${escapeHtml(id)}" data-state="${escapeHtml(state)}"><div class="plugin-card-head"><strong class="plugin-name">${escapeHtml(display)}</strong><span class="plugin-state" data-state="${escapeHtml(state)}">${escapeHtml(pluginStateLabel(state))}</span></div>${meta ? `<p class="plugin-meta">${escapeHtml(meta)}</p>` : ""}${error ? `<p class="plugin-error" role="alert">${escapeHtml(error)}</p>` : ""}${renderPermissions(status)}${renderThemeSummary(status)}${renderActions(status)}${renderPluginPanels(status)}<div class="plugin-settings" hidden></div></article>`;
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
function invalidValue(key, reason, prefix = "插件设置") {
  throw new Error(`${prefix} ${key || "字段"} ${reason}`);
}

/** Coerce a checkbox-like raw value into a boolean. */
function coerceBoolean(key, raw, prefix = "插件设置") {
  if (typeof raw === "boolean") return raw;
  if (raw === null || raw === undefined) return false;
  if (typeof raw === "object") invalidValue(key, "的取值必须是布尔值。", prefix);
  const text = String(raw).trim().toLowerCase();
  if (TRUE_WORDS.has(text)) return true;
  if (FALSE_WORDS.has(text)) return false;
  invalidValue(key, "的取值必须是布尔值。", prefix);
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

/** Chinese captions for the two theme modes a manifest may declare. */
const THEME_MODE_LABELS = new Map([
  ["dark", "深色"],
  ["light", "浅色"],
]);

/** Result tones the host styles; anything else degrades to `info`. */
const PANEL_TONES = new Set(["info", "success", "error"]);

/** Scalar kinds a transient panel field may declare, mirroring PluginPanelField. */
const PANEL_TYPES = new Set(["string", "integer", "number", "boolean"]);

/**
 * Normalise the transient fields one declarative panel declared.
 *
 * Args:
 *   fields: `fields` array of one projection from GET /api/plugins/status.
 *
 * Returns:
 *   Fields carrying a usable key and one supported scalar kind. Unknown kinds
 *   are dropped instead of guessed at, because the backend would reject the
 *   invoke body with a 422 rather than coerce it.
 */
export function panelFields(fields) {
  const declared = Array.isArray(fields) ? fields : [];
  const result = [];
  for (const field of declared) {
    if (!field || typeof field !== "object") continue;
    const key = String(field.key ?? "").trim();
    const type = String(field.type ?? "");
    if (!key || !PANEL_TYPES.has(type)) continue;
    result.push({ ...field, key, type });
  }
  return result;
}

/**
 * Normalise the declarative panels one plugin projection carries.
 *
 * Args:
 *   status: One plugin projection from GET /api/plugins/status.
 *
 * Returns:
 *   `{id,title,description,submitLabel,fields}` records for every panel that
 *   declared a usable id. Panels are metadata only: the backend never exposes
 *   the action id or handler through this projection, and the host only ever
 *   calls the documented invoke route.
 */
export function pluginPanels(status) {
  const declared = Array.isArray(status?.panels) ? status.panels : [];
  const result = [];
  for (const panel of declared) {
    if (!panel || typeof panel !== "object") continue;
    const id = String(panel.id ?? "").trim();
    if (!id) continue;
    result.push({
      id,
      title: String(panel.title ?? "").trim() || id,
      description: String(panel.description ?? "").trim(),
      submitLabel: String(panel.submit_label ?? "").trim() || "提交",
      fields: panelFields(panel.fields),
    });
  }
  return result;
}

/**
 * Normalise the read-only theme summary one plugin projection carries.
 *
 * Args:
 *   status: One plugin projection from GET /api/plugins/status.
 *
 * Returns:
 *   `{id,title,asset,mode}` records for every declared skin. The asset name is
 *   package-relative metadata; this panel never injects it, it only lists it.
 */
export function pluginThemes(status) {
  const declared = Array.isArray(status?.themes) ? status.themes : [];
  const result = [];
  for (const theme of declared) {
    if (!theme || typeof theme !== "object") continue;
    const id = String(theme.id ?? "").trim();
    if (!id) continue;
    result.push({
      id,
      title: String(theme.title ?? "").trim() || id,
      asset: String(theme.asset ?? "").trim(),
      mode: String(theme.mode ?? "").trim(),
    });
  }
  return result;
}

/**
 * Build the documented invoke path for one plugin panel.
 *
 * Args:
 *   pluginId: Durable plugin identity (record id, else manifest name).
 *   panelId: Manifest-declared panel identity.
 *
 * Returns:
 *   `POST /api/plugins/{plugin_id}/panels/{panel_id}/invoke`, or an empty
 *   string when either identity is missing. Both segments are percent-encoded
 *   so an id containing a slash cannot address a different route.
 */
export function panelInvokePath(pluginId, panelId) {
  const id = String(pluginId ?? "").trim();
  const panel = String(panelId ?? "").trim();
  if (!id || !panel) return "";
  return `/api/plugins/${encodeURIComponent(id)}/panels/${encodeURIComponent(panel)}/invoke`;
}

/**
 * Coerce and validate one raw panel control value.
 *
 * Mirrors `PluginManager._validate_fields()` for transient panel input: the
 * same scalar kinds, the same enum membership check, and the same inclusive
 * bounds, so a rejected submit is reported inside the panel instead of as a 422
 * round-trip. `format` is a renderer hint only (`uri` and `path` are not
 * re-validated here, exactly like the backend), and a sensitive field is never
 * filled from a declared default.
 *
 * Args:
 *   field: One field record from `panelFields()`.
 *   raw: Raw control value (string, number, boolean, null).
 *
 * Returns:
 *   Boolean, integer, number, or trimmed string.
 *
 * Raises:
 *   Error: With a Chinese message naming the field and the violated rule.
 */
export function coercePanelValue(field, raw) {
  const key = String(field?.key ?? "").trim();
  const type = String(field?.type ?? "");
  if (type === "boolean") return coerceBoolean(key, raw, "插件面板");
  if (type === "integer" || type === "number") {
    if (typeof raw === "boolean" || raw === null || raw === undefined) invalidValue(key, "不能为空。", "插件面板");
    if (typeof raw === "string" && !raw.trim()) invalidValue(key, "不能为空。", "插件面板");
    const value = Number(raw);
    if (!Number.isFinite(value)) invalidValue(key, "必须是数字。", "插件面板");
    if (type === "integer" && !Number.isInteger(value)) invalidValue(key, "必须是整数。", "插件面板");
    if (field.minimum !== null && field.minimum !== undefined && value < field.minimum) invalidValue(key, `不能小于 ${field.minimum}。`, "插件面板");
    if (field.maximum !== null && field.maximum !== undefined && value > field.maximum) invalidValue(key, `不能大于 ${field.maximum}。`, "插件面板");
    return value;
  }
  if (type === "string") {
    const value = String(raw ?? "").trim();
    if (field.required === true && !value) invalidValue(key, "不能为空。", "插件面板");
    if (field.sensitive === true && !value) invalidValue(key, "不能为空。", "插件面板");
    if (Array.isArray(field.enum) && field.enum.length && !field.enum.includes(value)) invalidValue(key, `必须是以下选项之一：${field.enum.map(String).join("、")}。`, "插件面板");
    return value;
  }
  return invalidValue(key, "的类型不受支持。", "插件面板");
}

/**
 * Build the flat invoke body for one panel from raw control values.
 *
 * Args:
 *   fields: Fields of the panel being submitted (raw or normalised).
 *   rawValues: Object keyed by field key holding raw control values.
 *
 * Returns:
 *   A flat `{key: scalar}` body containing only declared keys, so the backend
 *   never has to reject an unknown field. Optional blank inputs are omitted so
 *   the declared manifest default applies (`defaults=True` on the backend); a
 *   blank required field fails here instead of costing a round-trip.
 *
 * Raises:
 *   Error: With a Chinese validation message for the first offending field.
 */
export function buildPanelPayload(fields, rawValues = {}) {
  const declared = panelFields(fields);
  const raw = rawValues && typeof rawValues === "object" ? rawValues : {};
  const payload = {};
  for (const field of declared) {
    const value = Object.hasOwn(raw, field.key) ? raw[field.key] : undefined;
    const blank = value === null || value === undefined || (typeof value === "string" && !value.trim());
    if (blank) {
      if (field.required === true) invalidValue(field.key, "不能为空。", "插件面板");
      // An unchecked checkbox is a real `false`, never an omitted key, so the
      // action sees the same value the user saw.
      if (field.type === "boolean") payload[field.key] = false;
      continue;
    }
    payload[field.key] = coercePanelValue(field, value);
  }
  return payload;
}

/** Numeric bounds for one panel number input; integers step by one. */
function panelNumberAttributes(field) {
  const parts = [`step="${field?.type === "integer" ? "1" : "any"}"`];
  if (Number.isFinite(field?.minimum)) parts.push(`min="${escapeHtml(field.minimum)}"`);
  if (Number.isFinite(field?.maximum)) parts.push(`max="${escapeHtml(field.maximum)}"`);
  return parts.join(" ");
}

/**
 * Build the single control for one declared panel field.
 *
 * Args:
 *   field: One field record from `panelFields()`.
 *
 * Returns:
 *   Escaped HTML for exactly one control. `enum` always becomes a `<select>`;
 *   `format` picks textarea/url/path/password; a `sensitive` field is forced to
 *   a password control with no value at all, even if a malformed projection
 *   still carried a default. `required` is exposed as `aria-required` because
 *   the helper markup is not a `<form>` and the enforcement is `buildPanelPayload`.
 */
function panelControl(field) {
  const key = escapeHtml(field.key);
  const type = escapeHtml(field.type);
  const format = String(field?.format ?? "");
  const placeholder = String(field?.placeholder ?? "").trim();
  const placeholderAttribute = placeholder ? ` placeholder="${escapeHtml(placeholder)}"` : "";
  const requiredAttribute = field?.required === true ? ` aria-required="true"` : "";
  const common = `data-panel-key="${key}" data-panel-type="${type}"`;
  const declared = field?.default === null || field?.default === undefined ? "" : String(field.default);
  if (field?.sensitive === true) return `<input type="password" ${common} data-panel-format="password" value="" autocomplete="off"${placeholderAttribute}${requiredAttribute} />`;
  if (Array.isArray(field?.enum) && field.enum.length) {
    const options = field.enum.map(String);
    const rows = options.map((item) => `<option value="${escapeHtml(item)}"${item === declared ? " selected" : ""}>${escapeHtml(item)}</option>`);
    if (!declared) rows.unshift(`<option value="">请选择</option>`);
    return `<select ${common} data-panel-enum="1"${requiredAttribute}>${rows.join("")}</select>`;
  }
  if (field.type === "boolean") return `<input type="checkbox" ${common}${field?.default === true ? " checked" : ""} />`;
  if (field.type === "integer" || field.type === "number") return `<input type="number" ${common} value="${escapeHtml(declared)}" ${panelNumberAttributes(field)}${placeholderAttribute}${requiredAttribute} />`;
  if (format === "textarea") return `<textarea rows="3" ${common} data-panel-format="textarea"${placeholderAttribute}${requiredAttribute}>${escapeHtml(declared)}</textarea>`;
  if (format === "password") return `<input type="password" ${common} data-panel-format="password" value="" autocomplete="off"${placeholderAttribute}${requiredAttribute} />`;
  if (format === "uri") return `<input type="url" ${common} data-panel-format="uri" value="${escapeHtml(declared)}"${placeholderAttribute}${requiredAttribute} />`;
  if (format === "path") return `<input type="text" ${common} data-panel-format="path" value="${escapeHtml(declared)}"${placeholderAttribute}${requiredAttribute} />`;
  return `<input type="text" ${common} value="${escapeHtml(declared)}"${placeholderAttribute}${requiredAttribute} />`;
}

/**
 * Render one panel field as a labelled row.
 *
 * Args:
 *   field: One field record from `panelFields()`.
 *
 * Returns:
 *   Escaped HTML for exactly one field, including its hint line.
 */
export function renderPanelField(field) {
  const title = String(field?.title ?? "").trim() || String(field?.key ?? "").trim();
  const description = String(field?.description ?? "").trim();
  const hints = [
    description,
    field?.required === true ? "必填" : "",
    field?.sensitive === true ? "仅本次提交使用，不会保存。" : "",
  ].filter(Boolean).join(" ");
  const attributes = [
    `data-panel-field="${escapeHtml(field?.key ?? "")}"`,
    field?.required === true ? `data-panel-required="1"` : "",
    field?.sensitive === true ? `data-panel-sensitive="1"` : "",
  ].filter(Boolean).join(" ");
  return `<label class="plugin-panel-field" ${attributes}><span>${escapeHtml(title)}</span>${panelControl(field)}${hints ? `<small class="plugin-panel-hint">${escapeHtml(hints)}</small>` : ""}</label>`;
}

/**
 * Render one declarative panel: title, description, inputs, submit, and the
 * two live regions the mount handler writes into.
 *
 * Args:
 *   panel: Raw projection panel or one record from `pluginPanels()`.
 *
 * Returns:
 *   Escaped HTML, or an empty string when the panel declared no usable id.
 */
export function renderPanelForm(panel) {
  const id = String(panel?.id ?? "").trim();
  if (!id) return "";
  const title = String(panel?.title ?? "").trim() || id;
  const description = String(panel?.description ?? "").trim();
  const label = String(panel?.submit_label ?? panel?.submitLabel ?? "").trim() || "提交";
  const controls = panelFields(panel?.fields);
  const fields = controls.length
    ? `<div class="plugin-panel-fields">${controls.map(renderPanelField).join("")}</div>`
    : `<p class="plugin-panel-hint">该面板没有输入字段</p>`;
  return `<section class="plugin-panel" data-panel-id="${escapeHtml(id)}"><div class="plugin-panel-head"><strong class="plugin-panel-title">${escapeHtml(title)}</strong></div>${description ? `<p class="plugin-panel-description">${escapeHtml(description)}</p>` : ""}${fields}<div class="plugin-panel-footer"><button type="button" class="primary plugin-panel-submit" data-panel-submit="${escapeHtml(id)}">${escapeHtml(label)}</button></div><div class="plugin-panel-error" role="alert" hidden></div><div class="plugin-panel-result" aria-live="polite" hidden></div></section>`;
}

/**
 * Render every panel one plugin projection declared.
 *
 * Args:
 *   status: One plugin projection from GET /api/plugins/status.
 *
 * Returns:
 *   Escaped HTML, or an empty string when no panel was declared. Only an
 *   `active` record gets submittable forms: POST /…/invoke answers 404 unless
 *   the plugin is loaded, so the loadable note keeps the card honest instead of
 *   offering a button that cannot work.
 */
export function renderPluginPanels(status) {
  const panels = pluginPanels(status);
  if (!panels.length) return "";
  if (String(status?.state ?? "") !== "active") return `<p class="plugin-panel-note">声明了 ${escapeHtml(panels.length)} 个功能面板，插件加载后可提交。</p>`;
  return `<div class="plugin-panels">${panels.map(renderPanelForm).join("")}</div>`;
}

/**
 * Render the read-only theme summary one plugin declared.
 *
 * Args:
 *   status: One plugin projection from GET /api/plugins/status.
 *
 * Returns:
 *   Escaped HTML, or an empty string when the plugin ships no skins. Themes are
 *   listed only: the host never injects a plugin-provided stylesheet here.
 */
export function renderThemeSummary(status) {
  const themes = pluginThemes(status);
  if (!themes.length) return "";
  const rows = themes.map((theme) => {
    const mode = theme.mode ? ` · ${THEME_MODE_LABELS.get(theme.mode) ?? theme.mode}` : "";
    return `<span class="plugin-theme" data-theme-id="${escapeHtml(theme.id)}" data-theme-mode="${escapeHtml(theme.mode)}">${escapeHtml(theme.title)}${escapeHtml(mode)}</span>`;
  }).join("");
  return `<details class="plugin-details plugin-themes-details"><summary><span>声明的主题</span><span>${escapeHtml(themes.length)}</span></summary><div class="plugin-themes">${rows}</div><p class="plugin-theme-note">只读：主题样式由插件包提供。</p></details>`;
}

/**
 * Render one panel action result (`{title,content,tone}`) from POST /…/invoke.
 *
 * Args:
 *   result: JSON body returned by the invoke route.
 *
 * Returns:
 *   Escaped HTML, or an empty string when the body carries neither field. The
 *   content is plugin-authored text, so it is always escaped and `tone` only
 *   ever selects one of the three known style classes.
 */
export function panelResultView(result) {
  if (!result || typeof result !== "object") return "";
  const title = String(result.title ?? "").trim();
  const content = String(result.content ?? "");
  const raw = String(result.tone ?? "");
  const tone = PANEL_TONES.has(raw) ? raw : "info";
  if (!title && !content) return "";
  const heading = title ? `<strong class="plugin-panel-result-title">${escapeHtml(title)}</strong>` : "";
  const body = content ? `<p class="plugin-panel-result-content">${escapeHtml(content)}</p>` : "";
  return `<div class="plugin-panel-result-body plugin-tone-${tone}" data-tone="${tone}">${heading}${body}</div>`;
}

/**
 * Mount the plugin configuration panel for the narrow left dock column.
 *
 * Only documented endpoints are called: GET /api/plugins/status for the list,
 * POST /api/plugins/rescan, POST /api/plugins/discovered/{name}/register,
 * POST /api/plugins/{id}/load, POST /api/plugins/{id}/unload,
 * GET/PUT /api/plugins/{id}/settings, and
 * POST /api/plugins/{id}/panels/{panel_id}/invoke. Code execution and permission grants are
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

  /** Read the raw control values of one rendered panel, keyed by field key. */
  function readPanelValues(section) {
    const values = {};
    for (const control of section.querySelectorAll("[data-panel-key]")) {
      const key = String(control.dataset.panelKey ?? "");
      if (!key) continue;
      values[key] = control.type === "checkbox" ? control.checked : control.value;
    }
    return values;
  }

  /**
   * Validate and submit one declarative panel, then render its action result.
   *
   * Validation runs before the request so a rejected field never costs a
   * round-trip, and both validation failures and invoke errors land in the
   * panel's own role="alert" slot (and through onStatus) instead of vanishing.
   */
  async function submitPanel(section) {
    if (!section) { fail("插件面板提交失败：缺少面板节点。"); return; }
    const id = String(section.closest("[data-plugin-id]")?.dataset.pluginId ?? "");
    const panelId = String(section.dataset.panelId ?? "");
    const status = plugins.find((item) => pluginIdentity(item) === id);
    const panel = pluginPanels(status).find((item) => item.id === panelId);
    const panelError = section.querySelector(".plugin-panel-error");
    const resultBox = section.querySelector(".plugin-panel-result");
    const setPanelError = (message = "") => { if (panelError) { panelError.textContent = message; panelError.hidden = !message; } };
    setError("");
    setPanelError("");
    if (resultBox) { resultBox.innerHTML = ""; resultBox.hidden = true; }
    const path = panelInvokePath(id, panelId);
    if (!panel || !path) {
      setPanelError("插件面板提交失败：该面板已不在当前插件声明中。");
      onStatus("插件面板提交失败：该面板已不在当前插件声明中。");
      return;
    }
    let body;
    try {
      body = buildPanelPayload(panel.fields, readPanelValues(section));
    } catch (caught) {
      setPanelError(caught.message);
      onStatus(caught.message);
      return;
    }
    await run(async () => {
      try {
        const payload = await api(path, { method: "POST", body: JSON.stringify(body) });
        if (resultBox) { resultBox.innerHTML = panelResultView(payload); resultBox.hidden = false; }
        onStatus(`插件面板“${panel.title}”已提交。`);
      } catch (caught) {
        const message = `插件面板提交失败：${caught.message}`;
        setPanelError(message);
        onStatus(message);
      }
    });
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
    const submit = target?.closest?.("[data-panel-submit]");
    if (submit) { submitPanel(submit.closest("[data-panel-id]")); return; }
    const button = target?.closest?.("[data-plugin-action]");
    if (!button) return;
    handleAction(button, button.closest("[data-plugin-id]"));
  });

  return { refresh };
}
