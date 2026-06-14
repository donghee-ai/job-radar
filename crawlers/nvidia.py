# ============================================================
# NVIDIA 크롤러
# ============================================================
# 방식: Playwright XHR 인터셉트 (브라우저 세션 기반)
# URL: https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite
#
# [시행착오]
# 1. locationHierarchy1 필터로 Workday API 직접 POST
#    → 400 Bad Request. 한국 location ID(2fcb99c455831013ea52b82135ba3266)가
#      만료됐거나 필터 형식 자체가 변경된 것으로 추정.
#
# 2. Content-Type, Accept, Origin, Referer 헤더 추가 후 재시도
#    → 여전히 400. 헤더 조합과 무관하게 차단됨.
#
# 3. 위치 필터 제거, searchText: "Korea" 로 변경
#    → 여전히 400. Workday가 브라우저 세션(CSRF 토큰, 쿠키) 없이
#      오는 요청은 봇으로 간주해 일괄 차단하는 방식으로 확인됨.
#      아무리 헤더를 흉내 내도 세션 정보 없이는 통과 불가.
#
# [현재 방식: Playwright XHR 인터셉트]
# 실제 Chromium으로 채용 페이지(?q=Korea)를 열면 브라우저가
# 자동으로 Workday 내부 API를 XHR로 호출함.
# playwright_intercept()가 /wday/cxs/ 패턴 응답을 실시간 캡처 → jobPostings 파싱.
# 브라우저 세션에서 CSRF 토큰과 쿠키가 자동으로 처리되므로 400 문제 해결.
# 직접 POST 방식과 달리 Workday 입장에서 정상 브라우저 요청으로 인식됨.
#
# [상세 페이지]
# 목록 수집 후 별도 Playwright 세션으로 각 공고 URL을 방문해
# Workday 상세 페이지의 자격 요건(Qualifications 등) 추출.
# ============================================================

import re
from datetime import datetime, timedelta
from .base import BaseCrawler


def _parse_workday_date(posted_on: str) -> str:
    """Workday 상대 날짜 텍스트 → YYYY-MM-DD 변환.
    "Posted 30+ Days Ago" 같은 '+' 표기는 해당 일수를 최솟값으로 처리.
    파싱 불가 시 빈 문자열 반환."""
    m = re.search(r'Posted\s+(\d+)\+?\s+Days?\s+Ago', posted_on, re.IGNORECASE)
    if m:
        days = int(m.group(1))
        return (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    return ""


def _clean_location(loc: str) -> str:
    """Workday 위치 형식 정리.
    "Korea, Seoul" → "Seoul, South Korea"
    그 외 country-first 형식도 city-first로 변환."""
    loc = loc.strip()
    replacements = {"Korea": "South Korea"}
    parts = [p.strip() for p in loc.split(",")]
    if len(parts) == 2:
        country = replacements.get(parts[0], parts[0])
        return f"{parts[1]}, {country}"
    return loc


class NvidiaCrawler(BaseCrawler):
    def __init__(self):
        super().__init__("NVIDIA", "외국계")
        self.careers_url = "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite"

    def fetch_jobs(self):
        jobs = []
        api_responses = self.playwright_intercept(
            url=f"{self.careers_url}?q=Korea",
            api_pattern="/wday/cxs/nvidia/NVIDIAExternalCareerSite/jobs"
        )

        seen = set()
        detail_urls = []  # (index, url)
        for data in api_responses:
            for item in data.get("jobPostings", []):
                path = item.get("externalPath", "")
                if not path or path in seen:
                    continue
                seen.add(path)
                url = f"https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite{path}"
                idx = len(jobs)
                jobs.append(self.format_job(
                    title=item.get("title", ""),
                    url=url,
                    location=_clean_location(item.get("locationsText", "")),
                    posted_date=_parse_workday_date(item.get("postedOn", ""))
                ))
                detail_urls.append((idx, url))

        # 상세 페이지 일괄 방문
        if detail_urls:
            self._fill_descriptions(jobs, detail_urls)

        return jobs

    def _fill_descriptions(self, jobs: list, detail_urls: list):
        """Playwright로 Workday 상세 페이지 방문, 자격 요건 추출."""
        try:
            from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(user_agent=self.headers['User-Agent'])
                page = context.new_page()

                for idx, url in detail_urls:
                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=20000)
                        page.wait_for_timeout(3000)
                        html = page.content()
                        desc = self.extract_qualifications(html)
                        if desc:
                            jobs[idx]["description"] = desc
                    except Exception as e:
                        print(f"  ⚠️  [NVIDIA] Detail page error: {e}")

                browser.close()
        except Exception as e:
            print(f"  ⚠️  [NVIDIA] Playwright error: {e}")
