#!/usr/bin/env python3
"""
선관위 사전투표 현황 OpenAPI 호출 스크립트
9회 전국동시지방선거(2026.6.3) 사전투표(5.29~5.30) 데이터를 일자별로 받아 저장.

특징:
    - sgTypecode 불필요 (사전투표는 선거 종류 무관 합산).
    - 일차(erVotingDiv): 1=1일차(5/29), 2=2일차(5/30). 누계는 클라이언트에서 합산.
    - 응답은 시도×시군구 단위 한 행씩 (전국 ~226개 시군구).
    - 사전투표 시작 전엔 빈 응답(ERROR-03 또는 totalCount=0)이 정상 → 스냅샷 미저장.

사용:
    export NEC_API_KEY=...
    python scripts/fetch_early_voting.py

산출물:
    data/early_voting/<sgId>/snapshot_YYYYMMDD.json
    형식: {sgId, fetched_at, rows: [{erVotingDiv, sdName, wiwName, votersCnt, erVotingCnt, erTurnout}, ...]}
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

BASE_URL = "http://apis.data.go.kr/9760000/ErVotingSttusInfoInqireService"
OPERATION = "getErVotingSttusInfoInqire"
API_KEY = os.environ.get("NEC_API_KEY", "").strip()
TARGET_SG_ID = "20260603"
KST = timezone(timedelta(hours=9))
def now_kst() -> datetime: return datetime.now(KST)

ROOT_DIR = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT_DIR / "data" / "early_voting" / TARGET_SG_ID

# 1일차·2일차만 호출. 누계가 필요하면 div=0을 추가하면 되지만,
# 합산은 클라이언트에서 row 단위로 더해도 충분히 정확.
VOTING_DIVS = (1, 2)

# 필드 정규화: API에서 문자열로 오는 숫자들을 int로 변환.
NUMERIC_FIELDS = ("votersCnt", "erVotingCnt")
FLOAT_FIELDS = ("erTurnout",)


def fetch_pages(params: dict, max_pages: int = 20) -> list[dict]:
    items: list[dict] = []
    page = 1
    while page <= max_pages:
        query = {
            **params,
            "serviceKey": API_KEY,
            "pageNo": page,
            "numOfRows": 500,
            "resultType": "json",
        }
        url = f"{BASE_URL}/{OPERATION}"

        try:
            res = requests.get(url, params=query, timeout=30)
            res.raise_for_status()
        except requests.RequestException as e:
            print(f"      요청 실패: {e}", file=sys.stderr)
            return items

        if "<OpenAPI_ServiceResponse>" in res.text:
            sys.exit(f"\n포털 에러:\n{res.text}")

        try:
            data = res.json()
        except ValueError:
            print(f"      JSON 파싱 실패: {res.text[:200]}", file=sys.stderr)
            return items

        resp = data.get("response", {})
        header = resp.get("header", {})
        code = header.get("resultCode", "")

        # ERROR-03: 데이터 없음 (사전투표 시작 전 정상 케이스).
        if code in ("ERROR-03",):
            return items

        if code not in ("INFO-00", "00"):
            print(f"      결과 에러: {header}", file=sys.stderr)
            return items

        body = resp.get("body", {})
        wrapper = body.get("items", {})
        if isinstance(wrapper, dict):
            chunk = wrapper.get("item", [])
        else:
            chunk = wrapper or []
        if isinstance(chunk, dict):
            chunk = [chunk]

        items.extend(chunk)

        total = int(body.get("totalCount", 0) or 0)
        if total == 0 or len(items) >= total:
            break

        page += 1
        time.sleep(0.3)
    return items


def normalize(row: dict, voting_div: int) -> dict:
    out = {"erVotingDiv": voting_div}
    for k, v in row.items():
        if k in NUMERIC_FIELDS:
            try:
                out[k] = int(str(v).replace(",", ""))
            except (TypeError, ValueError):
                out[k] = v
        elif k in FLOAT_FIELDS:
            try:
                out[k] = float(str(v).replace("%", ""))
            except (TypeError, ValueError):
                out[k] = v
        else:
            out[k] = v
    return out


def main() -> None:
    if not API_KEY:
        sys.exit("환경변수 NEC_API_KEY가 설정되지 않았습니다.")

    print("=" * 60)
    print(f"사전투표 현황 수집 (sgId={TARGET_SG_ID})")
    print("=" * 60)

    started_at = now_kst()
    all_rows: list[dict] = []
    call_count = 0

    for div in VOTING_DIVS:
        print(f"[erVotingDiv={div}] {div}일차")
        rows = fetch_pages({"sgId": TARGET_SG_ID, "erVotingDiv": div})
        call_count += 1
        print(f"  → {len(rows)}건")
        all_rows.extend(normalize(r, div) for r in rows)
        time.sleep(0.2)

    if not all_rows:
        elapsed = (now_kst() - started_at).total_seconds()
        print()
        print("=" * 60)
        print("사전투표 데이터가 아직 없습니다 (사전투표 시작 전 또는 미공개).")
        print(f"  - API 호출: {call_count}회, 소요: {elapsed:.1f}초")
        print("  - 스냅샷은 저장하지 않습니다.")
        print("=" * 60)
        return

    today = now_kst().strftime("%Y%m%d")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_file = OUT_DIR / f"snapshot_{today}.json"

    snapshot = {
        "sgId": TARGET_SG_ID,
        "fetched_at": started_at.isoformat(timespec="seconds"),
        "total_api_calls": call_count,
        "total_rows": len(all_rows),
        "rows": all_rows,
    }

    out_file.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    elapsed = (now_kst() - started_at).total_seconds()
    print()
    print("=" * 60)
    print("수집 완료")
    print(f"  - 행 수: {len(all_rows):,}")
    print(f"  - API 호출: {call_count}회")
    print(f"  - 소요: {elapsed:.1f}초")
    print(f"  - 저장 위치: {out_file.relative_to(ROOT_DIR)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
