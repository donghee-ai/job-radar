# ============================================================
# MediaTek 크롤러 (온디바이스 AI · 외국계)
# ============================================================
# 방식: 채용 사이트(Next.js) tRPC JSON API (GET, requests)
# API: https://careers.mediatek.com/api/trpc/job.getJobs?input={...}
#
# - 한 번에 전체(~600건)를 받아 properties.location.code가 한국 지사(Seongnam 등)인 것만 남김
# - 공고 페이지 /en/jobs/{id} 는 첫 방문 때 쿠키를 심는 리다이렉트가 있지만
#   브라우저에서는 바로 열림. API 호출에는 쿠키가 필요 없음.
# ============================================================

import json
from .base import BaseCrawler
from .enrich import regions

# MediaTek 지사 코드 → regions()가 알아보는 지명
_KOREA_SITES = {"seongnam", "seoul", "pangyo", "bundang"}


class MediatekCrawler(BaseCrawler):
    API = "https://careers.mediatek.com/api/trpc/job.getJobs"

    def __init__(self):
        super().__init__("MediaTek", "외국계")

    def fetch_jobs(self):
        query = {"json": {"locales": "en_US", "page": 1,
                          "jobQueryInfo": {"keywords": [], "relation": "OR"},
                          "filters": {}, "sortBy": "publishedDate", "order": "DESC", "limit": 1000}}
        resp = self.safe_request(self.API, params={"input": json.dumps(query)})
        if not resp:
            return []
        items = resp.json().get("result", {}).get("data", {}).get("json", {}).get("jobs", [])
        jobs = []
        for it in items:
            props = it.get("properties") or {}
            site = ((props.get("location") or {}).get("code") or "").strip()
            if site.lower() not in _KOREA_SITES and "한국" not in regions(site):
                continue
            jobs.append(self.format_job(
                title=it.get("title", ""),
                url=f"https://careers.mediatek.com/en/jobs/{it.get('id')}",
                location=f"{site}, South Korea",
                department=((props.get("category") or {}).get("label") or ""),
                posted_date=(it.get("publishedDate") or "")[:10],
            ))
        return jobs
