#!/usr/bin/env python3
"""
선관위 사전투표 현황 OpenAPI 호출 스크립트
9회 전국동시지방선거(2026.6.3) 사전투표(5.29~5.30) 데이터를 수집 시점별로 받아 저장.

저장 구조:
    data/early_voting/<sgId>/
      ├── snapshots/snapshot_YYYYMMDD_HHMM.json   # 수집 시점별 raw 스냅샷
      ├── timeseries.json                         # 프론트용 시계열 (시도 누적)
      └── latest.json                             # 최신 1건 (띠배너용)

특징:
    - sgTypecode 불필요 (사전투표는 선거 종류 무관 합산).
    - erVotingDiv: 1=1일차(5/29), 2=2일차(5/30). 양일을 한 번에 합산.
    - 응답은 시도×시군구 단위 한 행씩 (전국 ~226개 시군구).
    - 사전투표 시작 전엔 빈 응답(ERROR-03 또는 totalCount=0) → 스냅샷 미저장.
    - 수집 시점별 파일로 시계열 보존. timeseries.json은 시도 단위로 집계해
      프론트가 가볍게 읽도록 함.

사용:
    export NEC_API_KEY=...
    python scripts/fetch_early_voting.py

산출물:
    snapshot 형식: {sgId, fetched_at, rows: [...]}
    timeseries 형식: {sgId, updated_at, snapshots: [{at, by_sido, national}, ...]}
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

BASE_URL = "http://apis.data.go.kr/9760000/ErVotingSttusInfoInqireService"
OPERATION = "getErVotingSttusInfoInqire"
API_KEY = os.environ.get("NEC_API_KEY", "").strip()
TARGET_SG_ID = "20260603"
KST = timezone(timedelta(hours=9))


def now_kst() -> datetime:
    return datetime.now(KST)


ROOT_DIR = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT_DIR / "data" / "early_voting" / TARGET_SG_ID
SNAPSHOT_DIR = OUT_DIR / "snapshots"
TIMESERIES_PATH = OUT_DIR / "timeseries.json"
LATEST_PATH = OUT_DIR / "latest.json"

# 1일차·2일차 동시 조회. 누계가 필요하면 div=0도 있지만,
# 합산은 클라이언트에서 row 단위로 더해도 정확.
VOTING_DIVS = (1, 2)

NUMERIC_FIELDS = ("votersCnt", "erVotingCnt")
FLOAT_FIELDS = ("erTurnout",)

# 시도 표준 명칭 매핑 (API는 구 명칭으로 반환할 수 있음 — 일관 보정).
SIDO_ALIAS = {
    "강원도": "강원특별자치도",
    "전라북도": "전북특별자치도",
}


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
    if "sdName" in out:
        out["sdName"] = SIDO_ALIAS.get(out["sdName"], out["sdName"])
    return out


def aggregate_by_sido(rows: list[dict]) -> tuple[list[dict], dict]:
    """양일(1+2) 누적으로 시도 단위 합산. national도 함께 반환."""
    # 핵심: 같은 시군구에 1일차+2일차 row가 둘 다 있음. 둘을 합산.
    # 단, votersCnt(선거인수)는 양일이 동일하므로 max로 받음.
    by_sido_voted: dict[str, int] = defaultdict(int)
    by_sido_voters: dict[str, int] = {}

    for r in rows:
        sd = r.get("sdName")
        if not sd:
            continue
        voted = r.get("erVotingCnt") or 0
        voters = r.get("votersCnt") or 0
        if isinstance(voted, (int, float)):
            by_sido_voted[sd] += int(voted)
        # 선거인수: 시군구별 max (1일차와 2일차가 같지만 안전하게 max).
        # 단 양일 row를 둘 다 더하면 2배가 되므로, (sd, wiwName, div) 기준 dedup 필요.
        # 여기선 (sd, wiwName) 단위로 가장 큰 voters를 한 번만 누적.

    # 정확한 voters 계산: (sd, wiwName) 기준 dedup → 시도별 합산
    voters_by_key: dict[tuple[str, str], int] = {}
    for r in rows:
        sd = r.get("sdName")
        wiw = r.get("wiwName") or r.get("sggName") or ""
        if not sd:
            continue
        voters = r.get("votersCnt") or 0
        if isinstance(voters, (int, float)):
            key = (sd, wiw)
            voters_by_key[key] = max(voters_by_key.get(key, 0), int(voters))

    by_sido_voters_sum: dict[str, int] = defaultdict(int)
    for (sd, _wiw), v in voters_by_key.items():
        by_sido_voters_sum[sd] += v

    by_sido = []
    for sd in sorted(set(by_sido_voted) | set(by_sido_voters_sum)):
        voted = by_sido_voted.get(sd, 0)
        voters = by_sido_voters_sum.get(sd, 0)
        turnout = (voted / voters * 100.0) if voters else 0.0
        by_sido.append({
            "sdName": sd,
            "voters": voters,
            "voted": voted,
            "turnout": round(turnout, 2),
        })

    total_voted = sum(s["voted"] for s in by_sido)
    total_voters = sum(s["voters"] for s in by_sido)
    national = {
        "voters": total_voters,
        "voted": total_voted,
        "turnout": round(total_voted / total_voters * 100.0, 2) if total_voters else 0.0,
    }
    return by_sido, national


def load_timeseries() -> dict:
    if TIMESERIES_PATH.exists():
        try:
            return json.loads(TIMESERIES_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            print(f"  ⚠ timeseries.json 파싱 실패 → 새로 생성", file=sys.stderr)
    return {
        "sgId": TARGET_SG_ID,
        "snapshots": [],
    }


def append_timeseries(ts: dict, at: datetime, by_sido: list[dict], national: dict) -> bool:
    """이미 같은 분(分) 스냅샷이 있으면 skip. 새로 추가했으면 True."""
    at_key = at.strftime("%Y-%m-%dT%H:%M")
    for s in ts.get("snapshots", []):
        if s.get("at", "").startswith(at_key):
            return False
    ts.setdefault("snapshots", []).append({
        "at": at.isoformat(timespec="seconds"),
        "by_sido": by_sido,
        "national": national,
    })
    ts["snapshots"].sort(key=lambda s: s["at"])
    ts["updated_at"] = at.isoformat(timespec="seconds")
    return True


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

    # 1) raw snapshot 저장 (HHMM 포함)
    SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = started_at.strftime("%Y%m%d_%H%M")
    snapshot_path = SNAPSHOT_DIR / f"snapshot_{stamp}.json"
    snapshot = {
        "sgId": TARGET_SG_ID,
        "fetched_at": started_at.isoformat(timespec="seconds"),
        "total_api_calls": call_count,
        "total_rows": len(all_rows),
        "rows": all_rows,
    }
    snapshot_path.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 2) 시도/전국 집계
    by_sido, national = aggregate_by_sido(all_rows)

    # 3) timeseries.json 누적
    ts = load_timeseries()
    appended = append_timeseries(ts, started_at, by_sido, national)
    TIMESERIES_PATH.write_text(
        json.dumps(ts, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 4) latest.json 갱신
    latest = {
        "sgId": TARGET_SG_ID,
        "fetched_at": started_at.isoformat(timespec="seconds"),
        "by_sido": by_sido,
        "national": national,
    }
    LATEST_PATH.write_text(
        json.dumps(latest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    elapsed = (now_kst() - started_at).total_seconds()
    print()
    print("=" * 60)
    print("수집 완료")
    print(f"  - row: {len(all_rows):,}건")
    print(f"  - 전국 누적: {national['voted']:,}/{national['voters']:,} ({national['turnout']}%)")
    print(f"  - 시도: {len(by_sido)}곳")
    print(f"  - timeseries 추가: {'yes' if appended else 'skip(중복)'}")
    print(f"  - API: {call_count}회, 소요 {elapsed:.1f}초")
    print(f"  - 저장: {snapshot_path.relative_to(ROOT_DIR)}")
    print(f"         {TIMESERIES_PATH.relative_to(ROOT_DIR)}")
    print(f"         {LATEST_PATH.relative_to(ROOT_DIR)}")
    print("=" * 60)


if __name__ == "__main__":
    main()
