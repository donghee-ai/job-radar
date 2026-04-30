# ============================================================
# Lever 공용 크롤러 (현재 미사용)
# ============================================================
# 방식: Lever 공개 REST API (GET)
# API: https://api.lever.co/v0/postings/{board_token}?mode=json
#
# Lever는 Greenhouse와 함께 많이 쓰이는 ATS.
# board_token만 알면 인증 없이 전체 공고를 가져올 수 있음.
#
# [제거된 회사]
# - Sendbird: 원래 Lever(board token `sendbird`) 로 등록되어 있었으나
#             api.lever.co/v0/postings/sendbird → 404.
#             확인 결과 Sendbird는 Greenhouse로 이전한 것으로 보임.
#             (boards-api.greenhouse.io/v1/boards/sendbird/jobs → 19개 공고 확인)
#             하지만 사용자 요청으로 Sendbird 전체 제거.
#
# Lever 기반 회사를 추가할 경우 BOARDS에 등록하고
# __init__.py에서 LeverCrawler("회사명") 으로 사용.
# ============================================================

from .base import BaseCrawler


class LeverCrawler(BaseCrawler):
    BOARDS = {}

    def __init__(self, company: str):
        if company not in self.BOARDS:
            raise ValueError(f"Lever에 등록되지 않은 회사입니다: '{company}'. 등록된 회사: {list(self.BOARDS)}")
        board_token, category = self.BOARDS[company]
        super().__init__(company, category)
        self.board_token = board_token

    def fetch_jobs(self):
        jobs = []
        url = f"https://api.lever.co/v0/postings/{self.board_token}?mode=json"
        resp = self.safe_request(url)
        if resp:
            try:
                for item in resp.json():
                    jobs.append(self.format_job(
                        title=item.get("text", ""),
                        url=item.get("hostedUrl", ""),
                        location=item.get("categories", {}).get("location", ""),
                        department=item.get("categories", {}).get("team", "")
                    ))
            except Exception as e:
                print(f"  ⚠️  {self.company} error: {e}")
        return jobs
