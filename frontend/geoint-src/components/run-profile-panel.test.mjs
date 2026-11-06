import assert from "node:assert/strict";
import {
  RUN_PROFILE_DEFAULTS,
  RUN_PROFILE_FIELDS,
  SESSION_CONTEXT_THRESHOLD_MINIMUM,
  buildProfilePayload,
  clampProfileDraft,
  describeProfileScope,
  profileScopePath,
  renderProfileForm,
  validateProfileField,
} from "./run-profile-panel.js";

// --- URL construction: both scopes, encoding, empty-session fallback --------
assert.equal(profileScopePath("global", "s-1"), "/api/settings/run-profile");
assert.equal(profileScopePath("global", ""), "/api/settings/run-profile");
assert.equal(profileScopePath("session", "s-1"), "/api/sessions/s-1/run-profile");
assert.equal(profileScopePath("session", "a/b"), "/api/sessions/a%2Fb/run-profile");
assert.equal(profileScopePath("session", "a b"), "/api/sessions/a%20b/run-profile");
assert.equal(profileScopePath("session", ""), "/api/settings/run-profile");
assert.equal(profileScopePath("session", "   "), "/api/settings/run-profile");
assert.equal(profileScopePath("session"), "/api/settings/run-profile");
assert.equal(profileScopePath("session", null), "/api/settings/run-profile");
assert.equal(profileScopePath(undefined, "s-1"), "/api/sessions/s-1/run-profile");

// --- Field descriptors ------------------------------------------------------
const byKey = new Map(RUN_PROFILE_FIELDS.map((field) => [field.key, field]));
assert.deepEqual(
  RUN_PROFILE_FIELDS.map((field) => field.key),
  ["temperature", "max_tokens", "thinking_mode", "reasoning_effort", "max_rounds", "max_retries", "request_timeout_seconds", "max_swarm_agents", "max_context_threshold", "compaction_output_max_tokens", "context_keep_recent", "tool_result_context_limit", "context_handler", "shell_network_mode"],
);
assert.equal(byKey.size, RUN_PROFILE_FIELDS.length, "field keys must be unique");

// Unrendered keys must never appear as descriptors: a whole-object PUT would
// otherwise rewrite structures this form cannot edit.
for (const unrendered of ["tool_permissions", "agent_overrides", "context_handler_settings", "context_block_order", "system_prompt", "session_memory_search_sessions", "connector_id", "provider", "model", "api_url"]) {
  assert.equal(byKey.has(unrendered), false, `${unrendered} must stay unrendered`);
}

const ALLOWED_TYPES = new Set(["number", "integer", "select", "text"]);
for (const field of RUN_PROFILE_FIELDS) {
  assert.equal(typeof field.title, "string", `${field.key} title must be a string`);
  assert.ok(field.title.length > 0, `${field.key} needs a title`);
  assert.equal(ALLOWED_TYPES.has(field.type), true, `${field.key} has an unsupported type`);
  assert.equal(typeof field.group, "string", `${field.key} group must be a string`);
  assert.ok(field.group.length > 0, `${field.key} needs a group`);
  assert.equal(typeof field.advanced, "boolean", `${field.key} needs an advanced flag`);
  assert.equal(Object.prototype.hasOwnProperty.call(RUN_PROFILE_DEFAULTS, field.key), true, `${field.key} needs a documented default`);
  if (field.type === "number" || field.type === "integer") {
    assert.equal(Object.prototype.hasOwnProperty.call(field, "minimum"), true, `${field.key} must carry minimum`);
    assert.equal(Object.prototype.hasOwnProperty.call(field, "maximum"), true, `${field.key} must carry maximum`);
    assert.equal(Number.isFinite(field.minimum), true, `${field.key} needs a numeric minimum`);
    assert.ok(field.maximum === null || Number.isFinite(field.maximum), `${field.key} maximum must be null or numeric`);
  }
  if (field.type === "select" && field.enum) {
    assert.equal(Array.isArray(field.enum), true);
    assert.ok(field.enum.length > 0, `${field.key} needs enum members`);
  }
}

// Documented bounds and vocabularies.
assert.deepEqual([byKey.get("temperature").minimum, byKey.get("temperature").maximum], [0, 2]);
assert.deepEqual([byKey.get("request_timeout_seconds").minimum, byKey.get("request_timeout_seconds").maximum], [1, 3600]);
assert.equal(byKey.get("max_tokens").minimum, 1);
assert.deepEqual(byKey.get("thinking_mode").enum, ["auto", "on", "off"]);
assert.deepEqual(byKey.get("reasoning_effort").enum, ["auto", "low", "medium", "high"]);
assert.deepEqual(byKey.get("shell_network_mode").enum, ["isolated", "host_network"]);
assert.equal(byKey.get("context_handler").type, "select");
for (const key of ["max_rounds", "max_retries", "max_context_threshold", "compaction_output_max_tokens", "context_keep_recent", "tool_result_context_limit", "max_swarm_agents"]) {
  assert.equal(byKey.get(key).type, "integer", `${key} must be an integer field`);
  assert.equal(byKey.get(key).minimum >= 0, true, `${key} must be non-negative`);
}
// Tuning-only fields hide behind <details>; the everyday knobs stay visible.
for (const key of ["max_rounds", "max_retries", "compaction_output_max_tokens", "context_keep_recent", "tool_result_context_limit", "max_swarm_agents"]) {
  assert.equal(byKey.get(key).advanced, true, `${key} should be advanced`);
}
for (const key of ["temperature", "thinking_mode", "reasoning_effort", "max_tokens", "max_context_threshold", "context_handler", "shell_network_mode"]) {
  assert.equal(byKey.get(key).advanced, false, `${key} should stay visible`);
}

// Documented defaults.
assert.deepEqual(
  { ...RUN_PROFILE_DEFAULTS },
  {
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
    context_handler: "linear",
  },
);

// --- clampProfileDraft: defaults, coercion, clamping, no unknown keys -------
assert.deepEqual(clampProfileDraft(null), { ...RUN_PROFILE_DEFAULTS });
assert.deepEqual(clampProfileDraft(undefined), { ...RUN_PROFILE_DEFAULTS });
assert.deepEqual(clampProfileDraft({}), { ...RUN_PROFILE_DEFAULTS });
assert.deepEqual(clampProfileDraft("nonsense"), { ...RUN_PROFILE_DEFAULTS });

const coerced = clampProfileDraft({
  temperature: "0.8",
  max_tokens: "4096",
  max_rounds: "3.6",
  thinking_mode: " off ",
  reasoning_effort: "high",
  request_timeout_seconds: "120",
  shell_network_mode: "isolated",
  max_context_threshold: "524288",
  context_handler: "  linear  ",
  tool_permissions: { tools: { shell: true } },
  agent_overrides: { coordinator: { max_rounds: 2 } },
  connector_id: "c-1",
});
assert.equal(coerced.temperature, 0.8);
assert.equal(coerced.max_tokens, 4096);
assert.equal(coerced.max_rounds, 4, "integer fields must be rounded");
assert.equal(coerced.thinking_mode, "off");
assert.equal(coerced.reasoning_effort, "high");
assert.equal(coerced.request_timeout_seconds, 120);
assert.equal(coerced.shell_network_mode, "isolated");
assert.equal(coerced.max_context_threshold, 524288);
assert.equal(coerced.context_handler, "linear");
// Unknown keys are not copied into the draft.
for (const key of ["tool_permissions", "agent_overrides", "connector_id"]) assert.equal(key in coerced, false);
assert.deepEqual(Object.keys(coerced).sort(), RUN_PROFILE_FIELDS.map((field) => field.key).sort());

// Out-of-range and unparseable values are clamped back to valid ones.
assert.equal(clampProfileDraft({ temperature: 9 }).temperature, 2);
assert.equal(clampProfileDraft({ temperature: -1 }).temperature, 0);
assert.equal(clampProfileDraft({ request_timeout_seconds: 0 }).request_timeout_seconds, 1);
assert.equal(clampProfileDraft({ request_timeout_seconds: 7200 }).request_timeout_seconds, 3600);
assert.equal(clampProfileDraft({ max_tokens: 0 }).max_tokens, 1);
assert.equal(clampProfileDraft({ max_tokens: "nope" }).max_tokens, 32768);
assert.equal(clampProfileDraft({ temperature: Number.NaN }).temperature, 0.4);
assert.equal(clampProfileDraft({ max_rounds: -5 }).max_rounds, 0);
// Unknown enum members and empty strings fall back to the documented default.
assert.equal(clampProfileDraft({ thinking_mode: "turbo" }).thinking_mode, "auto");
assert.equal(clampProfileDraft({ shell_network_mode: "" }).shell_network_mode, "host_network");
assert.equal(clampProfileDraft({ context_handler: "" }).context_handler, "linear");
assert.equal(clampProfileDraft({ max_context_threshold: null }).max_context_threshold, 262144);

// --- buildProfilePayload: unrendered keys survive, inputs stay untouched ----
const effective = {
  system_prompt: "keep me",
  temperature: 0.4,
  max_tokens: 32768,
  thinking_mode: "auto",
  tool_permissions: { categories: { shell: false }, tools: { shell: false, note_list: true } },
  agent_overrides: { coordinator: { max_rounds: 7 } },
  context_handler_settings: { linear: { keep_recent: 3 } },
  context_block_order: { notes: 10 },
  session_memory_search_sessions: ["s-1", "s-2"],
  session_artifact_open_sessions: ["s-3"],
  connector_id: "c-9",
  provider: "openai",
  model: "gpt-x",
  api_url: "http://localhost:1234",
};
const draft = { temperature: 1.1, max_tokens: 8192, thinking_mode: "on", evil_key: "x" };
const payload = buildProfilePayload(effective, draft);

assert.equal(payload.temperature, 1.1);
assert.equal(payload.max_tokens, 8192);
assert.equal(payload.thinking_mode, "on");
assert.equal("evil_key" in payload, false, "draft keys outside the field list are ignored");
assert.equal(payload.system_prompt, "keep me");
assert.deepEqual(payload.tool_permissions, { categories: { shell: false }, tools: { shell: false, note_list: true } });
assert.deepEqual(payload.agent_overrides, { coordinator: { max_rounds: 7 } });
assert.deepEqual(payload.context_handler_settings, { linear: { keep_recent: 3 } });
assert.deepEqual(payload.context_block_order, { notes: 10 });
assert.deepEqual(payload.session_memory_search_sessions, ["s-1", "s-2"]);
assert.deepEqual(payload.session_artifact_open_sessions, ["s-3"]);
assert.equal(payload.connector_id, "c-9");
assert.equal(payload.model, "gpt-x");
assert.equal(payload.api_url, "http://localhost:1234");

// Deep clone: mutating the payload must not reach the loaded profile.
assert.notEqual(payload.tool_permissions, effective.tool_permissions);
assert.notEqual(payload.tool_permissions.tools, effective.tool_permissions.tools);
assert.notEqual(payload.session_memory_search_sessions, effective.session_memory_search_sessions);
payload.tool_permissions.tools.shell = true;
payload.session_memory_search_sessions.push("s-9");
payload.agent_overrides.coordinator.max_rounds = 99;
assert.deepEqual(effective.tool_permissions.tools.shell, false);
assert.deepEqual(effective.session_memory_search_sessions, ["s-1", "s-2"]);
assert.deepEqual(effective.agent_overrides, { coordinator: { max_rounds: 7 } });
// Neither input was mutated by the merge itself.
assert.equal(effective.temperature, 0.4);
assert.deepEqual(draft, { temperature: 1.1, max_tokens: 8192, thinking_mode: "on", evil_key: "x" });

// Partial drafts leave the remaining rendered keys authoritative in the clone.
const partial = buildProfilePayload({ temperature: 0.4, max_retries: 9, tool_permissions: {} }, { temperature: 0.2 });
assert.equal(partial.max_retries, 9);
assert.deepEqual(partial.tool_permissions, {});

// Missing / malformed effective objects degrade to the draft alone.
assert.deepEqual(buildProfilePayload(null, { temperature: 1 }), { temperature: 1 });
assert.deepEqual(buildProfilePayload(undefined, null), {});
assert.deepEqual(buildProfilePayload([1, 2], {}), {});

// The canonical round trip: a clamped draft never drops unrendered keys.
// Rendered keys missing from `effective` are filled from the documented
// defaults (the form owns them), while every other key survives verbatim.
const roundTrip = buildProfilePayload(effective, clampProfileDraft(effective));
for (const field of RUN_PROFILE_FIELDS) {
  const expected = field.key in effective ? effective[field.key] : RUN_PROFILE_DEFAULTS[field.key];
  assert.equal(roundTrip[field.key], expected, `${field.key} must round-trip`);
}
for (const unrendered of Object.keys(effective)) {
  if (byKey.has(unrendered)) continue;
  assert.deepEqual(roundTrip[unrendered], effective[unrendered], `${unrendered} must survive the round trip`);
}

// --- validateProfileField: every rejection path ----------------------------
const ok = (field, raw, options) => validateProfileField(field, raw, options);
const fail = (field, raw, options) => {
  const result = validateProfileField(field, raw, options);
  assert.equal(result.ok, false, `expected rejection for ${field.key}=${String(raw)}`);
  assert.equal(typeof result.message, "string");
  assert.equal(result.message.includes(field.title), true, "rejection messages name the field");
  return result;
};

assert.deepEqual(ok(byKey.get("temperature"), "0.7"), { ok: true, value: 0.7 });
assert.deepEqual(ok(byKey.get("temperature"), 1.25), { ok: true, value: 1.25 });
assert.deepEqual(ok(byKey.get("temperature"), "0"), { ok: true, value: 0 });
assert.deepEqual(ok(byKey.get("temperature"), "2"), { ok: true, value: 2 });
fail(byKey.get("temperature"), "");
fail(byKey.get("temperature"), "   ");
fail(byKey.get("temperature"), "abc");
fail(byKey.get("temperature"), null);
fail(byKey.get("temperature"), true);
fail(byKey.get("temperature"), {});
fail(byKey.get("temperature"), "-0.1");
fail(byKey.get("temperature"), "2.1");
assert.match(fail(byKey.get("temperature"), "2.1").message, /不能大于 2/);

assert.deepEqual(ok(byKey.get("max_tokens"), "4096"), { ok: true, value: 4096 });
assert.deepEqual(ok(byKey.get("max_tokens"), "0"), { ok: false, message: "“最大输出 tokens”不能小于 1。" });
assert.match(fail(byKey.get("max_tokens"), "0").message, /不能小于 1/);
assert.match(fail(byKey.get("max_tokens"), "12.5").message, /必须是整数/);
assert.match(fail(byKey.get("max_rounds"), "-1").message, /不能小于 0/);
assert.deepEqual(ok(byKey.get("max_rounds"), "0"), { ok: true, value: 0 });

assert.match(fail(byKey.get("request_timeout_seconds"), "0").message, /不能小于 1/);
assert.match(fail(byKey.get("request_timeout_seconds"), "3601").message, /不能大于 3600/);
assert.deepEqual(ok(byKey.get("request_timeout_seconds"), "30"), { ok: true, value: 30 });

// Session-only floor on the compression threshold.
assert.equal(SESSION_CONTEXT_THRESHOLD_MINIMUM, 1024);
assert.deepEqual(ok(byKey.get("max_context_threshold"), "1024", { scope: "session" }), { ok: true, value: 1024 });
assert.match(fail(byKey.get("max_context_threshold"), "1023", { scope: "session" }).message, /1024/);
assert.match(fail(byKey.get("max_context_threshold"), "0", { scope: "session" }).message, /1024/);
assert.deepEqual(ok(byKey.get("max_context_threshold"), "512", { scope: "global" }), { ok: true, value: 512 });
assert.deepEqual(ok(byKey.get("max_context_threshold"), "0", { scope: "global" }), { ok: true, value: 0 });

// Closed vocabularies.
assert.deepEqual(ok(byKey.get("thinking_mode"), "on"), { ok: true, value: "on" });
assert.deepEqual(ok(byKey.get("thinking_mode"), "  off  "), { ok: true, value: "off" });
assert.match(fail(byKey.get("thinking_mode"), "turbo").message, /auto \/ on \/ off/);
assert.match(fail(byKey.get("thinking_mode"), "").message, /请选择/);
assert.deepEqual(ok(byKey.get("reasoning_effort"), "medium"), { ok: true, value: "medium" });
assert.match(fail(byKey.get("reasoning_effort"), "max").message, /auto \/ low \/ medium \/ high/);
assert.deepEqual(ok(byKey.get("shell_network_mode"), "isolated"), { ok: true, value: "isolated" });
assert.match(fail(byKey.get("shell_network_mode"), "bridge").message, /isolated \/ host_network/);

// context_handler is a dynamic select: only a non-empty string is required.
assert.deepEqual(ok(byKey.get("context_handler"), " linear "), { ok: true, value: "linear" });
assert.deepEqual(ok(byKey.get("context_handler"), "future-handler"), { ok: true, value: "future-handler" });
assert.match(fail(byKey.get("context_handler"), "   ").message, /不能为空/);
assert.match(fail(byKey.get("context_handler"), null).message, /不能为空/);

// Degenerate descriptors must reject instead of throwing.
assert.equal(validateProfileField(null, "1").ok, false);
assert.equal(validateProfileField(undefined, "1").ok, false);
assert.equal(validateProfileField({ title: "无键" }, "1").ok, false);
assert.doesNotThrow(() => validateProfileField(byKey.get("temperature"), Symbol("x")));

// --- describeProfileScope ---------------------------------------------------
assert.match(describeProfileScope({ scope: "session", inherits_default: true }), /继承全局默认/);
assert.match(describeProfileScope({ scope: "session", inherits_default: false }), /本会话覆盖生效/);
assert.match(describeProfileScope({ scope: "session" }), /继承全局默认/);
assert.match(describeProfileScope({ scope: "global", inherits_default: true }), /全局默认/);
assert.match(describeProfileScope(null), /尚未读取运行档案/);

// --- renderProfileForm ------------------------------------------------------
const hostileHandlers = [
  { id: "linear", title: "<img src=x onerror=alert(1)>", description: "\"><script>alert(2)</script>" },
  { id: "windowed", title: "窗口压缩", description: "保留最近消息" },
];
const form = renderProfileForm(
  { scope: "session", inherits_default: false, effective: { ...effective, context_handler: "windowed", temperature: 0.9 } },
  { scope: "session", handlers: hostileHandlers, sessionId: "s-1" },
);

// Escaping: handler titles/descriptions and values never reach the DOM raw.
assert.doesNotMatch(form, /<img/);
assert.doesNotMatch(form, /<script>/);
assert.match(form, /&lt;img src=x onerror=alert\(1\)&gt;/);
assert.match(form, /&lt;script&gt;alert\(2\)&lt;\/script&gt;/);

// Scope switcher reflects the active scope and offers both scopes.
assert.match(form, /data-profile-scope="global"/);
assert.match(form, /data-profile-scope="session"/);
assert.match(form, /class="profile-scope selected" data-profile-scope="session" aria-pressed="true"/);
assert.match(form, /全局默认<\/button>/);
assert.match(form, /本会话<\/button>/);
assert.doesNotMatch(form, /data-profile-scope="session"[^>]*disabled/);

// Every rendered field is tagged so the mount can read it back.
for (const field of RUN_PROFILE_FIELDS) {
  assert.match(form, new RegExp(`data-profile-key="${field.key}"`), `${field.key} control missing`);
  assert.match(form, new RegExp(`data-profile-field="${field.key}"`), `${field.key} row missing`);
}
assert.match(form, /<input class="profile-input" id="profile-field-temperature" data-profile-key="temperature" type="number" min="0" max="2" step="0.1" value="0.9"/);
assert.match(form, /<select class="profile-input" id="profile-field-thinking_mode" data-profile-key="thinking_mode"/);
assert.match(form, /<option value="auto" selected>自动<\/option>/);
assert.match(form, /<option value="host_network" selected/);
assert.match(form, /<option value="windowed" selected/);
assert.match(form, /<option value="linear" title=/);

// Grouping: single-column fieldsets, advanced tuning inside <details>.
assert.match(form, /<fieldset class="profile-group"><legend>采样<\/legend>/);
assert.match(form, /<fieldset class="profile-group"><legend>推理<\/legend>/);
assert.match(form, /<fieldset class="profile-group"><legend>上下文<\/legend>/);
assert.match(form, /<fieldset class="profile-group"><legend>工具<\/legend>/);
assert.match(form, /<details class="agent-details profile-advanced"><summary><span>高级参数<\/span>/);
assert.equal((form.match(/<details /g) || []).length, 2, "推理 and 上下文 keep their advanced groups");
assert.equal((form.match(/data-profile-key=/g) || []).length, RUN_PROFILE_FIELDS.length);

// Next-run note + scope description.
assert.match(form, /执行快照/);
assert.match(form, /下一次运行/);
assert.match(form, /本会话覆盖生效/);

// Session scope is disabled only when the caller reports no selection.
const noSession = renderProfileForm({ scope: "global", inherits_default: true, effective: {} }, { scope: "global", handlers: [], sessionId: "" });
assert.match(noSession, /data-profile-scope="session"[^>]*disabled/);
assert.match(noSession, /type="number"[^>]*min="0"[^>]*max="2"[^>]*step="0.1"[^>]*value="0.4"/);
assert.match(noSession, /value="32768"/);
assert.match(noSession, /value="262144"/);
assert.match(noSession, /value="60"/);
// Renderable without a payload or a handler catalogue (defaults + one option).
const emptyForm = renderProfileForm(null, { scope: "global" });
assert.match(emptyForm, /尚未读取运行档案/);
assert.match(emptyForm, /<option value="linear" selected>linear<\/option>/);
assert.match(emptyForm, /全局默认/);

console.log("Run profile panel checks passed.");
