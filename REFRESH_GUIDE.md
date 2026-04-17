# Data Refresh Guide

How to re-execute the full pipeline, in order, with data fidelity checks at each step.

---

## One-time setup

```bash
pip install playwright beautifulsoup4 python-dateutil requests googlesearch-python pandas
playwright install chromium
```

---

## Execution order

### 1. Back up existing raw data

```bash
cp raw/events_web.json raw/events_web.json.bak
```

`raw/basement_text.txt` is a manual RA scrape from pages that may no longer exist — it is **irreplaceable**. Never overwrite it.

### 2. Parse the RA text file

```bash
python parse_ra.py
```

Fast and deterministic — no network calls. Produces `raw/events_ra.json`. Run this first to establish a stable baseline before any scraping.

### 3. Scrape basementny.net

```bash
python scrape.py
```

Takes ~30–60 minutes (2-second delay per event, 150+ events expected). Produces `raw/events_web.json`.

If the scrape crashes mid-run, restart with `--since` set to the last successfully scraped date:

```bash
python scrape.py --since 2024-06-01
```

Then manually concatenate the two partial outputs before running build.

**Spot-check before proceeding:**
- Count events — does the number look right for 2022–present?
- Verify the earliest date is around May 2022 (BASEMENT's reopening)
- Check a few known events (WRECKED, BOUND BLACKOUT) for correct stage assignments
- Look for events with empty `event_detail_music` — signals a page structure the scraper couldn't parse

### 4. Build aggregate CSVs

```bash
python build.py
```

Merges both sources, deduplicates, writes:
- `data/all_data.csv`
- `data/basement_data.csv`
- `data/studio_data.csv`
- `data/party_data.csv`
- `review/normalization_review.csv`

### 5. Review DJ names and party titles (HITL)

`build.py` writes two review files. Open both in Excel/Numbers after each run.

**`review/normalization_review.csv`** — DJ name audit

| Column | What to look for |
|--------|-----------------|
| `rule_applied = none` | Names the normalizer left untouched — highest risk for suffixes, typos, broken splits |
| `is_new_dj = YES` | DJs not yet in `dj_soundcloud.csv` — flag for SoundCloud lookup |
| `rule_applied = b2b_split` or `slash_split` | Verify the split produced two real names, not fragments |

Common problems: suffixes still attached ("OPEN TO CLOSE", "ALL NIGHT LONG", "LIVE"), ampersands `&` not split, two spellings of the same DJ (e.g., "SHAUN J WRIGHT" vs "SHAUN J. WRIGHT").

**`review/party_review.csv`** — event title audit

| Column | What to look for |
|--------|-----------------|
| `rule_applied = none` | Titles the normalizer left untouched — check if any are recurring parties that need a canonical name added |
| `rule_applied = suppressed` | Month-named events (DECEMBER 13, etc.) — verify these are genuinely one-offs, not named parties |
| `normalized_title = (dropped)` | Postponed/cancelled events excluded from counts — confirm this is correct |

Fix any issues by editing `normalize_rules.json`:
- DJ spelling corrections → `remaps`
- DJ names to drop → `skip`
- DJ names that expand to multiple → `expand`
- Party names shared across both sources → `title_remaps_both`
- Party names specific to web (post-2022) → `title_remaps_web`
- Party names specific to RA (2019–2021) → `title_remaps_ra`

Then re-run:

```bash
python build.py
```

Repeat until no issues remain. No re-scraping needed.

### 6. Update hardcoded stats in index.html

The three stat numbers are hardcoded and **will not update automatically**. Run this to get the correct values:

```bash
python -c "
import csv, json
djs = set(r['DJ'] for r in csv.DictReader(open('data/all_data.csv')))
parties = list(csv.DictReader(open('data/party_data.csv')))
web = json.load(open('raw/events_web.json'))
ra = json.load(open('raw/events_ra.json'))
print(f'Artists:     {len(djs)}')
print(f'Club nights: {len(web) + len(ra)}')
print(f'Parties:     {len(parties)}')
"
```

Then edit the three `.stat-number` spans in `output/index.html` manually.

Also update the title and year badge if needed (`7 Years`, `2019 - 2026`).

### 7. Test locally

Open `output/index.html` directly in a browser. Verify:
- DJ tables load for all three tabs (All Stages / Basement / Studio)
- Clicking a DJ name loads a SoundCloud embed
- Year label and stats look correct

### 8. Commit and push

Per standard git hygiene: `git status`, stage specific files, review the diff, confirm before committing. Push to `main` — GitHub Actions deploys automatically.

---

## Data fidelity risks

| Risk | Signal | Mitigation |
|------|--------|------------|
| basementny.net HTML changes | Events with empty `event_detail_music` | Spot-check step 3 |
| Scroll-to-load misses early events | Earliest date in `events_web.json` is later than May 2022 | Compare against known reopening date |
| Same DJ counted twice under variant spellings | Suspiciously high count for a name, or two similar names in `all_data.csv` | `normalization_review.csv` cross-reference |
| Partial scrape crash | `events_web.json` missing or truncated | Use `.bak` from step 1; restart with `--since` |
| Wrong SoundCloud profile | Broken or mismatched embed on the site | Review `dj_soundcloud.csv` additions before committing |
| Stale hardcoded stats | Site shows old numbers after refresh | Always run the snippet in step 6 |
| RA file encoding issues | `parse_ra.py` errors on the `̸` delimiter | File must be read as UTF-8; check for BOM if errors occur |

---

## Incremental refresh (future runs)

Once the 2022–2026 backfill is complete, future refreshes only need new events:

```bash
python scrape.py --since 2026-04-01   # adjust to last known event date
python build.py
```

Then repeat steps 5–8.
