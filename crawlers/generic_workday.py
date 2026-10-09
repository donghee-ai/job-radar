# ============================================================
# Workday 공용 크롤러
# ============================================================
# 방식: Workday 채용 사이트 내부 JSON API (POST, requests)
# API: https://{host}/wday/cxs/{tenant}/{site}/jobs
#      body {"appliedFacets": {}, "limit": 20, "offset": N, "searchText": "..."}
#
# - limit 최대 20 → offset을 늘려 total까지 페이지네이션
# - searchText는 전문 검색이라 느슨하다("Korea"로 찾아도 미국 공고가 섞임).
#   korea_only 보드는 locationsText로 한 번 더 걸러 한국 근무지만 남긴다.
#   "2 Locations"처럼 지역이 요약된 공고는 판별할 수 없어 제외.
# - NVIDIA는 nvidia.py(브라우저 기반)를 그대로 둔다. 이 방식으로 옮길 수 있지만
#   지금 정상 동작 중이라 바꿀 이유가 없음.
#
# [등록 회사]
# - Boston Dynamics (피지컬 AI) — 전체 공고 (~70건)
# - Intel (온디바이스 AI) — 전 세계 수백 건이라 한국 근무지만
# ============================================================

from .base import BaseCrawler
from .enrich import regions
from .nvidia import _parse_workday_date, _clean_location


class WorkdayCrawler(BaseCrawler):
    # 회사: (host, tenant, site, 구분, 한국만?)
    BOARDS = {
        "Boston Dynamics": ("bostondynamics.wd1.myworkdayjobs.com", "bostondynamics", "Boston_Dynamics", "외국계", False),
        "Intel": ("intel.wd1.myworkdayjobs.com", "intel", "External", "외국계", True),
    }
    PAGE = 20
    MAX_PAGES = 30

    def __init__(self, company: str):
        if company not in self.BOARDS:
            raise ValueError(f"Workday에 등록되지 않은 회사: '{company}'. 등록된 회사: {list(self.BOARDS)}")
        host, tenant, site, category, korea_only = self.BOARDS[company]
        super().__init__(company, category)
        self.api = f"https://{host}/wday/cxs/{tenant}/{site}/jobs"
        self.site_url = f"https://{host}/{site}"
        self.korea_only = korea_only

    def fetch_jobs(self):
        jobs, seen = [], set()
        offset, total = 0, None
        for _ in range(self.MAX_PAGES):
            body = {"appliedFacets": {}, "limit": self.PAGE, "offset": offset,
                    "searchText": "Korea" if self.korea_only else ""}
            resp = self.safe_post(self.api, json=body, headers={"Accept": "application/json"})
            if not resp:
                break
            data = resp.json()
            if total is None:
                total = data.get("total", 0)
            postings = data.get("jobPostings", [])
            for item in postings:
                path = item.get("externalPath", "")
                if not path or path in seen:
                    continue
                seen.add(path)
                location = _clean_location(item.get("locationsText", ""))
                if self.korea_only and "한국" not in regions(location):
                    continue
                jobs.append(self.format_job(
                    title=item.get("title", ""),
                    url=self.site_url + path,
                    location=location,
                    posted_date=_parse_workday_date(item.get("postedOn", "")),
                ))
            offset += self.PAGE
            if not postings or offset >= total:
                break
        return jobs
