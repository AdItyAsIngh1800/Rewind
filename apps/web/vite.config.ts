import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import path from "node:path";

// The dev server proxies the API so the browser talks to one origin. `make mock` and
// `make api` both listen on 8000, so swapping mock for real (E8.6) is which one is
// running, not a code change; REWIND_API_URL overrides for anything else.
export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: { alias: { "@": path.resolve(__dirname, "src") } },
  server: {
    port: 5173,
    proxy: { "/api": process.env.REWIND_API_URL ?? "http://localhost:8000" },
  },
});
