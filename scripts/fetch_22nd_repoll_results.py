#!/usr/bin/env python3
"""
22대 국회의원선거(2024-04-10) 결과 중 9회 동시 재·보궐 14개 선거구만 가져온다.

repoll.js의 consti 명단(부산광역시북구갑 등)으로 sdName·sggName 후보를
자동 매칭. OpenAPI 호출은 시도 단위(sdName=부산광역시)로 한 번에 받고
클라이언트 측에서 consti 정확 매칭.

산출물:
    data/assembly_22nd_repoll_results.json
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "assembly_22nd_repoll_results.json"
API_KEY = os.environ.get("NEC_API_KEY", "").strip()
BASE = "https://apis.data.go.kr/9760000/VoteXmntckInfoInqireService2/getXmntckSttusInfoInqire"
SG_ID = "20240410"
SG_TYPE = "2"

# 14개 재보궐 선거구 — MBC repoll.js 명단을 하드코딩 (tmp 의존성 제거)
REPOLL_RACES = [
    {"consti": "부산광역시북구갑",       "region1_site": "부산", "region2_site": "북갑"},
    {"consti": "대구광역시달성군",       "region1_site": "대구", "region2_site": "달성"},
    {"consti": "인천광역시연수구갑",      "region1_site": "인천", "region2_site": "연수갑"},
    {"consti": "인천광역시계양구을",      "region1_site": "인천", "region2_site": "계양을"},
    {"consti": "광주광역시광산구을",      "region1_site": "광주", "region2_site": "광산을"},
    {"consti": "울산광역시남구갑",       "region1_site": "울산", "region2_site": "남갑"},
    {"consti": "경기도평택시을",        "region1_site": "경기", "region2_site": "평택을"},
    {"consti": "경기도안산시갑",        "region1_site": "경기", "region2_site": "안산갑"},
    {"consti": "경기도하남시갑",        "region1_site": "경기", "region2_site": "하남갑"},
    {"consti": "충청남도공주시부여군청양군", "region1_site": "충남", "region2_site": "공주부여청양"},
    {"consti": "충청남도아산시을",       "region1_site": "충남", "region2_site": "아산을"},
    {"consti": "전라북도군산시김제시부안군갑", "region1_site": "전북", "region2_site": "군산김제부안갑"},
    {"consti": "전라북도군산시김제시부안군을", "region1_site": "전북", "region2_site": "군산김제부안을"},
    {"consti": "제주특별자치도서귀포시",    "region1_site": "제주", "region2_site": "서귀포"},
]

SIDO_TO_FULL = {
    "부산": "부산광역시", "대구": "대구광역시", "인천": "인천광역시",
    "광주": "광주광역시", "울산": "울산광역시", "경기": "경기도",
    "충남": "충청남도", "전북": "전북특별자치도", "제주": "제주특별자치도",
}


def parse_repoll() -> list[dict]:
    return REPOLL_RACES


def to_int(v):
    if v in (None, "", "null"):
        return 0
    try:
        return int(str(v).replace(",", "").strip() or 0)
    except ValueError:
        return 0


def extract_candidates(row):
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
        out.append({"slot": i, "name": name, "party": party, "votes": votes, "vote_share": share})
    out.sort(key=lambda c: c["votes"], reverse=True)
    return out


def fetch_sido(sido_full: str) -> list[dict]:
    """한 시도의 22대 모든 지역구 결과 fetch (sggName 미지정 → 전체)."""
    items = []
    page = 1
    while page <= 10:
        params = {
            "ServiceKey": API_KEY, "sgId": SG_ID, "sgTypecode": SG_TYPE,
            "sdName": sido_full, "pageNo": page, "numOfRows": 100, "resultType": "json",
        }
        r = requests.get(BASE, params=params, timeout=30)
        r.raise_for_status()
        d = r.json().get("response", {})
        code = d.get("header", {}).get("resultCode")
        if code in ("INFO-03", "ERROR-03"):
            return []
        body = d.get("body", {}) or {}
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


def match_consti(consti: str, sido_full: str, rows: list[dict]) -> dict | None:
    """OpenAPI 응답 row 중 consti와 가장 일치하는 합계행 1개 선택."""
    target = consti.replace(sido_full, "").replace(" ", "")
    # 후보 패턴 (점·구분자 다양)
    cands = {
        target,
        target.replace("·", ""),
        target.replace("구", "", 1),  # 북구갑 → 북갑
    }
    # rows에서 wiwName=='합계'이고 sggName이 cands에 들어가는 것
    for r in rows:
        if (r.get("wiwName") or "").strip() not in ("", "합계"):
            continue
        sgg = (r.get("sggName") or "").replace(" ", "").replace("·", "")
        if sgg in {c.replace("·", "") for c in cands} or sgg == target.replace("·", ""):
            return r
        # 보다 너그럽게: target이 sgg에 포함되거나 그 반대
        if target.replace("·", "") and (target.replace("·", "") in sgg or sgg in target.replace("·", "")):
            return r
    return None


def main():
    if not API_KEY:
        sys.exit("환경변수 NEC_API_KEY가 설정되지 않았습니다.")
    repoll = parse_repoll()
    # 시도별로 그룹핑
    by_sido = {}
    for rp in repoll:
        r1 = rp.get("region1_site")
        sido_full = SIDO_TO_FULL.get(r1)
        if sido_full:
            by_sido.setdefault(sido_full, []).append(rp)

    out_races = []
    for sido_full, rps in by_sido.items():
        print(f"  fetch {sido_full} ...")
        rows = fetch_sido(sido_full)
        print(f"    응답 {len(rows)}행")
        for rp in rps:
            consti = rp["consti"]
            row = match_consti(consti, sido_full, rows)
            if not row:
                print(f"    ! {consti} — 매칭 실패")
                continue
            cands = extract_candidates(row)
            winner = cands[0] if cands else None
            dem = next((c for c in cands if c["party"] == "더불어민주당"), None)
            con = next((c for c in cands if c["party"] == "국민의힘"), None)
            margin = (dem["vote_share"] - con["vote_share"]) if (dem and con) else None
            out_races.append({
                "consti": consti,
                "sgg_name_actual": (row.get("sggName") or "").strip(),
                "sd_name": sido_full,
                "winner": {"name": winner["name"], "party": winner["party"], "share": winner["vote_share"]} if winner else None,
                "dem_22": {"name": dem["name"], "share": dem["vote_share"]} if dem else None,
                "con_22": {"name": con["name"], "share": con["vote_share"]} if con else None,
                "margin_22": round(margin, 2) if margin is not None else None,
            })
            print(f"    · {consti:<28s} [{row.get('sggName')}]  "
                  f"D {dem['vote_share'] if dem else '—'}% vs R {con['vote_share'] if con else '—'}%  "
                  f"margin {margin:+.1f}%p" if margin is not None else f"    · {consti}")

    payload = {
        "generated_at": "2026-05-27",
        "source": "선관위 OpenAPI · 22대 국회의원선거 (sgId=20240410)",
        "races": out_races,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장: {OUT.relative_to(ROOT)}  ({len(out_races)}개 매칭)")


if __name__ == "__main__":
    main()
