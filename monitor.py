#!/usr/bin/env python3
import hashlib
import json
import os
import re
import sqlite3
import sys
from html import unescape
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

SS_URL = "https://www.ss.com/lv/real-estate/flats/riga/centre/hand_over/"
STATE_FILE = "state.json"
BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/154.0 Safari/537.36"
    ),
    "Accept-Language": "lv-LV,lv;q=0.9,en;q=0.8",
}

session = requests.Session()
session.headers.update(HEADERS)


def load_state():
    if not os.path.exists(STATE_FILE):
        return {"ids": [], "initialized": False}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"ids": [], "initialized": False}


def save_state(state):
    tmp = STATE_FILE + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2)
    os.replace(tmp, STATE_FILE)


def normalize_url(href):
    return urljoin(SS_URL, href.split("#", 1)[0])


def listing_id(url):
    # Typical SS.com listing URL ends in a short alphanumeric ID, e.g. /bklxo.html
    m = re.search(r"/([a-z0-9]+)\.html$", url.rstrip("/"), re.I)
    if m:
        return m.group(1).lower()
    return hashlib.sha256(url.encode()).hexdigest()[:20]


def clean(text):
    return re.sub(r"\s+", " ", unescape(text or "")).strip()


def parse_price(text):
    m = re.search(r"([\d\s,.]+)\s*€", text or "")
    return clean(m.group(1)).replace(" ", "") + " €" if m else clean(text)


def parse_page():
    r = session.get(SS_URL, timeout=30)
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    listings = []

    # SS.com currently renders listing rows as links to /msg/...html.
    seen = set()
    for a in soup.select('a[href*="/msg/"]'):
        href = a.get("href", "")
        url = normalize_url(href)
        if not re.search(r"/msg/[a-z0-9]+\.html$", url, re.I):
            continue

        lid = listing_id(url)
        if lid in seen:
            continue
        seen.add(lid)

        # The listing row is normally the nearest table row.
        row = a.find_parent("tr")
        if not row:
            continue

        cells = [clean(c.get_text(" ", strip=True)) for c in row.find_all(["td", "th"])]
        title = clean(a.get_text(" ", strip=True))

        # Keep only rows that look like actual listings.
        if len(cells) < 5:
            continue

        # Usually: date, title, street, rooms, area, floor, series, €/m2, price.
        # Extract fields defensively because SS.com may change markup.
        row_text = " | ".join(cells)
        street = ""
        rooms = ""
        area = ""
        floor = ""
        price_m2 = ""
        price = ""

        # Identify numeric columns by their current ordering.
        if len(cells) >= 9:
            street = cells[-7] if len(cells) >= 7 else ""
            rooms = cells[-6] if len(cells) >= 6 else ""
            area = cells[-5] if len(cells) >= 5 else ""
            floor = cells[-4] if len(cells) >= 4 else ""
            price_m2 = cells[-2] if len(cells) >= 2 else ""
            price = cells[-1] if cells else ""

        # More robust fallbacks.
        if not area:
            m = re.search(r"\b(\d+(?:[.,]\d+)?)\s*m²\b", row_text)
            area = m.group(1) + " m²" if m else ""
        if not rooms:
            m = re.search(r"\b([1-9])\b", row_text)
            rooms = m.group(1) if m else ""
        if not price:
            m = re.search(r"[\d\s,.]+\s*€/mēn\.", row_text)
            price = m.group(0) if m else ""
        if not price_m2:
            m = re.search(r"[\d\s,.]+\s*€(?:/m²)?", row_text)
            price_m2 = m.group(0) if m else ""

        listings.append({
            "id": lid,
            "url": url,
            "title": title,
            "street": street,
            "rooms": rooms,
            "area": area,
            "floor": floor,
            "price_m2": price_m2,
            "price": price,
            "row": row_text,
        })

    # SS.com sorts newest first. De-duplicate just in case.
    unique = {}
    for x in listings:
        unique[x["id"]] = x
    return list(unique.values())


def send_telegram(listing):
    text = (
        "🏠 <b>Jauns SS.com sludinājums</b>\n\n"
        f"<b>{escape_html(listing['title'])}</b>\n"
        f"📍 {escape_html(listing['street'])}\n"
        f"🚪 Istabas: {escape_html(listing['rooms'])}\n"
        f"📐 Platība: {escape_html(listing['area'])}\n"
        f"🏢 Stāvs: {escape_html(listing['floor'])}\n"
        f"💶 {escape_html(listing['price'])}"
    )
    if listing["price_m2"]:
        text += f"\n📊 {escape_html(listing['price_m2'])}"
    text += f"\n\n🔗 <a href=\"{listing['url']}\">Atvērt sludinājumu</a>"

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    r = session.post(
        url,
        data={
            "chat_id": CHAT_ID,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": False,
        },
        timeout=20,
    )
    r.raise_for_status()


def escape_html(s):
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def main():
    listings = parse_page()
    if not listings:
        raise RuntimeError("No listings parsed. SS.com markup may have changed.")

    state = load_state()
    known = set(state.get("ids", []))

    # First run seeds the current page and sends nothing.
    if not state.get("initialized", False):
        state["ids"] = [x["id"] for x in listings]
        state["initialized"] = True
        save_state(state)
        print(f"Initialized with {len(listings)} existing listings; no notifications sent.")
        return

    new = [x for x in listings if x["id"] not in known]

    # Update state before notifications so a failed Telegram call won't create
    # duplicate messages on every subsequent run. Failed notifications are
    # printed and can be recovered manually by removing the IDs from state.json.
    state["ids"] = list(dict.fromkeys(
        [x["id"] for x in listings] + state.get("ids", [])
    ))[:1000]
    save_state(state)

    for listing in reversed(new):
        try:
            send_telegram(listing)
            print("Sent:", listing["id"], listing["title"])
        except Exception as e:
            print("Telegram error:", listing["id"], e, file=sys.stderr)

    print(f"Checked {len(listings)} listings; {len(new)} new.")


if __name__ == "__main__":
    main()
