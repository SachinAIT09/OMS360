import asyncio

from app import weather

OPEN_METEO = {"source": "Open-Meteo", "temp_f": 77.0, "wind_mph": 3.0}


def _run(monkeypatch, openweather, open_meteo, key="bad-key"):
    weather.clear_cache()
    monkeypatch.setattr(weather, "_openweather", openweather)
    monkeypatch.setattr(weather, "_open_meteo", open_meteo)
    return asyncio.run(weather.current(key, force=True))


async def _fail(*_):
    raise RuntimeError("OpenWeather returned 401: Invalid API key")


async def _meteo():
    return dict(OPEN_METEO)


def test_bad_openweather_key_falls_back_to_open_meteo(monkeypatch):
    wx = _run(monkeypatch, _fail, _meteo)
    assert wx["source"] == "Open-Meteo" and wx["temp_f"] == 77.0
    assert wx["error"] is None and "401" in wx["key_error"]


def test_error_when_fallback_also_fails(monkeypatch):
    async def down():
        raise RuntimeError("network down")
    wx = _run(monkeypatch, _fail, down)
    assert "401" in wx["error"] and "network down" in wx["error"]


def test_no_key_uses_open_meteo_without_key_error(monkeypatch):
    wx = _run(monkeypatch, _fail, _meteo, key="")
    assert wx["source"] == "Open-Meteo" and wx["error"] is None and wx["key_error"] is None
