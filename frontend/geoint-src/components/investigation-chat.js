import { renderMarkdownInto } from "../../static/components/markdown-renderer.js";
import { renderToolResult } from "./tool-result-renderer.js";
// Same admission set as the controller and the backend: offering steering outside
// it only produces a 409 after the operator has already typed the guide.
import { isSteerable } from "../run-states.js";

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
function createContextSummary(node) { const card = document.createElement("aside"), title = document.createElement("strong"), copy = document.createElement("span"); card.className = "investigation-context-summary"; title.textContent = "已恢复 Agent 工作上下文"; copy.textContent = `${node.messages} 条当前记忆 · ${node.characters.toLocaleString()} 字符`; card.append(title, copy); return card; }
function createSteerStatus(node) {
  const card = document.createElement("article"), head = document.createElement("header"), title = document.createElement("strong"), detail = document.createElement("span"), content = document.createElement("p");
  const queued = node.type === "steer_queued", injected = Array.isArray(node.applied) ? node.applied.length : 0;
  card.className = `investigation-steer-status ${queued ? "queued" : "applied"}`;
  title.textContent = queued ? "调查引导已排队" : "调查引导已应用";
  detail.textContent = queued ? (node.targets?.length ? `目标：${node.targets.join("、")}` : "等待 Agent 接收") : `${node.agent || "协调者"}${node.round === "" ? "" : ` · 第 ${node.round} 轮`}${injected ? ` · 已注入 ${injected} 个 Agent` : ""}`;
  content.textContent = node.content;
  head.append(title, detail); card.append(head, content); return card;
}

/** Mount the complete investigation transcript inside its dockable panel. */
export function mountInvestigationChat({ panel, projector, onSend, onSteer, onStop, onLoadOlder = async () => ({ has_more: false }) }) {
  panel.replaceChildren(); panel.classList.add("investigation-chat-panel");
  const head = document.createElement("div"); head.className = "investigation-chat-head";
  head.innerHTML = '<div><span class="eyebrow">ANGELUS ORCHESTRATION</span><h3>证据调查</h3></div><div id="agent-actions" class="action-group"></div>';
  const hint = document.createElement("p"); hint.className = "fineprint"; hint.textContent = "当前会话中的 Agent、资产与工具权限会决定本次调查的可用范围。";
  const status = document.createElement("div"); status.id = "agent-status"; status.className = "investigation-chat-status";
  const timeline = document.createElement("section"); timeline.className = "investigation-timeline"; timeline.setAttribute("aria-live", "polite");
  const composer = document.createElement("label"); composer.className = "investigation-composer"; composer.innerHTML = '<span>调查问题</span><textarea id="agent-prompt" rows="3" placeholder="描述要调查的问题、范围和期望证据。"></textarea><div><small>Ctrl / ⌘ + Enter 发送</small><button class="primary" type="button">发送调查</button></div>';
  const input = composer.querySelector("textarea"), send = composer.querySelector("button");
  panel.append(head, hint, status, timeline, composer);
  let followsLatest = true, frame = 0, snapshot = null, loadingOlder = false, hasOlder = false;
  const atLatest = () => timeline.scrollHeight - timeline.clientHeight - timeline.scrollTop <= scrollTolerance;
  async function loadOlder() {
    if (loadingOlder || !hasOlder) return;
    loadingOlder = true;
    const previousHeight = timeline.scrollHeight, previousTop = timeline.scrollTop;
    try {
      const page = await onLoadOlder(); hasOlder = Boolean(page?.has_more);
      // Rendering happens on the next animation frame; retain the reader's
      // visual anchor rather than jumping them to a different conversation turn.
      requestAnimationFrame(() => { timeline.scrollTop = timeline.scrollHeight - previousHeight + previousTop; if (!frame) frame = requestAnimationFrame(render); });
    } finally { loadingOlder = false; }
  }
  timeline.addEventListener("scroll", () => { followsLatest = atLatest(); if (timeline.scrollTop <= scrollTolerance) loadOlder().catch(() => {}); }, { passive: true });
  function render() {
    frame = 0; if (!snapshot) return;
    const wasAtLatest = followsLatest || atLatest(); timeline.replaceChildren();
    if (hasOlder) { const older = document.createElement("button"); older.type = "button"; older.className = "investigation-load-older"; older.textContent = loadingOlder ? "正在加载更早记录…" : "加载更早记录"; older.disabled = loadingOlder; older.onclick = () => loadOlder().catch(() => {}); timeline.append(older); }
    if (!snapshot.nodes.length) { const empty = document.createElement("p"); empty.className = "empty investigation-empty"; empty.textContent = snapshot.session_id ? "提出一个问题，Agent 会将调查过程与证据操作按时间显示在这里。" : "先在顶部选择或创建一个会话，然后开始调查。"; timeline.append(empty); }
    snapshot.nodes.forEach((node) => { if (node.type === "tool_batch") { const batch = document.createElement("section"); batch.className = "investigation-tool-batch"; const caption = document.createElement("h4"); caption.textContent = `工具操作 · ${node.tools.length} 项`; batch.append(caption); node.tools.forEach((tool) => batch.append(renderToolResult(tool))); timeline.append(batch); } else if (node.type === "system_status") timeline.append(createStatus(node)); else if (node.type === "context_summary") timeline.append(createContextSummary(node)); else if (node.type === "steer_queued" || node.type === "steer_applied") timeline.append(createSteerStatus(node)); else timeline.append(createMessage(node)); });
    const running = snapshot.run_state === "running", stopping = ["stopping", "force_stopping"].includes(snapshot.run_state);
    const followUp = terminalStates.has(snapshot.run_state);
    status.className = `investigation-chat-status${running || stopping ? " running" : terminalStates.has(snapshot.run_state) ? " terminal" : ""}`;
    status.textContent = running ? "调查进行中。可在下方发送引导，补充范围、优先级或证据要求。" : stopping ? "正在停止调查，暂不能发送新的引导。" : snapshot.run_state === "failed" ? "调查失败。可查看上方的错误记录或重新发起。" : snapshot.run_state === "completed" ? "调查已完成。" : ["stopped", "interrupted"].includes(snapshot.run_state) ? "调查已停止。" : snapshot.session_id ? "准备就绪。" : "请选择调查会话。";
    composer.querySelector("span").textContent = running ? "调查引导" : followUp ? "继续调查" : "调查问题";
    input.placeholder = running ? "向正在执行的 Agent 补充方向、范围或优先级。" : followUp ? "基于本轮结果继续调查、要求补充证据或调整方向。" : "描述要调查的问题、范围和期望证据。";
    send.textContent = running ? "发送引导" : followUp ? "继续调查" : "发送调查";
    send.disabled = !snapshot.session_id || stopping;
    input.disabled = !snapshot.session_id || stopping;
    if (wasAtLatest) timeline.scrollTop = timeline.scrollHeight;
  }
  const unsubscribe = projector.subscribe((next) => { snapshot = next; if (!frame) frame = requestAnimationFrame(render); });
  async function submit() { const content = input.value.trim(); if (!content || send.disabled) return; send.disabled = true; try { const steering = isSteerable(snapshot?.run_state); await (steering ? onSteer(content) : onSend(content)); input.value = ""; } catch (error) { projector.applyEvent({ event: "error", message: error?.message || "无法发送调查请求" }); } finally { send.disabled = false; } }
  send.addEventListener("click", submit); input.addEventListener("keydown", (event) => { if ((event.ctrlKey || event.metaKey) && event.key === "Enter") { event.preventDefault(); submit(); } });
  return { focus: () => input.focus(), stop: () => onStop(), setHistoryPaging: (value) => { hasOlder = Boolean(value); if (!frame) frame = requestAnimationFrame(render); }, dispose() { unsubscribe(); if (frame) cancelAnimationFrame(frame); } };
}
