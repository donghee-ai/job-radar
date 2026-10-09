"""
classifier.py 단위 테스트
- 규칙 단계 정확도 (평가셋 기준선)
- 이전 버전에서 실제로 틀렸던 경계 사례
- 정규화·분절 헬퍼
"""
import pytest
from crawlers.classifier import (
    ROLE_GROUPS, ROLE_TO_GROUP, OTHER, classify, classify_role, evaluate,
    normalize_title, split_head, _keyword_classify,
)


class TestBaseline:
    def test_gold_set_accuracy(self):
        # 규칙을 다듬으며 쓴 평가셋 — 회귀 방지용 (떨어지면 어떤 규칙이 다른 걸 깼다는 뜻)
        assert evaluate("tests/data/role_gold.tsv", verbose=False) >= 0.97

    def test_holdout_accuracy(self):
        # 튜닝에 쓰지 않은 무작위 표본 — 일반화 성능의 하한선
        assert evaluate("tests/data/role_holdout.tsv", verbose=False) >= 0.85


class TestEdgeCases:
    """이전 키워드 우선순위 방식에서 실제로 틀렸던 직함들"""

    @pytest.mark.parametrize("title,expected", [
        ("Data Center Mechanical Engineer", "하드웨어 / 반도체"),        # 이전: 제품 / 기획
        ("People Technology Analyst, Workday PATT & Benefits", "경영지원"),  # 이전: 마케팅
        ("IT Software Architect, SaaS Enablement", "소프트웨어 개발"),      # 이전: enablement → 영업
        ("Studio Scenarios Writer", OTHER),                            # 이전: 'ios ' 부분일치로 개발
        ("Revenue Accountant", "경영지원"),                              # 이전: revenue → 영업
        ("Commercial Counsel", "법무 / 정책"),                           # 이전: commercial → 영업
        ("Product Marketing Manager", "마케팅 / PR"),
        ("Engineering Manager, Growth", "소프트웨어 개발"),
        ("Senior Manager, EHS - Robotics", "운영 / 전략"),               # 일반어 head 승격
        ("Control Systems Software Engineer, Robotics", "로보틱스 / 자율주행"),  # 도메인어
        ("인사이트 리서처", OTHER),                                       # '인사' 오탐 방지
    ])
    def test_case(self, title, expected):
        assert classify_role(title) == expected

    def test_department_used_when_title_is_vague(self):
        # 직함만으로는 약한 단서뿐일 때 부서가 직무를 정한다
        assert classify_role("Analyst") == OTHER
        assert classify_role("Analyst", department="Finance") == "경영지원"


class TestHelpers:
    def test_normalize_strips_prefix_and_meta(self):
        assert normalize_title("[NAVER] 해외 변호사(외국법자문사) (경력)") == "해외 변호사(외국법자문사)"

    def test_normalize_nfkc_and_lower(self):
        assert normalize_title("ＭＬ Engineer") == "ml engineer"

    def test_split_head_basic(self):
        assert split_head("software engineer, research") == ("software engineer", "research")

    def test_split_head_promotes_generic(self):
        head, _ = split_head("senior manager, ehs - robotics")
        assert head == "ehs"

    def test_every_role_has_group(self):
        for roles in ROLE_GROUPS.values():
            for r in roles:
                assert ROLE_TO_GROUP[r]


class TestPublicApi:
    def test_returns_known_role(self):
        known = set(ROLE_TO_GROUP)
        for t in ["Software Engineer", "Account Executive", "xyz"]:
            assert classify_role(t) in known

    def test_classification_fields(self):
        c = classify("Machine Learning Engineer")
        assert c.role == "AI / ML" and c.group == "엔지니어링" and c.method == "rule"

    def test_unknown_is_other(self):
        assert classify_role("Completely Unknown Role XYZ123") == OTHER

    def test_keyword_stage_none_when_unsure(self):
        assert _keyword_classify("Completely Unknown Role XYZ123") is None

    def test_case_insensitive(self):
        assert classify_role("MACHINE LEARNING ENGINEER") == classify_role("machine learning engineer")
