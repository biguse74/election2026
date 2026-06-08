# -*- coding: utf-8 -*-
"""무소속·정당이동 기초단체장 사례 수집 (2022·2026).

2022: 선관위 OpenAPI(getXmntck, type4) 시군구별 후보.
2026: data/live_counting/current.json (라이브, type4).
추출: (A)무소속 당선  (B)민주/국힘 무공천  (C)동일후보 정당변경(2022↔2026).
2026 사전/당일 투표율 결합(turnout_party.json). 계열확인(웹검색)은 다음 단계.

출력: data/research/independent_heads.json (+ CSV는 별도 단계)
사용: python scripts/research_independent_heads.py
"""
import json
import urllib.request
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parent.parent
KEY = (ROOT / "data" / ".nec_api_key").read_text(encoding="utf-8").strip()
BASE = "http://apis.data.go.kr/9760000/VoteXmntckInfoInqireService2/getXmntckSttusInfoInqire"
OUTDIR = ROOT / "data" / "research"
OUTDIR.mkdir(parents=True, exist_ok=True)

HONAM = {"전북특별자치도", "전라북도", "전라남도", "광주광역시"}
YEONGNAM = {"부산광역시", "대구광역시", "울산광역시", "경상남도", "경상북도"}
DEM, CON, IND = "더불어민주당", "국민의힘", "무소속"


SD_NORM = {"전라북도": "전북특별자치도", "강원도": "강원특별자치도"}


def nsd(sd):
    return SD_NORM.get(sd, sd)


def region(sd):
    sd = nsd(sd)
    return "호남" if sd in HONAM else ("영남" if sd in YEONGNAM else "기타")


def num(x):
    try:
        return int(str(x).replace(",", ""))
    except (ValueError, TypeError):
        return 0


def fetch_2022():
    out, page, seen = {}, 1, 0
    while True:
        q = urlencode({"serviceKey": KEY, "sgId": "20220601", "sgTypecode": "4",
                       "numOfRows": "100", "pageNo": str(page), "resultType": "json"})
        with urllib.request.urlopen(f"{BASE}?{q}", timeout=60) as r:
            b = json.load(r)["response"]["body"]
        items = (b.get("items") or {}).get("item") or []
        items = items if isinstance(items, list) else [items]
        seen += len(items)
        for it in items:
            sd, sgg = it.get("sdName"), it.get("sggName")
            # 시군구 합계 행만(sdName=시도·wiwName=합계). 전국합계(sdName=합계) 제외.
            if it.get("wiwName") != "합계" or not sd or sd == "합계" or not sgg:
                continue
            cands = []
            for i in range(1, 51):
                n = f"{i:02d}"
                nm = it.get("hbj" + n)
                if nm:
                    cands.append({"name": nm, "party": it.get("jd" + n) or "", "votes": num(it.get("dugsu" + n))})
            if cands:
                out[(nsd(sd), sgg)] = cands
        if not items or seen >= int(b.get("totalCount") or 0):
            break
        page += 1
    return out


def load_2026():
    cur = json.loads((ROOT / "data" / "live_counting" / "current.json").read_text(encoding="utf-8"))
    out = {}
    for r in cur["races"]:
        if str(r.get("sg_type_code")) != "4":
            continue
        cs = [{"name": c.get("name"), "party": c.get("jd_name") or "", "votes": c.get("votes") or 0}
              for c in (r.get("candidates") or []) if c.get("name")]
        if cs:
            out[(nsd(r.get("sd_name")), r.get("sgg_name"))] = cs
    return out


def winner(cands):
    return max(cands, key=lambda c: c["votes"]) if cands else None


def parties(cands):
    return {c["party"] for c in cands}


def main():
    c22, c26 = fetch_2022(), load_2026()
    print(f"2022 기초단체장 {len(c22)}곳 · 2026 {len(c26)}곳", flush=True)

    turn = {}
    tp = ROOT / "data" / "live_counting" / "turnout_party.json"
    if tp.exists():
        for p in json.loads(tp.read_text(encoding="utf-8"))["points"]:
            turn[(p["sd"], p["sgg"])] = {"early": p["early"], "day": p["day"]}

    def tot(cands):
        return sum(c["votes"] for c in cands) or 1

    # (A) 무소속 당선
    ind_wins = {"2022": [], "2026": []}
    for yr, data in (("2022", c22), ("2026", c26)):
        for (sd, sgg), cs in data.items():
            w = winner(cs)
            if w and w["party"] == IND:
                ind_wins[yr].append({"권역": region(sd), "시도": sd, "시군구": sgg, "후보명": w["name"],
                                     "득표율": round(w["votes"] / tot(cs) * 100, 1)})

    # (B) 무공천(민주/국힘 후보 없음)
    no_nom = {"2022": [], "2026": []}
    for yr, data in (("2022", c22), ("2026", c26)):
        for (sd, sgg), cs in data.items():
            ps = parties(cs)
            miss = [p for p in (DEM, CON) if p not in ps]
            if miss:
                no_nom[yr].append({"권역": region(sd), "시도": sd, "시군구": sgg, "무공천": "·".join(miss),
                                   "당선정당": (winner(cs) or {}).get("party")})

    # (C) 동일후보 정당변경 — 같은 시군구 + 후보명 일치 우선
    changers = []
    for (sd, sgg), cs26 in c26.items():
        cs22 = c22.get((sd, sgg))
        if not cs22:
            continue
        by22 = {c["name"]: c for c in cs22}
        for c in cs26:
            o = by22.get(c["name"])
            if o and o["party"] != c["party"]:
                w22, w26 = winner(cs22), winner(cs26)
                changers.append({
                    "권역": region(sd), "시도": sd, "시군구": sgg, "후보명": c["name"],
                    "2022_정당": o["party"], "2022_당락": "당선" if w22 and w22["name"] == c["name"] else "낙선",
                    "2022_득표율": round(o["votes"] / tot(cs22) * 100, 1),
                    "2026_정당": c["party"], "2026_당락": "당선" if w26 and w26["name"] == c["name"] else "낙선",
                    "2026_득표율": round(c["votes"] / tot(cs26) * 100, 1),
                    "사전투표율": turn.get((sd, sgg), {}).get("early"),
                    "당일투표율": turn.get((sd, sgg), {}).get("day"),
                    "방향": f"{o['party']}→{c['party']}", "매칭확신도": "중(동명+동일시군구)",
                })

    payload = {"무소속당선": ind_wins, "무공천": no_nom, "정당변경동일후보": changers}
    (OUTDIR / "independent_heads.json").write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    # 콘솔 요약
    for yr in ("2022", "2026"):
        from collections import Counter
        rc = Counter(x["권역"] for x in ind_wins[yr])
        print(f"\n[{yr} 무소속 당선] 총 {len(ind_wins[yr])} · 호남 {rc['호남']} 영남 {rc['영남']} 기타 {rc['기타']}")
    print(f"\n[정당변경 동일후보] {len(changers)}명")
    from collections import Counter
    dc = Counter(x["방향"] for x in changers)
    for d, n in dc.most_common():
        print(f"  {d}: {n}")
    print("\n[정당변경 상세]")
    for x in sorted(changers, key=lambda z: (z["권역"], z["시도"])):
        print(f"  {x['권역']} {x['시도']} {x['시군구']} {x['후보명']}: {x['방향']} "
              f"(22 {x['2022_당락']}{x['2022_득표율']}% → 26 {x['2026_당락']}{x['2026_득표율']}%) 사전{x['사전투표율']}")
    print(f"\n→ {OUTDIR / 'independent_heads.json'}")


if __name__ == "__main__":
    main()
