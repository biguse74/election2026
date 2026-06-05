# -*- coding: utf-8 -*-
"""정당별 공천 효율(당선율) 집계 → data/party_efficiency.json.

4분면(광역장·기초장·광역의원·기초의원) × 정당 × {무투표 포함 / 경합만}.
  - 출마자 = 후보 등록(status='등록') 스냅샷.
  - 당선 = data/winner_huboids.json.
  - 무투표 = 선거구별 등록후보수 ≤ 의원정수(단독선출은 정수1).
  - 비례·교육감·재보궐은 제외(명부/소수 표본이라 '출마-당선' 효율과 성격이 다름).

전남광주통합특별시 함정: 5·6 후보가 sd='전남광주통합특별시'로 묶여 정수 매칭이 깨지므로
선거구 코드의 (sgg→sd)로 광주/전남에 되돌려 매칭한다.
사용: python scripts/build_party_efficiency.py
"""
import glob
import json
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CD = ROOT / "data" / "codes" / "20260603" / "constituencies"
WH = ROOT / "data" / "winner_huboids.json"
OUT = ROOT / "data" / "party_efficiency.json"

QUAD = [("3", "gov", "광역장", "시도지사"), ("4", "head", "기초장", "구시군장"),
        ("5", "metro", "광역의원", "시도의원 지역구"), ("6", "basic", "기초의원", "구시군의원 지역구"),
        ("2", "byelect", "국회 재보궐", "국회의원 재·보궐")]
QMAP = {t: (key, label, sub) for t, key, label, sub in QUAD}
# 표시 정당(고정 순서). 나머지는 '기타'로 합산.
SHOW = ["더불어민주당", "국민의힘", "무소속", "조국혁신당", "진보당", "정의당", "개혁신당", "녹색당"]


def main():
    snap = sorted(glob.glob(str(ROOT / "data/candidates/20260603/snapshot_*.json")))[-1]
    reg = [c for c in json.loads(Path(snap).read_text(encoding="utf-8"))["candidates"]
           if str(c.get("status")) == "등록"]
    winners = set(json.loads(WH.read_text(encoding="utf-8"))["huboids"])

    mag, sgg2sd = {}, {}
    for t in ("5", "6"):
        for x in json.loads((CD / f"sgType_{t}.json").read_text(encoding="utf-8")):
            mag[(t, x["sdName"], x["sggName"])] = int(x.get("sggJungsu") or 0)
            if x["sdName"] in ("광주광역시", "전라남도"):
                sgg2sd[(t, x["sggName"])] = x["sdName"]

    def magnitude(t, sd, sgg):
        return 1 if t in ("2", "3", "4") else mag.get((t, sd, sgg), 0)

    # 선거구별 후보 그룹(무투표 판정용)
    races = defaultdict(list)
    for c in reg:
        t = str(c.get("sgTypecode"))
        if t not in QMAP:
            continue
        sd = c.get("sdName")
        sgg = c.get("sggName") or sd
        if sd == "전남광주통합특별시":
            sd = sgg2sd.get((t, sgg), sd)
        races[(t, sd, sgg)].append(c)

    # 집계: quad → party → counts
    stat = defaultdict(lambda: defaultdict(lambda: {"run": 0, "win": 0, "runC": 0, "winC": 0}))
    for (t, sd, sgg), cl in races.items():
        uncontested = len(cl) <= magnitude(t, sd, sgg)
        for c in cl:
            p = c.get("jdName") or "무소속"
            key = p if p in SHOW else "기타"
            w = 1 if str(c.get("huboid")) in winners else 0
            s = stat[t][key]
            s["run"] += 1
            s["win"] += w
            if not uncontested:
                s["runC"] += 1
                s["winC"] += w

    quadrants = []
    for t, key, label, sub in QUAD:
        order = [p for p in SHOW if stat[t].get(p, {}).get("run")] + (["기타"] if stat[t].get("기타", {}).get("run") else [])
        parties = [{"p": p, **stat[t][p]} for p in order]
        tot_run = sum(s["run"] for s in stat[t].values())
        tot_win = sum(s["win"] for s in stat[t].values())
        quadrants.append({"key": key, "label": label, "sub": sub,
                          "total_run": tot_run, "total_win": tot_win, "parties": parties})

    OUT.write_text(json.dumps({
        "note": "정당별 당선율. 출마=등록후보, 당선=winner_huboids, 무투표=후보수≤정수. "
                "경합만(C)은 무투표 선거구 제외. 비례·교육감 제외(지역구 단독선출+의원+국회재보궐).",
        "quadrants": quadrants,
    }, ensure_ascii=False, indent=1), encoding="utf-8")
    for q in quadrants:
        print(f"[{q['label']}] {q['total_win']}/{q['total_run']}", file=sys.stderr)
        for p in q["parties"][:4]:
            r = f"{p['win']}/{p['run']}" + (f" · 경합 {p['winC']}/{p['runC']}" if p['runC'] != p['run'] else "")
            print(f"   {p['p']}: {r}", file=sys.stderr)


if __name__ == "__main__":
    main()
