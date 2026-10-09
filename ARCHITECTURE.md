# Job Radar — Architecture

## Table of Contents

1. [Project Overview](#1-project-overview)
2. [Directory Layout](#2-directory-layout)
3. [System Architecture](#3-system-architecture)
4. [Crawling Techniques](#4-crawling-techniques)
5. [Role Classification](#5-role-classification)
6. [Per-Crawler Details](#6-per-crawler-details)
7. [Data Schema](#7-data-schema)
8. [Configuration](#8-configuration)
9. [GitHub Actions Automation](#9-github-actions-automation)
10. [Adding a New Crawler](#10-adding-a-new-crawler)

---

## 1. Project Overview

A personal job radar that aggregates postings from multiple tech companies into a single searchable, filterable dashboard.

- **Backend**: Python crawlers → produces `docs/data/jobs.json`
- **Frontend**: Plain HTML/CSS/JS static site (hosted on GitHub Pages)
- **Automation**: GitHub Actions runs daily at 09:00 KST (optional)

---

## 2. Directory Layout

```
job-radar/
├── crawlers/
│   ├── __init__.py          # Crawler registry (get_all_crawlers)
│   ├── base.py              # BaseCrawler abstract class
│   ├── classifier.py        # Role classifier (weighted title rules)
│   ├── enrich.py            # Post-processing: role, seniority, regions, first_seen
│   ├── google.py            # Google — Playwright + JS evaluate
│   ├── nvidia.py            # NVIDIA — Playwright XHR interception
│   ├── samsung.py           # Samsung — Playwright + conditional waits
│   ├── naver.py             # Naver — internal AJAX API
│   ├── toss.py              # Toss — Playwright (Next.js)
│   ├── upstage.py           # Upstage — Requests + BeautifulSoup
│   ├── generic_greenhouse.py # Shared Greenhouse ATS crawler (Anthropic, Figure AI, Waymo, …)
│   ├── generic_ashby.py     # Shared Ashby ATS crawler (OpenAI, 42dot, 1X, …)
│   ├── generic_lever.py     # Shared Lever ATS crawler
│   ├── generic_workday.py   # Shared Workday JSON crawler (Boston Dynamics, Intel)
│   ├── qualcomm.py / amd.py / mediatek.py   # On-device AI silicon, Korea-only
│   └── lg.py / sk.py        # Korean conglomerate group career APIs
├── docs/                    # Static web UI (GitHub Pages)
│   ├── index.html
│   ├── style.css
│   ├── app.js
│   └── data/
│       └── jobs.json        # Crawl output (auto-generated)
├── .github/workflows/
│   └── daily-crawl.yml      # GitHub Actions workflow (daily 09:00 KST)
├── tests/data/role_*.tsv    # Labeled titles for classifier evaluation
├── main.py                  # Crawler entry point (+ --reclassify)
├── server.py                # Local dev server
├── toggle_schedule.py       # Toggle GitHub Actions schedule on/off
├── config.json              # Crawler enablement
└── requirements.txt
```

---

## 3. System Architecture

```
┌─────────────────────────────────────────────────────┐
│                     main.py                         │
│  read config.json → pick active crawlers → run them │
│  partial runs merge into existing jobs.json         │
└──────────────────────┬──────────────────────────────┘
                       │
          ┌────────────▼────────────┐
          │      BaseCrawler        │  (abstract class)
          │  - safe_request()       │  shared HTTP request
          │  - playwright_fetch()   │  JS-rendered pages
          │  - playwright_intercept()│ XHR response capture
          │  - format_job()         │  standard data shape
          │  - is_expired()         │  deadline filter
          └────────────┬────────────┘
                       │ inherits
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
   REST API       Requests       Playwright-
   crawlers       + BS4          based crawlers
  (Greenhouse    (Naver,         (Google,
   Ashby)        Upstage)        NVIDIA, Toss,
                                 Samsung)
                       │
                       ▼
              crawlers/classifier.py
              title → role classification
              (weighted rules → enrich)
                       │
                       ▼
              docs/data/jobs.json
                       │
                       ▼
              docs/app.js (frontend)
              filter · search · render
```

**Patterns applied**

- **Template Method**: `BaseCrawler` provides shared infrastructure; subclasses only implement `fetch_jobs()`.
- **Factory**: `get_all_crawlers()` returns a dict of crawler instances.
- **Single pass**: Classification and enrichment run once in `main.py` over all postings, cached per title.

---

## 4. Crawling Techniques

### 4-1. Direct public REST API

**Used by**: Anthropic (Greenhouse), OpenAI (Ashby)

```
requests.get(api_url) → parse JSON → format_job()
```

ATSes like Greenhouse and Ashby expose the entire job board as a public JSON API as long as you know the `board_token` — no auth required.

| Pros                                          | Cons                                                       |
| --------------------------------------------- | ---------------------------------------------------------- |
| Fastest and most reliable                     | Breaks instantly if the company switches ATS               |
| Immune to HTML changes                        | You have to discover the board_token yourself              |
| Returns structured data (pagination, dates)   | OpenAI's Greenhouse → Ashby migration broke the old crawler |

---

### 4-2. Requests + BeautifulSoup (SSR scraping)

**Used by**: Upstage, Naver (secondary)

Parses fully server-rendered HTML statically. Naver also calls an internal AJAX API (`/rcrt/loadJobList.do`) directly to paginate as JSON.

```
requests.get(url)
  → parse HTML with BeautifulSoup → extract links via CSS selectors

or (Naver)
requests.get(ajax_api?firstIndex=N)
  → parse JSON → iterate pages
```

| Pros                                  | Cons                                       |
| ------------------------------------- | ------------------------------------------ |
| Fast. No browser required             | Can't be used on JS-rendered pages         |
| ~1/10 the resource use of Playwright  | Breaks immediately if the site moves to CSR |

---

### 4-3. Playwright + HTML/JS parsing (CSR/SPA rendering)

**Used by**: Google, Samsung, Toss

Runs a real headless Chromium browser, waits for JS rendering to finish, then parses the DOM.

```
launch Playwright Chromium
  → page.goto(url, wait_until="networkidle")
  → wait_for_selector(wait for a specific element)
  → page.evaluate()   ← walk the DOM directly in JS context
    or parse HTML with BeautifulSoup
```

**Why `page.evaluate()` for Google**
A CSS selector like `a[href*="..."]` matches against the literal `href` attribute string in the HTML, but Google's job links are mostly stored as absolute URLs (`https://...`), so only one element matches. The `a.href` property, on the other hand, always returns a full URL from the browser, so the JS-context evaluation must be used to collect them all.

```
querySelectorAll('a[href*="/jobs/results/"]')  →  1 hit   (HTML attribute basis)
filter via a.href property                     →  20 hits (full URL basis)
```

| Pros                                      | Cons                                            |
| ----------------------------------------- | ----------------------------------------------- |
| Handles JS-rendered pages                 | Slow (5–15s per page)                           |
| Identical DOM to a real browser           | Heavy memory use                                |
| Handles cookies/sessions automatically    | Selectors break when CSS classes are obfuscated |

---

### 4-4. Playwright XHR interception

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
The Workday page loads its listings through an internal API. Letting the browser load the page handles the session and CSRF token automatically, and since we just read the API responses the browser already receives, there's no need to reverse-engineer the API contract.

| Pros                                      | Cons                                              |
| ----------------------------------------- | ------------------------------------------------- |
| No manual session/CSRF handling           | Depends on Playwright                             |
| Works without knowing the API spec        | Breaks if the internal API format changes         |
| Handles sessions and CSRF automatically   | Has to wait for the page to load                  |

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
| `tests/data/role_holdout.tsv` | 79 | Random sample labeled *before* looking at predictions: generalization |

Held-out accuracy: previous keyword-priority classifier 65.8% (scored leniently against its coarser 7 categories),
new rules 87.3% on first run. Remaining misses are genuinely ambiguous titles (e.g. "Applied AI Engineer" in a
go-to-market team). Do not tune rules against the held-out file, or it stops being held out.

**Other derived fields** (`enrich.py`)

- `seniority`: 인턴 / 신입·주니어 / 경력 / 시니어 / 리더, from the title first, then site level tags (Google Early/Mid/Advanced, Upstage "경력 3년 이상")
- `employment`: 계약직 when the title or tags say contract / fixed-term / 계약
- `pool`: true for talent-pool / expression-of-interest posts (real listings, but not a specific opening)
- `regions`: 한국 / 북미 / 유럽 / 아시아·태평양 / 원격 / 기타 from the free-text location
- `first_seen`: carried over by URL from the previous `jobs.json`; a company newly added to the tracker gets an empty baseline instead of "new today"

---

## 6. Per-Crawler Details

| Crawler   | Approach                  | Pagination                          | Deadline filter         | Notes                                                  |
| --------- | ------------------------- | ----------------------------------- | ----------------------- | ------------------------------------------------------ |
| Anthropic | Greenhouse REST API       | None (API returns only active jobs) | `first_published` field | board_token: `anthropic`                               |
| OpenAI    | Ashby REST API            | None                                | Drops `isListed=false`  | board_token: `openai`                                  |
| Naver     | Internal AJAX JSON API    | `firstIndex` parameter              | Drops `endYmd < today`  | Total pages computed from the `totalRows` JS variable  |
| Google    | Playwright + JS evaluate  | Clicks `aria-label="Go to next page"` | None                  | Has to click the cookie banner first                   |
| NVIDIA    | Playwright XHR intercept  | None (initial load only)            | None                    | Workday internal API                                   |
| Samsung   | Playwright + BS4          | None                                | None                    | Waits on `jobOpeningView`; 0 results is normal off-cycle |
| Toss      | Playwright + BS4          | None                                | None                    | Next.js CSR; filters out nav links                     |
| Upstage   | Requests + BS4            | None                                | None                    | Greeting HR SSR, `/ko/o/{id}` pattern                  |
| Greenhouse boards | REST API          | None                                | —                       | Figure AI, Skild AI, Agility, Waymo, Motional, LG AI연구원 |
| Ashby boards | REST API               | None                                | Drops `isListed=false`  | 42dot, 1X, Physical Intelligence, Wayve                |
| Workday (generic) | JSON POST `/wday/cxs/…/jobs` | `offset` += 20 until `total` | —                     | Boston Dynamics (all), Intel (Korea via `locationsText`) |
| Qualcomm  | Eightfold `/api/pcsx/search` | `start` += 10                 | —                       | `location=Korea`                                       |
| AMD       | Jibe `/api/jobs`          | `page`, 100 per page                | —                       | `location=Korea`, re-checked on `full_location`        |
| MediaTek  | tRPC `job.getJobs`        | One call (limit 1000)               | —                       | Keeps Korean sites (Seongnam)                          |
| LG전자    | LG Careers JSON POST      | One call                            | `recEndDateTime`        | companyCode LGE, RBO (로보스타)                         |
| SK하이닉스 | SK Careers form POST     | One call                            | `end`                   | SK hynix, SK telecom only                              |

---

## 7. Data Schema

### jobs.json

```json
{
  "updated_at": "2026-10-09T16:26:00+00:00",
  "total": 3086,
  "results": { "Anthropic": 646, "OpenAI": 818 },
  "sources": {
    "Google": { "company": "Google", "category": "외국계", "sectors": ["AI 연구소"],
                "count": 20, "status": "stale", "last_success": "2026-10-06" }
  },
  "taxonomy": { "groups": { "엔지니어링": ["AI / ML", "..."] }, "levels": ["인턴", "..."], "regions": ["한국", "..."] },
  "jobs": [ ... ]
}
```

`sources[*].status` is `stale` when a crawler returned 0 after previously returning postings: the previous
postings are kept and the dashboard shows a warning with `last_success`. After 7 days of continuous failure
(`STALE_MAX_DAYS`, counted from `stale_since`) the status becomes `failed` and those postings are dropped, so
closed jobs don't linger. A normal run replaces each company's postings wholesale, so a closed job disappears
on the next successful crawl. `taxonomy` lets the dashboard render filters without hard-coding role names.

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
  "posted_date": "2026-10-02T01:12:44.000+00:00",
  "seniority": "",
  "employment": "",
  "regions": ["한국"],
  "first_seen": "",
  "crawled_at": "2026-10-09T16:26:00+00:00"
}
```

| Field         | Description                                                        |
| ------------- | ------------------------------------------------------------------ |
| `category`    | Company bucket (외국계 / 대기업 / IT / 금융 / 제조업 / 스타트업)       |
| `role`, `role_group` | Role and family, assigned by `classifier.py`                |
| `tags`        | Optional site tags (Toss tech tags, Upstage experience, Google level) |
| `posted_date` | Format varies per company (ISO 8601 / YYYY-MM-DD)                  |
| `first_seen`  | KST date this URL first appeared ("" = before tracking / baseline) |
| `crawled_at`  | Collection time (always ISO 8601)                                  |

---

## 8. Configuration

### config.json

```json
{
  "schedule": {
    "enabled": false,
    "interval": "daily",
    "last_updated": "2026-05-01T15:00:00"
  },
  "crawlers": {
    "NVIDIA": true,
    "Google": true,
    "Anthropic": true,
    "OpenAI": true,
    "Samsung": true,
    "Naver": true,
    "Toss": true,
    "Upstage": true
  }
}
```

- `schedule.enabled`: Whether the GitHub Actions schedule runs (toggle with `toggle_schedule.py`)
- `crawlers.<name>`: When `false`, the crawler is skipped in the default `python main.py` run

---

## 9. GitHub Actions Automation

**File**: `.github/workflows/daily-crawl.yml`

```
Daily at 00:00 UTC (09:00 KST)
  → check schedule.enabled in config.json
  → only run if true:
      pip install (with pip cache)
      install Playwright chromium (cache keyed on requirements.txt hash)
      python main.py
      git add -f docs/data/jobs.json config.json
      git commit & push
```

**Key settings**

| Setting                       | Value                          | Reason                                                  |
| ----------------------------- | ------------------------------ | ------------------------------------------------------- |
| `concurrency: group: crawl`   | Limit to 1 concurrent run      | Prevents push conflicts from overlapping runs           |
| `timeout-minutes: 60`         | 60 minutes                     | Caps runner time if Playwright hangs                    |
| `cache: "pip"`                | pip cache                      | Skips dependency reinstall                              |
| Playwright cache              | Key on `requirements.txt` hash | Avoids re-downloading the browser binary                |

**Note**: The `-f` flag on `git add` is required. `docs/data/jobs.json` is in `.gitignore`, so without `-f` it wouldn't be staged and the commit would be skipped.

---

### Failure reporting

When a company comes back empty, the run says *why* in three places:

- **Data / dashboard**: `sources[name].error` holds the reason (an HTTP status with a hint such as "429 rate limit",
  a browser load error, "page loaded but no job links: page title …", a crawler exception, or
  "0 with no error recorded"). The dashboard's warning banner shows it.
- **Console**: a "수집 문제 요약" table at the end of every run, including sharp drops (more than 50% fewer postings than last time).
- **GitHub Actions**: `::error` / `::warning` annotations at the top of the run page, plus a per-company status
  table in the job summary. The crawl step still exits 1 so the run turns red.

Crawlers report problems through `BaseCrawler.warn()` rather than `print`, so a failure is never silent.

## 10. Adding a New Crawler

### Step 1 — Create the crawler file

```python
# crawlers/newcompany.py
from .base import BaseCrawler

class NewCompanyCrawler(BaseCrawler):
    def __init__(self):
        super().__init__("NewCompany", "Category")  # Global / IT / Finance / Startup / Manufacturing
        self.url = "https://..."

    def fetch_jobs(self):
        jobs = []
        resp = self.safe_request(self.url)
        if not resp:
            return jobs
        # parsing logic
        jobs.append(self.format_job(
            title="...",
            url="...",
            location="...",
            department="...",
            posted_date="..."
        ))
        return jobs
```

Calling `format_job()` attaches the `role` classification automatically.

### Step 2 — Register it

```python
# crawlers/__init__.py
from .newcompany import NewCompanyCrawler

def get_all_crawlers():
    return {
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

### Recommended approach per site type

| Site type                       | Recommended approach                                                   |
| ------------------------------- | ---------------------------------------------------------------------- |
| Greenhouse / Ashby / Lever ATS  | Add the board_token to `generic_greenhouse.py` or `generic_ashby.py`   |
| SSR (server-rendered)           | `safe_request()` + BeautifulSoup                                       |
| CSR / SPA (React, Next.js)      | `playwright_fetch()`                                                   |
| SPA backed by an internal API   | `playwright_intercept()`                                               |
