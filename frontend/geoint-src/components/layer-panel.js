export function renderLayerPanel(host, mapDocument, save) {
  host.replaceChildren();
  const groups = new Map(mapDocument.groups.map((group) => [group.id, group]));
  for (const layer of [...mapDocument.layers].sort((a, b) => a.z_index - b.z_index)) {
    const row = document.createElement("label"); row.className = "layer-control";
    const visible = document.createElement("input"); visible.type = "checkbox"; visible.checked = layer.visible;
    const title = document.createElement("span"); title.textContent = `${groups.get(layer.group_id)?.title || "未分组"} · ${layer.title}`;
    const opacity = document.createElement("input"); opacity.type = "range"; opacity.min = "0"; opacity.max = "1"; opacity.step = ".05"; opacity.value = String(layer.opacity);
    const changed = () => save(layer.id, { visible: visible.checked, opacity: Number(opacity.value) });
    visible.onchange = changed; opacity.onchange = changed; row.append(visible, title, opacity); host.append(row);
  }
}
