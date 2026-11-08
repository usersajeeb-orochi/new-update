"""Where the links go: a text file and/or a Telegram message."""
import json
import os
import urllib.parse

from .sources import _base
from .util import http_post


def group_lines(groups):
    lines = []
    for g in groups:
        main = g[0]
        when = main["published"].strftime("%d %b %H:%M") if main.get("published") else ""
        tag = "" if main.get("resolved", True) else "  (Google link: publisher address could not be read)"
        lines.append(f"{main['title']}\n{main['source'] or main['domain']}  {when}{tag}\n{main['link']}")
        for o in g[1:]:
            lines.append(f"   also: {o['source'] or o['domain']}  {o['link']}")
        lines.append("")
    return lines


def write_txt(path, title, groups, plain_links=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(f"{title}\n{'=' * len(title)}\n\n")
        if plain_links:
            for g in groups:
                for it in g:
                    f.write(it["link"] + "\n")
        else:
            f.write("\n".join(group_lines(groups)))
    return path


def send_telegram(settings, title, groups, log=print):
    tg = settings.get("telegram") or {}
    if not tg.get("token") or not tg.get("chat_id"):
        log("    Telegram skipped (token or chat id missing in Settings)")
        return 0
    base = _base(settings, "telegram")
    chunks, cur = [], title + "\n\n"
    for g in groups:
        main = g[0]
        block = f"{main['title']}\n{main['link']}\n\n"
        if len(cur) + len(block) > 3800:
            chunks.append(cur); cur = ""
        cur += block
    chunks.append(cur)
    n = 0
    for c in chunks:
        try:
            http_post(f"{base}/bot{tg['token']}/sendMessage", urllib.parse.urlencode({"chat_id": tg["chat_id"], "text": c, "disable_web_page_preview": "true"}).encode(),
                      {"Content-Type": "application/x-www-form-urlencoded"})
            n += 1
        except Exception as e:
            log(f"    Telegram failed: {e}")
            break
    log(f"    Telegram: {n} message(s) sent")
    return n
