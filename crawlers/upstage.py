# ============================================================
# Upstage 크롤러
# ============================================================
# 방식: requests + BeautifulSoup (SSR 페이지)
# URL: https://careers.upstage.ai/ko/upstage
#
# [시행착오]
# 1. Greenhouse API boards-api.greenhouse.io/v1/boards/upstage/jobs
#    → 404. Upstage는 Greeting HR 사용 (Greenhouse 아님).
#
# 2. Ashby API api.ashbyhq.com/posting-api/job-board/upstage
#    → 404. Ashby도 아님.
#
# 3. Greeting HR 자체 API 탐색 (api.greeting.hr, careers.upstage.ai/api/v1/jobs 등)
#    → 연결 거부 또는 404. 공개 API 없음.
#
# [현재 방식]
# Greeting HR 플랫폼은 SSR 방식으로 공고 목록을 HTML에 직접 포함시켜 렌더링함.
# (→ Playwright 없이 requests만으로 충분)
# 공고 링크 패턴: /ko/o/{숫자id}
# BeautifulSoup으로 해당 패턴의 a 태그를 파싱해 제목과 URL 추출.
# 상세 페이지도 SSR이므로 requests로 지원 자격 추출 가능.
# ============================================================

from .base import BaseCrawler


class UpstageCrawler(BaseCrawler):
    def __init__(self):
        super().__init__("Upstage", "스타트업", default_location="Seoul, South Korea")
        self.url = "https://careers.upstage.ai/ko/upstage"

    def fetch_jobs(self):
        jobs = []
        resp = self.safe_request(self.url)
        if not resp:
            return jobs
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(resp.text, "html.parser")
        seen = set()
        for a in soup.select("a[href*='/ko/o/']"):
            href = a.get("href", "")
            if not href or href in seen:
                continue
            seen.add(href)
            title = a.get_text(strip=True)
            if not title:
                continue
            full_url = "https://careers.upstage.ai" + href if href.startswith("/") else href
            desc = self._fetch_detail(full_url)
            jobs.append(self.format_job(title=title, url=full_url, description=desc))
        return jobs

    def _fetch_detail(self, url: str) -> str:
        """상세 페이지에서 지원 자격 추출 (SSR → requests 가능)."""
        resp = self.safe_request(url)
        if not resp:
            return ""
        return self.extract_qualifications(resp.text)
