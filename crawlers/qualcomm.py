# ============================================================
# Qualcomm 크롤러 (온디바이스 AI · 외국계)
# ============================================================
# 방식: 채용 사이트(Eightfold) 검색 JSON API (GET, requests)
# API: https://careers.qualcomm.com/api/pcsx/search?domain=qualcomm.com&query=&location=Korea&start=N
#
# - 전 세계 2,000건 이상이라 location=Korea 로 한국 근무지만 수집 (~15건)
# - 한 페이지 10건 → start를 10씩 늘림, 전체 건수는 data.count
# - 예전 엔드포인트 /api/apply/v2/jobs 는 403 → pcsx 사용
# - Edge Impulse(퀄컴 자회사) 공고도 같은 보드에 포함됨
# ============================================================

from datetime import datetime
from .base import BaseCrawler, KST


class QualcommCrawler(BaseCrawler):
    API = "https://careers.qualcomm.com/api/pcsx/search"
    MAX_PAGES = 20

    def __init__(self):
        super().__init__("Qualcomm", "외국계")

    def fetch_jobs(self):
        jobs, seen = [], set()
        start = 0
        for _ in range(self.MAX_PAGES):
            resp = self.safe_request(self.API, params={
                "domain": "qualcomm.com", "query": "", "location": "Korea", "start": start})
            if not resp:
                break
            data = resp.json().get("data", {})
            positions = data.get("positions", [])
            for p in positions:
                pid = p.get("id")
                if pid in seen:
                    continue
                seen.add(pid)
                ts = p.get("postedTs")
                posted = datetime.fromtimestamp(ts, KST).date().isoformat() if ts else ""
                jobs.append(self.format_job(
                    title=p.get("name", ""),
                    url="https://careers.qualcomm.com" + p.get("positionUrl", ""),
                    location=" | ".join(p.get("locations") or []),
                    department=p.get("department") or "",
                    posted_date=posted,
                ))
            start += len(positions) or 10
            if not positions or start >= data.get("count", 0):
                break
        return jobs
