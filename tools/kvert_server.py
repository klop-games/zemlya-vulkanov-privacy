# -*- coding: utf-8 -*-
"""Подготовить бюллетень KVERT для сверки редактором.

Обычный запуск показывает дату, полный список кодов и SHA-256 предложения.
После независимой сверки редактор передаёт --approve SHA256 через workflow_dispatch.
"""
import argparse
import datetime
import hashlib
import html
import json
import os
import re
import sys
import urllib.request

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
# Меньше - значит, страница KVERT поменяла вид: не публикуем, задача падает и пишет письмо
MIN_VOLCANOES = 20


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def text_of(url):
    # С серверов GitHub kvert.febras.net отвечает через раз (20.11.2026 один запуск
    # прошёл, следующий ушёл в тайм-аут) - три попытки с паузой
    import time
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    opener = urllib.request.build_opener(NoRedirect())
    for attempt in range(3):
        try:
            with opener.open(req, timeout=75) as response:
                raw_bytes = response.read(2_000_001)
            if len(raw_bytes) > 2_000_000:
                raise ValueError("Страница KVERT слишком велика")
            raw = raw_bytes.decode("utf-8", "replace")
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
        sys.exit("на странице нет недельного прогноза - проверьте kvert.febras.net")
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


def arguments():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--справка", action="help", help="показать эту справку")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--показать", action="store_true", help="только показать предложение")
    mode.add_argument("--approve", metavar="SHA256", help="отпечаток независимо проверенного бюллетеня")
    args = parser.parse_args()
    if args.approve is not None and not re.fullmatch("[0-9a-f]{64}", args.approve):
        parser.error("ожидается SHA-256 из 64 строчных шестнадцатеричных знаков")
    return args


def reviewed_update(old, vol, approval):
    date, pairs = parse(text_of(URL))
    if not date:
        sys.exit("Дата прогноза не разобрана")
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
    if unknown:
        sys.exit("Есть несопоставленные вулканы. Нужна проверка таблицы названий.")
    if len(items) < MIN_VOLCANOES or len({item["id"] for item in items}) != len(items):
        sys.exit("Неполный список вулканов или повтор идентификатора")
    if old.get("forecastDate") and old["forecastDate"] > date:
        sys.exit("На странице прогноз старее последнего опубликованного")
    if old.get("items") == items and old.get("forecastDate") == date:
        print("Прогноз от %s совпадает с текущим" % date)
        return None

    # Отпечаток связывает решение редактора с датой и каждым публикуемым кодом.
    bulletin = {"forecastDate": date, "items": items}
    payload = json.dumps(bulletin, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()
    digest = hashlib.sha256(payload).hexdigest()
    print("Кандидат от %s. Сверьте дату и каждую строку по независимому официальному источнику." % date)
    for item in items:
        print("  %s (%s): %s" % (item["nameRu"], item["id"], item["code"]))
    print("SHA-256: " + digest)
    if approval is None:
        print("Только просмотр. Последний проверенный бюллетень сохранён.")
        return None
    if approval != digest:
        sys.exit("Отпечаток отличается от подтверждённого. Получите и проверьте новый бюллетень.")
    return dict(old, **bulletin, count=len(items), version=old.get("version", 0) + 1)


def main():
    args = arguments()
    new = reviewed_update(load("activity.json"), load("tools/volcano_names.json")["items"], args.approve)
    if new is None:
        return 0
    save("activity.json", new)
    man = load("updates.json")
    man["files"]["activity"] = new["version"]
    save("updates.json", man)
    print("записано: activity.json версия %d" % new["version"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
