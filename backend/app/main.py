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
from .routers import admin, assets, auth_routes, engagement, events, field
from .services import connector

FRONTEND_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    from .services.assets import warm_plan_cache
    asyncio.get_running_loop().run_in_executor(None, warm_plan_cache)  # replacement planning answers instantly once warm
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
# Extra UI origins (e.g. a Netlify site) as a comma-separated list: OMS360_CORS_ORIGINS=https://oms360.netlify.app
CORS_ORIGINS = ["http://localhost:5173", "http://127.0.0.1:5173",
                *(o.strip().rstrip("/") for o in os.environ.get("OMS360_CORS_ORIGINS", "").split(",") if o.strip())]
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_methods=["*"], allow_headers=["*"])
for r in (auth_routes.router, events.router, field.router, engagement.router, admin.router, assets.router):
    app.include_router(r, prefix="/api")


@app.get("/api/health", tags=["platform"])
def health():
    return {"status": "ok"}


@app.get("/api/profile", tags=["platform"])
def profile():
    """The territory this deployment runs (public: the login page and public outage map are branded with it)."""
    from . import data
    from .services.events import EVENT_KINDS
    return {"territory": data.TERRITORY, "utility": data.UTILITY_NAME, "utility_short": data.UTILITY_SHORT, "site": data.SITE,
            "area": data.AREA, "state": data.STATE, "timezone": data.TZ_NAME, "hazard": data.HAZARD,
            "map_center": data.MAP_CENTER, "map_zoom": data.MAP_ZOOM, "weather_label": data.WEATHER_LABEL, "has_water": data.HAS_WATER,
            "regions": [{"id": r["id"], "name": r["name"]} for r in data.REGIONS], "event_kinds": EVENT_KINDS,
            "new_event": data.NEW_EVENT, "sample_addresses": [a for a, _ in data.SAMPLE_ADDRESSES],
            "jarvis_suggestions": [x.strip('"') for x in data.JARVIS_SUGGESTIONS],
            "demo_login_domain": data.EMAIL_DOMAIN}


# Serve the built React app (npm run build) so one process runs the whole product.
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            raise HTTPException(404, "Not found")
        f = FRONTEND_DIST / path
        return FileResponse(f if path and f.is_file() else FRONTEND_DIST / "index.html")
