"""정적 사이트(docs/) 배포 안전장치 — 브라우저 캐시 때문에 화면이 깨지지 않게"""
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INDEX = (ROOT / "docs" / "index.html").read_text(encoding="utf-8")


def test_asset_versions_are_current():
    # CSS·JS를 고친 뒤 scripts/stamp_assets.py 를 안 돌리면, 배포 직후 브라우저가
    # 새 index.html 과 캐시된 옛 JS 를 섞어 실행할 수 있다 (2026-10-10 화면이 비었던 원인)
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "stamp_assets.py"), "--check"],
                       capture_output=True, text=True, encoding="utf-8")
    assert r.returncode == 0, r.stdout


def test_every_asset_is_versioned():
    for name in ["style.css", "search.js", "app.js"]:
        assert re.search(rf'"{re.escape(name)}\?v=[0-9a-f]{{8}}"', INDEX), name


def test_content_is_not_hidden_in_html():
    # 본문을 HTML에서 숨겨 두고 JS가 여는 구조면, JS 버전이 어긋나는 순간 화면이 통째로 빈다.
    # 숨기는 건 로딩 실패 때 JS가 직접 한다.
    main_tag = re.search(r"<main[^>]*>", INDEX).group(0)
    assert "hidden" not in main_tag
