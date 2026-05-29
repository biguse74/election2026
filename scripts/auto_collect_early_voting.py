#!/usr/bin/env python3
"""사전투표율 자동 수집·커밋·푸시 — 윈도우 작업 스케줄러용 1회 실행 래퍼.

충돌 불가능(rebase-free) 전략:
    GitHub Actions cron과 이 작업 스케줄러가 같은 data 파일을 동시에 푸시하면
    `git pull --rebase`가 충돌해 파일이 깨질 수 있다(재생성 파일이라 병합 무의미).
    그래서 '병합'을 아예 안 한다 — 매 실행마다
      ① 원격에 hard 정렬(git reset --hard origin/main)  ← 이전 충돌 잔재도 자동 치유
      ② 그 위에서 스크래퍼로 데이터를 새로 생성
      ③ 변경 있으면 커밋 → push
      ④ push가 reject되면(원격이 그새 움직임) ①부터 재시도
    우리 커밋은 항상 원격 HEAD의 fast-forward 자식이라 충돌이 발생할 수 없다.
    스크래퍼가 idempotent라 새 데이터가 없으면 커밋도 없다(no-op).

작업 스케줄러 등록(예): 5/30 06:00부터 20분 간격.
로그: data/early_voting/_scheduler.log (append)
"""

from __future__ import annotations

import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = "data/early_voting/20260603/"
LOG = ROOT / "data" / "early_voting" / "_scheduler.log"
KST = timezone(timedelta(hours=9))
SCRAPER = str(ROOT / "scripts" / "scrape_early_voting.py")


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")


def log(msg: str) -> None:
    line = f"[{datetime.now(KST).strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    print(line)
    try:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def align_to_remote() -> None:
    """이전 run이 남긴 rebase/merge 잔재 정리 + 원격 HEAD에 hard 정렬."""
    run("git", "rebase", "--abort")   # 진행중 아니면 무시됨
    run("git", "merge", "--abort")
    run("git", "fetch", "origin", "main")
    run("git", "reset", "--hard", "origin/main")


def scrape_and_stage() -> bool:
    """스크래핑 후 data 변경을 스테이징. 변경 있으면 True."""
    r = run(sys.executable, SCRAPER)
    if r.returncode != 0:
        log("scrape 실패: " + (r.stderr or "")[:200])
    else:
        tail = (r.stdout or "").strip().splitlines()[-1:]
        log("scrape: " + (tail[0] if tail else "done"))
    run("git", "add", DATA_DIR)
    return run("git", "diff", "--staged", "--quiet").returncode != 0


def main() -> int:
    msg = "data: 사전투표율 자동 수집 (작업 스케줄러) KST " + datetime.now(KST).strftime("%H:%M")
    for attempt in (1, 2, 3):
        align_to_remote()
        if not scrape_and_stage():
            log("변경 없음 — 커밋 생략 (원격이 이미 최신)")
            return 0
        run("git", "commit", "-m", msg)
        p = run("git", "push", "origin", "main")
        if p.returncode == 0:
            log(f"push 성공 (시도 {attempt})")
            return 0
        log(f"push reject — 원격 재정렬 후 재시도 ({attempt}/3)")
    log("push 3회 실패 — 다음 주기에 자동 재시도")
    return 1


if __name__ == "__main__":
    sys.exit(main())
