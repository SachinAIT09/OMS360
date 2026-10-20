/* End-to-end tests: the built UI served by the real FastAPI backend on a fresh, temporary Oklahoma database.
   Run:  npm run build && npm run e2e      (the backend starts automatically; first start seeds the database, ~30 s) */
import { chromium, defineConfig, devices } from "@playwright/test";
import { existsSync, readdirSync } from "node:fs";
import { homedir, tmpdir } from "node:os";
import { join } from "node:path";

/** The bundled Chromium, or (if its download was incomplete) the newest complete Chromium already in the Playwright cache. */
function chromeExecutable(): string | undefined {
  if (process.env.PW_CHROMIUM) return process.env.PW_CHROMIUM;
  if (existsSync(chromium.executablePath())) return undefined;
  const cache = process.env.PLAYWRIGHT_BROWSERS_PATH ?? (process.platform === "win32" ? join(process.env.LOCALAPPDATA ?? "", "ms-playwright")
    : process.platform === "darwin" ? join(homedir(), "Library", "Caches", "ms-playwright") : join(homedir(), ".cache", "ms-playwright"));
  if (!existsSync(cache)) return undefined;
  const found = readdirSync(cache).filter(d => /^chromium-\d+$/.test(d)).sort((a, b) => Number(b.split("-")[1]) - Number(a.split("-")[1]))
    .flatMap(d => ["chrome-win64/chrome.exe", "chrome-win/chrome.exe", "chrome-linux/chrome", "chrome-linux64/chrome"].map(p => join(cache, d, p)))
    .find(p => existsSync(p));
  return found;
}

const PORT = 8123;
// A fresh database per run. The config is also loaded by worker processes, which inherit this variable from the runner,
// so they reuse the same file instead of touching the one the server has open.
process.env.E2E_DB ??= join(tmpdir(), `oms360-e2e-${Date.now()}.sqlite`);
const DB = process.env.E2E_DB;
const win = process.platform === "win32";

export default defineConfig({
  testDir: "./e2e",
  timeout: 90_000,
  expect: { timeout: 20_000 },
  fullyParallel: false,
  workers: 1,
  retries: 0,
  reporter: [["list"], ["html", { open: "never" }]],
  use: { baseURL: `http://127.0.0.1:${PORT}`, trace: "retain-on-failure", screenshot: "only-on-failure", viewport: { width: 1440, height: 900 } },
  projects: [{ name: "chromium", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 }, launchOptions: { executablePath: chromeExecutable() } } }],
  webServer: {
    command: `${win ? ".venv\\Scripts\\python.exe" : ".venv/bin/python"} -m uvicorn app.main:app --host 127.0.0.1 --port ${PORT}`,
    cwd: "../backend",
    url: `http://127.0.0.1:${PORT}/api/health`,
    timeout: 240_000,
    reuseExistingServer: !!process.env.E2E_REUSE,
    env: { OMS360_DB: DB, OMS360_TERRITORY: "oklahoma", OMS360_ASSET_DENSITY: "30", OMS360_DISABLE_CONNECTOR: "1", PYTHONUTF8: "1" },
    stdout: "ignore", stderr: "pipe",
  },
});
