import { renderMarkdownInto } from "../../static/components/markdown-renderer.js";
import { renderToolResult } from "./tool-result-renderer.js";

const terminalStates = new Set(["completed", "failed", "stopped", "interrupted"]);
const scrollTolerance = 10;

function createMessage(node) {
  const card = document.createElement("article"), isUser = node.type === "user_message";
  card.className = `investigation-message ${isUser ? "user" : "assistant"}${node.type === "assistant_draft" ? " streaming" : ""}`;
  const header = document.createElement("header"), author = document.createElement("strong"), state = document.createElement("span");
  author.textContent = isUser ? "你" : node.agent || "协调者";
  state.textContent = node.type === "assistant_draft" ? "正在生成" : isUser ? "调查问题" : "调查回复";
  header.append(author, state); card.append(header);
  if (node.reasoning) { const reasoning = document.createElement("details"), label = document.createElement("summary"), content = document.createElement("div"); reasoning.className = "investigation-reasoning"; label.textContent = "推理过程"; content.className = "markdown"; renderMarkdownInto(content, node.reasoning); reasoning.append(label, content); card.append(reasoning); }
  if (node.content) { const content = document.createElement("div"); content.className = isUser ? "plain-text" : "markdown"; if (isUser) content.textContent = node.content; else renderMarkdownInto(content, node.content); card.append(content); }
  return card;
}

function createStatus(node) { const card = document.createElement("article"); card.className = "investigation-system-status"; card.textContent = node.content; return card; }
function createContextSummary(node) { const card = document.createElement("aside"), title = document.createElement("strong"), copy = document.createElement("span"); card.className = "investigation-context-summary"; title.textContent = "已恢复会话上下文"; copy.textContent = `${node.messages} 条记录 · ${node.characters.toLocaleString()} 字符`; card.append(title, copy); return card; }

/** Mount the complete investigation transcript inside its dockable panel. */
export function mountInvestigationChat({ panel, projector, onSend, onStop }) {
  panel.replaceChildren(); panel.classList.add("investigation-chat-panel");
  const head = document.createElement("div"); head.className = "investigation-chat-head";
  head.innerHTML = '<div><span class="eyebrow">ANGELUS ORCHESTRATION</span><h3>证据调查</h3></div><div id="agent-actions" class="action-group"></div>';
  const hint = document.createElement("p"); hint.className = "fineprint"; hint.textContent = "当前会话中的 Agent、资产与工具权限会决定本次调查的可用范围。";
  const status = document.createElement("div"); status.id = "agent-status"; status.className = "investigation-chat-status";
  const timeline = document.createElement("section"); timeline.className = "investigation-timeline"; timeline.setAttribute("aria-live", "polite");
  const composer = document.createElement("label"); composer.className = "investigation-composer"; composer.innerHTML = '<span>调查问题</span><textarea id="agent-prompt" rows="3" placeholder="描述要调查的问题、范围和期望证据。"></textarea><div><small>Ctrl / ⌘ + Enter 发送</small><button class="primary" type="button">发送调查</button></div>';
  const input = composer.querySelector("textarea"), send = composer.querySelector("button");
  panel.append(head, hint, status, timeline, composer);
  let followsLatest = true, frame = 0, snapshot = null;
  const atLatest = () => timeline.scrollHeight - timeline.clientHeight - timeline.scrollTop <= scrollTolerance;
  timeline.addEventListener("scroll", () => { followsLatest = atLatest(); }, { passive: true });
  function render() {
    frame = 0; if (!snapshot) return;
    const wasAtLatest = followsLatest || atLatest(); timeline.replaceChildren();
    if (!snapshot.nodes.length) { const empty = document.createElement("p"); empty.className = "empty investigation-empty"; empty.textContent = snapshot.session_id ? "提出一个问题，Agent 会将调查过程与证据操作按时间显示在这里。" : "先在顶部选择或创建一个会话，然后开始调查。"; timeline.append(empty); }
    snapshot.nodes.forEach((node) => { if (node.type === "tool_batch") { const batch = document.createElement("section"); batch.className = "investigation-tool-batch"; const caption = document.createElement("h4"); caption.textContent = `工具操作 · ${node.tools.length} 项`; batch.append(caption); node.tools.forEach((tool) => batch.append(renderToolResult(tool))); timeline.append(batch); } else if (node.type === "system_status") timeline.append(createStatus(node)); else if (node.type === "context_summary") timeline.append(createContextSummary(node)); else timeline.append(createMessage(node)); });
    const running = ["running", "stopping", "force_stopping"].includes(snapshot.run_state);
    status.className = `investigation-chat-status${running ? " running" : terminalStates.has(snapshot.run_state) ? " terminal" : ""}`;
    status.textContent = running ? "调查进行中。流式回复与工具执行会实时显示。" : snapshot.run_state === "failed" ? "调查失败。可查看上方的错误记录或重新发起。" : snapshot.run_state === "completed" ? "调查已完成。" : ["stopped", "interrupted"].includes(snapshot.run_state) ? "调查已停止。" : snapshot.session_id ? "准备就绪。" : "请选择调查会话。";
    send.disabled = !snapshot.session_id || running;
    input.disabled = !snapshot.session_id || running;
    if (wasAtLatest) timeline.scrollTop = timeline.scrollHeight;
  }
  const unsubscribe = projector.subscribe((next) => { snapshot = next; if (!frame) frame = requestAnimationFrame(render); });
  async function submit() { const content = input.value.trim(); if (!content || send.disabled) return; send.disabled = true; try { await onSend(content); input.value = ""; } catch (error) { projector.applyEvent({ event: "error", message: error?.message || "无法发起调查" }); } finally { send.disabled = false; } }
  send.addEventListener("click", submit); input.addEventListener("keydown", (event) => { if ((event.ctrlKey || event.metaKey) && event.key === "Enter") { event.preventDefault(); submit(); } });
  return { focus: () => input.focus(), stop: () => onStop(), dispose() { unsubscribe(); if (frame) cancelAnimationFrame(frame); } };
}
