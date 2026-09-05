/** Move one layer before another in the top-to-bottom panel ordering. */
export function reorderLayerIds(ids, draggedId, targetId) {
  const ordered = [...ids];
  if (draggedId === targetId || !ordered.includes(draggedId) || !ordered.includes(targetId)) return ordered;
  ordered.splice(ordered.indexOf(draggedId), 1);
  ordered.splice(ordered.indexOf(targetId), 0, draggedId);
  return ordered;
}

function sourceLabel(layer) {
  if (layer.source?.kind === "cog" || layer.render?.kind === "raster") return "栅格 · COG";
  if (layer.source?.kind === "xyz") return "栅格 · XYZ";
  return "矢量 · GeoJSON";
}

function editableTitle(layer, groups) {
  const group = groups.get(layer.group_id)?.title || "未分组";
  const render = layer.render && typeof layer.render === "object" ? layer.render : {};
  if (render.kind !== "raster") return `${group} · ${sourceLabel(layer)}`;
  const mode = render.mode === "classified" ? "分类" : render.mode === "rgb" ? "RGB" : "单波段";
  const method = render.range?.method === "manual" ? "手动拉伸" : "统计拉伸";
  return `${group} · ${sourceLabel(layer)} · ${mode}${render.mode === "classified" ? "渲染" : ` · ${method}`}`;
}

const HEX_COLOR = /^#[0-9a-f]{6}$/i;

export function parseIgnoredValues(text) {
  return [...new Set(String(text || "").split(/[，,\s]+/).map(Number).filter(Number.isFinite))].slice(0, 128);
}

function classesFrom(render) {
  if (!Array.isArray(render.classification)) return [];
  const seen = new Set();
  return render.classification.filter((entry) => {
    if (!entry || !Number.isFinite(entry.value) || seen.has(entry.value) || !HEX_COLOR.test(entry.color || "")) return false;
    seen.add(entry.value); return true;
  }).slice(0, 128).map((entry) => ({ value: entry.value, label: typeof entry.label === "string" ? entry.label : "", color: entry.color }));
}

function createClassificationRow(entry, remove) {
  const row = document.createElement("div"); row.className = "raster-class-row";
  const value = document.createElement("input"); value.type = "number"; value.step = "any"; value.value = String(entry.value); value.setAttribute("aria-label", "栅格数值");
  const label = document.createElement("input"); label.type = "text"; label.maxLength = 80; label.value = entry.label; label.placeholder = "显示名称，例如草地"; label.setAttribute("aria-label", "类别显示名称");
  const color = document.createElement("input"); color.type = "color"; color.value = entry.color; color.setAttribute("aria-label", "类别颜色");
  const button = document.createElement("button"); button.type = "button"; button.className = "icon-btn danger-soft"; button.textContent = "×"; button.title = "删除类别"; button.onclick = () => remove(entry);
  row.append(value, label, color, button);
  return { row, entry, value, label, color };
}

function createRasterEditor(layer, save) {
  const render = layer.render && typeof layer.render === "object" ? layer.render : {};
  const bands = Array.isArray(render.bands) && render.bands.length ? render.bands : [1];
  const canClassify = bands.length === 1;
  const details = document.createElement("details"); details.className = "raster-render-editor";
  const summary = document.createElement("summary"); summary.textContent = canClassify ? "栅格显示设置" : "栅格显示 · RGB 统计拉伸";
  details.append(summary);
  if (!canClassify) {
    const hint = document.createElement("p"); hint.className = "fineprint"; hint.textContent = "多波段数据按各波段统计范围拉伸。分类值、别名和背景忽略仅适用于单波段整数栅格。";
    details.append(hint); return details;
  }

  const body = document.createElement("div"); body.className = "raster-render-body";
  const modeLabel = document.createElement("label"); modeLabel.textContent = "显示方式";
  const mode = document.createElement("select"); mode.setAttribute("aria-label", "栅格显示方式");
  mode.add(new Option("连续值 · 统计拉伸", "single_band")); mode.add(new Option("整数类别 · 颜色与别名", "classified"));
  mode.value = render.mode === "classified" ? "classified" : "single_band"; modeLabel.append(mode);
  const ignoredLabel = document.createElement("label"); ignoredLabel.textContent = "忽略的背景值";
  const ignored = document.createElement("input"); ignored.type = "text"; ignored.placeholder = "例如 0, 255, -9999"; ignored.value = Array.isArray(render.ignore_values) ? render.ignore_values.join(", ") : ""; ignoredLabel.append(ignored);
  const hint = document.createElement("p"); hint.className = "fineprint"; hint.textContent = "忽略值会透明显示；它不同于文件内置 NoData，适合去除编码背景。";

  const classes = classesFrom(render); const classArea = document.createElement("section"); classArea.className = "raster-classification";
  const caption = document.createElement("strong"); caption.textContent = "分类值、别名与颜色";
  const rows = document.createElement("div"); rows.className = "raster-class-list";
  const rowEntries = [];
  function rebuildRows() {
    rows.replaceChildren(); rowEntries.length = 0;
    classes.forEach((entry) => {
      const item = createClassificationRow(entry, (target) => { classes.splice(classes.indexOf(target), 1); rebuildRows(); });
      rowEntries.push(item); rows.append(item.row);
    });
  }
  const add = document.createElement("button"); add.type = "button"; add.className = "secondary raster-add-class"; add.textContent = "添加类别";
  add.onclick = () => { if (classes.length >= 128) return; classes.push({ value: 0, label: "", color: "#6baed6" }); rebuildRows(); };
  classArea.append(caption, rows, add); rebuildRows();
  function updateMode() { classArea.hidden = mode.value !== "classified"; }
  mode.onchange = updateMode; updateMode();

  const saveButton = document.createElement("button"); saveButton.type = "button"; saveButton.className = "primary raster-save-style"; saveButton.textContent = "应用栅格样式";
  saveButton.onclick = () => {
    const ignoreValues = parseIgnoredValues(ignored.value);
    const next = { ...render, kind: "raster", mode: mode.value, bands: [bands[0]], ignore_values: ignoreValues };
    if (mode.value === "classified") {
      const classified = rowEntries.map((item) => ({ value: Number(item.value.value), label: item.label.value.trim(), color: item.color.value }))
        .filter((item) => Number.isFinite(item.value) && item.label.length <= 80 && HEX_COLOR.test(item.color));
      next.classification = classified; next.interpolate = false;
    } else {
      delete next.classification; next.interpolate = render.interpolate !== false;
    }
    save({ type: "patch", id: layer.id, patch: { render: next } });
  };
  body.append(modeLabel, ignoredLabel, hint, classArea, saveButton); details.append(body);
  return details;
}

/**
 * Render evidence layers top-to-bottom. The caller persists their resulting
 * high-to-low z-index values, keeping component rendering state-free.
 */
export function renderLayerPanel(host, mapDocument, save) {
  host.replaceChildren();
  const groups = new Map(mapDocument.groups.map((group) => [group.id, group]));
  const ordered = mapDocument.layers
    .map((layer, index) => ({ layer, index }))
    .sort((left, right) => right.layer.z_index - left.layer.z_index || left.index - right.index)
    .map(({ layer }) => layer);
  let draggingId = null;

  for (const [index, layer] of ordered.entries()) {
    const card = document.createElement("article");
    card.className = "layer-card";
    card.draggable = true;
    card.dataset.layerId = layer.id;

    const header = document.createElement("div"); header.className = "layer-card-header";
    const handle = document.createElement("span"); handle.className = "layer-drag-handle"; handle.title = "拖动以调整渲染顺序"; handle.setAttribute("aria-label", "拖动以调整渲染顺序"); handle.textContent = "⠿";
    const visible = document.createElement("input"); visible.type = "checkbox"; visible.checked = layer.visible; visible.className = "layer-visible"; visible.setAttribute("aria-label", `显示图层：${layer.title}`);
    const heading = document.createElement("div"); heading.className = "layer-heading";
    const meta = document.createElement("span"); meta.className = "layer-meta"; meta.textContent = editableTitle(layer, groups);
    const title = document.createElement("strong"); title.textContent = layer.title;
    heading.append(meta, title);
    const order = document.createElement("span"); order.className = "layer-order"; order.textContent = index === 0 ? "最上层" : `第 ${index + 1} 层`;
    const remove = document.createElement("button"); remove.type = "button"; remove.className = "layer-remove";
    remove.textContent = "移除"; remove.title = `从当前会话地图移除 ${layer.title}`;
    remove.setAttribute("aria-label", `从当前会话地图移除 ${layer.title}`);
    remove.onclick = () => save({ type: "remove", id: layer.id });
    header.append(handle, visible, heading, order, remove);

    const controls = document.createElement("div"); controls.className = "layer-card-controls";
    const opacityLabel = document.createElement("span"); opacityLabel.textContent = "不透明度";
    const opacityValue = document.createElement("output"); opacityValue.textContent = `${Math.round(layer.opacity * 100)}%`;
    const opacity = document.createElement("input"); opacity.type = "range"; opacity.min = "0"; opacity.max = "1"; opacity.step = ".05"; opacity.value = String(layer.opacity); opacity.setAttribute("aria-label", `${layer.title} 不透明度`);
    opacity.oninput = () => { opacityValue.textContent = `${Math.round(Number(opacity.value) * 100)}%`; };
    opacity.onchange = () => save({ type: "patch", id: layer.id, patch: { opacity: Number(opacity.value) } });
    visible.onchange = () => save({ type: "patch", id: layer.id, patch: { visible: visible.checked } });
    controls.append(opacityLabel, opacityValue, opacity);
    card.append(header, controls);
    if (layer.render?.kind === "raster") card.append(createRasterEditor(layer, save));

    card.addEventListener("dragstart", (event) => {
      if (!event.target.closest(".layer-drag-handle")) { event.preventDefault(); return; }
      draggingId = layer.id; card.classList.add("dragging");
      event.dataTransfer.effectAllowed = "move"; event.dataTransfer.setData("text/plain", layer.id);
    });
    card.addEventListener("dragend", () => { draggingId = null; host.querySelectorAll(".layer-card").forEach((item) => item.classList.remove("dragging", "drop-target")); });
    card.addEventListener("dragover", (event) => { if (draggingId && draggingId !== layer.id) { event.preventDefault(); card.classList.add("drop-target"); } });
    card.addEventListener("dragleave", () => card.classList.remove("drop-target"));
    card.addEventListener("drop", (event) => {
      event.preventDefault(); card.classList.remove("drop-target");
      const dragged = draggingId || event.dataTransfer.getData("text/plain");
      const ids = ordered.map((item) => item.id); const next = reorderLayerIds(ids, dragged, layer.id);
      if (next.join("|") !== ids.join("|")) save({ type: "reorder", ids: next });
    });
    host.append(card);
  }
}
