#!/usr/bin/env python3
"""
9회 기초단체장 시뮬레이션 v2 — 여론조사 반영 + 무소속 3진영 모델.

v1(과거 개표결과만, 민주 vs 보수 2진영)의 두 한계를 보완:
  1) 여론조사 반영: 시군구별 최신 '본선' 여론조사(여심위 PDF 추출)를 prior로.
  2) 3진영: 민주(D) / 보수·국힘(C) / 무소속·기타(I). 호남 민주 vs 무소속 구도 반영.

진영 판정·중심값:
  · 본선 폴 있으면  → 중심 = 폴의 (민주 − 최대비민주) 마진, 도전자 진영 = 폴 1위 비민주 정당,
                      margin ~ N(center, POLL_SIGMA).  (과거 환경효과 미적용 — 폴이 이미 현재 반영)
  · 폴 없으면        → 과거 개표(민주−보수) 회귀 모델(year_effect+region_lean+noise),
                      도전자 진영 = 국힘 있으면 C, 없으면 I.
  · 민주 후보 없음   → 민주 0%.  민주 단독(무경쟁) → 민주 100%.

입력:
  data/candidates/20260603/snapshot_*.json     (226 본선 후보 — 정당·이름)
  data/history_counting_results.json           (과거 6회차 기초단체장 개표)
  data/polls_basic_head_extracted.json         (시군구별 최신 본선 폴 추출본)

출력:
  data/prediction_basic_head_v2.json           (/live/ 연동용 — 키 4|sd|sgg → 민주확률%, 진영, 폴여부)
  exports/simulation_9th_basic_head_v2/
    per_race.csv, summary.json
"""
from __future__ import annotations
import csv, json, glob, random, statistics
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "exports" / "simulation_9th_basic_head_v2"
N_SIM = 10_000
SEED = 42
POLL_SIGMA = 7.0          # 폴 마진의 불확실성(여론조사→실제 오차+시점표류, %p)
GEN = "2026-06-02"

DEMP = {"민주당","새천년민주당","열린우리당","대통합민주신당","통합민주당","민주통합당","새정치민주연합","더불어민주당"}
CONP = {"한나라당","새누리당","자유한국당","바른정당","미래통합당","국민의힘"}
ALIAS = {"강원도":"강원특별자치도","전라북도":"전북특별자치도","제주도":"제주특별자치도"}
DEM = "더불어민주당"

def bucket(party: str) -> str:
    if party in DEMP: return "D"
    if party in CONP: return "C"
    return "I"  # 무소속·조국혁신당·진보당·개혁신당 등

def norm(sd): return ALIAS.get(sd, sd)

# ── 1. 2026 본선 226 ─────────────────────────────────────────────
def load_ballot():
    snap = sorted(glob.glob(str(ROOT/"data/candidates/20260603/snapshot_*.json")))[-1]
    cs = json.load(open(snap, encoding="utf-8"))["candidates"]
    races = defaultdict(list)
    for c in cs:
        if str(c.get("sgTypecode")) == "4" and c.get("sdName") and c.get("sggName"):
            races[(c["sdName"], c["sggName"])].append((c.get("name"), c.get("jdName") or "무소속"))
    return races

# ── 2. 과거 개표(민주−보수) 회귀 파라미터 (폴 없는 곳용) ──────────
def load_hist_params():
    d = json.load(open(ROOT/"data/history_counting_results.json", encoding="utf-8"))
    margin = defaultdict(dict)
    for elec in d["elections"]:
        rd = int(elec["round"])
        head = next((r for r in elec["results"] if r["sgTypecode"]=="4"), None)
        if not head: continue
        for dist in head["districts"]:
            sd = norm(dist["sdName"]); sgg = (dist.get("sggName") or "").strip()
            if not sgg: continue
            cands = dist.get("candidates") or []
            dem = sum(c.get("vote_share",0) or 0 for c in cands if c.get("party") in DEMP)
            con = sum(c.get("vote_share",0) or 0 for c in cands if c.get("party") in CONP)
            margin[(sd,sgg)][rd] = dem - con
    rounds = sorted({r for v in margin.values() for r in v})
    year_effect = {r: statistics.mean([margin[s][r] for s in margin if r in margin[s]]) for r in rounds}
    region_mean, region_sd = {}, {}
    glb = []
    for s, dd in margin.items():
        res = [m - year_effect[r] for r, m in dd.items() if r in year_effect]
        if not res: continue
        region_mean[s] = statistics.mean(res)
        region_sd[s] = statistics.stdev(res) if len(res) >= 2 else None
        glb += [v - region_mean[s] for v in res]
    residual_sd = statistics.pstdev(glb) if glb else 12.0
    ye_vals = list(year_effect.values())
    return {"year_effect": year_effect, "ye_vals": ye_vals, "region_mean": region_mean,
            "region_sd": region_sd, "residual_sd": residual_sd}

# ── 3. race별 모델 스펙 ──────────────────────────────────────────
def build_specs(races, polls, hp):
    specs = {}
    for (sd, sgg), cands in races.items():
        buckets = {bucket(p) for _, p in cands}
        has_D = "D" in buckets
        key = f"{sd}/{sgg}"
        poll = polls.get(key)
        if poll:
            specs[(sd,sgg)] = {"source":"poll","center":poll["margin"],"sigma":POLL_SIGMA,
                "chal":bucket(poll["비민주당"]),"poll":poll,"buckets":buckets}
            continue
        if not has_D:
            chal = "C" if "C" in buckets else "I"
            specs[(sd,sgg)] = {"source":"none","fixed":"chal","chal":chal,"buckets":buckets}
            continue
        if buckets == {"D"}:
            specs[(sd,sgg)] = {"source":"uncontested","fixed":"D","chal":"C","buckets":buckets}
            continue
        rm = hp["region_mean"].get((sd,sgg))
        rs = hp["region_sd"].get((sd,sgg))
        chal = "C" if "C" in buckets else "I"
        specs[(sd,sgg)] = {"source":"hist","region_mean":rm,"region_sd":rs,
            "chal":chal,"buckets":buckets}
    return specs

# ── 4. 몬테카를로 ────────────────────────────────────────────────
def simulate(specs, hp, n=N_SIM, seed=SEED):
    rng = random.Random(seed)
    ye_vals = hp["ye_vals"]; resid = hp["residual_sd"]
    win_D = Counter(); seat = Counter()  # seat: tuple counts
    seat_dist = {"D":Counter(),"C":Counter(),"I":Counter()}
    keys = list(specs.keys())
    for _ in range(n):
        ye = rng.choice(ye_vals)  # 폴 없는 곳 환경효과(혼합 추출, 중립)
        cnt = {"D":0,"C":0,"I":0}
        for k in keys:
            sp = specs[k]
            src = sp["source"]
            if src == "poll":
                margin = sp["center"] + rng.gauss(0, sp["sigma"])
                w = "D" if margin > 0 else sp["chal"]
            elif src == "uncontested":
                w = "D"
            elif src == "none":
                w = sp["chal"]
            else:  # hist
                rm = sp["region_mean"] if sp["region_mean"] is not None else 0.0
                rs = sp["region_sd"] if (sp["region_sd"] and sp["region_sd"]>0) else resid
                margin = ye + rng.gauss(rm, rs) + rng.gauss(0, resid)
                w = "D" if margin > 0 else sp["chal"]
            cnt[w] += 1
            if w == "D": win_D[k] += 1
        for b in "DCI": seat_dist[b][cnt[b]] += 1
    return win_D, seat_dist

def ci80(counter, n):
    items = sorted(counter.items()); cum=0; lo=hi=items[0][0]; flo=False
    for s,c in items:
        cum+=c
        if not flo and cum>=n*0.10: lo=s; flo=True
        if cum>=n*0.90: hi=s; break
    return [lo,hi]

def main():
    OUT.mkdir(parents=True, exist_ok=True)
    races = load_ballot()
    hp = load_hist_params()
    pj = json.load(open(ROOT/"data/polls_basic_head_extracted.json", encoding="utf-8"))
    polls = pj["polls"]
    specs = build_specs(races, polls, hp)
    win_D, seat_dist = simulate(specs, hp)

    n_poll = sum(1 for s in specs.values() if s["source"]=="poll")
    print(f"226 본선 race: {len(specs)}곳 | 폴 반영 {n_poll}곳 | 폴 없음 {len(specs)-n_poll}곳")
    means = {b: round(sum(s*c for s,c in seat_dist[b].items())/N_SIM,1) for b in "DCI"}
    modes = {b: max(seat_dist[b], key=seat_dist[b].get) for b in "DCI"}
    cis = {b: ci80(seat_dist[b], N_SIM) for b in "DCI"}
    print(f"민주 {modes['D']}곳 {cis['D']} / 국힘 {modes['C']}곳 {cis['C']} / 무소속·기타 {modes['I']}곳 {cis['I']}")

    # per-race
    rows=[]
    for (sd,sgg),sp in specs.items():
        p = round(win_D.get((sd,sgg),0)/N_SIM*100,1)
        poll = sp.get("poll")
        rows.append({"시도":sd,"시군구":sgg,"민주확률%":p,"도전진영":sp["chal"],"근거":sp["source"],
            "폴기관":poll["기관"] if poll else "","폴등록일":poll["등록일"] if poll else "",
            "폴민주":poll["민주"] if poll else "","폴비민주":poll["비민주top"] if poll else "",
            "폴비민주당":poll["비민주당"] if poll else "","폴마진":poll["margin"] if poll else ""})
    rows.sort(key=lambda r:-r["민주확률%"])
    with open(OUT/"per_race.csv","w",newline="",encoding="utf-8-sig") as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)

    summary={"generated":GEN,"office":"기초단체장","model":"여론조사 반영 + 무소속 3진영",
        "n_simulations":N_SIM,"poll_sigma":POLL_SIGMA,"n_poll_races":n_poll,"n_total":len(specs),
        "seat_mode":modes,"seat_mean":means,"seat_80ci":cis,
        "note":"민주(D)/국힘(C)/무소속·기타(I). 본선 폴 있으면 폴 prior, 없으면 과거 개표 회귀. 폴 출처 여심위."}
    json.dump(summary, open(OUT/"summary.json","w",encoding="utf-8"), ensure_ascii=False, indent=2)

    # /live/ 연동 JSON
    prob={f"4|{sd}|{sgg}": round(win_D.get((sd,sgg),0)/N_SIM*100,1) for (sd,sgg) in specs}
    chal={f"4|{sd}|{sgg}": specs[(sd,sgg)]["chal"] for (sd,sgg) in specs}
    src={f"4|{sd}|{sgg}": specs[(sd,sgg)]["source"] for (sd,sgg) in specs}
    json.dump({"generated_at":GEN,"office":"기초단체장",
        "source":"뉴탐사 자체 시뮬레이션 v2 — 여론조사(여심위 등록 본선 폴) 반영 + 무소속 3진영. 1만회 몬테카를로.",
        "legal_note":"인용된 여론조사는 모두 공직선거법 공표금지기간(2026-05-28) 전 조사·여심위 등록분입니다. 금지기간 전 조사임을 명시하여 공표(§108 단서).",
        "summary":{"dem_mode":modes["D"],"dem_80_ci":cis["D"],"con_mode":modes["C"],"ind_mode":modes["I"]},
        "basic_head_dem_win_prob":prob,"challenger":chal,"basis":src,
        "note":"키 sgType|sd|sgg → 민주 당선확률(%). challenger=도전진영(C국힘/I무소속·기타). basis=poll/hist."},
        open(ROOT/"data/prediction_basic_head_v2.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"저장: {OUT.relative_to(ROOT)}/ , data/prediction_basic_head_v2.json")

if __name__ == "__main__":
    main()
