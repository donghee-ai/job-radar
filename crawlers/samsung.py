# ============================================================
# Samsung 크롤러
# ============================================================
# 방식: Playwright (헤드리스 Chromium) → BeautifulSoup HTML 파싱
# URL: https://www.samsungcareers.com/hr/
#
# [시행착오]
# 1. POST API /hr/svc/svchr.GetJobOpeningList.do (countryCd: KR, pageSize: 100)
#    → 404. 내부 API 엔드포인트 변경됨.
#
# 2. 다양한 API 경로 추측 시도
#    (/hr/usr/job/jobOpeningList.do, /hr/api/job/list 등 10여 개)
#    → 전부 404. 브라우저 DevTools 없이는 정확한 경로 파악 불가.
#
# 3. requests + BeautifulSoup로 /hr/ 페이지 스크래핑
#    → 삼성 채용 페이지도 JS 렌더링이라 공고 목록이 HTML에 없음.
#
# 4. playwright_fetch(url) — wait_selector 인자 없이 호출 (기본값 "body")
#    → networkidle 이후에도 JS가 비동기로 공고 카드를 추가 렌더링함.
#      "body" 존재 여부만 체크하면 렌더링 완료 전에 HTML을 캡처하게 돼
#      jobOpeningView 링크가 하나도 없는 상태로 파싱 → 항상 0건.
#      실제로 공고가 있어도 0건으로 잘못 반환됨.
#
# [현재 방식]
# Playwright로 페이지 완전 렌더링 후 HTML 파싱.
# 대기 전략을 두 단계로 분리:
#   1단계: wait_until="networkidle" (XHR/fetch 완료)
#   2단계: wait_for_selector("a[href*='jobOpeningView']", timeout=10000)
#          → 실제 공고 링크가 DOM에 나타날 때까지 명시적 대기.
#          → 타임아웃 시 (공고 없는 기간) TimeoutError를 무시하고 현재 HTML 파싱.
#
# [참고] 삼성은 수시채용이라 공고가 없는 기간에는 정상적으로 0건 반환.
# ============================================================

from bs4 import BeautifulSoup
from .base import BaseCrawler


class SamsungCrawler(BaseCrawler):
    def __init__(self):
        super().__init__("Samsung", "제조업", default_location="Seoul, South Korea")
        self.url = "https://www.samsungcareers.com/hr/"

    def fetch_jobs(self):
        jobs = []
        html = self._fetch_with_job_wait()
        if not html:
            return jobs

        soup = BeautifulSoup(html, "html.parser")
        seen = set()
        for a in soup.select("a[href*='jobOpeningView']"):
            href = a.get("href", "")
            title = a.get_text(strip=True)
            if not title or href in seen:
                continue
            seen.add(href)
            full_url = "https://www.samsungcareers.com" + href if href.startswith("/") else href
            jobs.append(self.format_job(title=title, url=full_url))
        return jobs

    def _fetch_with_job_wait(self) -> str:
        """networkidle 후 jobOpeningView 링크가 렌더링될 때까지 추가 대기."""
        try:
            from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(user_agent=self.headers['User-Agent'])
                page = context.new_page()
                page.goto(self.url, wait_until="networkidle", timeout=30000)

                # 공고 링크가 나타날 때까지 최대 10초 추가 대기
                # 공고가 없는 시즌에는 TimeoutError → 현재 HTML 그대로 반환
                try:
                    page.wait_for_selector("a[href*='jobOpeningView']", timeout=10000)
                except PWTimeout:
                    pass

                content = page.content()
                browser.close()
                return content
        except Exception as e:
            print(f"  ⚠️  [Samsung] Playwright error: {e}")
            return ""
