#!/usr/bin/env python3
"""광역의원(시도의원)·기초의원 지역구 정당별 의석 1회 집계 (완전판).

선거 종료 후 1회만 도는 정적 수집기(5분 자동 루프와 분리).
핵심: NEC 개표 리포트(VCCP09)는 '경합 선거구'만 반환하고 무투표 당선 선거구는
누락된다(개표 자체가 없으므로). 따라서 두 소스를 합쳐 100% 커버한다.

  1) 선거구 의원정수(constituencies/sgType_{5,6}.json의 sggJungsu) = M.
  2) 후보 등록자료에서 선거구별 유효후보(status='등록') 수 n 파악.
     · n <= M  → 무투표 당선: 등록후보 전원 당선 → 등록 정당으로 집계.
     · n >  M  → 경합: NEC VCCP09 개표 스크랩 → 득표 상위 M명 = 당선.
  3) 정당별·시도별 의석 집계. (지역구 한정. 비례 8·9는 별도.)

검증: 전북 시도의원 = 경합 13(스크랩) + 무투표 25(등록) = 38(정수코드)와 일치.
출력: data/live_counting/council_seats.json
"""
import json
import os
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_live_counting as F  # 스크랩 헬퍼 재사용

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
CODES = ROOT / "data" / "codes" / "20260603" / "constituencies"
OUT = ROOT / "data" / "live_counting" / "council_seats.json"
WIN_OUT = ROOT / "data" / "live_counting" / "council_winners.json"

OFFICES = {"5": "시도의원", "6": "기초의원"}
VALID_STATUS = {"등록"}  # 사퇴·등록무효·사망 제외

API_KEY = (os.environ.get("NEC_API_KEY", "").strip()
           or (ROOT / "data" / ".nec_api_key").read_text(encoding="utf-8").strip())
CAND_API = "http://apis.data.go.kr/9760000/PofelcddInfoInqireService/getPofelcddRegistSttusInfoInqire"


def load_magnitude(sg_type: str) -> dict:
    data = json.loads((CODES / f"sgType_{sg_type}.json").read_text(encoding="utf-8"))
    return {(x["sdName"], x["sggName"]): int(x.get("sggJungsu") or 0) for x in data}


def load_candidates_by_sgg(sg_type: str, sgg2sd: dict) -> dict:
    """후보 등록자료를 OpenAPI에서 직접 완전 수집(numOfRows=1000). 저장 스냅샷은 페이지네이션
    누락이 있어(서울 등 일부 시도) 무투표 판정이 틀어지므로 API를 1차 소스로 쓴다.
    후보 API는 광주+전남 시도의원/기초의원을 sdName='전남광주통합특별시'로 묶어 반환하므로,
    선거구코드의 (sgg→sd) 매핑으로 실제 광주/전남에 재배정해 정확히 조인한다."""
    items, page = [], 1
    while True:
        q = {"serviceKey": API_KEY, "pageNo": page, "numOfRows": 1000, "resultType": "json",
             "sgId": "20260603", "sgTypecode": sg_type}
        b = requests.get(CAND_API, params=q, timeout=40).json()["response"].get("body", {})
        w = b.get("items", {})
        it = w.get("item", []) if isinstance(w, dict) else w
        if isinstance(it, dict):
            it = [it]
        items += it
        total = int(b.get("totalCount", 0) or 0)
        if total == 0 or len(items) >= total:
            break
        page += 1
        time.sleep(0.2)
    by = defaultdict(list)       # (sd, sgg) -> 후보
    for c in items:
        if c.get("status") not in VALID_STATUS:
            continue
        sd, sgg = c["sdName"], c["sggName"]
        if sd == "전남광주통합특별시":
            sd = sgg2sd.get(sgg, sd)  # 광주/전남으로 재배정(광주·전남 내 sgg는 유일)
        by[(sd, sgg)].append(c)
    return by


def scrape_contested(sg_type: str) -> dict:
    """(sdName, sggName) -> race(개표). 시도 cityCode 1콜로 경합 선거구 전부 반환."""
    stmt = f"VCCP09_#{sg_type}"
    out = {}
    for sd_name, code in F._SIDO_CITYCODE.items():
        rows = F._vccp_rows("0020260603", sg_type, code, stmt)
        if not rows:
            continue
        for r in F._parse_vccp_blocks(rows, sg_type, sd_override=sd_name, sgg_col="b1"):
            out[(r["sd_name"], r["sgg_name"])] = r
        time.sleep(0.15)
    return out


def collect_office(sg_type: str) -> dict:
    mag = load_magnitude(sg_type)
    # 광주/전남 내 sgg→sd (통합특별시로 묶인 후보 재배정용; 이 범위 내 sgg는 유일)
    sgg2sd = {sgg: sd for (sd, sgg) in mag if sd in ("광주광역시", "전라남도")}
    cands = load_candidates_by_sgg(sg_type, sgg2sd)
    scraped = scrape_contested(sg_type)

    party = defaultdict(int)        # 정당 -> 의석
    by_sido = defaultdict(lambda: defaultdict(int))
    winners = []                    # 개별 당선자(검색용)
    n_contested = n_uncontested = n_missing = 0
    seats = 0

    def add(sd, sgg, name, jd, mode):
        nonlocal seats
        p = jd or "무소속"
        party[p] += 1
        by_sido[sd][p] += 1
        seats += 1
        winners.append({"name": name, "jd": p, "sd": sd, "sgg": sgg,
                        "office": OFFICES[sg_type], "sg_type_code": sg_type, "mode": mode})

    for (sd, sgg), M in mag.items():
        valid = cands.get((sd, sgg), [])
        n = len(valid)
        if n == 0:
            r = scraped.get((sd, sgg))
            if r:
                n_contested += 1
                for c in r["candidates"][:M]:
                    add(sd, sgg, c["name"], c["jd_name"], "개표")
            else:
                n_missing += 1
            continue
        if n <= M:
            # 무투표 당선 — 등록후보 전원
            n_uncontested += 1
            for c in valid:
                add(sd, sgg, c.get("name"), c.get("jdName"), "무투표")
        else:
            # 경합 — 개표 상위 M명
            r = scraped.get((sd, sgg))
            if r:
                n_contested += 1
                for c in r["candidates"][:M]:
                    add(sd, sgg, c["name"], c["jd_name"], "개표")
            else:
                n_missing += 1

    office = {
        "label": f"{OFFICES[sg_type]}(지역구)",
        "sg_type_code": sg_type,
        "total_seats": seats,
        "expected_seats": sum(mag.values()),
        "districts": n_contested + n_uncontested,
        "contested": n_contested,
        "uncontested": n_uncontested,
        "missing_districts": n_missing,
        "party": dict(sorted(party.items(), key=lambda kv: -kv[1])),
        "by_sido": {sd: dict(sorted(d.items(), key=lambda kv: -kv[1])) for sd, d in by_sido.items()},
    }
    return office, winners


def main():
    result = {
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "source": ("중앙선관위 — 경합 선거구는 VCCP09 개표 상위 M명(M=의원정수), "
                   "무투표 선거구는 후보 등록자료 전원 당선. 지역구 한정(비례 제외)."),
        "offices": {},
    }
    all_winners = []
    for sg_type in OFFICES:
        print(f"[type {sg_type}] {OFFICES[sg_type]} 수집…", file=sys.stderr)
        office, winners = collect_office(sg_type)
        result["offices"][sg_type] = office
        all_winners += winners
        print(f"  → 의석 {office['total_seats']}/{office['expected_seats']} · "
              f"경합 {office['contested']} · 무투표 {office['uncontested']} · 누락 {office['missing_districts']}",
              file=sys.stderr)
        for p, n in list(office["party"].items())[:6]:
            print(f"     {p}: {n}", file=sys.stderr)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"저장: {OUT}", file=sys.stderr)
    # 개별 당선자 명단(검색용) — 광역의원·기초의원
    win_out = {
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "source": "광역의원·기초의원 지역구 당선자(경합=개표 상위 M명, 무투표=등록후보 전원).",
        "count": len(all_winners),
        "winners": all_winners,
    }
    WIN_OUT.write_text(json.dumps(win_out, ensure_ascii=False), encoding="utf-8")
    print(f"저장: {WIN_OUT} ({len(all_winners)}명)", file=sys.stderr)


if __name__ == "__main__":
    main()
