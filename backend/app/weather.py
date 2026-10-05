"""Live weather for Tampa.

OpenWeather (free tier: current weather + 5-day/3-hour forecast + map tiles) when an API key is
configured (Settings screen or OPENWEATHER_API_KEY env var); otherwise the keyless Open-Meteo API.
The key never reaches the browser — map tiles are proxied through /api/weather/tiles.
"""
import os
import time
from datetime import datetime, timezone

import httpx

from .data import TAMPA

CACHE_TTL = 600  # seconds
_cache: dict[str, tuple[float, dict]] = {}

WMO = {0: "Clear", 1: "Mainly clear", 2: "Partly cloudy", 3: "Overcast", 45: "Fog", 48: "Fog", 51: "Light drizzle",
       53: "Drizzle", 55: "Heavy drizzle", 61: "Light rain", 63: "Rain", 65: "Heavy rain", 80: "Rain showers",
       81: "Rain showers", 82: "Violent showers", 95: "Thunderstorm", 96: "Thunderstorm, hail", 99: "Thunderstorm, hail"}

TILE_LAYERS = {"precipitation_new", "wind_new", "clouds_new", "pressure_new", "temp_new"}


def env_key() -> str:
    return os.environ.get("OPENWEATHER_API_KEY", "").strip()


async def _openweather(key: str) -> dict:
    params = {"lat": TAMPA["lat"], "lon": TAMPA["lon"], "units": "imperial", "appid": key}
    async with httpx.AsyncClient(timeout=10) as c:
        cur = await c.get("https://api.openweathermap.org/data/2.5/weather", params=params)
        if cur.status_code != 200:
            raise RuntimeError(f"OpenWeather returned {cur.status_code}: {cur.json().get('message', '')}")
        fc = await c.get("https://api.openweathermap.org/data/2.5/forecast", params=params)
    d = cur.json()
    hourly = []
    if fc.status_code == 200:
        for i in fc.json()["list"][:16]:
            hourly.append({"time": datetime.fromtimestamp(i["dt"], tz=timezone.utc).isoformat(),
                           "gust_mph": i["wind"].get("gust", i["wind"]["speed"]), "rain_chance": round(i.get("pop", 0) * 100)})
    return {"source": "OpenWeather", "temp_f": d["main"]["temp"], "humidity": d["main"]["humidity"],
            "pressure_mb": d["main"]["pressure"], "wind_mph": d["wind"]["speed"],
            "gust_mph": d["wind"].get("gust", d["wind"]["speed"]),
            "description": d["weather"][0]["description"].capitalize(), "hourly": hourly}


async def _open_meteo() -> dict:
    params = {"latitude": TAMPA["lat"], "longitude": TAMPA["lon"],
              "current": "temperature_2m,relative_humidity_2m,pressure_msl,wind_speed_10m,wind_gusts_10m,weather_code",
              "hourly": "wind_gusts_10m,precipitation_probability", "wind_speed_unit": "mph",
              "temperature_unit": "fahrenheit", "forecast_days": 3, "timezone": "UTC"}
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get("https://api.open-meteo.com/v1/forecast", params=params)
        r.raise_for_status()
    d = r.json()
    cur = d["current"]
    now = datetime.now(timezone.utc)
    hourly = []
    for i, t in enumerate(d["hourly"]["time"]):
        ts = datetime.fromisoformat(t).replace(tzinfo=timezone.utc)
        if (ts - now).total_seconds() >= -3600:
            hourly.append({"time": ts.isoformat(), "gust_mph": d["hourly"]["wind_gusts_10m"][i],
                           "rain_chance": d["hourly"]["precipitation_probability"][i]})
    return {"source": "Open-Meteo", "temp_f": cur["temperature_2m"], "humidity": cur["relative_humidity_2m"],
            "pressure_mb": cur["pressure_msl"], "wind_mph": cur["wind_speed_10m"], "gust_mph": cur["wind_gusts_10m"],
            "description": WMO.get(cur["weather_code"], "—"), "hourly": hourly[::3][:16]}


async def current(key: str, force: bool = False) -> dict:
    cache_key = "ow" if key else "om"
    hit = _cache.get(cache_key)
    if hit and not force and time.time() - hit[0] < CACHE_TTL:
        return hit[1]
    key_error = None
    try:
        data = await (_openweather(key) if key else _open_meteo())
    except Exception as e:  # network down, bad key, etc. — surface it, don't crash the UI
        if not key:
            return {"source": "Open-Meteo", "error": _msg(e), "key_error": None}
        # A bad or not-yet-active OpenWeather key shouldn't take weather off the screen: fall back to keyless Open-Meteo.
        key_error = _msg(e)
        try:
            data = await _open_meteo()
        except Exception as e2:
            return {"source": "OpenWeather", "error": f"{key_error}; Open-Meteo fallback also failed: {_msg(e2)}", "key_error": key_error}
    data["updated_at"] = datetime.now(timezone.utc).isoformat()
    data["error"] = None
    data["key_error"] = key_error
    _cache[cache_key] = (time.time(), data)
    return data


def _msg(e: Exception) -> str:
    return str(e) or e.__class__.__name__


async def tile(key: str, layer: str, z: int, x: int, y: int) -> bytes:
    async with httpx.AsyncClient(timeout=10) as c:
        r = await c.get(f"https://tile.openweathermap.org/map/{layer}/{z}/{x}/{y}.png", params={"appid": key})
        r.raise_for_status()
        return r.content


def clear_cache() -> None:
    _cache.clear()
