"""
수동 크롤링 실행 스크립트
사용법:
  python main.py              # config.json에서 활성화된 모든 크롤러 실행
  python main.py --all        # 모든 크롤러 강제 실행
  python main.py NVIDIA Toss  # 특정 크롤러만 실행
"""
import json
import sys
from datetime import datetime
from pathlib import Path
from dotenv import load_dotenv
from crawlers import get_all_crawlers

load_dotenv()

CONFIG_PATH = Path("config.json")
OUTPUT_PATH = Path("docs/data/jobs.json")


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def save_config(cfg):
    with open(CONFIG_PATH, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)


def run(targets=None, force_all=False):
    config = load_config()
    crawlers = get_all_crawlers()

    if force_all:
        selected = list(crawlers.keys())
    elif targets:
        unknown = [t for t in targets if t not in crawlers]
        if unknown:
            print(f"⚠️  알 수 없는 크롤러: {unknown}. 사용 가능: {list(crawlers.keys())}")
        selected = [t for t in targets if t in crawlers]
    else:
        crawler_cfg = config.get("crawlers", {})
        selected = [k for k, v in crawler_cfg.items() if v and k in crawlers]

    if not selected:
        print("❌ 실행할 크롤러가 없습니다. config.json을 확인하세요.")
        return

    print(f"\n{'='*50}")
    print(f"🚀 크롤링 시작 ({len(selected)}개)")
    print(f"{'='*50}\n")

    all_jobs = []
    results = {}

    for name in selected:
        crawler = crawlers[name]
        print(f"▶ {name}...")
        try:
            jobs = crawler.fetch_jobs()
            all_jobs.extend(jobs)
            results[name] = len(jobs)
            print(f"  ✅ {len(jobs)} jobs\n")
        except Exception as e:
            results[name] = 0
            print(f"  ❌ Error: {e}\n")

    output = {
        "updated_at": datetime.now().isoformat(),
        "total": len(all_jobs),
        "results": results,
        "jobs": all_jobs
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    if "schedule" not in config:
        config["schedule"] = {}
    config["schedule"]["last_updated"] = datetime.now().isoformat()
    save_config(config)
    
    print(f"{'='*50}")
    print(f"✨ 완료! 총 {len(all_jobs)}개 채용공고")
    print(f"📁 저장 위치: {OUTPUT_PATH}")
    print(f"{'='*50}\n")


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--all" in args:
        run(force_all=True)
    elif args:
        run(targets=args)
    else:
        run()