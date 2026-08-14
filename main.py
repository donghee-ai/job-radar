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
from pathlib import Path
from dotenv import load_dotenv
from crawlers import get_all_crawlers, now_utc

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
        return []

    # 기존 데이터는 항상 읽는다 — 부분 실행 병합과 크롤 실패 폴백 양쪽에 쓰인다
    is_partial = bool(targets) and not force_all
    existing = load_existing(OUTPUT_PATH)
    existing_jobs = existing.get("jobs", [])
    existing_results = existing.get("results", {})
    selected_companies = {crawlers[n].company for n in selected}

    # 부분 실행이면 선택되지 않은 회사의 기존 항목을 그대로 넘긴다
    if is_partial:
        carry_jobs = [j for j in existing_jobs if j.get("company") not in selected_companies]
        carry_results = {k: v for k, v in existing_results.items() if k not in selected}
    else:
        carry_jobs, carry_results = [], {}

    print(f"\n{'='*50}")
    print(f"🚀 크롤링 시작 ({len(selected)}개)" + (" [병합 모드]" if is_partial else ""))
    print(f"{'='*50}\n")

    new_jobs = []
    new_results = {}
    degraded = []

    for name in selected:
        crawler = crawlers[name]
        print(f"▶ {name}...")
        try:
            jobs = crawler.fetch_jobs()
        except Exception as e:
            jobs = []
            print(f"  ❌ Error: {e}")

        # 직전에 공고가 있었는데 0건이면 사이트가 빈 게 아니라 크롤이 실패한 것으로 본다.
        # 전체 교체 방식이라 그냥 두면 일시적 타임아웃 한 번에 그 회사 공고가 통째로 사라진다.
        prev_count = existing_results.get(name, 0)
        if not jobs and prev_count > 0:
            jobs = [j for j in existing_jobs if j.get("company") == crawler.company]
            degraded.append(name)
            print(f"  ⚠️  0건 (직전 {prev_count}건) — 크롤 실패로 보고 이전 {len(jobs)}건 유지\n")
        else:
            print(f"  ✅ {len(jobs)}건\n")

        new_jobs.extend(jobs)
        new_results[name] = len(jobs)

    all_jobs = carry_jobs + new_jobs
    all_results = {**carry_results, **new_results}

    output = {
        "updated_at": now_utc().isoformat(),
        "total": len(all_jobs),
        "results": all_results,
        "jobs": all_jobs
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    if "schedule" not in config:
        config["schedule"] = {}
    config["schedule"]["last_updated"] = now_utc().isoformat()
    save_config(config)

    print(f"{'='*50}")
    print(f"✨ 완료! 총 {len(all_jobs)}개 채용공고 (신규 {len(new_jobs)}개)")
    print(f"📁 저장 위치: {OUTPUT_PATH}")
    if degraded:
        print(f"⚠️  이전 데이터로 대체됨: {', '.join(degraded)} — 크롤러 점검 필요")
    print(f"{'='*50}\n")

    return degraded


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--all" in args:
        degraded = run(force_all=True)
    elif args:
        degraded = run(targets=args)
    else:
        degraded = run()

    # 데이터는 이미 저장됐지만 실패를 눈에 띄게 하려고 종료 코드로 알린다.
    # 워크플로는 커밋/푸시를 always()로 돌리므로 정상 데이터는 그대로 반영된다.
    sys.exit(1 if degraded else 0)
