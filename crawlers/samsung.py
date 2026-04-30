# ============================================================
# Samsung 크롤러
# ============================================================
# 방식: Playwright (헤드리스 Chromium) → BeautifulSoup HTML 파싱
# URL: https://www.samsungcareers.com/hr/
#
# [시행착오]
# 1. POST API /hr/svc/svchr.GetJobOpeningList.do (countryCd: KR, pageSize: 100)
#    → 404. 내부 API 엔드포인트가 변경됨.
#
# 2. 다양한 API 경로 추측 시도
#    (/hr/usr/job/jobOpeningList.do, /hr/api/job/list 등 10여 개)
#    → 전부 404. 브라우저 DevTools 없이는 정확한 경로 파악 불가.
#
# 3. requests + BeautifulSoup로 /hr/ 페이지 스크래핑
#    → 삼성 채용 페이지도 JS 렌더링이라 공고 목록이 HTML에 없음.
#
# [현재 방식]
# Playwright로 페이지를 완전히 렌더링한 뒤 HTML에서
# jobOpeningView가 포함된 링크를 파싱함.
# 공고 URL 패턴: /hr/usr/job/jobOpeningView.do?jobOpeningId={id}
#
# [참고] 2026-05-01 기준 삼성 채용공고 0건. 공고 생기면 정상 동작 예정.
# ============================================================

from bs4 import BeautifulSoup
from .base import BaseCrawler


class SamsungCrawler(BaseCrawler):
    def __init__(self):
        super().__init__("Samsung", "제조업")
        self.url = "https://www.samsungcareers.com/hr/"

    def fetch_jobs(self):
        jobs = []
        html = self.playwright_fetch(self.url)
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
