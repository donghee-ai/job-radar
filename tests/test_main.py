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
        assert expected.issubset(set(crawlers.keys()))

    def test_config_and_registry_in_sync(self):
        # config.json에 없는 크롤러는 기본 실행에서 조용히 빠진다 → 둘이 항상 같아야 한다
        from crawlers import get_all_crawlers
        from main import load_config
        assert set(get_all_crawlers()) == set(load_config()["crawlers"])

    def test_every_crawler_has_sector_or_is_general(self):
        from crawlers import get_all_crawlers
        for name, c in get_all_crawlers().items():
            assert isinstance(c.sectors, list), name

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


class TestStaleFallback:
    """크롤이 0건을 내면 이전 공고를 유지하되, 7일 넘게 실패하면 내린다"""

    class _Empty:
        company, category, sectors = "X", "외국계", []

        def fetch_jobs(self):
            return []

    def _run(self, tmp_path, monkeypatch, sources):
        import json
        import main
        out = tmp_path / "jobs.json"
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({"crawlers": {"X": True}}), encoding="utf-8")
        old_job = {"company": "X", "title": "Software Engineer", "url": "u1", "location": "Seoul"}
        out.write_text(json.dumps({"jobs": [old_job], "results": {"X": 1}, "sources": sources}), encoding="utf-8")
        monkeypatch.setattr(main, "OUTPUT_PATH", out)
        monkeypatch.setattr(main, "CONFIG_PATH", cfg)
        monkeypatch.setattr(main, "get_all_crawlers", lambda: {"X": self._Empty()})
        main.run()
        return json.loads(out.read_text(encoding="utf-8"))

    def test_first_failure_keeps_previous(self, tmp_path, monkeypatch):
        data = self._run(tmp_path, monkeypatch, {})
        assert len(data["jobs"]) == 1
        assert data["sources"]["X"]["status"] == "stale"

    def test_long_failure_drops_previous(self, tmp_path, monkeypatch):
        data = self._run(tmp_path, monkeypatch,
                         {"X": {"status": "stale", "stale_since": "2000-01-01", "last_success": "1999-12-31"}})
        assert data["jobs"] == []
        assert data["sources"]["X"]["status"] == "failed"
        assert data["sources"]["X"]["last_success"] == "1999-12-31"


class TestFailureReasons:
    """안 되는 날에는 왜 안 되는지가 데이터·로그·GitHub 화면에 남아야 한다"""

    def _run(self, tmp_path, monkeypatch, crawler, prev_jobs=0, env=None):
        """반환: (jobs.json의 회사 상태, 실패 목록, CI 보고서 본문)"""
        import json
        import main
        out = tmp_path / "jobs.json"
        cfg = tmp_path / "config.json"
        cfg.write_text(json.dumps({"crawlers": {"X": True}}), encoding="utf-8")
        jobs = [{"company": "X", "title": f"Engineer {i}", "url": f"u{i}", "location": "Seoul"} for i in range(prev_jobs)]
        out.write_text(json.dumps({"jobs": jobs, "results": {"X": prev_jobs} if prev_jobs else {}}), encoding="utf-8")
        monkeypatch.setattr(main, "OUTPUT_PATH", out)
        monkeypatch.setattr(main, "CONFIG_PATH", cfg)
        monkeypatch.setattr(main, "get_all_crawlers", lambda: {"X": crawler})
        report = tmp_path / "report.md"
        monkeypatch.setenv("CRAWL_REPORT_PATH", str(report))
        for k, v in (env or {}).items():
            monkeypatch.setenv(k, v)
        degraded = main.run()
        src = json.loads(out.read_text(encoding="utf-8"))["sources"]["X"]
        return src, degraded, report.read_text(encoding="utf-8")

    @staticmethod
    def _crawler(fetch):
        from crawlers.base import BaseCrawler

        class C(BaseCrawler):
            def __init__(self):
                super().__init__("X", "외국계")
                self.sectors = []

            def fetch_jobs(self):
                return fetch(self)
        return C()

    def test_recorded_issue_becomes_error(self, tmp_path, monkeypatch):
        def fetch(c):
            c.warn("요청 실패(3회 시도): HTTP 429 요청 과다(rate limit) — https://x")
            return []
        src, degraded, report = self._run(tmp_path, monkeypatch, self._crawler(fetch))
        assert src["status"] == "failed" and "HTTP 429" in report
        assert degraded == ["X"]

    def test_reason_not_in_public_data(self, tmp_path, monkeypatch):
        # 실패 원인은 운영 로그 — 방문자에게 공개되는 jobs.json에는 남기지 않는다
        def fetch(c):
            c.warn("요청 실패: HTTP 503 — https://internal")
            return []
        src, _, report = self._run(tmp_path, monkeypatch, self._crawler(fetch), prev_jobs=3)
        assert "error" not in src and "503" not in str(src) and "503" in report

    def test_exception_becomes_error(self, tmp_path, monkeypatch):
        def fetch(c):
            raise KeyError("positions")
        src, _, report = self._run(tmp_path, monkeypatch, self._crawler(fetch), prev_jobs=3)
        assert src["status"] == "stale" and "KeyError" in report

    def test_silent_zero_is_named(self, tmp_path, monkeypatch):
        _, _, report = self._run(tmp_path, monkeypatch, self._crawler(lambda c: []), prev_jobs=3)
        assert "오류 없이 0건" in report

    def test_sharp_drop_warns(self, tmp_path, monkeypatch):
        def fetch(c):
            return [c.format_job("Software Engineer", f"n{i}") for i in range(3)]
        src, degraded, report = self._run(tmp_path, monkeypatch, self._crawler(fetch), prev_jobs=20)
        assert src["status"] == "ok" and "급감" in report and degraded == []

    def test_github_annotation_and_summary(self, tmp_path, monkeypatch, capsys):
        summary = tmp_path / "summary.md"

        def fetch(c):
            c.warn("공고 링크가 안 보임 — 받은 페이지: 제목 'Sorry'")
            return []
        self._run(tmp_path, monkeypatch, self._crawler(fetch), prev_jobs=3,
                  env={"GITHUB_ACTIONS": "true", "GITHUB_STEP_SUMMARY": str(summary)})
        out = capsys.readouterr().out
        assert "::error title=X" in out and "Sorry" in out
        assert "| X | ❌ 실패 · 이전 공고 유지 | 3 |" in summary.read_text(encoding="utf-8")

    def test_all_ok_report(self, tmp_path, monkeypatch):
        def fetch(c):
            return [c.format_job("Software Engineer", "u0")]
        src, degraded, report = self._run(tmp_path, monkeypatch, self._crawler(fetch), prev_jobs=1)
        assert degraded == [] and "문제 0곳" in report
