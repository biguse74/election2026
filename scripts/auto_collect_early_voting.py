#!/usr/bin/env python3
"""사전투표율 자동 수집·커밋·푸시 — 윈도우 작업 스케줄러용 1회 실행 래퍼.

동작:
    1) scrape_early_voting.py 실행 (07~18시 전 시각 자가치유 수집)
    2) data/early_voting/20260603/ 변경이 있으면(=새 시각/수치 변동) commit
       (스크래퍼가 idempotent라 변동 없으면 파일을 안 건드림 → noise 커밋 없음)
    3) pull --rebase 후 push (GitHub 봇/다른 곳 커밋과 충돌 시 흡수)

작업 스케줄러 등록(예: 5/30 06:00부터 20분 간격 13시간):
    schtasks /Create /TN "뉴탐사_사전투표수집" ^
      /TR "C:\\Python314\\python.exe C:\\...\\scripts\\auto_collect_early_voting.py" ^
      /SC ONCE /ST 06:00 /SD 2026/05/30 /RI 20 /DU 13:00 /F

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


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        args, cwd=ROOT, capture_output=True, text=True,
        encoding="utf-8", errors="replace",
    )


def log(msg: str) -> None:
    stamp = datetime.now(KST).strftime("%Y-%m-%d %H:%M:%S")
    line = f"[{stamp}] {msg}"
    print(line)
    try:
        with LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass


def main() -> int:
    # 1) 스크래핑
    r = run(sys.executable, str(ROOT / "scripts" / "scrape_early_voting.py"))
    tail = (r.stdout or "").strip().splitlines()[-3:]
    log("scrape: " + " | ".join(tail))
    if r.returncode != 0:
        log("scrape 실패: " + (r.stderr or "")[:300])
        return 1

    # 2) 변경 스테이징
    run("git", "add", DATA_DIR)
    staged = run("git", "diff", "--staged", "--quiet")
    if staged.returncode == 0:
        log("변경 없음 — 커밋 생략")
        return 0

    # 3) 커밋
    msg = "data: 사전투표율 자동 수집 (작업 스케줄러) KST " + datetime.now(KST).strftime("%H:%M")
    c = run("git", "commit", "-m", msg)
    log("commit: " + (c.stdout or c.stderr or "").strip().splitlines()[0] if (c.stdout or c.stderr) else "commit done")

    # 4) pull --rebase 후 push (1회 재시도)
    for attempt in (1, 2):
        run("git", "pull", "--rebase", "origin", "main")
        p = run("git", "push", "origin", "main")
        if p.returncode == 0:
            log(f"push 성공 (시도 {attempt})")
            return 0
        log(f"push 실패 (시도 {attempt}): " + (p.stderr or "")[:200])
    return 1


if __name__ == "__main__":
    sys.exit(main())
