export const byId = (id) => document.getElementById(id);
export function setStatus(text) { byId("status-text").textContent = text; }
export function setRun(state = "idle") { byId("run-pill").textContent = `INVESTIGATION · ${String(state).toUpperCase()}`; }
export function selectedValue(id) { const value = byId(id).value; if (!value) throw new Error("请先选择会话"); return value; }
export function actionHref(action, values = {}) { return Object.entries(values).reduce((href, [key, value]) => href.replace(`{${key}}`, encodeURIComponent(value)), action.href); }
