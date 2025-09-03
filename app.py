# app.py
import time
from typing import Any, Dict, List, Optional
from urllib.parse import urlencode

import httpx
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse

OPENDOTA_LIVE = "https://api.opendota.com/api/live"
OPENDOTA_PRO  = "https://api.opendota.com/api/proMatches"

app = FastAPI(title="Esports Live (OpenDota)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # OK for local dev
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---- simple in-memory cache ----
_cache: Dict[str, Dict[str, Any]] = {}
CACHE_SECONDS = 10

def cache_get(k: str) -> Optional[Any]:
    v = _cache.get(k)
    if not v or v["exp"] < time.time():
        return None
    return v["data"]

def cache_set(k: str, data: Any, ttl: int = CACHE_SECONDS):
    _cache[k] = {"data": data, "exp": time.time() + ttl}

def normalize_live(rows: Any) -> List[Dict[str, Any]]:
    items = []
    if isinstance(rows, list):
        for m in rows:
            league = m.get("league_name") or ""
            team1 = m.get("team_name_radiant") or "Radiant"
            team2 = m.get("team_name_dire") or "Dire"
            score = f"{m.get('radiant_score', 0)} - {m.get('dire_score', 0)}"
            game_time = m.get("game_time", 0)
            status = f"Live • {max(game_time,0)//60}m" if game_time else "Live"
            items.append({
                "id": m.get("match_id"),
                "game": "Dota 2",
                "league": league,
                "series": "",
                "team1": team1,
                "team2": team2,
                "status": status,
                "score": score,
                "begin_at": None,
                "raw": m,
            })
    return items

def normalize_pro(rows: Any) -> List[Dict[str, Any]]:
    items = []
    if isinstance(rows, list):
        for m in rows[:20]:
            team1 = m.get("radiant_name") or "Radiant"
            team2 = m.get("dire_name") or "Dire"
            score = f"{m.get('radiant_score', 0)} - {m.get('dire_score', 0)}"
            items.append({
                "id": m.get("match_id"),
                "game": "Dota 2",
                "league": m.get("league_name") or "",
                "series": "",
                "team1": team1,
                "team2": team2,
                "status": "Finished",
                "score": score,
                "begin_at": None,
                "raw": m,
            })
    return items

@app.get("/api/dota/live")
async def dota_live(request: Request):
    params = dict(request.query_params)
    qs = urlencode(params, doseq=True)
    url = f"{OPENDOTA_LIVE}{'?' + qs if qs else ''}"

    cached = cache_get(url)
    if cached:
        return JSONResponse({"fromCache": True, **cached})

    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(url)
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"OpenDota upstream error {r.status_code}")

    rows = r.json()
    payload = {"count": len(rows), "items": normalize_live(rows)}
    cache_set(url, payload)
    return JSONResponse({"fromCache": False, **payload})

@app.get("/api/dota/recent")
async def dota_recent():
    cached = cache_get(OPENDOTA_PRO)
    if cached:
        return JSONResponse({"fromCache": True, **cached})

    async with httpx.AsyncClient(timeout=15.0) as client:
        r = await client.get(OPENDOTA_PRO)
    if r.status_code != 200:
        raise HTTPException(status_code=502, detail=f"OpenDota upstream error {r.status_code}")

    rows = r.json()
    payload = {"count": len(rows), "items": normalize_pro(rows)}
    cache_set(OPENDOTA_PRO, payload, 30)
    return JSONResponse({"fromCache": False, **payload})

# Serve the frontend
app.mount("/", StaticFiles(directory="static", html=True), name="static")
