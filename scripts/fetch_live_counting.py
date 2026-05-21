#!/usr/bin/env python3
"""
선관위 OpenAPI를 호출해 6/3 본투표 당일 투표율과 개표 누계를 모은다.

한 번 실행 = 한 번 폴링. cron 또는 GitHub Actions가 5분 간격으로 호출한다고 가정.

호출 두 종 (VoteXmntckInfoInqireService2):
  - getVoteSttusInfoInqire   ← 투표율 (시도별 + 전국 합계, 1회 호출)
  - getXmntckSttusInfoInqire ← 개표 (sg_type × 시도, 51회 호출)

6/3 18시 이전: 투표율만 들어옴, 개표는 ERROR-03.
6/3 18시 이후: 개표가 누적, 투표율은 final 값으로 고정.

산출물:
  data/live_counting/raw/openapi_<YYYYMMDD_HHMMSS>.json    # 두 API 원응답 모두
  data/live_counting/current.json                           # 프론트가 읽는 가공본
  data/live_counting/meta.json                              # 폴링 텔레메트리

사용:
  python scripts/fetch_live_counting.py
  python scripts/fetch_live_counting.py --sg-id 20220601    # 8회 지선 데이터로 시뮬레이션
  python scripts/fetch_live_counting.py --skip-counting     # 투표 시간대 (개표 호출 생략)
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
OP_COUNTING = "getXmntckSttusInfoInqire"
OP_TURNOUT = "getVoteSttusInfoInqire"
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
SIDOS = [
    "서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시",
    "대전광역시", "울산광역시", "세종특별자치시", "경기도", "강원특별자치도",
    "충청북도", "충청남도", "전북특별자치도", "전라남도", "경상북도",
    "경상남도", "제주특별자치도",
]

ELECTION_DAY_KST = datetime(2026, 6, 3, 18, 0, tzinfo=KST)
DEFAULT_SG_ID = "20260603"


def _pick(d: dict, *keys: str) -> Any:
    for k in keys:
        v = d.get(k)
        if v not in (None, "", "null"):
            return v
    return None


def _to_num(v: Any):
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


def to_int(v: Any) -> int:
    if v in (None, "", "null"):
        return 0
    try:
        return int(str(v).replace(",", "").strip() or 0)
    except ValueError:
        return 0


# ============ 개표 호출 ============

def call_counting(sg_id: str, sg_type: str, sd_name: str) -> dict:
    """한 (sg_type, sd_name) 묶음 개표 호출. 페이지 다 받아 items 합쳐 반환."""
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
        # 시도지사: fetch_past_counting_results.py와 동일 규약 (sggName도 시도명).
        if sg_type == "3":
            params["sggName"] = sd_name

        res = requests.get(f"{BASE_URL}/{OP_COUNTING}", params=params, timeout=30)
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


# ============ 투표율 호출 ============

def call_turnout(sg_id: str) -> dict:
    """전국 시도별 투표율 1회 호출. 응답이 없거나 실패해도 items=[] 반환."""
    items: list[dict] = []
    result_code = "?"
    try:
        params = {
            "ServiceKey": API_KEY,
            "sgId": sg_id,
            "sgTypecode": 3,   # 시도지사 단위 = 지방선거 본투표율
            "pageNo": 1,
            "numOfRows": 200,
            "resultType": "json",
        }
        res = requests.get(f"{BASE_URL}/{OP_TURNOUT}", params=params, timeout=30)
        res.raise_for_status()
        payload = res.json()
        header = payload.get("response", {}).get("header", {})
        result_code = header.get("resultCode", "?")
        if result_code in ("INFO-00", "00"):
            body = payload.get("response", {}).get("body", {}) or {}
            wrapper = body.get("items", {})
            chunk = wrapper.get("item", []) if isinstance(wrapper, dict) else wrapper
            if isinstance(chunk, dict):
                chunk = [chunk]
            items = chunk or []
    except Exception as e:
        print(f"  ! 투표율 호출 실패: {e}", file=sys.stderr)
    return {"result_code": result_code, "items": items}


def normalize_turnout(raw: dict) -> dict | None:
    """getVoteSttusInfoInqire 응답을 클린 스키마로 변환. 데이터 없으면 None.

    선관위 응답은 회차에 따라 필드명이 다르므로 _pick으로 여러 후보를 시도한다.
    합계 행이 빠져 있으면 시도 합산으로 추정해 national을 만든다.
    """
    items = raw.get("items") or []
    if not items:
        return None
    national: dict | None = None
    by_sido: list[dict] = []
    for it in items:
        sd_raw = (_pick(it, "sdName", "siDoNm") or "").strip()
        eligible = _to_num(_pick(it, "totSunsu", "tot_Sunsu", "elcGrpe", "elcCnt", "sunsu"))
        voted = _to_num(_pick(it, "totTusu", "tot_Tusu", "votCnt", "votngCnt", "tusu"))
        rate = _to_num(_pick(it, "Turnout", "turnout", "votRate", "votngRate"))
        if rate is None and eligible and voted:
            rate = round(voted / eligible * 100, 2)
        entry = {
            "sd_name": sd_raw or None,
            "eligible_voters": eligible,
            "voters_so_far": voted,
            "turnout_pct": rate,
        }
        if sd_raw in ("합계", "계", "전국", ""):
            entry["sd_name"] = "전국"
            national = entry
        else:
            by_sido.append(entry)
    if not national and by_sido:
        elig = sum((s["eligible_voters"] or 0) for s in by_sido)
        voted = sum((s["voters_so_far"] or 0) for s in by_sido)
        rate = round(voted / elig * 100, 2) if elig else None
        national = {
            "sd_name": "전국",
            "eligible_voters": elig,
            "voters_so_far": voted,
            "turnout_pct": rate,
        }
    return {"national": national, "by_sido": by_sido}


# ============ 가공 / 저장 ============

def build_current(
    sg_id: str,
    polled_at: datetime,
    counting_calls: list[dict],
    turnout: dict | None,
) -> tuple[dict, dict]:
    races: list[dict] = []
    seen_keys: set[str] = set()
    races_with_data = 0
    progress_sum = 0.0
    progress_count = 0

    for call in counting_calls:
        for row in call["items"]:
            # 선거구 합계행 또는 wiwName 비어있는 행만 사용 (읍면동 세부행은 드롭).
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
        all(c["result_code"] in ("INFO-03", "ERROR-03") for c in counting_calls)
        if counting_calls else True
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
    if turnout:
        current["turnout"] = turnout

    national_turnout = (
        (turnout or {}).get("national", {}).get("turnout_pct") if turnout else None
    )
    meta = {
        "polled_at": polled_at.isoformat(timespec="seconds"),
        "source": "openapi",
        "phase": phase,
        "races_total": len(races),
        "races_with_data": races_with_data,
        "avg_progress_pct": avg_progress,
        "openapi_empty": openapi_empty,
        "progress_calc": "(yutusu + mutusu) / sunsu * 100",
        "turnout_available": bool(turnout),
        "national_turnout_pct": national_turnout,
    }
    return current, meta


def atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def main() -> None:
    parser = argparse.ArgumentParser(description="선관위 투개표·투표율 OpenAPI 폴링 (1회 호출)")
    parser.add_argument("--sg-id", default=DEFAULT_SG_ID, help="기본 20260603")
    parser.add_argument(
        "--sg-types",
        default=",".join(DEFAULT_SG_TYPES),
        help="개표 호출 대상 sgTypecode. 기본 3,4,11 (시도지사·기초단체장·교육감)",
    )
    parser.add_argument("--skip-counting", action="store_true", help="개표 호출 생략 (투표 시간대용)")
    parser.add_argument("--skip-turnout", action="store_true", help="투표율 호출 생략")
    parser.add_argument("--dry-run", action="store_true", help="저장하지 않고 stdout만 출력")
    args = parser.parse_args()

    if not API_KEY:
        sys.exit("환경변수 NEC_API_KEY가 설정되지 않았습니다.")

    sg_types = [s.strip() for s in args.sg_types.split(",") if s.strip()]
    polled_at = datetime.now(KST)
    started = time.monotonic()
    print(f"[live_counting] polled_at={polled_at.isoformat(timespec='seconds')}")
    print(f"  sg_id={args.sg_id}  sg_types={sg_types}")

    # 투표율 — 1회 호출
    turnout_raw: dict = {"result_code": "skipped", "items": []}
    turnout: dict | None = None
    if not args.skip_turnout:
        turnout_raw = call_turnout(args.sg_id)
        turnout = normalize_turnout(turnout_raw)
        if turnout:
            print(
                f"  · 투표율  전국 {turnout['national'].get('turnout_pct')}% · "
                f"시도 {len(turnout['by_sido'])}개"
            )
        else:
            print(f"  · 투표율  resultCode={turnout_raw.get('result_code')}  데이터 없음")

    # 개표 — sg_types × 시도 호출
    counting_calls: list[dict] = []
    failed = 0
    if not args.skip_counting:
        for sg_type in sg_types:
            for sido in SIDOS:
                try:
                    result = call_counting(args.sg_id, sg_type, sido)
                except Exception as e:
                    failed += 1
                    print(f"  ! 실패 sg_type={sg_type} sd={sido}: {e}", file=sys.stderr)
                    continue
                counting_calls.append(result)
                print(
                    f"  · 개표 sg_type={sg_type} sd={sido:8s}  "
                    f"resultCode={result['result_code']}  rows={len(result['items'])}"
                )
                time.sleep(0.2)

    current, meta = build_current(args.sg_id, polled_at, counting_calls, turnout)
    meta["counting_calls_total"] = len(counting_calls) + failed
    meta["counting_calls_failed"] = failed
    meta["elapsed_seconds"] = round(time.monotonic() - started, 1)

    print(
        f"\n  races={meta['races_total']}  with_data={meta['races_with_data']}  "
        f"avg_progress={meta['avg_progress_pct']}  "
        f"national_turnout={meta['national_turnout_pct']}  phase={meta['phase']}"
    )

    if args.dry_run:
        print("\n  --dry-run: 저장 생략")
        return

    raw_path = RAW_DIR / f"openapi_{polled_at.strftime('%Y%m%d_%H%M%S')}.json"
    atomic_write(
        raw_path,
        {
            "polled_at": polled_at.isoformat(timespec="seconds"),
            "counting_calls": counting_calls,
            "turnout_call": turnout_raw,
        },
    )
    atomic_write(OUT_DIR / "current.json", current)
    atomic_write(OUT_DIR / "meta.json", meta)
    print(f"\n  저장: {raw_path.relative_to(ROOT)}")
    print(f"        {(OUT_DIR / 'current.json').relative_to(ROOT)}")
    print(f"        {(OUT_DIR / 'meta.json').relative_to(ROOT)}")


if __name__ == "__main__":
    main()
