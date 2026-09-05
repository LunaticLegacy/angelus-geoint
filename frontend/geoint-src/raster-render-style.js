/** Browser-side translation of the declarative, server-validated raster style. */
const TRANSPARENT = [0, 0, 0, 0];
const HEX_COLOR = /^#[0-9a-f]{6}$/i;

function finite(value) { return typeof value === "number" && Number.isFinite(value); }

export function normalizedIgnoreValues(value) {
  if (!Array.isArray(value)) return [];
  return [...new Set(value.filter(finite))].slice(0, 128);
}

export function normalizedClasses(value, ignored = []) {
  const skipped = new Set(ignored);
  if (!Array.isArray(value)) return [];
  const used = new Set();
  return value.filter((item) => {
    if (!item || !finite(item.value) || skipped.has(item.value) || used.has(item.value) || !HEX_COLOR.test(item.color || "")) return false;
    used.add(item.value); return true;
  }).slice(0, 128);
}

/**
 * Return a WebGL style only when it is needed.  Returning ``undefined``
 * retains OpenLayers' native RGB/single-band output for continuous rasters.
 */
export function rasterWebGlStyle(render) {
  const value = render && typeof render === "object" ? render : {};
  const bands = Array.isArray(value.bands) ? value.bands : [1];
  const singleBand = bands.length === 1 && Number.isInteger(bands[0]) && bands[0] > 0 ? bands[0] : null;
  if (!singleBand) return undefined;
  const ignored = normalizedIgnoreValues(value.ignore_values);
  const classes = normalizedClasses(value.classification, ignored);
  if (value.mode !== "classified" && !ignored.length) return undefined;

  if (value.mode !== "classified") {
    const shade = ["*", 255, ["band", singleBand]];
    return {
      color: ["case", ["in", ["band", singleBand], ["literal", ignored]], TRANSPARENT, ["color", shade, shade, shade, 1]],
    };
  }

  // A category raster remains integer-valued; for classified layers we
  // deliberately request raw values from the source in map-layer-sync.
  const match = ["match", ["band", singleBand]];
  ignored.forEach((category) => match.push(category, TRANSPARENT));
  classes.forEach((category) => match.push(category.value, category.color));
  match.push(TRANSPARENT);
  return { color: match };
}

export function rasterUsesRawCategories(render) {
  return render?.kind === "raster" && render.mode === "classified";
}
