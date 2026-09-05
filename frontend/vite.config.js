import { resolve } from "node:path";

export default {
  root: resolve(import.meta.dirname, "geoint-src"),
  base: "/static/geoint-dist/",
  build: {
    outDir: resolve(import.meta.dirname, "static/geoint-dist"), emptyOutDir: true,
    cssCodeSplit: false,
    rollupOptions: { input: resolve(import.meta.dirname, "geoint-src/main.js"), output: { entryFileNames: "main.js", chunkFileNames: "assets/[name]-[hash].js", assetFileNames: (asset) => asset.name?.endsWith('.css') ? 'map.css' : 'assets/[name]-[hash][extname]' } },
  },
};
