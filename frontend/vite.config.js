import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// In dev, proxy /api to the FastAPI server so the frontend can use relative URLs everywhere.
export default defineConfig({
  plugins: [react()],
  build: { rollupOptions: { output: { manualChunks: { charts: ["recharts"], react: ["react", "react-dom"] } } } },
  server: { proxy: { "/api": "http://localhost:8000" } },
});
