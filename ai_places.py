import json
import re
import config

# слова, которые часто встречаются, но не являются названием места
STOP_WORDS = {
    "у", "в", "во", "на", "к", "от", "до", "за", "под", "над",
    "около", "возле", "рядом", "рядомс", "рядом-с", "рядом_с",
    "со", "с", "по", "через", "после", "перед",
    "там", "тут", "здесь", "сегодня", "вчера", "сейчас",
    "стоит", "стоят", "стоял", "стояли",
    "едет", "едут", "поехал", "поехали", "движется", "движ",
    "чисто", "нет", "нету", "пусто", "пустая", "пустой",
    "машина", "тачка", "авто"
}

# простые паттерны, чтобы выделять "район/местность" после предлогов
AREA_AFTER_PREP = re.compile(
    r"\b(?:в|во|на|у|около|возле|рядом(?:\s+с)?)\s+([A-Za-zА-Яа-яЁё0-9\-]{2,})",
    re.IGNORECASE
)

WORD_RE = re.compile(r"[A-Za-zА-Яа-яЁё0-9\-]{2,}")

def _clean_token(t: str) -> str:
    return t.strip().strip(",.!?:;\"'()[]{}").strip()

def _heuristic_extract(text: str) -> dict:
    """
    Надёжный fallback: всегда возвращает хотя бы objects или areas,
    если в тексте есть хоть одно нормальное слово.
    """
    text = (text or "").strip()
    if not text:
        return {"objects": [], "areas": []}

    low = text.lower()

    # 1) area: достаём то, что идёт после "в/у/около/..."
    areas = []
    for m in AREA_AFTER_PREP.finditer(low):
        a = _clean_token(m.group(1))
        if a and a not in STOP_WORDS:
            areas.append(a)

    # 2) tokens: все слова
    tokens = []
    for m in WORD_RE.finditer(low):
        tok = _clean_token(m.group(0))
        if not tok:
            continue
        if tok in STOP_WORDS:
            continue
        tokens.append(tok)

    # если после вычистки ничего не осталось — попробуем хотя бы первое “сырое” слово
    if not tokens:
        parts = [p for p in re.split(r"\s+", low) if p]
        if parts:
            tok = _clean_token(parts[0])
            if tok:
                tokens = [tok]

    # 3) objects:
    # если есть явные tokens — считаем их объектами (первое слово самое важное)
    objects = []
    for t in tokens:
        if t not in areas:
            objects.append(t)

    # ограничим
    return {
        "objects": objects[:3],
        "areas": areas[:3],
    }

def analyze_event(text: str) -> dict:
    """
    Возвращает:
      {"objects":[...], "areas":[...]}
    Всегда старается вернуть кандидаты. Если AI пустой — fallback эвристика.
    """
    text = (text or "").strip()
    if not text:
        return {"objects": [], "areas": []}

    # если нет ключа — только эвристика
    if not config.OPENAI_API_KEY:
        return _heuristic_extract(text)

    # 1) пробуем AI
    try:
        from openai import OpenAI
        client = OpenAI(api_key=config.OPENAI_API_KEY)

        prompt = f"""
Из сообщения выдели кандидаты для геокодинга.

Верни СТРОГО JSON:
{{
  "objects": ["что искать на карте (магазин/кафе/ориентир/населённый пункт)"],
  "areas": ["уточнение местности (район/деревня/сокращение)"]
}}

ПРАВИЛА:
- Если фраза короткая типа "электричка стоят" — objects должен содержать "электричка".
- Если "у балково" — areas должен содержать "балково" (можно и в objects тоже, если считаешь).
- Если есть сокращения (бг, пущ, серп) — оставь как есть, не разворачивай.
- Лучше добавить кандидат, чем вернуть пусто.

Сообщение: {text}
"""
        resp = client.chat.completions.create(
            model=getattr(config, "OPENAI_MODEL", "gpt-4o-mini"),
            messages=[{"role": "user", "content": prompt}],
            temperature=0.1,
        )

        raw = (resp.choices[0].message.content or "").strip()
        raw = raw.replace("```json", "").replace("```", "").strip()
        data = json.loads(raw)

        if isinstance(data, dict):
            objects = data.get("objects") or []
            areas = data.get("areas") or []
            # нормализация
            objects = [_clean_token(str(x)) for x in objects if isinstance(x, (str, int, float))]
            areas = [_clean_token(str(x)) for x in areas if isinstance(x, (str, int, float))]
            objects = [x for x in objects if x and x.lower() not in STOP_WORDS]
            areas = [x for x in areas if x and x.lower() not in STOP_WORDS]

            # 2) если AI вернул пусто — fallback
            if not objects and not areas:
                return _heuristic_extract(text)

            return {"objects": objects[:3], "areas": areas[:3]}
    except Exception as e:
        print("[AI ERROR]", e)

    # 3) если AI упал — fallback
    return _heuristic_extract(text)
