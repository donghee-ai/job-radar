"""
수집 후처리 — 크롤러가 넘긴 원본 공고에 파생 필드를 붙인다.

크롤러마다 같은 로직을 넣지 않고 main.py 마지막에 한 번 돌리므로,
분류 규칙을 바꾸면 다음 실행에서 이전 데이터(크롤 실패로 유지된 공고 포함)까지
모두 새 규칙으로 다시 분류된다.

붙이는 필드
  role, role_group   직무 / 직군 (classifier.py)
  seniority          인턴 · 신입/주니어 · 경력 · 시니어 · 리더  (모르면 "")
  employment         계약직 (정규직·미표기는 "")
  regions            ["한국", "북미", "유럽", "아시아·태평양", "원격", "기타"] 중 해당 지역들
  first_seen         이 URL을 처음 수집한 날짜 (KST, YYYY-MM-DD)
"""

from __future__ import annotations

import re
import unicodedata

from .classifier import classify

# ─── 연차 ────────────────────────────────────────────────────────────────────

_LEVELS = [
    # (레벨, 패턴) — 위에서부터 먼저 맞는 것을 채택
    ("인턴", r"\bintern(ship)?s?\b|인턴|체험형|\bco-?op\b|\bapprentice"),
    ("신입/주니어", r"\bnew grad|\bentry[- ]level|\bjunior\b|\bjr\.?\s|신입|주니어|"
                 r"\buniversity grad|\bearly career|\d+\s*년\s*이하"),
    ("리더", r"\bhead of\b|\bdirector\b|\bvp\b|\bvice president|\bchief\b|\bengineering manager|"
           r"\btech(nical)? lead|\bteam lead|\bleader\b|^manager\b|\bsenior manager|"
           r"\bgroup manager|\bgeneral manager|팀장|리더|본부장|실장|\blead\b"),
    ("시니어", r"\bsenior\b|\bsr\.?\s|\bstaff\b|\bprincipal\b|\bdistinguished\b|시니어|"
             r"(?:[5-9]|1\d)\s*년\s*이상"),
    ("경력", r"경력(?!\s*무관)|\bexperienced\b|\d+\s*년\s*이상"),
]
_LEVELS = [(lv, re.compile(p, re.I)) for lv, p in _LEVELS]


LEVELS = ["인턴", "신입/주니어", "경력", "시니어", "리더"]

# 채용 사이트가 따로 주는 레벨 태그 (Google: Early / Mid / Advanced / Director+)
_TAG_LEVELS = {"early": "신입/주니어", "mid": "경력", "advanced": "시니어",
               "director+": "리더", "director": "리더", "intern & apprentice": "인턴"}


def seniority(title: str, extra_tags=()) -> str:
    """직함 → 사이트 레벨 태그 → 나머지 태그 텍스트 순으로 본다.
    태그를 직함과 섞어 검색하면 "Mid-Market" 같은 직함 단어가 레벨로 오인된다."""
    t = unicodedata.normalize("NFKC", title or "")
    for level, pat in _LEVELS:
        if pat.search(t):
            return level
    for tag in extra_tags:
        if tag.strip().lower() in _TAG_LEVELS:
            return _TAG_LEVELS[tag.strip().lower()]
    extra = unicodedata.normalize("NFKC", " ".join(extra_tags))
    for level, pat in _LEVELS:
        if pat.search(extra):
            return level
    return ""


_CONTRACT = re.compile(r"계약|\bcontract\b|fixed[- ]?term|\btemporary\b|\btemp\b|파견|기간제", re.I)


def employment(title: str, extra: str = "") -> str:
    return "계약직" if _CONTRACT.search(f"{title} {extra}") else ""


# 특정 자리가 아니라 인재풀·상시 지원 성격의 게시물 (실제 게시물이지만 구분해서 보여준다)
_POOL = re.compile(r"인재풀|멘토풀|talent (pool|community)|expression of interest|general application", re.I)


def is_pool(title: str) -> bool:
    return bool(_POOL.search(title or ""))


# ─── 지역 ────────────────────────────────────────────────────────────────────

_REGION_PATTERNS = {
    "한국": r"korea|seoul|pangyo|seongnam|suwon|incheon|busan|daejeon|서울|한국|판교|성남|"
           r"경기|수원|화성|기흥|평택|용인|대전|부산|대구|광주|인천|울산|창원|구미|세종|이천|청주|분당",
    "북미": r"united states|\busa?\b|san francisco|new york|seattle|washington|\bdc\b|boston|"
           r"austin|santa clara|mountain view|sunnyvale|palo alto|san jose|los angeles|chicago|"
           r"atlanta|denver|pittsburgh|savannah|texas|\bca\b|\bny\b|\bwa\b|\bma\b|\btx\b|canada|"
           r"\bcan\b|ontario|toronto|vancouver|montreal|waltham",
    "유럽": r"london|\buk\b|united kingdom|dublin|ireland|\bie\b|munich|germany|berlin|paris|"
           r"france|z[uü]rich|switzerland|\bch\b|madrid|spain|milan|italy|amsterdam|netherlands|"
           r"stockholm|sweden|warsaw|poland|oslo|copenhagen|brussels|lisbon|europe|\bemea\b",
    "아시아·태평양": r"tokyo|japan|singapore|sydney|melbourne|australia|india|delhi|mumbai|"
                 r"bangalore|bengaluru|hyderabad|taipei|taiwan|hong kong|shanghai|beijing|"
                 r"shenzhen|china|jakarta|indonesia|bangkok|manila|vietnam|\bapac\b",
    "원격": r"remote",
}
_REGION_PATTERNS = {k: re.compile(v, re.I) for k, v in _REGION_PATTERNS.items()}
REGIONS = list(_REGION_PATTERNS) + ["기타"]


def regions(location: str) -> list[str]:
    loc = unicodedata.normalize("NFKC", location or "")
    found = [name for name, pat in _REGION_PATTERNS.items() if pat.search(loc)]
    if not found and loc.strip():
        found = ["기타"]
    return found


# ─── 일괄 적용 ────────────────────────────────────────────────────────────────

def clean_title(title: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", title or "")).strip()


def enrich_job(job: dict, first_seen: str) -> dict:
    title = clean_title(job.get("title", ""))
    tags = job.get("tags") or []
    extra = " ".join(tags)
    c = classify(title, job.get("department", ""), tags)
    job.update({
        "title": title,
        "role": c.role,
        "role_group": c.group,
        "seniority": seniority(title, tags),
        "employment": employment(title, extra),
        "pool": is_pool(title),
        "regions": regions(job.get("location", "")),
        "first_seen": first_seen,
    })
    return job


def enrich_jobs(jobs: list[dict], previous: list[dict], today: str) -> list[dict]:
    """previous(직전 jobs.json)의 first_seen을 URL 기준으로 이어받는다.
    직전 데이터에 first_seen이 없던 공고(추적 도입 전)와 새로 추가한 회사의 첫 수집분은
    ""로 두어 '신규'로 오인하지 않게 한다."""
    known: dict[str, str] = {}
    tracked = set()
    for p in previous:
        tracked.add(p.get("company"))
        url = p.get("url")
        if url:
            known[url] = p.get("first_seen", "")
    seen_urls = set()
    out = []
    for j in jobs:
        url = j.get("url")
        if url in seen_urls:   # 같은 공고가 여러 번 잡히는 경우(페이지네이션 중복 등) 제거
            continue
        seen_urls.add(url)
        if url in known:
            first = known[url]
        elif j.get("company") not in tracked and previous:
            # 추적 대상에 새로 넣은 회사의 첫 수집분은 '새 공고'가 아니라 기준선
            first = ""
        else:
            first = today
        out.append(enrich_job(j, first))
    return out
