"""
BaseCrawler 유틸리티 메서드 단위 테스트
- format_job: 반환 구조, 필드 검증
- is_expired: 날짜 경계 조건
"""
import pytest
from datetime import date, timedelta
from crawlers.base import BaseCrawler


class _Dummy(BaseCrawler):
    """테스트용 최소 구현체"""
    def fetch_jobs(self):
        return []


REQUIRED_FIELDS = {"company", "category", "role", "title", "url",
                   "location", "department", "posted_date", "description",
                   "crawled_at"}


class TestFormatJob:
    def setup_method(self):
        self.crawler = _Dummy("TestCo", "개발", "서울")

    def test_required_fields_present(self):
        job = self.crawler.format_job("Software Engineer", "https://example.com")
        assert REQUIRED_FIELDS.issubset(job.keys())

    def test_basic_values(self):
        job = self.crawler.format_job("Software Engineer", "https://example.com/job")
        assert job["company"] == "TestCo"
        assert job["title"] == "Software Engineer"
        assert job["url"] == "https://example.com/job"
        assert job["category"] == "개발"

    def test_default_location_used(self):
        job = self.crawler.format_job("Engineer", "https://example.com")
        assert job["location"] == "서울"

    def test_override_location(self):
        job = self.crawler.format_job("Engineer", "https://example.com", location="부산")
        assert job["location"] == "부산"

    def test_role_classified(self):
        job = self.crawler.format_job("Machine Learning Engineer", "https://example.com")
        assert job["role"] == "AI / ML"

    def test_dev_role_classified(self):
        job = self.crawler.format_job("Software Engineer", "https://example.com")
        assert job["role"] == "개발"

    def test_optional_fields(self):
        job = self.crawler.format_job(
            "PM", "https://example.com",
            department="Product", posted_date="2025-01-01"
        )
        assert job["department"] == "Product"
        assert job["posted_date"] == "2025-01-01"

    def test_crawled_at_is_string(self):
        job = self.crawler.format_job("Engineer", "https://example.com")
        assert isinstance(job["crawled_at"], str)
        assert len(job["crawled_at"]) > 0


class TestIsExpired:
    def setup_method(self):
        self.crawler = _Dummy("TestCo", "개발")

    def test_yesterday_is_expired(self):
        yesterday = (date.today() - timedelta(days=1)).strftime("%Y%m%d")
        assert self.crawler.is_expired(yesterday) is True

    def test_tomorrow_is_not_expired(self):
        tomorrow = (date.today() + timedelta(days=1)).strftime("%Y%m%d")
        assert self.crawler.is_expired(tomorrow) is False

    def test_today_is_not_expired(self):
        today = date.today().strftime("%Y%m%d")
        assert self.crawler.is_expired(today) is False

    def test_invalid_string_returns_false(self):
        assert self.crawler.is_expired("invalid") is False

    def test_empty_string_returns_false(self):
        assert self.crawler.is_expired("") is False

    def test_none_returns_false(self):
        assert self.crawler.is_expired(None) is False

    def test_far_past_is_expired(self):
        assert self.crawler.is_expired("20200101") is True

    def test_far_future_is_not_expired(self):
        assert self.crawler.is_expired("20991231") is False
