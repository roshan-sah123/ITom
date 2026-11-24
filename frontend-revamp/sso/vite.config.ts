import { fileURLToPath } from "node:url";
import { defineConfig, loadEnv } from "vite";
import react from "@vitejs/plugin-react";
import { readSettings } from "./src/auth";

// Same-host deployment: the launcher is served from the registered callback path.
const deployedPath = "/oauth2callback/";

function checkProductionSettings(mode: string): void {
  const env = loadEnv(mode, fileURLToPath(new URL(".", import.meta.url)), "VITE_");
  let origin = "";
  try {
    origin = new URL(env.VITE_ENTRA_REDIRECT_URI ?? "").origin;
  } catch {
    // readSettings reports the missing or invalid redirect URI.
  }
  try {
    const settings = readSettings(env, origin, deployedPath);
    if (!settings.redirectUri.startsWith("https://")) {
      throw new Error("The redirect URI must use HTTPS.");
    }
  } catch (error) {
    const reason = error instanceof Error ? error.message : String(error);
    throw new Error(`Production sign-in configuration (.env.${mode}.local): ${reason}`);
  }
}

export default defineConfig(({ command, mode }) => {
  const building = command === "build";
  if (building) checkProductionSettings(mode);
  return {
    plugins: [react()],
    publicDir: false,
    base: building ? deployedPath : "/",
    build: {
      outDir: fileURLToPath(new URL("../../frontend/oauth2callback", import.meta.url)),
      emptyOutDir: true,
    },
    server: {
      host: "localhost",
      port: 5173,
      strictPort: true,
    },
  };
});
