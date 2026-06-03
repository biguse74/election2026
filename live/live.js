// 실시간 개표 페이지 로직
// 데이터 소스:
//   data/live_counting/current.json    — 선관위 OpenAPI 가공본 (투표율 + races[])
//   data/live_counting/watchlist.json  — 주목 후보 목록 (수동 편집)
//   data/live_counting/groups.json     — 관심 지역 그룹 (수동 편집)
//   data/prediction_sido.json          — 뉴탐사 자체 시뮬레이션 (시도별 민주 당선확률 %)
//   data/parties.json                  — 정당 색상

const PATHS = {
  current:     '../data/live_counting/current.json',
  watchlist:   '../data/live_counting/watchlist.json',
  groups:      '../data/live_counting/groups.json',
  prevWinner:  '../data/live_counting/prev_winner.json',
  prevResult:  '../data/live_counting/prev_result.json',
  prediction:  '../data/prediction_sido.json',
  predBasicHead: '../data/prediction_basic_head.json',
  parties:     '../data/parties.json',
  earlyVoting: '../data/early_voting/20260603/latest.json',
  histHourly:  '../data/history_turnout_hourly.json',
  exitPoll:    '../data/live_counting/exit_poll.json',
  photos:      './candidate_photos.json',
};

const DEM = '더불어민주당';
const CON = '국민의힘';
const REFRESH_MS = 60 * 1000;  // 1분마다 재로딩 (개표일에만 의미)

const SIDO_ORDER = [
  '서울특별시', '부산광역시', '대구광역시', '인천광역시', '광주광역시',
  '대전광역시', '울산광역시', '세종특별자치시', '경기도', '강원특별자치도',
  '충청북도', '충청남도', '전북특별자치도', '전라남도', '경상북도',
  '경상남도', '제주특별자치도', '전남광주통합특별시',
];
const SIDO_SHORT = {
  '서울특별시': '서울', '부산광역시': '부산', '대구광역시': '대구', '인천광역시': '인천',
  '광주광역시': '광주', '대전광역시': '대전', '울산광역시': '울산', '세종특별자치시': '세종',
  '경기도': '경기', '강원특별자치도': '강원', '충청북도': '충북', '충청남도': '충남',
  '전북특별자치도': '전북', '전라남도': '전남', '경상북도': '경북', '경상남도': '경남',
  '제주특별자치도': '제주', '전남광주통합특별시': '전남광주',
};
const TYPE_ORDER = ['3', '4', '5', '6', '11'];

let LATEST_RACES = [];
let LATEST_PARTIES = {};
let LATEST_PREVWIN = {};
let LATEST_PREVRESULT = {};
let filtersBound = false;
let filtersPopulated = false;
let expandBound = false;
const expandedKeys = new Set();  // 펼쳐진 선거구 race_key (갱신에도 유지)

// 후보 사진 조회맵(중앙선관위 후보 사진). 개표 단계에서만 1회 lazy-load.
let PHOTO_MAP = null;
let _photoPromise = null;
function ensurePhotos() {
  if (PHOTO_MAP) return Promise.resolve(PHOTO_MAP);
  if (!_photoPromise) {
    _photoPromise = loadJSON(PATHS.photos).then(m => { PHOTO_MAP = m || { by_full: {}, by_sd: {} }; return PHOTO_MAP; });
  }
  return _photoPromise;
}
// race + candidate → https 사진 URL (없으면 null). 미세키→통합키→거친키 순.
function candPhoto(r, c) {
  if (!PHOTO_MAP || !c) return null;
  const t = r.sg_type_code || '', sd = r.sd_name || '', sgg = r.sgg_name || sd, nm = (c.name || '').trim();
  if (!nm) return null;
  const f = PHOTO_MAP.by_full || {}, s = PHOTO_MAP.by_sd || {};
  return f[`${t}|${sd}|${sgg}|${nm}`] || f[`${t}|${sd}|${sd}|${nm}`] || s[`${t}|${sd}|${nm}`] || null;
}
function candPhotoImg(r, c, cls) {
  const u = candPhoto(r, c);
  return u
    ? `<img class="${cls}" src="${esc(u)}" alt="${esc(c.name || '')}" loading="lazy" referrerpolicy="no-referrer" onerror="this.style.display='none'">`
    : `<span class="${cls} cand-noimg">${esc((c.name || ' ').slice(0, 1))}</span>`;
}

async function loadJSON(path) {
  try {
    const res = await fetch(path + '?t=' + Date.now(), { cache: 'no-store' });
    if (!res.ok) return null;
    return await res.json();
  } catch (e) { return null; }
}

function fmt1(v) { return (v == null || isNaN(v)) ? '—' : Number(v).toFixed(1); }
function intComma(v) { return (v == null || isNaN(v)) ? '—' : Number(v).toLocaleString('ko-KR'); }
function partyColor(parties, name) { return (parties && parties[name]) || '#888'; }
function esc(s) { return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;'); }

// 피어슨 상관 + 단순회귀
function pearson(xs, ys) {
  const n = xs.length;
  if (n < 2) return null;
  const mx = xs.reduce((a, b) => a + b, 0) / n;
  const my = ys.reduce((a, b) => a + b, 0) / n;
  let sxy = 0, sxx = 0, syy = 0;
  for (let i = 0; i < n; i++) { const dx = xs[i] - mx, dy = ys[i] - my; sxy += dx * dy; sxx += dx * dx; syy += dy * dy; }
  if (sxx <= 0 || syy <= 0) return null;
  return { r: sxy / Math.sqrt(sxx * syy), slope: sxy / sxx, intercept: my - (sxy / sxx) * mx, n };
}

function fmtKST(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso);
    const mm = `${d.getMonth() + 1}`.padStart(2, '0');
    const dd = `${d.getDate()}`.padStart(2, '0');
    const hh = `${d.getHours()}`.padStart(2, '0');
    const mi = `${d.getMinutes()}`.padStart(2, '0');
    return `${mm}/${dd} ${hh}:${mi}`;
  } catch (e) { return iso; }
}

function racePlace(r) {
  const tail = [r.sgg_name, r.wiw_name].filter(x => x && x !== '합계' && x !== r.sd_name).join(' ');
  return tail ? `${r.sd_name} ${tail}` : r.sd_name;
}

// 선거구 전체 후보 상세 (펼침 영역)
function candDetailHTML(r) {
  const cands = r.candidates || [];
  if (!cands.length) return '<div class="rd-empty">후보 데이터 없음</div>';
  return cands.map(c => {
    const color = partyColor(LATEST_PARTIES, c.jd_name);
    const w = Math.max(0, Math.min(100, c.share_pct || 0));
    return `<div class="rd-cand">
      <span class="rd-rank">${c.current_rank}</span>
      ${candPhotoImg(r, c, 'rd-photo')}
      <span class="cand-dot" style="background:${color}"></span>
      <span class="rd-name">${c.name || '—'}</span>
      <span class="rd-party">${c.jd_name || ''}</span>
      <span class="rd-bar-wrap"><span class="rd-bar" style="width:${w}%;background:${color}"></span></span>
      <span class="rd-share">${fmt1(c.share_pct)}%</span>
      <span class="rd-votes">${intComma(c.votes)}표</span>
    </div>`;
  }).join('');
}

// 표 한 행(요약, 클릭 시 펼침) + 상세 행 — 검색·그룹 공용
function raceTableRow(r) {
  const rk = r.race_key || '';
  const c1 = (r.candidates || [])[0];
  const c2 = (r.candidates || [])[1];
  const dot = c1 ? `<span class="cand-dot" style="background:${partyColor(LATEST_PARTIES, c1.jd_name)}"></span>` : '';
  const lphoto = c1 ? candPhotoImg(r, c1, 'lead-photo') : '';
  const lead = c1 ? `${lphoto}${dot}<b>${c1.name}</b> <span class="cand-party">${c1.jd_name || ''}</span> ${fmt1(c1.share_pct)}%` : '—';
  const second = c2 ? `${c2.name} ${fmt1(c2.share_pct)}%` : '—';
  const open = expandedKeys.has(rk);
  const summary = `<tr class="race-sum" data-rk="${esc(rk)}">
    <td>${r.sg_type_label}</td>
    <td>${racePlace(r)}</td>
    <td class="lead-cell">${lead}</td>
    <td>${second}</td>
    <td class="num">${fmt1(r.rank1_minus_rank2_pp)}pp</td>
    <td class="num">${fmt1(r.progress_pct)}%<span class="rd-caret">${open ? '▴' : '▾'}</span></td>
  </tr>`;
  const detail = `<tr class="rd-row" data-rk="${esc(rk)}"${open ? '' : ' hidden'}>
    <td colspan="6"><div class="rd-box">${candDetailHTML(r)}</div></td>
  </tr>`;
  return summary + detail;
}

function raceTable(rows) {
  return `<div class="other-wrap"><table class="other">
    <thead><tr><th>선거</th><th>지역</th><th>1위</th><th>2위</th><th>격차</th><th>개표</th></tr></thead>
    <tbody>${rows}</tbody>
  </table></div>`;
}

// 표 행 클릭 → 해당 선거구 상세 토글 (delegation, 1회 바인드)
function bindRaceExpand() {
  if (expandBound) return;
  document.addEventListener('click', (ev) => {
    const row = ev.target.closest('tr.race-sum');
    if (!row) return;
    const rk = row.getAttribute('data-rk');
    if (rk == null) return;
    const on = !expandedKeys.has(rk);
    if (on) expandedKeys.add(rk); else expandedKeys.delete(rk);
    document.querySelectorAll('tr.rd-row').forEach(d => { if (d.getAttribute('data-rk') === rk) d.hidden = !on; });
    document.querySelectorAll('tr.race-sum').forEach(s => {
      if (s.getAttribute('data-rk') === rk) { const ca = s.querySelector('.rd-caret'); if (ca) ca.textContent = on ? '▴' : '▾'; }
    });
  });
  expandBound = true;
}

// ── Hero ──────────────────────────────────────────────────────────
function renderHero(cur, earlyVoting) {
  const nat = cur?.turnout?.national;
  const badge = document.getElementById('live-badge');
  if (cur?.phase === 'live') badge.hidden = false;

  const t = document.getElementById('hero-turnout');
  const tm = document.getElementById('hero-turnout-meta');
  if (nat?.turnout_pct != null) {
    t.innerHTML = `${fmt1(nat.turnout_pct)}<span class="pct">%</span>`;
    tm.textContent = `투표자 ${intComma(nat.voters_so_far)} / 선거인 ${intComma(nat.eligible_voters)}`;
  }

  const races = cur?.races || [];
  const p = document.getElementById('hero-progress');
  const pm = document.getElementById('hero-progress-meta');
  if (races.length) {
    let wsum = 0, w = 0;
    for (const r of races) { const e = r.eligible_voters || 0; wsum += (r.progress_pct || 0) * e; w += e; }
    const avg = w ? wsum / w : 0;
    p.innerHTML = `${fmt1(avg)}<span class="pct">%</span>`;
    pm.textContent = `수집된 선거구 ${races.length}곳 기준 (선거인 가중)`;
  } else {
    p.innerHTML = `대기<span class="pct"></span>`;
    pm.textContent = '18시 마감 후 개표 시작';
  }

  document.getElementById('updated-at').textContent = fmtKST(cur?.polled_at) + ' (KST)';
}

// 역대 전국동시지방선거 최종 투표율(%) — 중앙선관위 공식 확정치.
const ZIBANG_HISTORY = [
  { round: 1, year: 1995, rate: 68.4 },
  { round: 2, year: 1998, rate: 52.7 },
  { round: 3, year: 2002, rate: 48.9 },
  { round: 4, year: 2006, rate: 51.6 },
  { round: 5, year: 2010, rate: 54.5 },
  { round: 6, year: 2014, rate: 56.8 },
  { round: 7, year: 2018, rate: 60.2 },
  { round: 8, year: 2022, rate: 50.9 },
];

// ── 예상 최종 투표율 (전국) — '도달 수준' 매칭 가산법 ─────────────────
// 시도별 표와 동일한 방식. 현재 누계값(사전 포함)과 같은 수준에 도달했던 과거선거
// 시점을 찾아 거기서 최종까지의 증가분(평균)을 더한다. 시각 배율법은 사전 합산
// 타이밍 차이로 과대추정되므로 쓰지 않는다(상단 박스 = 시도별 표 전국값 일치).
function computeProjection(cur, histHourly) {
  const nat = cur && cur.turnout && cur.turnout.national;
  let level = nat && nat.turnout_pct;
  if (level == null) {  // 박스 누계값 없으면 정시 최신값으로 폴백
    const today = (cur && cur.turnout && cur.turnout.hourly) || [];
    level = today.length ? today[today.length - 1].turnout_pct : null;
  }
  if (level == null) return null;
  const incs = [];
  for (const r of ((histHourly && histHourly.rounds) || [])) {
    const arr = r.national || [];
    if (!arr.length) continue;
    const fin = arr[arr.length - 1].turnout_pct;
    if (fin == null) continue;
    let base = null;
    for (const d of arr) { if (d.turnout_pct != null && d.turnout_pct >= level) { base = d.turnout_pct; break; } }
    if (base == null) base = fin;  // 과거 최종보다 이미 높으면 잔여 0
    incs.push(Math.max(0, fin - base));
  }
  if (!incs.length) return null;
  const mean = incs.reduce((s, v) => s + v, 0) / incs.length;
  const cap = v => Math.min(99, v);
  return { x0: level, n: incs.length, proj: cap(level + mean), lo: cap(level + Math.min(...incs)), hi: cap(level + Math.max(...incs)) };
}

// 예상 최종 투표율의 역대 맥락 한 줄. 불확실성(범위) 명시, '역대 최고' 단정 금지(1995년 68.4%가 역대 1위).
function projectionContext(pj) {
  const record = Math.max(...ZIBANG_HISTORY.map(h => h.rate));  // 1995년 68.4%
  const rank = ZIBANG_HISTORY.filter(h => h.rate > pj.proj).length + 1;
  const ctx = (pj.proj >= record)
    ? `1995년 ${fmt1(record)}% 상회 수준(추정)`
    : `역대 ${rank}위권 · 1995년 ${fmt1(record)}% 이후 높은 수준`;
  return `도달수준 추정 · 범위 ${fmt1(pj.lo)}~${fmt1(pj.hi)}% · ${ctx}`;
}

function renderProjection(cur, histHourly) {
  const e = document.getElementById('hero-early');
  const meta = document.getElementById('hero-early-meta');
  if (!e) return;
  const pj = computeProjection(cur, histHourly);
  if (!pj) return;
  e.innerHTML = `${fmt1(pj.proj)}<span class="pct">%</span>`;
  if (meta) meta.textContent = projectionContext(pj);
}

// ── 4년 전(2022) 동시각 투표율 카드 (투표 중 표시) ─────────────────
function renderCompare2022(cur, histHourly) {
  const big = document.getElementById('hero-cmp');
  const meta = document.getElementById('hero-cmp-meta');
  if (!big) return;
  const hourly = (cur && cur.turnout && cur.turnout.hourly) || [];
  if (!hourly.length) return;
  const cp = hourly[hourly.length - 1];              // 마지막 정시점(HH:00) — 사과 대 사과 비교
  const T = cp.time, todayV = cp.turnout_pct;
  const r2022 = ((histHourly && histHourly.rounds) || []).find(r => r.year === 2022);
  const at = r2022 && (r2022.national || []).find(d => d.time === T);
  if (!at || at.turnout_pct == null || todayV == null) return;
  big.innerHTML = `${fmt1(at.turnout_pct)}<span class="pct">%</span>`;
  if (meta) {
    const dv = todayV - at.turnout_pct;
    const word = dv > 0.05 ? `${fmt1(dv)}%p 빠름` : (dv < -0.05 ? `${fmt1(Math.abs(dv))}%p 느림` : '비슷');
    meta.textContent = `${parseInt(T)}시 기준 · 오늘이 4년 전보다 ${word}`;
  }
}

// ── 역대 지방선거 투표율 비교 (1~8회 + 오늘 회귀 추정) ───────────────
function renderHistoryCompare(cur, histHourly) {
  const block = document.getElementById('histcmp-block');
  const wrap = document.getElementById('histcmp-table');
  const note = document.getElementById('histcmp-note');
  if (!block || !wrap) return;
  const pj = computeProjection(cur, histHourly);
  // 막대 최대 기준: 역대 최고(1995 68.4%)와 오늘 추정 중 큰 값 + 여유
  const maxRate = Math.max(...ZIBANG_HISTORY.map(h => h.rate), (pj && pj.proj) || 0) + 3;
  const recordYear = ZIBANG_HISTORY.reduce((a, b) => (b.rate > a.rate ? b : a)).year;
  const rows = ZIBANG_HISTORY.map(h => {
    const w = (h.rate / maxRate * 100).toFixed(1);
    const top1 = h.year === recordYear ? `<span class="hc-top1">역대1위</span>` : '';
    return `<div class="hc-row">` +
      `<div class="hc-name">${h.round}회 ${h.year}${top1}</div>` +
      `<div class="hc-bar-wrap"><div class="hc-bar" style="width:${w}%"></div></div>` +
      `<div class="hc-val">${fmt1(h.rate)}%</div></div>`;
  });
  if (pj) {
    const w = (pj.proj / maxRate * 100).toFixed(1);
    rows.push(`<div class="hc-row hc-today">` +
      `<div class="hc-name">9회 2026<span class="hc-est">예상</span></div>` +
      `<div class="hc-bar-wrap"><div class="hc-bar hc-bar-today" style="width:${w}%"></div></div>` +
      `<div class="hc-val">${fmt1(pj.proj)}%</div></div>`);
  }
  wrap.innerHTML = rows.join('');
  if (note) {
    note.textContent = pj
      ? `오늘 예상은 같은 누계 도달 시점→최종 증가분 추정(범위 ${fmt1(pj.lo)}~${fmt1(pj.hi)}%). 확정 아님.`
      : `역대 지방선거 최종 투표율(중앙선거관리위원회 확정). 1995년 1회가 ${fmt1(Math.max(...ZIBANG_HISTORY.map(h=>h.rate)))}%로 역대 최고.`;
  }
  block.hidden = false;
}

// ── 시도별 실시간 투표율 표 ────────────────────────────────────────
function renderTurnoutTable(cur, histHourly) {
  const block = document.getElementById('turnout-block');
  const wrap = document.getElementById('turnout-table');
  if (!block || !wrap) return;
  const nat = cur && cur.turnout && cur.turnout.national;
  if (!nat || nat.turnout_pct == null) { block.hidden = true; return; }
  block.hidden = false;
  const tt = document.getElementById('turnout-time');
  if (tt) tt.textContent = fmtKST(cur.polled_at) + ' (KST)';
  const hourly = (cur.turnout.hourly || []);
  const curT = hourly.length ? hourly[hourly.length - 1].time : null;
  const r2022 = ((histHourly && histHourly.rounds) || []).find(r => r.year === 2022);
  const past2022 = sd => {
    if (!r2022 || !curT) return null;
    const arr = sd === '전국' ? r2022.national : (r2022.by_sido && r2022.by_sido[sd]);
    const hit = arr && arr.find(d => d.time === curT);
    return hit ? hit.turnout_pct : null;
  };
  // 시도별 예상 최종 투표율 — '도달 수준' 매칭 가산법.
  // 현재 누계값엔 사전투표가 이미 합산돼 있을 수 있어, 시각 기준 배율법은 과대추정된다.
  // 대신 과거선거에서 '같은 누계 수준'에 도달했던 지점을 찾아, 거기서 최종까지의
  // 증가분(평균)을 현재값에 더한다. 수준으로 매칭하므로 사전 합산 타이밍에 둔감하다.
  const remainingPP = (sd, level) => {
    if (level == null) return null;
    const incs = [];
    for (const r of ((histHourly && histHourly.rounds) || [])) {
      const arr = sd === '전국' ? r.national : (r.by_sido && r.by_sido[sd]);
      if (!arr || !arr.length) continue;
      const fin = arr[arr.length - 1].turnout_pct;
      if (fin == null) continue;
      let base = null;
      for (const d of arr) { if (d.turnout_pct != null && d.turnout_pct >= level) { base = d.turnout_pct; break; } }
      if (base == null) base = fin;  // 과거 최종보다 이미 높으면 잔여 증가분 0
      incs.push(Math.max(0, fin - base));
    }
    return incs.length ? incs.reduce((a, b) => a + b, 0) / incs.length : null;
  };
  const natRem = remainingPP('전국', nat.turnout_pct);
  const projOf = (s) => {
    if (s.turnout_pct == null) return null;
    const rem = remainingPP(s.sd_name, s.turnout_pct) ?? natRem;
    if (rem == null) return null;
    return Math.min(99, s.turnout_pct + rem);
  };
  const sidos = (cur.turnout.by_sido || []).slice().sort((a, b) => (b.turnout_pct || 0) - (a.turnout_pct || 0));
  const maxPct = Math.max(nat.turnout_pct || 0, ...sidos.map(s => s.turnout_pct || 0), 1);
  const natMark = ((nat.turnout_pct || 0) / maxPct * 100).toFixed(1);  // 전국 평균 파선 위치
  const row = (s, isNat) => {
    const pv = past2022(s.sd_name);
    const proj = projOf(s);
    const w = ((s.turnout_pct || 0) / maxPct * 100).toFixed(1);
    return `<div class="tr-row${isNat ? ' tr-nat' : ''}" title="투표 ${intComma(s.voters_so_far)} / 선거인 ${intComma(s.eligible_voters)}${pv != null ? ` · 2022 ${curT} 같은시각 ${fmt1(pv)}%` : ''}">` +
      `<div class="tr-name">${s.sd_name}</div>` +
      `<div class="tr-bar-wrap"><div class="tr-bar" style="width:${w}%"><span class="tr-inbar">${fmt1(s.turnout_pct)}%</span></div>${isNat ? '' : `<span class="tr-natline" style="left:${natMark}%"></span>`}</div>` +
      `<div class="tr-proj">${proj == null ? '—' : `${fmt1(proj)}<span class="tr-proj-u">%</span>`}</div></div>`;
  };
  wrap.innerHTML = row(nat, true) + sidos.map(s => row(s, false)).join('');
}

// ── 서울 자치구별 실시간 투표율 (25개 구) ──────────────────────────
function renderSeoulGu(cur) {
  const block = document.getElementById('seoul-gu-block');
  const wrap = document.getElementById('seoul-gu-table');
  if (!block || !wrap) return;
  const gus = ((cur && cur.turnout && cur.turnout.seoul_gu) || []).filter(g => g.turnout_pct != null);
  if (!gus.length) { block.hidden = true; return; }
  block.hidden = false;
  const tt = document.getElementById('seoul-gu-time');
  if (tt) tt.textContent = fmtKST(cur.polled_at) + ' (KST)';
  const seoul = ((cur.turnout.by_sido) || []).find(s => s.sd_name === '서울특별시');
  const avg = seoul && seoul.turnout_pct;          // 서울 평균(파선)
  const sorted = gus.slice().sort((a, b) => b.turnout_pct - a.turnout_pct);
  const maxPct = Math.max(...sorted.map(g => g.turnout_pct), avg || 0, 1);
  const avgMark = avg != null ? (avg / maxPct * 100).toFixed(1) : null;
  wrap.innerHTML = sorted.map((g, i) => {
    const w = (g.turnout_pct / maxPct * 100).toFixed(1);
    const aboveAvg = avg != null && g.turnout_pct >= avg;
    return `<div class="tr-row" title="투표 ${intComma(g.voters_so_far)} / 선거인 ${intComma(g.eligible_voters)}">` +
      `<div class="tr-name">${g.gu_name}</div>` +
      `<div class="tr-bar-wrap"><div class="tr-bar${aboveAvg ? ' sg-hi' : ''}" style="width:${w}%"><span class="tr-inbar">${fmt1(g.turnout_pct)}%</span></div>${avgMark != null ? `<span class="tr-natline" style="left:${avgMark}%"></span>` : ''}</div>` +
      `<div class="sg-rank">${i + 1}위</div></div>`;
  }).join('');
}

// ── 전국 시군구별 종합 투표율 (시도별 그룹) ─────────────────────────
function renderSigunguAll(cur) {
  const block = document.getElementById('sigungu-block');
  const root = document.getElementById('sigungu-groups');
  if (!block || !root) return;
  const bys = (cur && cur.turnout && cur.turnout.by_sigungu) || {};
  const names = Object.keys(bys).sort((a, b) => SIDO_ORDER.indexOf(a) - SIDO_ORDER.indexOf(b));
  if (!names.length) { block.hidden = true; return; }
  block.hidden = false;
  const nat = cur.turnout.national && cur.turnout.national.turnout_pct;  // 전국 평균(막대 색 기준)
  root.innerHTML = names.map(sd => {
    const g = bys[sd];
    const rows = (g.sigungu || []).filter(r => r.turnout_pct != null).slice()
      .sort((a, b) => b.turnout_pct - a.turnout_pct);
    if (!rows.length) return '';
    const barMax = Math.max(...rows.map(r => r.turnout_pct), nat || 0, 1);
    const t = g.total;
    const head = t && t.turnout_pct != null
      ? `합계 <strong>${fmt1(t.turnout_pct)}%</strong> · 투표 ${intComma(t.voters_so_far)}` : '';
    const list = rows.map(r => {
      const elig = r.eligible_voters || 0;
      const earlyPct = elig ? (r.early_voters_so_far || 0) / elig * 100 : 0;
      const dayPct = elig ? (r.day_voters_so_far || 0) / elig * 100 : 0;
      const ew = earlyPct / barMax * 100, dw = dayPct / barMax * 100;
      // 시도(evd)처럼 막대 안에 수치 라벨 — 칸이 좁으면(약 24px 미만) 생략
      const eLbl = ew >= 15 ? fmt1(earlyPct) : '';
      const dLbl = dw >= 15 ? fmt1(dayPct) : '';
      return `<div class="sgg-row" title="${r.name} · 사전 ${fmt1(earlyPct)}% + 당일 ${fmt1(dayPct)}% = ${fmt1(r.turnout_pct)}% · 투표 ${intComma(r.voters_so_far)} / 선거인 ${intComma(r.eligible_voters)}">` +
        `<span class="sgg-name">${r.name}</span>` +
        `<span class="sgg-bar-wrap"><span class="sgg-seg e" style="width:${ew.toFixed(1)}%">${eLbl}</span><span class="sgg-seg d" style="width:${dw.toFixed(1)}%">${dLbl}</span></span>` +
        `<span class="sgg-rate">${fmt1(r.turnout_pct)}%</span></div>`;
    }).join('');
    return `<div class="sgg-group"><div class="sgg-head"><span class="sgg-sido">${SIDO_SHORT[sd] || sd}</span><span class="sgg-total">${head}</span></div><div class="sgg-list">${list}</div></div>`;
  }).join('');
}

// ── 시간대별 투표율 추이 (오늘 vs 과거선거) ────────────────────────
function renderTurnoutTrend(cur, histHourly) {
  const block = document.getElementById('trend-block');
  const svg = document.getElementById('trend-svg');
  const legend = document.getElementById('trend-legend');
  if (!block || !svg) return;
  // 누계 투표율은 시간이 갈수록 단조 증가해야 한다. 정시 스냅샷이 중복·역전되면
  // 차트가 같은 값 두 번 찍히거나 아래로 꺾이므로, 시간순 + 엄격 증가만 남긴다.
  let today = (cur && cur.turnout && cur.turnout.hourly || [])
    .filter(h => h.turnout_pct != null)
    .slice()
    .sort((a, b) => (a.time < b.time ? -1 : a.time > b.time ? 1 : 0));
  let _mx = -1;
  today = today.filter(h => (h.turnout_pct > _mx + 0.01) ? ((_mx = h.turnout_pct), true) : false);
  // 정시점(HH:00) 외에 '현재 최신 누계'(박스값)를 끝점으로 추가 → 박스값보다 시간·값 모두 엄격히 클 때만
  const _natNow = cur && cur.turnout && cur.turnout.national;
  if (_natNow && _natNow.turnout_pct != null && typeof cur.polled_at === 'string' && cur.polled_at.length >= 16) {
    const _hhmm = cur.polled_at.slice(11, 16);
    const _last = today[today.length - 1];
    if (!_last || (_hhmm > _last.time && _natNow.turnout_pct > _last.turnout_pct + 0.15)) {
      today.push({ time: _hhmm, turnout_pct: _natNow.turnout_pct });
    }
  }
  const rounds = (histHourly && histHourly.rounds) || [];
  const r2022 = rounds.find(r => r.year === 2022);
  const r2018 = rounds.find(r => r.year === 2018);
  if (today.length < 1 || !r2022) { block.hidden = true; return; }
  block.hidden = false;
  const COLORS = { 2018: '#cbd5e1', 2022: '#9aa6b2', 2024: '#5b8def', 2025: '#e8a33d' };
  const TYPE = { '지방선거': '지선', '국회의원선거': '총선', '대통령선거': '대선' };
  const series = rounds.slice().sort((a, b) => a.year - b.year).map(r => ({
    label: `${r.year} ${TYPE[r.election_type] || ''}`.trim(),
    color: COLORS[r.year] || '#aaa',
    data: r.national || [],
    dash: r.election_type === '지방선거' ? '' : '5 3',
  }));
  series.push({ label: '2026 오늘', color: '#c41e3a', data: today, width: 2.8 });
  const t2x = t => { const [h, m] = t.split(':').map(Number); return (h * 60 + m) - 7 * 60; };
  const W = 640, H = 320, padL = 34, padR = 50, padT = 12, padB = 26;
  const xMax = Math.max(13 * 60, ...series.flatMap(s => s.data.map(d => t2x(d.time))));
  const yMax = Math.max(...series.flatMap(s => s.data.map(d => d.turnout_pct || 0)), 50) + 4;
  const px = x => padL + x / xMax * (W - padL - padR);
  const py = y => H - padB - (y / yMax) * (H - padT - padB);
  const g = [];
  for (let y = 0; y <= yMax; y += 10) {
    g.push(`<line x1="${padL}" y1="${py(y).toFixed(1)}" x2="${W - padR}" y2="${py(y).toFixed(1)}" stroke="#eee"/>`);
    g.push(`<text x="${padL - 4}" y="${(py(y) + 3).toFixed(1)}" font-size="9" fill="#999" text-anchor="end">${y}</text>`);
  }
  for (const t of ['07:00', '09:00', '11:00', '13:00', '15:00', '17:00', '19:00']) {
    const xx = t2x(t); if (xx > xMax) continue;
    g.push(`<text x="${px(xx).toFixed(1)}" y="${H - padB + 13}" font-size="9" fill="#999" text-anchor="middle">${t.slice(0, 5)}</text>`);
  }
  g.push(`<line x1="${px(t2x('13:00')).toFixed(1)}" y1="${padT}" x2="${px(t2x('13:00')).toFixed(1)}" y2="${H - padB}" stroke="#e3c4c4" stroke-dasharray="2 2"/>`);
  g.push(`<text x="${(px(t2x('13:00')) + 3).toFixed(1)}" y="${padT + 8}" font-size="8" fill="#b06">13시 사전투표 합산</text>`);
  for (const s of series) {
    const dd = s.data.filter(d => d.turnout_pct != null);
    if (!dd.length) continue;
    const path = dd.map((d, i) => (i === 0 ? 'M' : 'L') + px(t2x(d.time)).toFixed(1) + ',' + py(d.turnout_pct).toFixed(1)).join(' ');
    g.push(`<path d="${path}" fill="none" stroke="${s.color}" stroke-width="${s.width || 1.5}" ${s.dash ? `stroke-dasharray="${s.dash}"` : ''} stroke-linecap="round" stroke-linejoin="round"/>`);
    if (s.label.includes('오늘')) {
      // 오늘 선: 점마다 원, 라벨은 겹치지 않게. 오른쪽(현재값)부터 채우고 30px 이내면 생략
      // → 박스(현재) 점이 직전 정시 점과 가까워도 끝 숫자가 겹치지 않음.
      const showLabel = new Set();
      let keptX = Infinity;
      for (let i = dd.length - 1; i >= 0; i--) {
        const X = px(t2x(dd[i].time));
        if (i === dd.length - 1 || keptX - X >= 30) { showLabel.add(i); keptX = X; }
      }
      dd.forEach((d, i) => {
        const X = px(t2x(d.time)), Y = py(d.turnout_pct);
        g.push(`<circle cx="${X.toFixed(1)}" cy="${Y.toFixed(1)}" r="3" fill="${s.color}"/>`);
        if (showLabel.has(i))
          g.push(`<text x="${X.toFixed(1)}" y="${(Y - 7).toFixed(1)}" font-size="10.5" font-weight="800" fill="${s.color}" text-anchor="middle">${fmt1(d.turnout_pct)}</text>`);
      });
    } else {
      // 과거 선: 끝점(최종값) 라벨
      const last = dd[dd.length - 1];
      g.push(`<text x="${(px(t2x(last.time)) + 3).toFixed(1)}" y="${(py(last.turnout_pct) + 3).toFixed(1)}" font-size="9.5" font-weight="700" fill="${s.color}" text-anchor="start">${fmt1(last.turnout_pct)}</text>`);
    }
  }
  svg.innerHTML = g.join('');
  if (legend) legend.innerHTML = series.slice().reverse().map(s =>
    `<span class="tl-item"><span class="tl-dot" style="background:${s.color}"></span>${s.label}</span>`).join('');
}

// ── 시도별 누적 투표율 (사전 + 당일 스택) ──────────────────────────
function renderEarlyVsDay(cur, earlyVoting) {
  const block = document.getElementById('evd-block');
  const wrap = document.getElementById('evd-table');
  const note = document.getElementById('evd-note');
  if (!block || !wrap) return;
  // 라이브 집계 자체에 당일·사전 분리값이 있으므로 그대로 사용(외부 사전파일 불필요·일관).
  //   사전투표율 = 사전접수 / 선거인,  당일 본투표율 = 당일투표 / 선거인,  합 = 누계 투표율
  const rows = [];
  for (const s of (cur && cur.turnout && cur.turnout.by_sido || [])) {
    const eligible = s.eligible_voters || 0;
    if (!eligible) continue;
    const earlyPct = (s.early_voters_so_far || 0) / eligible * 100;
    const dayPct = (s.day_voters_so_far || 0) / eligible * 100;
    rows.push({ sd: s.sd_name, earlyPct, dayPct, total: earlyPct + dayPct });
  }
  if (rows.length < 3) { block.hidden = true; return; }
  block.hidden = false;
  rows.sort((a, b) => b.total - a.total);
  const maxTotal = Math.max(...rows.map(r => r.total), 1);
  // 전국 평균 누적(사전+당일) — 세로 파선 기준선
  const cN = cur && cur.turnout && cur.turnout.national;
  let natTotal = null;
  if (cN && cN.eligible_voters) {
    natTotal = ((cN.early_voters_so_far || 0) + (cN.day_voters_so_far || 0)) / cN.eligible_voters * 100;
  }
  const avgMark = (natTotal != null) ? (natTotal / maxTotal * 100).toFixed(1) : null;
  wrap.className = 'evd-table';
  wrap.innerHTML = rows.map(r => {
    const ew = r.earlyPct / maxTotal * 100, dw = r.dayPct / maxTotal * 100;
    const above = (natTotal != null && r.total >= natTotal);
    const cls = natTotal != null ? (above ? ' evd-above' : ' evd-below') : '';
    return `<div class="evd-row${cls}" title="${r.sd} · 사전 ${fmt1(r.earlyPct)}% + 당일 ${fmt1(r.dayPct)}% = ${fmt1(r.total)}%${natTotal != null ? ` · 전국평균 ${fmt1(natTotal)}% ${above ? '이상' : '이하'}` : ''}">` +
      `<div class="evd-name">${r.sd}</div>` +
      `<div class="evd-stack">` +
        `<span class="evd-seg e" style="width:${ew.toFixed(1)}%">${ew >= 9 ? fmt1(r.earlyPct) : ''}</span>` +
        `<span class="evd-seg d" style="width:${dw.toFixed(1)}%">${dw >= 9 ? fmt1(r.dayPct) : ''}</span>` +
        `${avgMark != null ? `<span class="evd-avgline" style="left:${avgMark}%"></span>` : ''}` +
      `</div>` +
      `<div class="evd-total">${fmt1(r.total)}%</div></div>`;
  }).join('');
  if (note) note.innerHTML =
    `<span class="tl-item"><span class="tl-dot" style="background:#2b6cb0"></span>사전투표</span>` +
    `<span class="tl-item"><span class="tl-dot" style="background:#c0392b"></span>당일 본투표</span>` +
    `<span class="tl-item"><span class="tl-dot tl-dash"></span>전국 평균${natTotal != null ? ` (${fmt1(natTotal)}%)` : ''}</span>` +
    `<span class="evd-legend-note">막대가 파선보다 길면 평균 이상</span>`;
}

// ── 투표율과 표심 (상관 산점도) ────────────────────────────────────
// 시도별 투표율(X) vs 시도지사 민주−국힘 격차(Y). 점=시도, 점선=추세, 피어슨 r.
function renderTurnoutCorr(cur) {
  const block = document.getElementById('corr-block');
  const svg = document.getElementById('corr-svg');
  const note = document.getElementById('corr-note');
  if (!block || !svg || !note) return;

  const tmap = {};
  for (const s of (cur?.turnout?.by_sido || [])) tmap[s.sd_name] = s.turnout_pct;
  const pts = [];
  for (const r of (cur?.races || [])) {
    if (String(r.sg_type_code) !== '3') continue;
    const dem = partyShare(r, DEM), con = partyShare(r, CON);
    const tn = tmap[r.sd_name];
    if (dem && con && tn != null) pts.push({ sd: r.sd_name, x: tn, y: dem.share - con.share });
  }
  if (pts.length < 3) { block.hidden = true; return; }
  block.hidden = false;

  const xs = pts.map(p => p.x), ys = pts.map(p => p.y);
  const stat = pearson(xs, ys);
  const xlo = Math.floor(Math.min(...xs) - 2), xhi = Math.ceil(Math.max(...xs) + 2);
  const ymax = Math.max(10, Math.ceil(Math.max(...ys.map(Math.abs)) / 5) * 5 + 5);
  const W = 640, H = 340, padL = 52, padR = 16, padT = 16, padB = 42;
  const px = x => padL + (x - xlo) / (xhi - xlo) * (W - padL - padR);
  const py = y => padT + (1 - (y + ymax) / (2 * ymax)) * (H - padT - padB);
  const clampY = y => Math.max(-ymax, Math.min(ymax, y));

  const g = [];
  g.push(`<line x1="${padL}" x2="${W - padR}" y1="${py(0).toFixed(1)}" y2="${py(0).toFixed(1)}" stroke="#bbb" stroke-width="1"/>`);
  [ymax, ymax / 2, -ymax / 2, -ymax].forEach(yv => {
    g.push(`<text x="${padL - 7}" y="${(py(yv) + 4).toFixed(1)}" font-size="10" fill="#999" text-anchor="end">${yv > 0 ? '민주+' + yv : '국힘+' + (-yv)}</text>`);
  });
  g.push(`<text x="${padL - 7}" y="${(py(0) + 4).toFixed(1)}" font-size="10" fill="#999" text-anchor="end">0</text>`);
  const step = Math.max(2, Math.round((xhi - xlo) / 6));
  for (let xv = xlo; xv <= xhi; xv += step) {
    g.push(`<line x1="${px(xv).toFixed(1)}" x2="${px(xv).toFixed(1)}" y1="${padT}" y2="${H - padB}" stroke="#f2f2f2"/>`);
    g.push(`<text x="${px(xv).toFixed(1)}" y="${H - padB + 15}" font-size="10" fill="#999" text-anchor="middle">${xv}%</text>`);
  }
  g.push(`<text x="${((padL + W - padR) / 2).toFixed(0)}" y="${H - 7}" font-size="10.5" fill="#777" text-anchor="middle">시도 투표율 →</text>`);

  if (stat) {
    const y1 = stat.slope * xlo + stat.intercept, y2 = stat.slope * xhi + stat.intercept;
    g.push(`<line x1="${px(xlo).toFixed(1)}" y1="${py(clampY(y1)).toFixed(1)}" x2="${px(xhi).toFixed(1)}" y2="${py(clampY(y2)).toFixed(1)}" stroke="#c41e3a" stroke-width="1.6" stroke-dasharray="5 4"/>`);
  }
  for (const p of pts) {
    const color = p.y >= 0 ? 'var(--dem)' : 'var(--con)';
    g.push(`<circle cx="${px(p.x).toFixed(1)}" cy="${py(clampY(p.y)).toFixed(1)}" r="4.5" fill="${color}"><title>${p.sd} 투표율 ${fmt1(p.x)}% · ${marginText(p.y)}</title></circle>`);
    g.push(`<text x="${px(p.x).toFixed(1)}" y="${(py(clampY(p.y)) - 8).toFixed(1)}" font-size="9.5" fill="#555" text-anchor="middle">${SIDO_SHORT[p.sd] || p.sd}</text>`);
  }
  svg.innerHTML = g.join('');

  let interp;
  if (!stat) interp = '상관 계산 불가';
  else if (stat.r > 0.3) interp = `투표율이 높은 시도일수록 <b>민주 우세</b> 경향 (상관 r=${stat.r.toFixed(2)}, n=${stat.n})`;
  else if (stat.r < -0.3) interp = `투표율이 높은 시도일수록 <b>국힘 우세</b> 경향 (상관 r=${stat.r.toFixed(2)}, n=${stat.n})`;
  else interp = `투표율과 우세 정당 사이 <b>뚜렷한 상관 없음</b> (r=${stat.r.toFixed(2)}, n=${stat.n})`;
  note.innerHTML = `${interp}.<br><span class="corr-warn">⚠️ 지역 고유 성향(호남↑민주·영남↑국힘)이 섞여 있어 '투표율→표심' 인과로 단정할 수 없습니다.</span> 같은 지역의 예측 대비 초과분 분석은 별도.`;
}

// ── 주목 후보 워치리스트 ────────────────────────────────────────────
function findWatch(races, w) {
  for (const r of races) {
    if (w.sido && r.sd_name !== w.sido) continue;
    if (w.where) {
      const place = [r.sd_name, r.sgg_name, r.wiw_name].filter(Boolean).join(' ');
      if (!place.includes(w.where)) continue;
    }
    const c = (r.candidates || []).find(c => c.name === w.name);
    if (c) return { race: r, cand: c };
  }
  return null;
}

function watchStatus(race, cand) {
  const prog = race.progress_pct || 0;
  const cands = race.candidates || [];
  const rank = cand.current_rank;
  if (rank === 1) {
    const lead = (cand.share_pct ?? 0) - (cands[1]?.share_pct ?? 0);
    if (prog >= 80 && lead >= 5) return { cls: 'wc-win', label: '당선 유력' };
    if (prog < 30) return { cls: 'wc-lead', label: '1위 (개표 초반)' };
    return { cls: 'wc-lead', label: lead < 3 ? '1위 (접전)' : '1위' };
  }
  const behind = (cands[0]?.share_pct ?? 0) - (cand.share_pct ?? 0);
  if (behind < 5) return { cls: 'wc-close', label: `${rank}위 (접전 추격)` };
  return { cls: 'wc-behind', label: `${rank}위 열세` };
}

function renderWatchlist(watchlist) {
  const block = document.getElementById('watch-block');
  const root = document.getElementById('watchlist');
  if (!root || !block) return;
  const list = (watchlist && watchlist.candidates) || [];
  if (!list.length) { block.hidden = true; return; }
  block.hidden = false;

  root.innerHTML = list.map(w => {
    const m = findWatch(LATEST_RACES, w);
    const where = [w.sido, w.label].filter(Boolean).join(' · ');
    if (!m) {
      return `<div class="watch-card">
        <div class="watch-head"><span class="watch-name">${w.name}</span></div>
        <div class="watch-where">${where}</div>
        <div class="watch-figure"><span class="watch-meta">개표 데이터 대기 — 18시 마감 후 표시</span></div>
        <span class="watch-chip wc-wait">대기</span>
      </div>`;
    }
    const { race, cand } = m;
    const st = watchStatus(race, cand);
    const color = partyColor(LATEST_PARTIES, cand.jd_name);
    return `<div class="watch-card">
      <div class="watch-head">
        <span class="watch-name">${cand.name}<span class="watch-party">${cand.jd_name || ''}</span></span>
        <span class="watch-rank">개표 ${fmt1(race.progress_pct)}%</span>
      </div>
      <div class="watch-where">${race.sg_type_label} · ${racePlace(race)}</div>
      <div class="watch-figure">
        <span class="watch-share" style="color:${color}">${fmt1(cand.share_pct)}<span style="font-size:0.5em">%</span></span>
        <span class="watch-rank">${cand.current_rank}위 / ${(race.candidates || []).length}명</span>
      </div>
      <span class="watch-chip ${st.cls}">${st.label}</span>
    </div>`;
  }).join('');
}

// ── 관심 지역 그룹 ──────────────────────────────────────────────────
// 텃밭(전통 강세 지역) — '이변' 판정용. 호남=민주 / 영남=보수.
const DEM_STRONGHOLD = new Set(['광주광역시', '전라남도', '전북특별자치도', '전남광주통합특별시']);
const CON_STRONGHOLD = new Set(['대구광역시', '경상북도', '경상남도', '부산광역시', '울산광역시']);

// 이변 = 지난 선거(8회) 당선 정당과 현재 1위 정당이 다른 경우(정당 교체).
//   지난 당선 정당 미상(선거구 재획정 등)이면 텃밭 휴리스틱(호남=비민주·영남=비국힘)으로 보완.
//   무당적 선거(교육감 등)·개표 20% 미만은 제외.
function upsetKey(r) {
  const t = String(r.sg_type_code);
  return t === '3' ? `3|${r.sd_name}` : `${t}|${r.sd_name}|${r.sgg_name || ''}`;
}
function isUpset(r) {
  const leader = (r.candidates || [])[0];
  if (!leader || !leader.jd_name || (r.progress_pct || 0) < 20) return false;
  const prev = LATEST_PREVWIN[upsetKey(r)];
  if (prev) return leader.jd_name !== prev;
  if (DEM_STRONGHOLD.has(r.sd_name) && leader.jd_name !== DEM) return true;
  if (CON_STRONGHOLD.has(r.sd_name) && leader.jd_name !== CON) return true;
  return false;
}

function matcherHit(r, m) {
  if (m.type && String(r.sg_type_code) !== m.type) return false;
  if (m.sido && r.sd_name !== m.sido) return false;
  if (m.where) {
    const place = [r.sd_name, r.sgg_name, r.wiw_name].filter(Boolean).join(' ');
    if (!place.includes(m.where)) return false;
  }
  if (m.party && !(r.candidates || []).some(c => c.jd_name === m.party)) return false;
  if (m.name && !(r.candidates || []).some(c => c.name === m.name)) return false;
  if (m.closeRace != null && !(r.rank1_minus_rank2_pp != null && r.rank1_minus_rank2_pp <= m.closeRace)) return false;
  if (m.prevClose != null) {
    const pr = LATEST_PREVRESULT[upsetKey(r)];
    if (!(pr && pr.lead != null && pr.lead <= m.prevClose)) return false;
  }
  if (m.upset && !isUpset(r)) return false;
  return true;
}

function renderGroups(groupsData) {
  const block = document.getElementById('groups-block');
  const root = document.getElementById('groups');
  if (!root || !block) return;
  const groups = (groupsData && groupsData.groups) || [];
  if (!groups.length) { block.hidden = true; return; }
  block.hidden = false;

  root.innerHTML = groups.map(g => {
    const seen = new Set();
    const matched = [];
    for (const r of LATEST_RACES) {
      if ((g.matchers || []).some(m => matcherHit(r, m)) && !seen.has(r.race_key)) {
        seen.add(r.race_key); matched.push(r);
      }
    }
    matched.sort((a, b) =>
      (TYPE_ORDER.indexOf(String(a.sg_type_code)) - TYPE_ORDER.indexOf(String(b.sg_type_code))) ||
      ((a.rank1_minus_rank2_pp ?? 999) - (b.rank1_minus_rank2_pp ?? 999)));

    const body = matched.length
      ? raceTable(matched.slice(0, 100).map(raceTableRow).join(''))
      : `<div class="state-empty" style="padding:18px 0">아직 매칭된 개표 데이터가 없습니다 (마감 후 표시).</div>`;

    return `<div class="group-box">
      <div class="group-head">
        <span class="group-title">${g.title}</span>
        <span class="group-desc">${g.desc || ''}</span>
        <span class="group-count">${matched.length}곳</span>
      </div>
      ${body}
    </div>`;
  }).join('');
}

// ── 시도지사 예측 vs 실제 ──────────────────────────────────────────
function partyShare(race, party) {
  const c = (race.candidates || []).find(c => c.jd_name === party);
  return c ? { share: c.share_pct, name: c.name } : null;
}

function classifyRace(race, demProb) {
  const dem = partyShare(race, DEM);
  const con = partyShare(race, CON);
  const prog = race.progress_pct || 0;
  const actualMargin = (dem && con) ? (dem.share - con.share) : null;

  if (prog < 5) return { verdict: 'early', label: '개표 초반', actualMargin, demProb };
  if (demProb == null) return { verdict: 'none', label: '예측 없음', actualMargin, demProb };
  if (actualMargin == null) return { verdict: 'none', label: '양자 비교 불가', actualMargin, demProb };

  const predDem = demProb >= 50;
  const actualDem = actualMargin > 0;
  const confident = demProb >= 80 || demProb <= 20;
  const tossup = demProb > 35 && demProb < 65;

  if (predDem !== actualDem) return { verdict: 'upset', label: '이변 — 예측과 반대', actualMargin, demProb };
  if (tossup) return { verdict: 'band', label: '접전 예측 적중', actualMargin, demProb };
  if (confident) return { verdict: 'hit', label: '예측 적중', actualMargin, demProb };
  return { verdict: 'hit', label: '예측 부합', actualMargin, demProb };
}

function predText(demProb) {
  if (demProb == null) return '—';
  return demProb >= 50 ? `민주 ${Math.round(demProb)}%` : `국힘 ${Math.round(100 - demProb)}%`;
}

function candRowHTML(parties, c, isLead, race) {
  const color = partyColor(parties, c.jd_name);
  const w = Math.max(0, Math.min(100, c.share_pct || 0));
  return `<div class="cand-row ${isLead ? 'cand-rank1' : ''}">
    ${race ? candPhotoImg(race, c, 'cand-photo') : ''}
    <span class="cand-dot" style="background:${color}"></span>
    <span class="cand-name">${c.name || '—'}</span>
    <span class="cand-party">${c.jd_name || ''}</span>
    <span class="cand-bar-wrap"><span class="cand-bar" style="width:${w}%;background:${color}"></span></span>
    <span class="cand-share">${fmt1(c.share_pct)}%</span>
  </div>`;
}

// ── 출구조사 (지상파 3사 공동) — 개표 시작 직후 표시 ────────────────
function renderExitPoll(exitPoll) {
  const block = document.getElementById('exitpoll-block');
  const root = document.getElementById('exitpoll-grid');
  const asmRoot = document.getElementById('exitpoll-asm');
  if (!block || !root) return;
  const gov = (exitPoll && exitPoll.governor) || [];
  if (!gov.length) { block.hidden = true; return; }
  block.hidden = false;
  const sub = document.getElementById('exitpoll-sub');
  if (sub) sub.textContent = `${exitPoll.source || '출구조사'} · ${exitPoll.note || ''}`;
  const card = (race) => {
    const cands = (race.candidates || []).slice().sort((a, b) => b.pct - a.pct);
    if (!cands.length) return '';
    const margin = cands.length > 1 ? (cands[0].pct - cands[1].pct) : null;
    const tag = margin == null ? ''
      : (margin < 3 ? `<span class="ep-tag close">경합 ${fmt1(margin)}%p</span>`
        : `<span class="ep-tag">${esc(cands[0].party || '무소속')} 우세</span>`);
    const rows = cands.map((c, i) => {
      const color = partyColor(LATEST_PARTIES, c.party);
      const w = Math.max(0, Math.min(100, c.pct));
      return `<div class="ep-cand${i === 0 ? ' ep-lead' : ''}">` +
        `<span class="ep-dot" style="background:${color}"></span>` +
        `<span class="ep-name">${esc(c.name)}</span>` +
        `<span class="ep-party" style="color:${color}">${esc(c.party || '무소속')}</span>` +
        `<span class="ep-bar-wrap"><span class="ep-bar" style="width:${w}%;background:${color}"></span></span>` +
        `<span class="ep-pct">${fmt1(c.pct)}<small>%</small></span></div>`;
    }).join('');
    return `<div class="ep-card"><div class="ep-head"><b>${esc(race.label || race.region)}</b>${tag}</div>${rows}</div>`;
  };
  root.innerHTML = gov.map(card).join('');
  if (asmRoot) {
    const asm = (exitPoll.assembly) || [];
    asmRoot.innerHTML = asm.map(r => card({ label: r.region, candidates: r.candidates })).join('');
  }
}

function marginText(m) {
  if (m == null) return '—';
  const who = m > 0 ? '민주' : '국힘';
  return `${who} +${Math.abs(m).toFixed(1)}pp`;
}

function renderChiefRaces(cur, predMap, parties) {
  const root = document.getElementById('chief-races');
  const chiefs = (cur?.races || []).filter(r => String(r.sg_type_code) === '3');
  if (!chiefs.length) {
    root.innerHTML = `<div class="state-empty">시도지사 개표 데이터가 아직 없습니다. 18시 마감 후 표시됩니다.</div>`;
    return;
  }
  chiefs.sort((a, b) => (a.rank1_minus_rank2_pp ?? 99) - (b.rank1_minus_rank2_pp ?? 99));

  root.innerHTML = chiefs.map(race => {
    const demProb = (predMap[race.sd_name] != null) ? predMap[race.sd_name] : null;
    const cls = classifyRace(race, demProb);
    const cands = (race.candidates || []).slice(0, 2);
    const candHTML = cands.map((c, i) => candRowHTML(parties, c, i === 0, race)).join('');

    let compareHTML = '';
    if (cls.actualMargin != null) {
      const predPart = (demProb != null)
        ? `<span class="rc-item">뉴탐사 예측 <b>${predText(demProb)}</b> 당선확률</span>`
        : `<span class="rc-item">예측 <b>—</b></span>`;
      compareHTML = `
        <span class="rc-item">실제 <b>${marginText(cls.actualMargin)}</b></span>
        ${predPart}
        <span class="rc-verdict v-${cls.verdict}">${cls.label}</span>`;
    } else {
      compareHTML = `<span class="rc-item">개표 진행 ${fmt1(race.progress_pct)}%</span>
        <span class="rc-verdict v-${cls.verdict}">${cls.label}</span>`;
    }

    return `<div class="race-card">
      <div class="race-card-head">
        <span class="race-sido">${race.sd_name}</span>
        <span class="race-progress">개표 <b>${fmt1(race.progress_pct)}%</b></span>
      </div>
      ${candHTML}
      <div class="race-compare">${compareHTML}</div>
    </div>`;
  }).join('');
}

// ── 기초단체장 226 — 예측 vs 실제 ──────────────────────────────────
function renderBasicHead(cur, predBH) {
  const root = document.getElementById('bh-compare');
  if (!root) return;
  const prob = (predBH && predBH.basic_head_dem_win_prob) || {};
  const sm = (predBH && predBH.summary) || {};
  const races = (cur?.races || []).filter(r => String(r.sg_type_code) === '4');
  const counted = races.filter(r => (r.progress_pct || 0) > 0 && (r.candidates || []).length);
  if (!counted.length) {
    root.innerHTML = `<div class="state-empty">기초단체장 개표 데이터가 아직 없습니다. 18시 마감 후 표시됩니다.</div>`;
    return;
  }
  let dem = 0, con = 0, etc = 0, matched = 0, withPred = 0;
  const upsets = [];
  for (const r of counted) {
    const lead = (r.candidates || [])[0]; if (!lead) continue;
    const p = lead.jd_name;
    if (p === DEM) dem++; else if (p === CON) con++; else etc++;
    const pr = prob[`4|${r.sd_name}|${r.sgg_name || ''}`];
    if (pr != null && (r.progress_pct || 0) >= 20) {
      const predDem = pr >= 50, actualDem = p === DEM;
      withPred++;
      if (predDem === actualDem) matched++; else upsets.push(r);
    }
  }
  const ci = sm.dem_80_ci || [];
  const predLine = (sm.dem_mode != null)
    ? `<b style="color:var(--dem)">민주 ${sm.dem_mode}곳</b> · 그외 ${sm.con_mode}곳 <span class="bh-sub">(민주 예상범위 ${ci[0]}~${ci[1]}곳)</span>`
    : '—';
  const acc = withPred ? Math.round(matched / withPred * 100) : null;
  const verdict = acc != null ? `예측 방향 적중 ${matched}/${withPred}곳 (${acc}%)` : '개표 20%+ 선거구부터 적중 집계';
  root.innerHTML = `
    <div class="bh-grid">
      <div class="bh-card" style="border-left:4px solid var(--dem)">
        <div class="bh-label">뉴탐사 예측 (시뮬)</div>
        <div class="bh-figure">${predLine}</div>
      </div>
      <div class="bh-card" style="border-left:4px solid #777">
        <div class="bh-label">실제 개표 집계 (${counted.length}/226곳 개표중)</div>
        <div class="bh-figure"><b style="color:var(--dem)">민주 ${dem}</b> · <b style="color:var(--con)">국힘 ${con}</b> · 그외 ${etc}</div>
        <div class="bh-sub">${verdict}</div>
      </div>
    </div>
    ${upsets.length ? `<div class="bh-upset-h">예측과 다른 곳 — 예측 우세 진영이 실제로 뒤집힌 기초단체장 ${upsets.length}곳</div>${raceTable(upsets.slice(0, 40).map(raceTableRow).join(''))}` : ''}`;
}

// ── 전체 선거구 검색·필터 ──────────────────────────────────────────
function populateFilters(races) {
  if (filtersPopulated) return;
  const typeSel = document.getElementById('f-type');
  const sidoSel = document.getElementById('f-sido');
  const partySel = document.getElementById('f-party');

  const typeLabels = {};
  for (const r of races) typeLabels[String(r.sg_type_code)] = r.sg_type_label;
  Object.keys(typeLabels)
    .sort((a, b) => TYPE_ORDER.indexOf(a) - TYPE_ORDER.indexOf(b))
    .forEach(t => typeSel.add(new Option(typeLabels[t], t)));

  [...new Set(races.map(r => r.sd_name).filter(Boolean))]
    .sort((a, b) => SIDO_ORDER.indexOf(a) - SIDO_ORDER.indexOf(b))
    .forEach(s => sidoSel.add(new Option(s, s)));

  const partySet = new Set();
  for (const r of races) for (const c of (r.candidates || [])) if (c.jd_name) partySet.add(c.jd_name);
  [...partySet].sort((a, b) => a.localeCompare(b, 'ko')).forEach(p => partySel.add(new Option(p, p)));

  filtersPopulated = true;
}

function currentFilters() {
  return {
    type: document.getElementById('f-type').value,
    sido: document.getElementById('f-sido').value,
    party: document.getElementById('f-party').value,
    q: (document.getElementById('f-q').value || '').trim().toLowerCase(),
  };
}

function raceMatches(r, f) {
  if (f.type && String(r.sg_type_code) !== f.type) return false;
  if (f.sido && r.sd_name !== f.sido) return false;
  if (f.party && !(r.candidates || []).some(c => c.jd_name === f.party)) return false;
  if (f.q) {
    const hay = [r.sd_name, r.sgg_name, r.wiw_name, r.sg_type_label,
      ...(r.candidates || []).map(c => c.name), ...(r.candidates || []).map(c => c.jd_name)]
      .filter(Boolean).join(' ').toLowerCase();
    if (!hay.includes(f.q)) return false;
  }
  return true;
}

const RESULT_CAP = 300;

function renderSearch() {
  const root = document.getElementById('search-results');
  const countEl = document.getElementById('f-count');
  if (!root) return;
  const f = currentFilters();
  const matched = LATEST_RACES.filter(r => raceMatches(r, f));
  countEl.textContent = `${matched.length.toLocaleString('ko-KR')}개 선거구`;

  if (!matched.length) {
    root.innerHTML = `<div class="state-empty">조건에 맞는 선거구가 없습니다. 필터를 바꿔 보세요.</div>`;
    return;
  }
  matched.sort((a, b) => (a.rank1_minus_rank2_pp ?? 999) - (b.rank1_minus_rank2_pp ?? 999));
  const shown = matched.slice(0, RESULT_CAP);

  const capNote = matched.length > RESULT_CAP
    ? `<div class="state-empty" style="padding:14px 0">접전 순 상위 ${RESULT_CAP}개만 표시 중 — 필터로 좁혀 주세요.</div>` : '';

  root.innerHTML = raceTable(shown.map(raceTableRow).join('')) + capNote;
}

function bindFilters() {
  if (filtersBound) return;
  ['f-type', 'f-sido', 'f-party'].forEach(id => {
    document.getElementById(id).addEventListener('change', renderSearch);
  });
  let t = null;
  document.getElementById('f-q').addEventListener('input', () => {
    clearTimeout(t);
    t = setTimeout(renderSearch, 180);
  });
  filtersBound = true;
}

// 개표일 이전엔 보관용/테스트 데이터가 실제 결과처럼 보이지 않도록 대기 화면.
function showWaiting(msg) {
  document.getElementById('live-badge').hidden = true;
  document.getElementById('hero-turnout').innerHTML = `대기<span class="pct"></span>`;
  document.getElementById('hero-turnout-meta').textContent = msg;
  document.getElementById('hero-progress').innerHTML = `—<span class="pct"></span>`;
  document.getElementById('hero-progress-meta').textContent = '투표 마감(18시) 후 개표 시작';
  document.getElementById('hero-early').innerHTML = `—<span class="pct"></span>`;
  const wb = document.getElementById('watch-block'); if (wb) wb.hidden = true;
  const gb = document.getElementById('groups-block'); if (gb) gb.hidden = true;
  const cb = document.getElementById('corr-block'); if (cb) cb.hidden = true;
  document.getElementById('chief-races').innerHTML = `<div class="state-empty">${msg}</div>`;
  const bh = document.getElementById('bh-compare'); if (bh) bh.innerHTML = `<div class="state-empty">${msg}</div>`;
  document.getElementById('search-results').innerHTML = '';
  document.getElementById('updated-at').textContent = '—';
}

// ── main ──────────────────────────────────────────────────────────
async function render() {
  const preview = location.search.includes('preview');
  const COUNT_START = Date.parse('2026-06-03T18:00:00+09:00');
  const beforeCount = !preview && Date.now() < COUNT_START;
  // 투표 중엔 '실시간 투표율', 마감(18시) 후엔 '실시간 개표'로 타이틀 전환
  var _tt = document.getElementById('page-title-text');
  var _ts = document.getElementById('page-sub');
  if (_tt) _tt.textContent = beforeCount ? '실시간 투표율' : '실시간 개표';
  // 히어로 가운데 카드: 투표 중엔 '4년 전 동시각', 18시 후엔 '개표 진행률' (항상 3칸).
  const _pc = document.getElementById('hero-progress-card');
  if (_pc) _pc.hidden = beforeCount;
  const _cc = document.getElementById('hero-cmp-card');
  if (_cc) _cc.hidden = !beforeCount;
  // 투표 중엔 개표 전용 섹션(시도지사·기초단체장·검색) 통째 숨김 → 18시부터 노출
  ['chief-block', 'bh-block', 'search-block'].forEach(id => {
    const s = document.getElementById(id);
    if (s) s.hidden = beforeCount;
  });
  if (_ts) _ts.textContent = beforeCount
    ? '2026-06-03(수) 투표 진행 중 · 시도별 투표율 자동 갱신 · 18시 마감 후 개표로 전환'
    : '2026-06-03(수) 개표 진행 · 자동 갱신 · 뉴탐사 자체 시뮬레이션 예측과 비교';
  const [cur, watchlist, groups, prevWinner, prevResult, prediction, predBasicHead, parties, earlyVoting, histHourly, exitPoll] = await Promise.all([
    loadJSON(PATHS.current), loadJSON(PATHS.watchlist), loadJSON(PATHS.groups),
    loadJSON(PATHS.prevWinner), loadJSON(PATHS.prevResult), loadJSON(PATHS.prediction), loadJSON(PATHS.predBasicHead), loadJSON(PATHS.parties),
    loadJSON(PATHS.earlyVoting), loadJSON(PATHS.histHourly), loadJSON(PATHS.exitPoll),
  ]);
  LATEST_PARTIES = parties || LATEST_PARTIES;
  renderExitPoll(exitPoll);
  // 투표 시간대(개표 전): 실제 투표율이 있으면 투표율만 표시, 개표 섹션은 대기.
  if (beforeCount) {
    const nat = cur && cur.turnout && cur.turnout.national;
    if (nat && nat.turnout_pct != null) {
      renderHero(cur, earlyVoting);
      renderProjection(cur, histHourly);
      renderCompare2022(cur, histHourly);
      renderTurnoutTrend(cur, histHourly);
      renderEarlyVsDay(cur, earlyVoting);
      renderSigunguAll(cur);
      renderHistoryCompare(cur, histHourly);
      renderTurnoutCorr(cur);
      const wb = document.getElementById('watch-block'); if (wb) wb.hidden = true;
      const gb = document.getElementById('groups-block'); if (gb) gb.hidden = true;
      const w = '투표 진행 중 — 개표는 18시 투표 마감 후 시작됩니다.';
      document.getElementById('chief-races').innerHTML = `<div class="state-empty">${w}</div>`;
      const bh = document.getElementById('bh-compare'); if (bh) bh.innerHTML = `<div class="state-empty">${w}</div>`;
      document.getElementById('search-results').innerHTML = '';
    } else {
      showWaiting('개표는 6월 3일(수) 18시 투표 마감 후 시작됩니다. 마감 후 자동으로 결과가 표시됩니다.');
    }
    return;
  }
  if (!cur) {
    document.getElementById('chief-races').innerHTML =
      `<div class="state-empty">개표 데이터가 아직 없습니다. 6/3 18시 투표 마감 후 수집이 시작됩니다.</div>`;
    const bh0 = document.getElementById('bh-compare');
    if (bh0) bh0.innerHTML = `<div class="state-empty">기초단체장 개표 데이터가 아직 없습니다. 18시 마감 후 표시됩니다.</div>`;
    document.getElementById('search-results').innerHTML = '';
    return;
  }
  const predMap = (prediction && prediction.sido_dem_win_prob) || {};
  LATEST_RACES = cur.races || [];
  LATEST_PARTIES = parties || {};
  LATEST_PREVWIN = (prevWinner && prevWinner.winner_party) || {};
  LATEST_PREVRESULT = (prevResult && prevResult.results) || {};

  // 개표 후보 사진맵 1회 로드(없어도 이니셜로 폴백). 개표 렌더 전에 확보.
  if ((cur.races || []).length) { await ensurePhotos(); }

  renderHero(cur, earlyVoting);
  renderProjection(cur, histHourly);
  renderTurnoutTrend(cur, histHourly);
  renderEarlyVsDay(cur, earlyVoting);
  renderSigunguAll(cur);
  renderHistoryCompare(cur, histHourly);
  renderWatchlist(watchlist);
  renderGroups(groups);
  renderChiefRaces(cur, predMap, LATEST_PARTIES);
  renderBasicHead(cur, predBasicHead);
  renderTurnoutCorr(cur);
  populateFilters(LATEST_RACES);
  bindFilters();
  bindRaceExpand();
  renderSearch();
}

render();
setInterval(render, REFRESH_MS);
