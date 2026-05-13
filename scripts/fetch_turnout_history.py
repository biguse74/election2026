#!/usr/bin/env python3
"""
역대 지방선거(3~8회) 시도별 투표율을 선관위 OpenAPI에서 받아
data/history_turnout.json에 정리한다.

호출: VoteXmntckInfoInqireService2 / getVoteSttusInfoInqire
파라미터: sgId, sgTypecode=3 (시도지사 단위로 가져옴 — 전체 선거 투표율과 동일)

선관위 OpenAPI는 1·2회 지방선거(1995, 1998) 미제공. 그 두 회차는
data/history.json의 정적 입력값을 유지한다.

산출물: data/history_turnout.json
  { generated_at, elections: [
      { round, year, sgId, total: {sunsu, tusu, rate},
        by_sido: [{ sdName, sunsu, tusu, rate }] }, ...
    ] }
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

BASE_URL = "http://apis.data.go.kr/9760000/VoteXmntckInfoInqireService2"
OPERATION = "getVoteSttusInfoInqire"
API_KEY = os.environ.get("NEC_API_KEY", "").strip()

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "history_turnout.json"
KST = timezone(timedelta(hours=9))

# 회차별 sgId (광역단체장 투표 = 지방선거 본투표율과 동일)
ELECTIONS = [
    (3, 2002, "20020613"),
    (4, 2006, "20060531"),
    (5, 2010, "20100602"),
    (6, 2014, "20140604"),
    (7, 2018, "20180613"),
    (8, 2022, "20220601"),
]


def fetch_pages(sg_id: str, max_pages: int = 20) -> list[dict]:
    items: list[dict] = []
    page = 1
    while page <= max_pages:
        query = {
            "serviceKey": API_KEY,
            "sgId": sg_id,
            "sgTypecode": 3,           # 시도지사 — 광역단체장 투표가 곧 지방선거 본투표율
            "pageNo": page,
            "numOfRows": 200,
            "resultType": "json",
        }
        url = f"{BASE_URL}/{OPERATION}"
        try:
            res = requests.get(url, params=query, timeout=30)
            res.raise_for_status()
        except requests.RequestException as e:
            print(f"  요청 실패: {e}", file=sys.stderr)
            return items
        if "<OpenAPI_ServiceResponse>" in res.text:
            sys.exit(f"\n포털 에러:\n{res.text}")
        try:
            data = res.json()
        except ValueError:
            print(f"  JSON 파싱 실패: {res.text[:200]}", file=sys.stderr)
            return items
        resp = data.get("response", {})
        header = resp.get("header", {})
        code = header.get("resultCode", "")
        if code in ("ERROR-03",):
            return items
        if code not in ("INFO-00", "00"):
            print(f"  결과 에러 sgId={sg_id}: {header}", file=sys.stderr)
            return items
        body = resp.get("body", {})
        wrapper = body.get("items", {})
        chunk = wrapper.get("item", []) if isinstance(wrapper, dict) else (wrapper or [])
        if isinstance(chunk, dict):
            chunk = [chunk]
        items.extend(chunk)
        total = int(body.get("totalCount", 0) or 0)
        if total == 0 or len(items) >= total:
            break
        page += 1
        time.sleep(0.3)
    return items


def to_num(v):
    """API가 쉼표·% 섞어 문자열로 보내는 숫자를 정수/실수로 변환."""
    if v is None:
        return None
    s = str(v).replace(",", "").replace("%", "").strip()
    if not s:
        return None
    try:
        f = float(s)
        return int(f) if f.is_integer() else round(f, 3)
    except ValueError:
        return None


def extract_total_and_sido(items: list[dict]) -> tuple[dict | None, list[dict]]:
    """API 응답에서 '합계' 행과 시도별 행을 분리.

    선관위 응답은 보통 sdName 안에 '합계'/'계' 같은 값을 한 행으로 함께 반환.
    그 행을 total로, 나머지를 시도별로 분리한다. 필드명은 회차마다 약간 다를 수
    있어 여러 후보를 시도한다.
    """
    def pick(d, *keys):
        for k in keys:
            if k in d and d[k] not in (None, "", "null"):
                return d[k]
        return None

    total_row = None
    sido_rows = []
    for it in items:
        sd = (pick(it, "sdName", "sgg_NAME", "siDoNm") or "").strip()
        if sd in ("합계", "계", "전국", ""):
            total_row = it
        else:
            sido_rows.append(it)

    def normalize(row):
        if not row:
            return None
        return {
            "sdName": (pick(row, "sdName", "siDoNm") or "").strip() or None,
            "sunsu": to_num(pick(row, "totSunsu", "tot_Sunsu", "elcGrpe", "elcCnt")),
            "tusu":  to_num(pick(row, "totTusu", "tot_Tusu", "votCnt", "votngCnt")),
            "rate":  to_num(pick(row, "Turnout", "turnout", "votRate", "votngRate")),
        }

    return normalize(total_row), [normalize(r) for r in sido_rows if r]


def main() -> None:
    if not API_KEY:
        sys.exit("환경변수 NEC_API_KEY가 설정되지 않았습니다.")

    print("=" * 60)
    print("역대 지방선거 투표율 수집")
    print("=" * 60)

    results = []
    for round_, year, sg_id in ELECTIONS:
        print(f"\n[{round_}회 {year} · sgId={sg_id}]")
        items = fetch_pages(sg_id)
        if not items:
            print("  데이터 없음(스킵)")
            continue
        total, by_sido = extract_total_and_sido(items)
        print(f"  rows={len(items)} · 전국 투표율 {total.get('rate') if total else 'N/A'}% · 시도 {len(by_sido)}개")
        results.append({
            "round": round_,
            "year": year,
            "sgId": sg_id,
            "total": total,
            "by_sido": by_sido,
        })
        time.sleep(0.3)

    payload = {
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "source": "중앙선거관리위원회 OpenAPI · VoteXmntckInfoInqireService2/getVoteSttusInfoInqire",
        "note": "광역단체장(sgTypecode=3) 투표 기준 시도별 투표율. 1·2회는 OpenAPI 미제공.",
        "elections": results,
    }

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장: {OUT.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
