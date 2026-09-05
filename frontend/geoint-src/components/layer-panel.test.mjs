import assert from "node:assert/strict";
import { parseIgnoredValues, reorderLayerIds } from "./layer-panel.js";

assert.deepEqual(reorderLayerIds(["top", "middle", "bottom"], "bottom", "top"), ["bottom", "top", "middle"]);
assert.deepEqual(reorderLayerIds(["top", "middle", "bottom"], "top", "bottom"), ["middle", "top", "bottom"]);
assert.deepEqual(reorderLayerIds(["top"], "top", "top"), ["top"]);
assert.deepEqual(reorderLayerIds(["top"], "missing", "top"), ["top"]);
assert.deepEqual(parseIgnoredValues("0, 255，-9999 0 text"), [0, 255, -9999]);
console.log("Layer ordering checks passed.");
