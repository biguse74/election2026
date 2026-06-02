#!/usr/bin/env python3
"""
9회 시도지사 16곳 시뮬 v2 — 기초단체장 v2와 동일 방법.
  prior = 2022 시도지사(8회) + 2024 총선 + 2025 대선 가중평균(최근↑)
  무소속 3진영(D/C/I). 전북은 무소속 김관영을 뉴탐사 5/12 여론조사로 반영.
출력: data/prediction_sido_v2.json , sim/sido-v2/index.html
"""
from __future__ import annotations
import json, glob, random, statistics
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
N_SIM, SEED = 10_000, 42
W_LOCAL, W_GEN, W_PRES = 0.25, 0.30, 0.45
POLL_W, LEAN_W = 1.0, 0.0   # 시도지사는 거물 후보 변수가 커 폴 단독(prior는 폴 없는 곳만)
HIST_SIGMA, POLL_SIGMA, NAT_SD = 9.0, 7.0, 4.0
GEN = "2026-06-02"
DEMP = {"민주당","새천년민주당","열린우리당","대통합민주신당","통합민주당","민주통합당","새정치민주연합","더불어민주당"}
CONP = {"한나라당","새누리당","자유한국당","바른정당","미래통합당","국민의힘"}
ALIAS = {"강원도":"강원특별자치도","전라북도":"전북특별자치도","제주도":"제주특별자치도"}
# 2026 전남광주통합특별시 = 2022·총선·대선의 광주+전남 합산
MERGE = {"전남광주통합특별시": ["광주광역시","전라남도"]}
def bucket(p): return "D" if p in DEMP else ("C" if p in CONP else "I")
def norm(s): return ALIAS.get(s,s)

def load_ballot():
    cs=json.load(open(sorted(glob.glob(str(ROOT/"data/candidates/20260603/snapshot_*.json")))[-1],encoding="utf-8"))["candidates"]
    r=defaultdict(list)
    for c in cs:
        if str(c.get("sgTypecode"))=="3" and c.get("sggName"):
            r[c["sggName"]].append((c.get("name"), c.get("jdName") or "무소속"))
    return r

def votes8():  # 2022 시도지사 시도별 민주/국힘 득표
    H=json.load(open(ROOT/"data/history_counting_results.json",encoding="utf-8"))
    r3=[r for e in H["elections"] if e["round"]==8 for r in e["results"] if r["sgTypecode"]=="3"][0]
    out=defaultdict(lambda:[0,0])
    for d in r3["districts"]:
        sd=norm(d["sggName"])
        for c in d.get("candidates",[]):
            if c.get("party") in DEMP: out[sd][0]+=c.get("votes",0)
            elif c.get("party") in CONP: out[sd][1]+=c.get("votes",0)
    return out

def lean_sido():  # national_lean 시군구 → 시도 합산
    L=json.load(open(ROOT/"data/national_lean.json",encoding="utf-8"))["lean"]
    agg=defaultdict(lambda:[0,0,0,0])
    for k,v in L.items():
        sd=k.split("/")[0]; g=v.get("gen2024",{}); p=v.get("pres2025",{})
        agg[sd][0]+=g.get("dem",0); agg[sd][1]+=g.get("con",0)
        agg[sd][2]+=p.get("dem",0); agg[sd][3]+=p.get("con",0)
    return agg

def members(sido): return MERGE.get(sido, [sido])

def prior_margin(sido, v8, lean):
    vals, ws = [], []
    # 8회
    d=c=0
    for m in members(sido):
        a=v8.get(m);
        if a: d+=a[0]; c+=a[1]
    if d+c>0: vals.append((d-c)/(d+c)*100); ws.append(W_LOCAL)
    # 총선/대선
    gd=gc=pd=pc=0
    for m in members(sido):
        a=lean.get(m)
        if a: gd+=a[0]; gc+=a[1]; pd+=a[2]; pc+=a[3]
    if gd+gc>0: vals.append((gd-gc)/(gd+gc)*100); ws.append(W_GEN)
    if pd+pc>0: vals.append((pd-pc)/(pd+pc)*100); ws.append(W_PRES)
    if not vals: return None
    return sum(x*w for x,w in zip(vals,ws))/sum(ws)

def build(races, v8, lean, polls):
    specs={}
    for sido,cands in races.items():
        buckets={bucket(p) for _,p in cands}
        P=prior_margin(sido,v8,lean)
        poll=polls.get(sido)
        if poll:
            chal=bucket(poll["비민주당"])
            center = (POLL_W*poll["margin"]+LEAN_W*P) if (chal=="C" and P is not None) else poll["margin"]
            specs[sido]={"center":center,"sigma":POLL_SIGMA,"chal":chal,"source":"poll","prior":P,
                "polltxt":f'여론조사 {poll["등록일"][5:]} · 민주 {poll["민주"]} vs {poll["비민주당"][:2]} {poll["비민주top"]}'}
        else:
            chal="C" if "C" in buckets else "I"
            specs[sido]={"center":(P if P is not None else 0.0),"sigma":HIST_SIGMA,"chal":chal,
                "source":"past","prior":P,"polltxt":""}
    return specs

def simulate(specs):
    rng=random.Random(SEED); winD=Counter(); seat={"D":Counter(),"C":Counter(),"I":Counter()}
    ks=list(specs)
    for _ in range(N_SIM):
        sw=rng.gauss(0,NAT_SD); cnt={"D":0,"C":0,"I":0}
        for k in ks:
            sp=specs[k]; m=sp["center"]+sw+rng.gauss(0,sp["sigma"])
            w="D" if m>0 else sp["chal"]; cnt[w]+=1
            if w=="D": winD[k]+=1
        for b in "DCI": seat[b][cnt[b]]+=1
    return winD,seat

def ci80(c):
    it=sorted(c.items());cum=0;lo=hi=it[0][0];f=False
    for s,n in it:
        cum+=n
        if not f and cum>=N_SIM*.1:lo=s;f=True
        if cum>=N_SIM*.9:hi=s;break
    return [lo,hi]

SIDO_ORDER=["서울특별시","부산광역시","대구광역시","인천광역시","대전광역시","울산광역시","세종특별자치시",
    "경기도","강원특별자치도","충청북도","충청남도","전북특별자치도","경상북도","경상남도","제주특별자치도","전남광주통합특별시"]
def main():
    races=load_ballot(); v8=votes8(); lean=lean_sido()
    pf=ROOT/"data/polls_sido_extracted.json"
    polls=json.load(open(pf,encoding="utf-8"))["polls"] if pf.exists() else {}
    specs=build(races,v8,lean,polls); winD,seat=simulate(specs)
    modes={b:max(seat[b],key=seat[b].get) for b in "DCI"}; cis={b:ci80(seat[b]) for b in "DCI"}
    prob={k:round(winD.get(k,0)/N_SIM*100,1) for k in specs}
    print(f"시도지사 16: 민주 {modes['D']} {cis['D']} / 국힘 {modes['C']} {cis['C']} / 무소속 {modes['I']} {cis['I']}")
    for k in sorted(specs,key=lambda x:-prob[x]):
        sp=specs[k]; print(f"  {k:14s} 민주 {prob[k]:5}% (도전 {sp['chal']}, prior {round(sp['prior'],1) if sp['prior'] is not None else '-'}, {sp['source']})")
    out={"generated_at":GEN,"office":"시도지사","n_simulations":N_SIM,
        "source":"뉴탐사 v2 — 2022지선+2024총선+2025대선 prior + 무소속 3진영. 전북은 뉴탐사 5/12 여론조사(공표금지기간 전).",
        "summary":{"dem_mode":modes["D"],"dem_80_ci":cis["D"],"con_mode":modes["C"],"ind_mode":modes["I"]},
        "sido_dem_win_prob":prob,
        "detail":{k:{"chal":specs[k]["chal"],"prior":round(specs[k]["prior"],1) if specs[k]["prior"] is not None else None,
                     "source":specs[k]["source"],"poll":specs[k]["polltxt"]} for k in specs}}
    json.dump(out,open(ROOT/"data/prediction_sido_v2.json","w",encoding="utf-8"),ensure_ascii=False,indent=1)
    write_html(races,specs,prob,modes,cis)
    print("저장: data/prediction_sido_v2.json , sim/sido-v2/index.html")

HEADERHTML='''<header class="sim-header"><div class="sim-header-inner">
<a href="https://election2026.newtamsa.org/" class="sim-brand"><span class="sim-brand-title">뉴탐사 · 6·3 지방선거 2026</span><span class="sim-brand-sub">결과 예측 시뮬레이션</span></a>
<nav class="sim-nav"><a class="sim-nav-link" href="/sim/">시뮬레이션 홈</a><a class="sim-nav-link sim-nav-link-active" href="/sim/sido/" aria-current="page">시도지사 17</a><a class="sim-nav-link" href="/sim/basic-head/">기초단체장 226</a><a class="sim-nav-link" href="/sim/assembly/">재·보궐 14</a></nav>
<a class="sim-live-link js-live-gate" href="https://election2026.newtamsa.org/#live" hidden>실시간 개표 →</a>
<script>document.addEventListener('DOMContentLoaded',function(){if(Date.now()>=Date.parse('2026-06-03T18:00:00+09:00')){var e=document.querySelectorAll('.js-live-gate');for(var i=0;i<e.length;i++)e[i].hidden=false;}});</script>
</div></header>'''
HEADERCSS='''
.sim-header{background:#1a1a1a;color:#fff;border-bottom:3px solid #c41e3a}
.sim-header-inner{max-width:1100px;margin:0 auto;padding:12px 24px;display:flex;align-items:center;gap:20px;flex-wrap:wrap}
.sim-brand{color:#fff;text-decoration:none;display:flex;flex-direction:column;line-height:1.2;margin-right:auto}
.sim-brand-title{font-size:1.05rem;font-weight:800}.sim-brand-sub{font-size:.78rem;color:#c41e3a;font-weight:700}
.sim-nav{display:flex;gap:4px;flex-wrap:wrap}
.sim-nav-link{color:rgba(255,255,255,.78);text-decoration:none;font-size:.86rem;font-weight:600;padding:6px 12px;border-radius:999px}
.sim-nav-link:hover{background:rgba(255,255,255,.08);color:#fff}.sim-nav-link-active{background:#c41e3a;color:#fff}
.sim-live-link{background:#c41e3a;color:#fff;text-decoration:none;padding:7px 14px;border-radius:6px;font-size:.84rem;font-weight:700}
@media(max-width:720px){.sim-header-inner{padding:10px 16px;gap:10px}.sim-brand-title{font-size:.95rem}.sim-nav-link{font-size:.78rem;padding:5px 10px}}
'''
def write_html(races,specs,prob,modes,cis):
    def row(k):
        p=prob[k]; rp=100-p; sp=specs[k]; is_i=sp["chal"]=="I"
        cc="#6b7280" if is_i else "#E61E2B"; chal="무소속·기타" if is_i else "국민의힘"
        basis=(f'<span class="b-poll">{sp["polltxt"]}</span>' if sp["source"]=="poll"
               else f'<span class="b-hist">과거선거 (민주 {sp["prior"]:+.0f})</span>' if sp["prior"] is not None else '<span class="b-hist">—</span>')
        cls="r-toss" if 42<=p<=58 else ("r-ind" if (is_i and p<50) else "")
        cn=', '.join(f'{n}({(pp or "무소속")[:2]})' for n,pp in races[k])
        return (f'<tr class="{cls}"><td class="sgg">{k.replace("특별자치도","").replace("광역시","").replace("특별시","").replace("특별자치시","")}</td>'
            f'<td><div class="bar"><span class="bd" style="width:{p:.0f}%"></span><span class="bc" style="width:{rp:.0f}%;background:{cc}"></span></div></td>'
            f'<td class="nd">{p:.0f}%</td><td class="nc">vs {chal} {rp:.0f}%</td><td class="basis">{basis}</td></tr>'
            f'<tr class="cand"><td colspan="5">{cn}</td></tr>')
    rows="".join(row(k) for k in sorted(SIDO_ORDER,key=lambda x:-prob.get(x,0)) if k in specs)
    html=f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>시도지사 시뮬 v2 — 뉴탐사</title><style>
body{{font-family:-apple-system,'Pretendard',sans-serif;margin:0;padding:0;color:#1a1a1a;line-height:1.5}}
.wrap{{max-width:840px;margin:0 auto;padding:22px}}
{HEADERCSS}
h1{{font-size:1.5rem;margin:0 0 4px}}.sub{{color:#666;font-size:.85rem;margin:0 0 14px}}
.legal{{background:#fff8e1;border:1px solid #ffe08a;border-radius:6px;padding:10px 14px;font-size:.82rem;color:#7a5b00;margin:0 0 16px}}
.pills{{display:flex;gap:10px;margin:0 0 14px}}.pill{{flex:1;padding:12px;border-radius:8px}}.pill b{{font-size:1.6rem;display:block}}
.p-d{{background:#eef2fb;border-left:5px solid #152484}}.p-c{{background:#fdecee;border-left:5px solid #E61E2B}}.p-i{{background:#f0f0ee;border-left:5px solid #6b7280}}
.pl{{font-size:.76rem;color:#555;font-weight:700}}.ps{{font-size:.74rem;color:#666}}
table{{width:100%;border-collapse:collapse;font-size:.86rem}}td{{padding:5px 7px;border-bottom:1px solid #eee}}
td.sgg{{font-weight:700}}.bar{{display:flex;height:13px;border-radius:3px;overflow:hidden;min-width:150px;background:#eee}}
.bd{{background:#152484}}.bc{{background:#E61E2B}}.nd{{color:#152484;font-weight:700}}.nc{{color:#666;font-size:.78rem}}
.basis{{font-size:.72rem}}.b-poll{{background:#152484;color:#fff;padding:1px 5px;border-radius:3px;font-size:.66rem}}.b-hist{{color:#888;font-size:.72rem}}
tr.cand td{{padding:0 7px 6px;font-size:.74rem;color:#888;border-bottom:1px solid #eee}}
tr.r-toss td{{background:#fffbe9}}tr.r-ind td{{background:#f4f5f6}}
</style></head><body>
{HEADERHTML}
<main class="wrap">
<h1>시도지사 16 — 결과 예측 시뮬레이션</h1>
<p class="sub">2026-06-02 · 본선 여론조사 16곳 + 과거선거(2022지선·2024총선·2025대선) + 무소속 3진영 · 1만 회 몬테카를로 · 뉴탐사</p>
<div class="legal">⚖️ 인용 여론조사는 모두 공직선거법 공표금지기간(5/28) 전 조사·여심위 등록분입니다. (§108 단서) 폴 없는 곳은 과거선거 기반.</div>
<div class="pills"><div class="pill p-d"><span class="pl">민주</span><b>{modes['D']}곳</b><span class="ps">{cis['D'][0]}~{cis['D'][1]}</span></div>
<div class="pill p-c"><span class="pl">국힘</span><b>{modes['C']}곳</b><span class="ps">{cis['C'][0]}~{cis['C'][1]}</span></div>
<div class="pill p-i"><span class="pl">무소속·기타</span><b>{modes['I']}곳</b><span class="ps">{cis['I'][0]}~{cis['I'][1]}</span></div></div>
<table><tbody>{rows}</tbody></table>
<p style="color:#666;font-size:.8rem;margin-top:14px">노랑=접전(42~58%), 회색=무소속 우세. 막대 회색=무소속 도전. 현직 이점 미반영. 세종은 총선·대선 시군구 데이터 부재로 8회만 반영. 예측이지 단정 아님.</p>
</main>
</body></html>'''
    for sub in ("sido","sido-v2"):   # 공개 경로 + 미리보기 경로 동시 발행
        out=ROOT/"sim"/sub; out.mkdir(parents=True,exist_ok=True)
        (out/"index.html").write_text(html,encoding="utf-8")

if __name__=="__main__": main()
