"""
수동 크롤링 실행 스크립트
사용법:
  python main.py              # config.json에서 활성화된 모든 크롤러 실행
  python main.py --all        # 모든 크롤러 강제 실행
  python main.py NVIDIA Toss  # 특정 크롤러만 실행
  python main.py --reclassify # 크롤링 없이 기존 데이터의 직무·연차·지역만 다시 계산
"""
import sys
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

import json
import os
from pathlib import Path
from dotenv import load_dotenv
from crawlers import get_all_crawlers, now_utc, now_kst
from crawlers.enrich import enrich_jobs, REGIONS, LEVELS
from crawlers.classifier import ROLE_GROUPS

# 대시보드가 필터 순서·이름을 하드코딩하지 않도록 분류 체계를 데이터와 함께 내보낸다
TAXONOMY = {"groups": ROLE_GROUPS, "levels": LEVELS, "regions": REGIONS}

# 크롤 실패 시 이전 공고를 유지하는 최대 일수 — 넘기면 닫힌 공고가 남지 않도록 내린다
STALE_MAX_DAYS = 7


def days_between(a: str, b: str) -> int:
    from datetime import date
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


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
    existing_sources = existing.get("sources", {})
    selected_companies = {crawlers[n].company for n in selected}
    today = now_kst().date().isoformat()

    # 부분 실행이면 선택되지 않은 회사의 기존 항목을 그대로 넘긴다
    if is_partial:
        carry_jobs = [j for j in existing_jobs if j.get("company") not in selected_companies]
        carry_results = {k: v for k, v in existing_results.items() if k not in selected}
        carry_sources = {k: v for k, v in existing_sources.items() if k not in selected}
    else:
        carry_jobs, carry_results, carry_sources = [], {}, {}

    print(f"\n{'='*50}")
    print(f"🚀 크롤링 시작 ({len(selected)}개)" + (" [병합 모드]" if is_partial else ""))
    print(f"{'='*50}\n")

    new_jobs = []
    new_results = {}
    new_sources = {}
    degraded = []

    problems = []   # (회사, 상태, 원인) — 실행 끝 요약과 GitHub Actions 표시에 쓴다

    for name in selected:
        crawler = crawlers[name]
        crawler.issues = []
        print(f"▶ {name}...")
        crash = ""
        try:
            jobs = crawler.fetch_jobs()
        except Exception as e:
            jobs = []
            crash = f"크롤러 코드 예외 {type(e).__name__}: {e}"
            print(f"  ❌ {crash}")

        # 0건의 원인: 예외 > 크롤러가 남긴 마지막 기록 > (기록이 없으면) 그 사실 자체
        reason = crash or (crawler.issues[-1] if crawler.issues else "")
        prev_count = existing_results.get(name, 0)
        prev_src = existing_sources.get(name, {})
        stale_since, warning, error = "", "", ""

        # 직전에 공고가 있었는데 0건이면 사이트가 빈 게 아니라 크롤이 실패한 것으로 본다.
        # 전체 교체 방식이라 그냥 두면 일시적 타임아웃 한 번에 그 회사 공고가 통째로 사라진다.
        # 단, 실패가 STALE_MAX_DAYS 넘게 이어지면 그사이 닫힌 공고가 쌓이므로 이전 데이터도 내린다.
        if not jobs and (prev_count > 0 or prev_src.get("status") in ("stale", "failed") or reason):
            degraded.append(name)
            error = reason or "오류 없이 0건 — 사이트 구조가 바뀌었거나 실제로 열린 공고가 없음"
            stale_since = prev_src.get("stale_since") or today
            last_ok = prev_src.get("last_success", "")
            if prev_count == 0 and prev_src.get("status") not in ("stale",):
                status = "failed"
                print(f"  ❌ 0건 — {error}\n")
            elif days_between(stale_since, today) >= STALE_MAX_DAYS:
                status = "failed"
                print(f"  ❌ 0건 — {stale_since}부터 실패가 이어져 이전 공고를 내림. 원인: {error}\n")
            else:
                jobs = [j for j in existing_jobs if j.get("company") == crawler.company]
                status = "stale"
                print(f"  ⚠️  0건 (직전 {prev_count}건) — 이전 {len(jobs)}건 유지. 원인: {error}\n")
            problems.append((name, status, error))
        else:
            print(f"  ✅ {len(jobs)}건\n")
            status, last_ok = "ok", today
            # 0은 아니지만 반 넘게 줄었다면 일부 페이지만 실패했을 수 있다
            if prev_count >= 10 and len(jobs) < prev_count * 0.5:
                warning = f"직전 {prev_count}건 → {len(jobs)}건으로 급감" + (f" ({reason})" if reason else "")
                problems.append((name, "warning", warning))

        new_jobs.extend(jobs)
        new_results[name] = len(jobs)
        # 대시보드가 '며칠째 갱신 안 됨'을 보여줄 수 있도록 회사별 상태를 남긴다
        new_sources[name] = {
            "company": crawler.company,
            "category": crawler.category,
            "sectors": getattr(crawler, "sectors", []),
            "count": len(jobs),
            "status": status,
            "last_success": last_ok,
            "stale_since": stale_since,
            "error": error,
            "warning": warning,
        }

    # 분류·연차·지역·최초 수집일은 여기서 한 번에 붙인다 (유지된 이전 데이터도 새 규칙으로 재분류)
    all_jobs = enrich_jobs(carry_jobs + new_jobs, existing_jobs, today)
    all_results = {**carry_results, **new_results}
    all_sources = {**carry_sources, **new_sources}

    output = {
        "updated_at": now_utc().isoformat(),
        "total": len(all_jobs),
        "results": all_results,
        "sources": all_sources,
        "taxonomy": TAXONOMY,
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
    fresh = sum(1 for j in all_jobs if j.get("first_seen") == today)
    print(f"✨ 완료! 총 {len(all_jobs)}개 채용공고 (오늘 처음 본 공고 {fresh}개)")
    print(f"📁 저장 위치: {OUTPUT_PATH}")
    print(f"{'='*50}\n")
    report_problems(problems, new_sources)

    return degraded


STATUS_LABEL = {"stale": "실패 (이전 공고 유지)", "failed": "실패 (공고 없음)", "warning": "급감"}


def report_problems(problems, sources):
    """실패 원인을 한곳에 모아 보여 준다.
    로컬: 콘솔 표 / GitHub Actions: 실행 화면 상단 오류 표시(::error)와 요약 표(STEP_SUMMARY)."""
    if not problems:
        print("✅ 모든 회사 정상 수집\n")
    else:
        print("🔎 수집 문제 요약")
        for name, status, why in problems:
            print(f"  - {name}: {STATUS_LABEL[status]} — {why}")
        print()

    if os.environ.get("GITHUB_ACTIONS") == "true":
        for name, status, why in problems:
            level = "warning" if status == "warning" else "error"
            # 줄바꿈·콜론이 annotation 문법을 깨지 않도록 정리
            msg = why.replace("\n", " ").replace("%", "%25")
            print(f"::{level} title={name} {STATUS_LABEL[status]}::{msg}")

    summary_path = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary_path:
        lines = ["## 채용공고 수집 결과", "",
                 "| 회사 | 상태 | 건수 | 원인 |", "| --- | --- | ---: | --- |"]
        flagged = {n: (s, w) for n, s, w in problems}
        for name, src in sources.items():
            status, why = flagged.get(name, ("ok", ""))
            label = {"ok": "✅ 정상", "warning": "⚠️ 급감", "stale": "❌ 실패 · 이전 공고 유지",
                     "failed": "❌ 실패"}[status]
            lines.append(f"| {name} | {label} | {src['count']} | {why.replace('|', '/')} |")
        with open(summary_path, "a", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")


def reclassify():
    """분류 규칙을 고친 뒤 크롤링 없이 바로 결과를 확인할 때 쓴다."""
    data = load_existing(OUTPUT_PATH)
    jobs = data.get("jobs", [])
    data["jobs"] = enrich_jobs(jobs, jobs, now_kst().date().isoformat())
    data["taxonomy"] = TAXONOMY
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"✅ {len(data['jobs'])}건 재분류 완료 → {OUTPUT_PATH}")


if __name__ == "__main__":
    args = sys.argv[1:]
    if "--reclassify" in args:
        reclassify()
        sys.exit(0)
    if "--all" in args:
        degraded = run(force_all=True)
    elif args:
        degraded = run(targets=args)
    else:
        degraded = run()

    # 데이터는 이미 저장됐지만 실패를 눈에 띄게 하려고 종료 코드로 알린다.
    # 워크플로는 커밋/푸시를 always()로 돌리므로 정상 데이터는 그대로 반영된다.
    sys.exit(1 if degraded else 0)
