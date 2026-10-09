# ============================================================
# NVIDIA 크롤러
# ============================================================
# 방식: Playwright XHR 인터셉트 (브라우저 세션 기반)
# URL: https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite
#
# [현재 방식: Playwright XHR 인터셉트]
# 실제 Chromium으로 채용 페이지(?q=Korea)를 열면 브라우저가
# 자동으로 Workday 내부 API를 XHR로 호출함.
# playwright_intercept()가 /wday/cxs/ 패턴 응답을 실시간 캡처 → jobPostings 파싱.
# 세션/CSRF 토큰은 브라우저가 처리하므로 API 스펙을 몰라도 됨.
# ============================================================

import re
from datetime import timedelta
from .base import BaseCrawler, now_kst


def _parse_workday_date(posted_on: str) -> str:
    """Workday 상대 날짜 텍스트 → YYYY-MM-DD 변환.
    "Posted 30+ Days Ago" 같은 '+' 표기는 해당 일수를 최솟값으로 처리.
    파싱 불가 시 빈 문자열 반환."""
    m = re.search(r'Posted\s+(\d+)\+?\s+Days?\s+Ago', posted_on, re.IGNORECASE)
    if m:
        days = int(m.group(1))
        return (now_kst() - timedelta(days=days)).strftime('%Y-%m-%d')
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
        for data in api_responses:
            for item in data.get("jobPostings", []):
                path = item.get("externalPath", "")
                if not path or path in seen:
                    continue
                seen.add(path)
                jobs.append(self.format_job(
                    title=item.get("title", ""),
                    url=f"https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite{path}",
                    location=_clean_location(item.get("locationsText", "")),
                    posted_date=_parse_workday_date(item.get("postedOn", ""))
                ))
        return jobs
