#!/usr/bin/env python3
"""당선자 huboid 집합 생성 → data/winner_huboids.json.

전과 등 후보 정보공개에서 당선자만 실명, 낙선자는 익명 처리하기 위한 기준.
당선자 키(직책|시도|선거구|이름)를 candidate_details로 huboid 변환한다.

함정: candidate_details는 광주·전남 광역의원/기초의원(5·6)을 sdName='전남광주통합특별시'로
묶어 반환한다. 선거구 의원정수 코드(sgType_5/6.json)의 (선거구→시도)로 실제 광주/전남에
되돌려 매칭한다.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CODES = ROOT / "data" / "codes" / "20260603" / "constituencies"
DET = ROOT / "data" / "candidate_details.json"
CUR = ROOT / "data" / "live_counting" / "current.json"
CC = ROOT / "data" / "live_counting" / "council_candidates.json"
OUT = ROOT / "data" / "winner_huboids.json"

_k = lambda t, sd, sgg, nm: f"{t}|{sd}|{sgg}|{nm}"


def main():
    # 광주/전남 선거구→시도 (통합특별시 되돌리기용).
    # 주의: '동구제1선거구' 등 일반명이 다른 시도와 겹치므로, 코드 '행' 단위로 광주/전남만
    # 먼저 거른 뒤 매핑한다(딕셔너리 덮어쓰기 방지). 광주+전남 내에서 선거구명은 유일.
    sgg2sd = {}
    for t in ("5", "6"):
        data = json.loads((CODES / f"sgType_{t}.json").read_text(encoding="utf-8"))
        for x in data:
            if x["sdName"] in ("광주광역시", "전라남도"):
                sgg2sd[(t, x["sggName"])] = x["sdName"]

    # candidate_details → huboid 맵
    det = json.loads(DET.read_text(encoding="utf-8")).get("details", [])
    hub = {}
    for d in det:
        t = str(d.get("sgTypecode"))
        sd = d.get("sdName")
        sgg = d.get("sggName") or sd
        nm = d.get("name")
        if sd == "전남광주통합특별시":
            sd = sgg2sd.get((t, sgg), sd)  # 광주/전남으로 되돌림
        hub[_k(t, sd, sgg, nm)] = d.get("huboid")

    # 당선자 키 수집
    winners = []
    cur = json.loads(CUR.read_text(encoding="utf-8"))
    for r in cur.get("races", []):
        t = str(r.get("sg_type_code"))
        if t in ("3", "4", "11", "2"):
            c1 = (r.get("candidates") or [{}])[0]
            if c1.get("name"):
                winners.append(_k(t, r.get("sd_name"), r.get("sgg_name") or r.get("sd_name"), c1["name"]))
    cc = json.loads(CC.read_text(encoding="utf-8"))
    for c in cc.get("cands", []):
        if c.get("w") == 1:
            winners.append(_k(c["t"], c["sd"], c["sg"], c["n"]))

    wh, miss = set(), []
    for w in winners:
        h = hub.get(w)
        if h:
            wh.add(str(h))
        else:
            miss.append(w)

    OUT.write_text(json.dumps({"sgId": "20260603", "count": len(wh),
                               "note": "당선자 huboid. 후보 정보공개 익명처리 기준(당선=실명·낙선=성만).",
                               "huboids": sorted(wh)}, ensure_ascii=False),
                   encoding="utf-8")
    print(f"당선자 키 {len(winners)} → huboid {len(wh)} · 미매칭 {len(miss)}", file=sys.stderr)
    if miss:
        print("  미매칭 샘플:", miss[:8], file=sys.stderr)
    print(f"저장: {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
