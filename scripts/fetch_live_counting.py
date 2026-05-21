#!/usr/bin/env python3
"""
선관위 투개표 OpenAPI를 호출해 개표 누계를 모은다.

한 번 실행 = 한 번 폴링. cron 또는 GitHub Actions가 5분 간격으로 호출한다고 가정.

- VoteXmntckInfoInqireService2/getXmntckSttusInfoInqire 호출
- 6/3 이전에는 ERROR-03 / INFO-03(데이터 없음)이 정상 응답
- 응답이 비어 있어도 current.json과 meta.json은 갱신해서 프론트가 stale 여부를 판별 가능

산출물:
  data/live_counting/raw/openapi_<YYYYMMDD_HHMMSS>.json    # 한 폴링의 원응답 전부 (감사용)
  data/live_counting/current.json                           # 프론트가 읽는 가공본
  data/live_counting/meta.json                              # 폴링 텔레메트리

사용:
  python scripts/fetch_live_counting.py
  python scripts/fetch_live_counting.py --sg-id 20220601    # 8회 지선 데이터로 시뮬레이션
  python scripts/fetch_live_counting.py --dry-run           # 호출만 하고 저장 생략
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

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "live_counting"
RAW_DIR = OUT_DIR / "raw"

SG_LABELS = {
    "3": "시도지사",
    "4": "기초단체장",
    "11": "교육감",
}
DEFAULT_SG_TYPES = ["3", "4", "11"]

# 9회 지선 시도 표준명. 강원·전북·제주는 신명칭.
# 통합특별시(전남광주) 시도지사는 광주광역시·전라남도 두 호출 모두에서 동일 race로
# 반환되므로 race_key dedup으로 1건만 남는다.
SIDOS = [
    "서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시",
    "대전광역시", "울산광역시", "세종특별자치시", "경기도", "강원특별자치도",
    "충청북도", "충청남도", "전북특별자치도", "전라남도", "경상북도",
    "경상남도", "제주특별자치도",
]

ELECTION_DAY_KST = datetime(2026, 6, 3, 18, 0, tzinfo=KST)
DEFAULT_SG_ID = "20260603"


def to_int(v: Any) -> int:
    if v in (None, "", "null"):
        return 0
    try:
        return int(str(v).replace(",", "").strip() or 0)
    except ValueError:
        return 0


def call_one(sg_id: str, sg_type: str, sd_name: str) -> dict:
    """한 (sg_type, sd_name) 묶음 호출. 페이지 다 받아 items 합쳐 반환."""
    items: list[dict] = []
    page = 1
    result_code = "?"
    total_count = 0
    while page <= 50:
        params = {
            "ServiceKey": API_KEY,
            "sgId": sg_id,
            "sgTypecode": sg_type,
            "sdName": sd_name,
            "pageNo": page,
            "numOfRows": 200,
            "resultType": "json",
        }
        # 시도지사는 fetch_past_counting_results.py와 동일 규약: sggName도 시도명.
        if sg_type == "3":
            params["sggName"] = sd_name

        res = requests.get(f"{BASE_URL}/{OPERATION}", params=params, timeout=30)
        res.raise_for_status()
        payload = res.json()
        header = payload.get("response", {}).get("header", {})
        result_code = header.get("resultCode", "?")
        if result_code in ("INFO-03", "ERROR-03"):
            break
        if result_code not in ("INFO-00", "00"):
            raise RuntimeError(f"API error: {header}")

        body = payload.get("response", {}).get("body", {}) or {}
        wrapper = body.get("items", {})
        chunk = wrapper.get("item", []) if isinstance(wrapper, dict) else wrapper
        if isinstance(chunk, dict):
            chunk = [chunk]
        items.extend(chunk or [])

        total_count = int(body.get("totalCount", 0) or 0)
        if total_count == 0 or len(items) >= total_count:
            break
        page += 1
        time.sleep(0.2)

    return {
        "request": {"sg_id": sg_id, "sg_type": sg_type, "sd_name": sd_name},
        "result_code": result_code,
        "total_count": total_count,
        "items": items,
    }


def extract_candidates(row: dict) -> list[dict]:
    """hbj01~50 / jd01~50 / dugsu01~50 슬롯에서 후보 추출. 득표수 내림차순 정렬."""
    valid_votes = to_int(row.get("yutusu"))
    cands: list[dict] = []
    for i in range(1, 51):
        s = f"{i:02d}"
        name = (row.get(f"hbj{s}") or "").strip()
        party = (row.get(f"jd{s}") or "").strip()
        votes = to_int(row.get(f"dugsu{s}"))
        if not name and not party and votes == 0:
            continue
        share = round(votes / valid_votes * 100, 2) if valid_votes else None
        cands.append({"name": name, "jd_name": party, "votes": votes, "share_pct": share})
    cands.sort(key=lambda c: c["votes"], reverse=True)
    for idx, c in enumerate(cands, 1):
        c["current_rank"] = idx
    return cands


def race_key(row: dict) -> str:
    sg_type = str(row.get("sgTypecode", ""))
    sd = (row.get("sdName") or "").strip()
    sgg = (row.get("sggName") or "").strip()
    return "|".join(p for p in (sg_type, sd, sgg) if p)


def normalize_row(row: dict) -> dict:
    sg_type = str(row.get("sgTypecode", ""))
    candidates = extract_candidates(row)
    eligible = to_int(row.get("sunsu"))
    valid = to_int(row.get("yutusu"))
    invalid = to_int(row.get("mutusu"))
    counted = valid + invalid
    progress = round(counted / eligible * 100, 2) if eligible else None

    rank_diff = None
    if (
        len(candidates) >= 2
        and candidates[0]["share_pct"] is not None
        and candidates[1]["share_pct"] is not None
    ):
        rank_diff = round(candidates[0]["share_pct"] - candidates[1]["share_pct"], 2)

    return {
        "race_key": race_key(row),
        "sg_type_code": sg_type,
        "sg_type_label": SG_LABELS.get(sg_type, sg_type),
        "sd_name": (row.get("sdName") or "").strip(),
        "sgg_name": (row.get("sggName") or "").strip() or None,
        "wiw_name": (row.get("wiwName") or "").strip() or None,
        "eligible_voters": eligible,
        "valid_votes": valid,
        "invalid_votes": invalid,
        "progress_pct": progress,
        "rank1_minus_rank2_pp": rank_diff,
        "candidates": candidates,
    }


def build_current(sg_id: str, polled_at: datetime, calls: list[dict]) -> tuple[dict, dict]:
    races: list[dict] = []
    seen_keys: set[str] = set()
    races_with_data = 0
    progress_sum = 0.0
    progress_count = 0

    for call in calls:
        for row in call["items"]:
            # 선거구 합계행 또는 wiwName이 비어있는 행만 사용 (읍면동 세부행은 드롭).
            wiw = (row.get("wiwName") or "").strip()
            if wiw and wiw != "합계":
                continue
            normalized = normalize_row(row)
            if normalized["race_key"] in seen_keys:
                continue
            seen_keys.add(normalized["race_key"])
            races.append(normalized)
            if normalized["progress_pct"] is not None:
                progress_sum += normalized["progress_pct"]
                progress_count += 1
            if normalized["candidates"]:
                races_with_data += 1

    races.sort(key=lambda r: (r["sg_type_code"], r["sd_name"], r["sgg_name"] or ""))

    avg_progress = round(progress_sum / progress_count, 2) if progress_count else None
    openapi_empty = (
        all(c["result_code"] in ("INFO-03", "ERROR-03") for c in calls) if calls else True
    )

    if polled_at < ELECTION_DAY_KST:
        phase = "pre"
    elif openapi_empty:
        phase = "official-pending"
    elif avg_progress is not None and avg_progress >= 99.0:
        phase = "final"
    else:
        phase = "live"

    current = {
        "sgId": sg_id,
        "polled_at": polled_at.isoformat(timespec="seconds"),
        "source": "openapi",
        "phase": phase,
        "races": races,
    }
    meta = {
        "polled_at": polled_at.isoformat(timespec="seconds"),
        "source": "openapi",
        "phase": phase,
        "races_total": len(races),
        "races_with_data": races_with_data,
        "avg_progress_pct": avg_progress,
        "openapi_empty": openapi_empty,
        "progress_calc": "(yutusu + mutusu) / sunsu * 100",
    }
    return current, meta


def atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="선관위 투개표 OpenAPI 폴링 (1회 호출)")
    parser.add_argument("--sg-id", default=DEFAULT_SG_ID, help="기본 20260603")
    parser.add_argument(
        "--sg-types",
        default=",".join(DEFAULT_SG_TYPES),
        help="콤마 구분. 기본 3,4,11 (시도지사·기초단체장·교육감)",
    )
    parser.add_argument("--dry-run", action="store_true", help="저장하지 않고 stdout만 출력")
    args = parser.parse_args()

    if not API_KEY:
        sys.exit("환경변수 NEC_API_KEY가 설정되지 않았습니다.")

    sg_types = [s.strip() for s in args.sg_types.split(",") if s.strip()]
    polled_at = datetime.now(KST)
    started = time.monotonic()
    print(f"[live_counting] polled_at={polled_at.isoformat(timespec='seconds')}")
    print(f"  sg_id={args.sg_id}  sg_types={sg_types}")

    calls: list[dict] = []
    failed = 0
    for sg_type in sg_types:
        for sido in SIDOS:
            try:
                result = call_one(args.sg_id, sg_type, sido)
            except Exception as e:
                failed += 1
                print(f"  ! 실패 sg_type={sg_type} sd={sido}: {e}", file=sys.stderr)
                continue
            calls.append(result)
            print(
                f"  · sg_type={sg_type} sd={sido:8s}  "
                f"resultCode={result['result_code']}  rows={len(result['items'])}"
            )
            time.sleep(0.2)

    current, meta = build_current(args.sg_id, polled_at, calls)
    meta["calls_total"] = len(calls) + failed
    meta["calls_failed"] = failed
    meta["elapsed_seconds"] = round(time.monotonic() - started, 1)

    print(
        f"\n  races={meta['races_total']}  with_data={meta['races_with_data']}  "
        f"avg_progress={meta['avg_progress_pct']}  phase={meta['phase']}"
    )

    if args.dry_run:
        print("\n  --dry-run: 저장 생략")
        return

    raw_path = RAW_DIR / f"openapi_{polled_at.strftime('%Y%m%d_%H%M%S')}.json"
    atomic_write(
        raw_path,
        {"polled_at": polled_at.isoformat(timespec="seconds"), "calls": calls},
    )
    atomic_write(OUT_DIR / "current.json", current)
    atomic_write(OUT_DIR / "meta.json", meta)
    print(f"\n  저장: {raw_path.relative_to(ROOT)}")
    print(f"        {(OUT_DIR / 'current.json').relative_to(ROOT)}")
    print(f"        {(OUT_DIR / 'meta.json').relative_to(ROOT)}")


if __name__ == "__main__":
    main()
