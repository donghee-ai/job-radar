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
                   department: str = "", posted_date: str = "") -> Dict:
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
            "crawled_at": datetime.now().isoformat()
        }

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
        """
        results = []
        try:
            from playwright.sync_api import sync_playwright
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                context = browser.new_context(user_agent=self.headers['User-Agent'])
                page = context.new_page()

                def handle_response(response):
                    if api_pattern in response.url and response.status == 200:
                        try:
                            results.append(response.json())
                        except Exception:
                            pass

                page.on("response", handle_response)
                page.goto(url, wait_until="networkidle", timeout=timeout)
                browser.close()
        except Exception as e:
            print(f"  ⚠️  [{self.company}] Intercept error: {e}")
        return results