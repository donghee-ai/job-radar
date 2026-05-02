# Job Radar

> Personal job tracker that aggregates openings from 20+ top tech companies — built to streamline my own job search.

[![Python](https://img.shields.io/badge/Python-3.11-blue)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![GitHub Actions](https://img.shields.io/badge/CI-GitHub%20Actions-blue)](https://github.com/features/actions)

**[Live Demo](https://donghee-ai.github.io/job-radar/)** • **[Architecture](ARCHITECTURE.md)**

---

## Why I Built This

Tired of checking 20+ career pages every week, I built a unified dashboard that automatically aggregates job postings from companies I'm interested in — including global tech giants (NVIDIA, OpenAI, Anthropic), Korean IT (Naver, Toss), and AI startups (Upstage, Furiosa).

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
# 1. 저장소 클론
git clone https://github.com/donghee-ai/job-radar.git
cd job-radar

# 2. 가상환경 생성 및 활성화
python -m venv venv

# Windows
venv\Scripts\activate
# Mac / Linux
# source venv/bin/activate

# 3. 패키지 설치
pip install -r requirements.txt

# 4. Playwright 브라우저 바이너리 설치
#    (pip 설치만으로는 부족 — 이 단계를 빠뜨리면 Google/Samsung/Toss/NVIDIA 크롤러 실패)
playwright install chromium
```

### Usage

```bash
# 전체 크롤링 (config.json에서 활성화된 회사)
python main.py

# 특정 회사만
python main.py Google NVIDIA Toss

# 모든 회사 강제 실행
python main.py --all

# 로컬 대시보드 열기
python server.py
```

### GitHub Pages 라이브 데모 설정 (선택)

1. GitHub 리포지토리 → **Settings** → **Pages**
2. Source: `Deploy from a branch` → Branch: `main` / `docs` → Save
3. 잠시 후 `https://donghee-ai.github.io/job-radar/` 에서 접근 가능

### GitHub Actions 자동화 (선택)

매일 09:00 KST에 자동 크롤링하려면:

```bash
python toggle_schedule.py on   # 활성화
python toggle_schedule.py off  # 비활성화
```

활성화 후 변경사항을 push하면 이후부터 매일 자동 실행됩니다.

---

## Architecture

Python 크롤러 (`crawlers/`) → `docs/data/jobs.json` → GitHub Pages 정적 UI.
자세한 내용은 [ARCHITECTURE.md](ARCHITECTURE.md) 참고.
