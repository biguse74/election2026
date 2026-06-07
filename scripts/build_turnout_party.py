# -*- coding: utf-8 -*-
"""투표율 ↔ 정당 득표 상관관계 분석 데이터 생성(시군구 단위).

기초단체장(sg_type 4) 시군구별 민주·국힘 득표율을 그 시군구의
사전/당일/전체 투표율과 매칭해, 산점도용 점과 상관계수(Pearson r)를 낸다.

⚠️ 지역 단위 생태학적 상관 — 인과 아님(농촌/도시·지역색 교란). 페이지에 경고 표기.
출력: data/live_counting/turnout_party.json
사용: python scripts/build_turnout_party.py
"""
import json
import statistics as st
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CUR = ROOT / "data" / "live_counting" / "current.json"
OUT = ROOT / "data" / "live_counting" / "turnout_party.json"


def pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sx = sum((x - mx) ** 2 for x in xs) ** 0.5
    sy = sum((y - my) ** 2 for y in ys) ** 0.5
    return round(cov / (sx * sy), 3) if sx * sy else None


def main():
    c = json.loads(CUR.read_text(encoding="utf-8"))
    bysgg = c["turnout"]["by_sigungu"]
    turn = {}
    for sd, obj in bysgg.items():
        for s in obj.get("sigungu", []):
            ev = s.get("eligible_voters") or 0
            if ev <= 0 or s.get("turnout_pct") is None:
                continue
            turn[(sd, s["name"])] = {
                "early": round((s.get("early_voters_so_far") or 0) / ev * 100, 1),
                "day": round((s.get("day_voters_so_far") or 0) / ev * 100, 1),
                "total": s.get("turnout_pct"),
            }

    pts = []
    for r in c["races"]:
        if str(r.get("sg_type_code")) != "4":
            continue
        cs = r.get("candidates") or []
        tot = sum(x.get("votes") or 0 for x in cs)
        if tot <= 0:
            continue
        t = turn.get((r.get("sd_name"), r.get("sgg_name")))
        if not t:
            continue
        dem = next((x for x in cs if x.get("jd_name") == "더불어민주당"), None)
        con = next((x for x in cs if x.get("jd_name") == "국민의힘"), None)
        pts.append({
            "sd": r["sd_name"], "sgg": r["sgg_name"],
            "early": t["early"], "day": t["day"], "total": t["total"],
            "dem": round((dem.get("votes") or 0) / tot * 100, 1) if dem else 0,
            "con": round((con.get("votes") or 0) / tot * 100, 1) if con else 0,
            "win": cs[0].get("jd_name") or "무소속",
        })

    col = lambda k: [p[k] for p in pts]
    corr = {
        "day_con": pearson(col("day"), col("con")),
        "early_con": pearson(col("early"), col("con")),
        "early_day": pearson(col("early"), col("day")),
        "early_dem": pearson(col("early"), col("dem")),
        "total_dem": pearson(col("total"), col("dem")),
        "total_con": pearson(col("total"), col("con")),
    }
    demw = [p for p in pts if p["win"] == "더불어민주당"]
    conw = [p for p in pts if p["win"] == "국민의힘"]
    mean = lambda a, k: round(st.mean(p[k] for p in a), 1) if a else None
    summary = {
        "n": len(pts),
        "dem_win": {"n": len(demw), "early": mean(demw, "early"), "day": mean(demw, "day"), "total": mean(demw, "total")},
        "con_win": {"n": len(conw), "early": mean(conw, "early"), "day": mean(conw, "day"), "total": mean(conw, "total")},
    }
    OUT.write_text(json.dumps({"points": pts, "corr": corr, "summary": summary,
                               "unit": "기초단체장 시군구", "generated": c.get("polled_at")},
                              ensure_ascii=False), encoding="utf-8")
    print(f"생성: {len(pts)}개 시군구 → {OUT.name}")
    for k, v in corr.items():
        print(f"  {k}: r={v}")


if __name__ == "__main__":
    main()
