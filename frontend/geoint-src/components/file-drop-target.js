/** Present a file-drop affordance without taking ownership of session or network state. */
export function mountFileDropTarget(element, onFiles, onEmptyDrop = () => {}) {
  let depth = 0;
  const hasFiles = (event) => [...(event.dataTransfer?.types || [])].includes("Files");
  const clear = () => { depth = 0; element.classList.remove("file-drop-active"); };
  const enter = (event) => { if (!hasFiles(event)) return; event.preventDefault(); depth += 1; element.classList.add("file-drop-active"); };
  const leave = (event) => { if (!hasFiles(event)) return; depth = Math.max(0, depth - 1); if (!depth) element.classList.remove("file-drop-active"); };
  const over = (event) => { if (hasFiles(event)) event.preventDefault(); };
  const drop = (event) => { if (!hasFiles(event)) return; event.preventDefault(); clear(); const files = [...(event.dataTransfer?.files || [])]; if (files.length) onFiles(files); else onEmptyDrop(); };
  element.addEventListener("dragenter", enter); element.addEventListener("dragleave", leave); element.addEventListener("dragover", over); element.addEventListener("drop", drop);
  return { dispose() { element.removeEventListener("dragenter", enter); element.removeEventListener("dragleave", leave); element.removeEventListener("dragover", over); element.removeEventListener("drop", drop); } };
}
