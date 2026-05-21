#!/usr/bin/env python3
"""
선관위 투개표 OpenAPI (VoteXmntckInfoInqireService2/getXmntckSttusInfoInqire) 응답 정찰.

6/3 본투표 당일 OpenAPI가 실제로 어떤 응답을 주는지 확인하기 위한 일회성 스크립트.
6/3 이전에는 ERROR-03(데이터 없음)이 정상 응답이며, 그 자체가 첫 검증 지점이다.

원응답은 docs/live_counting/samples/ 아래에 그대로 저장하고, 표준출력에는
개표 진행도와 후보 키 후보를 진단해서 출력한다.

사용:
    # 6/3 시점 OpenAPI에 실제로 데이터가 없는지 1차 확인
    python scripts/probe_openapi_counting.py

    # 2022년 8회 지선 데이터로 응답 스키마 확인 (이쪽은 실데이터가 들어 있음)
    python scripts/probe_openapi_counting.py --sg-id 20220601

    # 다른 선거 종류 / 시도
    python scripts/probe_openapi_counting.py --sg-type 4 --sd-name 경기도
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

BASE_URL = "https://apis.data.go.kr/9760000/VoteXmntckInfoInqireService2"
OPERATION = "getXmntckSttusInfoInqire"
API_KEY = os.environ.get("NEC_API_KEY", "").strip()

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
SAMPLE_DIR = ROOT / "docs" / "live_counting" / "samples"

DEFAULT_SG_ID = "20260603"
DEFAULT_SG_TYPE = "3"
DEFAULT_SD = "서울특별시"

# 응답 키 중 개표 진행도 / 후보·득표 관련일 가능성이 있는 키워드.
PROGRESS_HINTS = (
    "gae", "gaepyo", "gpv", "progress", "rate", "ratio", "pct", "percent",
    "tusu", "sunsu", "yutusu", "complete", "finish", "status",
)
CANDIDATE_HINTS = ("hbj", "hubo", "jd", "dugsu", "votes", "party", "name")


def call(sg_id: str, sg_type: str, sd_name: str) -> dict:
    params = {
        "ServiceKey": API_KEY,
        "sgId": sg_id,
        "sgTypecode": sg_type,
        "sdName": sd_name,
        "pageNo": 1,
        "numOfRows": 5,
        "resultType": "json",
    }
    # 시도지사(3)는 기존 fetch_past_counting_results.py와 동일 규약: sggName도 시도명을 넣어야 매칭됨.
    if sg_type == "3":
        params["sggName"] = sd_name
    res = requests.get(f"{BASE_URL}/{OPERATION}", params=params, timeout=30)
    res.raise_for_status()
    return res.json()


def diagnose(payload: dict) -> None:
    resp = payload.get("response", {})
    header = resp.get("header", {})
    code = header.get("resultCode", "?")
    msg = header.get("resultMsg", "")
    body = resp.get("body", {}) or {}
    total = int(body.get("totalCount", 0) or 0)

    print(f"  resultCode = {code}  ({msg})")
    print(f"  totalCount = {total}")

    if code in ("INFO-03", "ERROR-03"):
        print("  → 데이터 없음. 6/3 이전엔 정상 응답.")
        return
    if code not in ("INFO-00", "00"):
        print("  → 알 수 없는 응답 코드. 스키마 변경 가능성.")
        return

    wrapper = body.get("items", {})
    item = wrapper.get("item", []) if isinstance(wrapper, dict) else wrapper
    if isinstance(item, dict):
        item = [item]
    item = item or []
    print(f"  rows       = {len(item)}")

    if not item:
        print("  → totalCount는 있는데 row가 비었음. 페이징 또는 응답 형식 확인 필요.")
        return

    first = item[0]
    all_keys = sorted(first.keys())
    print(f"\n  첫 행의 키 ({len(all_keys)}개):")
    print("    " + ", ".join(all_keys))

    wiw_names = sorted({(r.get("wiwName") or "").strip() for r in item})
    print(f"\n  wiwName 분포: {wiw_names}")

    progress_keys = [k for k in all_keys if any(h in k.lower() for h in PROGRESS_HINTS)]
    cand_keys = [k for k in all_keys if any(h in k.lower() for h in CANDIDATE_HINTS)]
    print(f"\n  개표 진행도 관련 후보 키: {progress_keys}")
    print(f"  후보·정당·득표 관련 키:    {cand_keys[:20]}{' …' if len(cand_keys) > 20 else ''}")


def main() -> None:
    parser = argparse.ArgumentParser(description="VoteXmntckInfoInqireService2 응답 정찰")
    parser.add_argument("--sg-id", default=DEFAULT_SG_ID, help="기본 20260603. 과거 데이터 테스트 시 20220601 등")
    parser.add_argument("--sg-type", default=DEFAULT_SG_TYPE, help="기본 3(시도지사)")
    parser.add_argument("--sd-name", default=DEFAULT_SD, help="기본 서울특별시")
    args = parser.parse_args()

    if not API_KEY:
        sys.exit("환경변수 NEC_API_KEY가 설정되지 않았습니다.")

    print("=" * 60)
    print(f"VoteXmntckInfoInqireService2/{OPERATION} 정찰")
    print(f"  sgId={args.sg_id}  sgTypecode={args.sg_type}  sdName={args.sd_name}")
    print("=" * 60)

    payload = call(args.sg_id, args.sg_type, args.sd_name)
    diagnose(payload)

    SAMPLE_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(KST).strftime("%Y%m%d_%H%M%S")
    out = SAMPLE_DIR / f"openapi_{args.sg_id}_{args.sg_type}_{args.sd_name}_{ts}.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n원응답 저장: {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
