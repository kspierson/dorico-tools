import { defineConfig } from "vite";
import { svelte } from "@sveltejs/vite-plugin-svelte";

// Tauri expects a fixed port and no screen clearing (so Rust errors stay visible).
export default defineConfig({
  plugins: [svelte()],
  clearScreen: false,
  server: { port: 1420, strictPort: true },
  // Verovio (notation) is one ~8 MB chunk, loaded only when notation is first shown.
  build: { target: "es2022", outDir: "dist", chunkSizeWarningLimit: 9000 },
});
