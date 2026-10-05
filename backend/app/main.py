"""OMS360 API. Run from /backend:  uvicorn app.main:app --reload"""
import asyncio
import contextlib
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .db import init_db
from .routers import admin, auth_routes, engagement, events, field
from .services import connector

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    task = None
    if os.environ.get("OMS360_DISABLE_CONNECTOR") != "1":
        task = asyncio.create_task(connector.run_forever())
    yield
    if task:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task


app = FastAPI(title="OMS360 API", version="2.0.0", lifespan=lifespan,
              description="Storm outage management: events, predictions, outage tickets, crews, mutual aid, ETRs, communications.")
app.add_middleware(CORSMiddleware, allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"], allow_methods=["*"], allow_headers=["*"])
for r in (auth_routes.router, events.router, field.router, engagement.router, admin.router):
    app.include_router(r, prefix="/api")


@app.get("/api/health", tags=["platform"])
def health():
    return {"status": "ok"}


# Serve the built React app (npm run build) so one process runs the whole product.
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "Not found")
        f = FRONTEND_DIST / path
        return FileResponse(f if path and f.is_file() else FRONTEND_DIST / "index.html")
