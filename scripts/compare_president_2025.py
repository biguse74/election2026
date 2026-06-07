# -*- coding: utf-8 -*-
"""2025 21대 대선(20250603) 시군구별 사전/당일/전체 투표율 ↔ 이재명·김문수 득표 상관.
지방선거(2026)와 같은 방식으로 계산해 비교. 선관위 OpenAPI 직접 호출.
출력: data/live_counting/turnout_party_pres25.json + 콘솔 비교표
"""
import json
import urllib.request
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parent.parent
KEY = (ROOT / "data" / ".nec_api_key").read_text(encoding="utf-8").strip()
BASE = "http://apis.data.go.kr/9760000/VoteXmntckInfoInqireService2"
SGID = "20250603"
SIDO = {  # 2자리 sidoCode
    "서울특별시": "11", "부산광역시": "26", "대구광역시": "27", "인천광역시": "28",
    "광주광역시": "29", "대전광역시": "30", "울산광역시": "31", "세종특별자치시": "51",
    "경기도": "41", "강원특별자치도": "52", "충청북도": "43", "충청남도": "44",
    "전북특별자치도": "53", "전라남도": "46", "경상북도": "47", "경상남도": "48",
    "제주특별자치도": "49",
}
DEM, CON = "더불어민주당", "국민의힘"


def call_all(op):
    """전 페이지 수집. 개표/투표율 API는 sidoCode를 무시하고 전국 시군구를 반환한다."""
    out, page = [], 1
    while True:
        q = urlencode({"serviceKey": KEY, "sgId": SGID, "sgTypecode": "1",
                       "numOfRows": "1000", "pageNo": str(page), "resultType": "json"})
        with urllib.request.urlopen(f"{BASE}/{op}?{q}", timeout=60) as r:
            body = json.load(r)["response"]["body"]
        items = (body.get("items") or {}).get("item") or []
        items = items if isinstance(items, list) else [items]
        out += items
        total = int(body.get("totalCount") or 0)
        if len(out) >= total or not items:
            break
        page += 1
    return out


def num(x):
    try:
        return int(str(x).replace(",", ""))
    except (ValueError, TypeError):
        return 0


def main():
    # (시도, 시군구) 쌍으로 매칭 — 동명 시군구(남구·중구 등) 시도 넘나듦 방지.
    skip = {"합계", "관외", "국외부재자", "선상투표"}
    turn = {}
    for it in call_all("getVoteSttusInfoInqire"):
        sd, wiw = it.get("sdName"), it.get("wiwName")
        if sd and wiw and sd != "합계" and wiw not in skip:
            turn[(sd, wiw)] = it
    pts = []
    for it in call_all("getXmntckSttusInfoInqire"):
        sd, wiw = it.get("sdName"), it.get("wiwName")
        if not sd or not wiw or sd == "합계" or wiw in skip or (sd, wiw) not in turn:
            continue
        dem = con = 0
        for i in range(1, 51):
            n = f"{i:02d}"
            jd = it.get("jd" + n)
            if jd == DEM:
                dem = num(it.get("dugsu" + n))
            elif jd == CON:
                con = num(it.get("dugsu" + n))
        yu = num(it.get("yutusu"))
        t = turn[(sd, wiw)]
        ev = num(t.get("totSunsu"))
        if yu <= 0 or ev <= 0:
            continue
        if True:
            pts.append({
                "sd": sd, "sgg": wiw,
                "early": round(num(t.get("psEtcTusu")) / ev * 100, 1),   # 사전+거소 등
                "day": round(num(t.get("psTusu")) / ev * 100, 1),         # 당일 본투표소
                "total": float(t.get("turnout") or 0),
                "dem": round(dem / yu * 100, 1), "con": round(con / yu * 100, 1),
                "win": DEM if dem >= con else CON,
            })

    def pear(xs, ys):
        n = len(xs)
        mx, my = sum(xs) / n, sum(ys) / n
        cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
        sx = sum((x - mx) ** 2 for x in xs) ** .5
        sy = sum((y - my) ** 2 for y in ys) ** .5
        return round(cov / (sx * sy), 3) if sx * sy else None

    col = lambda k: [p[k] for p in pts]
    corr = {"day_con": pear(col("day"), col("con")), "early_con": pear(col("early"), col("con")),
            "early_day": pear(col("early"), col("day")), "early_dem": pear(col("early"), col("dem")),
            "total_dem": pear(col("total"), col("dem"))}
    out = ROOT / "data" / "live_counting" / "turnout_party_pres25.json"
    out.write_text(json.dumps({"points": pts, "corr": corr, "unit": "21대 대선 시군구",
                               "election": "2025 대선"}, ensure_ascii=False), encoding="utf-8")
    print(f"2025 대선 시군구 {len(pts)}곳 → {out.name}")
    for k, v in corr.items():
        print(f"  {k}: r={v}")
    import statistics as st
    dw = [p for p in pts if p["dem"] > p["con"]]
    cw = [p for p in pts if p["con"] > p["dem"]]
    print(f"이재명 우세 {len(dw)}곳 평균 사전 {st.mean(p['early'] for p in dw):.1f}% · 당일 {st.mean(p['day'] for p in dw):.1f}%")
    print(f"김문수 우세 {len(cw)}곳 평균 사전 {st.mean(p['early'] for p in cw):.1f}% · 당일 {st.mean(p['day'] for p in cw):.1f}%")


if __name__ == "__main__":
    main()
