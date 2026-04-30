# ============================================================
# Google 크롤러
# ============================================================
# 방식: Playwright (헤드리스 Chromium) → BeautifulSoup HTML 파싱
# URL: https://www.google.com/about/careers/applications/jobs/results/?location=South+Korea
#
# [시행착오]
# 1. requests + BeautifulSoup로 직접 스크래핑
#    → 공고 1개만 잡힘. Google 채용 페이지는 React 앱이라
#      실제 공고 목록은 JS 실행 후 동적으로 렌더링됨.
#      requests는 JS를 실행 못 하므로 빈 껍데기만 받게 됨.
#
# 2. Google Careers JSON API 탐색 (careers.google.com/api/v3/search/ 등)
#    → 404. 내부 API는 외부에서 접근 불가.
#
# [현재 방식]
# Playwright로 실제 Chromium을 실행, networkidle 상태까지 대기해
# JS가 공고를 다 그린 후 HTML을 받음.
# `ul[class*='jobs']` 선택자로 목록이 렌더링될 때까지 대기.
# 실제 공고 링크는 숫자 ID가 포함된 /jobs/results/{id} 패턴이므로
# regex로 네비게이션 링크와 구분함.
# ============================================================

import re
from bs4 import BeautifulSoup
from .base import BaseCrawler


class GoogleCrawler(BaseCrawler):
    def __init__(self):
        super().__init__("Google", "외국계")
        self.url = "https://www.google.com/about/careers/applications/jobs/results/?location=South+Korea"

    def fetch_jobs(self):
        jobs = []
        html = self.playwright_fetch(self.url, wait_selector="ul[class*='jobs']")
        if not html:
            return jobs
        soup = BeautifulSoup(html, "html.parser")
        seen = set()
        for a in soup.select("a[href*='/jobs/results/']"):
            href = a.get("href", "")
            if not href or href in seen:
                continue
            # 숫자 ID가 있는 링크만 실제 공고 (네비게이션 링크 제외)
            if not re.search(r"/jobs/results/\d+", href):
                continue
            seen.add(href)
            title = a.get_text(strip=True)
            if not title:
                continue
            full_url = "https://www.google.com" + href if href.startswith("/") else href
            jobs.append(self.format_job(title=title, url=full_url, location="South Korea"))
        return jobs
