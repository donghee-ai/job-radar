from abc import ABC, abstractmethod
from datetime import datetime, timedelta, timezone
from typing import List, Dict
import time
import requests

KST = timezone(timedelta(hours=9))


def now_utc() -> datetime:
    """기록용 현재 시각 — UTC.
    isoformat() 결과에 +00:00 오프셋이 붙는다. 오프셋만 있으면 표시 계층이
    어느 지역 시간으로든 정확히 변환하므로, 저장은 UTC로 통일한다."""
    return datetime.now(timezone.utc)


def now_kst() -> datetime:
    """한국 달력 기준 판단용 현재 시각(UTC+9).
    '한국에서 오늘이 며칠인가'가 기준인 값에만 쓴다 — 크롤은 04:07 KST
    (= 전날 19:07 UTC)에 돌기 때문에 UTC로 날짜를 구하면 하루 밀린다."""
    return datetime.now(KST)


def describe_request_error(err) -> str:
    """requests 예외를 원인이 바로 보이는 한 줄로 바꾼다."""
    resp = getattr(err, "response", None)
    if resp is not None:
        hint = {403: "접근 거부", 404: "주소가 바뀌었거나 사라짐", 429: "요청 과다(rate limit)",
                500: "상대 서버 오류", 502: "상대 서버 오류", 503: "상대 서버 점검·과부하"}.get(resp.status_code, "")
        return f"HTTP {resp.status_code}{' ' + hint if hint else ''} — {resp.url}"
    if isinstance(err, requests.exceptions.Timeout):
        return f"응답 시간 초과 — {getattr(err.request, 'url', '')}"
    if isinstance(err, requests.exceptions.ConnectionError):
        return f"연결 실패(DNS·네트워크) — {getattr(err.request, 'url', '')}"
    return f"{type(err).__name__}: {err}"


def _retry_wait(err, attempt: int, backoff: float) -> float:
    """재시도 대기 시간. 429(요청 과다)면 서버가 준 Retry-After를 따르고,
    없으면 일반 오류보다 길게(10초 → 20초) 기다린다. 그 외는 1초 → 2초 → 4초."""
    resp = getattr(err, "response", None)
    if resp is not None and resp.status_code == 429:
        try:
            return min(float(resp.headers.get("Retry-After", "")), 60.0)
        except ValueError:
            return 10.0 * attempt
    return backoff ** (attempt - 1)


class BaseCrawler(ABC):
    def __init__(self, company: str, category: str, default_location: str = ""):
        self.company = company
        self.category = category
        self.default_location = default_location
        # 이번 실행에서 생긴 실패 원인. 0건이면 main.py가 마지막 원인을 기록·표시한다
        self.issues: List[str] = []
        self.headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                          'AppleWebKit/537.36 (KHTML, like Gecko) '
                          'Chrome/120.0.0.0 Safari/537.36'
        }

    @abstractmethod
    def fetch_jobs(self) -> List[Dict]:
        pass

    def warn(self, msg: str) -> None:
        """실패 원인을 출력하고 기록한다. 조용히 0건을 내는 대신 반드시 이걸 거친다."""
        self.issues.append(msg)
        print(f"  ⚠️  [{self.company}] {msg}")

    def format_job(self, title: str, url: str, location: str = "",
                   department: str = "", posted_date: str = "", tags=None) -> Dict:
        """크롤러 공통 출력 형식. 직무는 여기서 1차 분류하고,
        main.py의 enrich 단계에서 연차·지역 등과 함께 최종 확정한다."""
        from .classifier import classify_role
        tags = [t for t in (tags or []) if t]
        job = {
            "company": self.company,
            "category": self.category,
            "role": classify_role(title, department, tags),
            "title": title,
            "url": url,
            "location": location or self.default_location,
            "department": department,
            "posted_date": posted_date,
            "crawled_at": now_utc().isoformat()
        }
        if tags:
            job["tags"] = tags
        return job

    def is_expired(self, end_date_str: str, fmt: str = "%Y%m%d") -> bool:
        """end_date_str 을 fmt 형식으로 파싱해 오늘보다 이전이면 True 반환.
        파싱 실패 시 False (마감일 불명확 → 유지)."""
        try:
            return datetime.strptime(end_date_str, fmt).date() < now_kst().date()
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
                    self.warn(f"요청 실패({retries}회 시도): {describe_request_error(e)}")
                else:
                    wait = _retry_wait(e, attempt, backoff)
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
                    self.warn(f"요청 실패({retries}회 시도): {describe_request_error(e)}")
                else:
                    wait = _retry_wait(e, attempt, backoff)
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
            self.warn(f"브라우저 로딩 실패: {str(e).splitlines()[0]}")
            return ""

    def playwright_intercept(self, url: str, api_pattern: str, timeout: int = 30000) -> list:
        """브라우저로 url에 접속하면서 api_pattern이 포함된 XHR/fetch 응답을 캡처해 반환.

        페이지가 내부 API로 데이터를 받아오는 SPA에서 사용.
        세션·CSRF 처리는 브라우저가 맡으므로 API 스펙을 몰라도 됨.
        현재 사용처: NVIDIA (Workday)

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
                else:
                    self.warn(f"페이지는 열렸지만 공고 API({api_pattern}) 응답이 {timeout // 1000}초 안에 오지 않음"
                              f" — 받은 페이지 제목 {page.title()!r}")

                browser.close()
        except Exception as e:
            self.warn(f"브라우저 로딩 실패: {str(e).splitlines()[0]}")
        return results