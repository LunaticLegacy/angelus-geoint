import assert from "node:assert/strict";
import Collection from "ol/Collection.js";
import VectorLayer from "ol/layer/Vector.js";
import { rasterDisplayOptions, syncLayers, vectorDataProjection, vectorDisplayOptions, zoomToMapLayer } from "./map-layer-sync.js";

const stretched = rasterDisplayOptions({
  source: { projection: "EPSG:3857" },
  render: {
    bands: [1, 2, 3], nodata: -9999, interpolate: true,
    band_ranges: [
      { band: 1, min: 10, max: 100 },
      { band: 2, min: 20, max: 200 },
      { band: 3, min: 30, max: 300 },
    ],
  },
}, "/assets/raster/render");
assert.equal(stretched.normalize, true);
assert.deepEqual(stretched.source.bands, [1, 2, 3]);
assert.deepEqual(stretched.source.min, [10, 20, 30]);
assert.deepEqual(stretched.source.max, [100, 200, 300]);
assert.deepEqual(stretched.source.nodata, [-9999, -9999, -9999]);

assert.equal(vectorDataProjection({ type: "FeatureCollection", features: [{ geometry: { type: "Point", coordinates: [12025080, 3810415] } }] }), "EPSG:3857");
assert.equal(vectorDataProjection({ type: "FeatureCollection", features: [{ geometry: { type: "Point", coordinates: [108.95, 34.27] } }] }), "EPSG:4326");
assert.deepEqual(
  vectorDisplayOptions({ render: { kind: "vector", stroke_color: "#202020", fill_color: "#80c341", fill_opacity: .36 } }),
  { strokeColor: "#202020", fillColor: "#80c341", fillOpacity: .36 },
);
assert.deepEqual(
  vectorDisplayOptions({ render: { kind: "vector", stroke_color: "invalid", fill_opacity: 2 } }),
  { strokeColor: "#3f82e8", fillColor: "#3f82e8", fillOpacity: .11 },
);

const prior = new VectorLayer();
prior.set("geoint", true);
const layers = new Collection([prior]);
const map = { getLayers: () => layers, removeLayer: (layer) => layers.remove(layer), addLayer: (layer) => layers.push(layer) };
let resolveFetch;
globalThis.fetch = () => new Promise((resolve) => { resolveFetch = resolve; });
let current = true;
const task = syncLayers(map, {
  layers: [{ z_index: 1, visible: true, opacity: 1, source: { kind: "vector", url: "/assets/a/render" } }],
}, "session-a", { isCurrent: () => current });

assert.equal(layers.item(0), prior, "existing layers remain while the new response is loading");
current = false;
resolveFetch({ ok: true, json: async () => ({ type: "FeatureCollection", features: [] }) });
assert.equal(await task, false);
assert.equal(layers.getLength(), 1, "stale data must not replace the current session's map layers");
assert.equal(layers.item(0), prior);

let fitOptions;
const zoomLayer = {
  get: (key) => key === "geointLayerId" ? "layer-a" : undefined,
  getSource: () => ({ getExtent: () => [10, 20, 30, 40] }),
};
const zoomMap = {
  getLayers: () => ({ getArray: () => [zoomLayer] }),
  getView: () => ({ fit: (extent, options) => { fitOptions = { extent, options }; } }),
};
assert.equal(await zoomToMapLayer(zoomMap, "layer-a"), true);
assert.deepEqual(fitOptions.extent, [10, 20, 30, 40]);
assert.equal(await zoomToMapLayer(zoomMap, "missing"), false);
console.log("Map stale-request guard checks passed.");
