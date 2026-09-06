import { api, presentation } from "./api.js";
import { createMap, syncLayers } from "./map.js";
import { createWorkspaceState } from "./state.js";
import { createSessionRequestScope } from "./session-request-scope.js";
import { byId, setStatus } from "./dom.js";
import { renderActions } from "./components/workspace-ui.js";
import { renderLayerPanel } from "./components/layer-panel.js";
import { createSessions } from "./controllers/session-controller.js";
import { createConnectors } from "./controllers/connector-controller.js";
import { createContext } from "./controllers/context-controller.js";
import { createAgent } from "./controllers/agent-controller.js";
import { createInvestigationEventProjector } from "./conversation/investigation-event-projector.js";
import { mountInvestigationChat } from "./components/investigation-chat.js";
import { createDockLayout } from "./components/dock-layout.js";
import { installMapEdgeResizers } from "./components/map-edge-resizers.js";
import { installBottomDockResizer } from "./components/bottom-dock-resizer.js";
import { createBasemapMap } from "./basemap-map.js";
import { mountBasemapPanel } from "./components/basemap-panel.js";
import { createBasemaps } from "./controllers/basemap-controller.js";
import { mountFileDropTarget } from "./components/file-drop-target.js";
import { mountDataImportPanel } from "./components/data-import/panel.js";
import { createImports } from "./controllers/import-controller.js";
import { createNativeImportBridge } from "./native-import-bridge.js";
import { createTraceView } from "./components/trace-view.js";

// The old panel-local selector is retired; the persistent shell selector is canonical.
document.querySelector(".investigation-session")?.remove();
const state = createWorkspaceState(), requestScope = createSessionRequestScope(state), map = createMap("map");
installMapEdgeResizers(document.querySelector(".workspace"), document.querySelector(".map-stage"), () => requestAnimationFrame(() => map.updateSize()));
let sources = {};
async function refreshMap() {
  const request = requestScope.capture("map"), sessionId = request.sessionId;
  if (!sessionId) { setStatus("请选择 Angelus 会话后加载会话图层。"); return null; }
  const doc = await api(presentation(sessionId));
  if (!requestScope.isCurrent(request)) return null;
  const applied = await syncLayers(map, doc.effective, sessionId, { isCurrent: () => requestScope.isCurrent(request) });
  if (!applied || !requestScope.isCurrent(request)) return null;
  renderLayerPanel(document.querySelector('[data-panel="layers"] .layer-list'), doc.effective, async (change) => {
    const update = requestScope.capture("map-update");
    if (!requestScope.isCurrent(update)) return null;
    const editable = (layer) => ({ ...layer, source: {} });
    let layers;
    let removedLayerIds = doc.user_overrides.removed_layer_ids || [];
    if (change.type === "patch") {
      const base = doc.effective.layers.find((layer) => layer.id === change.id);
      if (!base) return null;
      layers = doc.user_overrides.layers.filter((layer) => layer.id !== change.id);
      layers.push(editable({ ...base, ...change.patch }));
    } else if (change.type === "reorder") {
      const currentIds = doc.effective.layers.map((layer) => layer.id);
      if (change.ids.length !== currentIds.length || change.ids.some((id) => !currentIds.includes(id))) return null;
      const zIndex = new Map(change.ids.map((id, index) => [id, change.ids.length - index]));
      const previous = new Map(doc.user_overrides.layers.map((layer) => [layer.id, layer]));
      layers = doc.effective.layers.map((base) => editable({ ...base, ...(previous.get(base.id) || {}), z_index: zIndex.get(base.id) }));
    } else if (change.type === "remove") {
      const base = doc.effective.layers.find((layer) => layer.id === change.id);
      if (!base) return null;
      if (!globalThis.confirm(`从当前会话地图移除“${base.title}”？原始导入资产不会删除。`)) return null;
      layers = doc.user_overrides.layers.filter((layer) => layer.id !== change.id);
      removedLayerIds = [...new Set([...removedLayerIds, change.id])];
    } else return null;
    await api(presentation(sessionId), { method: "PUT", body: JSON.stringify({ ...doc.user_overrides, layers, removed_layer_ids: removedLayerIds }) });
    if (!requestScope.isCurrent(update)) return null;
    return refreshMap();
  });
  return doc;
}
async function boot() {
  const ui = await api("/api/geoint/ui"); sources = ui.sources; byId("workspace-title").textContent = ui.title;
  const basemapHost = document.createElement("section"); basemapHost.className = "tab-panel"; basemapHost.dataset.panel = "basemap";
  document.querySelector(".right-panel").append(basemapHost);
  let basemaps;
  const basemapView = mountBasemapPanel(basemapHost, Object.fromEntries(["select", "add", "update", "remove", "setKey", "locate"].map((name) => [name, (...args) => basemaps[name](...args)])));
  const basemapMap = createBasemapMap(map, (message) => { basemapView.status(message); setStatus(message); });
  basemapMap.select({ kind: "osm" });
  const quickBasemap = byId("basemap-select");
  basemaps = createBasemaps({ view: basemapView, map: basemapMap, onSnapshot(value) {
    if (!quickBasemap) return;
    quickBasemap.replaceChildren(...value.sources.map((s) => { const option = new Option(s.name, s.id); option.disabled = !s.enabled; return option; }));
    quickBasemap.value = value.selected_id;
  } });
  if (quickBasemap) {
    quickBasemap.replaceChildren(new Option("OpenStreetMap", "osm"));
    quickBasemap.onchange = async () => { quickBasemap.disabled = true; try { await basemaps.select(quickBasemap.value); } catch (error) { quickBasemap.value = basemaps.selectedId(); basemapView.status(error.message); setStatus(error.message); } finally { quickBasemap.disabled = false; } };
  }
  await basemaps.load().catch((error) => basemapView.status(`底图配置加载失败：${error.message}`));
  const projector = createInvestigationEventProjector(), trace = createTraceView(byId("trace-log"));
  const sessions = createSessions({ state, sources, requestScope }), connectors = createConnectors({ state, sources }), context = createContext({ state, requestScope }), agent = createAgent({ state, projector, requestScope, trace });
  let imports;
  const importView = mountDataImportPanel(byId("data-import-panel"), {
    acceptFiles: (files) => imports.acceptFiles(files).catch((error) => { importView.status(error.message); setStatus(error.message); }),
    commit: (snapshot) => imports.commit(snapshot).catch((error) => { importView.status(error.message); setStatus(error.message); }),
    selectSession: () => byId("session-select").focus(),
  });
  imports = createImports({ state, requestScope, view: importView, onComplete: async () => { await refreshMap(); setStatus("数据已登记并加入当前会话地图"); } });
  const nativeImports = createNativeImportBridge((event) => {
    if (event?.type === "inspection" && event.snapshot?.session_id === state.sessionId()) { importView.render(event.snapshot); setStatus("桌面文件预检完成，请确认加入地图。"); }
    else if (event?.type === "progress") { importView.status(event.message || "正在从桌面导入文件…"); setStatus(event.message || "正在从桌面导入文件…"); }
    else if (event?.type === "error") { importView.status(event.message || "桌面导入失败"); setStatus(event.message || "桌面导入失败"); }
  });
  mountFileDropTarget(document.querySelector(".map-stage"), (files) => {
    if (nativeImports.available) {
      const message = "正在由桌面应用读取拖入文件…";
      importView.status(message); setStatus(message);
      return;
    }
    imports.acceptFiles(files).catch((error) => { importView.status(error.message); setStatus(error.message); });
  }, () => {
    const message = nativeImports.available ? "正在由桌面应用读取拖入文件…" : "未获得可上传的文件；请使用“选择文件”。";
    importView.status(message); setStatus(message);
  });
  mountInvestigationChat({ panel: document.querySelector('[data-panel="agent"]'), projector, onSend: (message) => agent.run(message), onStop: () => agent.stop() });
  async function restoreSelectedSession() {
    const request = requestScope.capture("session-restore");
    importView.setSession(request.sessionId);
    await nativeImports.setSession(request.sessionId).catch(() => {}); if (!requestScope.isCurrent(request)) return null;
    await sessions.loadProfile(); if (!requestScope.isCurrent(request)) return null;
    await context.loadAgents(); if (!requestScope.isCurrent(request)) return null;
    const contextSnapshot = await context.refresh(); if (!requestScope.isCurrent(request)) return null;
    await agent.reconcile(contextSnapshot); if (!requestScope.isCurrent(request)) return null;
    await imports.load(); if (!requestScope.isCurrent(request)) return null;
    return refreshMap();
  }
  async function refreshAll() { const health = await api(sources.health); byId("db-pill").textContent = health.connected ? "POSTGIS · CONNECTED" : "DATA · LOCAL"; await sessions.refresh(); importView.setSession(state.sessionId()); await connectors.refresh(); if (state.sessionId()) await restoreSelectedSession(); }
  const actions = { "workspace.refresh": refreshAll, "session.create": async () => { const created = await sessions.create(); await restoreSelectedSession(); return { status_message: `已创建工作空间“${created.name}”，可直接导入数据或发起调查。` }; }, "session.delete": async () => { await sessions.remove(); importView.setSession(null); await nativeImports.setSession(null).catch(() => {}); }, "session.profile.load": sessions.loadProfile, "session.profile.save": sessions.saveProfile, "connector.refresh": connectors.refresh, "connector.create": connectors.createAndBind, "connector.bind": () => connectors.bind(byId("connector-select").value), "context.refresh": context.refresh, "context.export": context.export, "context.import": context.import, "agent.run": agent.run, "agent.stop": agent.stop, "trace.clear": () => trace.clear() };
  const dock = createDockLayout({ workspace: document.querySelector(".workspace"), leftRail: document.querySelector(".left-panel"), rightRail: document.querySelector(".right-panel"), onLayoutChange: () => requestAnimationFrame(() => map.updateSize()), onActivePanelsChange: (activePanels) => trace.setActive(activePanels.has("trace")) });
  dock.mount(ui.tabs.map((tab) => ({ id: tab.id, title: tab.label, element: document.querySelector(`[data-panel="${tab.id}"]`) })).filter((tab) => tab.element));
  installBottomDockResizer(document.querySelector(".workspace"), document.querySelector(".bottom-dock"), () => requestAnimationFrame(() => map.updateSize()));
  const reset = document.createElement("button"); reset.type = "button"; reset.className = "dock-reset"; reset.textContent = "恢复默认面板"; reset.onclick = () => dock.reset(); document.querySelector(".workspace-brief")?.append(reset);
  renderActions(ui.actions, async (id) => { const action = actions[id]; if (!action) throw new Error(`控件尚未迁移：${id}`); const result = await action(); setStatus(result?.status_message || "操作已完成"); });
  byId("session-select").onchange = async () => { requestScope.select(byId("session-select").value); await restoreSelectedSession(); };
  byId("context-agent").onchange = () => context.refresh().catch((error) => setStatus(error.message));
  await refreshAll(); setStatus("GEOINT 工作区已就绪");
}
boot().catch((error) => setStatus(`启动失败 · ${error.message}`));
