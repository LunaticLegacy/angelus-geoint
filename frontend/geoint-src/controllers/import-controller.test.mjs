import assert from "node:assert/strict";
import { validateBrowserImportFiles } from "./import-controller.js";

const file = (name) => ({ name, size: 1 });
assert.doesNotThrow(() => validateBrowserImportFiles([file("省界.shp"), file("省界.shx"), file("省界.dbf"), file("省界.prj")]));
assert.throws(() => validateBrowserImportFiles([file("省界.shp")]), /缺少 \.shx、\.dbf/);
assert.doesNotThrow(() => validateBrowserImportFiles([file("rain.tif"), file("boundary.geojson")]));
console.log("Browser Shapefile bundle preflight checks passed.");
