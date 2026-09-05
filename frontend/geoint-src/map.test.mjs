import assert from "node:assert/strict";
import Collection from "ol/Collection.js";
import VectorLayer from "ol/layer/Vector.js";
import { syncLayers } from "./map-layer-sync.js";

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
console.log("Map stale-request guard checks passed.");
