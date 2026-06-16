#!/usr/bin/env python3
"""PTT MacShop 爬蟲 - 搜尋 Mac Mini M4 販售文章並通知 Telegram Bot"""

import json
import os
import re
import sys
from pathlib import Path

import requests
from bs4 import BeautifulSoup

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
STATE_FILE = Path("seen_posts.json")
PTT_BASE = "https://www.ptt.cc"
BOARD = "MacShop"
# 關鍵字：標題需同時包含 mac mini 和 m4（不分大小寫）
KEYWORDS = [["mac mini", "m4"]]
# 只通知販售文章（標題以 [售] 開頭）
SELL_TAG = "[售]"
SESSION = requests.Session()
SESSION.cookies.set("over18", "1")
HEADERS = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}


def load_seen() -> set:
    if STATE_FILE.exists():
        return set(json.loads(STATE_FILE.read_text()))
    return set()


def save_seen(seen: set):
    STATE_FILE.write_text(json.dumps(sorted(seen), ensure_ascii=False, indent=2))


def fetch_index_pages(pages: int = 3) -> list[dict]:
    """抓最新幾頁的文章列表"""
    posts = []
    url = f"{PTT_BASE}/bbs/{BOARD}/index.html"
    for _ in range(pages):
        r = SESSION.get(url, headers=HEADERS, timeout=15)
        r.raise_for_status()
        soup = BeautifulSoup(r.text, "html.parser")
        for div in soup.select("div.r-ent"):
            title_a = div.select_one("div.title a")
            if not title_a:
                continue
            title = title_a.get_text(strip=True)
            href = title_a["href"]
            post_id = href.split("/")[-1].replace(".html", "")
            date_div = div.select_one("div.date")
            date = date_div.get_text(strip=True) if date_div else ""
            author_div = div.select_one("div.author")
            author = author_div.get_text(strip=True) if author_div else ""
            posts.append({
                "id": post_id,
                "title": title,
                "url": PTT_BASE + href,
                "date": date,
                "author": author,
            })
        # 找上一頁連結
        prev = soup.select_one("a.btn.wide", string=re.compile("上頁|‹"))
        if prev:
            url = PTT_BASE + prev["href"]
        else:
            break
    return posts


def match_keywords(title: str) -> bool:
    t = title.lower()
    for group in KEYWORDS:
        if all(kw.lower() in t for kw in group):
            return True
    return False


def is_sell_post(title: str) -> bool:
    return title.startswith(SELL_TAG)


def send_telegram(text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    r = requests.post(url, json=payload, timeout=10)
    r.raise_for_status()


def main():
    seen = load_seen()
    posts = fetch_index_pages(pages=3)
    new_posts = [
        p for p in posts
        if p["id"] not in seen
        and is_sell_post(p["title"])
        and match_keywords(p["title"])
    ]

    if new_posts:
        for p in new_posts:
            msg = (
                f"🖥️ <b>PTT MacShop 發現新販售！</b>\n\n"
                f"📌 <b>{p['title']}</b>\n"
                f"👤 作者：{p['author']}　📅 {p['date']}\n"
                f"🔗 <a href=\"{p['url']}\">{p['url']}</a>"
            )
            send_telegram(msg)
            print(f"通知已發送：{p['title']}")
        seen.update(p["id"] for p in new_posts)
        save_seen(seen)
    else:
        print("沒有新的 Mac Mini M4 販售文章")

    # 限制 seen 最多保留 2000 筆，避免無限成長
    if len(seen) > 2000:
        seen = set(sorted(seen)[-2000:])
        save_seen(seen)


if __name__ == "__main__":
    main()
