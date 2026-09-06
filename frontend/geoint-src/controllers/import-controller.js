import { createImportClient } from "../import-client.js";

const SHAPEFILE_REQUIRED_SUFFIXES = [".shp", ".shx", ".dbf"];

/**
 * Browser FileLists cannot inspect unselected sibling paths.  Fail locally
 * with an actionable bundle error instead of starting an upload that the
 * server must later reject.  The desktop native bridge performs sibling
 * discovery before this controller is involved.
 */
export function validateBrowserImportFiles(files) {
  const groups = new Map();
  files.forEach((file) => {
    const name = String(file?.name || ""), dot = name.lastIndexOf(".");
    if (dot < 1) return;
    const suffix = name.slice(dot).toLowerCase();
    if (!SHAPEFILE_REQUIRED_SUFFIXES.includes(suffix) && ![".prj", ".cpg"].includes(suffix)) return;
    const stem = name.slice(0, dot).toLocaleLowerCase();
    const group = groups.get(stem) || { title: name.slice(0, dot), suffixes: new Set() };
    group.suffixes.add(suffix); groups.set(stem, group);
  });
  for (const group of groups.values()) {
    const missing = SHAPEFILE_REQUIRED_SUFFIXES.filter((suffix) => !group.suffixes.has(suffix));
    if (missing.length) throw new Error(`Shapefile“${group.title}”缺少 ${missing.join("、")}。浏览器无法扫描同目录，请同时选择同名 .shp、.shx、.dbf；桌面版只选择 .shp 即会自动补齐。`);
  }
}

/** Retains File objects only for an active upload; server state is the resume source. */
export function createImports({ state, requestScope, view, onComplete = () => {} }) {
  const client = createImportClient(); let abort = null;
  async function acceptFiles(files) {
    const token = requestScope.capture("data-import"), sessionId = token.sessionId;
    if (!sessionId) throw new Error("请先选择会话，再导入数据");
    validateBrowserImportFiles(files);
    const declarations = files.map((file) => ({ name: file.name, size_bytes: file.size }));
    const clientRequestId = globalThis.crypto?.randomUUID?.() || `${Date.now()}-${Math.random()}`;
    let current = await client.create(sessionId, declarations, clientRequestId); if (!requestScope.isCurrent(token)) return null;
    view.render(current); abort = new AbortController();
    try {
      for (let index = 0; index < files.length; index += 1) {
        const record = current.files[index], file = files[index];
        if (record.status === "uploaded") continue;
        view.status(`正在上传 ${file.name}…`);
        current = await client.upload(sessionId, current.import_id, file, record.file_id, { signal: abort.signal, onProgress: (fraction) => { if (requestScope.isCurrent(token)) view.status(`正在上传 ${file.name} · ${Math.round(fraction * 100)}%`); } });
        if (!requestScope.isCurrent(token)) return null;
      }
      const uploaded = await client.inspect(sessionId, current.import_id, current.revision);
      if (!requestScope.isCurrent(token)) return null;
      view.render(uploaded);
      return uploaded.status === "awaiting_confirmation" ? commit(uploaded) : uploaded;
    } finally { abort = null; }
  }
  async function commit(snapshot) {
    const token = requestScope.capture("data-import"), sessionId = token.sessionId;
    if (!sessionId || snapshot.session_id !== sessionId) return null;
    const datasets = (snapshot.candidates || []).filter((item) => item.renderability?.supported).map((item) => ({ dataset_id: item.dataset_id, title: item.name }));
    const completed = await client.commit(sessionId, snapshot.import_id, snapshot.revision, datasets);
    if (!requestScope.isCurrent(token)) return null; view.render(completed); await onComplete(); return completed;
  }
  async function load() {
    const token = requestScope.capture("data-import-load"), sessionId = token.sessionId;
    if (!sessionId) { view.render(null); return null; }
    const snapshot = await client.list(sessionId);
    if (!requestScope.isCurrent(token)) return null;
    const latest = snapshot.imports?.[0] || null; view.render(latest);
    return latest?.status === "awaiting_confirmation" ? commit(latest) : latest;
  }
  return { acceptFiles, commit, load, cancel() { abort?.abort(); } };
}
