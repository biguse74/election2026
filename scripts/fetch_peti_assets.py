#!/usr/bin/env python3
"""
인사혁신처 공직윤리시스템(PETI)에서 지방선거 당선자의 항목별 재산신고 명세를 수집한다.

선관위 후보자 공개정보는 선거일까지만 공개되고(공직선거법 제49조 제12항) 그 뒤 사라지지만,
당선자는 공직자윤리법 제10조에 따라 공직자윤리위원회가 재산을 별도로 공개한다.
PETI는 국회·법원·헌재·선관위·지방자치단체 공개분을 한곳에 모아 둔다.

지방선거 당선자 일정 (2026년 기준)
    임기 개시 2026-07-01 → 등록 마감 2026-09-30(제5조①) → 공개 마감 2026-10-31(제10조①)
    즉 11월 초에 돌려야 전원이 잡힌다. 그 전에 돌리면 미공개 시·도가 빠진다.

수집 경로 (순수 HTTP, 브라우저·RAONK 불필요)
    1) GET  /peOptpListVie.do                → csrfToken
    2) POST /peoptp/getListOptpListVie.do    → 성명으로 공개목록 조회, rgsMno 획득
    3) POST /peoptp/getListDetailPrptOptp.do → rgsMno로 항목별 명세 JSON

사용:
    python scripts/fetch_peti_assets.py --limit 5          # 시험
    python scripts/fetch_peti_assets.py --name 추미애       # 특정인
    python scripts/fetch_peti_assets.py                    # 당선자 전원
    python scripts/fetch_peti_assets.py --sg-type 3,4,11   # 단체장·교육감만

산출물:
    data/peti_assets/index.json        수집 상태 요약(재개용)
    data/peti_assets/detail/{huboid}.json

주의
  · NetFunnel(대기열)이 붙어 있어 과속하면 막힌다. --delay 기본 1.2초를 줄이지 말 것.
  · 동명이인이 흔하다. 기관명이 맞지 않으면 matched=false로 남기고 사람이 판단하게 둔다.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

BASE = "https://www.peti.go.kr"
LIST_PAGE = f"{BASE}/peOptpListVie.do"
LIST_API = f"{BASE}/peoptp/getListOptpListVie.do"
DETAIL_API = f"{BASE}/peoptp/getListDetailPrptOptp.do"

TARGET_SG_ID = "20260603"
# 지방자치단체장·지방의원 임기 개시일. 이 날짜가 등록기준일인 건이 지방선거 당선자 몫이다.
TERM_START = "2026-07-01"

ROOT_DIR = Path(__file__).resolve().parent.parent
SNAP_DIR = ROOT_DIR / "data" / "candidates" / TARGET_SG_ID
WINNERS = ROOT_DIR / "data" / "winner_huboids.json"
OUT_DIR = ROOT_DIR / "data" / "peti_assets"
DETAIL_DIR = OUT_DIR / "detail"
INDEX_FILE = OUT_DIR / "index.json"

KST = timezone(timedelta(hours=9))
def now_kst() -> datetime: return datetime.now(KST)

HEADERS = {
    "User-Agent": "newtamsa-election2026/1.0 (+https://github.com/biguse74/election2026)",
    "Referer": LIST_PAGE,
    "X-Requested-With": "XMLHttpRequest",
}
TOKEN_RE = re.compile(r'id="csrfToken"[^>]*value="([^"]+)"')


def latest_snapshot() -> Path:
    files = sorted(SNAP_DIR.glob("snapshot_*.json"))
    if not files:
        raise SystemExit(f"후보 스냅샷이 없다: {SNAP_DIR}")
    return files[-1]


def load_winners(sg_types: set[str] | None) -> list[dict]:
    ids = set(map(str, json.loads(WINNERS.read_text(encoding="utf-8"))["huboids"]))
    snap = json.loads(latest_snapshot().read_text(encoding="utf-8"))["candidates"]
    out = []
    for c in snap:
        if str(c["huboid"]) not in ids:
            continue
        if sg_types and str(c.get("sgTypecode")) not in sg_types:
            continue
        out.append(c)
    return out


def org_hints(c: dict) -> list[str]:
    """PETI 기관명(ornm)과 대조할 후보 소속 문자열. 넓게 잡고 매칭은 부분일치로 한다."""
    sd = str(c.get("sdName") or "").strip()
    wiw = str(c.get("wiwName") or "").strip()
    sgg = str(c.get("sggName") or "").strip()
    # 선거구명에 붙는 꼬리(제1선거구·가선거구 등)를 떼어 시군구명만 남긴다
    trimmed = re.sub(r"(제?\d+선거구|[가-힣]선거구)$", "", sgg).strip()
    hints = [sd, wiw, sgg, trimmed]
    # PETI 기관명은 기초단체를 "강원특별자치도 원주시"처럼 시도명을 붙여 쓴다.
    # 조합형을 넣어야 부분일치가 아니라 완전일치로 잡힌다.
    for sub in (wiw, trimmed, sgg):
        if sd and sub and sub != sd:
            hints.append(f"{sd} {sub}")
    return [h for h in dict.fromkeys(hints) if h]


def session_with_token() -> tuple[requests.Session, str]:
    s = requests.Session()
    s.headers.update(HEADERS)
    html = s.get(LIST_PAGE, timeout=30).text
    m = TOKEN_RE.search(html)
    if not m:
        raise SystemExit("csrfToken을 찾지 못했다. PETI 페이지 구조가 바뀌었을 수 있다.")
    return s, m.group(1)


def search_by_name(s, token, name, from_dt, to_dt) -> list[dict]:
    r = s.post(LIST_API, timeout=60, data={
        "fromOptpDt": from_dt, "toOptpDt": to_dt,
        "firstCount": 1, "lastCount": 100,
        "ornm": "", "rgsDtrNm": name, "srchSe": "dtrSrch", "csrfToken": token,
    })
    r.raise_for_status()
    return r.json().get("result") or []


def fetch_detail(s, token, rgs_mno) -> dict:
    r = s.post(DETAIL_API, timeout=120, data={"rgsMno": rgs_mno, "csrfToken": token})
    r.raise_for_status()
    return r.json()


# 선거종류코드별로 기대되는 직위(ofpsNm) 키워드. PETI 행의 직위가 이와 어긋나면 후보에서 뺀다.
# 기관명 부분일치만 믿으면 "경상북도 울릉군 울릉군의회 의원"이 경북도지사로 붙는다.
OFFICE_KEYWORDS = {
    "3": ("도지사", "시장"),            # 시도지사 (특별시장·광역시장 포함)
    "4": ("시장", "군수", "구청장"),     # 기초단체장
    "11": ("교육감",),
    "5": ("의원",), "6": ("의원",), "8": ("의원",), "9": ("의원",),
    "2": ("의원",),
}


def office_ok(row: dict, sg_type: str) -> bool:
    want = OFFICE_KEYWORDS.get(str(sg_type))
    ofps = str(row.get("ofpsNm") or "").strip()
    if not want or not ofps:
        return True                      # 직위 정보가 없으면 판단 보류(배제하지 않는다)
    if ofps.startswith("(전)"):
        return False                     # 전직은 이번 임기 당선자가 아니다
    return any(k in ofps for k in want)


def pick_row(rows: list[dict], hints: list[str], sg_type: str = "") -> tuple[dict | None, str]:
    """등록기준일이 임기 개시일인 건 중 기관명이 후보 소속과 맞는 행을 고른다.

    부분일치만으로 고르면 안 된다. 실제로 경북도지사 이철우가 "경상북도 울릉군 울릉군의회"
    소속 동명이인에 붙은 적이 있다("경상북도"가 부분문자열이라서). 완전일치를 먼저 보고,
    부분일치는 후보가 유일할 때만 쓰되 따로 표시한다.
    """
    term = [x for x in rows
            if (x.get("rgsSrDt") or "") == TERM_START and office_ok(x, sg_type)]
    if not rows:
        return None, "not_found"
    if not term:
        return None, "no_term_row"      # 이름은 있으나 지방선거 당선자 몫(임기개시일 기준)이 없다
    hintset = {h.strip() for h in hints if h and h.strip()}

    exact = [x for x in term if str(x.get("ornm") or "").strip() in hintset]
    if len(exact) == 1:
        return exact[0], "matched"
    if len(exact) > 1:
        return None, "ambiguous"

    loose = [x for x in term
             if any(h in str(x.get("ornm") or "") for h in hintset)]
    if len(loose) == 1:
        return loose[0], "matched_loose"   # 기관명이 부분일치. 사람이 확인할 것
    if len(loose) > 1:
        return None, "ambiguous"
    if len(term) == 1:
        return term[0], "term_only"        # 기관명은 안 맞지만 임기개시일 기준 1건뿐
    return None, "ambiguous"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="앞에서 N명만")
    ap.add_argument("--name", action="append", default=[], help="특정 성명만 (반복 가능)")
    ap.add_argument("--sg-type", default="", help="선거종류코드 필터. 예: 3,4,11")
    ap.add_argument("--from-dt", default="20260701", help="공개일자 시작 YYYYMMDD")
    ap.add_argument("--to-dt", default="", help="공개일자 끝 YYYYMMDD (기본: 오늘)")
    ap.add_argument("--delay", type=float, default=1.2, help="요청 간 대기 초. NetFunnel 때문에 줄이지 말 것")
    ap.add_argument("--refresh", action="store_true", help="이미 수집한 사람도 다시 조회")
    args = ap.parse_args()

    to_dt = args.to_dt or now_kst().strftime("%Y%m%d")
    sg_types = {x.strip() for x in args.sg_type.split(",") if x.strip()} or None

    winners = load_winners(sg_types)
    if args.name:
        want = set(args.name)
        winners = [c for c in winners if c.get("name") in want]
    if args.limit:
        winners = winners[: args.limit]

    DETAIL_DIR.mkdir(parents=True, exist_ok=True)
    index = {}
    if INDEX_FILE.exists() and not args.refresh:
        try:
            index = json.loads(INDEX_FILE.read_text(encoding="utf-8")).get("people") or {}
        except (json.JSONDecodeError, OSError):
            index = {}

    todo = [c for c in winners if args.refresh or index.get(str(c["huboid"]), {}).get("status") not in ("matched", "matched_loose", "term_only")]
    print(f"대상 {len(winners):,}명 · 이번에 조회 {len(todo):,}명 (수집 완료 {len(winners) - len(todo):,}명 건너뜀)")
    print(f"공개일자 {args.from_dt}~{to_dt} · 요청 간격 {args.delay}초")
    if not todo:
        return

    s, token = session_with_token()
    started = now_kst()
    stat = {"matched": 0, "matched_loose": 0, "term_only": 0,
            "not_found": 0, "no_term_row": 0, "ambiguous": 0, "error": 0}

    for i, c in enumerate(todo, 1):
        hid = str(c["huboid"])
        name = c.get("name") or ""
        try:
            rows = search_by_name(s, token, name, args.from_dt, to_dt)
            row, status = pick_row(rows, org_hints(c), str(c.get("sgTypecode") or ""))
            entry = {
                "huboid": hid, "name": name,
                "sgTypecode": str(c.get("sgTypecode") or ""),
                "sdName": c.get("sdName"), "sggName": c.get("sggName"),
                "status": status,
                "candidates_found": [
                    {k: x.get(k) for k in ("optpDt", "ornm", "ofpsNm", "rgsDtrNm", "rgsSrDt")} for x in rows
                ],
            }
            if row:
                detail = fetch_detail(s, token, row["rgsMno"])
                (DETAIL_DIR / f"{hid}.json").write_text(
                    json.dumps(detail, ensure_ascii=False, indent=1), encoding="utf-8")
                lst = (detail.get("list") or [{}])[0]
                entry["optpDt"] = row.get("optpDt")
                entry["ornm"] = row.get("ornm")
                entry["rgsSrDt"] = row.get("rgsSrDt")
                entry["rows"] = len(lst.get("optpList") or [])
                time.sleep(args.delay)
            index[hid] = entry
            stat[status] = stat.get(status, 0) + 1
        except Exception as exc:  # noqa: BLE001 - 개별 실패는 기록하고 계속
            index[hid] = {"huboid": hid, "name": name, "status": "error", "error": str(exc)[:200]}
            stat["error"] += 1
            print(f"  실패 {hid} {name}: {exc}", file=sys.stderr)

        time.sleep(args.delay)
        if i % 25 == 0 or i == len(todo):
            print(f"  진행 {i:,}/{len(todo):,} · " + " · ".join(f"{k} {v:,}" for k, v in stat.items() if v))

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    INDEX_FILE.write_text(json.dumps({
        "source": BASE,
        "generated_at": started.isoformat(timespec="seconds"),
        "term_start": TERM_START,
        "optp_date_range": [args.from_dt, to_dt],
        "count": len(index),
        "stat": stat,
        "people": index,
    }, ensure_ascii=False, indent=1), encoding="utf-8")

    print(f"\n완료: {(now_kst() - started).total_seconds():.0f}초")
    for k, v in stat.items():
        if v:
            print(f"  {k}: {v:,}")
    print(f"저장: {INDEX_FILE.relative_to(ROOT_DIR)} · {DETAIL_DIR.relative_to(ROOT_DIR)}/")
    if stat.get("not_found"):
        print("\n※ not_found 는 아직 공개 전일 수 있다. 공개 마감은 2026-10-31.")
    for k, msg in (("ambiguous", "동명이인이 여럿이라 자동 판단을 보류"),
                   ("matched_loose", "기관명이 부분일치라 확인 필요"),
                   ("term_only", "기관명 불일치, 임기개시일 기준 1건이라 채택"),
                   ("no_term_row", "이름은 있으나 임기개시일 기준 건이 없음")):
        if stat.get(k):
            print(f"※ {k} {stat[k]:,}건 — {msg}. index.json 의 candidates_found 확인할 것.")


if __name__ == "__main__":
    main()
