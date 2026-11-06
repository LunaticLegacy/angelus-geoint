import { api, presentation } from "./api.js";
import { createMap, previewVectorLayerStyle, syncLayers, zoomToMapLayer } from "./map.js";
import { setEvidenceLayerVisible, syncEvidenceLayer } from "./evidence-map.js";
import { createWorkspaceState } from "./state.js";
import { createSessionRequestScope } from "./session-request-scope.js";
import { byId, setStatus } from "./dom.js";
import { renderActions, renderConnectors } from "./components/workspace-ui.js";
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
import { mountPlanPanel } from "./components/task-plan-panel.js";
import { mountNotesPanel } from "./components/notes-panel.js";
import { createTraceView } from "./components/trace-view.js";
import { renderEvidencePanel } from "./components/evidence-panel.js";

const state = createWorkspaceState(), requestScope = createSessionRequestScope(state), map = createMap("map");
installMapEdgeResizers(document.querySelector(".workspace"), document.querySelector(".map-stage"), () => requestAnimationFrame(() => map.updateSize()));
let sources = {};
async function refreshMap() {
  const request = requestScope.capture("map"), sessionId = request.sessionId;
  if (!sessionId) { setStatus("请选择 Angelus 会话后加载会话图层。"); return null; }
  const [doc, catalog] = await Promise.all([
    api(presentation(sessionId)),
    api(`/api/geoint/catalog/assets?session_id=${encodeURIComponent(sessionId)}`),
  ]);
  if (!requestScope.isCurrent(request)) return null;
  const applied = await syncLayers(map, doc.effective, sessionId, { isCurrent: () => requestScope.isCurrent(request) });
  if (!applied || !requestScope.isCurrent(request)) return null;
  renderLayerPanel(document.querySelector('[data-panel="layers"] .layer-list'), doc.effective, catalog.assets || [], async (change) => {
    if (change.type === "zoom-to") {
      const layer = doc.effective.layers.find((item) => item.id === change.id);
      const zoomed = await zoomToMapLayer(map, change.id);
      setStatus(zoomed ? `已缩放至图层“${layer?.title || ""}”` : "该图层尚未获得可用空间范围。");
      return zoomed;
    }
    if (change.type === "preview-vector-style") return previewVectorLayerStyle(map, change.id, change.render);
    const update = requestScope.capture("map-update");
    if (!requestScope.isCurrent(update)) return null;
    const editable = (layer) => ({ ...layer, source: {} });
    let layers;
    let groups = doc.user_overrides.groups || [];
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
    } else if (change.type === "move") {
      const base = doc.effective.layers.find((layer) => layer.id === change.id);
      const currentIds = doc.effective.layers.map((layer) => layer.id);
      const groupId = change.group_id || null;
      if (!base || !Array.isArray(change.ids) || change.ids.length !== currentIds.length || change.ids.some((id) => !currentIds.includes(id))) return null;
      if (groupId && !doc.effective.groups.some((group) => group.id === groupId)) return null;
      const zIndex = new Map(change.ids.map((id, index) => [id, change.ids.length - index]));
      const previous = new Map(doc.user_overrides.layers.map((layer) => [layer.id, layer]));
      layers = doc.effective.layers.map((item) => editable({
        ...item, ...(previous.get(item.id) || {}),
        group_id: item.id === base.id ? groupId : item.group_id,
        z_index: zIndex.get(item.id),
      }));
    } else if (change.type === "remove") {
      const base = doc.effective.layers.find((layer) => layer.id === change.id);
      if (!base) return null;
      if (!globalThis.confirm(`从当前会话地图移除“${base.title}”？原始导入资产不会删除。`)) return null;
      layers = doc.user_overrides.layers.filter((layer) => layer.id !== change.id);
      removedLayerIds = [...new Set([...removedLayerIds, change.id])];
    } else if (change.type === "group-add") {
      const title = String(change.title || "").trim();
      if (!title || title.length > 160) return null;
      const groupId = `group_${globalThis.crypto?.randomUUID?.().replaceAll("-", "") || Date.now()}`;
      groups = [...doc.effective.groups, { id: groupId, title, visible: true, expanded: true, z_index: doc.effective.groups.length }];
      layers = doc.user_overrides.layers;
    } else if (change.type === "group-patch") {
      const base = doc.effective.groups.find((group) => group.id === change.id);
      if (!base || !change.patch || typeof change.patch !== "object") return null;
      groups = doc.effective.groups.map((group) => group.id === base.id ? { ...group, ...change.patch } : group);
      layers = doc.user_overrides.layers;
    } else if (change.type === "add") {
      const asset = (catalog.assets || []).find((item) => item.id === change.asset_id && ["GeoJSON", "GeoTIFF"].includes(item.format));
      if (!asset || doc.effective.layers.some((layer) => layer.asset_id === asset.id)) return null;
      const groupId = change.group_id || null;
      if (groupId && !doc.effective.groups.some((group) => group.id === groupId)) return null;
      const maxZ = Math.max(0, ...doc.effective.layers.map((layer) => Number(layer.z_index) || 0));
      const title = String(change.title || asset.name).trim().slice(0, 160) || asset.name;
      layers = [...doc.user_overrides.layers, {
        id: `layer_${globalThis.crypto?.randomUUID?.().replaceAll("-", "") || Date.now()}`,
        asset_id: asset.id, title, group_id: groupId, source: {}, visible: true, opacity: 1,
        z_index: maxZ + 1, min_zoom: null, max_zoom: null, render: {}, attribute_view: {},
      }];
    } else return null;
    await api(presentation(sessionId), { method: "PUT", body: JSON.stringify({ ...doc.user_overrides, groups, layers, removed_layer_ids: removedLayerIds }) });
    if (!requestScope.isCurrent(update)) return null;
    return refreshMap();
  });
  return doc;
}
async function refreshEvidence() {
  const request = requestScope.capture("evidence"), sessionId = request.sessionId;
  if (!sessionId) return null;
  const [snapshot, catalog, geojson] = await Promise.all([
    api(`/api/geoint/sessions/${encodeURIComponent(sessionId)}/evidence`),
    api(`/api/geoint/catalog/assets?session_id=${encodeURIComponent(sessionId)}`),
    api(`/api/geoint/sessions/${encodeURIComponent(sessionId)}/evidence/geojson`),
  ]);
  if (!requestScope.isCurrent(request)) return null;
  renderEvidencePanel(document.querySelector('[data-panel="evidence"]'), snapshot, catalog.assets || []);
  syncEvidenceLayer(map, geojson, { visible: byId("evidence-map-visible")?.checked === true });
  return snapshot;
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
  const evidenceMapToggle = byId("evidence-map-visible");
  if (evidenceMapToggle) evidenceMapToggle.onchange = () => {
    const shown = setEvidenceLayerVisible(map, evidenceMapToggle.checked);
    setStatus(shown ? (evidenceMapToggle.checked ? "已在地图显示证据范围" : "已隐藏地图证据范围") : "当前会话没有可显示的证据范围");
  };
  const sessions = createSessions({ state, sources, requestScope }), connectors = createConnectors({ state, sources }), context = createContext({ state, requestScope }), agent = createAgent({ state, projector, requestScope, trace, onMapChanged: () => refreshMap(), onEvidenceChanged: () => refreshEvidence() });
  let imports, nativeImports;
  const importView = mountDataImportPanel(byId("data-import-panel"), {
    acceptFiles: (files) => imports.acceptFiles(files).catch((error) => { importView.status(error.message); setStatus(error.message); }),
    chooseNativeFiles: async () => nativeImports?.chooseFiles(),
    status: (message) => setStatus(message),
  });
  imports = createImports({ state, requestScope, view: importView, onComplete: async () => { await refreshMap(); setStatus("数据已登记并加入当前会话地图"); } });
  nativeImports = createNativeImportBridge((event) => {
    if (event?.type === "inspection" && event.snapshot?.session_id === state.sessionId()) {
      importView.render(event.snapshot);
      imports.commit(event.snapshot).catch((error) => { importView.status(error.message); setStatus(error.message); });
    }
    else if (event?.type === "progress") { importView.status(event.message || "正在从桌面导入文件…"); setStatus(event.message || "正在从桌面导入文件…"); }
    else if (event?.type === "error") { importView.status(event.message || "桌面导入失败"); setStatus(event.message || "桌面导入失败"); }
  });
  // Both panels are backed by documented HTTP surfaces (plan: GET/PUT/PATCH,
  // notes: GET/POST/PATCH/DELETE); they render their own failures, so a missing
  // session or a rejected write can never be mistaken for a working control.
  const planPanel = mountPlanPanel(document.querySelector('[data-panel="plan"]'), { onStatus: setStatus });
  const notesPanel = mountNotesPanel(document.querySelector('[data-panel="notes"]'), { onStatus: setStatus });
  const openWorkspace = byId("open-session-workspace");
  const syncWorkspaceAction = () => {
    if (!openWorkspace) return;
    openWorkspace.disabled = !nativeImports.available || !state.sessionId();
    openWorkspace.title = nativeImports.available ? "用系统默认文件管理器打开当前会话工作空间" : "仅桌面版支持用系统文件管理器打开工作空间";
  };
  if (openWorkspace) openWorkspace.onclick = async () => {
    try { await nativeImports.openWorkspace(); setStatus("已在系统文件管理器中打开当前工作空间"); }
    catch (error) { setStatus(`打开工作空间失败：${error.message}`); }
  };
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
  const investigationChat = mountInvestigationChat({ panel: document.querySelector('[data-panel="agent"]'), projector, onSend: (message) => agent.run(message), onSteer: (message) => agent.steer(message), onStop: () => agent.stop(), onLoadOlder: () => agent.loadOlderHistory() });
  async function restoreSelectedSession() {
    const request = requestScope.capture("session-restore");
    importView.setSession(request.sessionId);
    syncWorkspaceAction();
    await nativeImports.setSession(request.sessionId).catch(() => {}); if (!requestScope.isCurrent(request)) return null;
    await sessions.loadProfile(); if (!requestScope.isCurrent(request)) return null;
    renderConnectors(state.connectors(), state);
    await context.loadAgents(); if (!requestScope.isCurrent(request)) return null;
    const contextSnapshot = await context.refresh(); if (!requestScope.isCurrent(request)) return null;
    await agent.reconcile(contextSnapshot); if (!requestScope.isCurrent(request)) return null;
    await planPanel.setSession(request.sessionId); if (!requestScope.isCurrent(request)) return null;
    await notesPanel.setSession(request.sessionId); if (!requestScope.isCurrent(request)) return null;
    investigationChat.setHistoryPaging(agent.hasOlderHistory());
    await imports.load(); if (!requestScope.isCurrent(request)) return null;
    await refreshMap();
    return refreshEvidence();
  }
  async function refreshAll() { const health = await api(sources.health); byId("db-pill").textContent = health.connected ? "POSTGIS · CONNECTED" : "DATA · LOCAL"; await sessions.refresh(); importView.setSession(state.sessionId()); syncWorkspaceAction(); await connectors.refresh(); if (state.sessionId()) await restoreSelectedSession(); }
  const actions = { "workspace.refresh": refreshAll, "session.create": async () => { const created = await sessions.create(); await restoreSelectedSession(); return { status_message: `已创建工作空间“${created.name}”，可直接导入数据或发起调查。` }; }, "session.delete": async () => { await sessions.remove(); importView.setSession(null); await nativeImports.setSession(null).catch(() => {}); }, "session.profile.load": sessions.loadProfile, "session.profile.save": sessions.saveProfile, "connector.refresh": async () => { await connectors.refresh(); return { status_message: "连接器列表已刷新。" }; }, "connector.create": async () => { const connector = await connectors.createAndBind(); return { status_message: `连接器“${connector.name}”已保存并绑定到当前会话。` }; }, "connector.bind": async () => { const connector = await connectors.bind(byId("connector-select").value); return { status_message: `当前会话已绑定连接器“${connector.name}”。` }; }, "context.refresh": context.refresh, "context.export": context.export, "context.import": context.import, "agent.run": agent.run, "agent.stop": agent.stop, "trace.clear": () => trace.clear() };
  const dock = createDockLayout({ workspace: document.querySelector(".workspace"), leftRail: document.querySelector(".left-panel"), rightRail: document.querySelector(".right-panel"), onLayoutChange: () => requestAnimationFrame(() => map.updateSize()), onActivePanelsChange: (activePanels) => {
    trace.setActive(activePanels.has("trace"));
    // A run mutates the plan and notes, so re-read them when their panel is opened.
    if (activePanels.has("plan")) planPanel.refresh();
    if (activePanels.has("notes")) notesPanel.refresh();
  } });
  dock.mount(ui.tabs.map((tab) => ({ id: tab.id, title: tab.label, element: document.querySelector(`[data-panel="${tab.id}"]`) })).filter((tab) => tab.element));
  installBottomDockResizer(document.querySelector(".workspace"), document.querySelector(".bottom-dock"), () => requestAnimationFrame(() => map.updateSize()));
  const reset = document.createElement("button"); reset.type = "button"; reset.className = "dock-reset"; reset.textContent = "恢复默认面板"; reset.onclick = () => dock.reset(); byId("left-rail-actions")?.append(reset);
  // Render only actions this shell implements: the server catalogue also lists
  // capabilities that still need a client surface, and a declared-but-unbuilt
  // button is worse than an absent one.
  renderActions(ui.actions.filter((action) => Boolean(actions[action.id])), async (id) => { const action = actions[id]; if (!action) throw new Error(`控件尚未迁移：${id}`); const result = await action(); setStatus(result?.status_message || "操作已完成"); });
  byId("session-select").onchange = async () => { requestScope.select(byId("session-select").value); syncWorkspaceAction(); await restoreSelectedSession(); };
  byId("context-agent").onchange = () => context.refresh().catch((error) => setStatus(error.message));
  await refreshAll(); setStatus("GEOINT 工作区已就绪");
}
boot().catch((error) => setStatus(`启动失败 · ${error.message}`));
