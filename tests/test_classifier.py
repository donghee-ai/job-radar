"""
classifier.py 단위 테스트
- 1단계 키워드 분류 정확도
- 우선순위 충돌 (ML vs 개발, 보안 vs 개발)
- classify_role 공개 API
"""
import pytest
from crawlers.classifier import _keyword_classify, classify_role


class TestKeywordClassify:
    def test_aiml_machine_learning(self):
        assert _keyword_classify("Machine Learning Engineer") == "AI / ML"

    def test_aiml_llm(self):
        assert _keyword_classify("LLM Researcher") == "AI / ML"

    def test_aiml_data_scientist(self):
        assert _keyword_classify("Data Scientist") == "AI / ML"

    def test_security_engineer(self):
        assert _keyword_classify("Security Engineer") == "보안"

    def test_security_aml(self):
        assert _keyword_classify("AML Compliance Analyst") == "보안"

    def test_sales_account(self):
        assert _keyword_classify("Account Executive") == "영업 / 사업개발"

    def test_sales_biz_dev(self):
        assert _keyword_classify("Business Development Manager") == "영업 / 사업개발"

    def test_dev_software_engineer(self):
        assert _keyword_classify("Software Engineer") == "개발"

    def test_dev_backend(self):
        assert _keyword_classify("Backend Developer") == "개발"

    def test_unknown_returns_none(self):
        assert _keyword_classify("Completely Unknown Role XYZ123") is None

    def test_priority_ml_over_dev(self):
        # "ml engineer"는 AI/ML 키워드가 개발보다 우선
        assert _keyword_classify("ML Engineer") == "AI / ML"

    def test_priority_security_over_dev(self):
        # "security engineer"는 보안이 개발보다 우선
        assert _keyword_classify("Security Engineer") == "보안"

    def test_case_insensitive(self):
        assert _keyword_classify("MACHINE LEARNING ENGINEER") == "AI / ML"
        assert _keyword_classify("software engineer") == "개발"


class TestClassifyRole:
    def test_returns_string(self):
        result = classify_role("Software Engineer")
        assert isinstance(result, str)
        assert len(result) > 0

    def test_known_role(self):
        assert classify_role("Machine Learning Engineer") == "AI / ML"

    def test_empty_string_returns_string(self):
        result = classify_role("")
        assert isinstance(result, str)
