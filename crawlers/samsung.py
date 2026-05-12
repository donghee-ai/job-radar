# ============================================================
# Samsung 크롤러
# ============================================================
# 방식: Playwright (헤드리스 Chromium) → BeautifulSoup HTML 파싱
# URL: https://www.samsungcareers.com/hr/
#
# [시행착오]
# 1~4: 이전 실패 이력은 git history 참조.
#
# 5. a[href*='jobOpeningView'] 셀렉터로 공고 링크 대기
#    → 2025-05 기준 페이지 리뉴얼로 링크 구조 변경됨.
#      공고가 ul.job#list > li 안에 a[data-value] href="/#none" 형태로 렌더링.
#      jobOpeningView 패턴이 사라져서 항상 0건 반환.
#
# [현재 방식]
# Playwright로 페이지 완전 렌더링 후 HTML 파싱.
# 대기 전략을 두 단계로 분리:
#   1단계: wait_until="networkidle" (XHR/fetch 완료)
#   2단계: wait_for_selector("ul.job#list li a[data-value]", timeout=10000)
#          → 실제 공고 카드가 DOM에 나타날 때까지 명시적 대기.
#          → 타임아웃 시 (공고 없는 기간) TimeoutError를 무시하고 현재 HTML 파싱.
#
# 파싱: ul.job#list > li 내부에서 회사명(.company), 제목(.title),
#       기간(.period), data-value(공고 ID)를 추출.
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
        job_list = soup.select_one("ul.job#list")
        if not job_list:
            return jobs

        seen = set()
        for li in job_list.find_all("li"):
            a = li.select_one("a[data-value]")
            if not a:
                continue
            job_id = a.get("data-value", "").strip()
            if not job_id or job_id in seen:
                continue
            seen.add(job_id)

            company = a.select_one(".company")
            title_el = a.select_one(".title")
            title_text = title_el.get_text(strip=True) if title_el else ""
            company_text = company.get_text(strip=True) if company else ""
            if company_text and title_text:
                title_text = f"[{company_text}] {title_text}"

            if not title_text:
                continue

            detail_url = f"https://www.samsungcareers.com/hr/?id={job_id}"
            jobs.append(self.format_job(title=title_text, url=detail_url))
        return jobs

    def _fetch_with_job_wait(self) -> str:
        """networkidle 후 공고 카드가 렌더링될 때까지 추가 대기."""
        try:
            from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(user_agent=self.headers['User-Agent'])
                page = context.new_page()
                page.goto(self.url, wait_until="networkidle", timeout=30000)

                # 공고 카드가 나타날 때까지 최대 10초 추가 대기
                # 공고가 없는 시즌에는 TimeoutError → 현재 HTML 그대로 반환
                try:
                    page.wait_for_selector("ul.job#list li a[data-value]", timeout=10000)
                except PWTimeout:
                    pass

                content = page.content()
                browser.close()
                return content
        except Exception as e:
            print(f"  ⚠️  [Samsung] Playwright error: {e}")
            return ""
