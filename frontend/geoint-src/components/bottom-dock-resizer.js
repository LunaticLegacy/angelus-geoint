const key = "angelus.geoint.bottom-dock-height.v1";

/** Install the shell-only splitter at the top edge of the bottom Dock. */
export function installBottomDockResizer(workspace, bottomDock, onResize = () => {}) {
  if (!workspace || !bottomDock) return;
  const saved = Number(localStorage.getItem(key));
  if (Number.isFinite(saved)) apply(bound(saved));
  const handle = document.createElement("div");
  handle.className = "bottom-dock-resizer"; handle.tabIndex = 0;
  handle.setAttribute("role", "separator"); handle.setAttribute("aria-label", "调整下方工作台高度");
  bottomDock.append(handle);
  handle.addEventListener('pointerdown', () => { workspace.classList.add('is-resizing'); window.getSelection()?.removeAllRanges(); });
  for (const event of ['pointerup', 'pointercancel', 'lostpointercapture']) handle.addEventListener(event, () => workspace.classList.remove('is-resizing'));
  window.addEventListener('blur', () => workspace.classList.remove('is-resizing'));
  function maximum() { return Math.max(220, Math.min(720, workspace.getBoundingClientRect().height - 180)); }
  function bound(value) { return Math.round(Math.max(180, Math.min(maximum(), value))); }
  function apply(value) { workspace.style.setProperty("--bottom-height", `${value}px`); }
  function update(clientY) { const box = workspace.getBoundingClientRect(), value = bound(box.bottom - clientY); apply(value); localStorage.setItem(key, String(value)); onResize(); }
  handle.addEventListener("pointerdown", (event) => { event.preventDefault(); handle.setPointerCapture(event.pointerId); const move = (next) => update(next.clientY); const end = () => { handle.removeEventListener("pointermove", move); handle.removeEventListener("pointerup", end); handle.removeEventListener("pointercancel", end); }; handle.addEventListener("pointermove", move); handle.addEventListener("pointerup", end); handle.addEventListener("pointercancel", end); });
  handle.addEventListener("keydown", (event) => { if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return; event.preventDefault(); const current = Number.parseInt(getComputedStyle(workspace).getPropertyValue("--bottom-height"), 10) || Math.round(workspace.getBoundingClientRect().height * .32); const delta = event.key === "ArrowUp" ? 24 : -24; update(workspace.getBoundingClientRect().bottom - current - delta); });
}
