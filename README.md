# Job Radar

> Personal job tracker that aggregates openings from 20+ top tech companies — built to streamline my own job search.

[![Python](https://img.shields.io/badge/Python-3.11-blue)](https://python.org)
[![License](https://img.shields.io/badge/License-MIT-green)](LICENSE)
[![GitHub Actions](https://img.shields.io/badge/CI-GitHub%20Actions-blue)](https://github.com/features/actions)

**[Live Demo](https://USERNAME.github.io/job-radar/)** • **[Screenshots](#screenshots)**

---

## Why I Built This

Tired of checking 20+ career pages every week, I built a unified dashboard that automatically aggregates job postings from companies I'm interested in — including global tech giants (NVIDIA, OpenAI, Anthropic), Korean IT (Naver, Toss), and AI startups (Upstage, Furiosa).

## Features

- **Multi-source crawling** — Supports Workday, Greenhouse, Lever, and custom APIs
- **Clean local dashboard** — Apple-inspired UI with category/company filters
- **Manual-first, auto-optional** — Run on demand or enable weekly automation
- **Extensible architecture** — Add new companies by inheriting `BaseCrawler`
- **Zero-cost deployment** — Pure static site + GitHub Actions

## Architecture
