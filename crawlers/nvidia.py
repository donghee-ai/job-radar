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
# ============================================================

from .base import BaseCrawler


class NvidiaCrawler(BaseCrawler):
    def __init__(self):
        super().__init__("NVIDIA", "외국계")
        self.careers_url = "https://nvidia.wd5.myworkdayjobs.com/NVIDIAExternalCareerSite"

    def fetch_jobs(self):
        jobs = []
        # 브라우저가 페이지를 로드하면서 발생하는 Workday API XHR을 캡처
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
                    location=item.get("locationsText", ""),
                    posted_date=item.get("postedOn", "")
                ))
        return jobs
