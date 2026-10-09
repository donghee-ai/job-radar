"""
직무 분류 모듈 — 가중치 규칙 + 임베딩 폴백

[분류 체계]  4개 직군 / 16개 직무 (+ 기타). ROLE_GROUPS 참고.

[1단계] 가중치 규칙 매칭 (휴리스틱 NLP)
  1. 정규화: NFKC, 소문자화, [회사명] 접두어·(경력)/(~10/11) 같은 괄호 메타 제거
  2. 분절: 쉼표 · " - " · "|" 기준으로 head(직함 본체)와 나머지(팀·도메인·지역)로 나눔.
     영문 직함은 앞 조각이 직무를 결정한다 ("Software Engineer, Research" → 개발).
     앞 조각이 "Senior Manager"처럼 일반어뿐이면 다음 조각을 head로 승격
     ("Senior Manager, EHS - Robotics" → head = "EHS").
  3. 규칙 매칭: 영문은 단어 경계 정규식(ios가 scenarios에 걸리지 않게),
     한글은 부분 문자열. 구(phrase)일수록 가중치가 높아 구체적인 표현이 이긴다
     ("product marketing manager" → 마케팅, "engineering manager" → 개발).
  4. 점수: head 매칭 ×1.0, 나머지 ×0.5, 부서(department) ×0.6, 태그 ×0.4.
     직무별 점수 = 최고 매칭 가중치 + 나머지 매칭 합 × 0.3.
     동점이면 ROLE_PRIORITY 순서.

[2단계] 임베딩 kNN 폴백 — 기본 꺼짐 (JOB_RADAR_EMBEDDING=1 + sentence-transformers 설치 시)
  - 홀드아웃 80건에서 규칙만 87.3%, 임베딩 추가해도 87.3% — 정확도 이득이 없고
    저신뢰 직함에 엉뚱한 답을 냄("IT Supporter" → 마케팅). 반면 CI에서 torch 설치 +
    모델 420MB 다운로드 비용이 매번 든다. 그래서 확신 없는 직함은 기타로 두는 쪽을 택함.
  - 규칙 점수가 MIN_RULE_SCORE 미만일 때만 사용
  - 직무별 예시 직함(EXEMPLARS)과 코사인 유사도 → 최댓값이 가장 큰 직무
  - 유사도 EMB_THRESHOLD 미만이거나 1·2위 차이가 EMB_MARGIN 미만이면 기타

[평가]  tests/data/role_gold.tsv (실데이터에서 뽑아 손으로 라벨링한 직함)
        python -m crawlers.classifier --eval  로 정확도/오분류 확인
"""

from __future__ import annotations

import os
import re
import unicodedata
from functools import lru_cache
from typing import NamedTuple, Optional

# ─── 분류 체계 ────────────────────────────────────────────────────────────────

ROLE_GROUPS: dict[str, list[str]] = {
    "엔지니어링": [
        "AI / ML", "소프트웨어 개발", "데이터", "하드웨어 / 반도체", "로보틱스 / 자율주행",
        "제조 / 품질", "보안",
    ],
    "제품 · 디자인": ["제품 / 기획", "디자인"],
    "비즈니스": ["영업 / 사업개발", "솔루션 / 고객지원", "마케팅 / PR"],
    "운영 · 지원": ["운영 / 전략", "리스크 / 컴플라이언스", "법무 / 정책", "경영지원"],
}
OTHER = "기타"
ROLE_TO_GROUP = {r: g for g, roles in ROLE_GROUPS.items() for r in roles}
ROLE_TO_GROUP[OTHER] = OTHER

# 동점일 때 앞쪽이 이긴다. 도메인이 좁은 직무를 앞에 둔다.
ROLE_PRIORITY = [
    "로보틱스 / 자율주행", "하드웨어 / 반도체", "제조 / 품질", "AI / ML", "보안", "리스크 / 컴플라이언스",
    "데이터", "솔루션 / 고객지원", "디자인", "법무 / 정책", "마케팅 / PR",
    "영업 / 사업개발", "제품 / 기획", "경영지원", "운영 / 전략", "소프트웨어 개발",
]

# ─── 1단계: 규칙 ──────────────────────────────────────────────────────────────
# (패턴, 가중치). 영문 패턴의 공백은 공백/하이픈/슬래시 모두 매칭, 끝의 복수형 s 허용.
# 가중치 기준: 4 = 그 자체로 직무가 확정되는 구, 3 = 강한 직함 명사,
#              2 = 도메인 단서, 1 = 약한 단서

RULES: dict[str, list[tuple[str, float]]] = {
    "AI / ML": [
        ("research scientist", 4), ("research engineer", 4), ("applied scientist", 4),
        ("machine learning", 3), ("deep learning", 3), ("reinforcement learning", 3),
        ("ml engineer", 4), ("ai engineer", 3), ("ai researcher", 4), ("ai research", 3),
        ("ml researcher", 4), ("ml infrastructure", 2), ("researcher", 2.5),
        ("llm", 2.5), ("nlp", 2.5), ("natural language", 2.5), ("computer vision", 3),
        ("vision language", 2.5), ("vlm", 2.5), ("multimodal", 2), ("neural", 2),
        ("foundation model", 2.5), ("pre training", 2.5), ("pretraining", 2.5),
        ("post training", 2.5), ("fine tuning", 2.5), ("rlhf", 2.5), ("alignment", 2),
        ("interpretability", 2.5), ("prompt engineer", 3), ("model behavior", 2),
        ("evals", 2), ("lm eval", 2.5), ("inference", 1.5), ("generative", 1.5),
        ("ai fellow", 3), ("on device ai", 3), ("agentic", 2), ("genai", 2), ("fellows program", 2.5), ("ai", 1), ("ml", 1.5), ("rl", 1.5),
        ("research", 1), ("re rs", 4), ("ml framework", 3),
        ("인공지능", 3), ("머신러닝", 3), ("딥러닝", 3), ("ai 연구", 3), ("모델 연구", 3),
        ("에이전트", 1.5), ("생성형", 1.5), ("연구원", 1.5), ("학습", 1),
    ],
    "소프트웨어 개발": [
        ("software engineer", 3), ("software developer", 3), ("software engineering", 2.5),
        ("swe", 3), ("backend", 3), ("back end", 3), ("frontend", 3), ("front end", 3),
        ("full stack", 3), ("fullstack", 3), ("mobile engineer", 3), ("ios", 3),
        ("android", 3), ("web developer", 3), ("devops", 3), ("site reliability", 3),
        ("sre", 3), ("platform engineer", 3), ("infrastructure engineer", 3),
        ("systems engineer", 2.5), ("system software", 3), ("operating systems", 3),
        ("kernel", 2.5), ("compiler", 3), ("distributed systems", 3),
        ("engineering manager", 3.5), ("member of technical staff", 2.5),
        ("cloud engineer", 3), ("network engineer", 3), ("production engineer", 3),
        ("build engineer", 3), ("release engineer", 3), ("qa engineer", 3),
        ("test automation", 3), ("developer productivity", 3), ("mlops", 3), ("ml ops", 3.5), ("aiops", 3),
        ("middleware", 3),
        ("developer", 2), ("programmer", 3), ("infrastructure", 1.5), ("platform", 1),
        ("server", 1.5), ("api", 1.5), ("kubernetes", 2), ("typescript", 2), ("kotlin", 2),
        ("java", 2), ("swift", 2), ("react", 2), ("spring", 1.5), ("engineer", 1),
        ("engineering", 1), ("systems generalist", 2), ("tech lead", 3), ("technical lead", 3),
        ("qa", 3), ("quality assurance", 3), ("sqa", 3), ("dba", 3.5), ("database", 2),
        ("software architect", 3.5), ("테스트", 2), ("품질검증", 3),
        ("개발자", 3), ("소프트웨어", 2.5), ("서버", 2), ("백엔드", 3), ("프론트엔드", 3),
        ("앱 개발", 3), ("웹 개발", 3), ("sw 개발", 3), ("플랫폼", 1.5), ("개발", 1.5),
        ("엔지니어", 1), ("프로그래머", 3),
    ],
    "데이터": [
        ("data scientist", 3.5), ("data science", 3), ("data engineer", 3.5),
        ("data analyst", 3.5), ("analytics engineer", 3.5), ("business intelligence", 3),
        ("analytics", 2.5), ("economist", 3), ("quantitative", 2.5), ("data", 1.5),
        ("sql", 2), ("airflow", 2), ("hadoop", 2), ("spark", 1.5), ("statistic", 2),
        ("데이터 분석", 3.5), ("데이터 엔지니어", 3.5), ("데이터 사이언티스트", 3.5),
        ("데이터", 1.5), ("분석가", 2.5),
    ],
    "하드웨어 / 반도체": [
        ("hardware", 3), ("asic", 3.5), ("silicon", 3), ("rtl", 3.5), ("fpga", 3.5),
        ("soc design", 3.5), ("soc architect", 3.5), ("physical design", 3.5),
        ("design verification", 3.5), ("verification engineer", 3.5), ("chip", 2.5),
        ("semiconductor", 3), ("pcb", 3), ("analog", 2.5), ("mixed signal", 3),
        ("signal integrity", 3), ("si pi", 3), ("electrical engineer", 3.5),
        ("mechanical engineer", 3.5), ("electrical", 2), ("mechanical", 2), ("thermal", 2.5),
        ("package", 2), ("packaging", 2), ("firmware", 3), ("embedded", 3),
        ("npu", 3), ("gpu architect", 3.5), ("accelerator", 2), ("data center", 2),
        ("datacenter", 2), ("commissioning", 3), ("rack", 2), ("cooling", 2.5),
        ("power engineer", 3), ("materials scientist", 3.5), ("cad", 3),
        ("hardware engineer", 4), ("dynamometer", 3), ("interconnect", 2),
        ("반도체", 3), ("회로", 3), ("하드웨어", 3), ("임베디드", 3), ("펌웨어", 3),
        ("기구 설계", 3), ("기구설계", 3), ("공정", 2.5), ("소자", 3), ("패키지", 2.5),
        ("인덕터", 3), ("탄탈", 3), ("전장", 2.5), ("단말기", 2.5), ("device", 1),
    ],
    "제조 / 품질": [
        ("manufacturing", 3), ("manufacturing engineer", 3.5), ("process engineer", 3),
        ("production", 2), ("production supervisor", 3.5), ("production lead", 3.5),
        ("quality engineer", 3.5), ("quality engineering", 3.5), ("quality", 2),
        ("product quality", 3), ("test engineer", 3), ("test technician", 4),
        ("test development", 3), ("validation", 2), ("technician", 3), ("machinist", 3.5),
        ("cnc", 3), ("fabricator", 3.5), ("fabrication", 3), ("assembly", 3), ("npi", 3),
        ("material handler", 3.5), ("3d printing", 2.5), ("prototyping", 2.5), ("prototype", 2),
        ("machining", 3.5), ("supplier development", 3), ("yield", 2.5),
        ("생산", 3), ("품질", 3), ("제조", 3), ("조립", 3), ("설비", 2.5), ("양산", 3),
    ],
    "로보틱스 / 자율주행": [
        ("robot", 4), ("robotics", 4), ("humanoid", 3.5), ("autonomous", 3),
        ("autonomy", 3), ("self driving", 3.5), ("perception", 2.5), ("slam", 3.5),
        ("motion planning", 3.5), ("manipulation", 3), ("locomotion", 3.5),
        ("control systems", 2.5), ("controls engineer", 3), ("actuator", 2.5),
        ("teleoperation", 3), ("lidar", 3), ("adas", 3.5), ("automotive", 2.5),
        ("drone", 3), ("uav", 3), ("embodied", 3), ("atlas", 1.5),
        ("로봇", 3.5), ("로보틱스", 3.5), ("자율주행", 3.5), ("휴머노이드", 3.5),
        ("제어", 2), ("모빌리티", 2), ("드론", 3), ("액추에이터", 3),
    ],
    "보안": [
        ("security engineer", 4), ("security analyst", 4), ("security architect", 4),
        ("security", 2.5), ("infosec", 3), ("information security", 3.5),
        ("cybersecurity", 3), ("cyber", 2.5), ("appsec", 3.5), ("detection", 2),
        ("incident response", 3), ("threat", 2.5), ("red team", 3.5), ("vulnerability", 3),
        ("penetration", 3), ("privacy engineer", 3.5), ("iam", 2), ("identity", 1.5),
        ("safeguards", 2), ("soc analyst", 3.5), ("security operations", 3.5),
        ("account takeover", 2),
        ("정보보안", 3.5), ("보안", 3), ("개인정보보호", 3), ("침해", 2.5), ("취약점", 3),
    ],
    "제품 / 기획": [
        ("product manager", 4), ("product owner", 4), ("product lead", 3.5),
        ("group product manager", 4), ("program manager", 2.5),
        ("technical program manager", 3.5), ("tpm", 3), ("project manager", 2.5),
        ("scrum master", 3), ("pmo", 3), ("technical writer", 3), ("documentation", 2.5), ("product management", 3), ("product", 1),
        ("기획", 3), ("서비스기획", 3.5), ("상품기획", 3.5), ("프로덕트", 2), ("po", 2),
        ("pm", 2), ("프로젝트 매니저", 2.5),
    ],
    "디자인": [
        ("designer", 4), ("design lead", 3.5), ("product design", 3.5), ("ux", 3),
        ("ui", 2.5), ("user experience", 3), ("user research", 3.5), ("ux researcher", 4),
        ("visual design", 3.5), ("brand design", 3.5), ("motion design", 3.5),
        ("illustrator", 3), ("3d artist", 3), ("design", 1.5),
        ("디자이너", 4), ("디자인", 3), ("일러스트", 3), ("유저리서치", 2.5),
    ],
    "영업 / 사업개발": [
        ("account executive", 4), ("account manager", 3.5), ("account director", 4),
        ("account strategist", 3.5), ("account management", 3.5), ("sales", 3),
        ("business development", 3.5), ("bdr", 3), ("sdr", 3), ("partner manager", 3.5),
        ("partnership", 3), ("partner", 1.5), ("alliance", 2.5), ("channel", 2),
        ("commercial", 1.5), ("revenue", 1.5), ("customer success", 3), ("gtm", 2),
        ("go to market", 2), ("go-to-market", 2), ("deal", 1.5), ("country lead", 2),
        ("expansion", 2), ("enablement", 1.5), ("field sales", 4), ("growth account", 3), ("client solutions", 3.5),
        ("영업", 3.5), ("세일즈", 3.5), ("사업개발", 4), ("제휴", 3), ("가맹", 3),
        ("파트너십", 3), ("소싱", 1.5),
    ],
    "솔루션 / 고객지원": [
        ("solutions architect", 4), ("solution architect", 4), ("solutions engineer", 4), ("solutions consultant", 4),
        ("solutions expert", 3.5), ("technical solutions", 3.5), ("architect", 2), ("escalation", 3),
        ("solution engineer", 4), ("sales engineer", 4), ("customer engineer", 4),
        ("forward deployed", 4.5), ("fde", 4), ("deployment lead", 4),
        ("deployment strategist", 4), ("applied ai architect", 4.5), ("ai architect", 3.5),
        ("support engineer", 4), ("field service", 4), ("field repair", 3.5), ("technical support", 4), ("customer support", 3.5),
        ("support delivery", 3.5), ("support specialist", 3.5), ("support", 1.5),
        ("technical account manager", 4.5), ("field engineer", 3), ("implementation", 2),
        ("onboarding", 2), ("customer education", 3), ("instructor", 3), ("trainer", 2.5),
        ("cx", 2), ("customer experience", 3),
        ("고객지원", 3.5), ("고객센터", 3.5), ("상담", 3), ("씨엑스", 2.5), ("고객관리", 2),
        ("기술지원", 3.5), ("강사", 3), ("교육", 1.5), ("솔루션", 2.5),
    ],
    "마케팅 / PR": [
        ("marketing", 3.5), ("marketer", 3.5), ("product marketing", 4.5),
        ("communications", 3), ("public relations", 3.5), ("pr", 2.5), ("brand", 2),
        ("content", 1.5), ("content manager", 3), ("campaign", 2.5), ("copywriter", 3.5),
        ("social media", 3), ("event", 2.5), ("community", 2), ("growth", 1.5),
        ("lifecycle", 2.5), ("seo", 3), ("creative", 2), ("editorial", 2),
        ("developer relations", 3.5), ("devrel", 3.5), ("evangelist", 3),
        ("developer advocate", 3.5), ("media", 1.5),
        ("마케팅", 3.5), ("마케터", 3.5), ("홍보", 3.5), ("브랜드", 2), ("콘텐츠", 1.5),
        ("커뮤니티", 2), ("퍼포먼스", 2),
    ],
    "운영 / 전략": [
        ("operations", 2.5), ("ops", 2), ("strategy", 2.5), ("business operations", 3.5),
        ("strategy and operations", 3.5), ("bizops", 3.5), ("chief of staff", 3.5),
        ("corporate development", 3.5), ("m&a", 3), ("trust and safety", 3.5), ("trust & safety", 3.5),
        ("content moderation", 3.5), ("ehs", 3.5), ("environmental health", 3.5),
        ("operator", 2.5), ("supply chain", 3.5), ("logistics", 3), ("sourcing", 2.5),
        ("procurement", 3), ("vendor", 2), ("inventory", 2.5), ("inventory control", 3), ("capacity", 2), ("capacity delivery", 3), ("program support", 2.5),
        ("settlement", 3), ("translator", 3), ("translation", 3), ("localization", 3), ("beta tester", 2.5),
        ("strategist", 2), ("planning", 1.5),
        ("운영", 3), ("전략", 2.5), ("사업전략", 3.5), ("신사업", 2.5), ("물류", 3),
        ("구매", 3), ("통번역", 3.5), ("번역", 3), ("식자", 3), ("현지화", 3), ("품질관리", 2.5),
    ],
    "리스크 / 컴플라이언스": [
        ("compliance", 3), ("aml", 3.5), ("anti money laundering", 4), ("kyc", 3.5),
        ("fds", 3.5), ("fraud", 3.5), ("risk", 2.5), ("risk management", 3.5),
        ("audit", 3), ("internal audit", 4), ("sox", 3), ("controls", 2.5), ("grc", 3),
        ("regulatory", 2.5), ("collections", 3), ("customer protection", 3),
        ("소비자보호", 3.5), ("대위변제", 3.5), ("채권", 3),
        ("자금세탁", 4), ("내부통제", 4), ("컴플라이언스", 3.5), ("감사", 3),
        ("금융사기", 3.5), ("이상거래", 3.5), ("리스크", 3), ("준법", 3.5), ("심사", 2.5),
    ],
    "법무 / 정책": [
        ("legal", 3.5), ("counsel", 4), ("attorney", 4), ("lawyer", 4), ("paralegal", 4),
        ("patent", 3), ("public policy", 4), ("policy", 2.5), ("government affairs", 4),
        ("global affairs", 4), ("public affairs", 4), ("affairs", 2.5),
        ("congressional", 3.5), ("political", 3), ("regulatory affairs", 4),
        ("legislative", 3.5), ("contracts manager", 3.5), ("contract manager", 3.5), ("government relations", 4),
        ("변호사", 4), ("법무", 4), ("외국법자문사", 4), ("특허", 3), ("대외협력", 3.5),
        ("대관", 3), ("정책", 2.5), ("규제", 2),
    ],
    "경영지원": [
        ("finance", 3), ("accounts payable", 4), ("accounts receivable", 4), ("financial", 2.5), ("accounting", 3), ("accountant", 3.5),
        ("fp&a", 3.5), ("treasury", 3.5), ("tax", 3), ("payroll", 3.5), ("controller", 3),
        ("equity", 2), ("billing", 2.5), ("human resources", 3.5), ("hr", 3),
        ("people", 2), ("people technology", 3), ("people partner", 3.5),
        ("recruiter", 4), ("recruiting", 3.5), ("talent acquisition", 4), ("sourcer", 4),
        ("benefits", 2.5), ("compensation", 3), ("workplace", 3), ("facilities", 3),
        ("office manager", 3.5), ("executive assistant", 4), ("assistant", 2),
        ("administrative", 3), ("admin", 2), ("coordinator", 2), ("it systems", 3), ("it systems engineer", 4),
        ("it support", 3.5), ("it operations", 3.5), ("it service", 3.5), ("it supporter", 4), ("supporter", 2), ("helpdesk", 3.5), ("help desk", 3.5), ("it assistant", 3.5),
        ("it manager", 3), ("client platform", 2.5), ("corporate it", 3.5),
        ("audio visual", 3), ("av engineer", 3), ("av production", 3), ("immigration", 3), ("investor relations", 4), ("ir", 2.5), ("hrbp", 4),
        ("real estate", 3), ("expense", 2.5), ("commission", 2), ("정산", 2.5),
        ("재무", 3.5), ("회계", 3.5), ("세무", 3.5), ("자금", 2), ("인사", 3),
        ("채용담당", 3.5), ("리크루터", 4), ("총무", 3.5), ("경영지원", 4), ("비서", 3.5),
        ("어시스턴트", 2.5), ("헬프데스크", 3.5), ("자산관리", 2.5), ("간호사", 3),
        ("치료사", 3), ("영양사", 3), ("조리사", 3),
    ],
}

# 패턴 컴파일 -----------------------------------------------------------------

_HANGUL = re.compile(r"[가-힣]")


def _compile(term: str) -> re.Pattern:
    if _HANGUL.search(term):
        if term == "인사":  # 인사이트·인사말 오탐 방지
            return re.compile(r"인사(?!이트|말)")
        return re.compile(re.escape(term))
    body = r"[\s\-/]*".join(re.escape(w) for w in term.split())
    return re.compile(r"(?<![a-z0-9])" + body + r"s?(?![a-z0-9])")


_COMPILED: list[tuple[str, re.Pattern, float]] = [
    (role, _compile(term), w) for role, items in RULES.items() for term, w in items
]
_PRIORITY_INDEX = {r: i for i, r in enumerate(ROLE_PRIORITY)}

# ─── 정규화 / 분절 ────────────────────────────────────────────────────────────

# 직함 앞의 [NAVER] [삼성전자 DS부문] 같은 소속 표기, (경력)/(계약)/(~10/11) 같은 메타
_BRACKET_PREFIX = re.compile(r"^\s*(\[[^\]]*\]\s*)+")
_META_PAREN = re.compile(
    r"\((?:[^)]*?(?:경력|신입|계약|정규|인턴|체험형|채용|~|\d+/\d+|년\s*(?:이상|이하))[^)]*)\)"
)
_SEPARATORS = re.compile(r"\s*(?:,|\s[-–—|]\s|\||/\s|:\s)\s*")
# head가 이것뿐이면 직무를 말해주지 않는 조각 → 다음 조각을 head로 승격
_GENERIC_HEAD = re.compile(
    r"^(?:(?:senior|sr\.?|staff|principal|lead|head|director|manager|vp|chief|global|"
    r"regional|associate|junior|jr\.?|of|the|and|&|team|group|\d+\+?|\+)\s*)+$"
)


def _has_strong_cue(text: str) -> bool:
    return any(w >= 2 and pat.search(text) for _, pat, w in _COMPILED)


def normalize_title(title: str) -> str:
    """분류용 정규화: NFKC → 소문자 → 소속 접두어/메타 괄호 제거 → 공백 정리."""
    t = unicodedata.normalize("NFKC", title or "")
    t = _BRACKET_PREFIX.sub("", t)
    t = _META_PAREN.sub(" ", t)
    t = t.replace("·", " ").replace("ㆍ", " ")
    return re.sub(r"\s+", " ", t).strip().lower()


def split_head(norm: str) -> tuple[str, str]:
    parts = [p for p in _SEPARATORS.split(norm) if p]
    if not parts:
        return "", ""
    i = 0
    # 일반어뿐이거나("Senior Manager") 직무 단서가 약한 조각("Training: ...")은 건너뛴다
    while i < len(parts) - 1 and (_GENERIC_HEAD.match(parts[i]) or not _has_strong_cue(parts[i])):
        i += 1
    if i == len(parts) - 1 and not _has_strong_cue(parts[i]):
        i = 0 if not _GENERIC_HEAD.match(parts[0]) else i
    head = parts[i]
    rest = " , ".join(parts[:i] + parts[i + 1:])
    return head, rest


# 나머지 조각에 있어도 직무를 거의 결정하는 도메인 ("Software Engineer, Robotics")
_DOMAIN_REST_FACTOR = {"로보틱스 / 자율주행": 0.8}
HEAD_END_BONUS = 0.5


def _match_scores(text: str, factor: float, acc: dict[str, list[float]],
                  head: bool = False, rest: bool = False) -> None:
    if not text:
        return
    for role, pat, w in _COMPILED:
        m = pat.search(text)
        if not m:
            continue
        f = _DOMAIN_REST_FACTOR.get(role, factor) if rest else factor
        score = w * f
        # 영문 직함은 맨 끝 명사가 직무다 ("Compliance Program Manager" → 매니저 쪽)
        if head and m.end() == len(text) and not _HANGUL.search(m.group()):
            score += HEAD_END_BONUS
        acc.setdefault(role, []).append(score)


def rule_scores(title: str, department: str = "", tags: tuple[str, ...] = ()) -> dict[str, float]:
    head, rest = split_head(normalize_title(title))
    hits: dict[str, list[float]] = {}
    _match_scores(head, 1.0, hits, head=True)
    _match_scores(rest, 0.5, hits, rest=True)
    _match_scores(normalize_title(department), 0.6, hits)
    _match_scores(normalize_title(" , ".join(tags)), 0.4, hits)
    scores = {}
    for role, ws in hits.items():
        ws.sort(reverse=True)
        scores[role] = ws[0] + 0.3 * sum(ws[1:])
    return scores


def _best(scores: dict[str, float]) -> Optional[tuple[str, float]]:
    if not scores:
        return None
    role = max(scores, key=lambda r: (round(scores[r], 6), -_PRIORITY_INDEX[r]))
    return role, scores[role]


# ─── 2단계: 임베딩 kNN 폴백 ────────────────────────────────────────────────────

EXEMPLARS: dict[str, list[str]] = {
    "AI / ML": ["Research Scientist, Language Models", "Machine Learning Engineer",
                "AI 모델 연구원", "LLM 학습 엔지니어", "Researcher, Pretraining"],
    "소프트웨어 개발": ["Backend Software Engineer", "Frontend Developer", "Site Reliability Engineer",
                   "서버 개발자", "iOS 앱 개발자"],
    "데이터": ["Data Analyst", "Data Engineer", "데이터 분석가", "Analytics Engineer"],
    "하드웨어 / 반도체": ["ASIC Design Engineer", "Hardware Engineer", "반도체 회로 설계",
                    "Data Center Electrical Engineer", "Firmware Engineer"],
    "로보틱스 / 자율주행": ["Robotics Software Engineer", "Autonomous Driving Perception Engineer",
                     "로봇 제어 엔지니어", "자율주행 연구원"],
    "제조 / 품질": ["Manufacturing Engineer", "Quality Engineer", "Test Technician", "생산기술 엔지니어"],
    "보안": ["Security Engineer", "정보보안 담당자", "Detection and Response Engineer"],
    "제품 / 기획": ["Product Manager", "서비스 기획자", "Technical Program Manager"],
    "디자인": ["Product Designer", "UX 디자이너", "Brand Designer"],
    "영업 / 사업개발": ["Account Executive", "Business Development Manager", "B2B 영업 담당자",
                   "Partnerships Lead"],
    "솔루션 / 고객지원": ["Solutions Architect", "Customer Support Specialist", "고객 상담",
                     "Technical Support Engineer"],
    "마케팅 / PR": ["Marketing Manager", "퍼포먼스 마케터", "Communications Lead", "홍보 담당"],
    "운영 / 전략": ["Business Operations Manager", "Strategy and Operations Lead", "서비스 운영 담당자",
                "Supply Chain Manager"],
    "리스크 / 컴플라이언스": ["Compliance Officer", "AML 담당자", "Fraud Risk Analyst", "내부감사"],
    "법무 / 정책": ["Legal Counsel", "Public Policy Manager", "법무 담당 변호사"],
    "경영지원": ["Financial Analyst", "Recruiter", "인사 담당자", "회계 담당", "Executive Assistant"],
}

MIN_RULE_SCORE = 1.5   # 이 미만이면 임베딩 폴백 시도
FALLBACK_RULE_SCORE = 1.0  # 임베딩이 판단 못 하면 이 이상인 규칙 결과는 그대로 채택
EMB_THRESHOLD = 0.55
EMB_MARGIN = 0.03


class _Embedder:
    """프로세스당 모델을 한 번만 로드. 미설치 시 조용히 비활성화."""

    def __init__(self):
        self._loaded = False
        self.model = None
        self.roles: list[str] = []
        self.matrix = None

    def load(self):
        if self._loaded:
            return self.model is not None
        self._loaded = True
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError:
            return False
        print("  ℹ️  직무 분류 임베딩 모델 로딩 중... (최초 1회, 이후 캐시 사용)")
        self.model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
        texts = []
        for role, ex in EXEMPLARS.items():
            self.roles += [role] * len(ex)
            texts += ex
        self.matrix = self.model.encode(texts, normalize_embeddings=True)
        return True

    def classify(self, text: str) -> Optional[tuple[str, float]]:
        if not text or not self.load():
            return None
        emb = self.model.encode([text], normalize_embeddings=True)[0]
        sims = self.matrix @ emb
        best: dict[str, float] = {}
        for role, s in zip(self.roles, sims):
            best[role] = max(best.get(role, -1.0), float(s))
        ranked = sorted(best.items(), key=lambda kv: kv[1], reverse=True)
        (r1, s1), (_, s2) = ranked[0], ranked[1]
        if s1 >= EMB_THRESHOLD and s1 - s2 >= EMB_MARGIN:
            return r1, s1
        return None


_embedder = _Embedder()


# ─── 공개 API ─────────────────────────────────────────────────────────────────

class Classification(NamedTuple):
    role: str
    group: str
    method: str   # "rule" | "embedding" | "weak-rule" | "none"
    score: float


@lru_cache(maxsize=8192)
def _classify_cached(title: str, department: str, tags: tuple[str, ...],
                     use_embedding: bool) -> Classification:
    best = _best(rule_scores(title, department, tags))
    if best and best[1] >= MIN_RULE_SCORE:
        return Classification(best[0], ROLE_TO_GROUP[best[0]], "rule", round(best[1], 2))
    if use_embedding:
        emb = _embedder.classify(normalize_title(title))
        if emb:
            return Classification(emb[0], ROLE_TO_GROUP[emb[0]], "embedding", round(emb[1], 3))
    if best and best[1] >= FALLBACK_RULE_SCORE:
        return Classification(best[0], ROLE_TO_GROUP[best[0]], "weak-rule", round(best[1], 2))
    return Classification(OTHER, OTHER, "none", 0.0)


EMBEDDING_ENABLED = os.environ.get("JOB_RADAR_EMBEDDING") == "1"


def classify(title: str, department: str = "", tags=(), use_embedding: Optional[bool] = None) -> Classification:
    if use_embedding is None:
        use_embedding = EMBEDDING_ENABLED
    return _classify_cached(title or "", department or "", tuple(tags or ()), use_embedding)


def classify_role(title: str, department: str = "", tags=()) -> str:
    """직함(+부서·태그)을 받아 직무명 하나를 반환."""
    return classify(title, department, tags).role


def _keyword_classify(title: str) -> Optional[str]:
    """규칙 단계만 실행 (임베딩 없이). 확신이 낮으면 None."""
    c = classify(title, use_embedding=False)
    return c.role if c.method == "rule" else None


# ─── 평가 CLI ────────────────────────────────────────────────────────────────

def evaluate(gold_path: str, use_embedding: bool = False, verbose: bool = True) -> float:
    rows = []
    with open(gold_path, encoding="utf-8") as f:
        for line in f:
            if not line.strip() or line.startswith("#"):
                continue
            title, dept, expected = (line.rstrip("\n").split("\t") + ["", ""])[:3]
            rows.append((title, dept, expected))
    wrong = []
    for title, dept, expected in rows:
        c = classify(title, dept, use_embedding=use_embedding)
        if c.role != expected:
            wrong.append((title, dept, expected, c))
    acc = 1 - len(wrong) / len(rows)
    if verbose:
        for title, dept, expected, c in wrong:
            print(f"  ✗ {title!r} [{dept}] → {c.role} ({c.method} {c.score}), 정답 {expected}")
        print(f"정확도 {acc:.1%} ({len(rows) - len(wrong)}/{len(rows)})")
    return acc


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")
    if "--eval" in sys.argv:
        evaluate("tests/data/role_gold.tsv", use_embedding="--emb" in sys.argv)
    else:
        for t in sys.argv[1:]:
            print(t, "→", classify(t))
