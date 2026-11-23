# -*- coding: utf-8 -*-
"""Коды KVERT на сервере GitHub — без Mac и без Claude (решение Никиты 20.11.2026, Д2 аудита).

Задача GitHub Actions в `klop-games/zemlya-vulkanov-privacy` запускает этот скрипт раз в день.
Он забирает недельный прогноз KVERT, сопоставляет названия с вулканами приложения
(`tools/volcano_names.json`) и, если прогноз изменился, пишет `activity.json`
с новой версией и поднимает её в `updates.json`. Коммит делает сама задача.

Разбор страницы — тот же, что в `ios/Kamchatka/tools/kvert.py` проекта; правишь
одно — поправь и другое. Названий не угадываем: что не сошлось, печатается отдельно.

    python3 tools/kvert_server.py            # обновить файлы в корне репозитория
    python3 tools/kvert_server.py --показать # только показать
"""
import datetime, html, json, os, re, sys, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
URL = "http://kvert.febras.net/progn/index"
UA = "ZemlyaVulkanov-app-data-check/1.1"
COLORS = {"ЗЕЛЁНЫЙ": "green", "ЗЕЛЕНЫЙ": "green", "ЖЁЛТЫЙ": "yellow", "ЖЕЛТЫЙ": "yellow",
          "ОРАНЖЕВЫЙ": "orange", "КРАСНЫЙ": "red", "НЕ ПРИСВОЕН": "unassigned"}
ALIASES = {
    "КЛЮЧЕВСКОЙ": "Ключевская сопка",
    "КОРЯКСКИЙ": "Корякская сопка",
    "АВАЧИНСКИЙ": "Авачинская сопка",
    "ПЛОСКИЙ ТОЛБАЧИК": "Толбачик",
    "ИЧИНСКИЙ": "Ичинская сопка",
    "КАРЫМСКИЙ": "Карымская сопка",
    "КРОНОЦКИЙ": "Кроноцкая сопка",
    "ДИКИЙ ГРЕБЕНЬ": "gvp-300022",
}
# Меньше — значит, страница KVERT поменяла вид: не публикуем, задача падает и пишет письмо
MIN_VOLCANOES = 20


def text_of(url):
    # С серверов GitHub kvert.febras.net отвечает через раз (20.11.2026 один запуск
    # прошёл, следующий ушёл в тайм-аут) — три попытки с паузой
    import time
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(3):
        try:
            raw = urllib.request.urlopen(req, timeout=90).read().decode("utf-8", "replace")
            break
        except OSError as e:
            if attempt == 2:
                raise
            print("KVERT не ответил (%s), повтор через минуту" % e)
            time.sleep(60)
    raw = re.sub(r"(?s)<script.*?</script>", " ", raw)
    raw = re.sub(r"(?s)<style.*?</style>", " ", raw)
    t = html.unescape(re.sub(r"\s+", " ", re.sub("<[^>]+>", "|", raw)))
    return re.sub(r"\|{2,}", "|", t)


def parse(t):
    i = t.find("KVERT-ПРОГНОЗ ДЛЯ АВИАЦИИ")
    if i < 0:
        sys.exit("на странице нет недельного прогноза — проверьте kvert.febras.net")
    m = re.search(r"([A-Za-z]+) (\d{1,2}), (\d{4})", t[i:i + 300])
    months = {"January": 1, "February": 2, "March": 3, "April": 4, "May": 5, "June": 6,
              "July": 7, "August": 8, "September": 9, "October": 10, "November": 11, "December": 12}
    date = (datetime.date(int(m.group(3)), months[m.group(1)], int(m.group(2))).isoformat()
            if m and m.group(1) in months else None)
    j = t.find("КАМЧАТКА", i)
    k = t.find("КУРИЛЫ", j)
    block = t[j:k if k > 0 else j + 4000]
    pairs = []
    for names, color in re.findall(r"([^|]+?):\s*\|(" + "|".join(COLORS) + r")\|", block):
        for n in names.split(","):
            n = n.strip(" |")
            if n and n.upper() == n:
                pairs.append((n, COLORS[color]))
    return date, pairs


def load(name):
    with open(os.path.join(ROOT, name), encoding="utf-8") as f:
        return json.load(f)


def save(name, data):
    with open(os.path.join(ROOT, name), "w", encoding="utf-8") as f:
        f.write(json.dumps(data, ensure_ascii=False, indent=1) + "\n")


def main():
    show = "--показать" in sys.argv
    date, pairs = parse(text_of(URL))
    if not date:
        sys.exit("дата прогноза не разобрана — формат страницы изменился")
    vol = load("tools/volcano_names.json")["items"]
    by_name = {v["nameRu"].strip().lower(): v for v in reversed(vol)}
    items, unknown = [], []
    for name, color in pairs:
        want = ALIASES.get(name, name)
        v = (next((x for x in vol if x["id"] == want), None) if want.startswith("gvp-")
             else by_name.get(want.strip().lower()))
        if not v:
            unknown.append(name)
            continue
        items.append({"gvp": v["gvpNumber"], "id": v["id"], "nameRu": v["nameRu"], "code": color})
    items.sort(key=lambda x: x["id"])
    print("прогноз от %s: разобрано %d вулканов" % (date, len(items)))
    for c in ("red", "orange", "yellow"):
        named = [i["nameRu"] for i in items if i["code"] == c]
        if named:
            print("  %-7s %s" % (c, ", ".join(named)))
    if unknown:
        print("  не сопоставлено (%d): %s" % (len(unknown), ", ".join(unknown)))
    if len(items) < MIN_VOLCANOES:
        sys.exit("разобрано меньше %d вулканов — не публикую" % MIN_VOLCANOES)

    old = load("activity.json")
    if old.get("items") == items and old.get("forecastDate") == date:
        print("прогноз не изменился")
        return 0
    if old.get("forecastDate") and old["forecastDate"] > date:
        sys.exit("на странице прогноз старее опубликованного (%s < %s) — не публикую" % (date, old["forecastDate"]))
    new = dict(old)
    new.update({"forecastDate": date, "count": len(items), "items": items,
                "version": old.get("version", 0) + 1})
    if show:
        print("опубликовал бы версию %d" % new["version"])
        return 0
    save("activity.json", new)
    man = load("updates.json")
    man["files"]["activity"] = new["version"]
    save("updates.json", man)
    print("записано: activity.json версия %d" % new["version"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
