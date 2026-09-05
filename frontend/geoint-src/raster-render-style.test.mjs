import assert from "node:assert/strict";
import { normalizedIgnoreValues, rasterUsesRawCategories, rasterWebGlStyle } from "./raster-render-style.js";

const categorical = {
  kind: "raster", mode: "classified", bands: [1], ignore_values: [0],
  classification: [{ value: 1, label: "草地", color: "#49a24d" }],
};
assert.equal(rasterUsesRawCategories(categorical), true);
assert.deepEqual(rasterWebGlStyle(categorical), {
  color: ["match", ["band", 1], 0, [0, 0, 0, 0], 1, "#49a24d", [0, 0, 0, 0]],
});
assert.deepEqual(normalizedIgnoreValues([0, 0, -9999, "x"]), [0, -9999]);
assert.deepEqual(rasterWebGlStyle({ kind: "raster", mode: "single_band", bands: [1], ignore_values: [0] }), {
  color: ["case", ["in", ["band", 1], ["literal", [0]]], [0, 0, 0, 0], ["color", ["*", 255, ["band", 1]], ["*", 255, ["band", 1]], ["*", 255, ["band", 1]], 1]],
});
console.log("Raster category renderer checks passed.");
