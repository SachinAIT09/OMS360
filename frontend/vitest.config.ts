import { defineConfig } from "vitest/config";

// Unit tests live next to the code in src/; browser journeys in e2e/ run with Playwright (npm run e2e).
export default defineConfig({ test: { include: ["src/**/*.test.ts"] } });
