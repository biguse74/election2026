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


def align_to_remote() -> None:
    """origin/main에 정렬하되 코드 등 미커밋 작업은 보존한다.
    --hard는 모든 작업트리를 날려 편집 중인 코드까지 지우므로,
    HEAD만 origin/main으로 옮기고(--mixed, 작업트리 유지) 데이터 디렉터리만 origin 상태로 되돌린다."""
    run("git", "rebase", "--abort")
    run("git", "merge", "--abort")
    run("git", "fetch", "origin", "main")
    run("git", "reset", "--mixed", "origin/main")
    # 데이터 디렉터리(추적 파일)만 origin 기준으로 정리 — 어차피 새로 생성해 덮어쓴다.
    run("git", "checkout", "origin/main", "--", "data/live_counting")


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
