"""
PostToolUse 훅: .py 파일 수정 시 pytest 실행
- 결과를 .claude/test-results.log에 기록
- 실패 시 additionalContext로 Claude에게 피드백 → 자동 재수정 유도
"""
import json
import sys
import subprocess
import os
from datetime import datetime

data = json.load(sys.stdin)
file_path = data.get("tool_input", {}).get("file_path", "")

if not str(file_path).endswith(".py"):
    sys.exit(0)

timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

result = subprocess.run(
    [sys.executable, "-m", "pytest", "tests/", "-v", "--tb=short", "--no-header", "-q"],
    capture_output=True,
    text=True,
    encoding="utf-8",
)

status = "PASS" if result.returncode == 0 else "FAIL"
divider = "=" * 60
log_entry = (
    f"\n{divider}\n"
    f"[{timestamp}] [{status}]\n"
    f"수정 파일: {file_path}\n"
    f"{divider}\n"
    f"{result.stdout}"
    f"{result.stderr}\n"
)

log_path = os.path.join(".claude", "test-results.log")
os.makedirs(".claude", exist_ok=True)
with open(log_path, "a", encoding="utf-8") as f:
    f.write(log_entry)

if result.returncode != 0:
    feedback = (
        "테스트가 실패했습니다. 아래 결과를 보고 코드를 수정하세요.\n\n"
        f"{result.stdout}"
        f"{result.stderr}"
    )
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": feedback,
        }
    }
    print(json.dumps(output, ensure_ascii=False))
