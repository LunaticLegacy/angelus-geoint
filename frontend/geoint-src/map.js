import "ol/ol.css";
import Map from "ol/Map.js";
import View from "ol/View.js";
import { fromLonLat } from "ol/proj.js";
export { previewVectorLayerStyle, syncLayers, zoomToMapLayer } from "./map-layer-sync.js";

export function createMap(target) {
  return new Map({ target, layers: [], view: new View({ center: fromLonLat([108.95, 34.27]), zoom: 7 }) });
}
