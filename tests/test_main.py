"""
main.py 유틸리티 함수 단위 테스트
- load_existing: 파일 없음 / 손상된 JSON / 정상
- load_config: config.json 구조 검증
- get_all_crawlers: 등록된 크롤러 목록 검증
"""
import json
import pytest
from pathlib import Path


class TestLoadExisting:
    def test_missing_file_returns_empty(self):
        from main import load_existing
        result = load_existing(Path("__nonexistent_xyz__.json"))
        assert result == {"jobs": [], "results": {}}

    def test_corrupt_json_returns_empty(self, tmp_path):
        from main import load_existing
        f = tmp_path / "corrupt.json"
        f.write_text("{ not valid json !!!", encoding="utf-8")
        result = load_existing(f)
        assert result == {"jobs": [], "results": {}}

    def test_valid_file_loaded(self, tmp_path):
        from main import load_existing
        data = {
            "jobs": [{"company": "TestCo", "title": "Engineer"}],
            "results": {"TestCo": 1}
        }
        f = tmp_path / "valid.json"
        f.write_text(json.dumps(data), encoding="utf-8")
        result = load_existing(f)
        assert len(result["jobs"]) == 1
        assert result["jobs"][0]["company"] == "TestCo"
        assert result["results"]["TestCo"] == 1

    def test_empty_json_object(self, tmp_path):
        from main import load_existing
        f = tmp_path / "empty.json"
        f.write_text("{}", encoding="utf-8")
        result = load_existing(f)
        assert result.get("jobs", []) == []
        assert result.get("results", {}) == {}


class TestLoadConfig:
    def test_config_has_crawlers_key(self):
        from main import load_config
        config = load_config()
        assert "crawlers" in config

    def test_crawlers_is_dict(self):
        from main import load_config
        config = load_config()
        assert isinstance(config["crawlers"], dict)

    def test_known_crawlers_present(self):
        from main import load_config
        config = load_config()
        expected = {"NVIDIA", "Google", "Anthropic", "OpenAI", "Samsung", "Naver", "Toss", "Upstage"}
        assert expected.issubset(set(config["crawlers"].keys()))


class TestGetAllCrawlers:
    def test_all_keys_present(self):
        from crawlers import get_all_crawlers
        crawlers = get_all_crawlers()
        expected = {"NVIDIA", "Google", "Samsung", "Naver", "Toss", "Anthropic", "OpenAI", "Upstage"}
        assert set(crawlers.keys()) == expected

    def test_each_crawler_has_company(self):
        from crawlers import get_all_crawlers
        for name, crawler in get_all_crawlers().items():
            assert hasattr(crawler, "company"), f"{name} crawler에 company 속성 없음"
            assert crawler.company, f"{name} crawler의 company가 비어 있음"

    def test_each_crawler_has_fetch_jobs(self):
        from crawlers import get_all_crawlers
        for name, crawler in get_all_crawlers().items():
            assert callable(getattr(crawler, "fetch_jobs", None)), \
                f"{name} crawler에 fetch_jobs 메서드 없음"
