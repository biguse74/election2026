#!/usr/bin/env python3
"""
역대 부산 북구갑 국회의원 선거 개표 결과를 CSV로 추출.

선거구명 변천:
  · 22대 (2024): 북갑          ← 북·강서를 분리하면서 명칭 변경
  · 17~21대 (2004~2020): 북강서갑
  · 16대 이전은 명칭이 또 다름 — 일단 17~22대만 수집

회차마다 가능한 sggName 후보를 차례로 시도하고 응답 있는 첫 값을 채택.
결과: exports/busan_buk_gap_history.csv

사용:
    $env:NEC_API_KEY = '<발급키>'
    python scripts/export_busan_buk_gap.py
"""

from __future__ import annotations

import csv
import os
import sys
import time
from pathlib import Path

import requests

API_KEY = os.environ.get("NEC_API_KEY", "").strip()
BASE_URL = "https://apis.data.go.kr/9760000/VoteXmntckInfoInqireService2/getXmntckSttusInfoInqire"
SG_TYPE = "2"  # 지역구 국회의원

# OpenAPI는 점·구분자 없이 구를 이어붙인다 ("중구영도구", "서구동구").
# 22대: "북갑" / 21~17대: "북강서갑" 형식으로 추정되지만 정확한 표기는
# 응답에서 자동 탐색 — '북' 포함 + '갑' 포함 sggName을 채택.
ELECTIONS = [
    (22, 2024, "20240410"),
    (21, 2020, "20200415"),
    (20, 2016, "20160413"),
    (19, 2012, "20120411"),
    (18, 2008, "20080409"),
    (17, 2004, "20040415"),
]
SD_NAME = "부산광역시"

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "exports" / "busan_buk_gap_history.csv"


def call(sg_id: str, sgg: str | None = None) -> list[dict]:
    """(sgId, [sggName]) 호출. sggName 미지정 시 시도 전체. 응답 row 리스트."""
    items: list[dict] = []
    page = 1
    while page <= 10:
        params = {
            "ServiceKey": API_KEY,
            "sgId": sg_id,
            "sgTypecode": SG_TYPE,
            "sdName": SD_NAME,
            "pageNo": page,
            "numOfRows": 100,
            "resultType": "json",
        }
        if sgg:
            params["sggName"] = sgg
        r = requests.get(BASE_URL, params=params, timeout=30)
        r.raise_for_status()
        payload = r.json()
        header = payload.get("response", {}).get("header", {})
        code = header.get("resultCode")
        if code in ("INFO-03", "ERROR-03"):
            return []
        if code not in ("INFO-00", "00"):
            print(f"  ! sgId={sg_id} sgg={sgg} resultCode={code} msg={header.get('resultMsg')}", file=sys.stderr)
            return []
        body = payload.get("response", {}).get("body", {}) or {}
        wrap = body.get("items", {})
        chunk = wrap.get("item", []) if isinstance(wrap, dict) else wrap
        if isinstance(chunk, dict):
            chunk = [chunk]
        items.extend(chunk or [])
        total = int(body.get("totalCount", 0) or 0)
        if total == 0 or len(items) >= total:
            break
        page += 1
        time.sleep(0.2)
    return items


def discover_buk_gap_sgg(sg_id: str) -> str | None:
    """sd=부산광역시 응답에서 '북' 포함 + '갑' 포함 sggName을 자동 탐색."""
    rows = call(sg_id, sgg=None)
    candidates = set()
    for r in rows:
        sgg = (r.get("sggName") or "").strip()
        if "북" in sgg and "갑" in sgg:
            candidates.add(sgg)
    if not candidates:
        return None
    # 여러 개 매칭되면 가장 짧은(=가장 단순한) 명칭 우선 — "북갑" > "북강서갑"
    return sorted(candidates, key=len)[0]


def to_int(v):
    if v in (None, "", "null"):
        return 0
    try:
        return int(str(v).replace(",", "").strip() or 0)
    except ValueError:
        return 0


def extract_candidates(row: dict) -> list[dict]:
    valid = to_int(row.get("yutusu"))
    out = []
    for i in range(1, 51):
        s = f"{i:02d}"
        name = (row.get(f"hbj{s}") or "").strip()
        party = (row.get(f"jd{s}") or "").strip()
        votes = to_int(row.get(f"dugsu{s}"))
        if not name and not party and votes == 0:
            continue
        share = round(votes / valid * 100, 2) if valid else None
        out.append({"slot": i, "name": name, "party": party, "votes": votes, "share": share})
    out.sort(key=lambda c: c["votes"], reverse=True)
    for idx, c in enumerate(out, 1):
        c["rank"] = idx
    return out


def main():
    if not API_KEY:
        sys.exit("환경변수 NEC_API_KEY가 설정되지 않았습니다.")

    rows_out: list[dict] = []

    for round_, year, sg_id in ELECTIONS:
        chosen_sgg = discover_buk_gap_sgg(sg_id)
        if not chosen_sgg:
            print(f"  · {round_}대 ({year}) — '북' + '갑' 매칭 sggName 없음 (선거구 명칭 변경 또는 데이터 부재)")
            continue
        # 해당 선거구만 다시 정밀 호출 (이미 위 응답에 있지만 wiwName='합계'만 정확히 골라내기)
        items = call(sg_id, sgg=chosen_sgg)
        rows = [r for r in items if (r.get("wiwName") or "").strip() in ("", "합계")]
        if not rows:
            print(f"  · {round_}대 ({year}) [{chosen_sgg}] — 합계행 없음")
            continue

        for row in rows:
            cands = extract_candidates(row)
            winner = cands[0] if cands else None
            for c in cands:
                rows_out.append({
                    "round": round_,
                    "year": year,
                    "election_date": f"{sg_id[:4]}-{sg_id[4:6]}-{sg_id[6:]}",
                    "sg_id": sg_id,
                    "sd_name": SD_NAME,
                    "sgg_name": chosen_sgg,
                    "rank": c["rank"],
                    "name": c["name"],
                    "party": c["party"],
                    "votes": c["votes"],
                    "vote_share_pct": c["share"],
                    "is_winner": "Y" if winner and c is winner else "",
                    "eligible_voters": to_int(row.get("sunsu")),
                    "valid_votes": to_int(row.get("yutusu")),
                    "invalid_votes": to_int(row.get("mutusu")),
                })
        print(f"  · {round_}대 ({year}) [{chosen_sgg}] — 후보 {len(cands)}명, 당선 {winner['name'] if winner else '?'} ({winner['party'] if winner else ''}) {winner['share']}%" if winner else f"  · {round_}대 ({year}) [{chosen_sgg}] — 데이터 있음")

    if not rows_out:
        sys.exit("어느 회차에서도 데이터를 받지 못했습니다.")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    fieldnames = list(rows_out[0].keys())
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows_out)
    print(f"\n저장: {OUT.relative_to(ROOT)}  ({len(rows_out)}행)")


if __name__ == "__main__":
    main()
