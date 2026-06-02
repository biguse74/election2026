#!/usr/bin/env python3
"""
21대 대선(2025-06-03)·22대 총선(2024-04-10)의 시군구별 민주/국힘 득표를 받아
무폴 시군구 prior 보강용 'national_lean.json'을 만든다.

  · 대선(sgTypecode=1): 시군구 단위 그대로 (이재명 민주 vs 김문수 국힘)
  · 총선(sgTypecode=2): 지역구(선거구) 단위 → 선거구명에서 시군구 추출해 득표 합산

사용:
    set NEC_API_KEY=...        (GitHub Secrets의 그 값)
    python scripts/fetch_national_lean.py

산출물: data/national_lean.json
  { "경기도/고양시": {"pres2025":{"dem":.., "con":.., "margin":..},
                      "gen2024":{"dem":.., "con":.., "margin":..}}, ... }
"""
from __future__ import annotations
import json, os, time, glob
from collections import defaultdict
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import urlopen

BASE = "https://apis.data.go.kr/9760000/VoteXmntckInfoInqireService2/getXmntckSttusInfoInqire"
KEY = os.environ.get("NEC_API_KEY", "").strip()
ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "national_lean.json"
DEM, CON = "더불어민주당", "국민의힘"
SIDOS = ["서울특별시","부산광역시","대구광역시","인천광역시","광주광역시","대전광역시","울산광역시","세종특별자치시",
    "경기도","강원특별자치도","강원도","충청북도","충청남도","전북특별자치도","전라북도","전라남도","경상북도","경상남도","제주특별자치도","제주도"]

def sigungu_names():
    snap = sorted(glob.glob(str(ROOT/"data/candidates/20260603/snapshot_*.json")))[-1]
    cs = json.load(open(snap, encoding="utf-8"))["candidates"]
    return sorted({c["sggName"] for c in cs if str(c.get("sgTypecode"))=="4" and c.get("sggName")}, key=len, reverse=True)

def to_int(v):
    if v in (None,"","null"): return 0
    return int(str(v).replace(",","").strip() or 0)

def fetch(sgId, sgType, sdName):
    rows=[]; page=1
    while page<=50:
        q={"ServiceKey":KEY,"pageNo":page,"numOfRows":200,"resultType":"json",
           "sgId":sgId,"sgTypecode":sgType,"sdName":sdName}
        with urlopen(f"{BASE}?{urlencode(q)}", timeout=30) as r:
            p=json.loads(r.read().decode("utf-8"))
        h=p.get("response",{}).get("header",{})
        if h.get("resultCode") in ("INFO-03","ERROR-03"): return []
        if h.get("resultCode") not in ("INFO-00","00"): raise RuntimeError(f"{sdName} {h}")
        b=p.get("response",{}).get("body",{}); w=b.get("items",{})
        ch=w.get("item",[]) if isinstance(w,dict) else w
        if isinstance(ch,dict): ch=[ch]
        rows+=ch or []
        if int(b.get("totalCount",0) or 0)<=len(rows): break
        page+=1; time.sleep(0.15)
    return rows

def party_shares(row):
    valid=to_int(row.get("yutusu")); dem=con=0
    for i in range(1,51):
        s=f"{i:02d}"; jd=(row.get(f"jd{s}") or "").strip(); v=to_int(row.get(f"dugsu{s}"))
        if jd==DEM: dem+=v
        elif jd==CON: con+=v
    return dem, con, valid

def main():
    if not KEY:
        print("NEC_API_KEY 환경변수가 없습니다.  set NEC_API_KEY=...  후 다시 실행하세요."); return
    SGG = sigungu_names()
    def find(nm):
        return [s for s in SGG if s in nm]
    out = defaultdict(dict)
    # 대선 2025 — 시군구는 wiwName (sggName="대한민국"), 행정구는 부모 시로 합산
    pres = defaultdict(lambda:[0,0])
    for sd in SIDOS:
        for row in fetch("20250603","1",sd):
            nm=(row.get("wiwName") or "").strip()
            if nm in ("","합계"): continue
            hits=find(nm)
            if not hits: continue
            d,c,_=party_shares(row)
            for h in hits:
                pres[f"{norm_sd(sd)}/{h}"][0]+=d; pres[f"{norm_sd(sd)}/{h}"][1]+=c
    for k,(d,c) in pres.items():
        if d+c>0: out[k]["pres2025"]={"dem":d,"con":c,"margin":round((d-c)/(d+c)*100,1)}
    # 총선 2024 — 선거구 → 시군구 합산
    gen = defaultdict(lambda:[0,0])
    for sd in SIDOS:
        for row in fetch("20240410","2",sd):
            sgg=(row.get("sggName") or "").strip()
            if not sgg or sgg=="합계": continue
            hits=find(sgg)  # 선거구명에 포함된 시군구들
            if not hits: continue
            d,c,_=party_shares(row)
            for h in hits:  # 합구 선거구는 포함 시군구 모두에 같은 표심 배분
                gen[f"{norm_sd(sd)}/{h}"][0]+=d; gen[f"{norm_sd(sd)}/{h}"][1]+=c
    for k,(d,c) in gen.items():
        if d+c>0: out[k].setdefault("gen2024",{}).update({"dem":d,"con":c,"margin":round((d-c)/(d+c)*100,1)})
    json.dump({"generated":"2026-06-02","source":"중앙선관위 OpenAPI VoteXmntck — 21대 대선(2025)·22대 총선(2024) 시군구별 민주-국힘",
               "lean":dict(out)}, open(OUT,"w",encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"저장: {OUT.name} — 시군구 {len(out)}곳 (대선 {len(pres)}, 총선 {len(gen)})")

def norm_sd(sd):
    return {"강원도":"강원특별자치도","전라북도":"전북특별자치도","제주도":"제주특별자치도"}.get(sd,sd)

if __name__=="__main__":
    main()
