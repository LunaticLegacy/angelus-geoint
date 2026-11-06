import assert from "node:assert/strict";
import {
  coerceSettingValue,
  formatPermission,
  mountPluginPanel,
  pluginActions,
  pluginStateLabel,
  renderPluginList,
  renderSettingsForm,
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

// --- Mount guard keeps the dock wiring safe without a host element --------
const detached = mountPluginPanel(null);
assert.equal(typeof detached.refresh, "function");
assert.equal(detached.refresh(), undefined);

console.log("Plugin panel checks passed.");
