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
│   ├── classifier.py        # Role classifier (keywords + transformer)
│   ├── google.py            # Google — Playwright + JS evaluate
│   ├── nvidia.py            # NVIDIA — Playwright XHR interception
│   ├── samsung.py           # Samsung — Playwright + conditional waits
│   ├── naver.py             # Naver — internal AJAX API
│   ├── toss.py              # Toss — Playwright (Next.js)
│   ├── upstage.py           # Upstage — Requests + BeautifulSoup
│   ├── generic_greenhouse.py # Shared Greenhouse ATS crawler
│   └── generic_ashby.py     # Shared Ashby ATS crawler
├── docs/                    # Static web UI (GitHub Pages)
│   ├── index.html
│   ├── style.css
│   ├── app.js
│   └── data/
│       └── jobs.json        # Crawl output (auto-generated)
├── .github/workflows/
│   └── daily-crawl.yml      # GitHub Actions workflow (daily 09:00 KST)
├── main.py                  # Crawler entry point
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
              (keywords → transformer)
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
- **Singleton**: The transformer model in `classifier.py` is loaded once per process.

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
Hitting the Workday API directly with POST returns 400 because of missing CSRF tokens and session cookies. Letting the browser load the page establishes the session automatically, bypassing the block; and since we just intercept the API calls the browser already makes, there's no need to reverse-engineer the API contract.

| Pros                                      | Cons                                              |
| ----------------------------------------- | ------------------------------------------------- |
| Bypasses bot blocks (400)                 | Depends on Playwright                             |
| Works without knowing the API spec        | Could be re-blocked if responses become encrypted |
| Handles sessions and CSRF automatically   | Has to wait for the page to load                  |

---

## 5. Role Classification

**File**: `crawlers/classifier.py`

Each posting's `title` is automatically mapped to one of 7 role categories.

```
title input
   │
   ▼
[Step 1] Keyword matching
   │  Search KEYWORD_MAP per category in priority order
   │  Return immediately on match
   │ no match
   ▼
[Step 2] Transformer embedding similarity (zero-shot)
   │  Model: paraphrase-multilingual-MiniLM-L12-v2 (~420MB)
   │  Supports Korean + English; runs on CPU
   │
   │  1. Embed anchor sentences per category up-front
   │  2. Compute cosine similarity against the title embedding
   │  3. Pick the highest-similarity category
   │
   ├── similarity ≥ 0.28 → return that category
   └── similarity < 0.28 → "Other"
```

**Keyword check order (priority)**

```
AI/ML → Security → Sales/BD → Marketing → Product/Planning → Operations → Engineering
```

Order matters: "Security Engineer" must be checked under Security before Engineering, or it would be misclassified. Likewise "ML Engineer" needs AI/ML to come before Engineering.

**Performance** (1,448 postings)

- "Other" rate: under ~1%
- Initial model load: ~3s (then cached, no reload)
- Inference throughput: ~1,000 titles/sec on CPU

**7 role categories**

| Category              | Representative titles                                |
| --------------------- | ---------------------------------------------------- |
| Engineering           | Software Engineer, Backend, Frontend, DevOps, SRE    |
| AI / ML               | Research Scientist, ML Engineer, Data Scientist, LLM |
| Security              | Security Engineer, AML, Compliance, KYC, SOX         |
| Sales / BD            | Account Executive, Sales, Business Development, GTM  |
| Marketing             | Marketing Manager, PR, Communications                |
| Product / Planning    | Product Manager, Program Manager, Designer, UX       |
| Operations / G&A      | Operations, Finance, HR, Legal, Administrative       |

---

## 6. Per-Crawler Details

| Crawler   | Approach                  | Pagination                          | Deadline filter         | Notes                                                  |
| --------- | ------------------------- | ----------------------------------- | ----------------------- | ------------------------------------------------------ |
| Anthropic | Greenhouse REST API       | None (API returns only active jobs) | `first_published` field | board_token: `anthropic`                               |
| OpenAI    | Ashby REST API            | None                                | Drops `isListed=false`  | board_token: `openai`                                  |
| Naver     | Internal AJAX JSON API    | `firstIndex` parameter              | Drops `endYmd < today`  | Total pages computed from the `totalRows` JS variable  |
| Google    | Playwright + JS evaluate  | Clicks `aria-label="Go to next page"` | None                  | Has to click the cookie banner first                   |
| NVIDIA    | Playwright XHR intercept  | None (initial load only)            | None                    | Bypasses Workday bot block                             |
| Samsung   | Playwright + BS4          | None                                | None                    | Waits on `jobOpeningView`; 0 results is normal off-cycle |
| Toss      | Playwright + BS4          | None                                | None                    | Next.js CSR; filters out nav links                     |
| Upstage   | Requests + BS4            | None                                | None                    | Greeting HR SSR, `/ko/o/{id}` pattern                  |

---

## 7. Data Schema

### jobs.json

```json
{
  "updated_at": "2026-05-01T15:20:04.123456",
  "total": 1448,
  "results": {
    "Anthropic": 439,
    "OpenAI": 667
  },
  "jobs": [ ... ]
}
```

### Single job object

```json
{
  "company": "Anthropic",
  "category": "Global",
  "role": "AI / ML",
  "title": "Research Scientist",
  "url": "https://...",
  "location": "San Francisco, CA",
  "department": "Research",
  "posted_date": "2026-03-25T10:53:39-04:00",
  "crawled_at": "2026-05-01T15:20:04.123456"
}
```

| Field         | Description                                                        |
| ------------- | ------------------------------------------------------------------ |
| `category`    | Company bucket (Global / IT / Finance / Startup / Manufacturing)   |
| `role`        | Role bucket (7 + Other) — assigned automatically by classifier.py  |
| `posted_date` | Format varies per company (ISO 8601 / YYYY-MM-DD / free text)      |
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
| API that blocks bots            | `playwright_intercept()`                                               |
