import WebGLTileLayer from "ol/layer/WebGLTile.js";
import VectorLayer from "ol/layer/Vector.js";
import GeoTIFF from "ol/source/GeoTIFF.js";
import VectorSource from "ol/source/Vector.js";
import GeoJSON from "ol/format/GeoJSON.js";

/**
 * Stage analytical layers before replacing the active set.  `isCurrent` is
 * injected by the workspace request scope so this map primitive stays free of
 * session-state dependencies.
 */
export async function syncLayers(map, document, sessionId, { isCurrent = () => true } = {}) {
  const staged = [];
  for (const record of [...document.layers].sort((a, b) => a.z_index - b.z_index)) {
    if (!isCurrent()) return false;
    const source = record.source;
    const url = `${source.url}?session_id=${encodeURIComponent(sessionId)}`;
    let layer;
    if (source.kind === "vector") {
      const response = await fetch(url); if (!response.ok) continue;
      const data = await response.json();
      layer = new VectorLayer({ source: new VectorSource({ features: new GeoJSON().readFeatures(data, { featureProjection: "EPSG:3857" }) }) });
    } else if (source.kind === "cog") {
      layer = new WebGLTileLayer({
        source: new GeoTIFF({
          sources: [{ url }],
          // The server publishes a controlled display projection. Supplying
          // it explicitly avoids browser-specific failures on source TIFFs
          // that originally used custom WKT definitions.
          projection: source.projection || "EPSG:3857",
          normalize: false,
        }),
      });
    } else continue;
    layer.setVisible(record.visible); layer.setOpacity(record.opacity); layer.setZIndex(record.z_index);
    layer.set("geoint", true); staged.push(layer);
  }
  if (!isCurrent()) return false;
  const previous = map.getLayers().getArray().filter((layer) => layer.get("geoint"));
  previous.forEach((layer) => map.removeLayer(layer));
  staged.forEach((layer) => map.addLayer(layer));
  return true;
}
