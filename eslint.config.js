// Flat ESLint config for the TypeScript frontend (frontend/src/*.ts).
// Type-checking is done separately by `tsc --noEmit`; this is lint only.
import js from "@eslint/js";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["frontend/dist/**", "node_modules/**", "static/**"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  {
    files: ["frontend/src/**/*.ts"],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: "module",
      globals: { ...globals.browser },
    },
    rules: {
      // Empty catch blocks are an intentional best-effort pattern here.
      "no-empty": ["error", { allowEmptyCatch: true }],
      "@typescript-eslint/no-unused-vars": ["warn", { argsIgnorePattern: "^_", caughtErrors: "none" }],
    },
  },
);
