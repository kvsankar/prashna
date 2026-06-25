import { resolve } from "node:path";
import { defineConfig, type Plugin } from "vite";

const ROOT = resolve(import.meta.dirname, "frontend");

// In production FastAPI maps clean URLs (/m/<code> → moderator.html). The
// Vite dev server needs the same mapping so HMR works at the real URLs, and
// so pathCode() (which reads location.pathname) still sees the code.
function cleanUrls(): Plugin {
  const routes: [RegExp, string][] = [
    [/^\/$/, "/index.html"],
    [/^\/s\/[^/]+\/?$/, "/participant.html"],
    [/^\/m\/[^/]+\/?$/, "/moderator.html"],
    [/^\/p\/[^/]+\/?$/, "/projector.html"],
    [/^\/quizzes\/?$/, "/quizzes.html"],
  ];
  return {
    name: "prashna-clean-urls",
    configureServer(server) {
      server.middlewares.use((req, _res, next) => {
        const path = (req.url ?? "/").split("?")[0];
        for (const [re, html] of routes) {
          if (re.test(path)) { req.url = html; break; }
        }
        next();
      });
    },
  };
}

export default defineConfig({
  root: "frontend",
  // During the JS→TS migration the built pages are served under /build/
  // (FastAPI mounts dist there) while un-migrated pages still come from the
  // old /static/. `input` lists only the pages migrated so far; add each as
  // it's converted. (At the end this collapses back to /static/.)
  base: "/build/",
  plugins: [cleanUrls()],
  build: {
    outDir: "dist",
    emptyOutDir: true,
    rollupOptions: {
      input: {
        projector: resolve(ROOT, "projector.html"),
      },
    },
  },
  server: {
    proxy: {
      "/api": "http://127.0.0.1:8000",
      "/uploads": "http://127.0.0.1:8000",
      "/ws": { target: "ws://127.0.0.1:8000", ws: true },
    },
  },
});
