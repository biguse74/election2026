#!/usr/bin/env python3
"""
최신 데이터 스냅샷을 읽어 index.html의 정적 placeholder를 갱신한다.

이유:
    - 사이트가 JS로 데이터를 fetch해서 렌더링하는 SPA 구조라, 검색엔진·SNS
      미리보기·JS off 환경에서 첫 화면이 "데이터 불러오는 중…"만 보임.
    - 핵심 숫자(D-day, 갱신일, 출마자 총수)를 HTML에 사전 박아 두면
      그런 환경에서도 의미 있는 정보가 노출된다.

호출 위치:
    fetch_preliminary.yml / fetch_candidates.yml 워크플로우에서
    데이터 fetch 후 push 직전에 한 번 실행.

대상 영역:
    - <div id="dday">…</div>          : D-22 등
    - <span id="last-updated">…</span> : 2026.05.12 · 예비후보 N,NNN명
    - <main id="app" class="loading">  : 로딩 중에 보이는 요약 블록
"""

from __future__ import annotations

import glob
import json
import re
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KST = timezone(timedelta(hours=9))
ELECTION_DATE = datetime(2026, 6, 3, tzinfo=KST)


def latest_snapshot() -> tuple[Path | None, str | None]:
    cand_files = sorted(ROOT.glob("data/candidates/20260603/snapshot_*.json"))
    if cand_files:
        return cand_files[-1], "candidates"
    prelim_files = sorted(ROOT.glob("data/preliminary/20260603/snapshot_*.json"))
    if prelim_files:
        return prelim_files[-1], "preliminary"
    return None, None


def dday_text(now: datetime) -> str:
    today = now.replace(hour=0, minute=0, second=0, microsecond=0)
    diff = (ELECTION_DATE - today).days
    if diff > 0:
        return f"D-{diff}"
    if diff == 0:
        return "D-DAY"
    return f"D+{-diff}"


def replace_block(html: str, pattern: str, replacement: str, label: str) -> str:
    new_html, n = re.subn(pattern, replacement, html, count=1, flags=re.DOTALL)
    if n == 0:
        print(f"  [경고] {label} 패턴 매치 실패", file=sys.stderr)
    return new_html


def main() -> None:
    snap_path, source = latest_snapshot()
    if not snap_path:
        sys.exit("데이터 스냅샷이 없습니다.")

    data = json.loads(snap_path.read_text(encoding="utf-8"))
    cands = data.get("candidates", [])
    total = len(cands)

    # 파일명 snapshot_YYYYMMDD.json → "2026.05.12"
    date_part = snap_path.stem.split("_")[-1]
    date_disp = f"{date_part[:4]}.{date_part[4:6]}.{date_part[6:8]}"
    stage_label = "후보 등록" if source == "candidates" else "예비후보"
    stage_short = "후보" if source == "candidates" else "예비후보"

    now = datetime.now(KST)
    dday = dday_text(now)

    html_path = ROOT / "index.html"
    html = html_path.read_text(encoding="utf-8")

    html = replace_block(
        html,
        r'<div class="dday-number" id="dday">[^<]*</div>',
        f'<div class="dday-number" id="dday">{dday}</div>',
        "D-day",
    )
    html = replace_block(
        html,
        r'<span id="last-updated">[^<]*</span>',
        f'<span id="last-updated">{date_disp} · {stage_label}</span>',
        "last-updated",
    )
    # main id="app" class="loading" 안의 텍스트를 의미 있는 요약 블록으로 교체.
    # JS가 로딩 끝나면 이 안을 통째로 덮어쓰므로(innerHTML), 사용자 인지엔 영향 없음.
    summary_block = (
        '<div class="pre-summary">'
        f'<p class="pre-summary-line">현재 등록 <strong>{stage_short} {total:,}명</strong></p>'
        f'<p class="pre-summary-line pre-summary-meta">기준 {date_disp} · 데이터를 불러오는 중…</p>'
        "</div>"
    )
    html = replace_block(
        html,
        r'<main id="app" class="loading">[^<]*</main>',
        f'<main id="app" class="loading">{summary_block}</main>',
        "loading-summary",
    )

    # Cache buster — 매 갱신마다 CSS/JS URL에 ?v=YYYYMMDDHHMM 박아
    # GitHub Pages·CDN·브라우저 캐시(max-age=600)를 우회한다.
    v = now.strftime("%Y%m%d%H%M")
    html = re.sub(r'(css/main\.css)(\?v=\d+)?', rf'\1?v={v}', html)
    html = re.sub(r'(js/main\.js)(\?v=\d+)?', rf'\1?v={v}', html)

    html_path.write_text(html, encoding="utf-8")
    print(
        f"render_summary: dday={dday}, {stage_label} {total:,}명, "
        f"기준 {date_disp}"
    )


if __name__ == "__main__":
    main()
