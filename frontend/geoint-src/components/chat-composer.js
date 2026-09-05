export function installChatComposer(onSend) {
  const field = document.querySelector(".agent-compose"), input = document.getElementById("agent-prompt");
  if (!field || !input) return;
  const button = document.createElement("button"); button.type = "button"; button.className = "primary chat-send"; button.textContent = "发送调查";
  const submit = async () => { button.disabled = true; try { await onSend(); } finally { button.disabled = false; } };
  button.onclick = submit;
  input.addEventListener("keydown", (event) => { if ((event.ctrlKey || event.metaKey) && event.key === "Enter") { event.preventDefault(); submit(); } });
  field.append(button);
}
