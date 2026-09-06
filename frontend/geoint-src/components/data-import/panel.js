function text(tag, value, className = "") { const node = document.createElement(tag); node.textContent = value; if (className) node.className = className; return node; }

/** Stateless view: all workflow actions are injected by the controller/main. */
export function mountDataImportPanel(host, actions) {
  const title = document.createElement("div"); title.className = "data-import-title";
  title.append(text("span", "DATA IMPORT", "eyebrow"), text("h4", "拖入数据"));
  const hint = text("p", "支持 GeoJSON、GeoTIFF/COG 和 Shapefile。Shapefile 请同时选择同名 .shp、.shx、.dbf（.prj/.cpg 可选）；文件会复制到当前会话的受控工作区。", "fineprint");
  const chooser = document.createElement("input"); chooser.type = "file"; chooser.multiple = true; chooser.accept = ".geojson,.json,.tif,.tiff,.shp,.shx,.dbf,.prj,.cpg,application/geo+json,application/json,image/tiff"; chooser.hidden = true;
  const choose = document.createElement("button"); choose.type = "button"; choose.className = "secondary"; choose.textContent = "选择文件"; choose.onclick = () => chooser.click();
  chooser.onchange = () => { const files = [...chooser.files]; chooser.value = ""; if (files.length) actions.acceptFiles(files); };
  const status = text("p", "可直接把文件拖到地图中央，或在此选择文件。", "data-import-status");
  const list = document.createElement("div"); list.className = "data-import-list";
  const selectSession = document.createElement("button"); selectSession.type = "button"; selectSession.className = "secondary data-import-session-action"; selectSession.textContent = "选择会话"; selectSession.onclick = () => actions.selectSession?.();
  host.replaceChildren(title, hint, choose, chooser, selectSession, status, list);
  function setSession(sessionId) {
    const ready = Boolean(sessionId);
    host.classList.toggle("data-import-needs-session", !ready);
    choose.disabled = !ready;
    selectSession.hidden = ready;
    if (!ready) {
      list.replaceChildren();
      status.textContent = "请先在右上角选择会话；若没有会话，请在下方“会话”页创建。数据必须归属一个会话。";
    } else {
      status.textContent = "可直接把文件拖到地图中央，或在此选择文件。";
    }
  }
  function render(snapshot) {
    list.replaceChildren();
    if (!snapshot) return;
    status.textContent = ({ receiving: "正在接收文件…", awaiting_confirmation: "预检完成，等待确认上图。", completed: "已登记资产并加入地图。" })[snapshot.status] || `导入状态：${snapshot.status}`;
    for (const file of snapshot.files || []) list.append(text("div", `${file.name} · ${file.status === "uploaded" ? "已上传" : "等待上传"} · ${Math.round((file.received_bytes || 0) / 1024)} KiB`, "data-import-file"));
    if (snapshot.status === "awaiting_confirmation") {
      const candidates = text("div", `${(snapshot.candidates || []).map((item) => `${item.name}（${item.format}）`).join("；")}`, "data-import-candidates");
      const commit = document.createElement("button"); commit.type = "button"; commit.className = "primary"; commit.textContent = "确认并加入地图"; commit.onclick = () => actions.commit(snapshot);
      list.append(candidates, commit);
    }
  }
  return { render, setSession, status: (value) => { status.textContent = value; } };
}
