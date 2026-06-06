# -*- coding: utf-8 -*-
"""기자 원본 대조 검증 도구(로컬 전용) 생성.

verify_data.json(인물별 자동추출 + 원본 PDF 경로) + verify.html(좌:명단 / 우:추출표+원본PDF)을
프로젝트 루트에 만든다. 로컬 http.server로 열어 원본과 자동추출을 나란히 비교한다.
  python scripts/build_verify_tool.py
  python -m http.server 8765   →   http://localhost:8765/verify.html
※ 출력물(verify.html·data/verify_data.json)은 .gitignore(원본경로 포함, 공개 안 함).
"""
import glob
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SLIM = ROOT / "stocks" / "stock_holdings.json"


def main():
    d = json.loads(SLIM.read_text(encoding="utf-8"))
    pdf_by_hb = {}
    for folder in glob.glob(str(ROOT / "data/disclosure_archive/*/재산")):
        hb = os.path.basename(os.path.dirname(folder)).split("_")[0]
        pdfs = sorted(set(glob.glob(os.path.join(folder, "*.PDF")) + glob.glob(os.path.join(folder, "*.pdf"))))
        pdf_by_hb[hb] = [os.path.relpath(p, ROOT).replace("\\", "/") for p in pdfs]

    people = []
    for p in d["people"]:
        hold = p["holdings"]
        n = len(hold)
        bigq = [h["종목"] for h in hold if (h.get("수량주") or 0) > 10_000_000]
        reasons, grade = [], "정상"
        if bigq:
            reasons.append("수량의심:" + ",".join(bigq[:3])); grade = "높음"
        if n >= 50:
            reasons.append("종목과다"); grade = "높음"
        if p.get("needs_review"):
            reasons.append("OCR추출불완전")
            if grade != "높음":
                grade = "중간"
        people.append({
            "huboid": str(p["huboid"]), "name": p["name"], "office": p.get("office"),
            "sido": p.get("sido"), "sgg": p.get("sgg"), "party": p.get("party"),
            "grade": grade, "reasons": reasons,
            "holdings": [{"종목": h["종목"], "수량주": h.get("수량주")} for h in hold],
            "pdfs": pdf_by_hb.get(str(p["huboid"]), []),
        })
    order = {"높음": 0, "중간": 1, "정상": 2}
    people.sort(key=lambda x: (order[x["grade"]], x["name"]))

    (ROOT / "data" / "verify_data.json").write_text(
        json.dumps({"count": len(people), "people": people}, ensure_ascii=False),
        encoding="utf-8")
    (ROOT / "verify.html").write_text(HTML, encoding="utf-8")
    nh = sum(1 for x in people if x["grade"] == "높음")
    print(f"검증 도구 생성: {len(people)}명(🔴{nh}) → verify.html + data/verify_data.json")
    print("열기: python -m http.server 8765  →  http://localhost:8765/verify.html")


HTML = r"""<!DOCTYPE html><html lang="ko"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>원본 대조 검증(로컬)</title>
<style>
*{box-sizing:border-box} body{margin:0;font-family:Pretendard,-apple-system,sans-serif;display:flex;height:100vh;overflow:hidden}
#side{width:320px;flex-shrink:0;border-right:1px solid #ddd;display:flex;flex-direction:column;background:#fafafa}
#side h1{font-size:1rem;margin:0;padding:12px 14px;background:#1a1a1a;color:#fff}
#q{margin:8px;padding:8px 10px;border:1px solid #ccc;border-radius:7px;font-size:.9rem}
#seg{display:flex;gap:4px;padding:0 8px 8px}
#seg button{flex:1;font-size:.76rem;font-weight:700;padding:5px;border:1px solid #ccc;border-radius:6px;background:#fff;cursor:pointer}
#seg button.on{background:#c41e3a;color:#fff;border-color:#c41e3a}
#list{flex:1;overflow-y:auto}
.it{padding:9px 14px;border-bottom:1px solid #eee;cursor:pointer;font-size:.88rem}
.it:hover{background:#f0f0f0} .it.sel{background:#fdeaea}
.it .nm{font-weight:800} .it .meta{font-size:.74rem;color:#777}
.badge{display:inline-block;font-size:.66rem;font-weight:800;border-radius:4px;padding:1px 5px;margin-right:5px;color:#fff}
.g높음{background:#c41e3a}.g중간{background:#d89a16}.g정상{background:#888}
#main{flex:1;display:flex;flex-direction:column;overflow:hidden}
#info{padding:10px 16px;border-bottom:1px solid #ddd}
#info h2{margin:0 0 3px;font-size:1.15rem}
#info .sub{font-size:.82rem;color:#666}
#info .rs{font-size:.8rem;color:#c41e3a;font-weight:700;margin-top:3px}
#body{flex:1;display:flex;overflow:hidden}
#ext{width:300px;flex-shrink:0;border-right:1px solid #ddd;overflow-y:auto;padding:10px 12px}
#ext table{width:100%;border-collapse:collapse;font-size:.82rem}
#ext td{padding:3px 4px;border-bottom:1px solid #f0f0f0} #ext td.q{text-align:right;font-weight:800}
#ext .warn{color:#a15c00}
#pdfwrap{flex:1;display:flex;flex-direction:column}
#tabs{display:flex;gap:2px;padding:5px 8px;background:#eee;flex-wrap:wrap}
#tabs button{font-size:.76rem;padding:4px 10px;border:1px solid #ccc;border-radius:5px 5px 0 0;background:#fff;cursor:pointer}
#tabs button.on{background:#c41e3a;color:#fff}
iframe{flex:1;width:100%;border:0}
.hint{color:#999;padding:40px;text-align:center}
</style></head><body>
<div id="side"><h1>🔎 원본 대조 검증</h1>
<input id="q" placeholder="이름·지역 검색">
<div id="seg"><button data-g="" class="on">전체</button><button data-g="높음">🔴높음</button><button data-g="중간">🟡중간</button></div>
<div id="list"></div></div>
<div id="main"><div id="info"><div class="hint">왼쪽에서 인물을 선택하세요</div></div>
<div id="body"><div id="ext"></div><div id="pdfwrap"><div id="tabs"></div><iframe id="pdf"></iframe></div></div></div>
<script>
let DATA=[],cur=null,fg='';
fetch('data/verify_data.json?t='+Date.now()).then(r=>r.json()).then(d=>{DATA=d.people;renderList();});
const esc=s=>String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/"/g,'&quot;');
function renderList(){
  const q=document.getElementById('q').value.trim();
  const list=DATA.filter(p=>(!fg||p.grade===fg)&&(!q||p.name.includes(q)||(p.sido||'').includes(q)||(p.sgg||'').includes(q)));
  document.getElementById('list').innerHTML=list.slice(0,500).map((p,i)=>
    `<div class="it" data-hb="${p.huboid}"><span class="badge g${p.grade}">${p.grade}</span><span class="nm">${esc(p.name)}</span>`+
    `<div class="meta">${esc(p.office||'')} · ${esc(p.sido||'')} ${esc(p.sgg||'')} · ${p.holdings.length}종목</div></div>`).join('')
    +(list.length>500?`<div class="meta" style="padding:10px">…${list.length}명 중 500 표시(검색으로 좁히세요)</div>`:'');
}
document.getElementById('q').addEventListener('input',renderList);
document.querySelectorAll('#seg button').forEach(b=>b.addEventListener('click',()=>{
  fg=b.dataset.g;document.querySelectorAll('#seg button').forEach(x=>x.classList.toggle('on',x===b));renderList();}));
document.getElementById('list').addEventListener('click',e=>{
  const it=e.target.closest('.it');if(!it)return;
  document.querySelectorAll('.it').forEach(x=>x.classList.remove('sel'));it.classList.add('sel');
  select(DATA.find(p=>p.huboid===it.dataset.hb));});
function select(p){
  cur=p;
  document.getElementById('info').innerHTML=`<h2>${esc(p.name)} <span class="badge g${p.grade}">${p.grade}</span></h2>`+
    `<div class="sub">${esc(p.party||'')} · ${esc(p.office||'')} · ${esc(p.sido||'')} ${esc(p.sgg||'')} · huboid ${p.huboid}</div>`+
    (p.reasons.length?`<div class="rs">⚠ ${p.reasons.map(esc).join(' · ')}</div>`:'');
  document.getElementById('ext').innerHTML=`<table><tr><td colspan="2" style="font-weight:900">자동 추출 ${p.holdings.length}종목</td></tr>`+
    p.holdings.map(h=>{const big=(h.수량주||0)>10000000;return `<tr><td>${esc(h.종목)}</td><td class="q ${big?'warn':''}">${big?'확인필요':(h.수량주||0).toLocaleString()+'주'}</td></tr>`}).join('')+'</table>';
  const tabs=document.getElementById('tabs');
  tabs.innerHTML=p.pdfs.length?p.pdfs.map((f,i)=>`<button data-f="${encodeURI(f)}" class="${i===0?'on':''}">원본 ${i+1}</button>`).join(''):'';
  if(p.pdfs.length){document.getElementById('pdf').src=encodeURI(p.pdfs[0]);}
  else{document.getElementById('pdf').removeAttribute('src');tabs.innerHTML='<span class="meta" style="padding:6px">원본 PDF 없음</span>';}
}
document.getElementById('tabs').addEventListener('click',e=>{const b=e.target.closest('button');if(!b||!b.dataset.f)return;
  document.querySelectorAll('#tabs button').forEach(x=>x.classList.remove('on'));b.classList.add('on');
  document.getElementById('pdf').src=b.dataset.f;});
</script></body></html>"""


if __name__ == "__main__":
    main()
