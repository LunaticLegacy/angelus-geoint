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

const HEX_COLOR = /^#[0-9a-f]{6}$/i;

export function vectorRenderDraft(render) {
  const value = render && typeof render === "object" ? render : {};
  const opacity = Number(value.fill_opacity);
  return {
    kind: "vector",
    stroke_color: HEX_COLOR.test(value.stroke_color || "") ? value.stroke_color : "#3f82e8",
    fill_color: HEX_COLOR.test(value.fill_color || "") ? value.fill_color : "#3f82e8",
    fill_opacity: Number.isFinite(opacity) && opacity >= 0 && opacity <= 1 ? opacity : .11,
  };
}

export function parseIgnoredValues(text) {
  return [...new Set(String(text || "").split(/[，,\s]+/).map(Number).filter(Number.isFinite))].slice(0, 128);
}

/** Return session-bound assets which can become a new map-document layer. */
export function availableMapAssets(assets, layers) {
  const layered = new Set((layers || []).map((layer) => layer.asset_id));
  return (assets || []).filter((asset) => (
    asset && ["GeoJSON", "GeoTIFF"].includes(asset.format) && !layered.has(asset.id)
  ));
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

function createVectorEditor(layer, save) {
  const render = vectorRenderDraft(layer.render);
  const details = document.createElement("details"); details.className = "vector-render-editor";
  const summary = document.createElement("summary"); summary.textContent = "矢量显示设置"; details.append(summary);
  const body = document.createElement("div"); body.className = "vector-render-body";

  const strokeLabel = document.createElement("label"); strokeLabel.textContent = "边界线颜色";
  const stroke = document.createElement("input"); stroke.type = "color"; stroke.value = render.stroke_color; stroke.setAttribute("aria-label", "边界线颜色"); strokeLabel.append(stroke);
  const fillLabel = document.createElement("label"); fillLabel.textContent = "内部填充颜色";
  const fill = document.createElement("input"); fill.type = "color"; fill.value = render.fill_color; fill.setAttribute("aria-label", "内部填充颜色"); fillLabel.append(fill);
  const opacityLabel = document.createElement("label"); opacityLabel.textContent = "内部填充透明度";
  const opacityRow = document.createElement("div"); opacityRow.className = "vector-fill-opacity";
  const opacity = document.createElement("input"); opacity.type = "range"; opacity.min = "0"; opacity.max = "1"; opacity.step = ".05"; opacity.value = String(render.fill_opacity); opacity.setAttribute("aria-label", "内部填充透明度");
  const opacityValue = document.createElement("output"); opacityValue.textContent = `${Math.round(render.fill_opacity * 100)}%`;
  opacity.oninput = () => { opacityValue.textContent = `${Math.round(Number(opacity.value) * 100)}%`; };
  opacityRow.append(opacity, opacityValue); opacityLabel.append(opacityRow);
  const hint = document.createElement("p"); hint.className = "fineprint"; hint.textContent = "边线用于点、线和面；填充颜色与透明度用于面状要素。";
  const apply = document.createElement("button"); apply.type = "button"; apply.className = "primary vector-save-style"; apply.textContent = "应用矢量样式";
  apply.onclick = () => save({ type: "patch", id: layer.id, patch: { render: {
    kind: "vector", stroke_color: stroke.value, fill_color: fill.value, fill_opacity: Number(opacity.value),
  } } });
  body.append(strokeLabel, fillLabel, opacityLabel, hint, apply); details.append(body);
  return details;
}

/**
 * Render evidence layers top-to-bottom. The caller persists their resulting
 * high-to-low z-index values, keeping component rendering state-free.
 */
export function renderLayerPanel(host, mapDocument, assets, save) {
  host.replaceChildren();
  const ordered = mapDocument.layers
    .map((layer, index) => ({ layer, index }))
    .sort((left, right) => right.layer.z_index - left.layer.z_index || left.index - right.index)
    .map(({ layer }) => layer);

  const toolbar = document.createElement("section"); toolbar.className = "layer-workspace-actions";
  const addGroup = document.createElement("div"); addGroup.className = "layer-picker layer-group-creator";
  const groupTitle = document.createElement("input"); groupTitle.type = "text"; groupTitle.maxLength = 160; groupTitle.placeholder = "新图层组名称"; groupTitle.setAttribute("aria-label", "新图层组名称");
  const groupButton = document.createElement("button"); groupButton.type = "button"; groupButton.className = "secondary"; groupButton.textContent = "新建图层组";
  const createGroup = () => {
    const title = groupTitle.value.trim();
    if (!title) { groupTitle.focus(); return; }
    save({ type: "group-add", title }); groupTitle.value = "";
  };
  groupButton.onclick = createGroup;
  groupTitle.addEventListener("keydown", (event) => { if (event.key === "Enter") { event.preventDefault(); createGroup(); } });
  addGroup.append(groupTitle, groupButton);

  const picker = document.createElement("div"); picker.className = "layer-picker layer-asset-picker";
  const assetSelect = document.createElement("select"); assetSelect.setAttribute("aria-label", "选择要添加到地图的会话资产");
  const candidates = availableMapAssets(assets, mapDocument.layers);
  assetSelect.add(new Option(candidates.length ? "选择会话资产" : "没有可添加的会话 GeoJSON / GeoTIFF 资产", ""));
  for (const asset of candidates) assetSelect.add(new Option(`${asset.name} · ${asset.format}`, asset.id));
  const groupSelect = document.createElement("select"); groupSelect.setAttribute("aria-label", "选择图层组"); groupSelect.add(new Option("未分组", ""));
  for (const group of mapDocument.groups) groupSelect.add(new Option(group.title, group.id));
  const add = document.createElement("button"); add.type = "button"; add.className = "primary"; add.textContent = "添加地图"; add.disabled = !candidates.length;
  add.onclick = () => {
    const asset = candidates.find((item) => item.id === assetSelect.value);
    if (!asset) { assetSelect.focus(); return; }
    save({ type: "add", asset_id: asset.id, title: asset.name, group_id: groupSelect.value || null });
  };
  picker.append(assetSelect, groupSelect, add); toolbar.append(addGroup, picker); host.append(toolbar);

  const groupLists = new Map();
  function makeGroupSection(group) {
    const groupId = group?.id || "";
    const members = ordered.filter((layer) => (layer.group_id || "") === groupId);
    const section = document.createElement("section"); section.className = "layer-group"; section.dataset.groupId = groupId;
    const header = document.createElement("button"); header.type = "button"; header.className = "layer-group-header";
    const name = document.createElement("strong"); name.textContent = group?.title || "未分组";
    const count = document.createElement("span"); count.textContent = `${members.length} 图层`;
    header.append(name, count);
    const list = document.createElement("div"); list.className = "layer-group-list";
    const expanded = group?.expanded !== false;
    header.setAttribute("aria-expanded", String(expanded));
    list.hidden = !expanded; section.classList.toggle("collapsed", !expanded);
    header.onclick = () => {
      const next = list.hidden;
      list.hidden = !next; section.classList.toggle("collapsed", !next); header.setAttribute("aria-expanded", String(next));
      // The ungrouped bucket is a presentation affordance rather than a
      // persisted map-document group. Named groups retain their state across
      // map refreshes and session switches.
      if (group) save({ type: "group-patch", id: group.id, patch: { expanded: next } });
    };
    section.append(header, list); host.append(section); groupLists.set(groupId, list);
  }
  makeGroupSection(null);
  for (const group of [...mapDocument.groups].sort((left, right) => left.z_index - right.z_index)) makeGroupSection(group);

  if (!ordered.length) {
    const empty = document.createElement("p"); empty.className = "empty layer-empty";
    empty.textContent = assets?.length ? "从上方选择已绑定到当前会话的资产，添加到地图。" : "当前会话还没有可显示的 GeoJSON 或 GeoTIFF 资产。";
    groupLists.get("")?.append(empty);
  }

  for (const layer of ordered) {
    const card = document.createElement("article");
    card.className = "layer-card";
    card.dataset.layerId = layer.id;

    const header = document.createElement("div"); header.className = "layer-card-header";
    const handle = document.createElement("span"); handle.className = "layer-drag-handle"; handle.title = "拖动以调整渲染顺序"; handle.setAttribute("aria-label", "拖动以调整渲染顺序"); handle.textContent = "⠿";
    const visible = document.createElement("input"); visible.type = "checkbox"; visible.checked = layer.visible; visible.className = "layer-visible"; visible.setAttribute("aria-label", `显示图层：${layer.title}`);
    const heading = document.createElement("div"); heading.className = "layer-heading";
    const meta = document.createElement("span"); meta.className = "layer-meta"; meta.textContent = sourceLabel(layer);
    const title = document.createElement("strong"); title.textContent = layer.title;
    heading.append(meta, title);
    const actions = document.createElement("div"); actions.className = "layer-card-actions";
    const zoom = document.createElement("button"); zoom.type = "button"; zoom.className = "layer-zoom"; zoom.textContent = "缩放至"; zoom.title = `缩放地图至 ${layer.title}`;
    zoom.onclick = () => save({ type: "zoom-to", id: layer.id });
    const rename = document.createElement("button"); rename.type = "button"; rename.className = "layer-rename"; rename.textContent = "重命名"; rename.title = `修改图层显示名：${layer.title}`;
    rename.onclick = () => {
      const input = document.createElement("input"); input.type = "text"; input.className = "layer-title-input"; input.maxLength = 160; input.value = layer.title; input.setAttribute("aria-label", "图层显示名");
      let finished = false;
      const close = (commit) => {
        if (finished) return; finished = true;
        const next = input.value.trim();
        if (commit && next && next !== layer.title) save({ type: "patch", id: layer.id, patch: { title: next } });
        else input.replaceWith(title);
      };
      input.addEventListener("keydown", (event) => {
        if (event.key === "Enter") { event.preventDefault(); close(true); }
        if (event.key === "Escape") { event.preventDefault(); close(false); }
      });
      input.addEventListener("blur", () => close(true));
      title.replaceWith(input); input.focus(); input.select();
    };
    const remove = document.createElement("button"); remove.type = "button"; remove.className = "layer-remove";
    remove.textContent = "移除"; remove.title = `从当前会话地图移除 ${layer.title}`;
    remove.setAttribute("aria-label", `从当前会话地图移除 ${layer.title}`);
    remove.onclick = () => save({ type: "remove", id: layer.id });
    actions.append(zoom, rename, remove);
    header.append(handle, visible, heading, actions);

    const controls = document.createElement("div"); controls.className = "layer-card-controls";
    const opacityLabel = document.createElement("span"); opacityLabel.textContent = "不透明度";
    const opacityValue = document.createElement("output"); opacityValue.textContent = `${Math.round(layer.opacity * 100)}%`;
    const opacity = document.createElement("input"); opacity.type = "range"; opacity.min = "0"; opacity.max = "1"; opacity.step = ".05"; opacity.value = String(layer.opacity); opacity.setAttribute("aria-label", `${layer.title} 不透明度`);
    opacity.oninput = () => { opacityValue.textContent = `${Math.round(Number(opacity.value) * 100)}%`; };
    opacity.onchange = () => save({ type: "patch", id: layer.id, patch: { opacity: Number(opacity.value) } });
    visible.onchange = () => save({ type: "patch", id: layer.id, patch: { visible: visible.checked } });
    controls.append(opacityLabel, opacityValue, opacity);
    card.append(header, controls);
    if (layer.source?.kind === "vector") card.append(createVectorEditor(layer, save));
    else if (layer.render?.kind === "raster") card.append(createRasterEditor(layer, save));

    function clearDragState() { host.querySelectorAll(".layer-card, .layer-group").forEach((item) => item.classList.remove("dragging", "drop-target")); }
    handle.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      event.preventDefault();
      const pointerId = event.pointerId, startX = event.clientX, startY = event.clientY; let moved = false; let targetCard = null; let targetGroup = null;
      card.classList.add("dragging"); handle.setPointerCapture?.(pointerId);
      const targetAt = (clientX, clientY) => {
        const target = document.elementFromPoint(clientX, clientY);
        targetCard = target?.closest?.(".layer-card") || null;
        targetGroup = target?.closest?.(".layer-group") || null;
        if (targetCard?.dataset.layerId === layer.id) targetCard = null;
        clearDragState(); card.classList.add("dragging");
        if (targetCard) targetCard.classList.add("drop-target");
        else if (targetGroup) targetGroup.classList.add("drop-target");
      };
      const finish = (eventUp) => {
        document.removeEventListener("pointermove", move);
        document.removeEventListener("pointerup", finish);
        document.removeEventListener("pointercancel", cancel);
        handle.releasePointerCapture?.(pointerId); clearDragState();
        if (!moved) { clearDragState(); return; }
        targetAt(eventUp.clientX, eventUp.clientY);
        const groupId = targetGroup ? (targetGroup.dataset.groupId || null) : layer.group_id;
        const ids = ordered.map((item) => item.id);
        let next = ids;
        if (targetCard) next = reorderLayerIds(ids, layer.id, targetCard.dataset.layerId);
        else if (targetGroup) {
          const without = ids.filter((id) => id !== layer.id);
          const members = ordered.filter((item) => item.id !== layer.id && (item.group_id || "") === (groupId || "")).map((item) => item.id);
          const last = members.at(-1); const position = last ? without.indexOf(last) + 1 : without.length;
          next = [...without.slice(0, position), layer.id, ...without.slice(position)];
        }
        if (groupId !== layer.group_id || next.join("|") !== ids.join("|")) save({ type: "move", id: layer.id, group_id: groupId, ids: next });
      };
      const move = (eventMove) => {
        moved ||= Math.abs(eventMove.clientX - startX) + Math.abs(eventMove.clientY - startY) > 4;
        if (moved) targetAt(eventMove.clientX, eventMove.clientY);
      };
      const cancel = () => { document.removeEventListener("pointermove", move); document.removeEventListener("pointerup", finish); document.removeEventListener("pointercancel", cancel); clearDragState(); };
      document.addEventListener("pointermove", move);
      document.addEventListener("pointerup", finish);
      document.addEventListener("pointercancel", cancel);
    });
    (groupLists.get(layer.group_id || "") || groupLists.get(""))?.append(card);
  }
}
