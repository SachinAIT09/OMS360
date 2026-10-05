// Cross-platform helper for the Python backend, used by the root npm scripts.
//   node scripts/backend.mjs setup    create backend/.venv and install requirements
//   node scripts/backend.mjs serve    run the API (+ built UI) on :8000
//   node scripts/backend.mjs dev      run the API with auto-reload on :8000
//   node scripts/backend.mjs test     run pytest
import { spawnSync } from "node:child_process";
import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const backend = join(dirname(fileURLToPath(import.meta.url)), "..", "backend");
const win = process.platform === "win32";
const venvPy = join(backend, ".venv", win ? "Scripts" : "bin", win ? "python.exe" : "python");

function run(cmd, args) {
  const r = spawnSync(cmd, args, { cwd: backend, stdio: "inherit" });
  if (r.error) {
    console.error(`Could not run "${cmd}": ${r.error.message}`);
    process.exit(1);
  }
  if (r.status !== 0) process.exit(r.status ?? 1);
}

function setup() {
  if (!existsSync(venvPy)) {
    console.log("Creating Python virtual environment in backend/.venv ...");
    run(win ? "python" : "python3", ["-m", "venv", ".venv"]);
  }
  console.log("Installing Python packages ...");
  run(venvPy, ["-m", "pip", "install", "-q", "-r", "requirements.txt"]);
}

const cmd = process.argv[2];
if (cmd === "setup") setup();
else {
  if (!existsSync(venvPy)) setup();
  if (cmd === "serve") run(venvPy, ["-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8000"]);
  // Reload only on app code changes (not tests or the database files), so edits elsewhere don't bounce the API.
  else if (cmd === "dev") run(venvPy, ["-m", "uvicorn", "app.main:app", "--reload", "--reload-dir", "app", "--host", "127.0.0.1", "--port", "8000"]);
  else if (cmd === "test") run(venvPy, ["-m", "pytest", "-q"]);
  else { console.error("usage: node scripts/backend.mjs setup|serve|dev|test"); process.exit(1); }
}
