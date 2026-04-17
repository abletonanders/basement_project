"""
parse_ra.py — parse the RA.co text scrape into events_ra.json

Usage:
    python parse_ra.py
    python parse_ra.py --in raw/basement_text.txt --out raw/events_ra.json

Input:  raw/basement_text.txt  (scraped RA listing, blocks delimited by "BASEMENT")
Output: raw/events_ra.json     (JSON array, same schema as events_web.json)

Note: RA data has no stage information — all DJs are assigned to stage "Basement".
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

from dateutil.parser import parse as parse_date_str

from normalize import normalize_djs, normalize_title

DEFAULT_IN = Path(__file__).parent / "raw" / "basement_text.txt"
DEFAULT_OUT = Path(__file__).parent / "raw" / "events_ra.json"


def split_by_basement(text: str) -> list[str]:
    blocks = []
    current = []
    for line in text.splitlines(keepends=True):
        if line.strip() == "BASEMENT":
            if current:
                blocks.append("".join(current).rstrip())
                current = []
        else:
            current.append(line)
    if current:
        blocks.append("".join(current).rstrip())
    return blocks


def parse_block(block: str) -> dict | None:
    lines = block.splitlines()

    date_pattern = re.compile(r"^(Mon|Tue|Wed|Thu|Fri|Sat|Sun),\s+\d{1,2}\s+\w+\s+\d{4}$")
    date_line = None
    for line in lines:
        if date_pattern.match(line.strip()):
            date_line = line.strip()
            break
    if not date_line:
        return None

    # DJ list: line immediately above "New York City"
    ny_index = next((i for i, l in enumerate(lines) if l.strip() == "New York City"), None)
    if ny_index is None:
        return None
    j = ny_index - 1
    while j >= 0 and not lines[j].strip():
        j -= 1
    dj_line = lines[j].strip() if j >= 0 else None

    # Event title: last non-empty line before the "̸" delimiter
    delim_index = next((i for i, l in enumerate(lines) if l.strip() == "̸"), None)
    if delim_index is None:
        return None
    j = delim_index - 1
    while j >= 0 and not lines[j].strip():
        j -= 1
    title = lines[j].strip() if j >= 0 else ""

    return {"date_line": date_line, "dj_line": dj_line, "title": title}


def main():
    parser = argparse.ArgumentParser(description="Parse RA text scrape into events_ra.json")
    parser.add_argument("--in", dest="input", type=str, default=str(DEFAULT_IN))
    parser.add_argument("--out", type=str, default=str(DEFAULT_OUT))
    args = parser.parse_args()

    text = Path(args.input).read_text(encoding="utf-8")
    blocks = split_by_basement(text)[:-1]  # last block is trailing content

    results = []
    skipped = 0
    for block in blocks:
        parsed = parse_block(block)
        if not parsed:
            skipped += 1
            continue

        title, _ = normalize_title(parsed["title"], source="ra")
        if title is None:  # postponed/cancelled
            skipped += 1
            continue

        try:
            event_date = parse_date_str(parsed["date_line"])
        except Exception:
            skipped += 1
            continue

        raw_djs = [name.strip() for name in parsed["dj_line"].split(",") if name.strip()]
        normalized = normalize_djs(raw_djs)
        dj_list = [norm for _, norm, _ in normalized if norm is not None]

        results.append({
            "event_detail_date": event_date.isoformat(),
            "event_detail_title": title,
            "event_detail_music": [{"Basement": dj_list}],
        })

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)

    print(f"Parsed {len(results)} events ({skipped} skipped) → {args.out}")


if __name__ == "__main__":
    main()
