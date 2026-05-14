# CLAUDE.md — Basement Project

## What This Is

A stats dashboard for BASEMENT NYC, a Bushwick techno club. Tracks DJs, recurring party nights, and stages across the club's full run (May 2019 – present). Live at basementstats.com (Netlify) and abletonanders.github.io/basement_project (GitHub Pages).

## Current State (pickup hints)

- **Last refresh: 2026-05-13** — full-archive RA ingestion + web rescrape, deployed and live.
- **Stats on site:** 727 artists / 485 unique club nights / 50 parties / 7.4 nights per month (2022–2025 mean).
- **Coverage:** May 2019 – May 2026.
- **Next refresh:** incremental — `python3 scrape.py --since 2026-05-13 && python3 build.py`, then steps 5–9 of `REFRESH_GUIDE.md`. Full rescrape (~45 min) is also fine.
- **Uncommitted right now:** `REFRESH_GUIDE.md` has real operational improvements from the May 13 refresh (SoundCloud lookup hardening, count-up animation `data-target` gotcha, local-server `cd` reminder). Inspect with `git diff REFRESH_GUIDE.md` and commit before doing more work — they're the runbook, not noise.
- **Working-tree noise to ignore in `git status`:** `.DS_Store`, `basement_local_test.html` (regenerable per §8), `raw/*.bak`, `raw/*_20260513.log`, `Basement_Project.ipynb` (kernel/output state churn only — notebook is reference-only, do not commit). The `review/` dir is gitignored.
- **Last 5 commits (ground truth for what shipped):** `1a5d8b3` scroll animations + larger hover labels · `9e67b5f` monthly chart hero refresh 7.3 → 7.4 · `096c2e9` full-archive RA ingest + merge logic + docs overhaul · `0d00e34` SoundCloud IDs for 23 new artists · `1d779d7` SEDEF ADASI remap + BASSIANI party rule.

## Data Sources

| Source | Coverage | File |
|--------|----------|------|
| RA.co text scrape (full archive) | May 2019 – present | `raw/basement_text.txt` (original) + dated supplements `raw/YYYYMMDD_basement_text.txt` |
| basementny.net web scrape | May 2019 – present | `raw/events_web.json` |

Both sources cover the full run as of the May 2026 refresh. `build.py` merges them with post-normalization conflict detection — RA wins on zero-DJ-overlap conflict dates (basementny.net periodically re-points pages to the wrong event). Web is the only source of Basement-vs-Studio stage info; RA hardcodes stage = Basement.

`raw/basement_text.txt` is **irreplaceable** — a manual scrape of RA pages that may no longer exist. Never overwrite it. New RA scrapes go in dated supplement files (`raw/YYYYMMDD_basement_text.txt`) which can be promoted to canonical via the procedure in `REFRESH_GUIDE.md` §2a.

## Pipeline Scripts

Run in this order:

```bash
python3 parse_ra.py            # parse RA text file → raw/events_ra.json
python3 scrape.py              # scrape basementny.net → raw/events_web.json  (~45 min)
python3 build.py               # merge + aggregate → data/*.csv + review/*.csv
```

For incremental updates (next refresh):
```bash
python3 scrape.py --since 2026-05-13   # adjust to last known scraped date
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
6. **RA disambiguation suffix stripping**: `"JEK (US)"` → `"JEK"`, `"MOS (NYC)"` → `"MOS"`, `"BEATRICE (DE)"` → `"BEATRICE"`. Regex: `\s*\(\s*[A-Z0-9 ]{1,5}\s*\)\s*$`. Required because RA disambiguates same-named artists by country/city tag — without this they get double-counted vs the web spelling.
7. **NE/RE/A merge**: fragments → `["NE/RE/A"]`
8. **Uppercase**
9. **Manual rules** from `normalize_rules.json`: `remaps`, `skip`, `expand`

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
