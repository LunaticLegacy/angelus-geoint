import assert from "node:assert/strict";
import { createSessions } from "./session-controller.js";
import { createSessionRequestScope } from "../session-request-scope.js";

// Deliberately tiny DOM: the refresh path only needs id lookup, child lists and a few
// properties.  A hand-written stub keeps the assertions honest about what the code
// actually touches -- in particular that it never assigns #session-profile.value.
const elements = new Map();
class StubElement {
  constructor(tag) { this.tagName = String(tag).toUpperCase(); this.children = []; this.parentElement = null; this.attributes = {}; this.className = ""; this.id = ""; this.textContent = ""; this.hidden = false; this.disabled = false; this.checked = false; this.type = ""; this.title = ""; this.onclick = null; this.onchange = null; this.replaceChildrenCalls = 0; }
  append(...nodes) { for (const node of nodes) { node.parentElement = this; this.children.push(node); if (node.id) elements.set(node.id, node); } }
  replaceChildren(...nodes) { this.replaceChildrenCalls += 1; this.children = []; this.append(...nodes); }
  setAttribute(name, value) { this.attributes[name] = String(value); }
  closest(selector) { const wanted = selector.replace(/^\./, ""); for (let node = this; node; node = node.parentElement) if (String(node.className).split(/\s+/).includes(wanted)) return node; return null; }
}
globalThis.document = { createElement: (tag) => new StubElement(tag), getElementById: (id) => elements.get(id) ?? null };

const permissionSection = new StubElement("section"); permissionSection.className = "tool-permissions";
const permissionList = new StubElement("div"); permissionList.id = "tool-permission-list"; permissionSection.append(permissionList);
const refreshButton = new StubElement("button"); refreshButton.id = "tool-permissions-refresh"; refreshButton.disabled = true; elements.set(refreshButton.id, refreshButton);
const statusText = new StubElement("p"); statusText.id = "status-text"; elements.set(statusText.id, statusText);
const sessionProfile = new StubElement("textarea"); sessionProfile.id = "session-profile"; elements.set(sessionProfile.id, sessionProfile);

// The draft trap: any assignment here means the refresh overwrote what the user typed.
const draftWrites = [];
let draft = '{ "effective": { "shell_network_mode": "isolated" } } // half-edited by the user';
Object.defineProperty(sessionProfile, "value", { get: () => draft, set: (next) => { draftWrites.push(String(next)); draft = String(next); } });

let sessionId = "session_demo", profile = null, profileSets = 0;
const state = { sessionId: () => sessionId, profile: () => profile, setProfile: (next) => { profileSets += 1; profile = next; }, sessions: () => [], selectSession: (id) => { sessionId = id; } };
const requestScope = createSessionRequestScope(state);

const catalog = { revision: 7, categories: [
  { id: "core", title: "核心工具", tools: [{ id: "geoint_manage_map_layers", title: "图层" }, { id: "geoint_query_features", title: "查询" }] },
  { id: "geo", title: "地理处理", tools: [{ id: "geoint_buffer", title: "缓冲" }] },
] };
const requests = [];
const okResponse = () => ({ ok: true, status: 200, statusText: "OK", text: async () => JSON.stringify(catalog) });
let responder = okResponse;
globalThis.fetch = async (url, options = {}) => { requests.push({ url, options }); return responder(); };
const feedback = () => elements.get("tool-permission-feedback");

const sessions = createSessions({ state, sources: {}, requestScope });
profile = { effective: { tool_permissions: { categories: { core: true }, tools: { geoint_buffer: true } } } };

// 1) Happy path.  The registry must be read from the real endpoint, and the list is
//    re-rendered from the live catalog while the persisted policy supplies the ticks.
assert.equal(await sessions.refreshCatalog().then((value) => value.revision), 7);
assert.equal(requests.length, 1);
assert.equal(requests[0].url, "/api/tool-registry");
assert.equal(requests[0].options.method, undefined);
assert.equal(permissionList.replaceChildrenCalls, 1);
assert.deepEqual(permissionList.children.map((node) => node.className), ["tool-category", "tool-category"]);
assert.equal(permissionList.children[0].children[0].children[0].checked, true, "persisted category tick survives the refresh");
assert.equal(permissionList.children[1].children[0].children[0].checked, false);
assert.equal(feedback().textContent, "工具集已刷新：2 个类别、3 个工具。");
assert.equal(feedback().className, "setting-feedback ok");
assert.equal(statusText.textContent, "工具集已刷新：2 个类别、3 个工具。");
assert.equal(refreshButton.disabled, false, "busy lock is released once the request settles");

// 2) No session: no request at all, button locked, and the user is told why.
requestScope.select("");
requests.length = 0;
refreshButton.disabled = false;
assert.equal(await sessions.refreshCatalog(), null);
assert.equal(requests.length, 0);
assert.match(feedback().textContent, /请先选择会话后再刷新工具集/);
assert.equal(refreshButton.disabled, true);
assert.equal(permissionList.replaceChildrenCalls, 1, "no session means no render");

// 3) HTTP failure: error feedback, no throw, and the rendered list is left alone.
requestScope.select("session_demo");
requests.length = 0;
responder = () => ({ ok: false, status: 500, statusText: "Internal Server Error", text: async () => JSON.stringify({ detail: "registry unavailable" }) });
assert.equal(await sessions.refreshCatalog(), null);
assert.equal(requests[0].url, "/api/tool-registry");
assert.match(feedback().textContent, /^工具集刷新失败：/);
assert.equal(feedback().className, "setting-feedback error");
assert.equal(permissionList.replaceChildrenCalls, 1, "a failed refresh keeps the checkboxes already on screen");
assert.equal(refreshButton.disabled, false);

// 4) Transport rejection is reported the same way instead of rejecting into the caller.
responder = () => { throw new Error("network down"); };
assert.equal(await sessions.refreshCatalog(), null);
assert.match(feedback().textContent, /工具集刷新失败：network down/);

// 5) A response that lands after the session changed is discarded, not rendered.
let release; const gate = new Promise((resolve) => { release = resolve; });
responder = () => gate.then(okResponse);
const pending = sessions.refreshCatalog();
requestScope.select("session_other");
release();
assert.equal(await pending, null);
assert.equal(permissionList.replaceChildrenCalls, 1, "stale catalog is dropped");

// 6) The whole run never touched the JSON draft or the stored profile.
assert.deepEqual(draftWrites, []);
assert.equal(profileSets, 0);
console.log("Session tool-catalog refresh checks passed.");
