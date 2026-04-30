# ============================================================
# NVIDIA 크롤러
# ============================================================
# 방식: Workday 내부 JSON API (POST)
# URL: https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/NVIDIAExternalCareerSite/jobs
#
# [시행착오]
# 1. locationHierarchy1 필터 사용 (한국 ID: 2fcb99c455831013ea52b82135ba3266)
#    → 400 Bad Request. ID가 만료됐거나 필터 형식 변경된 듯
#
# 2. Content-Type, Accept, Origin, Referer 헤더 추가
#    → 여전히 400. Workday가 CSRF 토큰 or 세션 쿠키를 요구하는 것으로 추정
#
# 3. 위치 필터 제거하고 searchText: "Korea" 로 변경
#    → 여전히 400. 현재 bot 차단 상태
#
# [현황]
# Workday는 브라우저 세션 없이 직접 API 호출 시 400을 반환함.
# 근본 해결은 Playwright로 페이지 로드 후 XHR 인터셉트하거나
# 세션 쿠키를 추출하는 방식이 필요함. 미해결 상태.
# ============================================================

from .base import BaseCrawler


class NvidiaCrawler(BaseCrawler):
    def __init__(self):
        super().__init__("NVIDIA", "외국계")
        self.api_url = "https://nvidia.wd5.myworkdayjobs.com/wday/cxs/nvidia/NVIDIAExternalCareerSite/jobs"

    def fetch_jobs(self):
        jobs = []
        for offset in range(0, 200, 50):
            payload = {
                "appliedFacets": {},
                "limit": 50,
                "offset": offset,
                "searchText": "Korea"
            }
            resp = self.safe_post(
                self.api_url, json=payload,
                headers={
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    'Origin': 'https://nvidia.wd5.myworkdayjobs.com',
                    'Referer': 'https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite',
                }
            )
            if not resp:
                break
            try:
                data = resp.json()
            except Exception as e:
                print(f"  ⚠️  NVIDIA JSON error: {e}")
                break
            postings = data.get("jobPostings", [])
            if not postings:
                break
            for p in postings:
                jobs.append(self.format_job(
                    title=p.get("title", ""),
                    url=f"https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite{p.get('externalPath', '')}",
                    location=p.get("locationsText", ""),
                    posted_date=p.get("postedOn", "")
                ))
        return jobs
