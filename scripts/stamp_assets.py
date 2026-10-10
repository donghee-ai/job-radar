"""
docs/index.html 이 부르는 CSS·JS 주소에 내용 해시를 붙인다 (style.css?v=1a2b3c4d).

GitHub Pages는 파일을 10분간 캐시한다(max-age=600). 주소가 그대로면 배포 직후
브라우저가 새 index.html 과 캐시된 옛 app.js 를 섞어 실행해 화면이 깨질 수 있다
(2026-10-10 실제 발생: 공고 영역이 통째로 안 보임). 내용이 바뀌면 주소도 바뀌게 해서 막는다.

사용법:  python scripts/stamp_assets.py        # index.html 갱신
         python scripts/stamp_assets.py --check  # 갱신이 필요하면 종료 코드 1 (테스트가 사용)
"""
import hashlib
import re
import sys
from pathlib import Path

DOCS = Path(__file__).resolve().parent.parent / "docs"
ASSETS = ["style.css", "search.js", "app.js"]


def stamped_html() -> str:
    html = (DOCS / "index.html").read_text(encoding="utf-8")
    for name in ASSETS:
        digest = hashlib.sha1((DOCS / name).read_bytes()).hexdigest()[:8]
        # href="style.css" / src="app.js" (기존 ?v= 가 있으면 교체)
        pattern = re.compile(rf'((?:href|src)="){re.escape(name)}(?:\?v=[0-9a-f]+)?(")')
        html, n = pattern.subn(rf"\g<1>{name}?v={digest}\g<2>", html)
        if n != 1:
            raise SystemExit(f"index.html 에서 {name} 참조를 하나만 찾아야 하는데 {n}개 찾음")
    return html


def main() -> int:
    current = (DOCS / "index.html").read_text(encoding="utf-8")
    new = stamped_html()
    if "--check" in sys.argv:
        if new != current:
            print("docs/index.html 의 자산 버전이 오래됨 — python scripts/stamp_assets.py 를 실행하세요")
            return 1
        return 0
    if new != current:
        (DOCS / "index.html").write_text(new, encoding="utf-8", newline="\n")
        print("docs/index.html 자산 버전 갱신")
    else:
        print("이미 최신")
    return 0


if __name__ == "__main__":
    sys.exit(main())
