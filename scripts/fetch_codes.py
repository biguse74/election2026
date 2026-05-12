#!/usr/bin/env python3
"""
선관위 코드정보 OpenAPI 호출 스크립트
9회 전국동시지방선거(2026.6.3) 관련 코드를 받아와 JSON으로 저장.

사용:
    export NEC_API_KEY=...        # 또는 GitHub Actions Secrets로 주입
    python scripts/fetch_codes.py

산출물:
    data/codes/elections.json                       # 전체 선거 목록
    data/codes/<sgId>/gusigun.json                  # 구시군 코드
    data/codes/<sgId>/parties.json                  # 정당 코드
    data/codes/<sgId>/jobs.json                     # 직업 코드
    data/codes/<sgId>/educations.json               # 학력 코드
    data/codes/<sgId>/constituencies/sgType_<n>.json  # 선거구 코드
"""

from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path
from typing import Any

import requests

BASE_URL = "http://apis.data.go.kr/9760000/CommonCodeService"
API_KEY = os.environ.get("NEC_API_KEY", "").strip()
TARGET_VOTE_DATE = "20260603"  # 9회 지선 본투표일
DATA_DIR = Path(__file__).resolve().parent.parent / "data" / "codes"

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


def fetch_pages(operation: str, params: dict, max_pages: int = 50) -> list[dict]:
    """
    OpenAPI 호출 후 페이지네이션 처리하여 전체 항목 반환.
    공공데이터포털 인증 에러는 XML로 오므로 별도 처리한다.
    """
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
            sys.exit(f"  요청 실패: {e}")

        # 인증/쿼터 에러는 XML로 옴
        if "<OpenAPI_ServiceResponse>" in res.text:
            sys.exit(f"  포털 에러:\n{res.text}")

        try:
            data = res.json()
        except ValueError:
            sys.exit(f"  JSON 파싱 실패. 원문:\n{res.text[:500]}")

        resp = data.get("response", {})
        header = resp.get("header", {})
        code = header.get("resultCode", "")
        if code not in ("INFO-00", "00"):
            sys.exit(f"  결과 에러: {header}")

        body = resp.get("body", {})
        wrapper = body.get("items", {})

        # items가 빈 문자열, dict(단건), list(다건)일 수 있음
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
        time.sleep(0.3)  # 과한 호출 방지

    return items


def save_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    count = len(data) if isinstance(data, list) else 1
    print(f"  → {path.relative_to(DATA_DIR.parent.parent)} ({count}건)")


def find_target_sg_id(elections: list[dict]) -> str:
    """전체 선거 목록에서 9회 지선 sgId를 찾는다."""
    matches = [e for e in elections if e.get("sgVotedate") == TARGET_VOTE_DATE]
    if not matches:
        print(f"\n  {TARGET_VOTE_DATE}에 해당하는 선거를 찾지 못했습니다.")
        print("  응답에 포함된 최근 선거 10건:")
        for e in elections[:10]:
            print(f"    {e}")
        sys.exit(1)

    # sgTypecode=0이 대표 선거명
    representative = [e for e in matches if str(e.get("sgTypecode")) == "0"]
    target = representative[0] if representative else matches[0]
    return str(target["sgId"])


def main() -> None:
    if not API_KEY:
        sys.exit("환경변수 NEC_API_KEY가 설정되지 않았습니다.")

    print("=" * 60)
    print("선관위 코드정보 수집")
    print("=" * 60)

    # 1. 전체 선거 목록
    print("\n[1/6] 선거 코드 조회")
    elections = fetch_pages("getCommonSgCodeList", {})
    save_json(DATA_DIR / "elections.json", elections)

    sg_id = find_target_sg_id(elections)
    print(f"\n  9회 지선 sgId 확정: {sg_id}")

    sg_dir = DATA_DIR / sg_id
    sg_dir.mkdir(parents=True, exist_ok=True)

    # 2. 구시군 코드
    print(f"\n[2/6] 구시군 코드 조회")
    save_json(
        sg_dir / "gusigun.json",
        fetch_pages("getCommonGusigunCodeList", {"sgId": sg_id}),
    )

    # 3. 정당 코드
    print(f"\n[3/6] 정당 코드 조회")
    save_json(
        sg_dir / "parties.json",
        fetch_pages("getCommonPartyCodeList", {"sgId": sg_id}),
    )

    # 4. 직업 코드
    print(f"\n[4/6] 직업 코드 조회")
    save_json(
        sg_dir / "jobs.json",
        fetch_pages("getCommonJobCodeList", {"sgId": sg_id}),
    )

    # 5. 학력 코드
    print(f"\n[5/6] 학력 코드 조회")
    save_json(
        sg_dir / "educations.json",
        fetch_pages("getCommonEduBckgrdCodeList", {"sgId": sg_id}),
    )

    # 6. 선거구 코드 (선거종류별)
    print(f"\n[6/6] 선거구 코드 조회 (선거종류별)")
    cstc_dir = sg_dir / "constituencies"
    cstc_dir.mkdir(exist_ok=True)
    combined: list[dict] = []
    for sg_type, label in LOCAL_ELECTION_TYPES.items():
        print(f"  - sgTypecode={sg_type} ({label})")
        items = fetch_pages(
            "getCommonSggCodeList",
            {"sgId": sg_id, "sgTypecode": sg_type},
        )
        save_json(cstc_dir / f"sgType_{sg_type}.json", items)
        combined.extend(items)

    # 클라이언트(main.js)에서 한 번에 읽도록 통합본을 site/data/에 출력.
    # sggJungsu(의석수)를 후보 수와 곱해 경쟁률 계산용으로 사용.
    root_dir = DATA_DIR.parent.parent
    site_data = root_dir / "site" / "data" / "constituencies.json"
    site_data.parent.mkdir(parents=True, exist_ok=True)
    save_json(site_data, combined)
    print(f"  통합본 저장: {site_data.relative_to(root_dir)} ({len(combined)}개)")

    print(f"\n완료. 저장 경로: {DATA_DIR.resolve()}")


if __name__ == "__main__":
    main()
