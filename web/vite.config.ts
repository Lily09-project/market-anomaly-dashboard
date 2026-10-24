import react from "@vitejs/plugin-react";
import { defineConfig } from "vitest/config";

// Relative base so the same build works under any GitHub Pages sub-path.
export default defineConfig({
  base: "./",
  plugins: [react()],
  build: {
    target: "es2022",
    sourcemap: false,
    assetsInlineLimit: 0,
  },
  worker: {
    format: "es",
  },
  test: {
    environment: "jsdom",
    include: ["src/**/*.test.{ts,tsx}"],
    setupFiles: ["src/test-setup.ts"],
    coverage: {
      provider: "v8",
      include: ["src/lib/**/*.ts"],
      exclude: ["src/lib/**/*.test.ts", "src/lib/types.ts"],
      reporter: ["text", "json-summary"],
      thresholds: { lines: 85, statements: 85, functions: 85, branches: 75 },
    },
  },
});
