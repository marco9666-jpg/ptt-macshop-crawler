#!/usr/bin/env python3
"""PTT MacShop 爬蟲 - 搜尋 Mac Mini M4 販售文章並通知 Telegram Bot"""

import json
import os
import time
import random
from pathlib import Path

import requests
from bs4 import BeautifulSoup

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
TELEGRAM_CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
STATE_FILE = Path("seen_posts.json")
PTT_BASE = "https://www.ptt.cc"
BOARD = "MacShop"
KEYWORDS = [["mac mini", "m4"]]
SELL_TAGS = ["[售]", "[販售]"]

SESSION = requests.Session()
SESSION.cookies.set("over18", "1")
# 完整模擬 Chrome 127 on macOS
SESSION.headers.update({
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/127.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-TW,zh;q=0.9,en-US;q=0.8,en;q=0.7",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Cache-Control": "max-age=0",
})


def load_seen() -> set:
    if STATE_FILE.exists():
        return set(json.loads(STATE_FILE.read_text()))
    return set()


def save_seen(seen: set):
    STATE_FILE.write_text(json.dumps(sorted(seen), ensure_ascii=False, indent=2))


def fetch_with_retry(url: str, max_retries: int = 3) -> requests.Response:
    for attempt in range(max_retries):
        try:
            time.sleep(random.uniform(1.5, 3.0))  # 避免被限速
            r = SESSION.get(url, timeout=20)
            r.raise_for_status()
            return r
        except Exception as e:
            if attempt == max_retries - 1:
                raise
            wait = (2 ** attempt) + random.uniform(0, 1)
            print(f"重試 {attempt + 1}/{max_retries}，等待 {wait:.1f}s，錯誤：{e}")
            time.sleep(wait)


def fetch_index_pages(pages: int = 3) -> list[dict]:
    """抓最新幾頁的文章列表（使用 JSON API）"""
    posts = []

    # 先取 HTML 版確認最新 index 編號
    r = fetch_with_retry(f"{PTT_BASE}/bbs/{BOARD}/index.html")
    soup = BeautifulSoup(r.text, "html.parser")

    # 找最新 index 編號（從「上頁」連結取得 index N，則最新是 N+1）
    prev_link = None
    for a in soup.select("a.btn.wide"):
        if "上頁" in a.get_text():
            prev_link = a["href"]
            break

    if prev_link:
        # /bbs/MacShop/index1234.html → 1234+1 是最新
        import re
        m = re.search(r"index(\d+)", prev_link)
        latest = int(m.group(1)) + 1 if m else None
    else:
        latest = None

    # 解析第一頁
    for div in soup.select("div.r-ent"):
        post = _parse_post(div)
        if post:
            posts.append(post)

    # 繼續往前抓幾頁
    if latest:
        for i in range(pages - 1):
            idx = latest - 1 - i
            if idx < 1:
                break
            try:
                r2 = fetch_with_retry(f"{PTT_BASE}/bbs/{BOARD}/index{idx}.html")
                soup2 = BeautifulSoup(r2.text, "html.parser")
                for div in soup2.select("div.r-ent"):
                    post = _parse_post(div)
                    if post:
                        posts.append(post)
            except Exception as e:
                print(f"抓第 {idx} 頁失敗：{e}")

    return posts


def _parse_post(div) -> dict | None:
    title_a = div.select_one("div.title a")
    if not title_a:
        return None
    title = title_a.get_text(strip=True)
    href = title_a["href"]
    post_id = href.split("/")[-1].replace(".html", "")
    date_div = div.select_one("div.date")
    date = date_div.get_text(strip=True) if date_div else ""
    author_div = div.select_one("div.author")
    author = author_div.get_text(strip=True) if author_div else ""
    return {
        "id": post_id,
        "title": title,
        "url": PTT_BASE + href,
        "date": date,
        "author": author,
    }


def match_keywords(title: str) -> bool:
    t = title.lower()
    return any(all(kw.lower() in t for kw in group) for group in KEYWORDS)


def is_sell_post(title: str) -> bool:
    return any(title.startswith(tag) for tag in SELL_TAGS)


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
                f"🖥️ <b>PTT MacShop 發現 Mac Mini M4！</b>\n\n"
                f"📌 <b>{p['title']}</b>\n"
                f"👤 作者：{p['author']}　📅 {p['date']}\n"
                f"🔗 <a href=\"{p['url']}\">{p['url']}</a>"
            )
            send_telegram(msg)
            print(f"通知已發送：{p['title']}")
        seen.update(p["id"] for p in new_posts)
        save_seen(seen)
    else:
        print(f"沒有新的 Mac Mini M4 販售文章（共掃描 {len(posts)} 篇）")

    if len(seen) > 2000:
        seen = set(sorted(seen)[-2000:])
        save_seen(seen)


if __name__ == "__main__":
    main()
