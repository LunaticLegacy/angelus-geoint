import GeoJSON from "ol/format/GeoJSON.js";
import VectorLayer from "ol/layer/Vector.js";
import VectorSource from "ol/source/Vector.js";
import { Circle as CircleStyle, Fill, Stroke, Style } from "ol/style.js";

/** Replace the non-canonical map projection of spatial evidence only. */
export function syncEvidenceLayer(map, featureCollection) {
  const previous = map.getLayers().getArray().filter((layer) => layer.get("geoint-evidence"));
  previous.forEach((layer) => map.removeLayer(layer));
  const features = new GeoJSON().readFeatures(featureCollection || { type: "FeatureCollection", features: [] }, { featureProjection: "EPSG:3857" });
  if (!features.length) return;
  const layer = new VectorLayer({ source: new VectorSource({ features }), style: new Style({ stroke: new Stroke({ color: "#f4cc58", width: 2 }), fill: new Fill({ color: "rgba(244,204,88,.18)" }), image: new CircleStyle({ radius: 6, fill: new Fill({ color: "#f4cc58" }), stroke: new Stroke({ color: "#182032", width: 1 }) }) }) });
  layer.set("geoint-evidence", true); layer.setZIndex(10000); map.addLayer(layer);
}
