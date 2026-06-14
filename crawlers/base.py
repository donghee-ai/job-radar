from abc import ABC, abstractmethod
from datetime import date, datetime
from typing import List, Dict
import time
import requests


class BaseCrawler(ABC):
    def __init__(self, company: str, category: str, default_location: str = ""):
        self.company = company
        self.category = category
        self.default_location = default_location
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/120.0.0.0 Safari/537.36'
        }

    @abstractmethod
    def fetch_jobs(self) -> List[Dict]:
        pass

    def format_job(self, title: str, url: str, location: str = "",
                   department: str = "", posted_date: str = "",
                   description: str = "", employment_type: str = "",
                   salary: str = "") -> Dict:
        from .classifier import classify_role
        return {
            "company": self.company,
            "category": self.category,
            "role": classify_role(title),
            "title": title,
            "url": url,
            "location": location or self.default_location,
            "department": department,
            "posted_date": posted_date,
            "description": description,
            "employment_type": employment_type,
            "salary": salary,
            "crawled_at": datetime.now().isoformat()
        }

    @staticmethod
    def strip_html(html: str, max_length: int = 200) -> str:
        """HTML 태그를 제거하고 max_length로 잘라 반환."""
        import re
        text = re.sub(r'<[^>]+>', ' ', html)
        text = re.sub(r'\s+', ' ', text).strip()
        if len(text) > max_length:
            text = text[:max_length].rsplit(' ', 1)[0] + '…'
        return text

    @staticmethod
    def extract_qualifications(html: str, max_length: int = 300) -> str:
        """HTML에서 지원 자격/요건 섹션을 우선 추출, 없으면 전체 요약.

        한국어/영어 자격 요건 키워드를 탐색해 해당 섹션 본문을 반환.
        """
        import re
        from bs4 import BeautifulSoup

        soup = BeautifulSoup(html, "html.parser")

        # 자격 요건 관련 키워드 (우선순위 순)
        qual_patterns = [
            r'이런\s*경험이\s*있으면\s*더\s*좋아요',
            r'필수\s*(?:사항|요건|자격|조건)',
            r'자격\s*(?:요건|조건|사항)',
            r'지원\s*(?:자격|조건|요건)',
            r'이런\s*분.*(?:찾|모시|함께)',
            r'우대\s*(?:사항|요건|조건)',
            r'minimum\s*qualifications?',
            r'required\s*qualifications?',
            r'preferred\s*qualifications?',
            r'what\s*(?:you.ll|we)\s*(?:need|require|bring)',
            r'requirements?',
            r'qualifications?',
            r'who\s*you\s*are',
        ]

        # 모든 heading 태그와 bold/strong 요소에서 키워드 탐색
        headers = soup.find_all(['h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'strong', 'b', 'p'])
        for pattern in qual_patterns:
            for header in headers:
                header_text = header.get_text(strip=True)
                if re.search(pattern, header_text, re.IGNORECASE):
                    # 이 헤더 다음의 콘텐츠를 수집
                    parts = []
                    for sibling in header.find_next_siblings():
                        # 다음 헤더/섹션 시작이면 중단
                        if sibling.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                            break
                        if sibling.name in ['strong', 'b'] and len(sibling.get_text(strip=True)) < 50:
                            break
                        text = sibling.get_text(strip=True)
                        if text:
                            parts.append(text)
                    if parts:
                        result = ' '.join(parts)
                        if len(result) > max_length:
                            result = result[:max_length].rsplit(' ', 1)[0] + '…'
                        return result

        # 키워드 매칭 실패 시 → 전체 텍스트 요약
        full_text = soup.get_text(' ', strip=True)
        full_text = re.sub(r'\s+', ' ', full_text).strip()
        if len(full_text) > max_length:
            full_text = full_text[:max_length].rsplit(' ', 1)[0] + '…'
        return full_text

    def is_expired(self, end_date_str: str, fmt: str = "%Y%m%d") -> bool:
        """end_date_str 을 fmt 형식으로 파싱해 오늘보다 이전이면 True 반환.
        파싱 실패 시 False (마감일 불명확 → 유지)."""
        try:
            return datetime.strptime(end_date_str, fmt).date() < date.today()
        except (ValueError, TypeError):
            return False

    def safe_request(self, url: str, retries: int = 3, backoff: float = 2.0, **kwargs):
        """GET 요청. 실패 시 최대 retries회 재시도 (지수 백오프).
        타임아웃은 기본 30초 — OpenAI(Ashby)처럼 대용량 응답에 여유를 줌."""
        timeout = kwargs.pop('timeout', 30)
        for attempt in range(1, retries + 1):
            try:
                resp = requests.get(url, headers=self.headers, timeout=timeout, **kwargs)
                resp.raise_for_status()
                return resp
            except requests.exceptions.RequestException as e:
                if attempt == retries:
                    print(f"  ⚠️  [{self.company}] Request error (시도 {attempt}/{retries}): {e}")
                else:
                    wait = backoff ** (attempt - 1)  # 1s → 2s → 4s
                    print(f"  ↩️  [{self.company}] 재시도 {attempt}/{retries} ({wait:.0f}초 후): {e}")
                    time.sleep(wait)
        return None

    def safe_post(self, url: str, retries: int = 3, backoff: float = 2.0, **kwargs):
        """POST 요청. 실패 시 최대 retries회 재시도 (지수 백오프)."""
        timeout = kwargs.pop('timeout', 30)
        for attempt in range(1, retries + 1):
            try:
                merged_headers = {**self.headers, **kwargs.pop('headers', {})}
                resp = requests.post(url, headers=merged_headers, timeout=timeout, **kwargs)
                resp.raise_for_status()
                return resp
            except requests.exceptions.RequestException as e:
                if attempt == retries:
                    print(f"  ⚠️  [{self.company}] Request error (시도 {attempt}/{retries}): {e}")
                else:
                    wait = backoff ** (attempt - 1)
                    print(f"  ↩️  [{self.company}] 재시도 {attempt}/{retries} ({wait:.0f}초 후): {e}")
                    time.sleep(wait)
        return None

    def playwright_fetch(self, url: str, wait_selector: str = "body", timeout: int = 20000) -> str:
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(user_agent=self.headers['User-Agent'])
                page = context.new_page()
                page.goto(url, wait_until="networkidle", timeout=timeout)
                if wait_selector:
                    page.wait_for_selector(wait_selector, timeout=timeout)
                content = page.content()
                browser.close()
                return content
        except Exception as e:
            print(f"  ⚠️  [{self.company}] Playwright error: {e}")
            return ""

    def playwright_intercept(self, url: str, api_pattern: str, timeout: int = 30000) -> list:
        """브라우저로 url에 접속하면서 api_pattern이 포함된 XHR/fetch 응답을 캡처해 반환.

        직접 API POST가 CSRF 토큰·세션 쿠키 부재로 봇 차단(400)되는 사이트에서 사용.
        브라우저가 페이지를 정상 로드하면서 내부 API를 자동 호출하므로,
        세션 인증이 브라우저 수준에서 투명하게 처리됨.
        현재 사용처: NVIDIA (Workday 봇 차단 우회)

        참고: SPA가 JS 번들 로드 후 비동기로 API를 호출하기 때문에
        networkidle로는 API 응답 캡처 전에 종료될 수 있음.
        domcontentloaded + 명시적 대기로 해결.
        """
        results = []
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(user_agent=self.headers['User-Agent'])
                page = context.new_page()

                api_hit = []

                def handle_response(response):
                    if api_pattern in response.url and response.status == 200:
                        try:
                            results.append(response.json())
                            api_hit.append(True)
                        except Exception:
                            pass

                page.on("response", handle_response)
                page.goto(url, wait_until="domcontentloaded", timeout=timeout)

                # SPA가 JS 번들 로드 → API 호출까지 시간이 걸리므로
                # 타겟 API 응답이 올 때까지 폴링 대기 (최대 timeout)
                deadline = timeout
                poll_interval = 500
                waited = 0
                while not api_hit and waited < deadline:
                    page.wait_for_timeout(poll_interval)
                    waited += poll_interval

                # API 응답 후 추가 데이터 로딩 여유
                if api_hit:
                    page.wait_for_timeout(1000)

                browser.close()
        except Exception as e:
            print(f"  ⚠️  [{self.company}] Intercept error: {e}")
        return results