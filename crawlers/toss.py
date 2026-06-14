# ============================================================
# Toss 크롤러
# ============================================================
# 방식: Playwright (헤드리스 Chromium) → BeautifulSoup HTML 파싱
# URL: https://toss.im/career/jobs
#
# [시행착오]
# 1. Greenhouse API boards-api.greenhouse.io/v1/boards/toss/jobs
#    → 404. Toss가 Greenhouse를 사용하지 않거나 board token이 다름.
#    tossinc, vivarepublica 등 다른 토큰도 시도 → 전부 404.
#
# 2. requests + BeautifulSoup로 toss.im/career/jobs 스크래핑
#    → "0개의 포지션이 열려있어요" 만 보임.
#      toss.im은 Next.js 앱 (CSR)이라 공고 목록이 JS로 동적 로드됨.
#      requests는 JS를 실행하지 못하므로 빈 껍데기만 받게 됨.
#
# [현재 방식]
# Playwright로 실제 Chromium을 실행, networkidle 상태까지 대기해
# Next.js 앱이 공고 목록 API를 호출하고 렌더링 완료 후 HTML을 받음.
# /career/ 경로를 가진 링크 중 네비게이션(_NAV_PATHS)을 제외한
# 것들이 실제 채용 공고 링크임.
# 상세 페이지: 동일 Playwright 세션으로 각 공고 URL 방문해 자격 요건 추출.
# ============================================================

from bs4 import BeautifulSoup
from .base import BaseCrawler

# 채용공고가 아닌 네비게이션 링크 (필터링용)
_NAV_PATHS = {"/career/joining-guide", "/career/culture", "/career/article", "/career/jobs", "/career/faq"}


class TossCrawler(BaseCrawler):
    def __init__(self):
        super().__init__("Toss", "금융", default_location="Seoul, South Korea")
        self.url = "https://toss.im/career/jobs"

    def fetch_jobs(self):
        jobs = []
        try:
            from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                ctx = browser.new_context(user_agent=self.headers['User-Agent'])
                pg = ctx.new_page()
                pg.goto(self.url, wait_until="networkidle", timeout=30000)

                html = pg.content()
                soup = BeautifulSoup(html, "html.parser")
                seen = set()
                job_entries = []  # (title, full_url)

                for a in soup.select("a[href*='/career/']"):
                    href = a.get("href", "")
                    if not href or href in seen:
                        continue
                    if any(href.startswith(nav) or href == nav for nav in _NAV_PATHS):
                        continue
                    seen.add(href)
                    title = a.get_text(strip=True)
                    if not title:
                        continue
                    full_url = "https://toss.im" + href if href.startswith("/") else href
                    job_entries.append((title, full_url))

                # 상세 페이지 방문해 자격 요건 + 고용형태 추출
                for title, full_url in job_entries:
                    desc = ""
                    emp_type = ""
                    try:
                        pg.goto(full_url, wait_until="domcontentloaded", timeout=15000)
                        pg.wait_for_timeout(3000)
                        detail_html = pg.content()
                        desc = self.extract_qualifications(detail_html)
                        emp_type = self._extract_employment_type(detail_html)
                    except Exception:
                        pass
                    jobs.append(self.format_job(
                        title=title, url=full_url, description=desc,
                        employment_type=emp_type, salary="협의"
                    ))

                browser.close()
        except Exception as e:
            print(f"  ⚠️  [Toss] Playwright error: {e}")

        return jobs

    @staticmethod
    def _extract_employment_type(html: str) -> str:
        """상세 페이지 텍스트에서 정규직/계약직 등 고용형태 추출."""
        soup = BeautifulSoup(html, "html.parser")
        text = soup.get_text()
        for keyword in ["정규직", "계약직", "인턴", "파견직"]:
            if keyword in text:
                return keyword
        return ""
