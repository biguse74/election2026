// 당선 의원 주식·이해충돌 감시 — stocks/stock_holdings.json(슬림 공개본 + watch 블록) 기반.
'use strict';
const PARTY_COLOR = { '더불어민주당':'#152484', '국민의힘':'#E61E2B', '개혁신당':'#FF7210',
  '조국혁신당':'#0073CF', '진보당':'#D6001C', '무소속':'#888' };
const SIDO_ORDER = ['서울특별시','부산광역시','대구광역시','인천광역시','광주광역시','대전광역시','울산광역시','세종특별자치시','경기도','강원특별자치도','충청북도','충청남도','전북특별자치도','전라남도','경상북도','경상남도','제주특별자치도'];
const CAT_LABEL = {};   // key→{label,icon,why}

let DATA = null;
// 감시용 — 당선자만 수록. cat: 이해충돌 카테고리 키
const state = { q:'', party:'', sido:'', office:'', stock:'', cat:'' };

function esc(s){ return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/"/g,'&quot;'); }
function pc(p){ return PARTY_COLOR[p] || '#666'; }
function intc(n){ return (n==null||isNaN(n))?'—':Number(n).toLocaleString('ko-KR'); }

async function load(){
  try {
    const r = await fetch('stock_holdings.json?t='+Date.now(), {cache:'no-store'});
    DATA = await r.json();
  } catch(e){ document.getElementById('cand-grid').innerHTML = '<div class="empty">데이터를 불러오지 못했습니다.</div>'; return; }
  (DATA.watch?.cats||[]).forEach(c=>{ CAT_LABEL[c.key]={label:c.label,icon:c.icon,why:c.why}; });
  initHero(); initConflict(); initRich(); initRanking(); initFilters(); render();
}

const OFFICE_GRP_ORDER = ['단체장','지방의원','국회의원','교육감','기타'];
function officeSplit(by){
  if (!by) return '';
  return OFFICE_GRP_ORDER.filter(g=>by[g]).map(g=>{
    const cls = (g==='단체장'||g==='지방의원') ? 'cf-head' : 'cf-edu';
    return `<span class="${cls}">${g} ${by[g]}</span>`;
  }).join(' · ');
}

function initHero(){
  const w = DATA.watch || {};
  if (w.scope) document.getElementById('scope-txt').textContent = w.scope.split(' (')[0];
  const og = w.office_groups || {};
  document.getElementById('h-holders').textContent = (w.winner_holders||0) + '명';
  const lbl = document.getElementById('h-holders-lbl');
  const grpTxt = OFFICE_GRP_ORDER.filter(g=>og[g]).map(g=>`${g} ${og[g]}`).join('·');
  if (grpTxt) lbl.innerHTML = `주식 보유 당선자 <span style="color:var(--ink)">(${grpTxt})</span>`;
  // 가장 직접적인 이해충돌(direct tier)을 헤드라인으로
  const direct = (w.cats||[]).find(c=>c.tier==='direct');
  if (direct){
    document.getElementById('h-cf').innerHTML = `${direct.icon} ${esc(direct.label)} <small style="font-size:0.55em;color:var(--muted);font-weight:700">${direct.count}명</small>`;
    document.getElementById('h-cf-lbl').textContent = `지방권력과 직접 충돌하는 보유`;
  }
  const rich = (w.rich||[])[0];
  if (rich){
    document.getElementById('h-rich').innerHTML = `${esc(rich.name)} <small style="font-size:0.55em;color:var(--muted);font-weight:700">${rich.n}종목</small>`;
    document.getElementById('h-rich-lbl').textContent = `종목 최다 보유 · ${rich.party} ${rich.office}`;
  }
}

function initConflict(){
  const cats = (DATA.watch?.cats)||[];
  const tiers = (DATA.watch?.tiers)||[];
  const root = document.getElementById('conflict-grid');
  const cardHtml = c =>
    `<button class="cf-card ${c.tier}" data-cat="${esc(c.key)}">`+
    `<div class="cf-ic">${c.icon}</div>`+
    `<div class="cf-num">${c.count}<small>명</small></div>`+
    `<div class="cf-lbl">${esc(c.label)}</div>`+
    `<div class="cf-by">${officeSplit(c.by_office)}</div>`+
    `<div class="cf-why">${esc(c.why)}</div></button>`;
  root.innerHTML = tiers.map(t=>{
    const inTier = cats.filter(c=>c.tier===t.key);
    if (!inTier.length) return '';
    return `<div class="tier-grp">`+
      `<div class="tier-head"><span class="tier-dot ${t.key}"></span>`+
      `<span class="tier-name ${t.key}">${esc(t.label)}</span>`+
      `<span class="tier-desc">${esc(t.desc)}</span></div>`+
      `<div class="conflict-grid">${inTier.map(cardHtml).join('')}</div></div>`;
  }).join('');
  root.addEventListener('click', e=>{
    const card = e.target.closest('.cf-card'); if (!card) return;
    const k = card.getAttribute('data-cat');
    state.cat = (state.cat===k) ? '' : k;     // 토글
    state.stock=''; state.q=''; document.getElementById('f-q').value='';
    syncConflictActive(); syncRankActive();
    document.getElementById('cand-grid').scrollIntoView({behavior:'smooth', block:'start'});
    render();
  });
}
function syncConflictActive(){
  document.querySelectorAll('.cf-card').forEach(c=>
    c.classList.toggle('active', c.getAttribute('data-cat')===state.cat));
}

function richRows(id, data, valFn){
  const root = document.getElementById(id);
  if (!root) return;
  root.innerHTML = (data||[]).map((r,i)=>
    `<div class="rich-row" data-name="${esc(r.name)}">`+
    `<span class="rich-i">${i+1}</span>`+
    `<span class="rich-name">${esc(r.name)}<span class="rich-meta">${esc(r.party)} · ${esc(r.office)} ${esc(r.sido||'')}</span></span>`+
    `<span class="rich-cnt">${valFn(r)}</span></div>`).join('');
}
function initRich(){
  richRows('rich-list', DATA.watch?.rich, r=>`${r.n}<small>종목</small>`);
  document.querySelectorAll('#rich-list').forEach(root=>
    root.addEventListener('click', e=>{
      const row = e.target.closest('.rich-row'); if (!row) return;
      const nm = row.getAttribute('data-name');
      state.q = (state.q===nm) ? '' : nm;
      document.getElementById('f-q').value = state.q;
      state.cat=''; state.stock=''; syncConflictActive(); syncRankActive();
      document.getElementById('cand-grid').scrollIntoView({behavior:'smooth', block:'start'});
      render();
    }));
}

function stockRanking(){
  // 종목별 '보유자 수'(1인이 같은 종목 여러건이어도 1). 당선자만 수록된 데이터.
  const m = new Map();
  for (const p of DATA.people){
    const seen = new Set();
    for (const h of p.holdings){ if (!seen.has(h.종목)){ seen.add(h.종목); m.set(h.종목, (m.get(h.종목)||0)+1); } }
  }
  return [...m.entries()].sort((a,b)=> b[1]-a[1] || a[0].localeCompare(b[0],'ko'));
}

function initRanking(){ renderRanking(); }
function renderRanking(){
  const rank = stockRanking().slice(0, 30);
  const max = rank.length ? rank[0][1] : 1;
  const root = document.getElementById('rank-list');
  root.innerHTML = rank.map((r,i)=>
    `<div class="rank-row" data-stock="${esc(r[0])}"><span class="rank-i">${i+1}</span>`+
    `<span class="rank-name">${esc(r[0])}</span>`+
    `<span class="rank-bar-wrap"><span class="rank-bar" style="width:${(r[1]/max*100).toFixed(1)}%"></span></span>`+
    `<span class="rank-cnt">${r[1]}명</span></div>`).join('');
  if (!root._bound){
    root._bound = true;
    root.addEventListener('click', e=>{
      const row = e.target.closest('.rank-row'); if (!row) return;
      const s = row.getAttribute('data-stock');
      state.stock = (state.stock===s) ? '' : s;
      state.q=''; state.cat=''; document.getElementById('f-q').value=''; syncConflictActive();
      syncRankActive(); render();
    });
  }
  syncRankActive();
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
    if (state.q){ state.stock=''; state.cat=''; syncRankActive(); syncConflictActive(); } render(); });
  document.getElementById('f-party').addEventListener('change', e=>{ state.party=e.target.value; render(); });
  document.getElementById('f-sido').addEventListener('change', e=>{ state.sido=e.target.value; render(); });
  document.getElementById('f-office').addEventListener('change', e=>{ state.office=e.target.value; render(); });
  document.getElementById('f-clear').addEventListener('click', ()=>{
    state.q=state.party=state.sido=state.office=state.stock=state.cat='';
    document.getElementById('f-q').value=''; document.getElementById('f-party').value='';
    document.getElementById('f-sido').value=''; document.getElementById('f-office').value='';
    syncRankActive(); syncConflictActive(); render();
  });
}

function matches(p){
  if (state.cat && !(p.cats||[]).includes(state.cat)) return false;
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

// 종목 검색 시 "OO 보유 당선자 N명 + 정당별 분포" 배너. (이름 검색이면 숨김)
function renderHolderSummary(list){
  const hs = document.getElementById('holder-summary');
  if (!hs) return;
  let stock = state.stock;
  if (!stock && state.q){
    const ql = state.q.toLowerCase();
    const nameHit = list.some(p=>(p.name||'').toLowerCase().includes(ql));
    if (!nameHit){
      for (const p of list){ const h=(p.holdings||[]).find(h=>h.종목.toLowerCase().includes(ql)); if (h){ stock=h.종목; break; } }
    }
  }
  if (!stock || !list.length){ hs.hidden = true; hs.innerHTML=''; return; }
  const byParty = {};
  list.forEach(p=>{ byParty[p.party]=(byParty[p.party]||0)+1; });
  const chips = Object.entries(byParty).sort((a,b)=>b[1]-a[1]).map(([p,n])=>
    `<span class="hs-pchip"><i style="background:${pc(p)}"></i>${esc(p)} ${n}</span>`).join('');
  hs.innerHTML = `<div class="hs-title">📈 <b>${esc(stock)}</b> 보유 당선자 <b>${list.length}명</b></div><div class="hs-parties">${chips}</div>`;
  hs.hidden = false;
}

const RENDER_CAP = 300;   // 1,500+명 전체를 한 번에 그리면 무거움 → 상위 N만(검색·필터로 좁힘)
function render(){
  if (!DATA) return;
  let list = DATA.people.filter(matches);
  // 보유 있음 우선 → 검토필요(OCR 칸뭉침으로 종목수 폭발)는 뒤로 → 종목 많은 순 → 이름
  list.sort((a,b)=> (b.holdings.length>0)-(a.holdings.length>0)
    || ((a.needs_review?1:0)-(b.needs_review?1:0))
    || b.holdings.length-a.holdings.length
    || (a.name||'').localeCompare(b.name||'','ko'));
  const grid = document.getElementById('cand-grid');
  const empty = document.getElementById('empty');
  const catTxt = state.cat ? ` · ${CAT_LABEL[state.cat]?.icon||''} ${CAT_LABEL[state.cat]?.label||''}` : '';
  const capped = list.length > RENDER_CAP;
  const capTxt = capped ? ` · 종목 많은 순 상위 ${RENDER_CAP} 표시(검색·필터로 좁혀보세요)` : '';
  document.getElementById('f-count').textContent = `${list.length}명${catTxt}${capTxt}`;
  renderHolderSummary(list);   // 종목 검색이면 "OO 보유 당선자 N명 · 정당별" 배너
  if (!list.length){ grid.innerHTML=''; empty.hidden=false; return; }
  empty.hidden = true;
  if (capped) list = list.slice(0, RENDER_CAP);
  const q = state.q.toLowerCase();
  grid.innerHTML = list.map(p=>{
    const photo = p.photo
      ? `<img class="sc-photo" src="${esc(p.photo)}" alt="${esc(p.name)}" loading="lazy" referrerpolicy="no-referrer" onerror="this.style.display='none'">`
      : `<span class="sc-noimg">${esc((p.name||' ').slice(0,1))}</span>`;
    const region = [p.sido, p.sgg].filter(Boolean).join(' ');
    const chips = p.holdings.length
      ? p.holdings.map(h=>{
          const hit = (state.stock && h.종목===state.stock) || (q && h.종목.toLowerCase().includes(q));
          const inCat = state.cat && (h.cats||[]).includes(state.cat);
          const cls = inCat ? 'sc-chip cf' : (hit ? 'sc-chip hit' : 'sc-chip');
          return `<span class="${cls}">${esc(h.종목)} <b>${intc(h.수량주)}</b>주</span>`;
        }).join('')
      : `<span class="sc-chip" style="background:#fdf0d5;border-color:#f0d6a8;color:#7a5a1e;">원문 확인 필요(추출 실패)</span>`;
    const nStocks = p.holdings.length;
    const sizeTxt = nStocks ? `<span class="sc-size">${nStocks}종목</span>` : '';
    return `<div class="sc-card">${photo}<div class="sc-body">`+
      `<div class="sc-top"><span class="sc-name">${esc(p.name)}</span>`+
        `<span class="sc-party" style="color:${pc(p.party)}">${esc(p.party)}</span>${sizeTxt}</div>`+
      `<div class="sc-meta">${esc(p.office)} · ${esc(region)}</div>`+
      `<div class="sc-chips">${chips}</div>`+
      `</div></div>`;
  }).join('');
}

load();
