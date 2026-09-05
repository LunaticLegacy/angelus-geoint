const secretKey = /(?:api[_-]?key|authorization|credential|password|secret|token)/i;
const pathKey = /(?:path|directory|filename|file)/i;
const maxDepth = 5, maxEntries = 80, maxText = 12_000;
const text = (value) => String(value ?? "");

function decoded(value) {
  let current = value;
  for (let depth = 0; depth < 2 && typeof current === "string"; depth += 1) {
    const candidate = current.trim(); if (!/^(\{|\[|\")/.test(candidate)) break;
    try { current = JSON.parse(candidate); } catch { break; }
  }
  return current;
}
function protectedValue(key, value) {
  if (secretKey.test(key)) return "[已脱敏]";
  if (pathKey.test(key) && typeof value === "string" && (value.startsWith("/") || /^[A-Za-z]:[\\/]/.test(value))) return "[受控路径]";
  return value;
}
function safeScalar(value) {
  const raw = text(value); return raw.length > maxText ? `${raw.slice(0, maxText)}\n… 已截断` : raw;
}
function tree(value, depth = 0, key = "") {
  const content = protectedValue(key, decoded(value));
  if (depth >= maxDepth) { const item = document.createElement("span"); item.textContent = "…"; return item; }
  if (Array.isArray(content) || (content && typeof content === "object")) {
    const entries = Array.isArray(content) ? content.map((item, index) => [String(index), item]) : Object.entries(content);
    const details = document.createElement("details"); details.className = "tool-json-node"; details.open = depth < 1;
    const summary = document.createElement("summary"); summary.textContent = `${Array.isArray(content) ? "列表" : "对象"} · ${entries.length} 项`; details.append(summary);
    const list = document.createElement("dl");
    entries.slice(0, maxEntries).forEach(([entryKey, item]) => { const term = document.createElement("dt"), description = document.createElement("dd"); term.textContent = entryKey; description.append(tree(item, depth + 1, entryKey)); list.append(term, description); });
    if (entries.length > maxEntries) { const note = document.createElement("p"); note.textContent = `另有 ${entries.length - maxEntries} 项未显示`; list.append(note); }
    details.append(list); return details;
  }
  const output = document.createElement("span"); output.className = "tool-scalar"; output.textContent = content === null ? "null" : safeScalar(content); return output;
}
function summary(value) {
  const content = decoded(value);
  if (content === undefined || content === null || content === "") return "无返回内容";
  if (Array.isArray(content)) return `返回 ${content.length} 项`;
  if (typeof content === "object") return `返回 ${Object.keys(content).length} 个字段`;
  const chars = text(content).length; return chars ? `返回文本 · ${chars} 字符` : "无返回内容";
}
function duration(value) { const ms = Number(value); if (!Number.isFinite(ms) || ms < 0) return ""; return ms < 1000 ? `${Math.round(ms)} ms` : `${(ms / 1000).toFixed(ms < 10_000 ? 2 : 1)} 秒`; }

/** Render one semantic tool envelope without branching on tool identity. */
export function renderToolResult(envelope) {
  const card = document.createElement("article"), state = envelope.status === "error" ? "error" : envelope.status === "running" ? "running" : "success";
  card.className = `investigation-tool ${state}`;
  const header = document.createElement("header"), title = document.createElement("strong"), meta = document.createElement("span");
  title.textContent = state === "running" ? "正在调用工具" : state === "error" ? "工具调用失败" : "工具调用完成";
  meta.textContent = [state === "running" ? "执行中" : state === "error" ? "失败" : "已完成", duration(envelope.duration_ms)].filter(Boolean).join(" · "); header.append(title, meta); card.append(header);
  const caption = document.createElement("p"); caption.className = "tool-summary"; caption.textContent = state === "running" ? "等待工具返回结构化结果…" : summary(envelope.output); card.append(caption);
  const details = document.createElement("details"); details.className = "tool-audit";
  const detailsTitle = document.createElement("summary"); detailsTitle.textContent = "查看调用详情"; details.append(detailsTitle);
  const name = document.createElement("p"); name.className = "tool-audit-meta"; name.textContent = `工具：${text(envelope.tool_name || "未命名")}${envelope.call_id ? ` · 调用 ${text(envelope.call_id)}` : ""}`; details.append(name);
  [["输入", envelope.input, "无参数"], ["输出", envelope.output, "无返回内容"]].forEach(([label, value, empty]) => { const section = document.createElement("section"), heading = document.createElement("h5"); heading.textContent = label; section.append(heading); if (value === undefined || value === null || value === "") { const placeholder = document.createElement("p"); placeholder.textContent = empty; section.append(placeholder); } else section.append(tree(value)); details.append(section); });
  card.append(details); return card;
}
