const key = "angelus.geoint.dock-layout.v2";
const defaults = { left: ["layers"], right: ["agent", "evidence"], bottom: ["trace", "session", "context", "connector", "basemap"], active: { left: "layers", right: "agent", bottom: "trace" } };
const clone = () => structuredClone(defaults);
export function createDockLayout({ workspace, leftRail, rightRail, onLayoutChange = () => {}, onActivePanelsChange = () => {} }) {
  let panels = new Map(), layout = load();
  const scrollOffsets = new WeakMap();
  const bottomRail = document.createElement("aside"); bottomRail.className = "panel bottom-dock"; workspace.append(bottomRail);
  const zones = { left: makeZone(leftRail, "left"), right: makeZone(rightRail, "right"), bottom: makeZone(bottomRail, "bottom") };
  function load() { try { const value = JSON.parse(localStorage.getItem(key)); if (value?.left && value?.right && value?.bottom) return value; } catch {} return clone(); }
  function save() { localStorage.setItem(key, JSON.stringify(layout)); }
  function makeZone(parent, id) { const root = document.createElement("section"); root.className = `dock-zone dock-zone-${id}`; root.dataset.zone = id; const tabs = document.createElement("div"); tabs.className = "dock-tabs"; const host = document.createElement("div"); host.className = "dock-host"; host.dataset.placeholder = "将面板拖到这里"; root.append(tabs, host); parent.append(root); root.addEventListener("dragover", (event) => { event.preventDefault(); root.classList.add("drag-over"); }); root.addEventListener("dragleave", () => root.classList.remove("drag-over")); root.addEventListener("drop", (event) => { event.preventDefault(); root.classList.remove("drag-over"); move(event.dataTransfer.getData("text/plain"), id); }); return { root, tabs, host }; }
  function normalize() { const known = new Set(panels.keys()), seen = new Set(); for (const zone of ["left", "right", "bottom"]) layout[zone] = (layout[zone] || []).filter((id) => known.has(id) && !seen.has(id) && seen.add(id)); for (const id of known) if (!seen.has(id)) layout.right.push(id); for (const zone of ["left", "right", "bottom"]) if (!layout[zone].includes(layout.active?.[zone])) layout.active[zone] = layout[zone][0] || null; }
  function rememberScroll(panel) { scrollOffsets.set(panel, { top: panel.scrollTop, left: panel.scrollLeft }); }
  function restoreScroll(panel) { const position = scrollOffsets.get(panel); if (position) requestAnimationFrame(() => { panel.scrollTop = position.top; panel.scrollLeft = position.left; }); }
  function notifyActive() { onActivePanelsChange(new Set(Object.values(layout.active).filter(Boolean))); }
  function tabFor(id, zone) {
    const panel = panels.get(id), tab = document.createElement("button");
    tab.type = "button"; tab.className = `dock-tab${layout.active[zone] === id ? " active" : ""}`;
    tab.textContent = panel.title; tab.draggable = true;
    tab.addEventListener("dragstart", (event) => { event.dataTransfer.effectAllowed = "move"; event.dataTransfer.setData("text/plain", id); });
    tab.addEventListener("dragover", (event) => event.preventDefault());
    tab.addEventListener("drop", (event) => { event.preventDefault(); event.stopPropagation(); move(event.dataTransfer.getData("text/plain"), zone, id); });
    // Selecting a sibling is intentionally not a layout reconciliation: all
    // mounted panel nodes, their input state, and their scroll offsets stay put.
    tab.onclick = () => { layout.active[zone] = id; save(); renderZone(zone, false); notifyActive(); };
    return tab;
  }
  function renderZone(zone, reconcile) {
    const view = zones[zone], ids = layout[zone];
    view.tabs.replaceChildren(...ids.map((id) => tabFor(id, zone)));
    view.root.classList.toggle("empty", !ids.length);
    if (reconcile) {
      ids.forEach((id) => rememberScroll(panels.get(id).element));
      view.host.replaceChildren(...ids.map((id) => panels.get(id).element));
    }
    ids.forEach((id) => {
      const panel = panels.get(id).element;
      panel.classList.toggle("active", layout.active[zone] === id);
      if (reconcile) restoreScroll(panel);
    });
  }
  function render(reconcile = true) {
    normalize();
    for (const zone of ["left", "right", "bottom"]) renderZone(zone, reconcile);
    notifyActive();
  }
  function move(id, target, before = null) { if (!panels.has(id) || !zones[target]) return; for (const zone of ["left", "right", "bottom"]) layout[zone] = layout[zone].filter((item) => item !== id); const index = before ? layout[target].indexOf(before) : -1; index < 0 ? layout[target].push(id) : layout[target].splice(index, 0, id); layout.active[target] = id; save(); render(); onLayoutChange(); }
  return { mount(items) { document.getElementById("workspace-tabs")?.remove(); panels = new Map(items.map((item) => [item.id, item])); render(); }, reset() { layout = clone(); save(); render(); onLayoutChange(); }, layout: () => structuredClone(layout) };
}
