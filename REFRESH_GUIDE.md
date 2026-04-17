# Data Refresh Guide

How to re-execute the full pipeline, in order, with data fidelity checks at each step.

Last refreshed: April 17, 2026 (Anders Zhou). Covered May 2019 – April 2026. 449 web events scraped, 97 RA events parsed.

---

## One-time setup

```bash
pip3 install playwright beautifulsoup4 python-dateutil requests pandas
python3 -m playwright install chromium
```

---

## Execution order

### 1. Back up existing raw data

```bash
cd ~/Desktop/basement_project
cp raw/events_web.json raw/events_web.json.bak
```

`raw/basement_text.txt` is **irreplaceable** — never overwrite it.

### 2. Parse the RA text file

```bash
python3 parse_ra.py
```

Fast, no network. Produces `raw/events_ra.json` (~97 events, 2019–2021). Run first to establish a stable baseline.

### 3. Scrape basementny.net

```bash
python3 scrape.py
```

Takes ~45–60 minutes (2-second delay, ~450 events expected). Produces `raw/events_web.json`.

Monitor progress in a second terminal:
```bash
wc -l ~/Desktop/basement_project/raw/events_web.progress.jsonl
tail -1 raw/events_web.progress.jsonl | python3 -c "import json,sys; e=json.load(sys.stdin); print(e['event_detail_date'][:10], e['event_detail_title'])"
```

If the scrape crashes mid-run, recover the partial file then restart:
```bash
python3 -c "
import json
events = [json.loads(l) for l in open('raw/events_web.progress.jsonl') if l.strip()]
json.dump(events, open('raw/events_web.json', 'w'), indent=2, ensure_ascii=False)
print(f'Recovered {len(events)} events')
"
python3 scrape.py --since 2024-06-01   # adjust to last recovered date
# then manually merge the two partial outputs
```

**Spot-check before proceeding:**
- Total event count should be ~450+
- Earliest date should be around May 10, 2019
- Latest date should be recent (within weeks of today)
- Zero SKIP lines in the output log
- No events with empty `event_detail_music`

### 4. Build aggregate CSVs

```bash
python3 build.py
```

Merges both sources (RA for 2019–2021, web for 2022+, plus 4 web-only supplement dates from late 2021). Outputs:
- `data/all_data.csv`, `basement_data.csv`, `studio_data.csv`
- `data/party_data.csv` — unique nights per party (not DJ rows)
- `data/dj_by_year.csv` — per-DJ counts by year (powers the bar chart)
- `review/normalization_review.csv`, `review/party_review.csv`
- `review/overlap_events.csv`, `review/overlap_djs.csv`

### 5. Review DJ names and party titles (HITL)

Generate the review JSONs for easier browsing:
```bash
python3 -c "
import csv, json
from collections import Counter
for source, out, field in [
    ('review/normalization_review.csv', 'review/dj_corrections.json', 'normalized_name'),
    ('review/party_review.csv', 'review/party_corrections.json', 'normalized_title'),
]:
    rows = list(csv.DictReader(open(source, encoding='utf-8')))
    counts = Counter(r[field].strip() for r in rows if r[field].strip() not in ('', '(dropped)'))
    with open(out, 'w', encoding='utf-8') as f:
        json.dump({f'{name} ({count})': '' for name, count in counts.most_common()}, f, indent=2, ensure_ascii=False)
    print(f'{out}: {len(counts)} entries')
"
```

Open `review/dj_corrections.json` in VS Code. Look for:
- Suffixes still attached: "OPEN TO CLOSE", "ALL NIGHT LONG", "LIVE", "PRESENTS"
- Smushed names: two DJ names concatenated with no space (e.g. `MAKADSIRON LIKE HELL`)
- Spelling variants of the same DJ
- `is_new_dj = YES` in `normalization_review.csv` → candidates for SoundCloud lookup

Open `review/party_corrections.json`. Look for:
- Recurring party names that should be canonicalized (add to `normalize_rules.json`)
- `rule_applied = none` titles appearing 3+ times

Fix by editing `normalize_rules.json`, re-run `build.py`. No re-scraping needed.

### 6. Add SoundCloud IDs for new DJs

**Automated lookup does not work.** Google rate-limits immediately. DuckDuckGo rate-limits after 2 searches. Slug guessing is unreliable — returns wrong profiles for common names.

**Correct process:**
1. From `review/normalization_review.csv`, filter `is_new_dj = YES` and count ≥ 5
2. Manually look up each DJ on SoundCloud
3. Add the correct URL to `review/soundcloud_lookup.csv` (column 5)
4. Run the ID scraper:

```bash
python3 -c "
import csv, requests, time
from bs4 import BeautifulSoup
HEADERS = {'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36'}
rows = list(csv.reader(open('review/soundcloud_lookup.csv', encoding='utf-8')))[1:]
existing = {r['DJ']: r for r in csv.DictReader(open('data/dj_soundcloud.csv', encoding='latin-1'))}
for row in rows:
    dj, _, _, _, correct_url = row[0], row[1], row[2], row[3], row[4] if len(row) > 4 else ''
    if not correct_url or correct_url in ('NO SOUNDCLOUD', 'url', ''):
        continue
    resp = requests.get(correct_url, headers=HEADERS, timeout=8)
    soup = BeautifulSoup(resp.text, 'html.parser')
    meta = soup.find('meta', {'property': 'al:ios:url'})
    sc_id = meta['content'].split('users:')[-1].strip() if meta and 'users:' in meta['content'] else ''
    existing[dj] = {'DJ': dj, 'Count': '', 'Soundcloud_Link': correct_url, 'Soundcloud_User_ID': sc_id}
    print(f'{dj}: {sc_id}')
    time.sleep(0.3)
with open('data/dj_soundcloud.csv', 'w', newline='', encoding='utf-8') as f:
    w = csv.DictWriter(f, fieldnames=['DJ','Count','Soundcloud_Link','Soundcloud_User_ID'])
    w.writeheader()
    for row in existing.values():
        w.writerow({k: row.get(k,'') for k in ['DJ','Count','Soundcloud_Link','Soundcloud_User_ID']})
print('Done')
"
```

Then re-run `build.py` to pick up the new IDs.

### 7. Update hardcoded stats in index.html

The three stat numbers won't update automatically. Run:

```bash
python3 -c "
import csv, json
djs = set(r['DJ'] for r in csv.DictReader(open('data/all_data.csv')))
parties = sum(1 for _ in csv.DictReader(open('data/party_data.csv')))
web = json.load(open('raw/events_web.json'))
ra = json.load(open('raw/events_ra.json'))
print(f'Artists:     {len(djs)}')
print(f'Club nights: {len(web) + len(ra)}')
print(f'Parties:     {parties}')
"
```

Edit the three `.stat-number` spans in `output/index.html`. Also update the year badge and title if a new year has begun.

### 8. Test locally

The site fetches CSVs from GitHub raw URLs — you cannot just open `index.html` directly. Run a local server:

```bash
python3 -m http.server 8001   # from project root
```

Generate the patched test file:
```bash
sed \
  -e 's|https://raw.githubusercontent.com/abletonanders/basement_project/main/data/all_data.csv|http://localhost:8001/data/all_data.csv|g' \
  -e 's|https://raw.githubusercontent.com/abletonanders/basement_project/main/data/basement_data.csv|http://localhost:8001/data/basement_data.csv|g' \
  -e 's|https://raw.githubusercontent.com/abletonanders/basement_project/main/data/studio_data.csv|http://localhost:8001/data/studio_data.csv|g' \
  -e 's|https://raw.githubusercontent.com/abletonanders/basement_project/main/data/party_data.csv|http://localhost:8001/data/party_data.csv|g' \
  -e 's|https://raw.githubusercontent.com/abletonanders/basement_project/main/data/dj_by_year.csv|http://localhost:8001/data/dj_by_year.csv|g' \
  -e 's|src="basementpic.jpeg"|src="output/basementpic.jpeg"|g' \
  output/index.html > basement_local_test.html
open "http://localhost:8001/basement_local_test.html"
```

Verify:
- Bar chart loads preloaded with RON LIKE HELL on page open
- Clicking a DJ updates the chart and loads their SoundCloud embed
- All three tabs (All Stages / Basement / Studio) load correctly
- Party counts look right (WRECKED should be ~61–70)
- Stats (artists / club nights / parties) are updated

### 9. Commit and push

`git status` first. Stage specific files — never `git add -A`. Key files to stage:
```
data/all_data.csv
data/basement_data.csv
data/studio_data.csv
data/party_data.csv
data/dj_by_year.csv
data/dj_soundcloud.csv
raw/events_web.json
raw/events_ra.json
output/index.html
normalize_rules.json
```

Push to `main` — both Netlify and GitHub Pages deploy automatically (~30 seconds).

Verify live at **basementstats.com** and hard-refresh (Cmd+Shift+R) to bypass browser cache.

---

## Data fidelity risks

| Risk | Signal | Mitigation |
|------|--------|------------|
| basementny.net HTML changes | Smushed DJ strings reappear (`StudioXXXDJNAME`) or events have empty `event_detail_music` | Check scraper leaf-div logic; re-examine page structure |
| Scroll-to-load misses early events | Earliest date in `events_web.json` is not May 2019 | Full re-scrape usually fixes this |
| Same DJ counted twice under variant spellings | Two similar names in `all_data.csv` | `normalization_review.csv` cross-reference |
| Partial scrape crash | `events_web.json` missing or smaller than expected | Use `.bak`; recover from progress file |
| Wrong SoundCloud profile | Clicking a DJ loads wrong artist | Manual verification only — do not trust automated lookup |
| Stale hardcoded stats | Site shows old artist/night/party counts | Always run the snippet in step 7 |
| Party counts inflated | WRECKED showing 200+ instead of ~60 | `party_data.csv` counts unique nights (fixed) — if inflated again, check `build.py` party_counter logic |

---

## Data provenance and CDC

### Snapshots (Option A)
Every `scrape.py` run automatically writes a dated snapshot to `raw/snapshots/events_web_YYYYMMDD.json`. These are **never overwritten or deleted** — they form a permanent archive of every scrape run. The canonical `raw/events_web.json` is always a copy of the most recent run.

To see all historical snapshots:
```bash
ls -lh raw/snapshots/
```

To restore a previous scrape:
```bash
cp raw/snapshots/events_web_20260417.json raw/events_web.json
python3 build.py
```

### Change detection (Option B)
`build.py` automatically compares the two most recent snapshots and writes `review/changes_YYYYMMDD.csv` if any differences are found. The report has three change types:

| change_type | Meaning |
|-------------|---------|
| `ADDED` | Event exists in new scrape but not previous — genuinely new event |
| `REMOVED` | Event existed before but is no longer on the website |
| `MODIFIED` | Same date, but title or DJ list changed |

**REMOVED events are the most important to review** — they may indicate the website removed an event that was real, or that a scrape missed something.

On first run after the initial baseline, `build.py` will print the change summary to stdout. The report is also saved to `review/changes_YYYYMMDD.csv` for your reference.

---

## Incremental refresh (future years)

```bash
python3 scrape.py --since 2026-04-17   # adjust to last scraped date
python3 build.py
```

Then repeat steps 5–9. Re-scraping everything from scratch (~45 min) is also fine and ensures no events are missed.
