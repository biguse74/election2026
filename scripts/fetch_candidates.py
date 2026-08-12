#!/usr/bin/env python3
"""
선관위 후보자 정보 OpenAPI 호출 스크립트
9회 전국동시지방선거(2026.6.3) 후보자 데이터를 시도단위로 받아
일자별 스냅샷으로 저장한다.

사용:
    export NEC_API_KEY=...
    python scripts/fetch_candidates.py

산출물:
    data/candidates/<sgId>/snapshot_YYYYMMDD.json
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

BASE_URL = "http://apis.data.go.kr/9760000/PofelcddInfoInqireService"
API_KEY = os.environ.get("NEC_API_KEY", "").strip()
TARGET_SG_ID = "20260603"
# 파일명을 KST 기준으로 (UTC now_kst()를 쓰면 KST 03시 cron이 전날 파일을 만듦)
KST = timezone(timedelta(hours=9))
def now_kst() -> datetime: return datetime.now(KST)

ROOT_DIR = Path(__file__).resolve().parent.parent
CODES_DIR = ROOT_DIR / "data" / "codes" / TARGET_SG_ID
OUT_DIR = ROOT_DIR / "data" / "candidates" / TARGET_SG_ID

LOCAL_ELECTION_TYPES: dict[int, str] = {
    2: "국회의원선거(재·보궐)",
    3: "시도지사선거",
    4: "구시군장선거",
    5: "시도의원선거",
    6: "구시군의회의원선거",
    8: "광역의원비례대표",
    9: "기초의원비례대표",
    11: "교육감선거",
}


def load_sido_list() -> list[str]:
    gusigun_file = CODES_DIR / "gusigun.json"
    if not gusigun_file.exists():
        sys.exit(f"코드정보가 없습니다. 먼저 fetch_codes.py를 실행하세요.")

    data = json.loads(gusigun_file.read_text(encoding="utf-8"))
    sidos = sorted({
        item["wiwName"]
        for item in data
        if not item.get("sdName") and item.get("wiwName")
    })
    if not sidos:
        sidos = sorted({
            item["sdName"]
            for item in data
            if item.get("sdName")
        })
    return sidos


def fetch_pages(operation: str, params: dict, max_pages: int = 100) -> list[dict]:
    items: list[dict] = []
    page = 1

    while page <= max_pages:
        query = {
            **params,
            "serviceKey": API_KEY,
            "pageNo": page,
            "numOfRows": 100,
            "resultType": "json",
        }
        url = f"{BASE_URL}/{operation}"

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


def dedupe_by_huboid(items: list[dict]) -> list[dict]:
    """huboid 기준 중복 제거.

    전남광주통합특별시 시도지사 후보는 sdName=광주광역시·전라남도 양쪽 호출에서
    모두 반환되어 약 240건 중복이 발생한다. 저장 전 한 번 정리해 둔다.
    """
    seen: set[str] = set()
    out: list[dict] = []
    for c in items:
        hid = c.get("huboid")
        if hid and hid in seen:
            continue
        if hid:
            seen.add(hid)
        out.append(c)
    return out


def main() -> None:
    if not API_KEY:
        sys.exit("환경변수 NEC_API_KEY가 설정되지 않았습니다.")

    print("=" * 60)
    print("후보자 데이터 수집 (시도단위)")
    print("=" * 60)

    sidos = load_sido_list()
    print(f"\n시도 {len(sidos)}개")

    base_calls = len(sidos) * len(LOCAL_ELECTION_TYPES)
    print(f"기본 호출: {base_calls}회\n")

    all_candidates: list[dict] = []
    call_count = 0
    started_at = now_kst()

    for sg_type, label in LOCAL_ELECTION_TYPES.items():
        print(f"[sgTypecode={sg_type}] {label}")
        type_total = 0
        for sido in sidos:
            call_count += 1
            items = fetch_pages(
                "getPofelcddRegistSttusInfoInqire",
                {
                    "sgId": TARGET_SG_ID,
                    "sgTypecode": sg_type,
                    "sdName": sido,
                },
            )
            type_total += len(items)
            print(f"  {sido}: {len(items)}명")
            all_candidates.extend(items)
            time.sleep(0.2)
        print(f"  -- 소계: {type_total:,}명\n")

    before = len(all_candidates)
    all_candidates = dedupe_by_huboid(all_candidates)
    removed = before - len(all_candidates)
    if removed:
        print(f"huboid 중복 제거: {removed}건 (통합특별시 시도지사 등)\n")

    today = now_kst().strftime("%Y%m%d")
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_file = OUT_DIR / f"snapshot_{today}.json"

    snapshot = {
        "sgId": TARGET_SG_ID,
        "fetched_at": started_at.isoformat(timespec="seconds"),
        "total_api_calls": call_count,
        "total_candidates": len(all_candidates),
        "candidates": all_candidates,
    }

    out_file.write_text(
        json.dumps(snapshot, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # 최신 스냅샷 포인터. 프론트가 이걸 먼저 읽으므로, 수집이 멈춘 뒤에도
    # 날짜 역탐색 창(30일)이 지나가며 사이트가 죽는 일이 없다.
    (OUT_DIR / "latest.json").write_text(
        json.dumps(
            {
                "date": today,
                "file": out_file.name,
                "fetched_at": snapshot["fetched_at"],
                "total_candidates": snapshot["total_candidates"],
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    elapsed = (now_kst() - started_at).total_seconds()

    print("=" * 60)
    print(f"수집 완료: 총 {len(all_candidates):,}명, 호출 {call_count}회, {elapsed:.1f}초")
    print(f"저장: {out_file.relative_to(ROOT_DIR)}\n")

    by_type: dict[str, int] = {}
    for c in all_candidates:
        t = str(c.get("sgTypecode"))
        by_type[t] = by_type.get(t, 0) + 1
    print("선거종류별:")
    for sg_type, label in LOCAL_ELECTION_TYPES.items():
        print(f"  - {label:18s}: {by_type.get(str(sg_type), 0):,}명")

    by_party: dict[str, int] = {}
    for c in all_candidates:
        p = c.get("jdName", "(미상)")
        by_party[p] = by_party.get(p, 0) + 1
    print("\n정당별 상위 10개:")
    for party, cnt in sorted(by_party.items(), key=lambda x: -x[1])[:10]:
        print(f"  - {party}: {cnt:,}명")

    by_status: dict[str, int] = {}
    for c in all_candidates:
        s = c.get("status", "(미상)")
        by_status[s] = by_status.get(s, 0) + 1
    print("\n등록상태별:")
    for status, cnt in sorted(by_status.items(), key=lambda x: -x[1]):
        print(f"  - {status}: {cnt:,}명")


if __name__ == "__main__":
    main()
