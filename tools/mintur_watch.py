# -*- coding: utf-8 -*-
"""Сторож сводок Минтуризма - сообщает о новой сводке, сам ничего не публикует.

Объявления (`notices.json`) меняются только после «да» Никиты по списку правок
(правило 13.09.2026). Поэтому задача GitHub Actions лишь замечает, что вышла
оперативная сводка новее даты в объявлениях, и заводит задачу (issue) в репозитории:
GitHub присылает о ней письмо. Правки готовит Claude, когда Никита попросит.

    python3 tools/mintur_watch.py   # печатает дату свежей сводки; с GH_TOKEN - заводит issue
"""
import html, json, os, re, subprocess, sys, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RSS = ("https://kamgov.ru/mintur/rss/rss/index?model=news%5CsearchModels%5CNewsSearch"
       "&NewsSearch%5Bonly_for_subordinate%5D=1&NewsSearch%5Bpublishing_news%5D=1"
       "&NewsSearch%5BgovIds%5D%5B0%5D=35&NewsSearch%5Bpublished%5D=1")


def latest_summary():
    req = urllib.request.Request(RSS, headers={"User-Agent": "Mozilla/5.0"})
    s = urllib.request.urlopen(req, timeout=60).read().decode("utf-8", "replace")
    best = None
    for it in re.findall(r"<item[\s>]([\s\S]*?)</item>", s):
        def g(k):
            m = re.search(r"<%s[^>]*>([\s\S]*?)</%s>" % (k, k), it)
            return html.unescape(re.sub(r"<!\[CDATA\[|\]\]>", "", m.group(1))).strip() if m else ""
        title, link = g("title"), g("link")
        if "сводк" not in title.lower():
            continue
        m = re.search(r"(\d{2})(\d{2})(20\d{2})", link) or re.search(r"(\d{2})\.(\d{2})\.(20\d{2})", title)
        if not m:
            continue
        date = "%s-%s-%s" % (m.group(3), m.group(2), m.group(1))
        if not best or date > best[0]:
            best = (date, title, link)
    return best


def main():
    best = latest_summary()
    if not best:
        sys.exit("в ленте нет оперативных сводок - проверьте адрес ленты")
    date, title, link = best
    with open(os.path.join(ROOT, "notices.json"), encoding="utf-8") as f:
        have = max(n["date"] for n in json.load(f)["items"])
    print("свежая сводка: %s (%s); в объявлениях: %s" % (date, link, have))
    if date <= have:
        print("новой сводки нет")
        return 0
    name = "Новая сводка Минтуризма от %s.%s.%s" % (date[8:], date[5:7], date[:4])
    if not os.environ.get("GH_TOKEN"):
        print("нужна задача: " + name)
        return 0
    found = subprocess.run(["gh", "issue", "list", "--state", "all", "--search", name, "--json", "title"],
                           capture_output=True, text=True, check=True).stdout
    if name in found:
        print("задача уже заведена")
        return 0
    body = ("Вышла %s - новее последней даты в объявлениях (%s).\n\n%s\n\n"
            "Объявления сами не меняются: попросите Claude подготовить список правок, "
            "после вашего «да» он их опубликует." % (title, have, link))
    subprocess.run(["gh", "issue", "create", "--title", name, "--body", body], check=True)
    print("заведена задача: " + name)
    return 0


if __name__ == "__main__":
    sys.exit(main())
