# ============================================================
# SK 크롤러 (대기업 — SK하이닉스 · SK텔레콤)
# ============================================================
# 방식: SK 그룹 채용 사이트 목록 API (POST form, requests)
# API: https://www.skcareers.com/Recruit/GetRecruitList
#      form: sort=1&searchText=&corpCode=&jobRole=&workingRegion=
#
# - 그룹 전체(~130건) 중 온디바이스 AI와 관련 있는 계열사만 남김
#     SK hynix (AI 메모리·반도체), SK telecom (온디바이스 AI·에이닷)
# - recruitType / workingType 파라미터를 넣으면 404 → 빈 값으로만 호출
# - 공고 URL: https://www.skcareers.com/Recruit/Detail/{noticeID}
# - 근무지는 "Seoul", "Gyeonggi/Incheon" 같은 권역 단위
# ============================================================

from datetime import datetime
from .base import BaseCrawler

CORPS = {"SK hynix": "SK하이닉스", "SK telecom": "SK텔레콤"}


def _parse_end(text: str) -> str:
    """'October 25, 2026(Sun)' → '20261025'. 실패 시 ''."""
    try:
        return datetime.strptime(text.split("(")[0].strip(), "%B %d, %Y").strftime("%Y%m%d")
    except (ValueError, AttributeError):
        return ""


class SkCrawler(BaseCrawler):
    API = "https://www.skcareers.com/Recruit/GetRecruitList"

    def __init__(self):
        super().__init__("SK하이닉스", "대기업")

    def fetch_jobs(self):
        form = {"sort": "1", "searchText": "", "corpCode": "", "jobRole": "", "workingRegion": ""}
        resp = self.safe_post(self.API, data=form)
        if not resp:
            return []
        jobs = []
        for n in resp.json().get("list", []):
            corp = CORPS.get(n.get("corpName", ""))
            if not corp:
                continue
            end = _parse_end(n.get("end", ""))
            if end and self.is_expired(end):
                continue
            title = n.get("title", "").strip()
            if corp != "SK하이닉스":
                title = f"[{corp}] {title}"
            area = n.get("workingArea", "")
            tags = [{"New": "신입", "Experienced": "경력", "Intern": "인턴"}.get(n.get("recruitType"), "")]
            if n.get("workingType") == "Contract":
                tags.append("계약직")
            jobs.append(self.format_job(
                title=title,
                url=f"https://www.skcareers.com/Recruit/Detail/{n.get('noticeID')}",
                location=f"{area}, South Korea" if area else "South Korea",
                department=n.get("jobRole", "") or "",
                tags=tags,
            ))
        return jobs
