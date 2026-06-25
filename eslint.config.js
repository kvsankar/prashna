// Flat ESLint config for the vanilla-JS frontend. Lints both static/*.js and
// the inline <script type="module"> blocks inside the HTML (via
// eslint-plugin-html). No build step — this only runs on demand / in CI.
import js from "@eslint/js";
import globals from "globals";
import html from "eslint-plugin-html";

export default [
  { ignores: ["static/vendor/**", "node_modules/**"] },
  js.configs.recommended,
  {
    files: ["static/**/*.js", "static/**/*.html"],
    plugins: { html },
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      globals: { ...globals.browser },
    },
    rules: {
      // Unused vars are a warning (some are intentional placeholders); the
      // high-value checks (no-undef, no-unsafe-negation, etc.) stay errors
      // from js.configs.recommended.
      "no-unused-vars": ["warn", { argsIgnorePattern: "^_", caughtErrors: "none" }],
      // Empty catch blocks are an intentional best-effort pattern here
      // (clipboard, QR render, optional fetches) — allow them.
      "no-empty": ["error", { allowEmptyCatch: true }],
    },
  },
];
