import assert from "node:assert/strict";
import {
  buildPanelPayload,
  coercePanelValue,
  coerceSettingValue,
  formatPermission,
  mountPluginPanel,
  panelFields,
  panelInvokePath,
  panelResultView,
  pluginActions,
  pluginPanels,
  pluginStateLabel,
  pluginThemes,
  renderPanelForm,
  renderPluginList,
  renderPluginPanels,
  renderSettingsForm,
  renderThemeSummary,
} from "./plugin-panel.js";

// --- Lifecycle state labels ------------------------------------------------
assert.equal(pluginStateLabel("error"), "错误");
assert.equal(pluginStateLabel("discovered"), "待注册");
assert.equal(pluginStateLabel("inactive"), "已注册未加载");
assert.equal(pluginStateLabel("active"), "运行中");
assert.equal(pluginStateLabel("something-else"), "未知");
assert.equal(pluginStateLabel(""), "未知");
assert.equal(pluginStateLabel(undefined), "未知");
assert.equal(pluginStateLabel(null), "未知");

// --- Action matrix: one lifecycle transition per real backend state -------
assert.deepEqual(pluginActions({ state: "error", registered: true, settings_available: true }), ["rescan"]);
assert.deepEqual(pluginActions({ state: "discovered", registered: false, settings_available: false }), ["register"]);
assert.deepEqual(pluginActions({ state: "inactive", registered: true, settings_available: false }), ["load"]);
assert.deepEqual(pluginActions({ state: "active", registered: true, settings_available: false }), ["unload"]);

// Settings only for registered, non-error records that declared settings.
assert.deepEqual(pluginActions({ state: "active", registered: true, settings_available: true }), ["unload", "settings"]);
assert.deepEqual(pluginActions({ state: "inactive", registered: true, settings_available: true }), ["load", "settings"]);
assert.deepEqual(pluginActions({ state: "error", registered: true, settings_available: true }), ["rescan"]);
assert.deepEqual(pluginActions({ state: "discovered", registered: false, settings_available: true }), ["register"]);
assert.deepEqual(pluginActions({ state: "active", registered: false, settings_available: true }), ["unload"]);

// An unrecognised state has no lifecycle transition, but the settings gate is
// independent of it, so a registered record still exposes its settings.
assert.deepEqual(pluginActions({ state: "weird", registered: true, settings_available: true }), ["settings"]);
assert.deepEqual(pluginActions({ state: "weird", registered: false, settings_available: true }), []);
assert.deepEqual(pluginActions({}), []);
assert.deepEqual(pluginActions(null), []);
assert.ok(!pluginActions({ state: "error", registered: true, settings_available: true }).includes("load"));
assert.ok(!pluginActions({ state: "error", registered: true, settings_available: true }).includes("settings"));

// --- Permission formatting -------------------------------------------------
assert.equal(formatPermission({ action: "network", scope: "outbound" }), "network (outbound)");
assert.equal(formatPermission({ action: " fs ", scope: " read " }), "fs (read)");
assert.equal(formatPermission(null), "");
assert.equal(formatPermission(undefined), "");
assert.equal(formatPermission("network:outbound"), "");
assert.equal(formatPermission({ action: "network" }), "");
assert.equal(formatPermission({ scope: "outbound" }), "");
assert.equal(formatPermission({ action: "", scope: "outbound" }), "");
assert.equal(formatPermission({ action: "network", scope: 7 }), "");

// --- List rendering: empty and missing payloads ----------------------------
assert.equal(renderPluginList([]), `<p class="plugin-empty">未发现插件</p>`);
assert.equal(renderPluginList(null), `<p class="plugin-empty">未发现插件</p>`);
assert.equal(renderPluginList(undefined), `<p class="plugin-empty">未发现插件</p>`);
assert.equal(renderPluginList({}), `<p class="plugin-empty">未发现插件</p>`);

// --- List rendering: hostile display_name / error are escaped --------------
const hostile = renderPluginList([
  { id: "plug_a", name: "alpha", display_name: "<img src=x onerror=alert(1)>", version: "1.2.3", state: "active", registered: true, settings_available: false, permissions_requested: [{ action: "net", scope: "out" }] },
  { id: "plug_b", name: "beta", display_name: "Beta", version: "0.1.0", state: "error", registered: false, settings_available: false, error: "<img src=x onerror=alert(1)>" },
]);
assert.match(hostile, /data-plugin-id="plug_a"/);
assert.match(hostile, /data-plugin-id="plug_b"/);
assert.match(hostile, /data-state="active"/);
assert.match(hostile, /data-state="error"/);
assert.match(hostile, /运行中/);
assert.match(hostile, /错误/);
assert.match(hostile, /1\.2\.3/);
assert.match(hostile, /net \(out\)/);
assert.doesNotMatch(hostile, /<img/);
assert.doesNotMatch(hostile, /<img/i);
assert.doesNotMatch(hostile, /<b>boom<\/b>/);
assert.equal(hostile.match(/&lt;img src=x onerror=alert\(1\)&gt;/g).length, 2);

// Error text only appears for errored items.
assert.doesNotMatch(renderPluginList([{ id: "x", name: "x", state: "active", error: "<b>boom</b>" }]), /boom/);

// --- List rendering: per-state action buttons ------------------------------
const actionsOf = (state, extra = {}) => {
  const html = renderPluginList([{ id: "p1", name: "pkg", state, registered: true, ...extra }]);
  return [...html.matchAll(/data-plugin-action="([a-z]+)"/g)].map((match) => match[1]);
};
assert.deepEqual(actionsOf("error", { settings_available: true }), ["rescan"]);
assert.deepEqual(actionsOf("discovered", { registered: false }), ["register"]);
assert.deepEqual(actionsOf("inactive"), ["load"]);
assert.deepEqual(actionsOf("active"), ["unload"]);
assert.deepEqual(actionsOf("active", { settings_available: true }), ["unload", "settings"]);
assert.deepEqual(actionsOf("unknown-state"), []);

// --- List rendering: id falls back to the manifest name -------------------
const fallback = renderPluginList([{ id: "", name: "manifest-name", state: "discovered", registered: false }]);
assert.match(fallback, /data-plugin-id="manifest-name"/);
const preferId = renderPluginList([{ id: "rec_1", name: "manifest-name", state: "inactive", registered: true }]);
assert.match(preferId, /data-plugin-id="rec_1"/);

// display_name falls back to name, then to id.
assert.match(renderPluginList([{ id: "rec_2", name: "plain-name", state: "active" }]), /<strong class="plugin-name">plain-name<\/strong>/);
assert.match(renderPluginList([{ id: "rec_3", display_name: "", name: "", state: "active" }]), /<strong class="plugin-name">rec_3<\/strong>/);

// --- Settings form rendering ----------------------------------------------
const schema = {
  enabled: { key: "enabled", type: "boolean", title: "启用", default: true },
  retries: { key: "retries", type: "integer", title: "重试次数", minimum: 0, maximum: 10, default: 3 },
  ratio: { key: "ratio", type: "number", title: "比例", minimum: 0.5, maximum: 2.5, default: 1 },
  label: { key: "label", type: "string", title: "标签", placeholder: "输入标签", default: "主" },
  notes: { key: "notes", type: "string", title: "备注", format: "textarea", default: "第一行\n第二行" },
  token: { key: "token", type: "string", title: "密钥", sensitive: true, default: "secret" },
};
const form = renderSettingsForm(schema, { enabled: false, retries: 7, ratio: 1.5, label: "副", notes: "<b>x</b>" });

// Boolean -> checkbox, reflecting the persisted value.
assert.match(form, /data-setting-key="enabled" data-setting-type="boolean"/);
assert.doesNotMatch(form, /data-setting-key="enabled"[^>]*checked/);

// Integer -> number input with step 1 and declared bounds.
assert.match(form, /type="number" data-setting-key="retries" data-setting-type="integer" value="7" step="1" min="0" max="10"/);

// Number -> number input with step any.
assert.match(form, /type="number" data-setting-key="ratio" data-setting-type="number" value="1\.5" step="any" min="0\.5" max="2\.5"/);

// String -> text input with placeholder; textarea when format is textarea.
assert.match(form, /type="text" data-setting-key="label" data-setting-type="string" value="副" placeholder="输入标签"/);
assert.match(form, /<textarea rows="3" data-setting-key="notes" data-setting-type="string" data-setting-format="textarea">/);
assert.match(form, /&lt;b&gt;x&lt;\/b&gt;/);

// Sensitive fields are skipped entirely (neither key nor title rendered).
assert.doesNotMatch(form, /token/);
assert.doesNotMatch(form, /密钥/);
assert.doesNotMatch(form, /secret/);

// Defaults fill in when the persisted value is missing; enum is advertised.
const defaults = renderSettingsForm({ mode: { key: "mode", type: "string", title: "模式", enum: ["fast", "safe"], default: "fast" } }, {});
assert.match(defaults, /value="fast"/);
assert.match(defaults, /可选值：fast、safe/);

// Checked booleans stay checked when the persisted value is true.
assert.match(renderSettingsForm({ on: { key: "on", type: "boolean", title: "开" } }, { on: true }), /data-setting-key="on" data-setting-type="boolean" checked/);

// Titles are escaped; empty or malformed schemas render nothing.
assert.match(renderSettingsForm({ a: { key: "a", type: "string", title: "<img src=x onerror=alert(1)>" } }, {}), /&lt;img src=x onerror=alert\(1\)&gt;/);
assert.equal(renderSettingsForm({}, {}), "");
assert.equal(renderSettingsForm(null, {}), "");
assert.equal(renderSettingsForm({ x: { key: "x", type: "unknown-type" } }, {}), "");
assert.equal(renderSettingsForm({ x: { key: "x", type: "string", sensitive: true } }, {}), "");

// --- Value coercion: happy paths ------------------------------------------
assert.equal(coerceSettingValue({ key: "enabled", type: "boolean" }, true), true);
assert.equal(coerceSettingValue({ key: "enabled", type: "boolean" }, "on"), true);
assert.equal(coerceSettingValue({ key: "enabled", type: "boolean" }, "checked"), true);
assert.equal(coerceSettingValue({ key: "enabled", type: "boolean" }, "true"), true);
assert.equal(coerceSettingValue({ key: "enabled", type: "boolean" }, false), false);
assert.equal(coerceSettingValue({ key: "enabled", type: "boolean" }, "off"), false);
assert.equal(coerceSettingValue({ key: "enabled", type: "boolean" }, ""), false);
assert.equal(coerceSettingValue({ key: "enabled", type: "boolean" }, null), false);

assert.equal(coerceSettingValue({ key: "retries", type: "integer", minimum: 0, maximum: 10 }, "7"), 7);
assert.equal(coerceSettingValue({ key: "retries", type: "integer" }, 0), 0);
assert.equal(coerceSettingValue({ key: "ratio", type: "number", minimum: 0, maximum: 2 }, "1.5"), 1.5);
assert.equal(coerceSettingValue({ key: "ratio", type: "number" }, 2), 2);
assert.equal(coerceSettingValue({ key: "label", type: "string" }, "  主  "), "主");
assert.equal(coerceSettingValue({ key: "label", type: "string" }, "a"), "a");
assert.equal(coerceSettingValue({ key: "mode", type: "string", enum: ["fast", "safe"] }, "fast"), "fast");

// --- Value coercion: rejections -------------------------------------------
assert.throws(() => coerceSettingValue({ key: "ratio", type: "number" }, "abc"), /插件设置 ratio 必须是数字。/);
assert.throws(() => coerceSettingValue({ key: "ratio", type: "number" }, ""), /不能为空/);
assert.throws(() => coerceSettingValue({ key: "ratio", type: "number" }, "   "), /不能为空/);
assert.throws(() => coerceSettingValue({ key: "ratio", type: "number" }, null), /不能为空/);
assert.throws(() => coerceSettingValue({ key: "retries", type: "integer" }, "1.5"), /必须是整数/);
assert.throws(() => coerceSettingValue({ key: "retries", type: "integer", minimum: 2 }, "1"), /不能小于 2/);
assert.throws(() => coerceSettingValue({ key: "retries", type: "integer", maximum: 4 }, "5"), /不能大于 4/);
assert.throws(() => coerceSettingValue({ key: "ratio", type: "number", minimum: 1.5 }, "1.4"), /不能小于 1\.5/);
assert.throws(() => coerceSettingValue({ key: "mode", type: "string", enum: ["fast", "safe"] }, "wild"), /必须是以下选项之一/);
assert.throws(() => coerceSettingValue({ key: "mode", type: "string", role: "x", required: true }, "  "), /不能为空/);
assert.throws(() => coerceSettingValue({ key: "enabled", type: "boolean" }, "maybe"), /必须是布尔值/);
assert.throws(() => coerceSettingValue({ key: "odd", type: "object" }, "x"), /类型不受支持/);

// Every rejection is a real Error with a renderable Chinese message.
try {
  coerceSettingValue({ key: "retries", type: "integer", maximum: 1 }, "9");
  assert.fail("expected a rejection");
} catch (caught) {
  assert.ok(caught instanceof Error);
  assert.match(caught.message, /插件设置 retries 不能大于 1。/);
}

// --- Declarative panel identity --------------------------------------------
assert.equal(panelInvokePath("plug_1", "lookup"), "/api/plugins/plug_1/panels/lookup/invoke");
assert.equal(panelInvokePath(" rec/1 ", " p q "), "/api/plugins/rec%2F1/panels/p%20q/invoke");
assert.equal(panelInvokePath("", "lookup"), "");
assert.equal(panelInvokePath("plug_1", "   "), "");
assert.equal(panelInvokePath(null, null), "");
assert.equal(panelInvokePath(undefined, "lookup"), "");

// Unknown scalar kinds and empty keys are dropped, never guessed at.
assert.deepEqual(
  panelFields([
    { key: " a ", type: "string" },
    { key: "", type: "string" },
    { key: "b", type: "object" },
    { key: "c" },
    null,
    "nope",
  ]),
  [{ key: "a", type: "string" }],
);
assert.deepEqual(panelFields(null), []);
assert.deepEqual(panelFields({}), []);

// --- Declarative panel normalisation ---------------------------------------
const lookupPanel = {
  id: "lookup",
  title: "知识查询",
  description: "查找本地知识。",
  submit_label: "查询",
  fields: [
    { key: "query", type: "string", title: "关键词", required: true, placeholder: "输入查询内容" },
    { key: "limit", type: "integer", title: "结果数", default: 10, minimum: 1, maximum: 100 },
    { key: "token", type: "string", title: "访问令牌", format: "password", sensitive: true },
  ],
};
const panels = pluginPanels({ panels: [lookupPanel, { id: "", title: "orphan" }, { id: "bare" }, null] });
assert.equal(panels.length, 2);
assert.equal(panels[0].id, "lookup");
assert.equal(panels[0].title, "知识查询");
assert.equal(panels[0].submitLabel, "查询");
assert.equal(panels[0].fields.length, 3);
// A panel without a title still needs a heading and a submit caption.
assert.equal(panels[1].title, "bare");
assert.equal(panels[1].submitLabel, "提交");
assert.equal(panels[1].description, "");
assert.deepEqual(panels[1].fields, []);
assert.deepEqual(pluginPanels({}), []);
assert.deepEqual(pluginPanels(null), []);
assert.deepEqual(pluginPanels({ panels: "nope" }), []);

// --- Theme summary normalisation / read-only rendering --------------------
assert.deepEqual(pluginThemes({ themes: [{ id: "night", title: "夜间", asset: "theme/night.css", mode: "dark" }] }), [
  { id: "night", title: "夜间", asset: "theme/night.css", mode: "dark" },
]);
assert.equal(pluginThemes({ themes: [{ id: "raw" }] })[0].title, "raw");
assert.equal(pluginThemes({ themes: [{ id: "raw" }] })[0].mode, "");
assert.deepEqual(pluginThemes({ themes: [{ id: "" }, null, "nope"] }), []);
assert.deepEqual(pluginThemes({}), []);

assert.equal(renderThemeSummary({}), "");
assert.equal(renderThemeSummary({ themes: [] }), "");
const themeMarkup = renderThemeSummary({ themes: [{ id: "night", title: "<img src=x onerror=alert(1)>", asset: "t.css", mode: "light" }] });
assert.match(themeMarkup, /plugin-themes-details/);
assert.match(themeMarkup, /data-theme-id="night" data-theme-mode="light"/);
assert.match(themeMarkup, /&lt;img src=x onerror=alert\(1\)&gt; · 浅色/);
assert.match(themeMarkup, /只读/);
assert.doesNotMatch(themeMarkup, /<img/);
// An unknown mode keeps its raw id instead of inventing a caption.
assert.match(renderThemeSummary({ themes: [{ id: "odd", mode: "sepia" }] }), /odd · sepia/);

// --- Panel form rendering: one control per declared type -------------------
assert.equal(renderPluginPanels(null), "");
assert.equal(renderPluginPanels({ id: "p", state: "active" }), "");
assert.equal(renderPluginPanels({ id: "p", state: "active", panels: [] }), "");

// A plugin that is not loaded cannot be invoked (the route answers 404), so
// the card states that instead of offering a button that cannot work.
const unloaded = renderPluginPanels({ state: "inactive", panels: [lookupPanel] });
assert.match(unloaded, /声明了 1 个功能面板，插件加载后可提交。/);
assert.doesNotMatch(unloaded, /data-panel-submit/);
assert.doesNotMatch(unloaded, /data-panel-key/);

const panelForm = renderPanelForm(lookupPanel);
assert.match(panelForm, /<section class="plugin-panel" data-panel-id="lookup">/);
assert.match(panelForm, /<strong class="plugin-panel-title">知识查询<\/strong>/);
assert.match(panelForm, /<p class="plugin-panel-description">查找本地知识。<\/p>/);
assert.match(panelForm, /class="primary plugin-panel-submit" data-panel-submit="lookup">查询<\/button>/);

// string -> text input carrying its placeholder
assert.match(panelForm, /type="text" data-panel-key="query" data-panel-type="string" value="" placeholder="输入查询内容" aria-required="true"/);
// required is flagged for assistive tech and for the row hint
assert.match(panelForm, /data-panel-field="query" data-panel-required="1"/);
assert.match(panelForm, /<small class="plugin-panel-hint">必填<\/small>/);
// integer -> number input with step 1, bounds, and the declared default
assert.match(panelForm, /type="number" data-panel-key="limit" data-panel-type="integer" value="10" step="1" min="1" max="100"/);
// sensitive -> password control with an empty value and no default leak
assert.match(panelForm, /type="password" data-panel-key="token" data-panel-type="string" data-panel-format="password" value="" autocomplete="off"/);
assert.match(panelForm, /data-panel-field="token" data-panel-sensitive="1"/);
assert.match(panelForm, /仅本次提交使用，不会保存。/);
assert.doesNotMatch(panelForm, /data-panel-key="token"[^>]*value="[^"]/);
// The two live regions the mount handler writes into always exist.
assert.match(panelForm, /<div class="plugin-panel-error" role="alert" hidden><\/div>/);
assert.match(panelForm, /<div class="plugin-panel-result" aria-live="polite" hidden><\/div>/);
assert.equal(renderPanelForm({ id: "" }), "");
assert.equal(renderPanelForm(null), "");

// number -> step any; boolean -> checkbox reflecting the default
assert.match(renderPanelForm({ id: "p", fields: [{ key: "ratio", type: "number", minimum: 0.5, maximum: 2.5 }] }), /type="number" data-panel-key="ratio" data-panel-type="number" value="" step="any" min="0\.5" max="2\.5"/);
assert.match(renderPanelForm({ id: "p", fields: [{ key: "dry", type: "boolean", default: true }] }), /type="checkbox" data-panel-key="dry" data-panel-type="boolean" checked/);
assert.doesNotMatch(renderPanelForm({ id: "p", fields: [{ key: "dry", type: "boolean" }] }), /checked/);

// enum -> select; a declared default is preselected, otherwise ask first
const enumForm = renderPanelForm({ id: "p", fields: [{ key: "mode", type: "string", enum: ["fast", "safe"] }] });
assert.match(enumForm, /<select data-panel-key="mode" data-panel-type="string" data-panel-enum="1">/);
assert.match(enumForm, /<option value="">请选择<\/option>/);
assert.match(enumForm, /<option value="fast">fast<\/option><option value="safe">safe<\/option>/);
const enumDefault = renderPanelForm({ id: "p", fields: [{ key: "mode", type: "string", enum: ["fast", "safe"], default: "safe" }] });
assert.match(enumDefault, /<option value="fast">fast<\/option><option value="safe" selected>safe<\/option>/);
assert.doesNotMatch(enumDefault, /请选择/);

// format hints: textarea / uri / path
const textareaForm = renderPanelForm({ id: "p", fields: [{ key: "notes", type: "string", format: "textarea", default: "<b>x</b>" }] });
assert.match(textareaForm, /<textarea rows="3" data-panel-key="notes" data-panel-type="string" data-panel-format="textarea">/);
assert.match(textareaForm, /&lt;b&gt;x&lt;\/b&gt;/);
assert.match(renderPanelForm({ id: "p", fields: [{ key: "url", type: "string", format: "uri" }] }), /type="url" data-panel-key="url" data-panel-type="string" data-panel-format="uri" value=""/);
assert.match(renderPanelForm({ id: "p", fields: [{ key: "dir", type: "string", format: "path" }] }), /type="text" data-panel-key="dir" data-panel-type="string" data-panel-format="path" value=""/);
// An unknown format stays a plain text input rather than guessing.
assert.match(renderPanelForm({ id: "p", fields: [{ key: "x", type: "string", format: "sql" }] }), /type="text" data-panel-key="x" data-panel-type="string" value=""/);
// A field list with nothing renderable still explains itself.
assert.match(renderPanelForm({ id: "p", fields: [] }), /该面板没有输入字段/);

// Manifest-authored panel text is package text, so every interpolation escapes.
const hostilePanel = renderPanelForm({
  id: "p<1>",
  title: "<img src=x onerror=alert(1)>",
  description: "<b>desc</b>",
  submit_label: "<i>go</i>",
  fields: [{ key: "q", type: "string", title: "<em>t</em>", description: "<u>hint</u>", placeholder: "\"><script>" }],
});
assert.doesNotMatch(hostilePanel, /<img|<b>|<i>|<em>|<u>|<script>/);
assert.match(hostilePanel, /data-panel-id="p&lt;1&gt;"/);
assert.match(hostilePanel, /data-panel-submit="p&lt;1&gt;"/);
assert.match(hostilePanel, /placeholder="&quot;&gt;&lt;script&gt;"/);

// --- Panel value coercion --------------------------------------------------
assert.equal(coercePanelValue({ key: "limit", type: "integer", minimum: 1, maximum: 10 }, "7"), 7);
assert.equal(coercePanelValue({ key: "ratio", type: "number" }, 1.5), 1.5);
assert.equal(coercePanelValue({ key: "on", type: "boolean" }, "on"), true);
assert.equal(coercePanelValue({ key: "on", type: "boolean" }, "off"), false);
assert.equal(coercePanelValue({ key: "q", type: "string", required: true }, "  地图 "), "地图");
assert.equal(coercePanelValue({ key: "token", type: "string", sensitive: true }, " s3cret "), "s3cret");

assert.throws(() => coercePanelValue({ key: "limit", type: "integer" }, "1.5"), /插件面板 limit 必须是整数。/);
assert.throws(() => coercePanelValue({ key: "limit", type: "integer", minimum: 2 }, "1"), /插件面板 limit 不能小于 2。/);
assert.throws(() => coercePanelValue({ key: "limit", type: "integer", maximum: 4 }, "5"), /插件面板 limit 不能大于 4。/);
assert.throws(() => coercePanelValue({ key: "ratio", type: "number" }, "abc"), /插件面板 ratio 必须是数字。/);
assert.throws(() => coercePanelValue({ key: "ratio", type: "number" }, "   "), /插件面板 ratio 不能为空。/);
assert.throws(() => coercePanelValue({ key: "mode", type: "string", enum: ["fast"] }, "slow"), /插件面板 mode 必须是以下选项之一/);
assert.throws(() => coercePanelValue({ key: "q", type: "string", required: true }, "  "), /插件面板 q 不能为空。/);
assert.throws(() => coercePanelValue({ key: "token", type: "string", sensitive: true }, ""), /插件面板 token 不能为空。/);
assert.throws(() => coercePanelValue({ key: "on", type: "boolean" }, "maybe"), /插件面板 on 的取值必须是布尔值。/);
assert.throws(() => coercePanelValue({ key: "odd", type: "object" }, "x"), /插件面板 odd 的类型不受支持。/);
// The shared helpers kept the settings wording for the settings form.
assert.throws(() => coerceSettingValue({ key: "retries", type: "integer", maximum: 1 }, "9"), /插件设置 retries 不能大于 1。/);
assert.throws(() => coerceSettingValue({ key: "enabled", type: "boolean" }, "maybe"), /插件设置 enabled 的取值必须是布尔值。/);

// --- Invoke body: flat, declared keys only, defaults left to the backend ---
const payloadFields = [
  { key: "query", type: "string", required: true },
  { key: "limit", type: "integer", default: 10, minimum: 1, maximum: 100 },
  { key: "dry", type: "boolean" },
  { key: "mode", type: "string", enum: ["fast", "safe"] },
];
assert.deepEqual(buildPanelPayload(payloadFields, { query: "  地图 ", limit: "25", dry: false, mode: "" }), { query: "地图", limit: 25, dry: false });
// Optional blanks are omitted so PluginManager applies the manifest default.
assert.deepEqual(buildPanelPayload(payloadFields, { query: "x" }), { query: "x", dry: false });
// Raw controls for undeclared keys never reach the body.
assert.deepEqual(buildPanelPayload(payloadFields, { query: "x", extra: "y" }), { query: "x", dry: false });
// An unchecked box is a real false, not a missing key.
assert.deepEqual(buildPanelPayload([{ key: "dry", type: "boolean" }], { dry: false }), { dry: false });
// Required blanks and bad values fail before any request is made.
assert.throws(() => buildPanelPayload(payloadFields, {}), /插件面板 query 不能为空。/);
assert.throws(() => buildPanelPayload(payloadFields, { query: "   " }), /插件面板 query 不能为空。/);
assert.throws(() => buildPanelPayload(payloadFields, { query: "x", limit: "500" }), /插件面板 limit 不能大于 100。/);
assert.throws(() => buildPanelPayload(payloadFields, { query: "x", mode: "wild" }), /插件面板 mode 必须是以下选项之一/);
// A sensitive field is never filled from a default and is always explicit.
assert.deepEqual(buildPanelPayload([{ key: "token", type: "string", sensitive: true }], {}), {});
assert.throws(() => buildPanelPayload([{ key: "token", type: "string", sensitive: true, required: true }], {}), /插件面板 token 不能为空。/);
// Malformed inputs stay harmless.
assert.deepEqual(buildPanelPayload(null, { a: 1 }), {});
assert.deepEqual(buildPanelPayload([{ key: "x", type: "object" }], { x: 1 }), {});
assert.deepEqual(buildPanelPayload([{ key: "dry", type: "boolean" }], null), { dry: false });

// --- Action result rendering ----------------------------------------------
assert.equal(panelResultView(null), "");
assert.equal(panelResultView("nope"), "");
assert.equal(panelResultView({}), "");
assert.equal(panelResultView({ title: "  ", content: "" }), "");
const okResult = panelResultView({ title: "查询结果", content: "地图: 25", tone: "success" });
assert.match(okResult, /class="plugin-panel-result-body plugin-tone-success" data-tone="success"/);
assert.match(okResult, /<strong class="plugin-panel-result-title">查询结果<\/strong>/);
assert.match(okResult, /<p class="plugin-panel-result-content">地图: 25<\/p>/);
// Plugin-authored content is text: markup is escaped, tone only picks a class.
const hostileResult = panelResultView({ title: "<img src=x onerror=alert(1)>", content: "<script>alert(1)</script>", tone: "error" });
assert.match(hostileResult, /plugin-tone-error/);
assert.match(hostileResult, /&lt;script&gt;alert\(1\)&lt;\/script&gt;/);
assert.doesNotMatch(hostileResult, /<script|<img/);
// An unknown or hostile tone degrades to `info` instead of becoming a class.
assert.match(panelResultView({ title: "t", content: "c", tone: "weird" }), /plugin-tone-info/);
assert.doesNotMatch(panelResultView({ title: "t", content: "c", tone: "\"><script>" }), /plugin-tone-</);
assert.match(panelResultView({ content: "only content" }), /plugin-tone-info/);
assert.doesNotMatch(panelResultView({ content: "only content" }), /plugin-panel-result-title/);

// --- The plugin card carries panels and themes from the same projection ---
const deck = renderPluginList([
  {
    id: "plug_a",
    name: "alpha",
    state: "active",
    registered: true,
    panels: [lookupPanel],
    themes: [{ id: "night", title: "夜间", asset: "theme/night.css", mode: "dark" }],
  },
  { id: "plug_b", name: "beta", state: "inactive", registered: true, panels: [lookupPanel], themes: [{ id: "day", title: "日间", mode: "light" }] },
]);
assert.match(deck, /data-panel-id="lookup"/);
assert.match(deck, /data-panel-submit="lookup"/);
assert.match(deck, /plugin-themes-details/);
assert.match(deck, /夜间 · 深色/);
// The unloaded plugin shows its theme summary and a load hint, no live form.
assert.match(deck, /日间 · 浅色/);
assert.match(deck, /声明了 1 个功能面板/);
assert.equal(deck.match(/data-panel-submit="lookup"/g).length, 1);
// Panel controls never reuse the settings control hooks or the action hooks.
assert.doesNotMatch(deck, /data-setting-key/);
assert.doesNotMatch(deck, /data-panel-submit="lookup" data-plugin-action/);
assert.equal(deck.match(/data-plugin-action=/g).length, 2);
// A projection without panels or themes renders exactly as before.
assert.doesNotMatch(renderPluginList([{ id: "plain", name: "plain", state: "active" }]), /plugin-panel|plugin-theme/);

// --- Mount guard keeps the dock wiring safe without a host element --------
const detached = mountPluginPanel(null);
assert.equal(typeof detached.refresh, "function");
assert.equal(detached.refresh(), undefined);

console.log("Plugin panel checks passed.");
