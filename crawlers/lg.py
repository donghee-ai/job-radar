# ============================================================
# LG 크롤러 (대기업 — LG전자 · 로보스타)
# ============================================================
# 방식: LG 그룹 채용 사이트 목록 JSON API (POST, requests)
# API: https://api.careers.lg.com/rmk/job/retrieveJobNoticesList
#
# - 그룹 전체(~80건) 중 피지컬·온디바이스 AI와 관련 있는 계열사만 남김
#     LGE = LG전자 (로봇·가전 온디바이스 AI), RBO = 로보스타 (산업용 로봇)
#   LG AI연구원은 Greenhouse 보드가 따로 있어 generic_greenhouse.py에서 수집
# - 공고 URL: https://careers.lg.com/apply/detail?id={jobNoticeId}
# - recEndDateTime(마감)이 지난 공고는 제외
# ============================================================

from .base import BaseCrawler

COMPANIES = {"LGE": "LG전자", "RBO": "로보스타"}


class LgCrawler(BaseCrawler):
    API = "https://api.careers.lg.com/rmk/job/retrieveJobNoticesList"

    def __init__(self):
        super().__init__("LG전자", "대기업", default_location="Seoul, South Korea")

    def fetch_jobs(self):
        body = {"lnbSearch": "", "hashTagText": "", "recDate": "CREATION_DATE", "order": "DESC",
                "careerList": [], "companyCodeList": [], "desireLocList": [], "jobGroupList": []}
        resp = self.safe_post(self.API, json=body, headers={"Content-Type": "application/json"})
        if not resp:
            return []
        payload = resp.json()
        notices = (payload.get("data") or payload).get("jobNoticeList", [])
        jobs = []
        for n in notices:
            code = n.get("companyCode")
            if code not in COMPANIES:
                continue
            end = (n.get("recEndDateTime") or "")[:10].replace(".", "")
            if end and self.is_expired(end):
                continue
            title = n.get("jobNoticeName", "")
            if code != "LGE":   # 회사 필터는 'LG전자' 하나로 두고, 계열사는 직함 앞에 표시
                title = f"[{COMPANIES[code]}] {title}"
            jobs.append(self.format_job(
                title=title,
                url=f"https://careers.lg.com/apply/detail?id={n.get('jobNoticeId')}",
                location=n.get("workLocationName", "") or "",
                department=n.get("jobGroupName", "") or "",
                tags=[n.get("careerTypeName", "")],
            ))
        return jobs
