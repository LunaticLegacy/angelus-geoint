function text(tag, value, className = "") { const node = document.createElement(tag); node.textContent = value; if (className) node.className = className; return node; }

/** Compact import control: file lifecycle stays in the import controller. */
export function mountDataImportPanel(host, actions) {
  const chooser = document.createElement("input"); chooser.type = "file"; chooser.multiple = true; chooser.accept = ".geojson,.json,.tif,.tiff,.shp,.shx,.dbf,.prj,.cpg,application/geo+json,application/json,image/tiff"; chooser.hidden = true;
  const choose = document.createElement("button"); choose.type = "button"; choose.className = "secondary"; choose.textContent = "导入文件"; choose.title = "导入 GeoJSON、GeoTIFF/COG 或 Shapefile"; choose.onclick = async () => { if (await actions.chooseNativeFiles?.()) return; chooser.click(); };
  chooser.onchange = () => { const files = [...chooser.files]; chooser.value = ""; if (files.length) actions.acceptFiles(files); };
  host.replaceChildren(choose, chooser);
  const announce = (value) => actions.status?.(value);
  function setSession(sessionId) {
    const ready = Boolean(sessionId);
    choose.disabled = !ready;
    choose.title = ready ? "导入 GeoJSON、GeoTIFF/COG 或 Shapefile" : "请先在顶部选择会话";
  }
  function render(snapshot) {
    if (!snapshot) return;
    announce(({ receiving: "正在接收文件…", awaiting_confirmation: "文件预检完成，正在登记并添加到地图…", completed: "文件已登记并添加到当前会话地图。" })[snapshot.status] || `导入状态：${snapshot.status}`);
  }
  return { render, setSession, status: announce };
}
