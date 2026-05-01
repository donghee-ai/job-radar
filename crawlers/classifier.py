"""
직무 분류 모듈 (2단계 하이브리드)

[1단계] 키워드 매칭
  - 빠르고, 도메인 특화 약어(AML, KYC, SRE 등)에 강함
  - 체크 순서가 우선순위 역할:
      AI/ML → 보안 → 영업/사업개발 → 마케팅 → 제품/기획 → 운영/경영지원 → 개발
    이유: 뒤에 오는 카테고리의 키워드가 앞 카테고리를 먹지 않도록
    예) "Security Engineer" → 보안이 개발보다 먼저 체크되어 보안으로 분류
        "ML Engineer"       → AI/ML이 개발보다 먼저 체크되어 AI/ML로 분류

[2단계] 트랜스포머 임베딩 유사도
  - 키워드에 없는 모호한 직무 처리
  - 모델: paraphrase-multilingual-MiniLM-L12-v2 (~420MB)
    · 한국어 + 영어 동시 지원
    · CPU 추론 가능 (1,400건 기준 약 2초)
    · 최초 실행 시 자동 다운로드, 이후 캐시 사용
  - 카테고리별 앵커 문장과 코사인 유사도 비교
  - 유사도 THRESHOLD(0.28) 미만이면 기타로 분류

[기타]
  - sentence-transformers 미설치 시 키워드 미분류 건은 모두 기타
  - 분류 결과는 jobs.json의 role 필드에 저장
"""

from __future__ import annotations
from typing import Optional

# ─── 1단계: 키워드 맵 ─────────────────────────────────────────────────────────
# 리스트 순서 = 우선순위. 위에 있을수록 먼저 체크.

KEYWORD_MAP: list[tuple[str, list[str]]] = [
    ("AI / ML", [
        "research scientist", "research engineer", "ai researcher",
        "machine learning", "deep learning", "reinforcement learning",
        "ml engineer", "ai engineer", "llm", "nlp", "natural language",
        "computer vision", "neural", "prompt engineer",
        "ai safety", "ai alignment",
        "panoptic", "segmentation", "3d mesh", "foundation model",
        "data scientist",
        "pre-training", "post-training", "fine-tuning",
        "ai research", "lm eval", "lm research",
        "fellows program", "stem fellow", "ai fellow",
        "인공지능", "머신러닝", "딥러닝",
    ]),
    ("보안", [
        # 직함
        "security engineer", "security architect", "security analyst",
        "security manager", "security lead", "security specialist",
        "security regional", "physical security",
        "network security", "cloud security", "data center security",
        "soc architect", "soc ",
        "resilience operations", "sox",
        # 금융 컴플라이언스
        "aml", "anti-money laundering", "compliance",
        "kyc", " str ", "fraud", "risk management",
        "audit",
        # 한국어
        "보안", "자금세탁", "내부통제", "컴플라이언스", "감사",
    ]),
    ("영업 / 사업개발", [
        "account executive", "account manager", "account director",
        "sales", "business development", "biz dev",
        "partner sales", "partner manager", "partnerships",
        "growth manager", "growth account",
        "channel manager", "revenue", "commercial",
        "customer success",
        "gtm", "go-to-market",
        "evangelist", "forward deployed",
        "enablement", "expansions lead", "international readiness",
        # 한국어
        "영업", "사업개발", "가맹점", "세일즈", "파트너십",
    ]),
    ("마케팅", [
        "marketing", "public relations", "pr manager",
        "communications manager", "brand manager",
        "content manager", "campaign", "performance marketer",
        "media effectiveness",
        # 한국어
        "마케팅", "홍보", "퍼포먼스 마케", "마케터",
    ]),
    ("제품 / 기획", [
        "product manager", "product owner", "product lead",
        "program manager", "technical program manager",
        "designer", "ux ", "ui ", "product design", "design lead",
        "scrum master", "pmo",
        # 한국어
        "기획", "디자인",
    ]),
    ("운영 / 경영지원", [
        "operations manager", "operations specialist",
        "research operations",
        "finance", "accounting", "financial",
        "human resources", "recruiter", "talent acquisition",
        "legal", "counsel", "administrative", "assistant",
        "immigration", "coordinator",
        "supply chain", "logistics", "sourcing", "procurement",
        "strategy and ops", "it manager",
        "customer education",
        "통번역", "번역",
        # 한국어
        "운영", "경영지원", "회계", "재무", "인사", "법무",
        "총무", "물류", "어시스턴트", "치료사",
    ]),
    ("개발", [
        # 직함
        "software engineer", "backend", "frontend",
        "full-stack", "fullstack", "full stack",
        "mobile developer", "ios ", "android",
        "devops", "site reliability", "sre ",
        "platform engineer", "infrastructure engineer",
        "systems engineer", "system software",
        "cloud engineer", "network engineer",
        "firmware", "embedded",
        "data engineer",
        "aiops", "mlops",
        "kernel engineer", "tpu ", "gpu ",
        "engineering manager",
        "developer relations",
        # 한국어
        "개발자", "엔지니어",
    ]),
]

# ─── 2단계: 트랜스포머 앵커 문장 ──────────────────────────────────────────────
# 각 카테고리를 대표하는 한국어+영어 혼합 문장.
# 직무명 임베딩과 코사인 유사도를 비교해 가장 가까운 카테고리를 선택.

ANCHORS: dict[str, str] = {
    "개발":           "software engineering backend frontend infrastructure cloud devops platform 소프트웨어 개발 엔지니어링 인프라 시스템",
    "AI / ML":        "machine learning deep learning AI research neural network LLM NLP computer vision 인공지능 머신러닝 딥러닝 AI 연구 데이터사이언스",
    "보안":           "security compliance AML anti-money laundering KYC fraud risk audit 보안 자금세탁방지 컴플라이언스 리스크 내부통제",
    "영업 / 사업개발": "sales account management business development partnerships revenue GTM 영업 사업개발 파트너십 세일즈 고객",
    "마케팅":         "marketing public relations communications brand content campaign performance 마케팅 홍보 브랜드 콘텐츠 퍼포먼스",
    "제품 / 기획":    "product manager program manager design UX UI planning 제품 기획 디자인 프로그램 매니저",
    "운영 / 경영지원": "operations finance accounting HR legal administrative assistant supply chain 운영 경영지원 재무 인사 법무 총무",
}

# 이 값 미만의 유사도는 기타로 분류
THRESHOLD = 0.28


# ─── 1단계 함수 ────────────────────────────────────────────────────────────────

def _keyword_classify(title: str) -> Optional[str]:
    t = title.lower()
    for category, keywords in KEYWORD_MAP:
        for kw in keywords:
            if kw in t:
                return category
    return None


# ─── 2단계 싱글톤 클래스 ────────────────────────────────────────────────────────

class _JobClassifier:
    """프로세스당 모델을 한 번만 로드하는 싱글톤."""

    def __init__(self):
        self._model = None
        self._anchor_embeddings = None
        self._categories: list[str] = []
        self._loaded = False

    def _load(self):
        if self._loaded:
            return
        self._loaded = True
        try:
            from sentence_transformers import SentenceTransformer
            print("  ℹ️  직무 분류 모델 로딩 중... (최초 1회, 이후 캐시 사용)")
            self._model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")
            self._categories = list(ANCHORS.keys())
            self._anchor_embeddings = self._model.encode(
                list(ANCHORS.values()), normalize_embeddings=True
            )
        except ImportError:
            # sentence-transformers 미설치 시 조용히 비활성화
            self._model = None

    def classify(self, title: str) -> str:
        # 1단계: 키워드
        result = _keyword_classify(title)
        if result:
            return result

        # 2단계: 트랜스포머
        self._load()
        if self._model is None:
            return "기타"

        try:
            import numpy as np
            emb = self._model.encode([title], normalize_embeddings=True)[0]
            sims = self._anchor_embeddings @ emb
            best_idx = int(np.argmax(sims))
            if float(sims[best_idx]) >= THRESHOLD:
                return self._categories[best_idx]
        except Exception:
            pass

        return "기타"


_classifier = _JobClassifier()


def classify_role(title: str) -> str:
    """직무명을 받아 7개 분류 중 하나(또는 '기타')를 반환."""
    return _classifier.classify(title)
