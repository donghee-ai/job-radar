# ============================================================
# AMD 크롤러 (온디바이스 AI · 외국계)
# ============================================================
# 방식: 채용 사이트(Jibe) 검색 JSON API (GET, requests)
# API: https://careers.amd.com/api/jobs?page=N&limit=100&location=Korea
#
# - 전 세계 1,300건 이상이라 location=Korea 로 한국 근무지만 수집
# - location 파라미터가 느슨하게 매칭될 수 있어 full_location으로 한 번 더 확인
# - 응답 jobs[].data: title, req_id, full_location, posted_date, category
# ============================================================

from .base import BaseCrawler
from .enrich import regions


class AmdCrawler(BaseCrawler):
    API = "https://careers.amd.com/api/jobs"
    MAX_PAGES = 5

    def __init__(self):
        super().__init__("AMD", "외국계")

    def fetch_jobs(self):
        jobs, seen = [], set()
        for page in range(1, self.MAX_PAGES + 1):
            resp = self.safe_request(self.API, params={"page": page, "limit": 100, "location": "Korea"})
            if not resp:
                break
            items = resp.json().get("jobs", [])
            for it in items:
                d = it.get("data", {})
                rid = d.get("req_id") or d.get("slug")
                if not rid or rid in seen:
                    continue
                seen.add(rid)
                location = d.get("full_location") or d.get("location_name") or ""
                if "한국" not in regions(location):
                    continue
                category = d.get("category")
                if isinstance(category, list):
                    category = category[0] if category else ""
                jobs.append(self.format_job(
                    title=d.get("title", ""),
                    url=f"https://careers.amd.com/careers-home/jobs/{rid}",
                    location=location,
                    department=category or "",
                    posted_date=(d.get("posted_date") or "")[:10],
                ))
            if len(items) < 100:
                break
        return jobs
