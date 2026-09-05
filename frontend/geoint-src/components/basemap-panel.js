import "./basemap-panel.css";
import { mountBasemapSourceEditor } from "./basemap-source-editor.js";

export function mountBasemapPanel(host, intents) {
  host.classList.add("basemap-panel");
  host.innerHTML = `
    <header><h2>底图与定位</h2><p>底图独立于会话分析图层，设置保存在当前工作区。</p></header>
    <div class="basemap-manager"><aside class="basemap-library">
    <p data-field="active-source"></p>
    <label>选择要查看或配置的来源<select data-field="source" aria-label="地图源列表"></select></label>
    <div class="basemap-actions"><button type="button" data-action="apply">用作底图</button><button type="button" data-action="add">添加地图源</button><button type="button" data-action="osm">恢复 OSM</button><button type="button" data-action="delete">删除自定义源</button></div>
    <p data-field="crs"></p></aside><section class="basemap-configuration">
    <p data-field="builtin-info">此内置来源无需配置凭据。</p>
    <div data-editor hidden></div>
    <p class="basemap-status" role="status" aria-live="polite"></p>
    <details data-location><summary>经纬度定位</summary><form data-form="locate">
      <div class="basemap-grid"><label>经度<input name="lon" type="number" min="-180" max="180" step="any" value="108.95" required></label><label>纬度<input name="lat" type="number" min="-85.05112878" max="85.05112878" step="any" value="34.27" required></label><label>缩放级别<input name="zoom" type="number" min="0" max="22" value="10" required></label></div>
      <button type="submit">定位</button><p>使用 WGS84 经度、纬度；不是地名搜索。</p>
    </form></details>
    <details data-credentials hidden open><summary>来源凭据</summary><form data-form="key">
      <p data-field="key-state"></p><label>服务 Key（只写）<input name="key" type="password" autocomplete="new-password" maxlength="128" required placeholder="输入支持 WMTS 服务访问的 Key"></label>
      <div class="basemap-actions"><button type="submit">保存 Key</button><button type="button" data-action="clear-key">清除 Key</button></div>
      <p>Key 保存在服务器受限文件，不回显。需自行申请服务权限；切换时同时加载底图与注记。</p>
    </form></details>
    <details><summary>导入公开 XYZ 地图源</summary><form data-form="import">
      <p>支持 WGS84 对齐的 EPSG:3857 标准 XYZ。仅 HTTPS，必须包含 {z}/{x}/{y}；提供者须允许跨域。暂不支持百度、GCJ-02、TMS 或任意 WMTS 配置。</p>
      <label>选择 JSON 文件<input name="file" type="file" accept=".json,application/json"></label>
      <label>或粘贴配置 JSON<textarea name="config" rows="8" spellcheck="false" required></textarea></label>
      <label class="basemap-check"><input name="confirm" type="checkbox" required>我已确认来源授权与坐标兼容性，地址不含私密凭据。</label>
      <button type="submit">导入地图源</button>
    </form></details></section></div>`;
  const status = (message) => { host.querySelector(".basemap-status").textContent = message; };
  const source = host.querySelector('[data-field="source"]');
  const run = async (action) => {
    host.querySelectorAll("button, select").forEach((el) => { el.disabled = true; });
    try { await action(); } catch (error) { status(error.message); }
    finally {
      host.querySelectorAll("button, select").forEach((el) => { el.disabled = false; });
      updateDelete();
    }
  };
  let snapshot, browsing = null;
  const editorHost = host.querySelector("[data-editor]");
  const editor = mountBasemapSourceEditor(editorHost, (id, config) => run(() => id ? intents.update(id, config) : intents.add(config)));
  function updateDelete() {
    host.querySelector('[data-action="delete"]').disabled = !snapshot?.sources.some((s) => s.id === browsing && !s.builtin);
    host.querySelector('[data-action="apply"]').disabled = !snapshot?.sources.some((s) => s.id === browsing && s.enabled);
  }
  function showConfiguration() {
    const record = snapshot?.sources.find((s) => s.id === browsing);
    const custom = !record || !record.builtin;
    editorHost.hidden = !custom;
    if (custom) editor.edit(record);
    host.querySelector('[data-credentials]').hidden = !record?.id.startsWith("tianditu-");
    host.querySelector('[data-field="builtin-info"]').hidden = custom || record?.id.startsWith("tianditu-");
    host.querySelector('[data-field="crs"]').textContent = record ? `地理坐标基准：${record.geographic_crs || "EPSG:4326"}；瓦片投影：${record.projection || "EPSG:3857"}；瓦片网格：${record.tile_grid || "XYZ"}。显示投影与数据基准不是同一概念。` : "自定义来源必须明确声明坐标与网格；更改标记不等于坐标转换。";
    updateDelete();
  }
  source.onchange = () => { browsing = source.value; showConfiguration(); };
  host.querySelector('[data-action="apply"]').onclick = () => run(() => intents.select(browsing));
  host.querySelector('[data-action="add"]').onclick = () => { browsing = "new"; source.value = ""; showConfiguration(); editorHost.querySelector("input").focus(); };
  host.querySelector('[data-action="osm"]').onclick = () => run(() => intents.select("osm"));
  host.querySelector('[data-action="delete"]').onclick = () => run(() => intents.remove(browsing));
  host.querySelector('[data-action="clear-key"]').onclick = () => run(() => intents.setKey(""));
  const keyForm = host.querySelector('[data-form="key"]');
  keyForm.onsubmit = (event) => { event.preventDefault(); const key = keyForm.elements.key.value.trim(); keyForm.elements.key.value = ""; run(() => intents.setKey(key)); };
  const locate = host.querySelector('[data-form="locate"]');
  locate.onsubmit = (event) => { event.preventDefault(); run(() => intents.locate(Number(locate.elements.lon.value), Number(locate.elements.lat.value), Number(locate.elements.zoom.value))); };
  const configForm = host.querySelector('[data-form="import"]');
  configForm.elements.config.value = JSON.stringify({ name: "我的地图源", url: "https://tiles.example.com/{z}/{x}/{y}.png", attribution: "© 数据提供者", projection: "EPSG:3857", min_zoom: 0, max_zoom: 19 }, null, 2);
  configForm.elements.file.onchange = () => run(async () => {
    const file = configForm.elements.file.files[0]; if (!file) return;
    if (file.size > 16384) throw new Error("配置文件不能超过 16 KB");
    configForm.elements.config.value = await file.text();
    status("配置已读取，请确认后导入。");
  });
  configForm.onsubmit = (event) => { event.preventDefault(); run(async () => {
    if (configForm.elements.config.value.length > 16384) throw new Error("配置过长");
    let value; try { value = JSON.parse(configForm.elements.config.value); } catch { throw new Error("配置不是有效 JSON"); }
    await intents.add(value);
  }); };
  return {
    status,
    render(value) {
      const added = snapshot ? value.sources.find((s) => !snapshot.sources.some((old) => old.id === s.id)) : null;
      if (added) browsing = added.id;
      snapshot = value;
      source.replaceChildren(...value.sources.map((s) => new Option(s.name + (s.enabled ? "" : "（待配置）"), s.id)));
      if (!value.sources.some((s) => s.id === browsing)) browsing = value.selected_id;
      source.value = browsing;
      host.querySelector('[data-field="active-source"]').textContent = `正在显示：${value.sources.find((s) => s.id === value.selected_id)?.name || value.selected_id}`;
      host.querySelector('[data-field="key-state"]').textContent = value.has_tianditu_key ? "已保存 Key（不回显）" : "尚未配置 Key";
      showConfiguration();
    },
  };
}
