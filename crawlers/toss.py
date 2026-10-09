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
#
# 카드 하나에 제목·기술 태그·계열사 배지가 들어 있어 a 태그 전체 텍스트를 쓰면
# "Product Owner [Search]프로덕트 ・ 서비스기획 ・ 검색토스"처럼 붙어 버린다.
# 제목은 [data-desktop-list-item-title], 태그는 그 다음 span(・ 구분),
# 계열사는 오른쪽 배지에서 따로 뽑는다. 구조가 바뀌면 전체 텍스트로 폴백.
# ============================================================

from bs4 import BeautifulSoup
from .base import BaseCrawler

# 채용공고가 아닌 네비게이션 링크 (필터링용)
_NAV_PATHS = {"/career/joining-guide", "/career/culture", "/career/article", "/career/jobs", "/career/faq"}


def _parse_card(a):
    """(제목, 태그 목록, 계열사 목록)"""
    title_el = a.select_one("[data-desktop-list-item-title]")
    if not title_el:
        return a.get_text(" ", strip=True), [], []
    title = title_el.get_text(" ", strip=True)
    tags = []
    container = title_el.find_parent(attrs={"data-desktop-list-item-title-container": True})
    tag_el = container.find_next_sibling("span") if container else None
    if tag_el:
        tags = [t.strip() for t in tag_el.get_text(" ", strip=True).split("・") if t.strip()]
    addon = a.select_one("[data-desktop-addon-root]")
    affiliates = [b.get_text(strip=True) for b in addon.find_all("span", recursive=False)] if addon else []
    return title, tags, [x for x in affiliates if x]


class TossCrawler(BaseCrawler):
    def __init__(self):
        super().__init__("Toss", "금융", default_location="Seoul, South Korea")
        self.url = "https://toss.im/career/jobs"

    def fetch_jobs(self):
        jobs = []
        html = self.playwright_fetch(self.url)
        if not html:
            return jobs
        soup = BeautifulSoup(html, "html.parser")
        seen = set()
        for a in soup.select("a[href*='/career/']"):
            href = a.get("href", "")
            if not href or href in seen:
                continue
            if any(href.startswith(nav) or href == nav for nav in _NAV_PATHS):
                continue
            seen.add(href)
            title, tags, affiliates = _parse_card(a)
            if not title:
                continue
            full_url = "https://toss.im" + href if href.startswith("/") else href
            jobs.append(self.format_job(title=title, url=full_url,
                                        department=" · ".join(affiliates), tags=tags))
        if not jobs:
            self.warn("페이지는 열렸지만 공고 링크(/career/...)를 하나도 못 찾음 — 페이지 구조 변경 가능성")
        return jobs
