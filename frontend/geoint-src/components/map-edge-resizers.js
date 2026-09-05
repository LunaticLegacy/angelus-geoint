const key = "angelus.geoint.map-edge-widths.v1";
export function installMapEdgeResizers(workspace, mapStage, onResize) {
  const saved = read(); apply(saved.left, saved.right);
  for (const edge of ["left", "right"]) {
    const handle = document.createElement("div"); handle.className = `map-edge-resizer map-edge-resizer-${edge}`; handle.tabIndex = 0; handle.setAttribute("role", "separator"); handle.setAttribute("aria-label", edge === "left" ? "调整左侧工作区宽度" : "调整右侧工作区宽度"); mapStage.append(handle);
    handle.addEventListener('pointerdown', () => { workspace.classList.add('is-resizing'); window.getSelection()?.removeAllRanges(); });
    for (const event of ['pointerup', 'pointercancel', 'lostpointercapture']) handle.addEventListener(event, () => workspace.classList.remove('is-resizing'));
    window.addEventListener('blur', () => workspace.classList.remove('is-resizing'));
    const update = (clientX) => { const box = workspace.getBoundingClientRect(); const value = edge === "left" ? clientX - box.left : box.right - clientX; const bounded = Math.round(Math.max(180, Math.min(520, value))); apply(edge === "left" ? bounded : null, edge === "right" ? bounded : null); persist(); onResize(); };
    handle.addEventListener("pointerdown", (event) => { event.preventDefault(); handle.setPointerCapture(event.pointerId); const move = (next) => update(next.clientX); const end = () => { handle.removeEventListener("pointermove", move); handle.removeEventListener("pointerup", end); handle.removeEventListener("pointercancel", end); }; handle.addEventListener("pointermove", move); handle.addEventListener("pointerup", end); handle.addEventListener("pointercancel", end); });
    handle.addEventListener("keydown", (event) => { if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return; event.preventDefault(); const current = Number.parseInt(getComputedStyle(workspace).getPropertyValue(edge === "left" ? "--left-width" : "--right-width"), 10) || (edge === "left" ? 236 : 400); const delta = event.key === "ArrowLeft" ? -20 : 20; update(edge === "left" ? workspace.getBoundingClientRect().left + current + delta : workspace.getBoundingClientRect().right - current - delta); });
  }
  function read() { try { const value = JSON.parse(localStorage.getItem(key)); return { left: Number(value?.left) || 236, right: Number(value?.right) || 400 }; } catch { return { left: 236, right: 400 }; } }
  function apply(left, right) { if (left) workspace.style.setProperty("--left-width", `${left}px`); if (right) workspace.style.setProperty("--right-width", `${right}px`); }
  function persist() { localStorage.setItem(key, JSON.stringify({ left: Number.parseInt(getComputedStyle(workspace).getPropertyValue("--left-width"), 10), right: Number.parseInt(getComputedStyle(workspace).getPropertyValue("--right-width"), 10) })); }
}
