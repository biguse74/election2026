#!/usr/bin/env python3
"""
선관위 예비후보자 정보 OpenAPI 호출 스크립트
9회 전국동시지방선거(2026.6.3) 예비후보자 데이터를 시도단위로 받아
일자별 스냅샷으로 저장한다.

주의:
    - 예비후보자 정보는 후보자등록일(2026.5.14)부터 OpenAPI 조회 불가능.
    - 사퇴·등록무효 추적을 위해 매일 한 번씩 실행 권장.
    - 코드정보가 먼저 받아져 있어야 함 (data/codes/20260603/gusigun.json).

사용:
    export NEC_API_KEY=...
    python scripts/fetch_preliminary.py

산출물:
    data/preliminary/<sgId>/snapshot_YYYYMMDD.json
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

BASE_URL = "http://apis.data.go.kr/9760000/PofelcddInfoInqireService"
API_KEY = os.environ.get("NEC_API_KEY", "").strip()
TARGET_SG_ID = "20260603"

ROOT_DIR = Path(__file__).resolve().parent.parent
CODES_DIR = ROOT_DIR / "data" / "codes" / TARGET_SG_ID
OUT_DIR = ROOT_DIR / "data" / "preliminary" / TARGET_SG_ID

# 9회 지선에서 실시되는 선거종류 (교육의원[10] 일몰 적용)
LOCAL_ELECTION_TYPES: dict[int, str] = {
    3: "시도지사선거",
    4: "구시군장선거",
    5: "시도의원선거",
    6: "구시군의회의원선거",
    8: "광역의원비례대표",
    9: "기초의원비례대표",
    11: "교육감선거",
}


def load_sido_list() -> list[str]:
    """gusigun.json에서 시도명 목록을 추출.
    PDF 명세: '구시군명이 시도이면 공란'이라는 규칙 기반.
    """
    gusigun_file = CODES_DIR / "gusigun.json"
    if not gusigun_file.exists():
        sys.exit(
            f"코드정보가 없습니다. 먼저 fetch_codes.py를 실행하세요.\n"
            f"  예상 경로: {gusigun_file}"
        )

    data = json.loads(gusigun_file.read_text(encoding="utf-8"))

    # sdName이 비어있고 wiwName이 있는 항목 → 시도 자체
    sidos = sorted({
        item["wiwName"]
        for item in data
        if not item.get("sdName") and item.get("wiwName")
    })

    # fallback: 모든 sdName 값 모음
    if not sidos:
        sidos = sorted({
            item["sdName"]
            for item in data
            if item.get("sdName")
        })

    return sidos


def fetch_pages(operation: str, params: dict, max_pages: int = 100) -> list[dict]:
    """OpenAPI 호출 + 페이지네이션 처리."""
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

        # 인증/쿼터 에러는 XML로 옴
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

        # ERROR-03: 데이터 없음 (해당 시도/선거종류에 예비후보 없을 때 정상)
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


def main() -> None:
    if not API_KEY:
        sys.exit("환경변수 NEC_API_KEY가 설정되지 않았습니다.")

    print("=" * 60)
    print("예비후보자 데이터 수집 (시도단위)")
    print("=" * 60)

    sidos = load_sido_list()
    print(f"\n시도 {len(sidos)}개:")
    for s in sidos:
        print(f"  - {s}")

    base_calls = len(sidos) * len(LOCAL_ELECTION_TYPES)
    print(f"\n기본 호출 횟수: {base_calls}회 "
          f"(시도 {len(sidos)} × 선거종류 {len(LOCAL_ELECTION_TYPES)})")
    print(f"+ 페이지네이션으로 시도당 추가 호출 가능 (개발계정 일일 한도 1,000회 이내)")
    print()

    all_candidates: list[dict] = []
    call_count = 0
    started_at = datetime.now()

    for sg_type, label in LOCAL_ELECTION_TYPES.items():
        print(f"[sgTypecode={sg_type}] {label}")
        type_total = 0
        for sido in sidos:
            call_count += 1
            items = fetch_pages(
                "getPoelpcddRegistSttusInfoInqire",
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
        print(f"  -- 소계: {type_total:,}명")
        print()

    # 스냅샷 저장
    today = datetime.now().strftime("%Y%m%d")
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

    elapsed = (datetime.now() - started_at).total_seconds()

    print("=" * 60)
    print(f"수집 완료")
    print(f"  - 총 예비후보자: {len(all_candidates):,}명")
    print(f"  - API 호출 횟수: {call_count}회")
    print(f"  - 소요 시간: {elapsed:.1f}초")
    print(f"  - 저장 위치: {out_file.relative_to(ROOT_DIR)}")
    print()

    # 선거종류별 요약
    print("선거종류별 집계:")
    by_type: dict[str, int] = {}
    for c in all_candidates:
        t = str(c.get("sgTypecode"))
        by_type[t] = by_type.get(t, 0) + 1
    for sg_type, label in LOCAL_ELECTION_TYPES.items():
        print(f"  - {label:18s}: {by_type.get(str(sg_type), 0):,}명")

    # 정당별 상위 10개
    print("\n정당별 상위 10개:")
    by_party: dict[str, int] = {}
    for c in all_candidates:
        p = c.get("jdName", "(미상)")
        by_party[p] = by_party.get(p, 0) + 1
    for party, cnt in sorted(by_party.items(), key=lambda x: -x[1])[:10]:
        print(f"  - {party}: {cnt:,}명")


if __name__ == "__main__":
    main()
