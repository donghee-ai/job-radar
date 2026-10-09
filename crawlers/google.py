# ============================================================
# Google 크롤러
# ============================================================
# 방식: Playwright (헤드리스 Chromium) → page.evaluate() JS 추출 + URL 페이지네이션
# URL: https://www.google.com/about/careers/applications/jobs/results/?location=South+Korea
#
# [시행착오]
# 1. requests + BeautifulSoup 직접 스크래핑
#    → 공고 1개만 잡힘. Google 채용 페이지는 React 앱이라
#      실제 공고 목록은 JS 실행 후 동적으로 렌더링됨.
#
# 2. Playwright + wait_selector="ul[class*='jobs']" (첫 번째 Playwright 시도)
#    → Google이 프론트엔드를 재설계하면서 CSS 클래스를 전부 난독화된 이름으로 교체.
#      기존 human-readable 클래스("jobs" 등)가 사라지고
#      VfPpkd-StrnGf-rymPhb, DMZ54e 같은 자동 생성 이름만 남음.
#    → ul[class*='jobs'] 셀렉터가 아무것도 매칭 못 해
#      "Timeout 15000ms exceeded" 오류와 함께 0건 반환.
#
# 3. URL 패턴 /jobs/results/\d+ 로 링크 필터링
#    → Google이 URL 구조도 변경. 구: /jobs/results/{숫자id}
#      신: /jobs/results/{숫자id}-{slug} (예: 124693657302246086-growth-manager-app-sales)
#    → 숫자만 매칭하는 정규식이면 실제로 링크를 잡기는 하지만,
#      다음 항목(4번)의 문제로 인해 여전히 0건.
#
# 4. CSS 속성 셀렉터 querySelectorAll('a[href*="/jobs/results/"]') 로 추출
#    → CSS [href*=...] 셀렉터는 HTML 파일에 기록된 속성 문자열 기준으로 매칭.
#      Google DOM에서 대부분의 job 링크는 href 속성이 절대경로
#      (https://www.google.com/about/careers/...) 로 저장됨.
#      "/jobs/results/" 문자열이 상대경로로 저장된 링크는 1개뿐이라
#      querySelectorAll 결과가 1개만 반환됨.
#      실제로 확인 시: querySelectorAll('a[href*=...]') → 1건,
#                     a.href 프로퍼티로 필터링 → 20건.
#
# 5. 쿠키 동의 팝업 미처리
#    → Google 채용 페이지 최초 접속 시 GDPR 쿠키 동의 팝업 등장.
#      "Agree" 클릭 전에는 job 카드가 1개만 DOM에 그려지고 나머지 33개는 렌더링 보류.
#      팝업을 닫아야 전체 목록이 완전히 렌더링됨.
#
# 6. wait_until="networkidle" 로 페이지 로드 대기
#    → Google 채용 페이지는 애널리틱스/롱폴링이 계속 붙어 networkidle에
#      도달하지 못하는 경우가 있음. CI 러너에서 간헐적으로 30초 타임아웃 →
#      예외가 잡혀 0건 반환 (2026-08-14 실제 발생, 그날 Google 공고 전멸).
#      NVIDIA에서 이미 같은 유형을 겪고 고친 적 있음(premature networkidle).
#    → domcontentloaded로 바꾸고, 렌더링 완료 판정은 아래 wait_for_selector에 맡김.
#
# [현재 방식]
# - 쿠키 팝업 자동 클릭 (없으면 스킵, TimeoutError 무시)
# - wait_until="domcontentloaded" + wait_for_selector 조합
#   (networkidle처럼 '네트워크가 조용해질 때까지'를 기다리지 않음)
# - wait_selector: 'a[href*="/jobs/results/"]' — 클래스 난독화와 무관하게 안정적
#   (1개라도 매칭되면 페이지 렌더링 완료로 간주)
# - page.evaluate()로 JS 컨텍스트에서 a.href 프로퍼티 기준 필터링
#   (항상 full URL 반환 → 절대경로로 저장된 링크도 전부 캡처)
# - 페이지네이션: aria-label="Go to next page" 링크의 href (?page=N) 로 URL 이동
# - 직함은 카드(li)의 h3 → 링크 aria-label("Learn more about ...") → URL slug 순으로 사용.
#   slug는 소문자·구두점이 사라져 "Head Of Youtube Music Partnerships English Korean"처럼 깨진다.
# - 근무지는 카드의 place 아이콘 옆 텍스트, 경력 레벨(Early/Mid/Advanced)은 tags로 남긴다.
#
# 7. GitHub Actions 러너에서만 0건 (2026-10-07~). 로컬에서는 정상 20건.
#    대기 셀렉터가 타임아웃되면 조용히 break 하던 탓에 러너가 무슨 페이지를 받았는지
#    로그에 남지 않았음 → 타임아웃 시 URL·제목·본문 앞부분을 출력하도록 함.
# ============================================================

from .base import BaseCrawler


class GoogleCrawler(BaseCrawler):
    def __init__(self):
        super().__init__("Google", "외국계")
        self.url = "https://www.google.com/about/careers/applications/jobs/results/?location=South+Korea"

    def fetch_jobs(self):
        jobs = []
        seen = set()

        try:
            from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                ctx = browser.new_context(user_agent=self.headers['User-Agent'])
                pg = ctx.new_page()
                pg.goto(self.url, wait_until="domcontentloaded", timeout=30000)

                # 쿠키 동의 팝업 처리
                try:
                    pg.click('button:has-text("Agree")', timeout=4000)
                except PWTimeout:
                    pass

                for _ in range(20):  # 최대 20페이지
                    # 클래스 난독화와 무관한 셀렉터로 공고 렌더링 대기
                    try:
                        pg.wait_for_selector('a[href*="/jobs/results/"]', timeout=10000)
                    except PWTimeout:
                        if not jobs:
                            self._log_page_state(pg)
                        break

                    # a.href 프로퍼티(항상 full URL)로 필터링.
                    # querySelectorAll('a[href*=...]') CSS 속성 셀렉터는 HTML에 저장된
                    # 상대경로 기준이라 절대경로로 저장된 Google 링크 대부분을 놓침.
                    cards = pg.evaluate(r"""() => {
                        const out = [], seen = new Set();
                        for (const a of document.querySelectorAll('a')) {
                            const h = a.href;
                            if (!h.includes('/jobs/results/') || !/\/\d/.test(h) || seen.has(h)) continue;
                            seen.add(h);
                            const li = a.closest('li');
                            const h3 = li && li.querySelector('h3');
                            const aria = (a.getAttribute('aria-label') || '').replace(/^Learn more about\s*/i, '');
                            let loc = '';
                            if (li) {
                                const icon = [...li.querySelectorAll('i')].find(i => i.textContent.trim() === 'place');
                                if (icon && icon.nextElementSibling) loc = icon.nextElementSibling.textContent.trim();
                            }
                            const level = li && li.querySelector('button[aria-label*="experience" i] span span');
                            out.push({href: h, title: (h3 && h3.innerText.trim()) || aria,
                                      location: loc, level: level ? level.textContent.trim() : ''});
                        }
                        return out;
                    }""")

                    new_count = 0
                    for card in cards:
                        href = card["href"]
                        if href in seen:
                            continue
                        seen.add(href)
                        title = card["title"]
                        if not title:
                            # URL의 slug 부분에서 직무명 추출: .../results/123-software-engineer?...
                            slug = href.split("/jobs/results/")[-1].split("?")[0]
                            title = " ".join(slug.split("-")[1:]).title() if "-" in slug else slug
                        level = card["level"]
                        jobs.append(self.format_job(
                            title=title, url=href,
                            location=card["location"] or "South Korea",
                            tags=[level] if level else None,
                        ))
                        new_count += 1

                    if new_count == 0:
                        break

                    # 다음 페이지 링크: aria-label="Go to next page"
                    next_href = pg.evaluate("""() => {
                        const a = document.querySelector('a[aria-label=\"Go to next page\"]');
                        return a ? a.href : null;
                    }""")
                    if not next_href:
                        break

                    pg.goto(next_href, wait_until="domcontentloaded", timeout=30000)

                browser.close()
        except Exception as e:
            self.warn(f"브라우저 로딩 실패: {str(e).splitlines()[0]}")

        return jobs

    def _log_page_state(self, pg):
        """공고 링크가 안 보일 때 러너가 실제로 받은 페이지를 원인으로 남긴다 (CI 원인 파악용)."""
        try:
            body = pg.evaluate("() => document.body ? document.body.innerText.slice(0, 300) : ''")
            self.warn(f"공고 링크가 안 보임 — 받은 페이지: 제목 {pg.title()!r}, 주소 {pg.url}, "
                      f"본문 앞부분 {' '.join(body.split())[:200]!r}")
        except Exception as e:
            self.warn(f"공고 링크가 안 보이고 페이지 상태도 읽지 못함: {e}")
