import asyncio
from datetime import datetime, timezone

from aiogram import Bot, Dispatcher
from aiogram.types import Message
from aiogram.filters import CommandStart

import config
import database as db
from geo import geocode_near_city
from ai_places import analyze_event


def utc_iso():
    return datetime.now(timezone.utc).isoformat()


def build_queries(objects, areas):
    """
    Генерируем варианты запросов (от более точных к более общим).
    """
    queries = []
    for obj in objects:
        obj = (obj or "").strip()
        if not obj:
            continue

        # сначала: obj + area
        for area in areas:
            area = (area or "").strip()
            if area:
                queries.append(f"{obj}, {area}, {config.GEO_REGION_HINT}")
                queries.append(f"{obj}, {area}")

        # потом: obj + регион / obj
        queries.append(f"{obj}, {config.GEO_REGION_HINT}")
        queries.append(obj)

    # убираем дубликаты
    seen = set()
    out = []
    for q in queries:
        k = q.lower()
        if k not in seen:
            seen.add(k)
            out.append(q)
    return out


async def main():
    print("=== BOT START ===")
    print("If bot reads nothing in group -> BotFather /setprivacy -> Disable")

    if not config.TELEGRAM_BOT_TOKEN:
        raise RuntimeError("В config.py вставь TELEGRAM_BOT_TOKEN")

    bot = Bot(config.TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()

    @dp.message(CommandStart())
    async def start(m: Message):
        await m.answer("Бот запущен. Пиши места/ориентиры — я поставлю точку.")

    @dp.message()
    async def handle_message(m: Message):
        if not m.text:
            return

        text = m.text.strip()
        print("\nTEXT:", text)

        data = analyze_event(text)
        print("[AI]:", data)

        objects = data.get("objects", []) or []
        areas = data.get("areas", []) or []

        # 🔥 ключ: если objects пусто, но areas есть — считаем areas объектами
        if not objects and areas:
            objects = areas.copy()

        # 🔥 если всё равно пусто — берём первое слово как объект (на крайний случай)
        if not objects:
            first = text.split()[0] if text.split() else ""
            if first:
                objects = [first]

        if not objects:
            print("[SKIP] nothing to geocode")
            return

        queries = build_queries(objects, areas)
        print("[QUERIES]:", queries)

        lat = lon = None
        used_query = None

        for q in queries:
            lat, lon = geocode_near_city(q)
            if lat is not None and lon is not None:
                used_query = q
                break

        if lat is None:
            print("[SKIP] nothing geocoded")
            return

        print("[FOUND]:", used_query, lat, lon)

        with db.get_db() as s:
            now = utc_iso()

            # сохраняем то, что реально использовали
            name_for_db = used_query

            existing = s.query(db.Place).filter(
                db.Place.name.ilike(f"%{name_for_db}%")
            ).first()

            if existing:
                existing.lat = lat
                existing.lon = lon
                existing.last_seen_at = now
                existing.confirmations = int((existing.confirmations or 1) + 1)
                db.commit_with_retry(s)
                print("[DB] updated:", existing.name)
            else:
                p = db.Place(
                    name=name_for_db,
                    lat=lat,
                    lon=lon,
                    created_at=now,
                    last_seen_at=now,
                    confirmations=1,
                    bearing=None,
                )
                s.add(p)
                db.commit_with_retry(s)
                print("[DB] inserted:", name_for_db)

    await dp.start_polling(bot)


if __name__ == "__main__":
    db.init_db()
    asyncio.run(main())
