# Job Radar

> Personal job tracker that aggregates openings from 20+ top tech companies — built to streamline my own job search.

[![Python](https://img.shields.io/badge/Python-3.11-blue)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![GitHub Actions](https://img.shields.io/badge/CI-GitHub%20Actions-blue)](https://github.com/features/actions)

**[Live Demo](https://donghee-ai.github.io/job-radar/)** • **[Architecture](ARCHITECTURE.md)**

---

## Why I Built This

Tired of checking 20+ career pages every week, I built a unified dashboard that automatically aggregates job postings from companies I'm interested in — including global tech giants (NVIDIA, OpenAI, Anthropic), Korean IT (Naver, Toss), and AI startups (Upstage).

## Features

- **Multi-source crawling** — Supports Workday, Greenhouse, Lever, and custom APIs
- **Clean local dashboard** — Apple-inspired UI with category/company filters
- **Manual-first, auto-optional** — Run on demand or enable daily automation
- **Extensible architecture** — Add new companies by inheriting `BaseCrawler`
- **Zero-cost deployment** — Pure static site + GitHub Actions

## Setup

### Requirements

- Python 3.11+
- Git

### Installation

```bash
# 1. Clone the repository
git clone https://github.com/donghee-ai/job-radar.git
cd job-radar

# 2. Create and activate virtual environment
python -m venv venv

# Windows
venv\Scripts\activate
# Mac / Linux
# source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Install Playwright browser binaries
#    (pip install alone is not enough — skipping this step will break Google/Samsung/Toss/NVIDIA crawlers)
playwright install chromium
```

### Usage

```bash
# Crawl all enabled companies (see config.json)
python main.py

# Crawl specific companies only
python main.py Google NVIDIA Toss

# Force-crawl all companies
python main.py --all

# Open local dashboard
python server.py
```

### GitHub Pages Live Demo (Optional)

1. Go to your GitHub repository → **Settings** → **Pages**
2. Source: `Deploy from a branch` → Branch: `main` / `docs` → Save
3. After a moment, your site will be available at `https://donghee-ai.github.io/job-radar/`

### GitHub Actions Automation (Optional)

To enable daily auto-crawling at 09:00 KST:

```bash
python toggle_schedule.py on   # Enable
python toggle_schedule.py off  # Disable
```

Push the changes after enabling, and the workflow will run automatically every day.

---

## Architecture

Python crawlers (`crawlers/`) → `docs/data/jobs.json` → GitHub Pages static UI.
See [ARCHITECTURE.md](ARCHITECTURE.md) for details.
