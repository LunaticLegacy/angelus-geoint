import WebGLTileLayer from "ol/layer/WebGLTile.js";
import VectorLayer from "ol/layer/Vector.js";
import GeoTIFF from "ol/source/GeoTIFF.js";
import VectorSource from "ol/source/Vector.js";
import GeoJSON from "ol/format/GeoJSON.js";
import { Circle as CircleStyle, Fill, Stroke, Style } from "ol/style.js";
import { rasterUsesRawCategories, rasterWebGlStyle } from "./raster-render-style.js";

function finiteNumber(value) {
  return typeof value === "number" && Number.isFinite(value) ? value : null;
}

function usableExtent(value) {
  return Array.isArray(value) && value.length === 4
    && value.every((coordinate) => Number.isFinite(coordinate))
    && value[2] > value[0] && value[3] > value[1];
}

const defaultVectorStyle = new Style({
  stroke: new Stroke({ color: "#3f82e8", width: 2.25 }),
  fill: new Fill({ color: "rgba(63, 130, 232, .11)" }),
  image: new CircleStyle({ radius: 5, fill: new Fill({ color: "#3f82e8" }), stroke: new Stroke({ color: "#f5f8ff", width: 1 }) }),
});

function coordinateBounds(value, bounds, remaining) {
  if (!remaining.value) return;
  if (Array.isArray(value) && value.length >= 2 && Number.isFinite(value[0]) && Number.isFinite(value[1])) {
    bounds.minX = Math.min(bounds.minX, value[0]); bounds.maxX = Math.max(bounds.maxX, value[0]);
    bounds.minY = Math.min(bounds.minY, value[1]); bounds.maxY = Math.max(bounds.maxY, value[1]); remaining.value -= 1;
  } else if (Array.isArray(value)) value.forEach((child) => coordinateBounds(child, bounds, remaining));
}

/** GeoJSON normally implies WGS84. Accept old managed exports whose missing
 * `.prj` left unmistakable EPSG:3857 metre coordinates in the GeoJSON body. */
export function vectorDataProjection(data) {
  const name = data?.crs?.properties?.name;
  if (typeof name === "string" && /EPSG(?::|\/|::)3857/i.test(name)) return "EPSG:3857";
  const bounds = { minX: Infinity, maxX: -Infinity, minY: Infinity, maxY: -Infinity };
  const remaining = { value: 200_000 };
  (Array.isArray(data?.features) ? data.features : []).forEach((feature) => coordinateBounds(feature?.geometry?.coordinates, bounds, remaining));
  const mercator = [bounds.minX, bounds.maxX, bounds.minY, bounds.maxY];
  const metreScale = mercator.every((value) => Number.isFinite(value) && Math.abs(value) <= 20_037_509)
    && Math.max(Math.abs(bounds.minX), Math.abs(bounds.maxX)) > 2_000_000
    && Math.max(Math.abs(bounds.minY), Math.abs(bounds.maxY)) > 1_000_000;
  return metreScale ? "EPSG:3857" : "EPSG:4326";
}

/** Fit the map to a rendered, session-owned layer without leaking OL objects
 * into the layer-panel component. GeoTIFF sources resolve their extent lazily;
 * vectors expose it synchronously after their GeoJSON source has loaded. */
export async function zoomToMapLayer(map, layerId) {
  const layer = map.getLayers().getArray().find((item) => item.get("geointLayerId") === layerId);
  const source = layer?.getSource?.();
  if (!source) return false;
  let extent = source.getExtent?.();
  if (!usableExtent(extent) && source.getView) {
    try { extent = (await source.getView())?.extent; } catch { return false; }
  }
  if (!usableExtent(extent)) return false;
  map.getView().fit(extent, { padding: [44, 44, 44, 44], duration: 220, maxZoom: 16 });
  return true;
}

function validBandIds(value) {
  if (!Array.isArray(value)) return [];
  return [...new Set(value.filter((band) => Number.isInteger(band) && band > 0))];
}

/**
 * Convert a server-published raster render contract into the OpenLayers source
 * options.  Raw sample values must never be handed to WebGL: a float NDVI or
 * reflectance input otherwise appears as an all-white/black tile.
 */
export function rasterDisplayOptions(record, url) {
  const render = record.render && typeof record.render === "object" ? record.render : {};
  const bands = validBandIds(render.bands);
  const source = { url };
  if (bands.length) source.bands = bands;

  const configuredRanges = new Map(
    (Array.isArray(render.band_ranges) ? render.band_ranges : [])
      .filter((item) => item && Number.isInteger(item.band) && item.band > 0)
      .map((item) => [item.band, { min: finiteNumber(item.min), max: finiteNumber(item.max) }]),
  );
  const fallback = render.range && typeof render.range === "object"
    ? { min: finiteNumber(render.range.min), max: finiteNumber(render.range.max) }
    : { min: null, max: null };
  const selected = bands.length ? bands : [1];
  const maximumBand = Math.max(...selected);
  const ranges = selected.map((band) => configuredRanges.get(band) || fallback);
  if (ranges.every((range) => range.min !== null && range.max !== null && range.max > range.min)) {
    // GeoTIFFSource indexes min/max/nodata by original TIFF band number, not
    // by the compact output array requested with `bands`.
    source.min = Array.from({ length: maximumBand }, (_, index) => configuredRanges.get(index + 1)?.min ?? fallback.min);
    source.max = Array.from({ length: maximumBand }, (_, index) => configuredRanges.get(index + 1)?.max ?? fallback.max);
  }
  const nodata = finiteNumber(render.nodata);
  if (nodata !== null) source.nodata = Array.from({ length: maximumBand }, () => nodata);

  const categoryValues = rasterUsesRawCategories(render);
  return {
    source,
    projection: record.source.projection || "EPSG:3857",
    interpolate: render.interpolate !== false,
    // The OpenLayers default is true, but making it explicit protects the
    // display pipeline against regressions to raw float/uint sample values.
    // Category matching compares original integer codes (e.g. 1 = grassland),
    // whereas all continuous products use the server-provided stretch.
    normalize: !categoryValues,
  };
}

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
      const dataProjection = vectorDataProjection(data);
      layer = new VectorLayer({
        source: new VectorSource({ features: new GeoJSON().readFeatures(data, { dataProjection, featureProjection: "EPSG:3857" }) }),
        style: defaultVectorStyle,
      });
      if (dataProjection !== "EPSG:4326") layer.set("geointProjectionWarning", "已按 EPSG:3857 兼容显示未标注 CRS 的历史矢量数据");
    } else if (source.kind === "cog") {
      const display = rasterDisplayOptions(record, url);
      layer = new WebGLTileLayer({
        source: new GeoTIFF({
          sources: [display.source],
          // The server publishes a controlled display projection. Supplying
          // it explicitly avoids browser-specific failures on source TIFFs
          // that originally used custom WKT definitions.
          projection: display.projection,
          interpolate: display.interpolate,
          normalize: display.normalize,
        }),
        style: rasterWebGlStyle(record.render),
      });
    } else continue;
    layer.setVisible(record.visible); layer.setOpacity(record.opacity); layer.setZIndex(record.z_index);
    layer.set("geoint", true); layer.set("geointLayerId", record.id); staged.push(layer);
  }
  if (!isCurrent()) return false;
  const previous = map.getLayers().getArray().filter((layer) => layer.get("geoint"));
  previous.forEach((layer) => map.removeLayer(layer));
  staged.forEach((layer) => map.addLayer(layer));
  return true;
}
