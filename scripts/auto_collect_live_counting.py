#!/usr/bin/env python3
"""라이브 투표율·개표 자동 수집 — 윈도우 작업 스케줄러용 1회 실행 래퍼.

GitHub Actions 크론이 6/3 당일 발화를 누락해, 로컬 작업 스케줄러로 이중화한다.
rebase-free 전략(코드 보존형):
    매 실행마다 origin/main 정렬(HEAD만 이동, 작업트리 유지) → data/live_counting만
    origin으로 정리 → 데이터 재생성 → data/live_counting만 스테이징·commit/push,
    push reject 시 재시도. 커밋은 data만 담으므로 편집 중인 코드는 절대 건드리지 않는다.

시간대(KST):
    06:00~17:59  투표율만 (--skip-counting)   웹 스크랩으로 투표율 생성
    18:00~       투표율 + 개표 (full)          개표는 OpenAPI

NEC_API_KEY: 환경변수 또는 data/.nec_api_key(gitignored) 파일에서 읽음.
작업 스케줄러 등록 예: 06:00부터 5분 간격.
로그: data/live_counting/_scheduler.log
"""
from __future__ import annotations
import os, subprocess, sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KST = timezone(timedelta(hours=9))
SCRIPT = str(ROOT / "scripts" / "fetch_live_counting.py")
KEY_FILE = ROOT / "data" / ".nec_api_key"
LOG = ROOT / "data" / "live_counting" / "_scheduler.log"


def log(msg: str) -> None:
    line = f"[{datetime.now(KST).strftime('%m-%d %H:%M:%S')}] {msg}"
    print(line)
    try:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def run(*args, env=None):
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env)


def load_key() -> str:
    key = os.environ.get("NEC_API_KEY", "").strip()
    if not key and KEY_FILE.exists():
        key = KEY_FILE.read_text(encoding="utf-8").strip()
    return key


# 스크래퍼가 매 회차 새로 생성하는 자동 파일(이것만 origin으로 되돌린다).
# watchlist.json·exit_poll*.json·groups.json 등 수동 편집 데이터는 건드리지 않아
# 미커밋 수동 편집도 보존된다(다음 add/commit 때 함께 반영).
AUTO_DATA = ["data/live_counting/current.json", "data/live_counting/meta.json",
             "data/live_counting/timeseries.json", "data/live_counting/raw"]


def align_to_remote() -> None:
    """origin/main에 정렬하되 코드·수동 데이터 등 미커밋 작업은 보존한다.
    --hard(작업트리 전체 삭제) 대신 HEAD만 origin/main으로 옮기고(--mixed),
    스크래퍼가 새로 만드는 자동 데이터 파일만 origin 기준으로 정리한다."""
    run("git", "rebase", "--abort")
    run("git", "merge", "--abort")
    run("git", "fetch", "origin", "main")
    run("git", "reset", "--mixed", "origin/main")
    run("git", "checkout", "origin/main", "--", *AUTO_DATA)


def collect_and_stage(env) -> bool:
    hour = datetime.now(KST).hour
    mode_args = ["--skip-counting"] if hour < 18 else []
    r = run(sys.executable, SCRIPT, *mode_args, env=env)
    tail = (r.stdout or "").strip().splitlines()[-3:]
    if r.returncode != 0:
        log("수집 실패: " + (r.stderr or "")[:200])
    else:
        for ln in tail:
            if "투표율" in ln or "races=" in ln:
                log("수집: " + ln.strip())
    run("git", "add", "data/live_counting")
    return run("git", "diff", "--staged", "--quiet").returncode != 0


def main() -> int:
    key = load_key()
    if not key:
        log("NEC_API_KEY 없음 — data/.nec_api_key 또는 환경변수 설정 필요")
        return 2
    env = {**os.environ, "NEC_API_KEY": key}
    msg = "data: 라이브 수집(로컬 스케줄러) KST " + datetime.now(KST).strftime("%H:%M")
    for attempt in (1, 2, 3):
        align_to_remote()
        if not collect_and_stage(env):
            log("변경 없음 — 커밋 생략")
            return 0
        run("git", "commit", "-m", msg)
        p = run("git", "push", "origin", "main")
        if p.returncode == 0:
            log(f"push 성공 (시도 {attempt})")
            return 0
        log(f"push reject — 재정렬 후 재시도 ({attempt}/3)")
    log("push 3회 실패 — 다음 주기 재시도")
    return 1


if __name__ == "__main__":
    sys.exit(main())
