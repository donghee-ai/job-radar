"""
대시보드(docs/) 화면 테스트 — 실제 브라우저(Playwright)로 페이지를 띄워 확인한다.

실데이터는 매일 바뀌므로 테스트마다 작은 jobs.json을 만들어 임시 폴더에서 서빙한다.
Playwright 브라우저가 설치돼 있지 않으면 건너뛴다 (playwright install chromium).
"""
import json
import os
import shutil
import threading
from datetime import datetime, timedelta, timezone
from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

sync_api = pytest.importorskip("playwright.sync_api")

DOCS = Path(__file__).resolve().parent.parent / "docs"
KST = timezone(timedelta(hours=9))


def kst_day(days_ago=0):
    return (datetime.now(KST) - timedelta(days=days_ago)).date().isoformat()


def job(title, role="소프트웨어 개발", group="엔지니어링", seen_days_ago=0, company="TestCo", **extra):
    return {
        "company": company, "category": "외국계", "title": title, "url": f"https://example.com/{title}",
        "role": role, "role_group": group, "location": "Seoul, South Korea", "department": "",
        "posted_date": "", "seniority": "", "employment": "", "pool": False, "regions": ["한국"],
        "first_seen": kst_day(seen_days_ago), **extra,
    }


def dataset(jobs, updated_days_ago=0):
    updated = datetime.now(timezone.utc) - timedelta(days=updated_days_ago)
    companies = sorted({j["company"] for j in jobs})
    return {
        "updated_at": updated.isoformat(), "total": len(jobs),
        "results": {c: sum(j["company"] == c for j in jobs) for c in companies},
        "sources": {c: {"company": c, "category": "외국계", "sectors": [], "count": 1,
                        "status": "ok", "last_success": kst_day(updated_days_ago)} for c in companies},
        "jobs": jobs,
    }


DEFAULT_JOBS = [
    job("Backend Engineer", seen_days_ago=0),
    job("Server Developer", seen_days_ago=3),
    job("Frontend Engineer", seen_days_ago=3),
    job("Account Executive", role="영업 / 사업개발", group="비즈니스", seen_days_ago=10, company="OtherCo"),
]


@pytest.fixture(scope="module")
def browser():
    with sync_api.sync_playwright() as p:
        try:
            b = p.chromium.launch()
        except Exception as e:  # 브라우저 바이너리 없음
            # 로컬에선 건너뛰지만, CI(REQUIRE_BROWSER_TESTS=1)에선 조용히 빠지면 안 되므로 실패
            if os.environ.get("REQUIRE_BROWSER_TESTS") == "1":
                raise
            pytest.skip(f"Playwright 브라우저가 없음 (playwright install chromium): {e}")
        yield b
        b.close()


@pytest.fixture
def site(tmp_path):
    """docs를 임시 폴더에 복사해 서빙. site.write(data)로 jobs.json을 바꾼다."""
    root = tmp_path / "site"
    shutil.copytree(DOCS, root, ignore=shutil.ignore_patterns("data", "screenshot.png"))
    (root / "data").mkdir()

    class Site:
        url = ""

        @staticmethod
        def write(data):
            (root / "data" / "jobs.json").write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")

        @staticmethod
        def remove_data():
            (root / "data" / "jobs.json").unlink(missing_ok=True)

    handler = partial(SimpleHTTPRequestHandler, directory=str(root))
    handler.log_message = lambda *a: None
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    Site.url = f"http://127.0.0.1:{server.server_address[1]}/"
    Site.write(dataset(DEFAULT_JOBS))
    yield Site
    server.shutdown()


@pytest.fixture
def page(browser):
    ctx = browser.new_context(viewport={"width": 1280, "height": 900})
    # 외부 폰트는 테스트와 무관 — 네트워크 없이도 돌게 막는다
    ctx.route("https://cdn.jsdelivr.net/**", lambda route: route.abort())
    pg = ctx.new_page()
    errors = []
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.errors = errors
    yield pg
    ctx.close()


def open_page(page, site, query=""):
    page.goto(site.url + query)
    page.wait_for_selector("#jobs .job, #empty:not([hidden]), #retry", state="attached")


def titles(page):
    return page.eval_on_selector_all(".job-title", "els => els.map(e => e.textContent.trim())")


def active(page, attr):
    return page.evaluate(f"document.activeElement && document.activeElement.getAttribute('{attr}')")


# ── 1. 날짜 기준 ────────────────────────────────────────────────────────

def test_new_badge_and_relative_date_for_today(page, site):
    open_page(page, site)
    row = page.locator(".job", has_text="Backend Engineer")
    assert row.locator(".badge-new").count() == 1
    assert row.locator(".job-date").inner_text() == "오늘"
    assert page.locator("#updated").inner_text().startswith("오늘 ")
    assert not page.errors


def test_dates_use_viewing_day_when_data_is_stale(page, site):
    # 수집이 5일 멈춘 상황: 5일 전에 처음 본 공고는 '5일 전'이고 NEW가 아니어야 한다
    site.write(dataset([job("Backend Engineer", seen_days_ago=5)], updated_days_ago=5))
    open_page(page, site)
    row = page.locator(".job").first
    assert row.locator(".badge-new").count() == 0
    assert row.locator(".job-date").inner_text() == "5일 전"
    assert page.locator("#updated").inner_text().startswith("5일 전 ")


# ── 검색 ────────────────────────────────────────────────────────────────

def test_related_search_finds_synonyms(page, site):
    open_page(page, site, "?q=백엔드")
    found = titles(page)
    assert "Backend Engineer" in found and "Server Developer" in found
    assert "Frontend Engineer" not in found
    assert page.locator("#search-hint").is_visible()


def test_url_state_restores_filters(page, site):
    open_page(page, site, "?group=비즈니스")
    assert titles(page) == ["Account Executive"]
    assert page.locator('#group-tabs [data-group="비즈니스"]').get_attribute("aria-pressed") == "true"


# ── 2. 키보드 ───────────────────────────────────────────────────────────

def test_group_tab_keeps_focus_after_keyboard_activation(page, site):
    open_page(page, site)
    page.focus('#group-tabs [data-group="비즈니스"]')
    page.keyboard.press("Enter")
    assert active(page, "data-group") == "비즈니스"
    assert titles(page) == ["Account Executive"]
    # 다시 그려진 뒤에도 Tab 순서가 이어진다
    page.keyboard.press("Tab")
    assert active(page, "data-group") is not None


def test_toggle_chip_keeps_focus(page, site):
    open_page(page, site)
    page.focus('#filter-chips [data-toggle="kr"]')
    page.keyboard.press("Space")
    assert active(page, "data-toggle") == "kr"


def test_menu_keyboard_navigation(page, site):
    open_page(page, site)
    page.focus('#filter-chips [data-menu="company"]')
    page.keyboard.press("Enter")
    assert page.locator("#popover").is_visible()
    assert page.evaluate("document.getElementById('popover').contains(document.activeElement)")
    assert page.locator('[data-menu="company"]').get_attribute("aria-expanded") == "true"

    # Esc → 닫히고 칩으로 돌아온다
    page.keyboard.press("Escape")
    assert page.locator("#popover").is_hidden()
    assert active(page, "data-menu") == "company"

    # 화살표로 내려가 고르면 필터가 걸리고 포커스는 칩에 남는다
    page.keyboard.press("Enter")
    page.keyboard.press("End")
    picked = page.evaluate("document.activeElement.dataset.v")
    page.keyboard.press("Enter")
    assert active(page, "data-menu") == "company"
    assert page.locator('[data-menu="company"]').inner_text().strip() == picked
    assert all(t for t in titles(page))


def test_menu_tab_closes_and_returns_to_chip(page, site):
    open_page(page, site)
    page.focus('#filter-chips [data-menu="region"]')
    page.keyboard.press("Enter")
    page.keyboard.press("Tab")
    assert page.locator("#popover").is_hidden()
    assert active(page, "data-menu") == "region"


# ── 3. 모바일 ───────────────────────────────────────────────────────────

def test_mobile_shows_update_time_and_job_dates(browser, site):
    ctx = browser.new_context(viewport={"width": 390, "height": 844})
    ctx.route("https://cdn.jsdelivr.net/**", lambda route: route.abort())
    page = ctx.new_page()
    open_page(page, site)
    assert page.locator("#updated").is_visible()
    meta = page.locator(".job", has_text="Server Developer").locator(".job-meta").inner_text()
    assert "3일 전" in meta
    assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
    ctx.close()


# ── 5. 로딩 실패 ────────────────────────────────────────────────────────

def test_load_failure_shows_retry_without_dev_instructions(page, site):
    site.remove_data()
    open_page(page, site)
    assert "불러오지 못했어요" in page.locator("#hero-title").inner_text()
    assert "python" not in page.locator("body").inner_text()
    assert page.locator("main").is_hidden()

    site.write(dataset(DEFAULT_JOBS))
    page.click("#retry")
    page.wait_for_selector("#jobs .job")
    assert page.locator("main").is_visible()
    assert len(titles(page)) == len(DEFAULT_JOBS)
