import { api } from "../api.js";

export function createBasemaps({ view, map, onSnapshot = () => {} }) {
  const endpoint = "/api/geoint/basemaps";
  let snapshot;
  let queue = Promise.resolve();
  function apply(value) {
    snapshot = value;
    view.render(value);
    onSnapshot(value);
    map.select(value.sources.find((s) => s.id === value.selected_id) || value.sources[0]);
  }
  function mutate(path, method, body, message) {
    const task = queue.then(async () => {
      const value = await api(endpoint + path, { method, body: body === undefined ? undefined : JSON.stringify(body) });
      apply(value);
      view.status(message);
    });
    queue = task.catch(() => {});
    return task;
  }
  return {
    async load() { apply(await api(endpoint)); view.status("底图配置已加载。"); },
    select(source_id) { return mutate("/selection", "PUT", { source_id }, "底图已切换，分析图层与地图视角保持不变。"); },
    add(config) { return mutate("", "POST", config, "地图源已导入，请在当前底图中选择。"); },
    update(id, config) { return mutate(`/${encodeURIComponent(id)}`, "PUT", config, "地图源配置已更新。"); },
    remove(id) { return mutate(`/${encodeURIComponent(id)}`, "DELETE", undefined, "自定义源已删除。"); },
    setKey(key) { return mutate("/tianditu-key", "PUT", { key }, key ? "Key 已保存，可以选择天地图。" : "Key 已清除。"); },
    locate(lon, lat, zoom) { map.locate(lon, lat, zoom); view.status(`已定位至 ${lon}, ${lat}。`); },
    selectedId() { return snapshot?.selected_id || "osm"; },
  };
}
