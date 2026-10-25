import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

const API = "http://127.0.0.1:8000";
const proxy = Object.fromEntries(
  [
    "/dashboard",
    "/model",
    "/customers",
    "/predict",
    "/eda",
    "/actions",
    "/history",
    "/feedback",
    "/db",
    "/figures",
    "/reports",
    "/docs",
  ].map((path) => [path, { target: API, changeOrigin: true }])
);

export default defineConfig({
  plugins: [react()],
  base: "/app/",
  server: {
    port: 5173,
    proxy,
  },
  build: {
    outDir: "dist",
    assetsDir: "assets",
  },
});
