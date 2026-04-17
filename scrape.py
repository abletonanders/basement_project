"""
scrape.py — scrape all past events from basementny.net

Usage:
    python scrape.py                        # scrape all events
    python scrape.py --since 2025-01-01     # skip events before this date
    python scrape.py --out raw/events_web.json

Output: raw/events_web.json (JSON array, one object per event)
Schema:
    {
        "event_detail_date": "2025-11-01T22:30:00",
        "event_detail_title": "BOUND BLACKOUT",
        "event_detail_music": [
            {"Basement": ["SALOME", "KATIE REX"]},
            {"Studio": ["DJ MINX", "MANU MIRAN"]}
        ]
    }
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time
from datetime import datetime
from pathlib import Path

from playwright.async_api import async_playwright
from bs4 import BeautifulSoup
from dateutil.parser import parse as parse_date_str

BASE_URL = "https://basementny.net"
DEFAULT_OUT = Path(__file__).parent / "raw" / "events_web.json"


async def get_event_links(page) -> list[str]:
    await page.goto(f"{BASE_URL}/past")
    previous_height = None
    while True:
        current_height = await page.evaluate("document.body.scrollHeight")
        if previous_height == current_height:
            break
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
        await asyncio.sleep(1)
        previous_height = current_height

    links = await page.query_selector_all("a[href*='/events/']")
    hrefs = [await link.get_attribute("href") for link in links]
    # deduplicate while preserving order
    seen = set()
    unique = []
    for h in hrefs:
        if h and h not in seen:
            seen.add(h)
            unique.append(h)
    return unique


async def get_event_detail(page, relative_url: str) -> dict | None:
    url = BASE_URL + relative_url
    await page.goto(url)
    try:
        await page.wait_for_selector("div.event-detail__date", timeout=9000)
    except Exception:
        print(f"  WARNING: timeout waiting for date on {url}")
        return None

    html = await page.content()
    soup = BeautifulSoup(html, "html.parser")

    date_div = soup.find("div", class_="event-detail__date")
    if not date_div:
        return None
    try:
        event_date = parse_date_str(date_div.get_text(strip=True).title())
    except Exception:
        return None

    title_h1 = soup.find("h1", class_="event-detail__title")
    if not title_h1:
        return None
    title_div = title_h1.find("div", recursive=False)
    event_title = title_div.get_text(strip=True) if title_div else ""

    event_detail_music = []
    stage_divs = title_h1.find_all("div", class_=lambda c: c and "event-detail__title-stages" in c)
    for stage in stage_divs:
        container = stage.find("p") if stage.find("p") else stage
        headline_div = container.find("div", class_="event-detail__headline")
        if not headline_div:
            continue
        stage_name = headline_div.get_text(strip=True)
        dj_list = []
        for dj in container.find_all("div"):
            if dj == headline_div:
                continue
            if "event-detail__headline" in dj.get("class", []):
                continue
            # Skip wrapper divs — they concatenate their children's text into a smushed string.
            # Only collect leaf divs (no div children) which hold actual DJ names.
            if dj.find("div"):
                continue
            text = dj.get_text(strip=True)
            if not text or text.lower() == "null":
                continue
            dj_list.append(text)
        if stage_name and dj_list:
            event_detail_music.append({stage_name: dj_list})

    return {
        "event_detail_date": event_date.isoformat(),
        "event_detail_title": event_title,
        "event_detail_music": event_detail_music,
    }


async def scrape(since: datetime | None, out_path: Path):
    out_path.parent.mkdir(parents=True, exist_ok=True)
    progress_path = out_path.with_suffix(".progress.jsonl")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        print("Fetching event links from basementny.net/past ...")
        links = await get_event_links(page)
        print(f"Found {len(links)} event links")
        print(f"Progress file: {progress_path}")
        print(f"  Monitor with:  tail -f {progress_path}")
        print(f"  Count so far:  wc -l {progress_path}\n")

        results = []
        with open(progress_path, "w", encoding="utf-8") as prog:
            for i, link in enumerate(links, 1):
                detail = await get_event_detail(page, link)
                if detail is None:
                    print(f"  [{i}/{len(links)}] SKIP (parse error): {link}")
                    continue

                event_date = datetime.fromisoformat(detail["event_detail_date"])
                if since and event_date < since:
                    print(f"  [{i}/{len(links)}] SKIP (before --since): {event_date.date()}")
                    continue

                print(f"  [{i}/{len(links)}] OK: {event_date.date()} — {detail['event_detail_title'] or '(no title)'}")
                results.append(detail)
                prog.write(json.dumps(detail, ensure_ascii=False) + "\n")
                prog.flush()
                time.sleep(2)

        await browser.close()

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    progress_path.unlink(missing_ok=True)
    print(f"\nSaved {len(results)} events to {out_path}")

    # Write versioned snapshot — never overwritten, permanent record of this scrape run
    snapshot_dir = out_path.parent / "snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    snapshot_path = snapshot_dir / f"events_web_{datetime.now().strftime('%Y%m%d')}.json"
    import shutil
    shutil.copy(out_path, snapshot_path)
    print(f"Snapshot saved to {snapshot_path}")


def main():
    parser = argparse.ArgumentParser(description="Scrape basementny.net past events")
    parser.add_argument("--since", type=str, default=None, help="Skip events before YYYY-MM-DD")
    parser.add_argument("--out", type=str, default=str(DEFAULT_OUT), help="Output JSON path")
    args = parser.parse_args()

    since = datetime.fromisoformat(args.since) if args.since else None
    asyncio.run(scrape(since, Path(args.out)))


if __name__ == "__main__":
    main()
