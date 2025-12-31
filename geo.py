import math
import requests
import config

UA = {"User-Agent": "dp-map-local/1.0"}
_city_center_cache = None

def get_city_center():
    global _city_center_cache
    if _city_center_cache is not None:
        return _city_center_cache

    r = requests.get(
        "https://nominatim.openstreetmap.org/search",
        params={"q": config.CITY_NAME, "format": "json", "limit": 1},
        headers=UA,
        timeout=20,
    )
    data = r.json() or []
    if not data:
        _city_center_cache = (55.7558, 37.6173)
        return _city_center_cache

    _city_center_cache = (float(data[0]["lat"]), float(data[0]["lon"]))
    return _city_center_cache

def haversine_km(lat1, lon1, lat2, lon2):
    R = 6371.0
    p1 = math.radians(lat1)
    p2 = math.radians(lat2)
    d1 = math.radians(lat2 - lat1)
    d2 = math.radians(lon2 - lon1)
    a = math.sin(d1 / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(d2 / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))

def _viewbox_around_city(lat, lon, km):
    # грубо: 1 градус широты ~= 111км, долгота зависит от широты
    dlat = km / 111.0
    dlon = km / (111.0 * max(0.2, math.cos(math.radians(lat))))
    left = lon - dlon
    right = lon + dlon
    top = lat + dlat
    bottom = lat - dlat
    return f"{left},{top},{right},{bottom}"  # minLon,maxLat,maxLon,minLat

def geocode_near_city(name: str):
    name = (name or "").strip()
    if not name:
        return None, None

    city_lat, city_lon = get_city_center()
    max_km = float(config.MAX_DISTANCE_KM)

    viewbox = _viewbox_around_city(city_lat, city_lon, max_km)

    # Пробуем разные запросы (с подсказкой региона и без)
    queries = [
        f"{name}, {config.GEO_REGION_HINT}",
        f"{name}, {config.CITY_NAME}",
        name,
    ]

    best = None
    best_dist = None

    for q in queries:
        try:
            r = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={
                    "q": q,
                    "format": "json",
                    "limit": 10,
                    "viewbox": viewbox,
                    "bounded": 1,       # 🔥 строго внутри viewbox
                    "addressdetails": 1
                },
                headers=UA,
                timeout=20,
            )
            r.raise_for_status()
            arr = r.json() or []
        except Exception:
            arr = []

        for it in arr:
            lat = float(it["lat"])
            lon = float(it["lon"])
            d = haversine_km(city_lat, city_lon, lat, lon)
            if d <= max_km:
                if best is None or d < best_dist:
                    best = (lat, lon)
                    best_dist = d

        if best is not None:
            break

    # Если вообще не нашли — пробуем "администрация города" как fallback,
    # если в названии есть признаки, что человек писал про админку/стоянку.
    if best is None and any(w in name.lower() for w in ["администра", "мэр", "совет"]):
        try:
            r = requests.get(
                "https://nominatim.openstreetmap.org/search",
                params={
                    "q": f"Администрация {config.CITY_NAME}",
                    "format": "json",
                    "limit": 5,
                    "viewbox": viewbox,
                    "bounded": 1,
                },
                headers=UA,
                timeout=20,
            )
            arr = r.json() or []
            if arr:
                best = (float(arr[0]["lat"]), float(arr[0]["lon"]))
        except Exception:
            pass

    if best is None:
        return None, None
    return best[0], best[1]
