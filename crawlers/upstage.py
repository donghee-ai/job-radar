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
# 확인 기준 45개 공고.
#
# a 태그 전체 텍스트에는 제목 뒤에 부문·직군·직무·경력·고용형태가 붙어 있어
# ("...EngineerUpstageTechSoftware Engineering경력 무관정규직") 제목은
# [data-variant="title-01"], 나머지는 data-testid="공고리스트_subtext_*"에서 따로 뽑는다.
# ============================================================

from bs4 import BeautifulSoup
from .base import BaseCrawler


def _parse_card(a):
    """(제목, 부서, 태그 목록)"""
    title_el = a.select_one('[data-variant="title-01"]')
    if not title_el:
        return a.get_text(" ", strip=True), "", []
    sub = {}
    for el in a.select('[data-testid^="공고리스트_subtext_"]'):
        key = el["data-testid"].rsplit("_", 1)[-1]
        sub[key] = el.get_text(" ", strip=True)
    department = sub.get("직무") or sub.get("직군", "")
    tags = [v for k, v in sub.items() if k not in ("부문",) and v]
    return title_el.get_text(" ", strip=True), department, tags


class UpstageCrawler(BaseCrawler):
    def __init__(self):
        super().__init__("Upstage", "스타트업", default_location="Seoul, South Korea")
        self.url = "https://careers.upstage.ai/ko/upstage"

    def fetch_jobs(self):
        jobs = []
        resp = self.safe_request(self.url)
        if not resp:
            return jobs
        soup = BeautifulSoup(resp.text, "html.parser")
        seen = set()
        for a in soup.select("a[href*='/ko/o/']"):
            href = a.get("href", "")
            if not href or href in seen:
                continue
            seen.add(href)
            title, department, tags = _parse_card(a)
            if not title:
                continue
            full_url = "https://careers.upstage.ai" + href if href.startswith("/") else href
            jobs.append(self.format_job(title=title, url=full_url, department=department, tags=tags))
        if not jobs:
            self.warn("페이지는 열렸지만 공고 링크(/ko/o/...)를 하나도 못 찾음 — 페이지 구조 변경 가능성")
        return jobs
