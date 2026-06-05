#!/usr/bin/env python3
"""광역의원 비례(8)·기초의원 비례(9) 정당별 의석 집계.

비례대표는 정당명부 → 헤어식(largest remainder) 배분. 선거 종료 후 1회 수집.
  · 봉쇄조항: 유효투표총수의 5% 이상 득표 정당만 배분(공직선거법 §190의2).
  · 배분: 의석할당정당 득표비율로 1차 정수배분 + 잔여는 소수 큰 순.
  · 광역·기초 모두 한 정당 2/3 초과 배분 제한 적용.
검증: 서울 광역비례(정수15) → 민주7·국힘8 (보도 최종 일치).

데이터 함정:
  · 광역비례(8)는 NEC가 광주+전남을 '전남광주통합특별시'(정수12)로 통합 반환
    (2026 통합특별시가 광역 비례를 함께 선출). → 광주+전남 VCCP 득표를 합산해 12석 배분.
  · 기초비례(9)는 광주/전남 분리(통합 아님). 세종·제주는 기초의원 없음(비례 없음).

소스: VCCP09_#8 / VCCP09_#9 (정당별 득표). 출력: council_seats.json의 offices['8'],['9'].
"""
import json
import sys
import time
from collections import defaultdict
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent))
import fetch_live_counting as F
import fetch_council_seats as CS  # 무투표 보완: 후보 등록자료 로더 재사용


def fetch_roster(sg_type, sd_name):
    """비례 후보 명부(num 순번 포함) 시도별 조회. status='등록'만."""
    items, page = [], 1
    while True:
        q = {"serviceKey": CS.API_KEY, "pageNo": page, "numOfRows": 1000, "resultType": "json",
             "sgId": "20260603", "sgTypecode": sg_type, "sdName": sd_name}
        b = requests.get(CS.CAND_API, params=q, timeout=40).json()["response"].get("body") or {}
        it = b.get("items", {})
        it = it.get("item", []) if isinstance(it, dict) else it
        if isinstance(it, dict):
            it = [it]
        items += [c for c in (it or []) if c.get("status") == "등록"]
        tot = int(b.get("totalCount", 0) or 0)
        if tot == 0 or len(items) >= tot:
            break
        page += 1
        time.sleep(0.1)
    return items


def winners_by_roster(roster, seats_by_party):
    """정당별 배분 의석만큼 명부 num(순번) 상위를 당선자 huboid로."""
    byparty = defaultdict(list)
    for c in sorted(roster, key=lambda x: int(x.get("num") or 0)):
        byparty[c.get("jdName") or "무소속"].append(c)
    out = []
    for p, n in seats_by_party.items():
        for c in byparty.get(p, [])[:n]:
            out.append(str(c.get("huboid")))
    return out

ROOT = Path(__file__).resolve().parent.parent
CODES = ROOT / "data" / "codes" / "20260603" / "constituencies"
SEATS = ROOT / "data" / "live_counting" / "council_seats.json"
EID = "0020260603"
DEM, CON = "더불어민주당", "국민의힘"
DEM_LIKE = {DEM}
CON_LIKE = {CON, "개혁신당"}   # result.js _partyTally와 동일 분류(보수계)


def allocate(votes: dict, seats: int, cap_two_thirds: bool = True) -> dict:
    """헤어식(최대잔여) 배분 + 5% 봉쇄 + 한 정당 2/3 상한."""
    total = sum(votes.values())
    if total == 0 or seats == 0:
        return {}
    thr = total * 0.05
    elig = {p: v for p, v in votes.items() if v >= thr}
    if not elig:
        return {}
    base = sum(elig.values())
    quota = {p: elig[p] / base * seats for p in elig}
    alloc = {p: int(quota[p]) for p in elig}
    rem = seats - sum(alloc.values())
    for p in sorted(elig, key=lambda p: -(quota[p] - int(quota[p])))[:rem]:
        alloc[p] += 1
    if cap_two_thirds and len(elig) > 1:
        cap = seats * 2 // 3
        for p in list(alloc):
            if alloc[p] > cap:
                extra = alloc[p] - cap
                alloc[p] = cap
                others = sorted([x for x in elig if x != p],
                                key=lambda x: -(quota[x] - int(quota[x])))
                for i in range(extra):
                    alloc[others[i % len(others)]] += 1
    return {p: n for p, n in alloc.items() if n > 0}


def _party_cols(header):
    s = header.index(DEM)
    e = header.index("계") if "계" in header else len(header)
    return [(i, header[i].strip()) for i in range(s, e) if header[i].strip()]


def parse_rows(rows):
    """VCCP09 비례 응답 → {지역명(첫칼럼): {정당:득표}}. 합계행은 '합계' 키로."""
    header = next((r for r in rows if DEM in r), None)
    if not header:
        return {}
    cols = _party_cols(header)
    out = {}
    for r in rows:
        if not r or not r[0].strip() or r[0].strip().startswith("&nbsp"):
            continue
        name = r[0].strip()
        if name in ("구시군명", "정당별 득표율 (%)"):
            continue
        votes = {}
        ok = False
        for i, p in cols:
            if i < len(r):
                v = r[i].replace(",", "")
                if v.isdigit():
                    votes[p] = int(v)
                    ok = ok or int(v) > 0
        if ok:
            out[name] = votes
    return out


def collect_metro():
    """광역비례(8) — 시도별 합계행. 광주+전남은 합산 통합(정수12)."""
    mag = {x["sdName"]: (x["sggName"], int(x.get("sggJungsu") or 0))
           for x in json.loads((CODES / "sgType_8.json").read_text(encoding="utf-8"))}
    party = defaultdict(int)
    by_sido = {}
    seats_total = 0
    winner_h = []

    # 광주+전남 통합 합산. 명부는 '광주광역시' sdName로 통합 제출(전남 별도 없음).
    gj = parse_rows(F._vccp_rows(EID, "8", F._SIDO_CITYCODE["광주광역시"], "VCCP09_#8") or [])
    time.sleep(0.15)
    jn = parse_rows(F._vccp_rows(EID, "8", F._SIDO_CITYCODE["전라남도"], "VCCP09_#8") or [])
    comb = defaultdict(int)
    for d in (gj.get("합계", {}), jn.get("합계", {})):
        for k, v in d.items():
            comb[k] += v
    gj_seats = mag.get("광주광역시", (None, 0))[1]  # 통합 정수 12
    a = allocate(dict(comb), gj_seats)
    by_sido["전남광주통합특별시"] = dict(sorted(a.items(), key=lambda kv: -kv[1]))
    for p, n in a.items():
        party[p] += n
    seats_total += sum(a.values())
    winner_h += winners_by_roster(fetch_roster("8", "광주광역시"), a)

    for sd, code in F._SIDO_CITYCODE.items():
        if sd in ("광주광역시", "전라남도"):
            continue
        sgg, seats = mag.get(sd, (None, 0))
        if not seats:
            continue
        rows = F._vccp_rows(EID, "8", code, "VCCP09_#8")
        tot = parse_rows(rows or []).get("합계", {})
        a = allocate(tot, seats)
        by_sido[sd] = dict(sorted(a.items(), key=lambda kv: -kv[1]))
        for p, n in a.items():
            party[p] += n
        seats_total += sum(a.values())
        winner_h += winners_by_roster(fetch_roster("8", sd), a)
        time.sleep(0.15)

    return {
        "label": "광역의원(비례대표)",
        "sg_type_code": "8",
        "total_seats": seats_total,
        "expected_seats": sum(s for _, s in mag.values()),
        "party": dict(sorted(party.items(), key=lambda kv: -kv[1])),
        "by_sido": by_sido,
        "winner_huboids": sorted(set(winner_h)),
        "note": "헤어식 배분(5% 봉쇄·2/3 상한). 광주+전남은 통합특별시로 합산(정수12). "
                "당선자=정당 배분의석만큼 명부 순번(num) 상위.",
    }


def parse_basic(rows):
    """기초비례(9) — 선거구별 3행 블록(헤더행에 정당, 다음 행에 득표).
    {sgg: {정당:득표}} (경합) 또는 {sgg: None} (무투표선거구 라벨). sgg는 접미사 제거."""
    out = {}
    i = 0
    while i < len(rows):
        r = rows[i]
        if r and DEM in r and r[0].strip() and not r[0].strip().startswith("&nbsp"):
            raw = r[0].strip()
            sgg = raw.split("(")[0].strip()   # '곡성군(무투표선거구)' → '곡성군'
            if "무투표" in raw:
                out[sgg] = None               # 무투표 — 등록 명부로 배분
                i += 1
                continue
            cols = _party_cols(r)
            if i + 1 < len(rows):
                vr = rows[i + 1]
                votes = {}
                for idx, p in cols:
                    if idx < len(vr):
                        v = vr[idx].replace(",", "")
                        if v.isdigit():
                            votes[p] = int(v)
                if any(v > 0 for v in votes.values()):
                    out[sgg] = votes
            i += 2
        else:
            i += 1
    return out


def collect_basic():
    """기초비례(9) — 경합은 VCCP 득표 헤어식 배분, 무투표는 등록 정당명부 전원 당선."""
    rows_code = json.loads((CODES / "sgType_9.json").read_text(encoding="utf-8"))
    mag = {(x["sdName"], x["sggName"]): int(x.get("sggJungsu") or 0) for x in rows_code}
    sidos = sorted({sd for sd, _ in mag})
    # 후보 등록자료(정당명부) — 무투표 판정·집계용. 광주/전남 통합 재배정.
    sgg2sd = {sgg: sd for (sd, sgg) in mag if sd in ("광주광역시", "전라남도")}
    cands = CS.load_candidates_by_sgg("9", sgg2sd)   # (sd,sgg) -> [후보(명부 등재자)]
    # VCCP 경합 득표 수집
    vbysgg = {}
    for sd in sidos:
        code = F._SIDO_CITYCODE.get(sd)
        if not code:
            continue
        for sgg, votes in parse_basic(F._vccp_rows(EID, "9", code, "VCCP09_#9") or []).items():
            vbysgg[(sd, sgg)] = votes
        time.sleep(0.15)

    party = defaultdict(int)
    by_sido = defaultdict(lambda: defaultdict(int))
    seats_total = 0
    n_contested = n_uncontested = n_missing = 0

    MISSING = object()
    winner_h = []
    for (sd, sgg), seats in mag.items():
        if not seats:
            continue
        v = vbysgg.get((sd, sgg), MISSING)
        cl = cands.get((sd, sgg), [])
        contested = (v is not MISSING and v is not None and bool(v))
        if contested:
            n_contested += 1
            a = allocate(v, seats)
            for p, k in a.items():
                party[p] += k
                by_sido[sd][p] += k
                seats_total += k
            winner_h += winners_by_roster(cl, a)   # 정당 배분의석만큼 명부 num순 상위
        else:
            # 무투표(VCCP '무투표선거구' 라벨 또는 VCCP 부재) — 등록 명부순 정수까지 당선
            if not cl:
                n_missing += 1
                continue
            n_uncontested += 1
            for c in sorted(cl, key=lambda x: int(x.get("num") or 0))[:seats]:
                p = c.get("jdName") or "무소속"
                party[p] += 1
                by_sido[sd][p] += 1
                seats_total += 1
                winner_h.append(str(c.get("huboid")))

    return {
        "label": "기초의원(비례대표)",
        "sg_type_code": "9",
        "total_seats": seats_total,
        "expected_seats": sum(mag.values()),
        "districts": n_contested + n_uncontested,
        "contested": n_contested,
        "uncontested": n_uncontested,
        "missing_districts": n_missing,
        "party": dict(sorted(party.items(), key=lambda kv: -kv[1])),
        "by_sido": {sd: dict(sorted(d.items(), key=lambda kv: -kv[1])) for sd, d in by_sido.items()},
        "winner_huboids": sorted(set(winner_h)),
        "note": "경합=VCCP 헤어식 배분(5%봉쇄·2/3상한), 무투표=등록 정당명부 전원 당선. "
                "당선자=정당 배분의석만큼 명부 순번(num) 상위.",
    }


def main():
    data = json.loads(SEATS.read_text(encoding="utf-8"))
    print("[8] 광역의원 비례…", file=sys.stderr)
    m = collect_metro()
    print(f"  → {m['total_seats']}/{m['expected_seats']}석 · " +
          " ".join(f"{p}:{n}" for p, n in list(m["party"].items())[:5]), file=sys.stderr)
    print("[9] 기초의원 비례…", file=sys.stderr)
    b = collect_basic()
    print(f"  → {b['total_seats']}/{b['expected_seats']}석 (경합 {b['contested']}·무투표 {b['uncontested']}·누락 {b['missing_districts']}) · " +
          " ".join(f"{p}:{n}" for p, n in list(b["party"].items())[:5]), file=sys.stderr)
    data["offices"]["8"] = m
    data["offices"]["9"] = b
    data["source"] = data.get("source", "") + " · 비례(8·9)는 VCCP 정당득표 헤어식 배분(5%봉쇄·2/3상한)."
    SEATS.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"저장: {SEATS}", file=sys.stderr)

    # 비례 당선자 huboid를 winner_huboids.json에 병합(검색·익명화 기준).
    wh_path = ROOT / "data" / "winner_huboids.json"
    wh = json.loads(wh_path.read_text(encoding="utf-8"))
    base = set(wh.get("huboids", []))
    pr = set(m["winner_huboids"]) | set(b["winner_huboids"])
    merged = base | pr
    wh["huboids"] = sorted(merged)
    wh["count"] = len(merged)
    wh["pr_count"] = len(pr)
    wh["note"] = wh.get("note", "") + " 비례 당선자 포함(명부 순번 기준)."
    wh_path.write_text(json.dumps(wh, ensure_ascii=False), encoding="utf-8")
    print(f"winner_huboids 병합: 기존 {len(base)} + 비례 {len(pr)} → {len(merged)}", file=sys.stderr)


if __name__ == "__main__":
    main()
