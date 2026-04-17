"""
build.py — merge event sources, regenerate aggregate CSVs, write HITL review files

Usage:
    python build.py
    python build.py --web raw/events_web.json --ra raw/events_ra.json

Outputs:
    data/all_data.csv                    DJ appearance counts, all stages
    data/basement_data.csv               DJ counts, Basement stage only
    data/studio_data.csv                 DJ counts, Studio stage only
    data/party_data.csv                  Recurring party/night counts
    review/normalization_review.csv      HITL: raw → normalized DJ names
    review/party_review.csv              HITL: raw → normalized party/event titles
    review/overlap_events.csv            Source overlap: event-level side-by-side
    review/overlap_djs.csv               Source overlap: DJ-level provenance tagging
"""

import argparse
import csv
import json
from collections import Counter
from datetime import datetime
from pathlib import Path

from normalize import normalize_djs, normalize_title

DEFAULT_WEB = Path(__file__).parent / "raw" / "events_web.json"
DEFAULT_RA = Path(__file__).parent / "raw" / "events_ra.json"
DATA_DIR = Path(__file__).parent / "data"
REVIEW_DIR = Path(__file__).parent / "review"
SC_CSV = DATA_DIR / "dj_soundcloud.csv"


def load_events(path: Path) -> list[dict]:
    if not path.exists():
        print(f"  WARNING: {path} not found, skipping")
        return []
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def load_soundcloud() -> set[str]:
    """Return the set of DJ names already in dj_soundcloud.csv (uppercased)."""
    if not SC_CSV.exists():
        return set()
    with open(SC_CSV, newline="", encoding="latin-1") as f:
        return {row["DJ"].strip().upper() for row in csv.DictReader(f) if row.get("DJ")}


def process_events(events: list[dict], source: str, known_djs: set[str]) -> tuple[list[dict], list[dict], list[dict]]:
    """
    Normalize titles and DJ names for a list of events.

    Returns:
        rows         [{date, event_title, stage, dj}]
        dj_review    [{raw_name, normalized_name, rule_applied, is_new_dj, event_date, stage, source}]
        party_review [{raw_title, normalized_title, rule_applied, event_date, source}]
    """
    rows = []
    dj_review = []
    party_review = []

    for event in events:
        date_str = event.get("event_detail_date", "")
        try:
            event_date = datetime.fromisoformat(date_str).date()
        except Exception:
            continue

        raw_title = event.get("event_detail_title", "")
        norm_title, title_rule = normalize_title(raw_title, source=source)

        party_review.append({
            "raw_title": raw_title,
            "normalized_title": norm_title if norm_title is not None else "(dropped)",
            "rule_applied": title_rule,
            "event_date": str(event_date),
            "source": source,
        })

        if norm_title is None:  # postponed/cancelled — skip entirely
            continue

        for stage_dict in event.get("event_detail_music", []):
            for stage, raw_djs in stage_dict.items():
                normalized = normalize_djs(raw_djs)
                for raw, norm, rule in normalized:
                    is_new = (norm is not None) and (norm.upper() not in known_djs)
                    dj_review.append({
                        "raw_name": raw,
                        "normalized_name": norm or "(dropped)",
                        "rule_applied": rule,
                        "is_new_dj": "YES" if is_new else "",
                        "event_date": str(event_date),
                        "stage": stage,
                        "source": source,
                    })
                    if norm:
                        rows.append({
                            "date": event_date,
                            "event_title": norm_title,
                            "stage": stage,
                            "dj": norm,
                        })

    return rows, dj_review, party_review


def write_dj_csv(path: Path, counter: Counter, soundcloud_ids: dict[str, str]):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["DJ", "Count", "Soundcloud_Link", "Soundcloud_User_ID"])
        for dj, count in counter.most_common():
            sc_id = soundcloud_ids.get(dj.upper(), "")
            sc_link = f"https://soundcloud.com/users/{sc_id}" if sc_id else ""
            writer.writerow([dj, count, sc_link, sc_id])


def load_soundcloud_ids() -> dict[str, str]:
    if not SC_CSV.exists():
        return {}
    with open(SC_CSV, newline="", encoding="latin-1") as f:
        return {
            row["DJ"].strip().upper(): row.get("Soundcloud_User_ID", "").strip()
            for row in csv.DictReader(f)
            if row.get("DJ")
        }


def write_review_csv(path: Path, rows: list[dict], fieldnames: list[str]):
    REVIEW_DIR.mkdir(parents=True, exist_ok=True)
    with open(path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def build_overlap_events(web_events: list[dict], ra_events: list[dict]) -> list[dict]:
    """
    Option 1: Event-level side-by-side comparison.
    One row per date that appears in both sources.
    """
    def events_by_date(events):
        by_date = {}
        for e in events:
            d = e.get("event_detail_date", "")[:10]
            by_date.setdefault(d, []).append(e)
        return by_date

    web_by_date = events_by_date(web_events)
    ra_by_date = events_by_date(ra_events)
    overlap_dates = sorted(set(web_by_date) & set(ra_by_date))

    rows = []
    for date in overlap_dates:
        for we in web_by_date[date]:
            web_djs = sorted({
                dj
                for sd in we.get("event_detail_music", [])
                for djs in sd.values()
                for dj in djs
            })
            for re in ra_by_date[date]:
                ra_djs = sorted({
                    dj
                    for sd in re.get("event_detail_music", [])
                    for djs in sd.values()
                    for dj in djs
                })
                web_set = {d.upper() for d in web_djs}
                ra_set = {d.upper() for d in ra_djs}
                if web_set == ra_set:
                    match_status = "djs_match"
                elif web_set & ra_set:
                    match_status = "djs_partial"
                else:
                    match_status = "djs_differ"
                if we.get("event_detail_title", "").upper() != re.get("event_detail_title", "").upper():
                    match_status += "+title_differ"
                rows.append({
                    "date": date,
                    "ra_title": re.get("event_detail_title", ""),
                    "ra_djs": ", ".join(ra_djs),
                    "web_title": we.get("event_detail_title", ""),
                    "web_djs": ", ".join(web_djs),
                    "match_status": match_status,
                })
    return rows


def build_overlap_djs(web_rows: list[dict], ra_rows: list[dict]) -> list[dict]:
    """
    Option 2: DJ-level provenance tagging.
    Every DJ appearance tagged as web_only, ra_only, or both — before dedup.
    """
    def keyed(rows, source):
        result = {}
        for r in rows:
            key = (str(r["date"]), r["stage"].upper(), r["dj"].upper())
            result[key] = {"date": r["date"], "stage": r["stage"], "dj": r["dj"], "source": source,
                           "event_title": r.get("event_title", "")}
        return result

    web_keyed = keyed(web_rows, "web")
    ra_keyed = keyed(ra_rows, "ra")
    all_keys = set(web_keyed) | set(ra_keyed)

    rows = []
    for key in sorted(all_keys):
        date, stage, dj = key
        in_web = key in web_keyed
        in_ra = key in ra_keyed
        source = "both" if (in_web and in_ra) else ("web_only" if in_web else "ra_only")
        base = web_keyed[key] if in_web else ra_keyed[key]
        rows.append({
            "date": base["date"],
            "stage": base["stage"],
            "dj": base["dj"],
            "event_title": base["event_title"],
            "source": source,
            "kept": "yes",  # all unique keys are kept after dedup
        })
    return rows


def main():
    parser = argparse.ArgumentParser(description="Build aggregate CSVs from event sources")
    parser.add_argument("--web", type=str, default=str(DEFAULT_WEB))
    parser.add_argument("--ra", type=str, default=str(DEFAULT_RA))
    args = parser.parse_args()

    print("Loading events...")
    web_events_all = load_events(Path(args.web))
    ra_events = load_events(Path(args.ra))

    # RA is authoritative for 2019-2021.
    # Web supplements RA for 2019-2021 dates RA didn't capture, and is used exclusively from 2022+.
    ra_dates = {e["event_detail_date"][:10] for e in ra_events}
    web_events = [
        e for e in web_events_all
        if e.get("event_detail_date", "")[:4] >= "2022"
        or e.get("event_detail_date", "")[:10] not in ra_dates
    ]
    web_supplement = [e for e in web_events if e.get("event_detail_date", "")[:4] < "2022"]
    print(f"  RA events  (2019-2021):          {len(ra_events)}")
    print(f"  Web events (2022+):              {len(web_events) - len(web_supplement)}")
    print(f"  Web events (2019-2021 supplement): {len(web_supplement)}  (dates RA missed)")

    known_djs = load_soundcloud()
    soundcloud_ids = load_soundcloud_ids()

    print("Processing...")
    web_rows, web_dj_review, web_party_review = process_events(web_events, "web", known_djs)
    ra_rows, ra_dj_review, ra_party_review = process_events(ra_events, "ra", known_djs)

    all_rows = web_rows + ra_rows
    all_dj_review = web_dj_review + ra_dj_review
    all_party_review = web_party_review + ra_party_review

    # Deduplicate rows by (date, stage, dj)
    seen = set()
    deduped = []
    for row in all_rows:
        key = (row["date"], row["stage"].upper(), row["dj"].upper())
        if key not in seen:
            seen.add(key)
            deduped.append(row)

    print(f"  Total DJ appearances (deduped): {len(deduped)}")

    # Build counters
    all_counter = Counter(r["dj"] for r in deduped)
    basement_counter = Counter(r["dj"] for r in deduped if r["stage"].lower() == "basement")
    studio_counter = Counter(r["dj"] for r in deduped if r["stage"].lower() == "studio")
    # Count unique nights per party (not DJ appearances)
    party_nights = {(r["event_title"], r["date"]): r["event_title"] for r in deduped if r["event_title"]}
    party_counter = Counter(party_nights.values())

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    write_dj_csv(DATA_DIR / "all_data.csv", all_counter, soundcloud_ids)
    write_dj_csv(DATA_DIR / "basement_data.csv", basement_counter, soundcloud_ids)
    write_dj_csv(DATA_DIR / "studio_data.csv", studio_counter, soundcloud_ids)

    with open(DATA_DIR / "party_data.csv", "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["event_title", "Count"])
        for title, count in party_counter.most_common():
            writer.writerow([title, count])

    print(f"  Wrote data/all_data.csv ({len(all_counter)} DJs)")
    print(f"  Wrote data/basement_data.csv ({len(basement_counter)} DJs)")
    print(f"  Wrote data/studio_data.csv ({len(studio_counter)} DJs)")
    print(f"  Wrote data/party_data.csv ({len(party_counter)} parties)")

    # Write HITL review files
    write_review_csv(
        REVIEW_DIR / "normalization_review.csv",
        all_dj_review,
        ["raw_name", "normalized_name", "rule_applied", "is_new_dj", "event_date", "stage", "source"],
    )
    write_review_csv(
        REVIEW_DIR / "party_review.csv",
        all_party_review,
        ["raw_title", "normalized_title", "rule_applied", "event_date", "source"],
    )
    print(f"  Wrote review/normalization_review.csv ({len(all_dj_review)} rows)")
    print(f"  Wrote review/party_review.csv ({len(all_party_review)} rows)")

    # Overlap reviews (uses raw event lists and pre-dedup rows)
    web_events_raw = load_events(Path(args.web))
    ra_events_raw = load_events(Path(args.ra))
    overlap_event_rows = build_overlap_events(web_events_raw, ra_events_raw)
    overlap_dj_rows = build_overlap_djs(web_rows, ra_rows)
    write_review_csv(
        REVIEW_DIR / "overlap_events.csv",
        overlap_event_rows,
        ["date", "ra_title", "ra_djs", "web_title", "web_djs", "match_status"],
    )
    write_review_csv(
        REVIEW_DIR / "overlap_djs.csv",
        overlap_dj_rows,
        ["date", "stage", "dj", "event_title", "source", "kept"],
    )
    print(f"  Wrote review/overlap_events.csv ({len(overlap_event_rows)} overlapping dates)")
    print(f"  Wrote review/overlap_djs.csv ({len(overlap_dj_rows)} DJ appearances tagged)")

    # Summarize
    new_dj_count = sum(1 for r in all_dj_review if r["is_new_dj"] == "YES")
    none_dj_count = sum(1 for r in all_dj_review if r["rule_applied"] == "none")
    none_party_count = sum(1 for r in all_party_review if r["rule_applied"] == "none" and r["normalized_title"] not in ("", "(dropped)"))

    print(f"\nReview summary:")
    print(f"  New DJs (not in dj_soundcloud.csv):  {new_dj_count}  ← add SoundCloud links for these")
    print(f"  DJ names untouched (rule=none):       {none_dj_count}  ← scan for mangled names")
    print(f"  Party titles untouched (rule=none):   {none_party_count}  ← scan for recurring parties needing a remap")


if __name__ == "__main__":
    main()
