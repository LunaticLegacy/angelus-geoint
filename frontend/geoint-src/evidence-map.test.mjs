import assert from "node:assert/strict";
import Collection from "ol/Collection.js";
import { setEvidenceLayerVisible, syncEvidenceLayer } from "./evidence-map.js";

const layers = new Collection();
const map = { getLayers: () => layers, addLayer: (layer) => layers.push(layer), removeLayer: (layer) => layers.remove(layer) };
const evidence = {
  type: "FeatureCollection",
  features: [{ type: "Feature", geometry: { type: "Point", coordinates: [108.95, 34.27] }, properties: {} }],
};

syncEvidenceLayer(map, evidence);
assert.equal(layers.getLength(), 1);
assert.equal(layers.item(0).getVisible(), false, "evidence geometry must not silently survive as a visible map layer");
assert.equal(setEvidenceLayerVisible(map, true), true);
assert.equal(layers.item(0).getVisible(), true);
assert.equal(setEvidenceLayerVisible(map, false), true);
assert.equal(layers.item(0).getVisible(), false);
console.log("Evidence overlay visibility checks passed.");
