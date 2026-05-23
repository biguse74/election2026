#!/usr/bin/env python3
"""
중앙선관위 선거통계시스템(info.nec.go.kr)의 9회 지선 페이지·엔드포인트가
활성화되었는지 자동 감지.

현재(5/24 기준) 상태:
  · findMenu.json?electionId=0020260603  → BI/CP/EC/VC 4개 메뉴 노출 (정적)
  · main_sub_menu.json?menuId=VC         → 빈 응답 (VC 비활성)
  · /electioninfo/0020260603/vc/index_vc.jsp → 67줄 에러 페이지

활성화 감지 시점:
  · 사전투표일(5/29~30) 또는 본투표일(6/3) 직전에 VC 메뉴가 채워짐
  · 그 순간 OpenAPI fallback 스크래퍼 작성 시작 가능

이 스크립트는 한 번 실행 = 한 번 체크. cron으로 5/24~6/3 사이 1시간 간격
실행하면서 활성화 감지 시 exit 1 (워크플로우 실패 → GitHub Actions 자동 알림).

사용:
  python scripts/probe_nec_site.py
  python scripts/probe_nec_site.py --verbose
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone, timedelta

import requests

KST = timezone(timedelta(hours=9))
SG_ID = "0020260603"
BASE = "https://info.nec.go.kr"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
HEADERS = {"Referer": f"{BASE}/", "User-Agent": UA}
TIMEOUT = 20


def get_json(url: str, params: dict) -> dict | None:
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except Exception as e:
        print(f"  ! {url} 호출 실패: {e}", file=sys.stderr)
        return None


def get_html(url: str) -> tuple[int, str | None]:
    """(status_code, body or None). 4xx/5xx도 status는 반환."""
    try:
        r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
        return r.status_code, r.text
    except Exception as e:
        print(f"  ! {url} 호출 실패: {e}", file=sys.stderr)
        return 0, None


def check_findmenu(verbose: bool) -> dict:
    """findMenu.json — 9회 메뉴 트리. 변화 추적."""
    d = get_json(f"{BASE}/main/findMenu.json", {"electionId": SG_ID})
    if not d:
        return {"ok": False, "active": False, "summary": "응답 실패"}
    menus = d.get("beanlist1") or []
    menu_ids = [m.get("menuId") for m in menus]
    # leafCount > 0 또는 internalMessage 비어있지 않으면 변화 신호.
    leaves = sum(int(m.get("leafCount") or 0) for m in menus)
    has_msg = any((m.get("internalMessage") or "").strip() for m in menus)
    # 기준 상태: 메뉴 4개(BI/CP/EC/VC), leafCount 모두 0, message 없음.
    baseline = set(menu_ids) == {"BI", "CP", "EC", "VC"} and leaves == 0 and not has_msg
    summary = f"{len(menus)}개 메뉴 {menu_ids}, leafCount={leaves}, msg={has_msg}"
    if verbose:
        print(f"  {summary}")
    return {"ok": True, "active": not baseline, "summary": summary}


BASELINE_SUBMENU_IDS = {"Hbj", "MySgg", "PrePoll"}


def check_vc_submenu(verbose: bool) -> dict:
    """main_sub_menu.json?menuId=VC vs ?menuId=BI 응답 비교.
    Baseline(5/24): 두 호출 모두 동일한 {Hbj, MySgg, PrePoll} 반환.
    활성화 신호: VC 응답이 BI와 달라지거나 baseline 밖의 MENU_ID 등장.
    """
    vc = get_json(f"{BASE}/main/main_sub_menu.json", {"electionId": SG_ID, "menuId": "VC"})
    bi = get_json(f"{BASE}/main/main_sub_menu.json", {"electionId": SG_ID, "menuId": "BI"})
    if vc is None or bi is None:
        return {"ok": False, "active": False, "summary": "응답 실패"}
    vc_main = vc.get("mainMenuList") or []
    bi_main = bi.get("mainMenuList") or []
    vc_ids = {it.get("MENU_ID", "") for it in vc_main}
    bi_ids = {it.get("MENU_ID", "") for it in bi_main}
    differs = vc_ids != bi_ids
    new_ids = vc_ids - BASELINE_SUBMENU_IDS
    active = differs or bool(new_ids)
    summary = (
        f"VC ids={sorted(vc_ids)}  ·  BI ids={sorted(bi_ids)}  ·  "
        f"differs={differs}  ·  new_ids={sorted(new_ids)}"
    )
    if active:
        summary += "  ← 🟢 VC 활성화 신호!"
        for it in vc_main[:10]:
            print(f"    · {it.get('MENU_ID'):>10} {it.get('MENU_NM','')}  →  {it.get('PGM_PATH','')}")
    elif verbose:
        print(f"  {summary}")
    return {"ok": True, "active": active, "summary": summary}


def check_vc_page(verbose: bool) -> dict:
    """/electioninfo/0020260603/vc/index_vc.jsp — 현재 baseline 404 (또는 67줄 에러).
    200 + 본문 큼 + error_h1 없음 → 활성.
    """
    status, html = get_html(f"{BASE}/electioninfo/{SG_ID}/vc/index_vc.jsp")
    if html is None:
        return {"ok": False, "active": False, "summary": "네트워크 실패"}
    size = len(html)
    has_error = "error_h1" in html or "오류" in html[:2000]
    # 활성: HTTP 200 + 본문 5KB 초과 + 에러 없음
    active = status == 200 and size > 5000 and not has_error
    summary = f"HTTP {status} · {size} bytes · error={has_error}"
    if active:
        summary += "  ← 🟢 VC 페이지 활성!"
    return {"ok": True, "active": active, "summary": summary}


def check_prevote(verbose: bool) -> dict:
    """사전투표소 페이지 — 5/29~30 활성."""
    status, html = get_html(f"{BASE}/main/main_prevote.jsp")
    if html is None:
        return {"ok": False, "active": False, "summary": "네트워크 실패"}
    size = len(html)
    has_error = "error_h1" in html or size < 1000
    active = status == 200 and not has_error and size > 2000
    summary = f"HTTP {status} · {size} bytes · error={has_error}"
    if active:
        summary += "  ← 🟢 사전투표 페이지 노출 중"
    return {"ok": True, "active": active, "summary": summary}


CHECKS = [
    ("findMenu (9회 메뉴 트리)",    check_findmenu),
    ("VC 서브메뉴 (투개표)",         check_vc_submenu),
    ("VC index 페이지",              check_vc_page),
    ("사전투표소 페이지 (BI)",       check_prevote),
]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    polled = datetime.now(KST).isoformat(timespec="seconds")
    print(f"[probe_nec_site] {polled}  electionId={SG_ID}")

    activated: list[str] = []
    for name, fn in CHECKS:
        print(f"· {name}")
        result = fn(args.verbose)
        print(f"  → {result['summary']}")
        if result.get("active"):
            activated.append(name)

    print()
    if activated:
        print("🟢 활성화 감지:")
        for n in activated:
            print(f"   - {n}")
        print("\n→ 워크플로우 fail로 알림. 정찰 작업 즉시 시작.")
        # exit 1 = GitHub Actions에서 빨간 X = 이메일·푸시 알림 발화
        sys.exit(1)
    else:
        print("⚪ 변화 없음 (모두 비활성/기준 상태)")


if __name__ == "__main__":
    main()
