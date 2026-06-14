# ============================================================
# Greenhouse 공용 크롤러
# ============================================================
# 방식: Greenhouse 공개 REST API (GET)
# API: https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs
#
# Greenhouse는 많은 테크 기업이 사용하는 ATS(채용관리시스템).
# board_token만 알면 인증 없이 공개 API로 전체 공고를 가져올 수 있음.
#
# [제거된 회사]
# - OpenAI: board token `openai` → 404. OpenAI가 Ashby로 ATS를 이전함.
#           → generic_ashby.py 로 이동
# - Upstage: board token `upstage` → 404. Upstage는 Greeting HR 사용.
#            → upstage.py (자체 HTML 스크래퍼)로 이동
# - Sendbird: Lever 방식 사용하다가 Greenhouse board token `sendbird`로
#             이전한 것 확인 (19개 공고 확인). 하지만 사용자 요청으로 제거.
#
# [시행착오]
# - posted_date 필드에 updated_at 값을 사용
#   → Greenhouse API 응답에는 updated_at(최종 수정일)과 first_published(최초 게시일) 두 가지 존재.
#     공고가 자주 수정될 경우 updated_at은 현재 날짜에 가깝게 갱신되어
#     "방금 올라온 공고"처럼 보이는 오해를 유발.
#     first_published가 실제 게시일이므로 이것을 우선 사용.
#     (first_published 없는 경우에만 updated_at 폴백)
#
# [현재 등록 회사]
# - Anthropic: board token `anthropic` (400개+ 공고 확인)
# ============================================================

from .base import BaseCrawler


class GreenhouseCrawler(BaseCrawler):
    BOARDS = {
        "Anthropic": ("anthropic", "외국계"),
    }

    def __init__(self, company: str):
        if company not in self.BOARDS:
            raise ValueError(f"Greenhouse에 등록되지 않은 회사입니다: '{company}'. 등록된 회사: {list(self.BOARDS)}")
        board_token, category = self.BOARDS[company]
        super().__init__(company, category)
        self.board_token = board_token

    def fetch_jobs(self):
        jobs = []
        url = f"https://boards-api.greenhouse.io/v1/boards/{self.board_token}/jobs?content=true"
        resp = self.safe_request(url)
        if resp:
            try:
                for item in resp.json().get("jobs", []):
                    # departments 배열에서 첫 번째 부서명 추출
                    depts = item.get("departments", [])
                    dept = depts[0].get("name", "") if depts else ""

                    # content(HTML)에서 자격 요건 우선 추출
                    raw_content = item.get("content", "")
                    desc = self.extract_qualifications(raw_content) if raw_content else ""

                    jobs.append(self.format_job(
                        title=item.get("title", ""),
                        url=item.get("absolute_url", ""),
                        location=item.get("location", {}).get("name", ""),
                        department=dept,
                        posted_date=item.get("first_published", "") or item.get("updated_at", ""),
                        description=desc,
                    ))
            except Exception as e:
                print(f"  ⚠️  {self.company} error: {e}")
        return jobs
