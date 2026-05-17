#!/usr/bin/env python3
"""
선관위 투개표 OpenAPI에서 역대 지방선거 개표 결과를 수집한다.

기본값은 지난 선거 페이지에 바로 쓰기 좋은 광역단체장(sgTypecode=3)
시도별 합계 결과다. 필요하면 --sg-type을 여러 번 넘겨 기초단체장,
지방의원, 비례대표 결과도 같은 구조로 받을 수 있다.

사용:
    set NEC_API_KEY=...
    python scripts/fetch_past_counting_results.py
    python scripts/fetch_past_counting_results.py --sg-type 3 --sg-type 4

산출물:
    data/history_counting_results.json
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import requests

BASE_URL = "https://apis.data.go.kr/9760000/VoteXmntckInfoInqireService2"
OPERATION = "getXmntckSttusInfoInqire"
API_KEY = os.environ.get("NEC_API_KEY", "").strip()

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "history_counting_results.json"
KST = timezone(timedelta(hours=9))

ELECTIONS = [
    {"round": 3, "year": 2002, "date": "2002-06-13", "sgId": "20020613"},
    {"round": 4, "year": 2006, "date": "2006-05-31", "sgId": "20060531"},
    {"round": 5, "year": 2010, "date": "2010-06-02", "sgId": "20100602"},
    {"round": 6, "year": 2014, "date": "2014-06-04", "sgId": "20140604"},
    {"round": 7, "year": 2018, "date": "2018-06-13", "sgId": "20180613"},
    {"round": 8, "year": 2022, "date": "2022-06-01", "sgId": "20220601"},
]

SGLABELS = {
    "3": "시도지사",
    "4": "구시군장",
    "5": "시도의원",
    "6": "구시군의회의원",
    "8": "광역의원비례대표",
    "9": "기초의원비례대표",
}

SIDOS = [
    "서울특별시",
    "부산광역시",
    "대구광역시",
    "인천광역시",
    "광주광역시",
    "대전광역시",
    "울산광역시",
    "세종특별자치시",
    "경기도",
    "강원도",
    "충청북도",
    "충청남도",
    "전라북도",
    "전라남도",
    "경상북도",
    "경상남도",
    "제주도",
    "제주특별자치도",
]


def to_int(value: Any) -> int:
    if value in (None, "", "null"):
        return 0
    return int(str(value).replace(",", "").strip() or 0)


def fetch_pages(params: dict[str, Any], max_pages: int = 200) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    page = 1
    while page <= max_pages:
        query = {
            **params,
            "ServiceKey": API_KEY,
            "pageNo": page,
            "numOfRows": 200,
            "resultType": "json",
        }
        res = requests.get(f"{BASE_URL}/{OPERATION}", params=query, timeout=30)
        res.raise_for_status()
        payload = res.json()
        header = payload.get("response", {}).get("header", {})
        if header.get("resultCode") in ("INFO-03", "ERROR-03"):
            return []
        if header.get("resultCode") not in ("INFO-00", "00"):
            raise RuntimeError(f"API error: {header}")

        body = payload.get("response", {}).get("body", {})
        wrapper = body.get("items", {})
        chunk = wrapper.get("item", []) if isinstance(wrapper, dict) else wrapper
        if isinstance(chunk, dict):
            chunk = [chunk]
        chunk = chunk or []
        rows.extend(chunk)

        total = int(body.get("totalCount", 0) or 0)
        if total == 0 or len(rows) >= total:
            break
        page += 1
        time.sleep(0.2)
    return rows


def extract_candidates(row: dict[str, Any]) -> list[dict[str, Any]]:
    candidates: list[dict[str, Any]] = []
    valid_votes = to_int(row.get("yutusu"))
    for idx in range(1, 51):
        suffix = f"{idx:02d}"
        party = (row.get(f"jd{suffix}") or "").strip()
        name = (row.get(f"hbj{suffix}") or "").strip()
        votes = to_int(row.get(f"dugsu{suffix}"))
        if not party and not name and votes == 0:
            continue
        share = round((votes / valid_votes) * 100, 2) if valid_votes else None
        candidates.append({
            "slot": idx,
            "party": party,
            "name": name,
            "votes": votes,
            "vote_share": share,
        })
    return candidates


def normalize_row(row: dict[str, Any]) -> dict[str, Any]:
    candidates = extract_candidates(row)
    winner = max(candidates, key=lambda c: c["votes"]) if candidates else None
    return {
        "sgId": row.get("sgId"),
        "sgTypecode": str(row.get("sgTypecode", "")),
        "sggName": row.get("sggName", ""),
        "sdName": row.get("sdName", ""),
        "wiwName": row.get("wiwName", ""),
        "eligible_voters": to_int(row.get("sunsu")),
        "turnout_votes": to_int(row.get("tusu")),
        "valid_votes": to_int(row.get("yutusu")),
        "invalid_votes": to_int(row.get("mutusu")),
        "abstentions": to_int(row.get("gigwonsu")),
        "winner": winner,
        "candidates": candidates,
    }


def district_total_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """읍면동 세부행을 제외하고 선거구 합계행만 남긴다."""
    totals = [r for r in rows if (r.get("wiwName") or "").strip() == "합계"]
    return totals or rows


def build_party_summary(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts: dict[str, int] = {}
    for row in rows:
        winner = row.get("winner") or {}
        party = winner.get("party") or "기타"
        counts[party] = counts.get(party, 0) + 1
    return [
        {"party": party, "wins": wins}
        for party, wins in sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    ]


def fetch_election_type(sg_id: str, sg_type: str) -> list[dict[str, Any]]:
    all_rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str, str]] = set()
    for sido in SIDOS:
        params: dict[str, Any] = {
            "sgId": sg_id,
            "sgTypecode": sg_type,
            "sdName": sido,
        }
        if sg_type == "3":
            params["sggName"] = sido
        rows = fetch_pages(params)
        total_rows = district_total_rows(rows)
        for row in total_rows:
            normalized = normalize_row(row)
            key = (
                normalized["sgTypecode"],
                normalized["sdName"],
                normalized["sggName"],
                normalized["wiwName"],
            )
            if key in seen:
                continue
            seen.add(key)
            all_rows.append(normalized)
        time.sleep(0.1)
    return all_rows


def main() -> None:
    if not API_KEY:
        sys.exit("환경변수 NEC_API_KEY가 설정되지 않았습니다.")

    parser = argparse.ArgumentParser()
    parser.add_argument("--sg-type", action="append", default=None, help="선거종류 코드. 기본값 3(시도지사)")
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()

    sg_types = [str(x) for x in (args.sg_type or ["3"])]
    elections = []
    print("역대 지방선거 개표 결과 수집")
    print(f"선거종류: {', '.join(SGLABELS.get(x, x) for x in sg_types)}")

    for election in ELECTIONS:
        by_type = []
        print(f"\n{election['round']}회 {election['year']} ({election['sgId']})")
        for sg_type in sg_types:
            rows = fetch_election_type(election["sgId"], sg_type)
            print(f"  {SGLABELS.get(sg_type, sg_type)}: {len(rows):,}개 선거구")
            by_type.append({
                "sgTypecode": sg_type,
                "office": SGLABELS.get(sg_type, sg_type),
                "district_count": len(rows),
                "party_wins": build_party_summary(rows),
                "districts": rows,
            })
        elections.append({**election, "results": by_type})

    payload = {
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "source": "중앙선거관리위원회 OpenAPI · VoteXmntckInfoInqireService2/getXmntckSttusInfoInqire",
        "note": "읍면동 세부행은 제외하고 선거구 합계행 기준으로 정리.",
        "elections": elections,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장: {args.out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
