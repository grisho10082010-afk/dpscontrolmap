from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Header, HTTPException
from fastapi.responses import FileResponse, HTMLResponse

import config
import database as db
from geo import get_city_center
from cleanup import cleanup_loop

BASE_DIR = Path(__file__).resolve().parent
WEB_DIR = BASE_DIR / "web"


def _require_admin(x_admin_token: str | None):
    if not x_admin_token or x_admin_token != config.ADMIN_TOKEN:
        raise HTTPException(status_code=401, detail="Bad admin token")


@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    task = asyncio.create_task(cleanup_loop())
    try:
        yield
    finally:
        task.cancel()


app = FastAPI(lifespan=lifespan)


# ===== DEBUG =====
@app.get("/__debug")
def debug():
    return {
        "loaded_file": str(Path(__file__).resolve()),
        "cwd": os.getcwd(),
        "web_dir_exists": WEB_DIR.exists(),
        "web_dir": str(WEB_DIR),
        "routes": sorted([r.path for r in app.routes]),
        "city": config.CITY_NAME,
    }


# ===== STATIC FILES =====
@app.get("/styles.css")
def styles():
    return FileResponse(WEB_DIR / "styles.css")


@app.get("/favicon.ico")
def favicon():
    return HTMLResponse(status_code=204)


# ===== PAGES =====
@app.get("/", response_class=HTMLResponse)
def home():
    return FileResponse(WEB_DIR / "menu.html")


@app.get("/menu", response_class=HTMLResponse)
def menu():
    return FileResponse(WEB_DIR / "menu.html")


@app.get("/map", response_class=HTMLResponse)
def map_page():
    return FileResponse(WEB_DIR / "map.html")


@app.get("/admin", response_class=HTMLResponse)
def admin_page():
    return FileResponse(WEB_DIR / "admin.html")


# ===== API =====
@app.get("/config")
def cfg():
    lat, lon = get_city_center()
    return {
        "city_name": config.CITY_NAME,
        "center": {"lat": lat, "lon": lon},
        "max_distance_km": float(config.MAX_DISTANCE_KM),
        "ttl_hours": int(getattr(config, "TTL_HOURS", 12)),
    }


@app.get("/places")
def places():
    with db.get_db() as s:
        rows = s.query(db.Place).order_by(db.Place.id.desc()).all()
        return [
            {
                "id": r.id,
                "name": r.name,
                "lat": r.lat,
                "lon": r.lon,
                "created_at": r.created_at,
                "last_seen_at": r.last_seen_at,
                "confirmations": int(r.confirmations or 1),
                "bearing": r.bearing,
            }
            for r in rows
        ]


# ===== ADMIN API =====
@app.get("/admin/places")
def admin_places(x_admin_token: str | None = Header(default=None)):
    _require_admin(x_admin_token)
    return places()


@app.delete("/admin/place/{place_id}")
def admin_delete(place_id: int, x_admin_token: str | None = Header(default=None)):
    _require_admin(x_admin_token)
    with db.get_db() as s:
        s.query(db.Place).filter(db.Place.id == place_id).delete()
        db.commit_with_retry(s)
    return {"ok": True}


@app.post("/admin/clear")
def admin_clear(x_admin_token: str | None = Header(default=None)):
    _require_admin(x_admin_token)
    with db.get_db() as s:
        s.query(db.Place).delete()
        db.commit_with_retry(s)
    return {"ok": True}
