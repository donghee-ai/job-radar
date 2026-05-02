"""
하루 단위 자동 크롤링 활성화/비활성화 토글

사용법:
  python toggle_schedule.py status   # 현재 상태 확인
  python toggle_schedule.py on       # 자동 크롤링 활성화
  python toggle_schedule.py off      # 자동 크롤링 비활성화
"""
import json
import sys
from pathlib import Path

CONFIG_PATH = Path("config.json")


def load():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def status():
    cfg = load()
    s = cfg["schedule"]
    print(f"\n📅 자동 크롤링 상태")
    print(f"  활성화: {'✅ ON' if s['enabled'] else '⛔ OFF'}")
    print(f"  주기:   {s['interval']}")
    print(f"  마지막 실행: {s['last_updated'] or '없음'}\n")


def toggle(enabled: bool):
    cfg = load()
    cfg["schedule"]["enabled"] = enabled
    save(cfg)
    print(f"\n{'✅ 자동 크롤링 활성화됨' if enabled else '⛔ 자동 크롤링 비활성화됨'}")
    if enabled:
        print("📌 GitHub Actions에 push하면 매일 09:00 KST에 자동 실행됩니다.\n")
    else:
        print("📌 수동으로만 실행됩니다: python main.py\n")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(1)
    
    cmd = sys.argv[1].lower()
    if cmd == "status":
        status()
    elif cmd == "on":
        toggle(True)
    elif cmd == "off":
        toggle(False)
    else:
        print(__doc__)