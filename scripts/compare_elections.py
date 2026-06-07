# -*- coding: utf-8 -*-
"""4개 선거(2022 지선·2024 총선·2025 대선·2026 지선) 시군구 단위
사전/당일 투표율 ↔ 민주(진보)·국힘(보수) 득표 상관을 동일 방식으로 비교.

선관위 OpenAPI(VoteXmntckInfoInqireService2) 직접 호출:
  getVoteSttusInfoInqire   투표율(사전 psEtc·당일 ps·전체) by 시군구
  getXmntckSttusInfoInqire 후보/정당 득표 by 시군구
모두 (시도,시군구) 쌍으로 매칭(동명 시군구 방지), 시군구 내 여러 선거구는 합산.

출력: data/live_counting/turnout_party_multi.json  + 콘솔 비교표
사용: python scripts/compare_elections.py
"""
import json
import urllib.request
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parent.parent
KEY = (ROOT / "data" / ".nec_api_key").read_text(encoding="utf-8").strip()
BASE = "http://apis.data.go.kr/9760000/VoteXmntckInfoInqireService2"
DEM, CON = "더불어민주당", "국민의힘"
SKIP = {"합계", "관외", "국외부재자", "선상투표", "거소투표"}

# 비교 대상: 진영대결 핵심 race(대선=대통령, 총선=지역구, 지선=시도지사)
# 2026 공식 OpenAPI는 선거 직후라 미공개 → 라이브(current.json)로 별도 합류.
# 지선은 양해 비교 위해 기초단체장(type 4)으로 통일.
ELECTIONS = [
    {"key": "2022지선", "sgId": "20220601", "type": "4", "label": "2022 지방선거(기초단체장)"},
    {"key": "2024총선", "sgId": "20240410", "type": "2", "label": "2024 총선(지역구)"},
    {"key": "2025대선", "sgId": "20250603", "type": "1", "label": "2025 대선"},
]


def num(x):
    try:
        return int(str(x).replace(",", ""))
    except (ValueError, TypeError):
        return 0


ER_BASE = "http://apis.data.go.kr/9760000/ErVotingSttusInfoInqireService"


def _pages(url_base, base_params):
    out, page = [], 1
    while True:
        q = urlencode({**base_params, "serviceKey": KEY, "numOfRows": "1000",
                       "pageNo": str(page), "resultType": "json"})
        with urllib.request.urlopen(f"{url_base}?{q}", timeout=60) as r:
            resp = json.load(r)["response"]
        if not resp.get("body"):
            break  # 데이터 없음(헤더만)
        body = resp["body"]
        items = (body.get("items") or {}).get("item") or []
        items = items if isinstance(items, list) else [items]
        out += items
        if len(out) >= int(body.get("totalCount") or 0) or not items:
            break
        page += 1
    return out


def call_all(op, sgid, sgtype):
    return _pages(f"{BASE}/{op}", {"sgId": sgid, "sgTypecode": sgtype})


def call_er(sgid):
    # 사전투표 1·2일차 합산 사전투표자 by 시군구. (div=2는 2일차 단독 → 합산 필요)
    agg = {}
    for div in ("1", "2"):
        for it in _pages(f"{ER_BASE}/getErVotingSttusInfoInqire", {"sgId": sgid, "erVotingDiv": div}):
            sd, wiw = it.get("sdName"), it.get("wiwName")
            if not sd or not wiw:
                continue
            a = agg.setdefault((sd, wiw), {"sdName": sd, "wiwName": wiw, "cnt": 0, "voters": 0})
            a["cnt"] += num(it.get("erVotingCnt"))
            a["voters"] = num(it.get("votersCnt")) or a["voters"]
    return list(agg.values())


def pear(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sx = sum((x - mx) ** 2 for x in xs) ** .5
    sy = sum((y - my) ** 2 for y in ys) ** .5
    return round(cov / (sx * sy), 3) if sx * sy else None


def fetch_election(e):
    # 사전투표율(최종) by 시군구
    early = {}
    for it in call_er(e["sgId"]):
        sd, wiw = it.get("sdName"), it.get("wiwName")
        if sd and wiw and sd != "합계" and wiw not in SKIP and it.get("voters", 0) > 0:
            early[(sd, wiw)] = round(it["cnt"] / it["voters"] * 100, 1)   # 사전율(1+2일차)
    # 개표: 시군구별 민주·국힘·유효 + 선거인·투표(전체 투표율용). 총선 다선거구는 합산.
    agg = {}
    for it in call_all("getXmntckSttusInfoInqire", e["sgId"], e["type"]):
        sd, wiw = it.get("sdName"), it.get("wiwName")
        if not sd or not wiw or sd == "합계" or wiw in SKIP:
            continue
        dem = con = 0
        for i in range(1, 51):
            n = f"{i:02d}"
            jd = it.get("jd" + n)
            if jd == DEM:
                dem += num(it.get("dugsu" + n))
            elif jd == CON:
                con += num(it.get("dugsu" + n))
        a = agg.setdefault((sd, wiw), {"dem": 0, "con": 0, "yu": 0, "sunsu": 0, "tusu": 0})
        a["dem"] += dem; a["con"] += con; a["yu"] += num(it.get("yutusu"))
        a["sunsu"] += num(it.get("sunsu")); a["tusu"] += num(it.get("tusu"))
    pts = []
    for k, a in agg.items():
        er = early.get(k)
        if er is None or a["yu"] <= 0 or a["sunsu"] <= 0:
            continue
        total = round(a["tusu"] / a["sunsu"] * 100, 1)     # 전체 투표율
        day = round(total - er, 1)                          # 당일 = 전체 − 사전
        pts.append({"sd": k[0], "sgg": k[1],
                    "early": round(er, 1), "day": day, "total": total,
                    "dem": round(a["dem"] / a["yu"] * 100, 1),
                    "con": round(a["con"] / a["yu"] * 100, 1),
                    "win": DEM if a["dem"] >= a["con"] else CON})
    col = lambda kk: [p[kk] for p in pts]
    corr = {"early_dem": pear(col("early"), col("dem")), "early_con": pear(col("early"), col("con")),
            "day_dem": pear(col("day"), col("dem")), "day_con": pear(col("day"), col("con")),
            "early_day": pear(col("early"), col("day")), "total_dem": pear(col("total"), col("dem"))}
    return {"key": e["key"], "label": e["label"], "n": len(pts), "corr": corr, "points": pts}


def main():
    import statistics as st
    res = []
    for e in ELECTIONS:
        print(f"… {e['label']} 수집 중", flush=True)
        res.append(fetch_election(e))
    # 2026 지선: 공식 OpenAPI 미공개 → 라이브 기반 turnout_party.json(기초단체장 224곳) 합류
    tp = ROOT / "data" / "live_counting" / "turnout_party.json"
    if tp.exists():
        d = json.loads(tp.read_text(encoding="utf-8"))
        pts = d["points"]
        col = lambda kk: [p[kk] for p in pts]
        res.append({"key": "2026지선", "label": "2026 지방선거(기초단체장)", "n": len(pts),
                    "corr": {"early_dem": pear(col("early"), col("dem")), "early_con": pear(col("early"), col("con")),
                             "day_dem": pear(col("day"), col("dem")), "day_con": pear(col("day"), col("con")),
                             "early_day": pear(col("early"), col("day")), "total_dem": pear(col("total"), col("dem"))},
                    "points": pts})
    out = ROOT / "data" / "live_counting" / "turnout_party_multi.json"
    # 웹 공개용: 점 데이터 제외(상관계수·요약만) — 가볍게.
    import statistics as _st
    web = []
    for r in res:
        dw = [p for p in r["points"] if p["dem"] > p["con"]]
        cw = [p for p in r["points"] if p["con"] > p["dem"]]
        # 산점도용 점은 가볍게(소수점 좌표·필요필드만)
        pts = [{"e": p["early"], "d": p["day"], "m": p["dem"], "c": p["con"], "w": p["win"]} for p in r["points"]]
        web.append({"key": r["key"], "label": r["label"], "n": r["n"], "corr": r["corr"], "points": pts,
                    "dem_win": {"n": len(dw), "early": round(_st.mean(p["early"] for p in dw), 1) if dw else None,
                                "day": round(_st.mean(p["day"] for p in dw), 1) if dw else None},
                    "con_win": {"n": len(cw), "early": round(_st.mean(p["early"] for p in cw), 1) if cw else None,
                                "day": round(_st.mean(p["day"] for p in cw), 1) if cw else None}})
    out.write_text(json.dumps({"elections": web}, ensure_ascii=False), encoding="utf-8")
    print(f"\n→ {out.name}\n")
    hdr = f"{'선거':22} {'n':>4} {'사전↔민주':>9} {'사전↔국힘':>9} {'당일↔민주':>9} {'당일↔국힘':>9} {'사전↔당일':>9}"
    print(hdr); print("-" * len(hdr))
    fnum = lambda v: "  n/a" if v is None else f"{v:>+.2f}"
    for r in res:
        c = r["corr"]
        print(f"{r['label']:22} {r['n']:>4} {fnum(c['early_dem']):>9} {fnum(c['early_con']):>9} {fnum(c['day_dem']):>9} {fnum(c['day_con']):>9} {fnum(c['early_day']):>9}")
    print("\n[진영별 평균 사전/당일 투표율]")
    for r in res:
        dw = [p for p in r["points"] if p["dem"] > p["con"]]
        cw = [p for p in r["points"] if p["con"] > p["dem"]]
        if dw and cw:
            print(f"  {r['label']:22} 민주우세 사전{st.mean(p['early'] for p in dw):.1f}/당일{st.mean(p['day'] for p in dw):.1f}"
                  f"  ·  국힘우세 사전{st.mean(p['early'] for p in cw):.1f}/당일{st.mean(p['day'] for p in cw):.1f}")


if __name__ == "__main__":
    main()
