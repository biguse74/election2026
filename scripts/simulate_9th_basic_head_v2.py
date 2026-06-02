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
    write_html(rows, modes, cis, means, n_poll, len(specs))
    print(f"저장: {OUT.relative_to(ROOT)}/ , data/prediction_basic_head_v2.json , sim/basic-head-v2/index.html")

SIDO_ORDER = ["서울특별시","부산광역시","대구광역시","인천광역시","광주광역시","대전광역시","울산광역시",
    "경기도","강원특별자치도","충청북도","충청남도","전북특별자치도","전라남도","경상북도","경상남도"]
BUCKET_KR = {"D":"민주당","C":"국민의힘","I":"무소속·기타"}

def write_html(rows, modes, cis, means, n_poll, n_total):
    by = {}
    for r in rows: by.setdefault(r["시도"], []).append(r)
    def srow(r):
        p = float(r["민주확률%"]); rp = 100 - p
        is_ind = r["도전진영"]=="I"
        chal = "무소속·기타" if is_ind else "국민의힘"
        cc = "#6b7280" if is_ind else "#E61E2B"   # 무소속·기타는 회색, 국힘은 빨강
        if r["근거"]=="poll":
            basis = f'<span class="b-poll">여론조사 {r["폴등록일"][5:]}</span><span class="b-detail">민주 {r["폴민주"]} vs {BUCKET_KR.get(r["도전진영"],"")[:2]} {r["폴비민주"]}</span>'
        else:
            basis = '<span class="b-hist">과거 개표</span>'
        cls = "r-ind" if (is_ind and p<50) else ("r-toss" if 42<=p<=58 else "")
        return (f'<tr class="{cls}"><td class="sgg">{r["시군구"]}</td>'
            f'<td><div class="bar"><span class="bd" style="width:{p:.0f}%"></span><span class="bc" style="width:{rp:.0f}%;background:{cc}"></span></div></td>'
            f'<td class="nd">{p:.0f}%</td><td class="nc">vs {chal} {rp:.0f}%</td><td class="basis">{basis}</td></tr>')
    secs = []
    for sd in sorted(by, key=lambda x: SIDO_ORDER.index(x) if x in SIDO_ORDER else 99):
        rs = sorted(by[sd], key=lambda r: -float(r["민주확률%"]))
        np = sum(1 for r in rs if r["근거"]=="poll")
        secs.append(f'<section class="sd"><h3>{sd} <span class="m">{len(rs)}곳 · 여론조사 반영 {np}곳</span></h3>'
            f'<table><thead><tr><th>시군구</th><th></th><th>민주</th><th>도전</th><th>근거</th></tr></thead><tbody>'
            + "".join(srow(r) for r in rs) + '</tbody></table></section>')
    html = f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>기초단체장 시뮬 v2 (여론조사 반영) — 뉴탐사</title><style>
body{{font-family:-apple-system,'Pretendard',sans-serif;max-width:1000px;margin:0 auto;padding:22px;color:#1a1a1a;line-height:1.5}}
h1{{font-size:1.5rem;margin:0 0 4px}} .sub{{color:#666;font-size:.85rem;margin:0 0 14px}}
.legal{{background:#fff8e1;border:1px solid #ffe08a;border-radius:6px;padding:10px 14px;font-size:.82rem;color:#7a5b00;margin:0 0 16px}}
.pills{{display:flex;gap:10px;flex-wrap:wrap;margin:0 0 8px}}
.pill{{flex:1;min-width:160px;padding:12px 16px;border-radius:8px}} .pill b{{font-size:1.7rem;display:block}}
.p-d{{background:#eef2fb;border-left:5px solid #152484}} .p-c{{background:#fdecee;border-left:5px solid #E61E2B}} .p-i{{background:#f0f0ee;border-left:5px solid #6b7280}}
.pl{{font-size:.78rem;color:#555;font-weight:700}} .ps{{font-size:.76rem;color:#666}}
.note{{font-size:.84rem;color:#555;background:#f6f6f6;padding:10px 14px;border-radius:6px;margin:14px 0}}
.sd{{margin:16px 0;padding:10px 12px;border:1px solid #e6e6e6;border-radius:6px;background:#fafafa}}
.sd h3{{font-size:1rem;margin:0 0 6px;display:flex;gap:10px;align-items:baseline;flex-wrap:wrap}} .sd .m{{font-size:.76rem;font-weight:400;color:#666}}
table{{width:100%;border-collapse:collapse;font-size:.8rem}} th,td{{padding:4px 6px;border-bottom:1px solid #eee;text-align:left;font-variant-numeric:tabular-nums}}
th{{font-size:.72rem;color:#777}} td.sgg{{font-weight:600}}
.bar{{display:flex;height:11px;border-radius:3px;overflow:hidden;min-width:120px;max-width:200px;background:#eee}}
.bd{{background:#152484}} .bc{{background:#E61E2B}} .nd{{color:#152484;font-weight:700}} .nc{{color:#666;font-size:.74rem}}
.basis{{font-size:.72rem}} .b-poll{{background:#152484;color:#fff;padding:1px 5px;border-radius:3px;font-size:.68rem}} .b-hist{{color:#999;font-size:.72rem}}
.b-detail{{color:#777;margin-left:5px}} tr.r-ind{{background:#f4f5f6}} tr.r-toss{{background:#fffbe9}}
@media(max-width:720px){{.basis .b-detail{{display:none}} .bar{{min-width:60px;max-width:90px}} th,td{{padding:3px 4px}}}}
</style></head><body>
<h1>기초단체장 226 — 여론조사 반영 시뮬 (v2)</h1>
<p class="sub">2026-06-02 · 무소속 3진영 + 본선 여론조사 반영 · 1만 회 몬테카를로 · 뉴탐사 (※ 미리보기)</p>
<div class="legal">⚖️ 인용한 여론조사는 모두 <b>공직선거법 공표금지기간(5/28) 전에 조사·여심위 등록</b>된 것입니다. (§108 단서: 금지기간 전 조사임을 명시한 공표는 제한되지 않음)</div>
<div class="pills">
  <div class="pill p-d"><span class="pl">더불어민주당</span><b>{modes['D']}곳</b><span class="ps">예상범위 {cis['D'][0]}~{cis['D'][1]}</span></div>
  <div class="pill p-c"><span class="pl">국민의힘</span><b>{modes['C']}곳</b><span class="ps">예상범위 {cis['C'][0]}~{cis['C'][1]}</span></div>
  <div class="pill p-i"><span class="pl">무소속·기타</span><b>{modes['I']}곳</b><span class="ps">예상범위 {cis['I'][0]}~{cis['I'][1]}</span></div>
</div>
<div class="note"><b>모델:</b> 본선 여론조사 있는 <b>{n_poll}곳</b>은 폴 마진(±7%p)을 중심값으로, 없는 {n_total-n_poll}곳은 과거 6회차(1995~2022) 개표 회귀. 사전투표율 미반영(방향 불명 지표). 막대 색: 민주=파랑, 국힘=빨강, <b>무소속·기타=회색</b>. <b>노란 행</b>=칼날 접전(42~58%). 시군구는 후보·현직 효과가 커 시도지사보다 정확도 낮습니다. 예측이지 단정이 아닙니다.</div>
{"".join(secs)}
</body></html>'''
    out = ROOT / "sim" / "basic-head-v2"
    out.mkdir(parents=True, exist_ok=True)
    (out / "index.html").write_text(html, encoding="utf-8")

if __name__ == "__main__":
    main()
