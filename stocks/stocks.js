// 후보 주식보유 페이지 — stocks/stock_holdings.json(슬림 공개본) 기반.
'use strict';
const PARTY_COLOR = { '더불어민주당':'#152484', '국민의힘':'#E61E2B', '개혁신당':'#FF7210',
  '조국혁신당':'#0073CF', '진보당':'#D6001C', '무소속':'#888' };
const SIDO_ORDER = ['서울특별시','부산광역시','대구광역시','인천광역시','광주광역시','대전광역시','울산광역시','세종특별자치시','경기도','강원특별자치도','충청북도','충청남도','전북특별자치도','전라남도','경상북도','경상남도','제주특별자치도'];

let DATA = null;
const state = { q:'', party:'', sido:'', office:'', stock:'' };

function esc(s){ return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/"/g,'&quot;'); }
function pc(p){ return PARTY_COLOR[p] || '#666'; }
function intc(n){ return (n==null||isNaN(n))?'—':Number(n).toLocaleString('ko-KR'); }

async function load(){
  try {
    const r = await fetch('stock_holdings.json?t='+Date.now(), {cache:'no-store'});
    DATA = await r.json();
  } catch(e){ document.getElementById('cand-grid').innerHTML = '<div class="empty">데이터를 불러오지 못했습니다.</div>'; return; }
  initHero(); initRanking(); initFilters(); render();
}

function initHero(){
  document.getElementById('h-clean').textContent = DATA.clean + '명';
  document.getElementById('h-review').textContent = DATA.review_only + '명';
  const rank = stockRanking();
  if (rank.length){ document.getElementById('h-top').textContent = rank[0][0];
    document.getElementById('h-top-lbl').textContent = `최다 보유 종목 (${rank[0][1]}명)`; }
}

function stockRanking(){
  // 종목별 '보유 후보 수'(한 후보가 같은 종목 여러 건이어도 1명으로)
  const m = new Map();
  for (const p of DATA.people){
    const seen = new Set();
    for (const h of p.holdings){ if (!seen.has(h.종목)){ seen.add(h.종목); m.set(h.종목, (m.get(h.종목)||0)+1); } }
  }
  return [...m.entries()].sort((a,b)=> b[1]-a[1] || a[0].localeCompare(b[0],'ko'));
}

function initRanking(){
  const rank = stockRanking().slice(0, 30);
  const max = rank.length ? rank[0][1] : 1;
  const root = document.getElementById('rank-list');
  root.innerHTML = rank.map((r,i)=>
    `<div class="rank-row" data-stock="${esc(r[0])}"><span class="rank-i">${i+1}</span>`+
    `<span class="rank-name">${esc(r[0])}</span>`+
    `<span class="rank-bar-wrap"><span class="rank-bar" style="width:${(r[1]/max*100).toFixed(1)}%"></span></span>`+
    `<span class="rank-cnt">${r[1]}명</span></div>`).join('');
  root.addEventListener('click', e=>{
    const row = e.target.closest('.rank-row'); if (!row) return;
    const s = row.getAttribute('data-stock');
    state.stock = (state.stock===s) ? '' : s;         // 토글
    state.q = ''; document.getElementById('f-q').value = '';
    syncRankActive(); render();
  });
}
function syncRankActive(){
  document.querySelectorAll('.rank-row').forEach(r=>
    r.classList.toggle('active', r.getAttribute('data-stock')===state.stock));
}

function initFilters(){
  const parties = [...new Set(DATA.people.map(p=>p.party))].sort((a,b)=>a.localeCompare(b,'ko'));
  const sidos = [...new Set(DATA.people.map(p=>p.sido))].sort((a,b)=> SIDO_ORDER.indexOf(a)-SIDO_ORDER.indexOf(b));
  const offices = [...new Set(DATA.people.map(p=>p.office))];
  const fill = (id, arr)=>{ const el=document.getElementById(id);
    arr.forEach(v=>{ const o=document.createElement('option'); o.value=v; o.textContent=v; el.appendChild(o); }); };
  fill('f-party', parties); fill('f-sido', sidos); fill('f-office', offices);
  document.getElementById('f-q').addEventListener('input', e=>{ state.q=e.target.value.trim();
    if (state.q){ state.stock=''; syncRankActive(); } render(); });
  document.getElementById('f-party').addEventListener('change', e=>{ state.party=e.target.value; render(); });
  document.getElementById('f-sido').addEventListener('change', e=>{ state.sido=e.target.value; render(); });
  document.getElementById('f-office').addEventListener('change', e=>{ state.office=e.target.value; render(); });
  document.getElementById('f-clear').addEventListener('click', ()=>{
    state.q=state.party=state.sido=state.office=state.stock='';
    document.getElementById('f-q').value=''; document.getElementById('f-party').value='';
    document.getElementById('f-sido').value=''; document.getElementById('f-office').value='';
    syncRankActive(); render();
  });
}

function matches(p){
  if (state.party && p.party!==state.party) return false;
  if (state.sido && p.sido!==state.sido) return false;
  if (state.office && p.office!==state.office) return false;
  if (state.stock && !p.holdings.some(h=>h.종목===state.stock)) return false;
  if (state.q){ const q=state.q.toLowerCase();
    const inName = (p.name||'').toLowerCase().includes(q);
    const inStock = p.holdings.some(h=>h.종목.toLowerCase().includes(q));
    if (!inName && !inStock) return false;
  }
  return true;
}

function render(){
  if (!DATA) return;
  let list = DATA.people.filter(matches);
  // 정렬: 종목 많은 순, 같으면 이름. 검토필요(종목0)는 뒤로.
  list.sort((a,b)=> (b.holdings.length>0)-(a.holdings.length>0) || b.holdings.length-a.holdings.length || (a.name||'').localeCompare(b.name||'','ko'));
  const grid = document.getElementById('cand-grid');
  const empty = document.getElementById('empty');
  document.getElementById('f-count').textContent = `${list.length}명`;
  if (!list.length){ grid.innerHTML=''; empty.hidden=false; return; }
  empty.hidden = true;
  const q = state.q.toLowerCase();
  grid.innerHTML = list.map(p=>{
    const photo = p.photo
      ? `<img class="sc-photo" src="${esc(p.photo)}" alt="${esc(p.name)}" loading="lazy" referrerpolicy="no-referrer" onerror="this.style.display='none'">`
      : `<span class="sc-noimg">${esc((p.name||' ').slice(0,1))}</span>`;
    const region = [p.sido, p.sgg].filter(Boolean).join(' ');
    const chips = p.holdings.length
      ? p.holdings.map(h=>{
          const hit = (state.stock && h.종목===state.stock) || (q && h.종목.toLowerCase().includes(q));
          return `<span class="sc-chip${hit?' hit':''}">${esc(h.종목)} <b>${intc(h.수량주)}</b>주</span>`;
        }).join('')
      : `<span class="sc-chip" style="background:#fdf0d5;border-color:#f0d6a8;color:#7a5a1e;">원문 확인 필요(추출 실패)</span>`;
    const review = p.needs_review ? `<span class="sc-review">검토필요</span>` : '';
    const nec = p.nec_url ? `<a href="${esc(p.nec_url)}" target="_blank" rel="noopener">선관위 원문 ↗</a>` : '';
    return `<div class="sc-card">${photo}<div class="sc-body">`+
      `<div class="sc-top"><span class="sc-name">${esc(p.name)}</span>`+
        `<span class="sc-party" style="color:${pc(p.party)}">${esc(p.party)}</span>${review}</div>`+
      `<div class="sc-meta">${esc(p.office)} · ${esc(region)}</div>`+
      `<div class="sc-chips">${chips}</div>`+
      `<div class="sc-links">${nec}</div>`+
      `</div></div>`;
  }).join('');
}

load();
