import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import { resolve } from "node:path";

export default defineConfig({
  plugins: [react()],
  base: "/assets/v2/",
  build: {
    outDir: resolve(import.meta.dirname, process.env.ENES_UI_OUT_DIR || "../cloud/static/v2"),
    emptyOutDir: true,
    assetsDir: "assets",
    rollupOptions: {
      input: {
        owner: resolve(import.meta.dirname, "owner.html"),
        admin: resolve(import.meta.dirname, "admin.html"),
        // O'rnatuvchi paneli ham shu bundle'dan: 2026-09-12 gacha u
        // yakka qo'lda yozilgan `cloud/static/installer.html` edi va
        // shu sababdan ikki UI ishidan (uch til, xato holatlari,
        // telefon QA) HECH NARSA olmagan.
        installer: resolve(import.meta.dirname, "installer.html"),
      },
    },
  },
});
