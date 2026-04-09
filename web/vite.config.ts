import { defineConfig } from "vite";

export default defineConfig({
  base: process.env.VITE_BASE_PATH || "/",
  server: {
    port: 4200,
    proxy: {
      "/ws": {
        target: "ws://localhost:2324",
        ws: true,
        rewriteWsOrigin: true,
      },
    },
  },
});
