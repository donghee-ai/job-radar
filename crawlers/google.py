# ============================================================
# Google 크롤러
# ============================================================
# 방식: requests + BeautifulSoup (서버 렌더링된 HTML 직접 파싱, 브라우저 없음)
# URL: https://www.google.com/about/careers/applications/jobs/results/?location=South+Korea&page=N
#
# [시행착오]
# 1. requests + BeautifulSoup 직접 스크래핑 (초기)
#    → 공고 1개만 잡힘. 당시엔 목록이 JS로 그려진다고 판단해 Playwright로 넘어감.
#      (8번에서 보듯 지금은 서버가 공고 카드를 HTML에 담아 보낸다.)
#
# 2. Playwright + wait_selector="ul[class*='jobs']"
#    → Google이 CSS 클래스를 전부 난독화된 이름(VfPpkd-…)으로 교체해 0건.
#
# 3. URL 패턴 /jobs/results/\d+ 로 링크 필터링
#    → URL 구조가 /jobs/results/{숫자id}-{slug} 로 바뀜.
#
# 4. CSS 속성 셀렉터 a[href*="/jobs/results/"] 로 추출
#    → 공고 링크의 href는 상대경로 "jobs/results/…"(앞에 / 없음)라 거의 안 걸림.
#      a.href 프로퍼티(완성된 URL)로 필터링해야 20건이 잡혔다.
#
# 5. 쿠키 동의 팝업 미처리 → 팝업을 닫기 전엔 카드가 일부만 그려짐.
#
# 6. wait_until="networkidle" → 애널리틱스 때문에 도달 못 해 30초 타임아웃 (2026-08-14).
#
# 7. 브라우저 방식이 날마다 들쑥날쑥 0건 (2026-10-07, 10-08, 10-10)
#    → 실패 원인 기록(warn)을 넣고 보니 받은 페이지는 정상 검색 결과 페이지였다.
#      범인은 '렌더링 완료' 신호로 기다리던 a[href*="/jobs/results/"]:
#      4번에서 봤듯 공고 링크는 이 조건에 안 맞고, 페이지 어딘가의 다른 링크 하나가
#      우연히 맞춰 주던 것. 그 링크가 없는 날엔 공고가 다 떠 있어도 10초 뒤 0건.
#
# 8. 현재 방식: 브라우저를 버리고 HTML을 바로 파싱
#    → 서버가 보내는 HTML에 공고 카드가 이미 들어 있다 (li[ssk] 안에 h3 제목,
#      상대경로 링크, place 아이콘 옆 근무지, 경력 레벨 버튼).
#      렌더링 대기가 없으니 7번 같은 타이밍 실패가 원천적으로 없고, 몇 초면 끝난다.
#    - 직함: 카드의 h3
#    - 근무지: place 아이콘 다음 요소의 텍스트
#    - 경력 레벨(Early/Mid/Advanced): 경험 툴팁 버튼 → tags로 남겨 enrich가 연차로 변환
#    - 페이지네이션: &page=N 을 늘리며 새 카드가 안 나올 때까지 (한 페이지 20건)
# ============================================================

from urllib.parse import urljoin, urlsplit, urlunsplit, parse_qsl, urlencode
from bs4 import BeautifulSoup
from .base import BaseCrawler

BASE = "https://www.google.com/about/careers/applications/"
MAX_PAGES = 15


def _canonical(href: str) -> str:
    """공고 링크에 붙는 &page=N 을 뗀다 — 주소가 바뀌면 first_seen이 끊겨 전부 '새 공고'로 잡힌다."""
    parts = urlsplit(urljoin(BASE, href))
    query = urlencode([(k, v) for k, v in parse_qsl(parts.query) if k != "page"])
    return urlunsplit((parts.scheme, parts.netloc, parts.path, query, ""))


def _parse_cards(html: str):
    """공고 카드 목록 → [(id, 제목, 상대 링크, 근무지, 경력 레벨)]"""
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for li in soup.select("li[ssk]"):
        job_id = li["ssk"].split(":")[-1]
        h3 = li.find("h3")
        link = li.select_one("a[href*='jobs/results/']")
        if not (h3 and link):
            continue
        place = next((i for i in li.find_all("i") if i.get_text(strip=True) == "place"), None)
        loc_el = place.find_next_sibling() if place else None
        level = li.select_one("button[aria-label*='experience'] span span")
        out.append((job_id, h3.get_text(" ", strip=True), link["href"],
                    loc_el.get_text(" ", strip=True) if loc_el else "",
                    level.get_text(strip=True) if level else ""))
    return out


class GoogleCrawler(BaseCrawler):
    def __init__(self):
        super().__init__("Google", "외국계")
        self.url = BASE + "jobs/results/"

    def fetch_jobs(self):
        jobs, seen = [], set()
        for page in range(1, MAX_PAGES + 1):
            resp = self.safe_request(self.url, params={"location": "South Korea", "page": page})
            if not resp:
                break
            cards = _parse_cards(resp.text)
            new = [c for c in cards if c[0] not in seen]
            if page == 1 and not cards:
                title = BeautifulSoup(resp.text, "html.parser").title
                self.warn(f"검색 결과 HTML에 공고 카드(li[ssk])가 없음 — 페이지 구조 변경 가능성 "
                          f"(받은 페이지 제목 {title.get_text(strip=True) if title else '?'!r}, {len(resp.text):,}바이트)")
            if not new:
                break
            for job_id, title, href, location, level in new:
                seen.add(job_id)
                jobs.append(self.format_job(
                    title=title,
                    url=_canonical(href),
                    location=location or "South Korea",
                    tags=[level] if level else None,
                ))
        return jobs
