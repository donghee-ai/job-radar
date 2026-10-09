"""enrich.py 단위 테스트 — 연차·고용형태·지역 추출, first_seen 이어받기"""
import pytest
from crawlers.enrich import seniority, employment, regions, enrich_jobs, is_pool


class TestSeniority:
    @pytest.mark.parametrize("title,tags,expected", [
        ("Full-Stack Product Engineer Internship (체험형)", [], "인턴"),
        ("iOS 앱 개발자 (신입)", [], "신입/주니어"),
        ("Staff+ Software Engineer, Platform", [], "시니어"),
        ("Senior Engineering Manager, Capacity", [], "리더"),
        ("Head of Partnerships, Japan", [], "리더"),
        ("[NAVER] AI 에이전트 엔지니어 (경력)", [], "경력"),
        ("Account Strategist, Mid-Market Sales", ["Early"], "신입/주니어"),  # Mid-Market ≠ Mid 레벨
        ("Platform Software Engineer", ["Tech", "경력 7년 이상"], "시니어"),
        ("Software Engineer", [], ""),
    ])
    def test_levels(self, title, tags, expected):
        assert seniority(title, tags) == expected


class TestEmployment:
    def test_contract(self):
        assert employment("Account Strategist (Fixed-Term Contract)") == "계약직"
        assert employment("[NAVER] 운영 담당자 (계약)") == "계약직"

    def test_default_empty(self):
        assert employment("Software Engineer") == ""


class TestPool:
    def test_pool_titles(self):
        assert is_pool("토스페이먼츠 신사업 초기멤버 인재풀 등록")
        assert is_pool("[Expression of Interest] Research Manager, Interpretability")
        assert not is_pool("Pool Maintenance Engineer")


class TestRegions:
    @pytest.mark.parametrize("loc,expected", [
        ("Seoul, South Korea", ["한국"]),
        ("San Francisco, CA | New York City, NY", ["북미"]),
        ("US - Remote", ["북미", "원격"]),
        ("London, UK; Ontario, CAN", ["북미", "유럽"]),
        ("Tokyo, Japan", ["아시아·태평양"]),
        ("São Paulo", ["기타"]),
        ("", []),
    ])
    def test_regions(self, loc, expected):
        assert regions(loc) == expected


class TestEnrichJobs:
    def _job(self, url, title="Software Engineer"):
        return {"company": "X", "title": title, "url": url, "location": "Seoul", "department": ""}

    def test_first_seen_carried_over(self):
        prev = [{"company": "X", "url": "a", "first_seen": "2026-09-01"}]
        out = enrich_jobs([self._job("a"), self._job("b")], prev, "2026-10-10")
        assert [j["first_seen"] for j in out] == ["2026-09-01", "2026-10-10"]

    def test_legacy_job_not_marked_new(self):
        # 추적 도입 전 데이터(first_seen 없음)는 오늘 신규로 보지 않는다
        out = enrich_jobs([self._job("a")], [{"url": "a"}], "2026-10-10")
        assert out[0]["first_seen"] == ""

    def test_newly_tracked_company_is_baseline(self):
        prev = [{"company": "Old", "url": "o", "first_seen": "2026-09-01"}]
        job = {**self._job("n"), "company": "NewCo"}
        out = enrich_jobs([job], prev, "2026-10-10")
        assert out[0]["first_seen"] == ""

    def test_duplicate_urls_removed(self):
        out = enrich_jobs([self._job("a"), self._job("a")], [], "2026-10-10")
        assert len(out) == 1

    def test_fields_added(self):
        j = enrich_jobs([self._job("a", "Senior Data Engineer")], [], "2026-10-10")[0]
        assert j["role"] == "데이터" and j["role_group"] == "엔지니어링"
        assert j["seniority"] == "시니어" and j["regions"] == ["한국"]
