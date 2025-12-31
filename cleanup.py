import asyncio
from datetime import datetime, timezone, timedelta

import config
import database as db


def _parse_iso(s: str):
    if not s:
        return None
    try:
        return datetime.fromisoformat(s.replace("Z", "+00:00"))
    except Exception:
        return None


async def cleanup_loop():
    """
    Каждые 10 минут проверяем и удаляем точки старше TTL_HOURS.
    """
    ttl = timedelta(hours=int(config.TTL_HOURS))

    while True:
        try:
            now = datetime.now(timezone.utc)
            deleted = 0

            with db.get_db() as s:
                rows = s.query(db.Place).all()
                for r in rows:
                    ts = r.last_seen_at or r.created_at
                    dt = _parse_iso(ts)
                    if dt and (now - dt) > ttl:
                        s.delete(r)
                        deleted += 1

                if deleted:
                    db.commit_with_retry(s)

        except Exception:
            pass

        await asyncio.sleep(600)
