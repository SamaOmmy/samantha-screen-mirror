import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Builds straight into the Python package so the server can serve it.
// For `npm run dev`, point SM_TARGET at a running server, e.g. http://100.x.y.z:8787
const target = process.env.SM_TARGET ?? "http://127.0.0.1:8787";

export default defineConfig({
  plugins: [react()],
  build: { outDir: "../mirror/web", emptyOutDir: true },
  server: { proxy: { "/api": target, "/stream": target } },
});
