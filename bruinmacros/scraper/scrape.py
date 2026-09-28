"""
BruinMacros menu scraper.

Downloads today's (and tomorrow's) menus from each UCLA Dining location page,
looks up nutrition for every item (caching it, since recipe numbers don't
change), and writes:

  data/menus/YYYY-MM-DD.json   one file per day, read by the website
  data/index.json              which dates are available
  data/recipes.json            nutrition cache, keyed by recipe number

Run:  python scraper/scrape.py            (today + tomorrow)
      python scraper/scrape.py --date 2026-10-01
      python scraper/scrape.py --debug    (also saves raw pages to debug/)

Be polite: this runs at most hourly, waits between requests, only fetches
nutrition for items it hasn't seen, and identifies itself with a contact
address (set the CONTACT_EMAIL environment variable).
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import re
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlparse
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup

BASE = "https://dining.ucla.edu"
TZ = ZoneInfo("America/Los_Angeles")
ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
MENUS = DATA / "menus"
DEBUG = ROOT / "debug"

# Display name, page slug. Order here is the order shown on the site.
LOCATIONS = [
    ("De Neve", "de-neve-dining"),
    ("Bruin Plate", "bruin-plate"),
    ("Epicuria at Covel", "epicuria-at-covel"),
    ("Feast at Rieber", "spice-kitchen"),
    ("Sproul", "sproul-dining"),
    ("Bruin Café", "bruin-cafe"),
    ("Rendezvous", "rendezvous"),
    ("The Study at Hedrick", "the-study-at-hedrick"),
    ("The Drey", "the-drey"),
    ("Epicuria at Ackerman", "epicuria-at-ackerman"),
    ("Café 1919", "cafe-1919"),
]

MEALS = {
    "BREAKFAST": "Breakfast",
    "BRUNCH": "Brunch",
    "LUNCH": "Lunch",
    "DINNER": "Dinner",
    "LATE NIGHT": "Late Night",
    "EXTENDED DINNER": "Extended Dinner",
    "ALL DAY": "All Day",
}
# Headings that are not stations even though they sit at station level.
NOT_STATIONS = {"icon legend", "today's dining hours", "allergen information", "nutrition"}
# Menu entries that are labels, not food.
SKIP_ITEMS = re.compile(r"^(theme of the day|brunch|lunch|dinner)$", re.I)
# Tags from the item page worth showing on the site.
KEEP_TAGS = re.compile(r"^(vegan|vegetarian|halal|contains .+|low.carbon.footprint|high.carbon.footprint)$", re.I)

KEEP_MENU_DAYS = 14
RECIPE_MAX_AGE_DAYS = 30
REQUEST_GAP_S = 1.0
MAX_TRAY_OZ = 20  # a single serving bigger than this is almost always a whole tray

session = requests.Session()
session.headers["User-Agent"] = (
    "BruinMacros menu bot (unofficial student project; contact: "
    + os.environ.get("CONTACT_EMAIL", "not-set")
    + ")"
)
_last_request = 0.0


def fetch(url: str) -> str | None:
    """GET a page politely, with a couple of retries. Returns HTML or None."""
    global _last_request
    for attempt in range(3):
        wait = REQUEST_GAP_S - (time.time() - _last_request)
        if wait > 0:
            time.sleep(wait)
        _last_request = time.time()
        try:
            r = session.get(url, timeout=30)
            if r.status_code == 200:
                return r.text
            print(f"  {r.status_code} for {url}", file=sys.stderr)
            if r.status_code in (403, 404):
                return None
        except requests.RequestException as e:
            print(f"  error for {url}: {e}", file=sys.stderr)
        time.sleep(3 * (attempt + 1))
    return None


def long_date(d: dt.date) -> str:
    return f"{d.strftime('%B')} {d.day}, {d.year}"  # "September 28, 2026"


def parse_menu(html: str, day: dt.date) -> list[dict] | None:
    """
    Turn a location page into [{name: meal, stations: [{name, items: [{id, name}]}]}].
    Returns None when the page isn't showing `day` (the site sometimes serves
    a stale day) so we never publish the wrong menu.
    """
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)
    if long_date(day) not in text:
        return None

    meals: list[dict] = []
    meal = station = None
    pending_name = None

    for el in soup.find_all(["h2", "h3", "a"]):
        if el.name == "h2":
            label = el.get_text(" ", strip=True)
            key = label.upper()
            if key in MEALS:
                meal = {"name": MEALS[key], "stations": []}
                meals.append(meal)
                station = None
            elif meal is not None and label.lower() not in NOT_STATIONS:
                station = {"name": label, "items": []}
                meal["stations"].append(station)
            pending_name = None
        elif el.name == "h3":
            pending_name = el.get_text(" ", strip=True)
        elif el.name == "a" and pending_name and station is not None:
            href = el.get("href") or ""
            if "menu-item" not in href:
                continue
            rid = parse_qs(urlparse(href).query).get("recipe", [None])[0]
            if rid and rid.isdigit() and not SKIP_ITEMS.match(pending_name):
                if all(it["id"] != rid for it in station["items"]):
                    station["items"].append({"id": rid, "name": pending_name})
            pending_name = None

    # Drop empty stations and meals (closed periods).
    for m in meals:
        m["stations"] = [s for s in m["stations"] if s["items"]]
    return [m for m in meals if m["stations"]]


NUM = r"([\d.]+)"


def parse_item(html: str) -> dict:
    """Read the nutrition label on a menu-item page."""
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(" ", strip=True)

    def grab(pattern: str) -> float | None:
        m = re.search(pattern, text, re.I)
        return float(m.group(1)) if m else None

    name_el = soup.find("h1") or soup.find("h2")
    serving = re.search(r"Serving Size:?\s*([\d.]+\s*[a-zA-Z]+)", text)
    info = {
        "name": name_el.get_text(" ", strip=True) if name_el else "",
        "serving": serving.group(1).replace(" ", "") if serving else "",
        "cal": grab(r"Calories:?\s*" + NUM),
        "f": grab(r"Total Fat\s*" + NUM + r"\s*g"),
        "c": grab(r"Total Carbohydrate\s*" + NUM + r"\s*g"),
        "p": grab(r"Protein\s*" + NUM + r"\s*g"),
    }
    tags = [li.get_text(" ", strip=True) for li in soup.find_all("li")]
    info["tags"] = [t for t in tags if KEEP_TAGS.match(t)][:8]

    oz = re.match(r"([\d.]+)oz", info["serving"] or "")
    too_big = bool(oz and float(oz.group(1)) > MAX_TRAY_OZ)
    if not info["cal"] or too_big:
        info.update(cal=0, p=0, c=0, f=0, nodata=True)
    else:
        for k in ("cal", "p", "c", "f"):
            info[k] = round(info[k] or 0, 2)
    return info


def load_json(path: Path, default):
    try:
        return json.loads(path.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=1, sort_keys=False) + "\n")


def scrape_day(day: dt.date, recipes: dict, debug: bool) -> dict:
    iso = day.isoformat()
    previous = load_json(MENUS / f"{iso}.json", {"locations": []})
    prev_by_name = {l["name"]: l for l in previous.get("locations", [])}
    today = dt.datetime.now(TZ).date().isoformat()

    locations = []
    for name, slug in LOCATIONS:
        url = f"{BASE}/{slug}/?date={iso}"
        print(f"{iso} {name}")
        html = fetch(url)
        if html and debug:
            save_json(DEBUG / f"{iso}-{slug}.json", {"url": url, "html": html})
        meals = parse_menu(html, day) if html else None
        if meals is None:
            # Page failed or showed another day: keep what we had, if anything.
            if name in prev_by_name:
                print("  kept previous menu (page unavailable or stale)")
                locations.append(prev_by_name[name])
            else:
                print("  skipped (no menu for this date)")
            continue
        if not meals:
            print("  closed")
            continue
        locations.append({"name": name, "url": f"{BASE}/{slug}/", "meals": meals})

    # Nutrition for anything new (or stale in the cache).
    cutoff = (dt.date.today() - dt.timedelta(days=RECIPE_MAX_AGE_DAYS)).isoformat()
    needed = {
        it["id"]
        for loc in locations
        for m in loc["meals"]
        for s in m["stations"]
        for it in s["items"]
        if it["id"] not in recipes or recipes[it["id"]].get("fetched", "") < cutoff
    }
    print(f"{iso}: {len(needed)} items need nutrition")
    for rid in sorted(needed):
        html = fetch(f"{BASE}/menu-item/?recipe={rid}")
        if not html:
            continue
        info = parse_item(html)
        info["fetched"] = today
        recipes[rid] = info

    # Fill in nutrition on every item.
    for loc in locations:
        for m in loc["meals"]:
            for s in m["stations"]:
                for it in s["items"]:
                    r = recipes.get(it["id"])
                    if not r:
                        it.update(serving="", cal=0, p=0, c=0, f=0, nodata=True)
                        continue
                    for k in ("serving", "cal", "p", "c", "f", "tags"):
                        if k in r:
                            it[k] = r[k]
                    if r.get("nodata"):
                        it["nodata"] = True
                    r["seen"] = today

    return {
        "date": iso,
        "updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "source": BASE,
        "locations": locations,
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", help="YYYY-MM-DD (default: today and tomorrow in Los Angeles)")
    ap.add_argument("--debug", action="store_true", help="save raw pages to debug/")
    args = ap.parse_args()

    today = dt.datetime.now(TZ).date()
    days = [dt.date.fromisoformat(args.date)] if args.date else [today, today + dt.timedelta(days=1)]

    recipes = load_json(DATA / "recipes.json", {})
    for day in days:
        menu = scrape_day(day, recipes, args.debug)
        if menu["locations"]:
            save_json(MENUS / f"{day.isoformat()}.json", menu)
        n = sum(len(s["items"]) for l in menu["locations"] for m in l["meals"] for s in m["stations"])
        print(f"{day}: {len(menu['locations'])} locations, {n} items")
        if day == today and n == 0:
            # Shows up as a yellow warning on the Actions run.
            print("::warning::No menu items found for today. The dining site may have changed its layout; check the raw-pages artifact.")

    # Prune: old menus, and cache entries not seen in a long time.
    oldest = (today - dt.timedelta(days=KEEP_MENU_DAYS)).isoformat()
    for f in MENUS.glob("*.json"):
        if f.stem < oldest:
            f.unlink()
    stale = (today - dt.timedelta(days=90)).isoformat()
    recipes = {k: v for k, v in recipes.items() if v.get("seen", v.get("fetched", "")) >= stale}
    save_json(DATA / "recipes.json", recipes)

    dates = sorted(f.stem for f in MENUS.glob("*.json"))
    save_json(DATA / "index.json", {"dates": dates, "updated": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")})
    return 0


if __name__ == "__main__":
    sys.exit(main())
