/** Structured public XYZ configuration. No transport or map-engine knowledge. */
export function mountBasemapSourceEditor(host, onSave) {
  host.innerHTML = `<form class="basemap-source-form">
    <h3 data-title>添加地图源</h3>
    <div class="basemap-fields"><label>名称<input name="name" maxlength="80" required></label>
    <label>协议<select name="protocol"><option>公开 HTTPS XYZ</option></select></label>
    <label class="wide">瓦片地址<input name="url" type="url" required placeholder="https://tiles.example.com/{z}/{x}/{y}.png"></label>
    <label class="wide">来源署名<input name="attribution" maxlength="300" required placeholder="© 数据提供者"></label>
    <label>地理坐标系<select name="geographic_crs"><option value="EPSG:4326">WGS84 · EPSG:4326</option></select></label>
    <label>瓦片投影<select name="projection"><option value="EPSG:3857">Web Mercator · EPSG:3857</option></select></label>
    <label>最小级别<input name="min_zoom" type="number" min="0" max="22" value="0" required></label>
    <label>最大级别<input name="max_zoom" type="number" min="0" max="22" value="19" required></label></div>
    <p>瓦片网格：XYZ，左上原点、256 像素。仅支持无私密凭据的公开源；提供者需允许跨域。坐标选项是兼容性声明，不会转换 GCJ-02、BD09 或 TMS。</p>
    <label class="basemap-check"><input type="checkbox" name="confirm" required>已核对来源授权、坐标基准和瓦片网格。</label>
    <button type="submit">保存地图源</button>
  </form>`;
  const form = host.querySelector("form");
  let id = null;
  form.onsubmit = (event) => {
    event.preventDefault();
    const data = Object.fromEntries(["name", "url", "attribution", "projection", "geographic_crs"].map((key) => [key, form.elements[key].value.trim()]));
    data.min_zoom = Number(form.elements.min_zoom.value); data.max_zoom = Number(form.elements.max_zoom.value); data.tile_grid = "XYZ";
    onSave(id, data);
  };
  return { edit(source) {
    id = source?.id || null;
    form.reset();
    host.querySelector("[data-title]").textContent = id ? "编辑地图源" : "添加地图源";
    for (const key of ["name", "url", "attribution", "projection", "geographic_crs", "min_zoom", "max_zoom"]) {
      if (source?.[key] !== undefined) form.elements[key].value = source[key];
    }
  } };
}
