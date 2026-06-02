#!/usr/bin/env python3
"""
9회 동시 국회의원 재·보궐 14곳 시뮬 v2 — 시도지사/기초단체장 v2와 동일 방법.
  본선 여론조사(여심위) 폴 우선, 없으면 2024총선·2025대선(선거구 포함 시군구) prior.
  무소속 3진영(D/C/I). 한동훈(부산 북구갑)·조국(평택을) 등 무소속·기타 포착.
출력: data/prediction_repoll_v2.json , sim/assembly/index.html (+ assembly-v2)
"""
from __future__ import annotations
import json, glob, random
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
N_SIM, SEED = 10_000, 42
W_GEN, W_PRES = 0.40, 0.60        # 선거구 prior: 2024총선·2025대선 (지선 없음)
POLL_SIGMA, HIST_SIGMA, NAT_SD = 7.0, 11.0, 4.0
GEN = "2026-06-02"
DEMP = {"더불어민주당","민주당"}; CONP = {"국민의힘"}
def bucket(p): return "D" if p in DEMP else ("C" if p in CONP else "I")
ABBR={"더불어민주당":"민주","민주당":"민주","국민의힘":"국힘","조국혁신당":"조국","진보당":"진보","개혁신당":"개혁","정의당":"정의","기본소득당":"기본","자유통일당":"자유","새미래민주연합":"새미"}
def ab(p): return ABBR.get(p,(p or "무소속")[:2])

def load_ballot():
    cs=json.load(open(sorted(glob.glob(str(ROOT/"data/candidates/20260603/snapshot_*.json")))[-1],encoding="utf-8"))["candidates"]
    r=defaultdict(list)
    for c in cs:
        if str(c.get("sgTypecode"))=="2" and c.get("sggName"):
            r[(c["sdName"],c["sggName"])].append((c.get("name"), c.get("jdName") or "무소속"))
    return r

def lean_map():
    L=json.load(open(ROOT/"data/national_lean.json",encoding="utf-8"))["lean"]
    return L

def sgg_in(sd, sgg_name, lean):
    """선거구명(군산시김제시부안군갑 등)에 포함된 시군구들의 2024총선·2025대선 평균 마진."""
    cands=[k for k in lean if k.startswith(sd+"/")]
    hits=[k for k in cands if k.split("/",1)[1] in sgg_name]
    if not hits: return None
    gd=gc=pd=pc=0
    for k in hits:
        v=lean[k]; g=v.get("gen2024",{}); p=v.get("pres2025",{})
        gd+=g.get("dem",0);gc+=g.get("con",0);pd+=p.get("dem",0);pc+=p.get("con",0)
    vals,ws=[],[]
    if gd+gc>0: vals.append((gd-gc)/(gd+gc)*100); ws.append(W_GEN)
    if pd+pc>0: vals.append((pd-pc)/(pd+pc)*100); ws.append(W_PRES)
    return sum(x*w for x,w in zip(vals,ws))/sum(ws) if vals else None

def build(races, polls, lean):
    specs={}
    for (sd,sgg),cands in races.items():
        buckets={bucket(p) for _,p in cands}
        P=sgg_in(sd,sgg,lean)
        poll=polls.get(sgg) or polls.get(f"{sd}/{sgg}")
        if poll:
            chal=bucket(poll["비민주당"])
            specs[(sd,sgg)]={"center":poll["margin"],"sigma":POLL_SIGMA,"chal":chal,"source":"poll","prior":P,
                "polltxt":f'여론조사 {poll.get("조사일") or ("~05-27" if poll["등록일"]>="2026-05-28" else poll["등록일"][5:])} · 민주 {poll["민주"]} vs {ab(poll["비민주당"])} {poll["비민주top"]}'}
        else:
            chal="C" if "C" in buckets else "I"
            specs[(sd,sgg)]={"center":(P if P is not None else 0.0),"sigma":HIST_SIGMA,"chal":chal,"source":"past","prior":P,"polltxt":""}
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

HEADERHTML='''<header class="sim-header"><div class="sim-header-inner">
<a href="https://election2026.newtamsa.org/" class="sim-brand"><span class="sim-brand-title">뉴탐사 · 6·3 지방선거 2026</span><span class="sim-brand-sub">결과 예측 시뮬레이션</span></a>
<nav class="sim-nav"><a class="sim-nav-link" href="/sim/">시뮬레이션 홈</a><a class="sim-nav-link" href="/sim/sido/">시도지사 17</a><a class="sim-nav-link" href="/sim/basic-head/">기초단체장 226</a><a class="sim-nav-link sim-nav-link-active" href="/sim/assembly/" aria-current="page">재·보궐 14</a></nav>
<a class="sim-live-link js-live-gate" href="https://election2026.newtamsa.org/#live" hidden>실시간 개표 →</a>
<script>document.addEventListener('DOMContentLoaded',function(){if(Date.now()>=Date.parse('2026-06-03T18:00:00+09:00')){var e=document.querySelectorAll('.js-live-gate');for(var i=0;i<e.length;i++)e[i].hidden=false;}});</script>
</div></header>'''
HEADERCSS='''
.sim-header{background:#1a1a1a;color:#fff;border-bottom:3px solid #c41e3a}
.sim-header-inner{max-width:1100px;margin:0 auto;padding:12px 24px;display:flex;align-items:center;gap:20px;flex-wrap:wrap}
.sim-brand{color:#fff;text-decoration:none;display:flex;flex-direction:column;line-height:1.2;margin-right:auto}
.sim-brand-title{font-size:1.05rem;font-weight:800}.sim-brand-sub{font-size:.78rem;color:#c41e3a;font-weight:700}
.sim-nav{display:flex;gap:4px;flex-wrap:wrap}.sim-nav-link{color:rgba(255,255,255,.78);text-decoration:none;font-size:.86rem;font-weight:600;padding:6px 12px;border-radius:999px}
.sim-nav-link:hover{background:rgba(255,255,255,.08);color:#fff}.sim-nav-link-active{background:#c41e3a;color:#fff}
.sim-live-link{background:#c41e3a;color:#fff;text-decoration:none;padding:7px 14px;border-radius:6px;font-size:.84rem;font-weight:700}
@media(max-width:720px){.sim-header-inner{padding:10px 16px;gap:10px}.sim-brand-title{font-size:.95rem}.sim-nav-link{font-size:.78rem;padding:5px 10px}}
'''
def main():
    races=load_ballot(); lean=lean_map()
    pf=ROOT/"data/polls_repoll_extracted.json"
    polls=json.load(open(pf,encoding="utf-8"))["polls"] if pf.exists() else {}
    specs=build(races,polls,lean); winD,seat=simulate(specs)
    modes={b:max(seat[b],key=seat[b].get) for b in "DCI"}; cis={b:ci80(seat[b]) for b in "DCI"}
    prob={k:round(winD.get(k,0)/N_SIM*100,1) for k in specs}
    npoll=sum(1 for s in specs.values() if s["source"]=="poll")
    print(f"재보선 14: 민주 {modes['D']} {cis['D']} / 국힘 {modes['C']} {cis['C']} / 무소속·기타 {modes['I']} {cis['I']} | 폴 {npoll}곳")
    for (sd,sgg) in sorted(specs,key=lambda x:-prob[x]):
        sp=specs[(sd,sgg)]; print(f"  {sd[:2]} {sgg:18s} 민주 {prob[(sd,sgg)]:5}% (도전 {sp['chal']}, {sp['source']})")
    out={"generated_at":GEN,"office":"국회의원 재·보궐","n_simulations":N_SIM,
        "source":"뉴탐사 v2 — 본선 여론조사 + 2024총선·2025대선 prior + 무소속 3진영. 여론조사는 공표금지기간 전 조사분.",
        "summary":{"dem_mode":modes["D"],"dem_80_ci":cis["D"],"con_mode":modes["C"],"ind_mode":modes["I"]},
        "repoll_dem_win_prob":{f"{sd}/{sgg}":prob[(sd,sgg)] for (sd,sgg) in specs}}
    json.dump(out,open(ROOT/"data/prediction_repoll_v2.json","w",encoding="utf-8"),ensure_ascii=False,indent=1)
    write_html(races,specs,prob,modes,cis,npoll)
    print("저장: data/prediction_repoll_v2.json , sim/assembly/index.html")

def write_html(races,specs,prob,modes,cis,npoll):
    def row(k):
        sd,sgg=k; p=prob[k]; rp=100-p; sp=specs[k]; is_i=sp["chal"]=="I"
        cc="#6b7280" if is_i else "#E61E2B"; chal="무소속·기타" if is_i else "국민의힘"
        basis=(f'<span class="b-poll">{sp["polltxt"]}</span>' if sp["source"]=="poll"
               else f'<span class="b-hist">과거선거 (민주 {sp["prior"]:+.0f})</span>' if sp["prior"] is not None else '<span class="b-hist">—</span>')
        cls="r-toss" if 42<=p<=58 else ("r-ind" if (is_i and p<50) else "")
        cn=', '.join(f'{n}({ab(pp)})' for n,pp in races[k])
        return (f'<tr class="{cls}"><td class="sgg">{sd[:2]} {sgg}</td>'
            f'<td><div class="bar"><span class="bd" style="width:{p:.0f}%"></span><span class="bc" style="width:{rp:.0f}%;background:{cc}"></span></div></td>'
            f'<td class="nd">{p:.0f}%</td><td class="nc">vs {chal} {rp:.0f}%</td><td class="basis">{basis}</td></tr>'
            f'<tr class="cand"><td colspan="5">{cn}</td></tr>')
    rows="".join(row(k) for k in sorted(specs,key=lambda x:-prob[x]))
    html=f'''<!doctype html><html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>국회의원 재·보궐 시뮬 — 뉴탐사</title><style>
body{{font-family:-apple-system,'Pretendard',sans-serif;margin:0;padding:0;color:#1a1a1a;line-height:1.5}}
.wrap{{max-width:880px;margin:0 auto;padding:22px}}
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
<h1>국회의원 재·보궐 14 — 결과 예측 시뮬레이션</h1>
<p class="sub">2026-06-02 · 본선 여론조사 {npoll}곳 + 과거선거(2024총선·2025대선) + 무소속 3진영 · 1만 회 몬테카를로 · 뉴탐사</p>
<div class="legal">⚖️ 인용 여론조사는 모두 공직선거법 공표금지기간(5/28) 전 조사·여심위 등록분입니다. (§108 단서) 폴 없는 곳은 과거선거 기반.</div>
<div class="pills"><div class="pill p-d"><span class="pl">민주</span><b>{modes['D']}석</b><span class="ps">{cis['D'][0]}~{cis['D'][1]}</span></div>
<div class="pill p-c"><span class="pl">국힘</span><b>{modes['C']}석</b><span class="ps">{cis['C'][0]}~{cis['C'][1]}</span></div>
<div class="pill p-i"><span class="pl">무소속·기타</span><b>{modes['I']}석</b><span class="ps">{cis['I'][0]}~{cis['I'][1]}</span></div></div>
<table><tbody>{rows}</tbody></table>
<p style="color:#666;font-size:.8rem;margin-top:14px">노랑=접전(42~58%), 회색=무소속 우세. 막대 회색=무소속·기타 도전(한동훈·조국 등). 합구 선거구는 포함 시군구 평균. 예측이지 단정 아님.</p>
</main>
</body></html>'''
    for sub in ("assembly","assembly-v2"):
        out=ROOT/"sim"/sub; out.mkdir(parents=True,exist_ok=True)
        (out/"index.html").write_text(html,encoding="utf-8")

if __name__=="__main__": main()
