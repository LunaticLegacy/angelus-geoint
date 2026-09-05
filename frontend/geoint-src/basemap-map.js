import LayerGroup from "ol/layer/Group.js";
import TileLayer from "ol/layer/Tile.js";
import OSM from "ol/source/OSM.js";
import XYZ from "ol/source/XYZ.js";
import { fromLonLat } from "ol/proj.js";

const escape = (text) => String(text).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
export function createBasemapMap(map, onError = () => {}) {
  const group = new LayerGroup({ layers: [], zIndex: -10000 });
  group.set("basemap", true);
  map.getLayers().insertAt(0, group);
  let revision = 0;
  return {
    select(record) {
      const current = ++revision;
      let reported = false;
      const sources = record.kind === "osm" ? [new OSM()] : record.tiles.map((url) => new XYZ({
        url, projection: "EPSG:3857", crossOrigin: "anonymous",
        minZoom: record.min_zoom, maxZoom: record.max_zoom, attributions: escape(record.attribution),
      }));
      const layers = sources.map((source) => {
        source.on("tileloaderror", () => {
          if (current === revision && !reported) { reported = true; onError(`${record.name} 瓦片加载失败：请检查网络、服务权限或 CORS，可切回 OSM。`); }
        });
        return new TileLayer({ source });
      });
      group.getLayers().clear();
      layers.forEach((layer) => group.getLayers().push(layer));
    },
    locate(lon, lat, zoom = 10) {
      if (![lon, lat, zoom].every(Number.isFinite) || Math.abs(lon) > 180 || Math.abs(lat) > 85.05112878 || zoom < 0 || zoom > 22) throw new Error("请输入有效经纬度（纬度 ±85.0511° 内）与 0–22 级缩放。");
      map.getView().animate({ center: fromLonLat([lon, lat]), zoom, duration: 350 });
    },
  };
}
