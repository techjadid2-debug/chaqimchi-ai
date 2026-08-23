import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "node:path";

export default defineConfig({
  plugins: [react()],
  base: "/assets/v2/",
  build: {
    outDir: resolve(import.meta.dirname, process.env.CHAQIMCHI_UI_OUT_DIR || "../cloud/static/v2"),
    emptyOutDir: true,
    assetsDir: "assets",
    rollupOptions: {
      input: {
        owner: resolve(import.meta.dirname, "owner.html"),
        admin: resolve(import.meta.dirname, "admin.html"),
      },
    },
  },
});
