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
  const lead = c1 ? `${dot}<b>${c1.name}</b> <span class="cand-party">${c1.jd_name || ''}</span> ${fmt1(c1.share_pct)}%` : '—';
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
function renderHero(cur) {
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

  const e = document.getElementById('hero-early');
  if (nat?.early_share_of_total_pct != null) {
    e.innerHTML = `${fmt1(nat.early_share_of_total_pct)}<span class="pct">%</span>`;
    document.getElementById('hero-early-meta').textContent =
      `사전 ${intComma(nat.early_voters_so_far)} · 당일 ${intComma(nat.day_voters_so_far)}`;
  }

  document.getElementById('updated-at').textContent = fmtKST(cur?.polled_at) + ' (KST)';
}

// ── 시도별 실시간 투표율 표 ────────────────────────────────────────
function renderTurnoutTable(cur) {
  const block = document.getElementById('turnout-block');
  const wrap = document.getElementById('turnout-table');
  if (!block || !wrap) return;
  const nat = cur && cur.turnout && cur.turnout.national;
  if (!nat || nat.turnout_pct == null) { block.hidden = true; return; }
  block.hidden = false;
  const tt = document.getElementById('turnout-time');
  if (tt) tt.textContent = fmtKST(cur.polled_at) + ' (KST)';
  const sidos = (cur.turnout.by_sido || []).slice().sort((a, b) => (b.turnout_pct || 0) - (a.turnout_pct || 0));
  const maxPct = Math.max(nat.turnout_pct || 0, ...sidos.map(s => s.turnout_pct || 0), 1);
  const row = (s, isNat) =>
    `<div class="tr-row${isNat ? ' tr-nat' : ''}" title="투표 ${intComma(s.voters_so_far)} / 선거인 ${intComma(s.eligible_voters)}">` +
    `<div class="tr-name">${s.sd_name}</div>` +
    `<div class="tr-bar-wrap"><div class="tr-bar" style="width:${((s.turnout_pct || 0) / maxPct * 100).toFixed(1)}%"></div></div>` +
    `<div class="tr-pct">${fmt1(s.turnout_pct)}%</div></div>`;
  wrap.innerHTML = row(nat, true) + sidos.map(s => row(s, false)).join('');
}

// ── 사전 vs 본투표 (진보·보수 가설) ────────────────────────────────
function renderEarlyVsDay(cur, earlyVoting) {
  const block = document.getElementById('evd-block');
  const wrap = document.getElementById('evd-table');
  const note = document.getElementById('evd-note');
  if (!block || !wrap) return;
  const evSido = {};
  for (const s of (earlyVoting && earlyVoting.by_sido || [])) evSido[s.sdName] = s;
  const curSido = {};
  for (const s of (cur && cur.turnout && cur.turnout.by_sido || [])) curSido[s.sd_name] = s;
  const marginSido = {};
  for (const r of (cur && cur.races || [])) {
    if (String(r.sg_type_code) !== '3') continue;
    const dem = partyShare(r, DEM), con = partyShare(r, CON);
    if (dem && con) marginSido[r.sd_name] = dem.share - con.share;
  }
  const rows = [];
  for (const sd of Object.keys(evSido)) {
    const ev = evSido[sd], cu = curSido[sd];
    const eligible = ev.voters || (cu && cu.eligible_voters) || 0;
    const dayVoted = (cu && cu.day_voters_so_far) || 0;
    const dayPct = eligible ? dayVoted / eligible * 100 : null;
    const earlyShare = (ev.voted + dayVoted) ? ev.voted / (ev.voted + dayVoted) * 100 : null;
    rows.push({ sd, earlyPct: ev.turnout, dayPct, earlyShare, margin: marginSido[sd] });
  }
  if (rows.length < 3) { block.hidden = true; return; }
  block.hidden = false;
  rows.sort((a, b) => (b.earlyShare || 0) - (a.earlyShare || 0));
  const maxE = Math.max(...rows.map(r => r.earlyPct || 0), 1);
  const maxD = Math.max(...rows.map(r => r.dayPct || 0), 1);
  const hasCount = rows.some(r => r.margin != null);
  const head = `<div class="evd-row evd-head"><div>시도</div><div>사전투표율</div><div>당일 본투표율</div><div class="evd-share">사전비중</div>${hasCount ? '<div class="evd-share">민주격차</div>' : ''}</div>`;
  const body = rows.map(r => {
    const mc = hasCount
      ? `<div class="evd-share ${r.margin > 0 ? 'm-dem' : r.margin < 0 ? 'm-con' : ''}">${r.margin == null ? '—' : (r.margin > 0 ? '민주+' : '국힘+') + fmt1(Math.abs(r.margin))}</div>`
      : '';
    return `<div class="evd-row"><div class="evd-name">${r.sd}</div>` +
      `<div class="evd-cell"><span class="evd-bar e" style="width:${(r.earlyPct / maxE * 100).toFixed(0)}%"></span><span class="evd-num">${fmt1(r.earlyPct)}%</span></div>` +
      `<div class="evd-cell"><span class="evd-bar d" style="width:${r.dayPct == null ? 0 : (r.dayPct / maxD * 100).toFixed(0)}%"></span><span class="evd-num">${r.dayPct == null ? '—' : fmt1(r.dayPct) + '%'}</span></div>` +
      `<div class="evd-share">${r.earlyShare == null ? '—' : fmt1(r.earlyShare) + '%'}</div>${mc}</div>`;
  }).join('');
  wrap.className = 'evd-table' + (hasCount ? ' has-count' : '');
  wrap.innerHTML = head + body;
  if (!note) return;
  if (hasCount) {
    const pts = rows.filter(r => r.earlyShare != null && r.margin != null);
    if (pts.length >= 3) {
      const st = pearson(pts.map(p => p.earlyShare), pts.map(p => p.margin));
      let v;
      if (st.r > 0.3) v = `사전투표 비중이 높은 시도일수록 <b>민주 우세</b> 경향 (r=${st.r.toFixed(2)}, n=${st.n}) — <b>가설과 부합</b>`;
      else if (st.r < -0.3) v = `사전투표 비중이 높은 시도일수록 <b>국힘 우세</b> 경향 (r=${st.r.toFixed(2)}, n=${st.n}) — <b>가설과 반대</b>`;
      else v = `사전비중과 우세 정당 사이 <b>뚜렷한 상관 없음</b> (r=${st.r.toFixed(2)}, n=${st.n})`;
      note.innerHTML = `📊 <b>개표로 본 가설 검증:</b> ${v}.<br><span class="corr-warn">⚠️ 호남(사전·민주 모두 높음)·영남처럼 지역 고유 성향이 섞여 '사전투표→정당' 인과로 단정할 수 없습니다. 2022 대선은 사전투표율이 높았어도 보수가 이긴 반례입니다.</span>`;
    }
  } else {
    note.innerHTML = `<b>가설:</b> 사전투표는 진보(민주)에, 당일 본투표는 보수(국힘)에 상대적으로 유리하다는 통념. <b>검증되지 않은 가설</b>이며 오늘 <b>개표로 확인</b>됩니다(18시 마감 후 이 표에 민주격차가 채워지고 상관이 계산됩니다).<br><span class="corr-warn">⚠️ 사전투표율↑이 특정 정당 유·불리로 직결되지 않습니다. 2022 대선 반례·지역 성향 교란이 큽니다.</span>`;
  }
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

function candRowHTML(parties, c, isLead) {
  const color = partyColor(parties, c.jd_name);
  const w = Math.max(0, Math.min(100, c.share_pct || 0));
  return `<div class="cand-row ${isLead ? 'cand-rank1' : ''}">
    <span class="cand-dot" style="background:${color}"></span>
    <span class="cand-name">${c.name || '—'}</span>
    <span class="cand-party">${c.jd_name || ''}</span>
    <span class="cand-bar-wrap"><span class="cand-bar" style="width:${w}%;background:${color}"></span></span>
    <span class="cand-share">${fmt1(c.share_pct)}%</span>
  </div>`;
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
    const candHTML = cands.map((c, i) => candRowHTML(parties, c, i === 0)).join('');

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
  const [cur, watchlist, groups, prevWinner, prevResult, prediction, predBasicHead, parties, earlyVoting] = await Promise.all([
    loadJSON(PATHS.current), loadJSON(PATHS.watchlist), loadJSON(PATHS.groups),
    loadJSON(PATHS.prevWinner), loadJSON(PATHS.prevResult), loadJSON(PATHS.prediction), loadJSON(PATHS.predBasicHead), loadJSON(PATHS.parties),
    loadJSON(PATHS.earlyVoting),
  ]);
  // 투표 시간대(개표 전): 실제 투표율이 있으면 투표율만 표시, 개표 섹션은 대기.
  if (beforeCount) {
    const nat = cur && cur.turnout && cur.turnout.national;
    if (nat && nat.turnout_pct != null) {
      renderHero(cur);
      renderTurnoutTable(cur);
      renderEarlyVsDay(cur, earlyVoting);
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

  renderHero(cur);
  renderTurnoutTable(cur);
  renderEarlyVsDay(cur, earlyVoting);
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
