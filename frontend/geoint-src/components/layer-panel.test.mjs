import assert from "node:assert/strict";
import { availableMapAssets, parseIgnoredValues, reorderLayerIds, vectorRenderDraft } from "./layer-panel.js";

assert.deepEqual(reorderLayerIds(["top", "middle", "bottom"], "bottom", "top"), ["bottom", "top", "middle"]);
assert.deepEqual(reorderLayerIds(["top", "middle", "bottom"], "top", "bottom"), ["middle", "top", "bottom"]);
assert.deepEqual(reorderLayerIds(["top"], "top", "top"), ["top"]);
assert.deepEqual(reorderLayerIds(["top"], "missing", "top"), ["top"]);
assert.deepEqual(parseIgnoredValues("0, 255，-9999 0 text"), [0, 255, -9999]);
assert.deepEqual(vectorRenderDraft({ kind: "vector", stroke_color: "#202020", fill_color: "#80c341", fill_opacity: .36 }), { kind: "vector", stroke_color: "#202020", fill_color: "#80c341", fill_opacity: .36 });
assert.deepEqual(vectorRenderDraft({ kind: "vector", stroke_color: "invalid", fill_opacity: 2 }), { kind: "vector", stroke_color: "#3f82e8", fill_color: "#3f82e8", fill_opacity: .11 });
assert.deepEqual(
  availableMapAssets(
    [{ id: "asset_vector", format: "GeoJSON" }, { id: "asset_raster", format: "GeoTIFF" }, { id: "asset_other", format: "Shapefile" }],
    [{ asset_id: "asset_vector" }],
  ).map((asset) => asset.id),
  ["asset_raster"],
);
console.log("Layer ordering checks passed.");
