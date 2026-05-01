# Job Radar — 기술 설명서

## 목차

1. [프로젝트 개요](#1-프로젝트-개요)
2. [디렉터리 구조](#2-디렉터리-구조)
3. [전체 아키텍처](#3-전체-아키텍처)
4. [크롤링 기법](#4-크롤링-기법)
5. [직무 분류 알고리즘](#5-직무-분류-알고리즘)
6. [크롤러별 상세](#6-크롤러별-상세)
7. [데이터 구조](#7-데이터-구조)
8. [설정 파일](#8-설정-파일)
9. [GitHub Actions 자동화](#9-github-actions-자동화)
10. [새 크롤러 추가 방법](#10-새-크롤러-추가-방법)

---

## 1. 프로젝트 개요

여러 테크 기업의 채용 페이지를 자동으로 수집해 하나의 대시보드에서 검색·필터링할 수 있는 개인용 채용 레이더.

- **백엔드**: Python 크롤러 → `docs/data/jobs.json` 생성
- **프론트엔드**: 순수 HTML/CSS/JS 정적 사이트 (GitHub Pages 배포)
- **자동화**: GitHub Actions 매주 월요일 09:00 KST 실행 (선택)

---

## 2. 디렉터리 구조

```
job-radar/
├── crawlers/
│   ├── __init__.py          # 크롤러 레지스트리 (get_all_crawlers)
│   ├── base.py              # BaseCrawler 추상 클래스
│   ├── classifier.py        # 직무 분류 모듈 (키워드 + 트랜스포머)
│   ├── google.py            # Google — Playwright + JS evaluate
│   ├── nvidia.py            # NVIDIA — Playwright XHR 인터셉트
│   ├── samsung.py           # Samsung — Playwright + 조건부 대기
│   ├── naver.py             # Naver — 내부 AJAX API
│   ├── toss.py              # Toss — Playwright (Next.js)
│   ├── upstage.py           # Upstage — Requests + BeautifulSoup
│   ├── generic_greenhouse.py # Greenhouse ATS 공용 크롤러
│   └── generic_ashby.py     # Ashby ATS 공용 크롤러
├── docs/                    # 정적 웹 UI (GitHub Pages)
│   ├── index.html
│   ├── style.css
│   ├── app.js
│   └── data/
│       └── jobs.json        # 크롤링 결과 (자동 생성)
├── .github/workflows/
│   └── weekly-crawl.yml     # GitHub Actions 워크플로우
├── main.py                  # 크롤링 실행 진입점
├── server.py                # 로컬 개발 서버
├── toggle_schedule.py       # GitHub Actions 스케줄 on/off
├── config.json              # 크롤러 활성화 설정
└── requirements.txt
```

---

## 3. 전체 아키텍처

```
┌─────────────────────────────────────────────────────┐
│                     main.py                         │
│  config.json 읽기 → 활성 크롤러 선택 → 순차 실행      │
│  부분 실행 시 기존 jobs.json 병합 (merge 모드)        │
└──────────────────────┬──────────────────────────────┘
                       │
          ┌────────────▼────────────┐
          │      BaseCrawler        │  (추상 클래스)
          │  - safe_request()       │  공통 HTTP 요청
          │  - playwright_fetch()   │  JS 렌더링 페이지
          │  - playwright_intercept()│ XHR 응답 캡처
          │  - format_job()         │  표준 데이터 포맷
          │  - is_expired()         │  마감일 필터
          └────────────┬────────────┘
                       │ 상속
        ┌──────────────┼──────────────┐
        ▼              ▼              ▼
   REST API       Requests       Playwright
   크롤러         + BS4          기반 크롤러
  (Greenhouse    (Naver,         (Google,
   Ashby)        Upstage)       NVIDIA, Toss
                                Samsung)
                       │
                       ▼
              crawlers/classifier.py
              직무명 → role 분류
              (키워드 → 트랜스포머)
                       │
                       ▼
              docs/data/jobs.json
                       │
                       ▼
              docs/app.js (프론트엔드)
              필터링 · 검색 · 렌더링
```

**적용 패턴**

- **Template Method**: `BaseCrawler`가 공통 인프라 제공, 서브클래스는 `fetch_jobs()`만 구현
- **Factory**: `get_all_crawlers()`가 크롤러 인스턴스 딕셔너리 반환
- **Singleton**: `classifier.py`의 트랜스포머 모델을 프로세스당 1회만 로드

---

## 4. 크롤링 기법

### 4-1. 공개 REST API 직접 호출

**사용 크롤러**: Anthropic (Greenhouse), OpenAI (Ashby)

```
requests.get(api_url) → JSON 파싱 → format_job()
```

Greenhouse, Ashby 같은 ATS(채용관리시스템)는 `board_token`만 알면
인증 없이 공개 API로 전체 공고를 JSON으로 제공한다.

| 장점                                      | 단점                                                |
| ----------------------------------------- | --------------------------------------------------- |
| 가장 빠르고 안정적                        | 회사가 ATS를 교체하면 즉시 404                      |
| HTML 구조 변경에 영향 없음                | board_token을 직접 찾아야 함                        |
| 페이지네이션·마감일 등 구조화 데이터 제공 | OpenAI가 Greenhouse → Ashby 이전으로 깨진 전례 있음 |

---

### 4-2. Requests + BeautifulSoup (SSR 스크래핑)

**사용 크롤러**: Upstage, Naver (보조)

서버가 완성된 HTML을 내려주는 SSR 페이지를 정적 파싱한다.
Naver는 HTML 파싱 외에 내부 AJAX API(`/rcrt/loadJobList.do`)를
직접 호출해 JSON으로 페이지네이션 처리한다.

```
requests.get(url)
  → BeautifulSoup HTML 파싱 → CSS 셀렉터로 링크 추출

또는 (Naver)
requests.get(ajax_api?firstIndex=N)
  → JSON 파싱 → 페이지네이션 반복
```

| 장점                             | 단점                         |
| -------------------------------- | ---------------------------- |
| 빠름. 브라우저 불필요            | JS 렌더링 페이지에 사용 불가 |
| Playwright 대비 리소스 1/10 수준 | SSR → CSR 전환 시 즉시 깨짐  |

---

### 4-3. Playwright + HTML/JS 파싱 (CSR/SPA 렌더링)

**사용 크롤러**: Google, Samsung, Toss

실제 Chromium 브라우저를 headless로 실행해 JS 렌더링이 완료된
후 DOM을 파싱한다.

```
Playwright Chromium 실행
  → page.goto(url, wait_until="networkidle")
  → wait_for_selector(특정 요소 등장 대기)
  → page.evaluate()   ← JS 컨텍스트에서 DOM 직접 순회
    또는 BeautifulSoup으로 HTML 파싱
```

**`page.evaluate()` 사용 이유 (Google)**
CSS 셀렉터 `a[href*="..."]`는 HTML에 기록된 속성 문자열 기준으로
매칭하는데, Google DOM의 job 링크는 대부분 절대경로(`https://...`)로
저장되어 있어 1건만 잡힌다. `a.href` 프로퍼티는 브라우저가 항상
full URL을 반환하므로 JS 컨텍스트에서 처리해야 전부 수집된다.

```
querySelectorAll('a[href*="/jobs/results/"]')  →  1건  (HTML 속성 기준)
a.href 프로퍼티로 필터링                        →  20건 (full URL 기준)
```

| 장점                       | 단점                             |
| -------------------------- | -------------------------------- |
| JS 렌더링 페이지 처리 가능 | 느림 (페이지당 5~15초)           |
| 실제 브라우저와 동일한 DOM | 메모리 소비 큼                   |
| 쿠키·세션 자동 처리        | CSS 클래스 난독화 시 셀렉터 깨짐 |

---

### 4-4. Playwright XHR 인터셉트

**사용 크롤러**: NVIDIA (Workday)

브라우저가 페이지를 로드하면서 발생시키는 내부 API 응답을
`page.on("response", handler)`로 실시간 캡처한다.

```
page.on("response", handler)  ← 응답 감청 등록
  → page.goto(url)            ← 브라우저가 페이지 로드
    → Workday 내부 API 자동 호출
      → handler: /wday/cxs/ 패턴 응답 캡처
        → jobPostings JSON 파싱
```

**도입 배경**
Workday API를 직접 POST하면 CSRF 토큰·세션 쿠키 부재를 이유로
400을 반환한다. 브라우저가 정상 로드하면서 세션을 자동 수립하므로
차단이 우회되고, 브라우저가 내부 API를 자동 호출하는 것을
가로채는 방식이라 API 명세를 역공학할 필요가 없다.

| 장점                      | 단점                            |
| ------------------------- | ------------------------------- |
| 봇 차단(400) 우회         | Playwright 의존                 |
| API 명세 몰라도 수집 가능 | 응답 암호화 도입 시 재차단 가능 |
| 세션·CSRF 자동 처리       | 페이지 로드 시간만큼 대기 필요  |

---

## 5. 직무 분류 알고리즘

**파일**: `crawlers/classifier.py`

각 공고의 직무명(`title`)을 7개 분류 중 하나로 자동 분류한다.

```
직무명 입력
   │
   ▼
[1단계] 키워드 매칭
   │  KEYWORD_MAP에서 카테고리별 키워드 우선순위 순으로 검색
   │  매칭 시 즉시 반환
   │ 미매칭
   ▼
[2단계] 트랜스포머 임베딩 유사도 (Zero-shot)
   │  모델: paraphrase-multilingual-MiniLM-L12-v2 (~420MB)
   │  한국어 + 영어 동시 지원, CPU 추론 가능
   │
   │  1. 카테고리별 앵커 문장을 사전에 임베딩
   │  2. 직무명 임베딩과 코사인 유사도 계산
   │  3. 최고 유사도 카테고리 선택
   │
   ├── 유사도 ≥ 0.28 → 해당 카테고리 반환
   └── 유사도 < 0.28 → "기타"
```

**키워드 체크 순서 (우선순위)**

```
AI / ML → 보안 → 영업/사업개발 → 마케팅 → 제품/기획 → 운영/경영지원 → 개발
```

순서가 중요한 이유: "Security Engineer"는 보안이 개발보다 먼저 체크되어야
개발로 잘못 분류되지 않는다. "ML Engineer" 역시 AI/ML이 개발보다 앞선다.

**성능** (1,448건 기준)

- 기타 비율: 약 1% 미만
- 모델 최초 로딩: ~3초 (이후 캐시, 재로딩 없음)
- 추론 속도: 1,000건/초 수준 (CPU)

**7개 직무 분류**

| 분류            | 대표 직무                                            |
| --------------- | ---------------------------------------------------- |
| 개발            | Software Engineer, Backend, Frontend, DevOps, SRE    |
| AI / ML         | Research Scientist, ML Engineer, Data Scientist, LLM |
| 보안            | Security Engineer, AML, Compliance, KYC, SOX         |
| 영업 / 사업개발 | Account Executive, Sales, Business Development, GTM  |
| 마케팅          | Marketing Manager, PR, Communications, 마케터        |
| 제품 / 기획     | Product Manager, Program Manager, Designer, UX       |
| 운영 / 경영지원 | Operations, Finance, HR, Legal, Administrative       |

---

## 6. 크롤러별 상세

| 크롤러    | 방식                     | 페이지네이션                        | 마감일 필터            | 비고                                                  |
| --------- | ------------------------ | ----------------------------------- | ---------------------- | ----------------------------------------------------- |
| Anthropic | Greenhouse REST API      | 없음 (API가 활성 공고만 반환)       | `first_published` 필드 | board_token: `anthropic`                              |
| OpenAI    | Ashby REST API           | 없음                                | `isListed=false` 제외  | board_token: `openai`                                 |
| Naver     | 내부 AJAX JSON API       | `firstIndex` 파라미터               | `endYmd < today` 제외  | `totalRows` JS 변수로 총 페이지 계산                  |
| Google    | Playwright + JS evaluate | `aria-label="Go to next page"` 클릭 | 없음                   | 쿠키 팝업 자동 클릭 필요                              |
| NVIDIA    | Playwright XHR 인터셉트  | 없음 (초기 로드만)                  | 없음                   | Workday 봇 차단 우회                                  |
| Samsung   | Playwright + BS4         | 없음                                | 없음                   | `jobOpeningView` 요소 대기, 공고 없는 기간엔 0건 정상 |
| Toss      | Playwright + BS4         | 없음                                | 없음                   | Next.js CSR, 네비게이션 링크 필터링                   |
| Upstage   | Requests + BS4           | 없음                                | 없음                   | Greeting HR SSR, `/ko/o/{id}` 패턴                    |

---

## 7. 데이터 구조

### jobs.json

```json
{
  "updated_at": "2026-05-01T15:20:04.123456",
  "total": 1448,
  "results": {
    "Anthropic": 439,
    "OpenAI": 667
  },
  "jobs": [ ... ]
}
```

### 단일 공고 객체

```json
{
  "company": "Anthropic",
  "category": "외국계",
  "role": "AI / ML",
  "title": "Research Scientist",
  "url": "https://...",
  "location": "San Francisco, CA",
  "department": "Research",
  "posted_date": "2026-03-25T10:53:39-04:00",
  "crawled_at": "2026-05-01T15:20:04.123456"
}
```

| 필드          | 설명                                                  |
| ------------- | ----------------------------------------------------- |
| `category`    | 회사 분류 (외국계 / IT / 금융 / 스타트업 / 제조업)    |
| `role`        | 직무 분류 (7개 + 기타) — classifier.py가 자동 분류    |
| `posted_date` | 형식이 회사마다 다름 (ISO 8601 / YYYY-MM-DD / 텍스트) |
| `crawled_at`  | 수집 시각 (항상 ISO 8601)                             |

---

## 8. 설정 파일

### config.json

```json
{
  "schedule": {
    "enabled": false,
    "interval": "weekly",
    "last_updated": "2026-05-01T15:00:00"
  },
  "crawlers": {
    "NVIDIA": true,
    "Google": true,
    "Anthropic": true,
    "OpenAI": true,
    "Samsung": true,
    "Naver": true,
    "Toss": true,
    "Upstage": true
  }
}
```

- `schedule.enabled`: GitHub Actions 자동 실행 여부 (`toggle_schedule.py`로 변경)
- `crawlers.<name>`: `false`면 `python main.py` 기본 실행에서 제외

---

## 9. GitHub Actions 자동화

**파일**: `.github/workflows/weekly-crawl.yml`

```
매주 월요일 00:00 UTC (09:00 KST)
  → config.json의 schedule.enabled 확인
  → true일 때만 실행:
      pip install -r requirements.txt
      playwright install chromium --with-deps
      python main.py
      git add -f docs/data/jobs.json config.json
      git commit & push
```

**주의**: `git add -f` 플래그 필수.
`docs/data/jobs.json`이 `.gitignore`에 등록되어 있어
`-f` 없이는 스테이지에 올라가지 않아 커밋이 스킵된다.

---

## 10. 새 크롤러 추가 방법

### 1단계 — 크롤러 파일 생성

```python
# crawlers/newcompany.py
from .base import BaseCrawler

class NewCompanyCrawler(BaseCrawler):
    def __init__(self):
        super().__init__("NewCompany", "카테고리")  # 외국계 / IT / 금융 / 스타트업 / 제조업
        self.url = "https://..."

    def fetch_jobs(self):
        jobs = []
        resp = self.safe_request(self.url)
        if not resp:
            return jobs
        # 파싱 로직
        jobs.append(self.format_job(
            title="...",
            url="...",
            location="...",
            department="...",
            posted_date="..."
        ))
        return jobs
```

`format_job()`을 호출하면 `role` 분류가 자동으로 붙는다.

### 2단계 — 레지스트리 등록

```python
# crawlers/__init__.py
from .newcompany import NewCompanyCrawler

def get_all_crawlers():
    return {
        ...
        "NewCompany": NewCompanyCrawler(),
    }
```

### 3단계 — config.json에 추가

```json
"crawlers": {
    "NewCompany": true
}
```

### 사이트 유형별 권장 방식

| 사이트 유형                    | 권장 방식                                                          |
| ------------------------------ | ------------------------------------------------------------------ |
| Greenhouse / Ashby / Lever ATS | `generic_greenhouse.py` 또는 `generic_ashby.py`에 board_token 추가 |
| SSR (서버 렌더링)              | `safe_request()` + BeautifulSoup                                   |
| CSR / SPA (React, Next.js)     | `playwright_fetch()`                                               |
| API가 봇 차단인 경우           | `playwright_intercept()`                                           |
