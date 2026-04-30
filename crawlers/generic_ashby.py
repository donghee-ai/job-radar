# ============================================================
# Ashby 공용 크롤러
# ============================================================
# 방식: Ashby 공개 REST API (GET)
# API: https://api.ashbyhq.com/posting-api/job-board/{board_token}
#
# Ashby는 Greenhouse의 대안으로 최근 많은 AI 스타트업이 채택하는 ATS.
# 공개 API를 제공하며, board_token만 알면 인증 없이 전체 공고를 가져올 수 있음.
#
# 응답 JSON 구조:
#   { "jobs": [ { "title", "jobUrl", "location", "department", "publishedAt", ... } ] }
#
# [등록 경위]
# - OpenAI가 Greenhouse에서 Ashby로 ATS를 이전함.
#   기존 boards-api.greenhouse.io/v1/boards/openai/jobs → 404
#   jobs.ashbyhq.com/openai 확인 → Ashby 사용 확인
#   api.ashbyhq.com/posting-api/job-board/openai → 정상 (8개 공고 확인)
# ============================================================

from .base import BaseCrawler


class AshbyCrawler(BaseCrawler):
    BOARDS = {
        "OpenAI": ("openai", "외국계"),
    }

    def __init__(self, company: str):
        if company not in self.BOARDS:
            raise ValueError(f"Ashby에 등록되지 않은 회사: '{company}'. 등록된 회사: {list(self.BOARDS)}")
        board_token, category = self.BOARDS[company]
        super().__init__(company, category)
        self.board_token = board_token

    def fetch_jobs(self):
        jobs = []
        url = f"https://api.ashbyhq.com/posting-api/job-board/{self.board_token}"
        resp = self.safe_request(url)
        if resp:
            try:
                for item in resp.json().get("jobs", []):
                    jobs.append(self.format_job(
                        title=item.get("title", ""),
                        url=item.get("jobUrl", ""),
                        location=item.get("location", ""),
                        department=item.get("department", ""),
                        posted_date=item.get("publishedAt", "")
                    ))
            except Exception as e:
                print(f"  ⚠️  {self.company} error: {e}")
        return jobs
