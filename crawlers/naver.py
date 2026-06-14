# ============================================================
# Naver 크롤러
# ============================================================
# 방식: 내부 AJAX JSON API (GET) — 페이지네이션 지원
# API: https://recruit.navercorp.com/rcrt/loadJobList.do?firstIndex=N
#
# [시행착오]
# 1. POST API /rcrt/loadJobList.do (빈 payload)
#    → 404. 기존에 동작하던 내부 API 엔드포인트가 변경됨.
#
# 2. 다른 API 경로 추측 시도
#    (/rcrt/loadJobListAjax.do, /rcrt/getJobList.do, /rcrt/jobList.do 등)
#    → 전부 404.
#
# 3. requests + BeautifulSoup — /rcrt/list.do HTML 파싱 (1차 방식)
#    → 네이버 채용 목록 페이지는 SSR로 첫 10건이 HTML에 포함됨 → 수집 가능.
#      그러나 페이지 하단의 "더보기" 버튼이 JS 기반(Scroll-to-Load/AJAX)이라
#      requests로는 추가 페이지를 가져올 수 없어 항상 10건만 수집됨.
#      실제 공고 수: 20건 → 10건 누락.
#
# 4. HTML 내 share('platform', 'annoId', 'title') JS 함수 regex 추출 (2차 폴백)
#    → 첫 페이지 HTML 내에 있는 공고만 추출 가능. 동일하게 10건 한계.
#
# 5. HTML 페이지 내 pagination 링크 탐색
#    → .next, .prev, [class*=paging] 등 탐색 결과 모두 slick-carousel 슬라이더의
#      이전/다음 버튼이었음 (class: mainPopup_next, slick-arrow).
#      실제 공고 목록 페이지네이션 링크는 존재하지 않음.
#      페이지 소스 JS 변수에서 pageSize="10", totalRows="20" 확인 →
#      더보기 방식(AJAX)임을 최종 확인.
#
# [현재 방식]
# 브라우저 Network 탭에서 발견한 AJAX 엔드포인트를 직접 호출.
# GET /rcrt/loadJobList.do?firstIndex=N 으로 페이지네이션 처리.
#   - pageSize: 10 (서버 고정값)
#   - firstIndex: 0, 10, 20, ... (빈 list 반환 시 종료)
# 초기 페이지 HTML에서 JS 변수 totalRows 를 파싱해 총 페이지 수 사전 계산.
# 응답 JSON: { "result": "Y", "list": [...] }
# jobDetailLink 필드에 상세 URL이 포함되어 별도 URL 조합 불필요.
# staYmd 필드(YYYYMMDD)를 YYYY-MM-DD 형식으로 변환해 posted_date에 저장.
#
# [상세 페이지]
# 네이버 상세 페이지는 JS 리다이렉트 방식이라 Playwright로 렌더링 후 자격 요건 추출.
# ============================================================

import re
from .base import BaseCrawler

PAGE_SIZE = 10
MAX_PAGES = 50  # 최대 500건 방어


class NaverCrawler(BaseCrawler):
    def __init__(self):
        super().__init__("Naver", "IT", default_location="Seoul, South Korea")
        self.list_url = "https://recruit.navercorp.com/rcrt/list.do"
        self.api_url = "https://recruit.navercorp.com/rcrt/loadJobList.do"

    def fetch_jobs(self):
        jobs = []
        seen = set()
        detail_urls = []  # (index, url) 쌍

        # 초기 페이지에서 totalRows 파악 (페이지 수 사전 계산용)
        total_rows = self._get_total_rows()

        for page_num in range(MAX_PAGES):
            first_index = page_num * PAGE_SIZE
            if total_rows and first_index >= total_rows:
                break

            resp = self.safe_request(self.api_url, params={"firstIndex": first_index})
            if not resp:
                break

            try:
                data = resp.json()
            except Exception as e:
                print(f"  ⚠️  [Naver] JSON 파싱 오류: {e}")
                break

            items = data.get("list", [])
            if not items:
                break

            for item in items:
                anno_id = str(item.get("annoId", ""))
                if not anno_id or anno_id in seen:
                    continue
                seen.add(anno_id)

                # endYmd(마감일)이 오늘 이전이면 제외
                if self.is_expired(item.get("endYmd", "")):
                    continue

                title = item.get("annoSubject", "")
                url = item.get("jobDetailLink", "")
                if not url:
                    url = f"https://recruit.navercorp.com/rcrt/view.do?annoId={anno_id}"

                # staYmd: "20260420" → "2026-04-20"
                raw_date = item.get("staYmd", "")
                posted = f"{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:]}" if len(raw_date) == 8 else raw_date

                idx = len(jobs)
                jobs.append(self.format_job(
                    title=title,
                    url=url,
                    department=item.get("subJobCdNm", ""),
                    posted_date=posted
                ))
                detail_urls.append((idx, url))

        # 상세 페이지 일괄 크롤링
        if detail_urls:
            self._fill_descriptions(jobs, detail_urls)

        return jobs

    def _get_total_rows(self) -> int:
        """초기 페이지 HTML에서 totalRows JS 변수를 추출."""
        resp = self.safe_request(self.list_url)
        if not resp:
            return 0
        m = re.search(r'totalRows\s*=\s*"(\d+)"', resp.text)
        return int(m.group(1)) if m else 0

    def _fill_descriptions(self, jobs: list, detail_urls: list):
        """Playwright로 상세 페이지들을 방문해 지원 자격 추출."""
        try:
            from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(user_agent=self.headers['User-Agent'])
                page = context.new_page()

                for idx, url in detail_urls:
                    try:
                        page.goto(url, wait_until="domcontentloaded", timeout=15000)
                        page.wait_for_timeout(3000)
                        html = page.content()
                        desc = self.extract_qualifications(html)
                        if desc:
                            jobs[idx]["description"] = desc
                    except Exception as e:
                        print(f"  ⚠️  [Naver] Detail page error: {e}")

                browser.close()
        except Exception as e:
            print(f"  ⚠️  [Naver] Playwright error: {e}")
