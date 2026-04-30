# ============================================================
# Naver 크롤러
# ============================================================
# 방식: requests + BeautifulSoup + regex (SSR 페이지)
# URL: https://recruit.navercorp.com/rcrt/list.do
#
# [시행착오]
# 1. POST API /rcrt/loadJobList.do (빈 payload)
#    → 404. 기존에 동작하던 내부 API 엔드포인트가 변경됨.
#
# 2. 다른 API 경로 추측 시도
#    (/rcrt/loadJobListAjax.do, /rcrt/getJobList.do, /rcrt/jobList.do 등)
#    → 전부 404.
#
# [현재 방식]
# 네이버 채용 목록 페이지(/rcrt/list.do)는 SSR(서버사이드 렌더링)로
# 공고 목록이 HTML에 직접 포함되어 있음 → requests로 충분.
#
# 공고 식별 방법 (우선순위):
#   1차: <a href="/rcrt/view.do?annoId={id}"> 형태 링크 직접 파싱
#   2차: 소셜 공유 JS 함수 share('platform', 'annoId', 'title') 에서 regex로 추출
#        → annoId는 7자리 이상 숫자, title은 세 번째 인자
#
# 공고 상세 URL 패턴: /rcrt/view.do?annoId={annoId}
# ============================================================

import re
from bs4 import BeautifulSoup
from .base import BaseCrawler


class NaverCrawler(BaseCrawler):
    def __init__(self):
        super().__init__("Naver", "IT")
        self.url = "https://recruit.navercorp.com/rcrt/list.do"

    def fetch_jobs(self):
        jobs = []
        resp = self.safe_request(self.url)
        if not resp:
            return jobs

        soup = BeautifulSoup(resp.text, "html.parser")
        seen = set()

        # 1차: view.do 직접 링크에서 annoId 추출
        for a in soup.select("a[href*='view.do?annoId=']"):
            href = a.get("href", "")
            m = re.search(r'annoId=(\d+)', href)
            if not m:
                continue
            anno_id = m.group(1)
            if anno_id in seen:
                continue
            seen.add(anno_id)
            title = a.get_text(strip=True)
            if title:
                full_url = "https://recruit.navercorp.com" + href if href.startswith("/") else href
                jobs.append(self.format_job(title=title, url=full_url))

        # 2차: share('platform', 'annoId', 'title') JS 함수에서 regex로 추출
        if not seen:
            for m in re.finditer(r"share\('[^']+',\s*'(\d{7,})',\s*'([^']+)'", resp.text):
                anno_id, title = m.group(1), m.group(2)
                if anno_id in seen:
                    continue
                seen.add(anno_id)
                jobs.append(self.format_job(
                    title=title,
                    url=f"https://recruit.navercorp.com/rcrt/view.do?annoId={anno_id}"
                ))

        return jobs
