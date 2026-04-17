# CLAUDE.md — Basement Project

## What This Is

A stats dashboard for BASEMENT NYC, a Bushwick techno club. Tracks DJs, recurring party nights, and stages across the club's full run (May 2019 – present). Live at basementstats.com (Netlify) and abletonanders.github.io/basement_project (GitHub Pages).

## Data Sources

| Source | Coverage | File |
|--------|----------|------|
| RA.co text scrape | May 2019 – Nov 2021 (pre-COVID closure) | `raw/basement_text.txt` |
| basementny.net web scrape | May 2022 – present (post-reopening) | `raw/events_web.json` |

RA is authoritative for 2019–2021. Web is used exclusively from 2022 onward, plus 4 web-only dates from late 2021 that RA didn't capture. The two sources are otherwise non-overlapping.

`raw/basement_text.txt` is **irreplaceable** — a manual scrape of RA pages that may no longer exist. Never overwrite it.

## Pipeline Scripts

Run in this order:

```bash
python3 parse_ra.py            # parse RA text file → raw/events_ra.json
python3 scrape.py              # scrape basementny.net → raw/events_web.json  (~45 min)
python3 build.py               # merge + aggregate → data/*.csv + review/*.csv
```

For incremental updates (next year refresh):
```bash
python3 scrape.py --since 2026-04-17   # adjust to last known scraped date
python3 build.py
```

## File Layout

```
basement_project/
├── CLAUDE.md                        ← this file
├── REFRESH_GUIDE.md                 ← step-by-step operational runbook
├── netlify.toml                     ← tells Netlify to serve from output/
├── normalize.py                     ← DJ + title normalization logic
├── normalize_rules.json             ← human-editable remap/skip/expand rules
├── scrape.py                        ← web scraper (basementny.net)
├── parse_ra.py                      ← RA text file parser
├── build.py                         ← aggregation + CSV generation
├── Basement_Project.ipynb           ← original notebook (reference only)
├── raw/
│   ├── basement_text.txt            ← raw RA scrape (DO NOT MODIFY)
│   ├── events_web.json              ← canonical web scrape output
│   ├── events_ra.json               ← canonical RA parse output
│   └── events_web.json.bak          ← backup before each re-scrape
├── data/
│   ├── all_data.csv                 ← DJ counts, all stages
│   ├── basement_data.csv            ← DJ counts, Basement stage only
│   ├── studio_data.csv              ← DJ counts, Studio stage only
│   ├── party_data.csv               ← recurring night counts (unique nights, not DJ rows)
│   ├── dj_by_year.csv               ← per-DJ appearance counts by year (for bar chart)
│   └── dj_soundcloud.csv            ← DJ → SoundCloud user ID mapping
├── review/                          ← HITL audit files (gitignored)
│   ├── normalization_review.csv     ← raw → normalized DJ names, with rule applied
│   ├── party_review.csv             ← raw → normalized party titles
│   ├── dj_corrections.json          ← deduplicated DJ names sorted by count (with counts)
│   ├── dj_corrections_no_counts.json← same, clean keys
│   ├── party_corrections.json       ← deduplicated party titles sorted by count
│   └── overlap_events.csv           ← dates appearing in both RA and web sources
└── output/
    ├── index.html                   ← the website
    ├── basementpic.jpeg
    └── CNAME                        ← basementstats.com custom domain for GitHub Pages
```

## Stage Assignment

Stage (Basement vs Studio) comes directly from basementny.net's HTML — no inference. Each event page has `div.event-detail__title-stages` containers, with `div.event-detail__headline` naming the stage and leaf `<div>` children listing DJs.

**Critical scraper detail**: the scraper uses `dj.find("div")` to skip wrapper divs and only collect leaf divs. Without this, wrapper divs produce smushed concatenations like `StudioRON LIKE HELLRYAN SMITH`. If smushed strings reappear in `normalization_review.csv`, the website HTML structure may have changed and the scraper needs re-examination.

RA data (2019–2021) has no stage info — all DJs hardcoded to `Basement`. The Studio room opened in 2022. For pre-2022 events, the website renders a Studio stage div but with no DJs — filtered via `skip` in `normalize_rules.json`.

## DJ Name Normalization

`normalize.py` applies these steps in order:
1. Strip Unicode zero-width chars
2. **Studio/Basement prefix stripping**: `StudioXXX` → strip prefix, re-queue remainder
3. **B2B split**: `"FJAAK B2B UMFANG"` → `["FJAAK", "UMFANG"]`
4. **Slash split**: `"DVS1 / VOLVOX"` → `["DVS1", "VOLVOX"]`
5. **Performance suffix stripping**: ` LIVE`, ` (DJ SET)`, ` PRESENTS ...`
6. **NE/RE/A merge**: fragments → `["NE/RE/A"]`
7. **Uppercase**
8. **Manual rules** from `normalize_rules.json`: `remaps`, `skip`, `expand`

## HITL Review Workflow

After `build.py` runs, review these files in Excel/Numbers:

- `review/dj_corrections.json` — all normalized DJ names sorted by count. Fill in `correction` value if wrong, leave blank if fine.
- `review/party_corrections.json` — all normalized party titles sorted by count. Same process.
- `review/normalization_review.csv` — full audit log. Filter `is_new_dj = YES` for SoundCloud candidates; `rule_applied = none` for untouched names.

Fix by editing `normalize_rules.json`, re-run `build.py`. No re-scraping needed.

## SoundCloud IDs

`data/dj_soundcloud.csv` maps DJ names to SoundCloud user IDs. To add new DJs:

**Automated lookup does NOT work reliably.** Google rate-limits immediately. DuckDuckGo rate-limits after ~2 searches. Slug guessing (`soundcloud.com/{dj-name-slugified}`) returns wrong profiles for common names.

**The only reliable approach:** manual lookup. Generate a list of priority DJs (5+ appearances missing IDs from `review/normalization_review.csv` filtered by `is_new_dj = YES`), look up correct SoundCloud URLs manually, add to `review/soundcloud_lookup.csv` in column 5, then run:

```bash
python3 -c "
import csv, requests, time
from bs4 import BeautifulSoup
# [see REFRESH_GUIDE.md for full script]
"
```

## Site / Hosting

- **basementstats.com** — hosted on Netlify, deploys from GitHub `main` branch, serves from `output/` (configured in `netlify.toml`)
- **abletonanders.github.io/basement_project** — GitHub Pages, deployed via `.github/workflows/static.yml`, also serves from `output/`
- `output/index.html` fetches `data/*.csv` from GitHub raw URLs client-side
- Three tab views: All Stages / Basement / Studio
- Clicking a DJ loads their SoundCloud embed + updates the year bar chart
- Bar chart: `data/dj_by_year.csv`, 8 bars (2019–2026), red `#8C2005`, hover turns `#ED4B00`, count appears above bar on hover

## Local Testing

The site fetches CSVs from GitHub raw URLs — opening `index.html` directly won't show local data. Use:

```bash
python3 -m http.server 8001   # serve from project root
# then open: http://localhost:8001/basement_local_test.html
```

`basement_local_test.html` is a patched version of `index.html` with GitHub raw URLs replaced by `localhost:8001`. Regenerate it with:

```bash
sed \
  -e 's|https://raw.githubusercontent.com/.../data/all_data.csv|http://localhost:8001/data/all_data.csv|g' \
  -e '[...other substitutions...]' \
  -e 's|src="basementpic.jpeg"|src="output/basementpic.jpeg"|g' \
  output/index.html > basement_local_test.html
```
