import { api } from "../api.js";
import { escapeHtml } from "../dom.js";

/** Endpoint holding the global default run profile. */
const GLOBAL_PROFILE_PATH = "/api/settings/run-profile";
/** Catalog used to populate the `context_handler` select. */
const CONTEXT_HANDLERS_PATH = "/api/context-handlers";
/** A Session override below this threshold is rejected by RunProfileStore. */
export const SESSION_CONTEXT_THRESHOLD_MINIMUM = 1024;

/**
 * Documented defaults for every rendered field.
 *
 * Mirrors `DEFAULT_RUN_PROFILE` in `profile_store.py` for the scalar keys this
 * form renders; object-valued and list-valued keys stay deliberately absent
 * because the panel never authors them (see `buildProfilePayload`).
 */
export const RUN_PROFILE_DEFAULTS = Object.freeze({
  temperature: 0.4,
  thinking_mode: "auto",
  reasoning_effort: "auto",
  max_tokens: 32768,
  max_rounds: 0,
  max_retries: 3,
  request_timeout_seconds: 60,
  shell_network_mode: "host_network",
  max_context_threshold: 262144,
  compaction_output_max_tokens: 16384,
  context_keep_recent: 0,
  tool_result_context_limit: 0,
  max_swarm_agents: 4,
  // `DEFAULT_CONTEXT_HANDLER` in llmfetcher; an unknown persisted id is kept
  // readable instead of being silently rewritten to this value.
  context_handler: "linear",
});

/**
 * Ordered descriptor list for every field this panel renders.
 *
 * Each descriptor carries `{key,title,type,enum,minimum,maximum,step,group,
 * advanced}`. `type` is one of `number` | `integer` | `select` | `text`;
 * `minimum`/`maximum` are `null` where the backend defines no bound, and
 * `enum` is `null` for selects whose options are supplied at render time
 * (`context_handler` comes from `GET /api/context-handlers`).
 *
 * Keys that are *not* listed here (`tool_permissions`, `agent_overrides`,
 * `context_handler_settings`, `context_block_order`, `session_memory_*`,
 * `system_prompt`, legacy connector fields) are unrendered and therefore have
 * to survive a save verbatim — see `buildProfilePayload`.
 */
export const RUN_PROFILE_FIELDS = Object.freeze([
  { key: "temperature", title: "温度", type: "number", enum: null, minimum: 0, maximum: 2, step: 0.1, group: "采样", advanced: false },
  { key: "max_tokens", title: "最大输出 tokens", type: "integer", enum: null, minimum: 1, maximum: null, step: 1, group: "采样", advanced: false },
  { key: "thinking_mode", title: "思考模式", type: "select", enum: ["auto", "on", "off"], minimum: null, maximum: null, step: null, group: "采样", advanced: false },
  { key: "reasoning_effort", title: "推理强度", type: "select", enum: ["auto", "low", "medium", "high"], minimum: null, maximum: null, step: null, group: "采样", advanced: false },
  { key: "max_rounds", title: "最大轮次（0 = 不限制）", type: "integer", enum: null, minimum: 0, maximum: null, step: 1, group: "推理", advanced: true },
  { key: "max_retries", title: "失败重试次数", type: "integer", enum: null, minimum: 0, maximum: null, step: 1, group: "推理", advanced: true },
  { key: "request_timeout_seconds", title: "请求超时（秒）", type: "number", enum: null, minimum: 1, maximum: 3600, step: 1, group: "推理", advanced: false },
  { key: "max_swarm_agents", title: "最大 Swarm 代理数", type: "integer", enum: null, minimum: 0, maximum: null, step: 1, group: "推理", advanced: true },
  { key: "max_context_threshold", title: "上下文压缩阈值（tokens）", type: "integer", enum: null, minimum: 0, maximum: null, step: 1, group: "上下文", advanced: false },
  // RunProfileStore additionally requires >= 1 for both compaction budgets.
  { key: "compaction_output_max_tokens", title: "压缩输出上限（tokens）", type: "integer", enum: null, minimum: 1, maximum: null, step: 1, group: "上下文", advanced: true },
  { key: "context_keep_recent", title: "保留最近消息数", type: "integer", enum: null, minimum: 0, maximum: null, step: 1, group: "上下文", advanced: true },
  { key: "tool_result_context_limit", title: "工具结果上下文上限", type: "integer", enum: null, minimum: 0, maximum: null, step: 1, group: "上下文", advanced: true },
  { key: "context_handler", title: "上下文处理器", type: "select", enum: null, minimum: null, maximum: null, step: null, group: "上下文", advanced: false },
  { key: "shell_network_mode", title: "Shell 网络模式", type: "select", enum: ["isolated", "host_network"], minimum: null, maximum: null, step: null, group: "工具", advanced: false },
]);

/** Chinese captions for the closed vocabularies the backend accepts. */
const ENUM_LABELS = new Map([
  ["thinking_mode:auto", "自动"],
  ["thinking_mode:on", "开启"],
  ["thinking_mode:off", "关闭"],
  ["reasoning_effort:auto", "自动"],
  ["reasoning_effort:low", "低"],
  ["reasoning_effort:medium", "中"],
  ["reasoning_effort:high", "高"],
  ["shell_network_mode:isolated", "隔离沙箱"],
  ["shell_network_mode:host_network", "宿主网络"],
]);

/**
 * Build the profile URL for one scope.
 *
 * Args:
 *   scope: `"global"` or `"session"`.
 *   sessionId: Selected Session; an empty value always falls back to global.
 *
 * Returns:
 *   The documented profile path. A Session id is percent-encoded so an id with
 *   a slash cannot address a different route.
 */
export function profileScopePath(scope, sessionId = "") {
  const id = String(sessionId ?? "").trim();
  if (scope === "global" || !id) return GLOBAL_PROFILE_PATH;
  return `/api/sessions/${encodeURIComponent(id)}/run-profile`;
}

/** Copy one JSON-ish value so payloads never alias the loaded profile. */
function cloneProfileValue(value) {
  if (Array.isArray(value)) return value.map(cloneProfileValue);
  if (value && typeof value === "object") {
    const copy = {};
    for (const [key, item] of Object.entries(value)) copy[key] = cloneProfileValue(item);
    return copy;
  }
  return value;
}

/** Coerce one raw value to a finite number, rounding integer fields. */
function coerceNumber(raw, integer) {
  let parsed;
  if (typeof raw === "number") parsed = raw;
  else if (typeof raw === "string" && raw.trim()) parsed = Number(raw.trim());
  else return null;
  if (!Number.isFinite(parsed)) return null;
  return integer ? Math.round(parsed) : parsed;
}

/**
 * Reduce an effective profile to the draft this form owns.
 *
 * Args:
 *   effective: `effective` object from either profile endpoint.
 *
 * Returns:
 *   A new plain object containing exactly the rendered keys, coerced to the
 *   declared types and clamped into the documented bounds. Missing, null or
 *   unparseable values fall back to `RUN_PROFILE_DEFAULTS`, and unknown keys
 *   are never copied, so the draft can be posted without leaking a partial
 *   view of the profile back to the API.
 */
export function clampProfileDraft(effective) {
  const source = effective && typeof effective === "object" ? effective : {};
  const draft = {};
  for (const field of RUN_PROFILE_FIELDS) {
    const fallback = RUN_PROFILE_DEFAULTS[field.key];
    const raw = source[field.key];
    if (field.type === "number" || field.type === "integer") {
      let value = coerceNumber(raw, field.type === "integer");
      if (value === null) value = fallback;
      if (Number.isFinite(field.minimum)) value = Math.max(field.minimum, value);
      if (Number.isFinite(field.maximum)) value = Math.min(field.maximum, value);
      draft[field.key] = value;
    } else if (field.type === "select") {
      const text = typeof raw === "string" ? raw.trim() : "";
      if (Array.isArray(field.enum)) draft[field.key] = field.enum.includes(text) ? text : fallback;
      else draft[field.key] = text || fallback;
    } else {
      const text = raw === null || raw === undefined ? "" : String(raw).trim();
      draft[field.key] = text || fallback;
    }
  }
  return draft;
}

/**
 * Merge the edited draft into the full effective profile.
 *
 * `PUT /run-profile` is a whole-object replace, so anything the form does not
 * render must be carried over untouched: tool permissions, per-Agent
 * overrides, context handler settings, block order, session memory lists and
 * the legacy connector fields would otherwise be wiped on every save.
 *
 * Args:
 *   effective: `effective` object the form was rendered from.
 *   draft: Values for the rendered keys only (usually `clampProfileDraft`
 *     output or validated form values).
 *
 * Returns:
 *   A deep-cloned copy of `effective` with only the rendered keys overwritten.
 *   Neither input is mutated and the clone shares no structure with
 *   `effective`.
 */
export function buildProfilePayload(effective, draft) {
  const base = effective && typeof effective === "object" && !Array.isArray(effective) ? cloneProfileValue(effective) : {};
  const source = draft && typeof draft === "object" ? draft : {};
  for (const field of RUN_PROFILE_FIELDS) {
    if (!Object.prototype.hasOwnProperty.call(source, field.key)) continue;
    base[field.key] = cloneProfileValue(source[field.key]);
  }
  return base;
}

/**
 * Validate one edited value without throwing.
 *
 * Args:
 *   field: One `RUN_PROFILE_FIELDS` descriptor.
 *   raw: Raw control value (usually a string from the DOM).
 *   options.scope: Scope being edited; `"session"` additionally enforces the
 *     1024 token floor on `max_context_threshold`.
 *
 * Returns:
 *   `{ok:true,value}` with the coerced value, or `{ok:false,message}` with a
 *   Chinese message that is safe to render. Never throws, so a hostile or
 *   half-typed value cannot break the save handler.
 */
export function validateProfileField(field, raw, { scope = "session" } = {}) {
  const meta = field && typeof field === "object" ? field : {};
  const title = typeof meta.title === "string" && meta.title ? meta.title : String(meta.key ?? "该字段");
  try {
    if (!meta.key) return { ok: false, message: "未知的运行档案字段。" };
    if (meta.type === "number" || meta.type === "integer") {
      const parsed = coerceNumber(raw, false);
      if (parsed === null) return { ok: false, message: `“${title}”必须是数字。` };
      if (meta.type === "integer" && !Number.isInteger(parsed)) return { ok: false, message: `“${title}”必须是整数。` };
      if (Number.isFinite(meta.minimum) && parsed < meta.minimum) return { ok: false, message: `“${title}”不能小于 ${meta.minimum}。` };
      if (Number.isFinite(meta.maximum) && parsed > meta.maximum) return { ok: false, message: `“${title}”不能大于 ${meta.maximum}。` };
      if (meta.key === "max_context_threshold" && scope === "session" && parsed < SESSION_CONTEXT_THRESHOLD_MINIMUM) {
        return { ok: false, message: `会话覆盖的“${title}”不能小于 ${SESSION_CONTEXT_THRESHOLD_MINIMUM}。` };
      }
      return { ok: true, value: parsed };
    }
    const text = typeof raw === "string" ? raw.trim() : raw === null || raw === undefined ? "" : String(raw).trim();
    if (Array.isArray(meta.enum)) {
      if (!text) return { ok: false, message: `请选择“${title}”。` };
      if (!meta.enum.includes(text)) return { ok: false, message: `“${title}”只能取 ${meta.enum.join(" / ")}。` };
      return { ok: true, value: text };
    }
    if (!text) return { ok: false, message: `“${title}”不能为空。` };
    return { ok: true, value: text };
  } catch {
    return { ok: false, message: `“${title}”的取值无法识别。` };
  }
}

/**
 * Describe which profile will be used for the next attempt.
 *
 * Args:
 *   payload: Loaded profile payload (`{scope,inherits_default,effective}`).
 *
 * Returns:
 *   One Chinese line for the form header.
 */
export function describeProfileScope(payload) {
  if (!payload || typeof payload !== "object") return "尚未读取运行档案。";
  if (payload.scope === "global") return "正在编辑全局默认档案：未覆盖的会话都会继承它。";
  if (payload.inherits_default !== false) return "继承全局默认：本会话尚未保存覆盖。";
  return "本会话覆盖生效：保存后仅影响下一次运行。";
}

/** Normalize `GET /api/context-handlers` into select options. */
function contextHandlerChoices(handlers, current) {
  const list = Array.isArray(handlers) ? handlers : Array.isArray(handlers?.handlers) ? handlers.handlers : [];
  const choices = [];
  for (const item of list) {
    const value = String(item?.id ?? "").trim();
    if (!value) continue;
    choices.push({
      value,
      label: String(item?.title || value),
      description: typeof item?.description === "string" ? item.description : "",
    });
  }
  if (current && !choices.some((choice) => choice.value === current)) choices.unshift({ value: current, label: current, description: "" });
  if (!choices.length) {
    const fallback = current || String(RUN_PROFILE_DEFAULTS.context_handler);
    choices.push({ value: fallback, label: fallback, description: "" });
  }
  return choices;
}

/** Options for one select, using Chinese captions for closed vocabularies. */
function fieldChoices(field) {
  if (!Array.isArray(field.enum)) return [];
  return field.enum.map((value) => ({ value, label: ENUM_LABELS.get(`${field.key}:${value}`) ?? value, description: "" }));
}

/** Human hint for the numeric bounds (the Session threshold is stricter). */
function fieldHint(field, scope) {
  const parts = [];
  if (field.key === "max_context_threshold" && scope === "session") parts.push(`会话覆盖需 ≥ ${SESSION_CONTEXT_THRESHOLD_MINIMUM}`);
  if (Number.isFinite(field.minimum) && Number.isFinite(field.maximum)) parts.push(`范围 ${field.minimum}–${field.maximum}`);
  else if (Number.isFinite(field.minimum)) parts.push(`≥ ${field.minimum}`);
  return parts.join("，");
}

/** Render the control for one field, with every interpolated value escaped. */
function renderFieldControl(field, value, choices) {
  const key = escapeHtml(field.key);
  const id = `profile-field-${field.key}`;
  const label = escapeHtml(field.title);
  if (field.type === "select") {
    const options = choices.map((choice) => {
      const selected = choice.value === String(value) ? " selected" : "";
      const description = choice.description ? ` title="${escapeHtml(choice.description)}"` : "";
      return `<option value="${escapeHtml(choice.value)}"${selected}${description}>${escapeHtml(choice.label)}</option>`;
    }).join("");
    return `<select class="profile-input" id="${id}" data-profile-key="${key}" aria-label="${label}">${options}</select>`;
  }
  const bounds = [
    Number.isFinite(field.minimum) ? ` min="${field.minimum}"` : "",
    Number.isFinite(field.maximum) ? ` max="${field.maximum}"` : "",
    Number.isFinite(field.step) ? ` step="${field.step}"` : "",
  ].join("");
  const type = field.type === "text" ? "text" : "number";
  return `<input class="profile-input" id="${id}" data-profile-key="${key}" type="${type}"${bounds} value="${escapeHtml(String(value))}" aria-label="${label}" />`;
}

/** Render one labelled field row. */
function renderField(field, value, choices, scope) {
  const key = escapeHtml(field.key);
  const hint = fieldHint(field, scope);
  return `<label class="field profile-field" data-profile-field="${key}"><span>${escapeHtml(field.title)}</span>${renderFieldControl(field, value, choices)}${hint ? `<small class="profile-hint">${escapeHtml(hint)}</small>` : ""}</label>`;
}

/**
 * Render the whole run-profile form.
 *
 * Args:
 *   payload: Loaded profile payload (`{scope,inherits_default,effective}`) or
 *     a bare effective object; null renders the documented defaults.
 *   options.scope: Active scope (`"global"` | `"session"`).
 *   options.handlers: `handlers` array (or whole payload) from
 *     `GET /api/context-handlers`.
 *   options.sessionId: Selected Session. `null` (default) means "unknown, so do
 *     not disable"; an empty string disables the 本会话 scope.
 *
 * Returns:
 *   Escaped HTML string with a scope switcher, one `data-profile-key` control
 *   per field grouped into compact single-column fieldsets, advanced tuning
 *   fields inside `<details>`, a `context_handler` select populated from the
 *   backend catalogue, and the next-run (执行快照) note.
 */
export function renderProfileForm(payload, { scope = "global", handlers = [], sessionId = null } = {}) {
  const activeScope = scope === "session" ? "session" : "global";
  const effective = payload && typeof payload === "object" && payload.effective && typeof payload.effective === "object"
    ? payload.effective
    : payload;
  const draft = clampProfileDraft(effective);
  const handlerChoices = contextHandlerChoices(handlers, String(draft.context_handler ?? ""));
  const sessionAvailable = sessionId === null || Boolean(sessionId);

  const groups = new Map();
  for (const field of RUN_PROFILE_FIELDS) {
    const group = field.group || "其他";
    if (!groups.has(group)) groups.set(group, { basic: [], advanced: [] });
    const choices = field.key === "context_handler" ? handlerChoices : fieldChoices(field);
    const markup = renderField(field, draft[field.key], choices, activeScope);
    groups.get(group)[field.advanced ? "advanced" : "basic"].push(markup);
  }
  const groupsHtml = [...groups].map(([group, bucket]) => {
    const advanced = bucket.advanced.length
      ? `<details class="agent-details profile-advanced"><summary><span>高级参数</span><span>调优</span></summary><div class="profile-advanced-body">${bucket.advanced.join("")}</div></details>`
      : "";
    return `<fieldset class="profile-group"><legend>${escapeHtml(group)}</legend>${bucket.basic.join("")}${advanced}</fieldset>`;
  }).join("");

  const sessionDisabled = sessionAvailable ? "" : ` disabled title="${escapeHtml("请先选择会话")}"`;
  return `<div class="profile-scope-switch" role="group" aria-label="运行档案作用域"><button type="button" class="profile-scope${activeScope === "global" ? " selected" : ""}" data-profile-scope="global" aria-pressed="${activeScope === "global"}">全局默认</button><button type="button" class="profile-scope${activeScope === "session" ? " selected" : ""}" data-profile-scope="session" aria-pressed="${activeScope === "session"}"${sessionDisabled}>本会话</button></div><p class="profile-scope-note">${escapeHtml(describeProfileScope(payload))}</p><p class="fineprint profile-snapshot-note">改动只影响下一次运行：启动 Agent 时这里保存的值会被冻结进执行快照，正在运行的 Agent 不会被热更新。</p><div class="profile-form">${groupsHtml}</div>`;
}

/**
 * Mount the structured run-profile form.
 *
 * Wires only documented endpoints: `GET|PUT /api/settings/run-profile` for the
 * global defaults, `GET|PUT|DELETE /api/sessions/{id}/run-profile` for the
 * Session override and `GET /api/context-handlers` for the handler catalogue.
 * Because both PUTs replace the whole object, a save is refused until the
 * profile has been read successfully; otherwise posting the rendered draft
 * would drop every key this form does not show.
 *
 * Args:
 *   root: Panel host element (`[data-panel="execution"]`).
 *   options.onStatus: Callback for the shell status bar messages.
 *
 * Returns:
 *   `setSession(id)` / `refresh()` handles used by the session lifecycle.
 */
export function mountRunProfilePanel(root, { onStatus = () => {} } = {}) {
  let sessionId = "", scope = "global", handlers = [], loaded = null, pending = 0, loadToken = 0;
  if (!root) return { setSession() {}, refresh() {} };
  root.innerHTML = '<div class="section-title compact"><div><span class="eyebrow">RUN PROFILE</span><h3>运行档案</h3></div><div class="action-group"><button type="button" class="profile-reload secondary">重新读取</button></div></div><p class="fineprint">运行档案决定下一次启动 Agent 时的采样参数、上下文压缩与 Shell 网络策略；未列出的设置（工具权限、Agent 覆盖等）保存时原样保留。</p><div class="profile-error" role="alert" hidden></div><div class="profile-form-host"></div><div class="profile-actions"><button type="button" class="profile-clear secondary" hidden>清除会话覆盖</button><button type="button" class="profile-save primary">保存运行档案</button></div>';
  const host = root.querySelector(".profile-form-host");
  const error = root.querySelector(".profile-error");
  const saveButton = root.querySelector(".profile-save");
  const clearButton = root.querySelector(".profile-clear");
  const reloadButton = root.querySelector(".profile-reload");

  function setError(message = "") {
    error.textContent = message;
    error.hidden = !message;
    if (message) onStatus(message);
  }

  function syncBusy() {
    const inFlight = pending > 0;
    saveButton.disabled = inFlight || !loaded;
    reloadButton.disabled = inFlight;
    clearButton.disabled = inFlight;
    for (const button of root.querySelectorAll("[data-profile-scope]")) button.disabled = inFlight || (button.dataset.profileScope === "session" && !sessionId);
  }

  function render() {
    host.innerHTML = renderProfileForm(loaded, { scope, handlers, sessionId });
    clearButton.hidden = !(scope === "session" && sessionId);
    saveButton.textContent = scope === "global" ? "保存全局默认" : "保存本会话档案";
    syncBusy();
  }

  function setPending(delta) {
    pending = Math.max(0, pending + delta);
    syncBusy();
  }

  /** Read the handler catalogue once; a failure only narrows the select. */
  async function loadHandlers() {
    if (handlers.length) return handlers;
    try {
      const payload = await api(CONTEXT_HANDLERS_PATH);
      if (Array.isArray(payload?.handlers)) handlers = payload.handlers;
    } catch {
      handlers = [];
    }
    return handlers;
  }

  async function load() {
    const token = ++loadToken;
    setError("");
    setPending(1);
    try {
      const catalog = await loadHandlers();
      const profile = await api(profileScopePath(scope, sessionId));
      if (token !== loadToken) return null;
      handlers = catalog;
      loaded = scope === "global"
        ? { scope: "global", inherits_default: true, effective: profile && typeof profile === "object" ? profile : {} }
        : { scope: "session", inherits_default: profile?.inherits_default !== false, effective: profile?.effective && typeof profile.effective === "object" ? profile.effective : {} };
      render();
      return loaded;
    } catch (caught) {
      if (token !== loadToken) return null;
      loaded = null;
      render();
      setError(`运行档案读取失败：${caught.message}`);
      return null;
    } finally {
      if (token === loadToken) setPending(-1);
    }
  }

  async function save() {
    if (pending > 0) return null;
    if (scope === "session" && !sessionId) { setError("请先选择会话后再保存本会话档案。"); return null; }
    if (!loaded) { setError("运行档案尚未成功读取，请先重新读取再保存，以免覆盖未显示的设置。"); return null; }
    const draft = {};
    for (const field of RUN_PROFILE_FIELDS) {
      const control = host.querySelector(`[data-profile-key="${field.key}"]`);
      if (!control) continue;
      const result = validateProfileField(field, control.value, { scope });
      if (!result.ok) {
        setError(result.message);
        control.focus?.();
        return null;
      }
      draft[field.key] = result.value;
    }
    const settings = buildProfilePayload(loaded.effective, draft);
    setError("");
    setPending(1);
    try {
      await api(profileScopePath(scope, sessionId), { method: "PUT", body: JSON.stringify({ settings }) });
      onStatus(scope === "global" ? "全局运行档案已保存；下一次启动 Agent 时生效。" : "本会话运行档案已保存；下一次启动 Agent 时生效。");
      return await load();
    } catch (caught) {
      setError(`运行档案保存失败：${caught.message}`);
      return null;
    } finally {
      setPending(-1);
    }
  }

  async function clearOverride() {
    if (pending > 0 || scope !== "session" || !sessionId) return null;
    const confirmed = typeof globalThis.confirm === "function"
      ? globalThis.confirm("清除本会话的运行档案覆盖？会话将重新继承全局默认。")
      : false;
    if (!confirmed) return null;
    setPending(1);
    try {
      await api(profileScopePath("session", sessionId), { method: "DELETE" });
      onStatus("已清除本会话覆盖；下一次启动 Agent 时使用全局默认。");
      return await load();
    } catch (caught) {
      setError(`清除会话覆盖失败：${caught.message}`);
      return null;
    } finally {
      setPending(-1);
    }
  }

  root.addEventListener("click", (event) => {
    const scopeButton = event.target.closest?.("[data-profile-scope]");
    if (scopeButton) {
      const next = scopeButton.dataset.profileScope === "session" ? "session" : "global";
      if (next === "session" && !sessionId) { setError("请先选择会话后再切换到本会话档案。"); return; }
      if (next === scope) return;
      scope = next;
      loaded = null;
      setError("");
      render();
      load();
      return;
    }
    if (event.target.closest?.(".profile-save")) { save(); return; }
    if (event.target.closest?.(".profile-clear")) { clearOverride(); return; }
    if (event.target.closest?.(".profile-reload")) load();
  });

  load();

  return {
    setSession(nextSessionId) {
      sessionId = nextSessionId ? String(nextSessionId) : "";
      if (!sessionId && scope === "session") scope = "global";
      loaded = null;
      return load();
    },
    refresh() { return load(); },
  };
}
