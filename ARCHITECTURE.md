# Job Radar — Architecture

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Directory Layout](#2-directory-layout)
3. [System Architecture](#3-system-architecture)
4. [Crawling Techniques](#4-crawling-techniques)
5. [Role Classification](#5-role-classification)
6. [Per-Crawler Details](#6-per-crawler-details)
7. [Data Schema](#7-data-schema)
8. [Dashboard & Search](#8-dashboard--search)
9. [Configuration](#9-configuration)
10. [GitHub Actions Automation](#10-github-actions-automation)
11. [Adding a New Crawler](#11-adding-a-new-crawler)

---

## 1. Project Overview

A personal job radar that aggregates postings from 25 companies (AI labs, Korean tech, physical AI, on-device AI silicon) into a single searchable, filterable dashboard.

- **Backend**: Python crawlers → post-processing (role, seniority, region, first-seen) → `docs/data/jobs.json`
- **Frontend**: Plain HTML/CSS/JS static site on GitHub Pages, no build step
- **Automation**: GitHub Actions crawls daily at 04:07 KST and commits the new data; a separate workflow runs the tests

---

## 2. Directory Layout

```
job-radar/
├── crawlers/
│   ├── __init__.py            # Crawler registry (get_all_crawlers) + per-company SECTORS
│   ├── base.py                # BaseCrawler: HTTP/Playwright helpers, warn(), format_job()
│   ├── classifier.py          # Role classifier (weighted title rules) + eval CLI
│   ├── enrich.py              # Post-processing: role, seniority, employment, pool, regions, first_seen
│   ├── google.py              # Google — Requests + BeautifulSoup (server-rendered cards)
│   ├── nvidia.py              # NVIDIA — Playwright XHR interception (Workday)
│   ├── samsung.py             # Samsung — Playwright + conditional waits
│   ├── naver.py               # Naver — internal AJAX API
│   ├── toss.py                # Toss — Playwright (Next.js)
│   ├── upstage.py             # Upstage — Requests + BeautifulSoup (Greeting HR)
│   ├── generic_greenhouse.py  # Shared Greenhouse crawler (Anthropic, Figure AI, Waymo, LG AI연구원, …)
│   ├── generic_ashby.py       # Shared Ashby crawler (OpenAI, 42dot, 1X, Physical Intelligence, Wayve)
│   ├── generic_lever.py       # Shared Lever crawler (no boards registered yet)
│   ├── generic_workday.py     # Shared Workday JSON crawler (Boston Dynamics, Intel)
│   ├── qualcomm.py / amd.py / mediatek.py   # On-device AI silicon, Korea-only
│   └── lg.py / sk.py          # Korean conglomerate group career APIs
├── docs/                      # Static web UI (GitHub Pages serves this folder)
│   ├── index.html
│   ├── style.css
│   ├── app.js                 # State, filters, rendering, carousel, URL sync
│   ├── search.js              # Related search (synonyms, typo tolerance, relevance)
│   ├── logos/                 # Company logos (local: the page CSP blocks remote images)
│   └── data/jobs.json         # Crawl output (auto-generated)
├── tests/
│   ├── test_classifier.py / test_enrich.py / test_main.py / test_base_crawler.py
│   └── data/role_gold.tsv, role_holdout.tsv   # Labeled titles for classifier evaluation
├── .github/workflows/
│   ├── daily-crawl.yml        # Daily crawl at 04:07 KST, commits jobs.json
│   └── tests.yml              # pytest on push / PR
├── main.py                    # Crawl entry point (+ --reclassify)
├── server.py                  # Local dev server (http://localhost:8000)
├── toggle_schedule.py         # Toggle the daily schedule on/off
├── config.json                # Crawler enablement + schedule flag
└── requirements.txt
```

---

## 3. System Architecture

```
┌──────────────────────────────────────────────────────────┐
│                         main.py                          │
│  config.json → pick crawlers → run each                  │
│  0 results? keep previous postings (≤ 7 days) + record   │
│  the reason · partial runs merge into existing data      │
└────────────────────────────┬─────────────────────────────┘
                             │
               ┌─────────────▼──────────────┐
               │        BaseCrawler         │  (abstract)
               │  safe_request / safe_post  │  retries, 429 Retry-After
               │  playwright_fetch          │  JS-rendered pages
               │  playwright_intercept      │  XHR response capture
               │  warn()                    │  records failure reasons
               │  format_job / is_expired   │
               └─────────────┬──────────────┘
                             │ inherits
     ┌───────────────┬───────┴────────┬───────────────────┐
     ▼               ▼                ▼                   ▼
 ATS REST APIs   Direct JSON APIs   Requests + BS4     Playwright
 Greenhouse,     Workday, Qualcomm, Google, Upstage    NVIDIA, Toss,
 Ashby, Lever    AMD, MediaTek,     (Naver: AJAX)      Samsung
                 LG, SK
                             │
                             ▼
               crawlers/enrich.py  ← crawlers/classifier.py
               role · role_group · seniority · employment
               pool · regions · first_seen · dedupe by URL
                             │
                             ▼
               docs/data/jobs.json (+ sources, taxonomy)
                             │
                             ▼
               docs/app.js + docs/search.js
               filters · related search · rendering
```

**Patterns applied**

- **Template Method**: `BaseCrawler` provides shared infrastructure; subclasses only implement `fetch_jobs()`.
- **Registry**: `get_all_crawlers()` returns crawler instances; generic crawlers hold a `BOARDS` table so adding a company on a known ATS is one line.
- **Single post-processing pass**: classification and enrichment run once in `main.py` over all postings (including carried-over ones), so rule changes apply to the whole dataset.

---

## 4. Crawling Techniques

### 4-1. Public ATS REST APIs

**Used by**: Greenhouse (Anthropic, Figure AI, Skild AI, Agility Robotics, Waymo, Motional, LG AI연구원), Ashby (OpenAI, 42dot, 1X, Physical Intelligence, Wayve)

```
requests.get(api_url) → parse JSON → format_job()
```

ATSes like Greenhouse, Ashby and Lever expose the entire job board as a public JSON API as long as you know the `board_token`. No auth required, and they only return open postings.

| Pros                                          | Cons                                                       |
| --------------------------------------------- | ---------------------------------------------------------- |
| Fastest and most reliable                     | Breaks instantly if the company switches ATS               |
| Immune to HTML changes                        | You have to discover the board_token yourself              |
| Returns structured data (dates, departments)  | OpenAI's Greenhouse → Ashby migration broke the old crawler |

Some boards return an `absolute_url` on the company's own site (Agility, Skild); it is used as-is.

---

### 4-2. Direct JSON APIs behind career sites

**Used by**: Workday (Boston Dynamics, Intel), Qualcomm (Eightfold), AMD (Jibe), MediaTek (tRPC), LG Careers, SK Careers

Many career sites load their listings from a JSON endpoint that answers plain `requests` calls:

| Site | Endpoint | Notes |
| ---- | -------- | ----- |
| Workday | `POST /wday/cxs/{tenant}/{site}/jobs` | 20 per page; `searchText` is fuzzy, so Korea filtering re-checks `locationsText` |
| Qualcomm | `GET /api/pcsx/search?location=Korea&start=N` | 10 per page |
| AMD | `GET /api/jobs?location=Korea&page=N` | re-checked on `full_location` |
| MediaTek | `GET /api/trpc/job.getJobs?input=…` | one call; keeps Korean sites |
| LG | `POST api.careers.lg.com/rmk/job/retrieveJobNoticesList` | filtered to LG전자 / 로보스타 |
| SK | `POST skcareers.com/Recruit/GetRecruitList` (form) | filtered to SK hynix / SK telecom |

Large chip vendors list thousands of global openings, so only Korea-based postings are kept.

---

### 4-3. Requests + BeautifulSoup (SSR scraping)

**Used by**: Google, Upstage, Naver

Parses fully server-rendered HTML statically. Naver calls its internal AJAX API (`/rcrt/loadJobList.do`) directly to paginate as JSON.

```
requests.get(url)
  → parse HTML with BeautifulSoup → extract cards via selectors

or (Naver)
requests.get(ajax_api?firstIndex=N)
  → parse JSON → iterate pages
```

**Google** sends its job cards in the HTML (`li[ssk]` with an `h3` title, a relative `jobs/results/{id}-{slug}` link,
the location next to the `place` icon and an Early / Mid / Advanced level). Pages are fetched with `&page=N` until no
new cards appear; the `page` parameter is stripped from job URLs so `first_seen` stays continuous. This replaced a
Playwright crawler that waited for `a[href*="/jobs/results/"]` as its "rendered" signal: job links are relative
(`jobs/results/…`, no leading slash) and never matched it, so the crawler only worked on days when some unrelated
link happened to match, and returned 0 otherwise (2026-10-07, 10-08, 10-10).

Upstage (Greeting HR) cards hold the title, team, experience and employment type in separate elements (`data-variant="title-01"`, `data-testid="공고리스트_subtext_*"`); they are extracted separately rather than reading the whole card text, which would glue them together.

| Pros                                  | Cons                                       |
| ------------------------------------- | ------------------------------------------ |
| Fast. No browser required             | Can't be used on JS-rendered pages         |
| ~1/10 the resource use of Playwright  | Breaks immediately if the site moves to CSR |

---

### 4-4. Playwright + HTML/JS parsing (CSR/SPA rendering)

**Used by**: Samsung, Toss

Runs a real headless Chromium browser, waits for JS rendering, then parses the DOM.

```
launch Playwright Chromium
  → page.goto(url)
  → wait_for_selector(a specific element)
  → page.evaluate()   ← walk the DOM in JS context
    or parse HTML with BeautifulSoup
```

**Toss** cards contain the title, tech tags and affiliate badges; each is read from its own element (`[data-desktop-list-item-title]`, the following tag span, the right-side badges).

| Pros                                      | Cons                                            |
| ----------------------------------------- | ----------------------------------------------- |
| Handles JS-rendered pages                 | Slow (5–15 s per page)                          |
| Identical DOM to a real browser           | Heavy memory use                                |
| Handles cookies/sessions automatically    | Selectors break when CSS classes are obfuscated |

---

### 4-5. Playwright XHR interception

**Used by**: NVIDIA (Workday)

Registers `page.on("response", handler)` to capture internal API responses as the page loads.

```
page.on("response", handler)  ← register a response listener
  → page.goto(url)            ← browser loads the page
    → Workday internal API is called automatically
      → handler captures responses matching /wday/cxs/
        → parse jobPostings JSON
```

**Why this approach**
The Workday page loads its listings through an internal API. Letting the browser load the page handles the session and CSRF token automatically. NVIDIA could also move to the generic Workday crawler (4-2); it stays on this path because it works.

---

## 5. Role Classification

**Files**: `crawlers/classifier.py`, `crawlers/enrich.py`

Classification runs once at the end of `main.py` (`enrich_jobs`) over every posting, including
postings carried over from a failed crawl, so a rule change re-labels the whole dataset on the next run
(or immediately with `python main.py --reclassify`).

**Taxonomy: 4 families, 16 roles (+ Other)**

| Family | Roles |
| ------ | ----- |
| Engineering | AI / ML · Software · Data · Hardware / Semiconductor · Robotics / Autonomy · Manufacturing / Quality · Security |
| Product & Design | Product / Planning · Design |
| Business | Sales / BD · Solutions / Customer Support · Marketing / PR |
| Operations & Support | Operations / Strategy · Risk / Compliance · Legal / Policy · G&A |

**Pipeline (weighted rules)**

```
title (+ department, + site tags)
   │
   ▼  normalize   NFKC, lowercase, drop "[NAVER]" prefixes and "(경력)", "(~10/11)" meta
   ▼  split       head = segment before "," / " - " / "|"   (English titles: the head names the job)
   │              generic heads ("Senior Manager, …") or heads without a job cue are skipped
   ▼  match       ~600 weighted patterns; English uses word boundaries ("ios" ≠ "scenarios"),
   │              Korean uses substrings; longer phrases carry more weight
   ▼  score       head ×1.0 (+0.5 if the match ends the head: the head noun),
   │              rest ×0.5 (domain words like robotics ×0.8), department ×0.6, tags ×0.4
   │              role score = best match + 0.3 × other matches; ties → ROLE_PRIORITY
   ▼  decide      score ≥ 1.5 → role · 1.0–1.5 → role (weak) · else → Other
```

An embedding fallback (multilingual MiniLM, kNN over example titles) is still in the code but **off by default**
(`JOB_RADAR_EMBEDDING=1` to enable). On the held-out set it added no accuracy (87.3% with and without) while
guessing badly on low-confidence titles, and it cost CI a torch install plus a 420 MB model download per run.

**Evaluation**

| Set | Rows | Purpose |
| --- | ---- | ------- |
| `tests/data/role_gold.tsv` | 195 | Titles used while writing rules: regression guard (≥ 97% in tests) |
| `tests/data/role_holdout.tsv` | 79 | Random sample labeled *before* looking at predictions: generalization (≥ 85% in tests) |

Held-out accuracy: previous keyword-priority classifier 65.8% (scored leniently against its coarser 7 categories),
new rules 87.3% on first run. Remaining misses are genuinely ambiguous titles (e.g. "Applied AI Engineer" in a
go-to-market team). Do not tune rules against the held-out file, or it stops being held out.

```bash
python -m crawlers.classifier --eval             # accuracy + every miss on the gold set
python -m crawlers.classifier "Backend Engineer" # classify ad-hoc titles
```

**Other derived fields** (`enrich.py`)

- `seniority`: 인턴 / 신입·주니어 / 경력 / 시니어 / 리더, from the title first, then site level tags (Google Early/Mid/Advanced, Upstage "경력 3년 이상")
- `employment`: 계약직 when the title or tags say contract / fixed-term / 계약
- `pool`: true for talent-pool / expression-of-interest posts (real listings, but not a specific opening)
- `regions`: 한국 / 북미 / 유럽 / 아시아·태평양 / 원격 / 기타 from the free-text location
- `first_seen`: carried over by URL from the previous `jobs.json`; a company newly added to the tracker gets an empty baseline instead of "new today"

---

## 6. Per-Crawler Details

| Crawler   | Approach                  | Pagination                          | Deadline / open filter  | Notes                                                  |
| --------- | ------------------------- | ----------------------------------- | ----------------------- | ------------------------------------------------------ |
| Greenhouse boards | REST API          | None                                | API returns open jobs only | Anthropic, Figure AI, Skild AI, Agility, Waymo, Motional, LG AI연구원 |
| Ashby boards | REST API               | None                                | Drops `isListed=false`  | OpenAI, 42dot, 1X, Physical Intelligence, Wayve        |
| Workday (generic) | JSON POST `/wday/cxs/…/jobs` | `offset` += 20 until `total` | Open jobs only        | Boston Dynamics (all), Intel (Korea via `locationsText`) |
| Qualcomm  | Eightfold `/api/pcsx/search` | `start` += 10                 | Open jobs only          | `location=Korea`                                       |
| AMD       | Jibe `/api/jobs`          | `page`, 100 per page                | Open jobs only          | `location=Korea`, re-checked on `full_location`        |
| MediaTek  | tRPC `job.getJobs`        | One call (limit 1000)               | API returns posted jobs | Keeps Korean sites (Seongnam)                          |
| LG전자    | LG Careers JSON POST      | One call                            | Drops past `recEndDateTime` | companyCode LGE, RBO (로보스타)                     |
| SK하이닉스 | SK Careers form POST     | One call                            | Drops past `end`        | SK hynix, SK telecom only                              |
| Naver     | Internal AJAX JSON API    | `firstIndex` parameter              | Drops `endYmd < today`  | Total pages computed from the `totalRows` JS variable  |
| Google    | Requests + BS4            | `&page=N` until no new cards        | Listing shows open jobs | Server-rendered `li[ssk]` cards; titles from `h3`      |
| NVIDIA    | Playwright XHR intercept  | None (initial load only)            | Open jobs only          | Workday internal API                                   |
| Samsung   | Playwright + BS4          | None                                | Listing shows open jobs | Waits on `ul.job#list li a[data-value]`; 0 results is normal off-cycle |
| Toss      | Playwright + BS4          | None                                | Listing shows open jobs | Title / tags / affiliates read separately              |
| Upstage   | Requests + BS4            | None                                | Listing shows open jobs | Greeting HR SSR, `/ko/o/{id}` pattern                  |

Each run replaces a company's postings wholesale, so a posting that closes disappears on the next successful crawl.

---

## 7. Data Schema

### jobs.json

```json
{
  "updated_at": "2026-10-09T17:37:05+00:00",
  "total": 3085,
  "results": { "Anthropic": 646, "OpenAI": 817 },
  "sources": {
    "Google": {
      "company": "Google", "category": "외국계", "sectors": ["AI 연구소"],
      "count": 20, "status": "stale", "last_success": "2026-10-06", "stale_since": "2026-10-07"
    }
  },
  "taxonomy": { "groups": { "엔지니어링": ["AI / ML", "..."] }, "levels": ["인턴", "..."], "regions": ["한국", "..."] },
  "jobs": [ ... ]
}
```

| `sources[*]` field | Meaning |
| ------------------ | ------- |
| `status` | `ok` · `stale` (0 results, previous postings kept) · `failed` (0 results and nothing kept: new company, or failing for 7+ days) |
| `last_success` / `stale_since` | KST dates of the last good crawl and the start of the current failure streak |

After 7 days of continuous failure (`STALE_MAX_DAYS`) a `stale` company becomes `failed` and its postings are dropped, so closed jobs don't linger. Failure *reasons* are deliberately not in this public file; they go to GitHub (see [Failure reporting](#failure-reporting)). `taxonomy` lets the dashboard render filters without hard-coding role names.

### Single job object

```json
{
  "company": "42dot",
  "category": "대기업",
  "role": "AI / ML",
  "role_group": "엔지니어링",
  "title": "Deep Learning Engineer (음성 합성 개발)",
  "url": "https://jobs.ashbyhq.com/42dot/...",
  "location": "Pangyo (Software Dream Center), South Korea",
  "department": "ENGINEERING",
  "tags": [],
  "posted_date": "2026-10-02T01:12:44.000+00:00",
  "seniority": "",
  "employment": "",
  "pool": false,
  "regions": ["한국"],
  "first_seen": "",
  "crawled_at": "2026-10-09T17:37:05+00:00"
}
```

| Field         | Description                                                        |
| ------------- | ------------------------------------------------------------------ |
| `category`    | Company bucket (외국계 / 대기업 / IT / 금융 / 제조업 / 스타트업)       |
| `role`, `role_group` | Role and family, assigned by `classifier.py`                |
| `tags`        | Optional site tags (Toss tech tags, Upstage experience, Google level) |
| `posted_date` | Format varies per company (ISO 8601 / YYYY-MM-DD)                  |
| `seniority`, `employment`, `pool`, `regions` | Derived in `enrich.py` (see section 5) |
| `first_seen`  | KST date this URL first appeared ("" = before tracking / baseline) |
| `crawled_at`  | Collection time (always ISO 8601)                                  |

---

## 8. Dashboard & Search

**Files**: `docs/index.html`, `docs/style.css`, `docs/app.js`, `docs/search.js`

The layout follows Korean job boards (원티드, 점핏, 토스 채용): a search hero with a count sentence, an auto-advancing
carousel of the most active companies (3 s per step, pauses on hover/focus/touch, arrows in the section header),
role-family tabs with role pills, dropdown filter chips (company, sector, experience, region) with live counts,
and a list of postings with company logos, colored role tags, NEW / 인재풀 badges and relative dates.
All filter state lives in the URL query string, so any view can be shared. Light and dark themes are token-based;
the toggle is remembered in `localStorage`.

**Related search** (`search.js`)

1. Query words map to *concepts*: Korean/English synonyms, abbreviations and company names
   ("백엔드" → backend · back-end · server · 서버; "엔비디아" → nvidia).
2. Related technologies count as weaker evidence, title only ("백엔드" → spring, kotlin, java).
3. English is matched on word boundaries with plural tolerance ("intern" ≠ "International"); multi-word
   terms ignore space/hyphen differences; Korean uses substring matching.
4. One-letter typos in 5+ letter English words are corrected and reported ("enginer → engineer").
5. Relevance: title 3 · company 2.5 · role/department/tags 2 · location 1.5 · related term 1.2 · typo 1.
   Searching switches the sort to relevance; matched words are highlighted in titles.
6. All concepts must match; if nothing does, postings matching some concepts are shown with a notice.

**Constraints**: the page sets a strict CSP (`script-src 'self'`, `img-src 'self' data:`, fonts and the
Pretendard stylesheet only from `cdn.jsdelivr.net`). Logos are therefore stored in `docs/logos/`, and colors that
depend on data use CSS classes instead of inline `style` attributes, which the CSP blocks.

**Logos**: official current logos (company sites / Wikimedia Commons), rendered to PNG. A company without a
file falls back to a colored initial badge. To add one, put the PNG in `docs/logos/` and map it in `LOGOS`
(and `WIDE_LOGOS` for wordmarks) in `app.js`.

---

## 9. Configuration

### config.json

```json
{
  "schedule": {
    "enabled": true,
    "interval": "daily",
    "last_updated": "2026-10-09T17:37:05+00:00"
  },
  "crawlers": {
    "NVIDIA": true,
    "Google": true,
    "Anthropic": true,
    "...": true,
    "MediaTek": true
  }
}
```

- `schedule.enabled`: Whether the daily GitHub Actions crawl runs (toggle with `toggle_schedule.py`)
- `crawlers.<name>`: When `false`, the crawler is skipped in the default `python main.py` run. Every name in
  `get_all_crawlers()` must appear here; a test fails if the two drift apart, because a missing entry would silently skip that company.

---

## 10. GitHub Actions Automation

**File**: `.github/workflows/daily-crawl.yml`

```
Daily at 19:07 UTC (04:07 KST next day), or manually (workflow_dispatch)
  → check schedule.enabled in config.json
  → only run if true:
      pip install (with pip cache)
      install Playwright chromium (cache keyed on requirements.txt hash)
      python main.py
      git add -f docs/data/jobs.json config.json
      git commit & pull --rebase & push   (always, even if some crawlers failed)
      open / comment on / close the crawl-failure issue
```

**Key settings**

| Setting                       | Value                          | Reason                                                  |
| ----------------------------- | ------------------------------ | ------------------------------------------------------- |
| `runs-on: ubuntu-24.04`       | Pinned runner                  | `ubuntu-latest` moves to Ubuntu 26 on 2026-10-19; Playwright's system deps are verified on 24.04 |
| Action versions               | checkout v7, setup-python v7, cache v6 | Node 24 runtimes (Node 20 is deprecated on runners) |
| `concurrency: group: crawl`   | Limit to 1 concurrent run      | Prevents push conflicts from overlapping runs           |
| `timeout-minutes: 60`         | 60 minutes                     | Caps runner time if Playwright hangs                    |
| `cache: "pip"`                | pip cache                      | Skips dependency reinstall                              |
| Playwright cache              | Key on `requirements.txt` hash | Avoids re-downloading the browser binary                |

The crawl step exits 1 when any company failed, so the run turns red, but the commit step runs with
`if: always()` so the healthy companies' data is still published.

### Tests workflow

`.github/workflows/tests.yml` runs `pytest` on every push to `main` (except data-only crawl commits) and on PRs.
It includes the classifier accuracy floors (gold ≥ 97%, holdout ≥ 85%), so a rule change that breaks
classification fails CI. Date logic is tested against KST, so the suite passes regardless of the runner's time zone.

### Failure reporting

Failures are operational logs, so they live on GitHub, not on the public dashboard or in `jobs.json`.
When a company comes back empty (or drops by more than half), the run records *why*: an HTTP status with a hint
such as "429 요청 과다(rate limit)", a browser load error, "page loaded but no job cards" with the page title, a
crawler exception, or "0 with no error recorded". It shows up in:

- **The run page**: `::error` / `::warning` annotations at the top, plus a per-company status table
  (status, count, last success, reason) in the job summary.
- **A `crawl-failure` issue**: the last workflow step opens one when the crawl fails, adds a comment with the
  new report if it is still failing the next day, and closes it with a link to the run once every company
  succeeds again. Opening the issue triggers a GitHub notification.
- **The console**: a "수집 문제 요약" list at the end of every local run.

`main.py` writes the report to `CRAWL_REPORT_PATH` (set by the workflow, gitignored). Crawlers report problems
through `BaseCrawler.warn()` rather than `print`, so a failure is never silent.

---

## 11. Adding a New Crawler

### Option A — the company uses a known ATS

Add one line to the `BOARDS` table of `generic_greenhouse.py`, `generic_ashby.py`, `generic_lever.py`
or `generic_workday.py`, then do steps 2–4 below.

### Option B — a custom site

### Step 1 — Create the crawler file

```python
# crawlers/newcompany.py
from .base import BaseCrawler

class NewCompanyCrawler(BaseCrawler):
    def __init__(self):
        super().__init__("NewCompany", "외국계")  # 외국계 / 대기업 / IT / 금융 / 제조업 / 스타트업
        self.url = "https://..."

    def fetch_jobs(self):
        jobs = []
        resp = self.safe_request(self.url)   # records the failure reason itself
        if not resp:
            return jobs
        for item in resp.json().get("jobs", []):
            jobs.append(self.format_job(
                title=item["title"],
                url=item["url"],
                location=item.get("location", ""),
                department=item.get("team", ""),
                posted_date=item.get("published", ""),
                tags=[],                       # optional site tags
            ))
        if not jobs:
            self.warn("페이지는 열렸지만 공고를 하나도 못 찾음 — 응답 형식 변경 가능성")
        return jobs
```

Role, seniority, region and first-seen are attached later by `enrich.py`; the crawler only returns raw postings.
Report anything that went wrong with `self.warn(...)` so an empty day shows its cause.

### Step 2 — Register it

```python
# crawlers/__init__.py
from .newcompany import NewCompanyCrawler

SECTORS = {..., "NewCompany": [PHYSICAL]}   # 피지컬 AI / 온디바이스 AI / AI 연구소, or omit

def get_all_crawlers():
    crawlers = {
        ...
        "NewCompany": NewCompanyCrawler(),
    }
```

### Step 3 — Add it to config.json

```json
"crawlers": {
    "NewCompany": true
}
```

### Step 4 — Add the logo (optional)

Save the official logo as `docs/logos/newcompany.png` and add `'NewCompany': 'newcompany'` to `LOGOS` in `docs/app.js`.

### Recommended approach per site type

| Site type                         | Recommended approach                                                  |
| --------------------------------- | --------------------------------------------------------------------- |
| Greenhouse / Ashby / Lever / Workday | Add a row to the matching generic crawler's `BOARDS`               |
| Site that loads a JSON endpoint   | Call it with `safe_request()` / `safe_post()` (check the browser's network tab) |
| SSR (server-rendered)             | `safe_request()` + BeautifulSoup                                      |
| CSR / SPA (React, Next.js)        | `playwright_fetch()`                                                  |
| SPA whose API needs a browser session | `playwright_intercept()`                                          |
