import { defineConfig } from "vite";
import type { ProxyOptions } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";

const moduleApiProxy = process.env.ITOM_MODULE_API_PROXY || "http://127.0.0.1:8080";
const moduleProxy: ProxyOptions = {
  target: moduleApiProxy,
  changeOrigin: true,
  bypass(incoming) {
    // Translate only an already same-origin request before proxying changes Host.
    if (incoming.headers.origin === `http://${incoming.headers.host}`)
      incoming.headers.origin = new URL(moduleApiProxy).origin;
  },
};

export default defineConfig({
  plugins: [react(), tailwindcss()],
  build: {
    outDir: "../frontend",
    emptyOutDir: false,
    assetsDir: "revamp-assets",
  },
  server: {
    port: 5173,
    proxy: {
      "/api/v1/vendors": moduleProxy,
      "/api/v1/assets": moduleProxy,
      "/api/v1/knowledge": moduleProxy,
      "/api": "http://127.0.0.1:8080",
      "/ready": "http://127.0.0.1:8080",
    },
  },
});
