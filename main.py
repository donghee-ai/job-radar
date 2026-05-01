"""
수동 크롤링 실행 스크립트
사용법:
  python main.py              # config.json에서 활성화된 모든 크롤러 실행
  python main.py --all        # 모든 크롤러 강제 실행
  python main.py NVIDIA Toss  # 특정 크롤러만 실행
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

import json
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


def load_existing(path: Path):
    """기존 jobs.json을 로드. 없거나 손상된 경우 빈 구조 반환."""
    if not path.exists():
        return {"jobs": [], "results": {}}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"jobs": [], "results": {}}


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

    # 부분 실행이면 기존 데이터를 보존하고 해당 회사 항목만 교체
    is_partial = bool(targets) and not force_all
    existing = load_existing(OUTPUT_PATH) if is_partial else {"jobs": [], "results": {}}
    selected_companies = {crawlers[n].company for n in selected}

    carry_jobs = [j for j in existing.get("jobs", []) if j.get("company") not in selected_companies]
    carry_results = {k: v for k, v in existing.get("results", {}).items() if k not in selected}

    print(f"\n{'='*50}")
    print(f"🚀 크롤링 시작 ({len(selected)}개)" + (" [병합 모드]" if is_partial else ""))
    print(f"{'='*50}\n")

    new_jobs = []
    new_results = {}

    for name in selected:
        crawler = crawlers[name]
        print(f"▶ {name}...")
        try:
            jobs = crawler.fetch_jobs()
            new_jobs.extend(jobs)
            new_results[name] = len(jobs)
            print(f"  ✅ {len(jobs)}건\n")
        except Exception as e:
            new_results[name] = 0
            print(f"  ❌ Error: {e}\n")

    all_jobs = carry_jobs + new_jobs
    all_results = {**carry_results, **new_results}

    output = {
        "updated_at": datetime.now().isoformat(),
        "total": len(all_jobs),
        "results": all_results,
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
    print(f"✨ 완료! 총 {len(all_jobs)}개 채용공고 (신규 {len(new_jobs)}개)")
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