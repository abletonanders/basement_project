# CLAUDE.md — Basement Project

## What This Is

A stats dashboard for BASEMENT NYC, a Bushwick techno club. Tracks DJs, recurring party nights, and stages across the club's full run (May 2019 – present). Hosted on GitHub Pages at abletonanders.github.io/basement_project.

## Data Sources

| Source | Coverage | File |
|--------|----------|------|
| RA.co text scrape | May 2019 – Nov 2021 (pre-COVID closure) | `raw/basement_text.txt` |
| basementny.net web scrape | 2022 – present (post-reopening) | `raw/events_web.json` |

The two sources are complementary and non-overlapping. RA data has no stage info (all DJs assigned to "Basement"). Web data has explicit Basement/Studio stage splits.

## Pipeline Scripts

Run in this order:

```bash
python scrape.py               # scrape basementny.net → raw/events_web.json
python parse_ra.py             # parse RA text file → raw/events_ra.json
python build.py                # merge sources → data/*.csv + review/normalization_review.csv
```

For incremental updates (skip already-scraped events):
```bash
python scrape.py --since 2026-01-01
```

## File Layout

```
basement_project/
├── CLAUDE.md                        ← this file
├── Basement_Project.ipynb           ← original notebook (reference only)
├── normalize.py                     ← DJ name normalization logic
├── normalize_rules.json             ← human-editable remap/skip/expand rules
├── scrape.py                        ← web scraper (basementny.net)
├── parse_ra.py                      ← RA text file parser
├── build.py                         ← aggregation + CSV generation
├── raw/
│   ├── basement_text.txt            ← raw RA scrape (manual, do not modify)
│   ├── events_web.json              ← canonical web scrape output
│   ├── events_ra.json               ← canonical RA parse output
│   └── event_detail_*.json/xlsx     ← legacy notebook outputs (archived)
├── data/
│   ├── all_data.csv                 ← DJ counts, all stages
│   ├── basement_data.csv            ← DJ counts, Basement stage only
│   ├── studio_data.csv              ← DJ counts, Studio stage only
│   ├── party_data.csv               ← recurring night/party counts
│   └── dj_soundcloud.csv            ← DJ → SoundCloud user ID mapping
├── review/
│   └── normalization_review.csv     ← HITL audit log: raw → normalized DJ names
└── output/
    ├── index.html                   ← the website (fetches CSVs client-side)
    └── basementpic.jpeg
```

## Stage Assignment

Stage (Basement vs Studio) comes directly from basementny.net's HTML — no inference. Each event page has `div.event-detail__title-stages` containers, with `div.event-detail__headline` naming the stage and sibling divs listing DJs.

RA data (2019–2021) predates/lacks stage info — all RA DJs hardcoded to `Basement`.

The Studio room was introduced in 2022. For pre-2022 events, the website retroactively renders a Studio stage div in the HTML (because the page template always includes it), but populates it with only the stage label "Studio" and no DJs. The scraper picked this up as a DJ name — it is filtered out via the `skip` list in `normalize_rules.json`. Studio stats are only meaningful from late 2022 onward.

## DJ Name Normalization

`normalize.py` applies these steps in order:
1. **B2B split**: `"FJAAK B2B UMFANG"` → `["FJAAK", "UMFANG"]`
2. **Slash split**: `"DVS1 / VOLVOX"` → `["DVS1", "VOLVOX"]`
3. **NE/RE/A merge**: if `["ne", "re", "a"]` appear as fragments → `["NE/RE/A"]`
4. **Uppercase**: all names uppercased
5. **Manual rules** from `normalize_rules.json`:
   - `remaps`: direct 1-to-1 substitutions (typos, suffixes like "ALL NIGHT LONG")
   - `skip`: names to drop entirely (e.g. `"WRECKED"` appearing as a DJ name)
   - `expand`: names that expand to multiple DJs

## HITL Review Workflow

After `build.py` runs, inspect `review/normalization_review.csv`:
- `rule_applied = none` rows are highest-risk (normalizer left them untouched)
- Fix problems by editing `normalize_rules.json`, then re-run `build.py`
- No need to re-scrape

## Site / Hosting

- Static site, no build step
- `output/index.html` fetches `data/*.csv` client-side via JS and renders as HTML tables
- Three tab views: All Stages / Basement / Studio
- Clicking a DJ loads their SoundCloud embed
- GitHub Actions (`.github/workflows/static.yml`) deploys entire repo root to GitHub Pages on push to `main`

## SoundCloud IDs

`data/dj_soundcloud.csv` maps DJ names to SoundCloud user IDs. To update for new DJs:
- The `soundcloud.py` script (or `build.py --update-soundcloud`) runs Google search + SoundCloud HTML scrape
- Only runs for DJs not already in the CSV
