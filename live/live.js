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
  prediction:  '../data/prediction_sido_v2.json',
  predBasicHead: '../data/prediction_basic_head_v2.json',
  parties:     '../data/parties.json',
  earlyVoting: '../data/early_voting/20260603/latest.json',
  histHourly:  '../data/history_turnout_hourly.json',
  exitPoll:    '../data/live_counting/exit_poll.json',
  exitCompare: '../data/live_counting/exit_poll_compare.json',
  turnoutParty: '../data/live_counting/turnout_party.json',
  turnoutMulti: '../data/live_counting/turnout_party_multi.json',
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
const TYPE_ORDER = ['2', '3', '4', '5', '6', '11'];

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
  const counting = (r.progress_pct || 0) > 0;
  return cands.map(c => {
    const color = partyColor(LATEST_PARTIES, c.jd_name);
    const w = Math.max(0, Math.min(100, c.share_pct || 0));
    const lead = counting && c.current_rank === 1;
    return `<div class="rd-cand${lead ? ' rd-lead' : ''}" style="--lead-color:${color}">
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
// 1·2위 득표수 차이(표차). 후보 2명 미만이면 null.
function marginVotes(r) {
  const c = r.candidates || [];
  if (c.length < 2) return null;
  return Math.abs((c[0].votes || 0) - (c[1].votes || 0));
}
// 근소한 표차(박빙) 여부 — 격차 3%p 미만. 중선거구(기초의원)는 제외.
function isCloseRace(r) {
  const pp = r.rank1_minus_rank2_pp;
  return pp != null && pp < 3.0 && (r.progress_pct || 0) >= 1 && String(r.sg_type_code) !== '6';
}
// 격차 셀 — 표차(표)를 크게, %p를 작게. 박빙이면 빨강 강조.
function marginCellHTML(r) {
  const mv = marginVotes(r);
  const pp = r.rank1_minus_rank2_pp;
  if (mv == null) return pp != null ? `${fmt1(pp)}pp` : '—';
  const close = isCloseRace(r);
  return `<b class="${close ? 'margin-close' : ''}">${intComma(mv)}표</b>` +
    `<small class="margin-pp">${fmt1(pp)}pp</small>`;
}

function raceTableRow(r) {
  const rk = r.race_key || '';
  const c1 = (r.candidates || [])[0];
  const c2 = (r.candidates || [])[1];
  const dot = c1 ? `<span class="cand-dot" style="background:${partyColor(LATEST_PARTIES, c1.jd_name)}"></span>` : '';
  const lphoto = c1 ? candPhotoImg(r, c1, 'lead-photo') : '';
  const call = electionCall(r);
  const callHTML = call ? ` <span class="call-chip ${call.cls}">${call.label}</span>` : '';
  const lead = c1 ? `${lphoto}${dot}<b>${c1.name}</b> <span class="cand-party">${c1.jd_name || ''}</span> ${fmt1(c1.share_pct)}%${callHTML}` : '—';
  const second = c2 ? `${c2.name} ${fmt1(c2.share_pct)}%` : '—';
  const open = expandedKeys.has(rk);
  const summary = `<tr class="race-sum" data-rk="${esc(rk)}">
    <td>${r.sg_type_label}</td>
    <td>${racePlace(r)}</td>
    <td class="lead-cell">${lead}</td>
    <td>${second}</td>
    <td class="num margin-cell">${marginCellHTML(r)}</td>
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

  const t = document.getElementById('hero-turnout');
  const tm = document.getElementById('hero-turnout-meta');
  if (nat?.turnout_pct != null) {
    t.innerHTML = `${fmt1(nat.turnout_pct)}<span class="pct">%</span>`;
    tm.textContent = `투표자 ${intComma(nat.voters_so_far)} / 선거인 ${intComma(nat.eligible_voters)}`;
  }

  const races = cur?.races || [];
  const p = document.getElementById('hero-progress');
  const pm = document.getElementById('hero-progress-meta');
  let avg = 0;
  if (races.length) {
    let wsum = 0, w = 0;
    for (const r of races) { const e = r.eligible_voters || 0; wsum += (r.progress_pct || 0) * e; w += e; }
    avg = w ? wsum / w : 0;
    p.innerHTML = `${fmt1(avg)}<span class="pct">%</span>`;
    pm.textContent = `수집된 선거구 ${races.length}곳 기준 (선거인 가중)`;
  } else {
    p.innerHTML = `대기<span class="pct"></span>`;
    pm.textContent = '18시 마감 후 개표 시작';
  }

  // 개표 국면 전환: 개표가 사실상 끝나면(가중 진행률 99.5%↑) LIVE 배지를 내리고
  //   '실시간/진행 중' 문구를 '기록(아카이브)'으로 전환한다. 역사 보존용 페이지.
  const ended = races.length > 0 && avg >= 99.5;
  if (ended) {
    badge.hidden = true;
    const _tt = document.getElementById('page-title-text');
    const _ts = document.getElementById('page-sub');
    if (_tt) _tt.textContent = '투표·개표 기록';
    if (_ts) _ts.textContent = '2026-06-03(수) 제9회 지방선거 · 개표 완료 · 투표율과 개표 과정 기록(아카이브)';
  } else if (cur?.phase === 'live') {
    badge.hidden = false;
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

// 히어로 4번째 카드 — 투표율 맥락: 4년 전(2022) 대비 + 역대 순위.
// (당선 결과는 /result/ 페이지로 분리. 이 페이지는 투표·개표 과정 아카이브)
function renderProjection(cur, _histHourly) {
  const e = document.getElementById('hero-early');
  const meta = document.getElementById('hero-early-meta');
  const label = document.getElementById('hero-early-label');
  if (!e) return;
  const nat = cur && cur.turnout && cur.turnout.national;
  if (!nat || nat.turnout_pct == null) {
    if (label) label.textContent = '투표율';
    e.innerHTML = `<span class="pct" style="font-size:1.1rem">집계 중</span>`;
    if (meta) meta.textContent = '';
    return;
  }
  const fin = nat.turnout_pct;
  const rank = ZIBANG_HISTORY.filter(h => h.rate > fin).length + 1;
  const prev22 = ZIBANG_HISTORY.find(h => h.year === 2022);
  const dv = prev22 ? fin - prev22.rate : null;
  if (label) label.textContent = '4년 전(2022) 대비';
  if (dv != null) {
    e.innerHTML = `${dv >= 0 ? '+' : ''}${fmt1(dv)}<span class="pct">%p</span>`;
    if (meta) meta.textContent = `2022년 ${fmt1(prev22.rate)}% → 올해 ${fmt1(fin)}% · 역대 ${rank}위`;
  } else {
    e.innerHTML = `${fmt1(fin)}<span class="pct">%</span>`;
    if (meta) meta.textContent = `최종 투표율 · 역대 ${rank}위`;
  }
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
  // 정시점(HH:00) 외에 '현재 최신 누계'(박스값)를 끝점으로 추가 → 박스값보다 시간·값 모두 엄격히 클 때만.
  // 투표는 18시 마감이므로 끝점 시각은 18:00을 넘기지 않는다(마감 후 박스값=최종 투표율).
  const _natNow = cur && cur.turnout && cur.turnout.national;
  if (_natNow && _natNow.turnout_pct != null && typeof cur.polled_at === 'string' && cur.polled_at.length >= 16) {
    let _hhmm = cur.polled_at.slice(11, 16);
    if (_hhmm > '18:00') _hhmm = '18:00';
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
// 투표율↔정당 상관 — 시군구(기초단체장) 단위 4분할 산점도 + 해설.
let _tpData = null;
const _winColor = w => w === DEM ? 'var(--dem)' : (w === CON ? 'var(--con)' : '#8a8a96');
const _CORR_STR = ['거의 없음', '약함', '뚜렷', '매우 강함'];
const _rStrength = r => { const a = Math.abs(r); return a >= 0.7 ? 3 : a >= 0.4 ? 2 : a >= 0.2 ? 1 : 0; };
const _CORR_CHARTS = [
  { xk: 'day', yk: 'con', xl: '당일투표율 →', hl: true,
    title: '본투표 ↔ 보수',
    take: rr => `당일(본)투표가 높은 시군구일수록 <b>국힘 득표율이 높습니다</b> (r=${rr}). 보수 지지층이 당일투표에 더 몰린 패턴.` },
  { xk: 'early', yk: 'day', xl: '사전투표율 →',
    title: '사전 ↔ 당일',
    take: rr => `사전투표가 높은 곳은 <b>당일투표가 오히려 낮습니다</b> (r=${rr}). 사전이 본투표에 더해지는 게 아니라 <b>일부 대체</b>합니다.` },
  { xk: 'early', yk: 'dem', xl: '사전투표율 →',
    title: '사전 ↔ 민주',
    take: rr => `'사전투표=진보 유리' 통념과 달리, 시군구 단위에선 <b>거의 무관</b>합니다 (r=${rr}).` },
  { xk: 'total', yk: 'dem', xl: '전체투표율 →',
    title: '전체투표율 ↔ 민주',
    take: rr => `전체투표율이 높다고 민주가 유리하진 않습니다 (r=${rr}). 농촌 소규모 군이 투표율↑·보수/무소속↑인 영향이 큽니다.` },
];

function _corrScatter(pts, xk, yk, xl) {
  const W = 300, H = 188, padL = 30, padR = 8, padT = 8, padB = 28;
  const xs = pts.map(p => p[xk]), ys = pts.map(p => p[yk]);
  const xlo = Math.floor(Math.min(...xs) - 1), xhi = Math.ceil(Math.max(...xs) + 1);
  const ylo = Math.floor(Math.min(...ys) - 1), yhi = Math.ceil(Math.max(...ys) + 1);
  const px = x => padL + (x - xlo) / (xhi - xlo) * (W - padL - padR);
  const py = y => padT + (1 - (y - ylo) / (yhi - ylo)) * (H - padT - padB);
  const stat = pearson(xs, ys);
  const g = [];
  g.push(`<line x1="${padL}" y1="${H - padB}" x2="${W - padR}" y2="${H - padB}" stroke="#ddd"/>`);
  g.push(`<line x1="${padL}" y1="${padT}" x2="${padL}" y2="${H - padB}" stroke="#ddd"/>`);
  [xlo, xhi].forEach((xv, i) => g.push(`<text x="${px(xv).toFixed(0)}" y="${H - padB + 13}" font-size="9" fill="#aaa" text-anchor="${i ? 'end' : 'start'}">${xv}</text>`));
  [ylo, yhi].forEach((yv, i) => g.push(`<text x="${padL - 4}" y="${(py(yv) + (i ? 8 : 3)).toFixed(0)}" font-size="9" fill="#aaa" text-anchor="end">${yv}</text>`));
  if (stat) {
    const cy = v => Math.max(ylo, Math.min(yhi, v));
    const y1 = stat.slope * xlo + stat.intercept, y2 = stat.slope * xhi + stat.intercept;
    g.push(`<line x1="${px(xlo).toFixed(1)}" y1="${py(cy(y1)).toFixed(1)}" x2="${px(xhi).toFixed(1)}" y2="${py(cy(y2)).toFixed(1)}" stroke="#c41e3a" stroke-width="1.4" stroke-dasharray="5 4"/>`);
  }
  for (const p of pts) {
    g.push(`<circle cx="${px(p[xk]).toFixed(1)}" cy="${py(p[yk]).toFixed(1)}" r="2.7" fill="${_winColor(p.win)}" fill-opacity="0.72"><title>${esc(p.sd)} ${esc(p.sgg)} · ${xk} ${p[xk]}% · ${yk} ${p[yk]}%</title></circle>`);
  }
  g.push(`<text x="${((padL + W - padR) / 2).toFixed(0)}" y="${H - 3}" font-size="9" fill="#888" text-anchor="middle">${xl}  (${yk === 'con' ? '국힘' : yk === 'dem' ? '민주' : '당일'}% ↑)</text>`);
  return `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet">${g.join('')}</svg>`;
}

function _drawCorr(d) {
  const block = document.getElementById('corr-block');
  block.hidden = false;
  const nEl = document.getElementById('corr-n'); if (nEl) nEl.textContent = d.summary.n;
  document.getElementById('corr-grid').innerHTML = _CORR_CHARTS.map(c => {
    const st = pearson(d.points.map(p => p[c.xk]), d.points.map(p => p[c.yk]));
    const r = st ? st.r : 0, s = _rStrength(r), rr = (r >= 0 ? '+' : '') + r.toFixed(2);
    return `<div class="corr-card${c.hl ? ' hl' : ''}">
      <div class="corr-hd"><h3>${c.title}</h3><span class="corr-r s${s}">r=${rr} · ${_CORR_STR[s]}</span></div>
      ${_corrScatter(d.points, c.xk, c.yk, c.xl)}
      <div class="corr-take">${c.take(rr)}</div></div>`;
  }).join('');
  const sm = d.summary;
  const sc = (t, o, col) => `<div class="corr-sum-card"><div class="t" style="color:${col}">${t} 승리 ${o.n}곳 · 평균 투표율</div>
    <div class="row"><span>사전투표</span><b>${o.early}%</b></div>
    <div class="row"><span>당일(본)투표</span><b>${o.day}%</b></div>
    <div class="row"><span>전체</span><b>${o.total}%</b></div></div>`;
  document.getElementById('corr-summary').innerHTML = sc('민주', sm.dem_win, 'var(--dem)') + sc('국힘', sm.con_win, 'var(--con)');
  document.getElementById('corr-note').innerHTML =
    `<b>한눈에:</b> 보수는 <b>당일투표</b>에서, 진보는 사전투표 비중이 큰 곳에서 강했고, 사전·당일은 <b>서로 대체</b> 관계였습니다. ` +
    `<span class="corr-warn">⚠️ 이건 지역(시군구) 단위 상관일 뿐 인과가 아닙니다.</span> ` +
    `농촌/도시·지역색(호남↑민주·영남↑국힘)이 섞여 있어 '투표율→표심'으로 단정할 수 없습니다. 기준: ${esc(d.unit)} ${sm.n}곳.`;
}

function renderTurnoutCorr() {
  const block = document.getElementById('corr-block');
  if (!block) return;
  if (_tpData) { _drawCorr(_tpData); return; }
  loadJSON(PATHS.turnoutParty).then(d => {
    if (!d || !d.points || d.points.length < 5) { block.hidden = true; return; }
    _tpData = d; _drawCorr(d);
  });
}

// 4개 선거 비교 — 같은 지표가 매번 같은 쪽이면 구조적.
let _multiData = null;
const _MULTI_SERIES = [
  { k: 'day_con', label: '당일투표 ↔ 보수(국힘)', color: '#d8842a' },
  { k: 'early_con', label: '사전투표 ↔ 보수(국힘)', color: '#1e7d8a' },
  { k: 'early_dem', label: '사전투표 ↔ 진보(민주)', color: '#152484' },
];
const _rColor = r => r == null ? 'transparent'
  : (r >= 0 ? `rgba(214,52,52,${Math.min(0.85, 0.12 + Math.abs(r) * 0.8)})`
            : `rgba(30,74,138,${Math.min(0.85, 0.12 + Math.abs(r) * 0.8)})`);

function renderMultiCompare() {
  const block = document.getElementById('multi-block');
  if (!block) return;
  const draw = d => {
    const els = d.elections || [];
    if (els.length < 2) { block.hidden = true; return; }
    block.hidden = false;
    const W = 640, H = 320, padL = 46, padR = 14, padT = 16, padB = 46;
    const n = els.length;
    const px = i => padL + (n === 1 ? 0.5 : i / (n - 1)) * (W - padL - padR);
    const py = r => padT + (1 - (r + 1) / 2) * (H - padT - padB);
    const g = [];
    // 가로 기준선(0)
    g.push(`<line x1="${padL}" x2="${W - padR}" y1="${py(0).toFixed(1)}" y2="${py(0).toFixed(1)}" stroke="#bbb"/>`);
    [1, 0.5, -0.5, -1].forEach(rv => {
      g.push(`<line x1="${padL}" x2="${W - padR}" y1="${py(rv).toFixed(1)}" y2="${py(rv).toFixed(1)}" stroke="#f2f2f2"/>`);
      g.push(`<text x="${padL - 6}" y="${(py(rv) + 4).toFixed(1)}" font-size="10" fill="#999" text-anchor="end">${rv > 0 ? '+' : ''}${rv}</text>`);
    });
    g.push(`<text x="${padL - 6}" y="${(py(0) + 4).toFixed(1)}" font-size="10" fill="#999" text-anchor="end">0</text>`);
    els.forEach((e, i) => g.push(`<text x="${px(i).toFixed(1)}" y="${H - padB + 16}" font-size="10.5" fill="#555" text-anchor="middle">${esc(e.key)}</text>`));
    g.push(`<text x="${padL}" y="${H - 8}" font-size="10" fill="#888">▲ 위쪽=보수와 +상관 · ▼ 아래=음의 상관</text>`);
    // 점선 영역 라벨
    for (const s of _MULTI_SERIES) {
      const pts = els.map((e, i) => `${px(i).toFixed(1)},${py(e.corr[s.k] == null ? 0 : e.corr[s.k]).toFixed(1)}`);
      g.push(`<polyline points="${pts.join(' ')}" fill="none" stroke="${s.color}" stroke-width="2.4"/>`);
      els.forEach((e, i) => {
        const r = e.corr[s.k]; if (r == null) return;
        g.push(`<circle cx="${px(i).toFixed(1)}" cy="${py(r).toFixed(1)}" r="4" fill="${s.color}"><title>${e.label} · ${s.label} r=${r}</title></circle>`);
      });
    }
    document.getElementById('multi-svg').innerHTML = g.join('');
    document.getElementById('multi-legend').innerHTML = _MULTI_SERIES.map(s =>
      `<i class="line" style="background:${s.color}"></i>${esc(s.label)}`).join('');
    // 표
    const cols = [['early_dem', '사전↔민주'], ['early_con', '사전↔국힘'], ['day_con', '당일↔국힘'], ['early_day', '사전↔당일']];
    const head = `<tr><th>선거</th><th>n</th>${cols.map(c => `<th>${c[1]}</th>`).join('')}</tr>`;
    const body = els.map(e => `<tr><td>${esc(e.label)}</td><td>${e.n}</td>${cols.map(c => {
      const r = e.corr[c[0]];
      return `<td><span class="rcell" style="background:${_rColor(r)};padding:2px 7px">${r == null ? '–' : (r >= 0 ? '+' : '') + r.toFixed(2)}</span></td>`;
    }).join('')}</tr>`).join('');
    document.getElementById('multi-table').innerHTML = `<table class="multi-table">${head}${body}</table>`;
    document.getElementById('multi-note').innerHTML =
      `<b>구조적(4개 선거 내내 일관):</b> <b style="color:#d8842a">당일↔보수는 항상 +</b>, <b style="color:#1e7d8a">사전↔보수는 항상 −</b>. ` +
      `보수는 당일, 진보·중도는 사전에 더 몰리는 경향이 2022~2026 반복됩니다. ` +
      `<b style="color:#152484">사전↔진보</b>는 <b>대선에서만 강하고</b>(전국 진영전) 지방선거에선 약해 — 통념은 선거 성격을 탑니다. ` +
      `<span class="corr-warn">⚠️ 지역 단위 상관(인과 아님).</span> 지선은 기초단체장, 총선은 지역구, 대선은 대통령 기준.`;
  };
  if (_multiData) { draw(_multiData); return; }
  loadJSON(PATHS.turnoutMulti).then(d => { if (!d) { block.hidden = true; return; } _multiData = d; draw(d); });
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

// 당선 확실/유력 판정 — 단독 1인 선출(시도지사3·기초단체장4·국회의원2)만. 기자용 보수 기준.
//   당선 확실 = 격차 > 남은표×0.7 → 2위가 남은표의 85%↑를 쓸어담아야 역전(사실상 불가).
//   당선 유력 = 격차 > 남은표×0.4 → 2위가 남은표의 70%↑ 필요(역전 가능성 매우 낮음).
function electionCall(r) {
  if (!['2', '3', '4'].includes(String(r.sg_type_code))) return null;  // 중선거구 제외
  const cands = r.candidates || [];
  const c1 = cands[0];
  if (!c1) return null;
  const prog = r.progress_pct || 0;
  if (prog < 30) return null;                          // 개표 초반 제외
  const v1 = c1.votes || 0;
  const v2 = cands[1] ? (cands[1].votes || 0) : 0;
  const margin = v1 - v2;
  if (margin <= 0) return null;
  const counted = r.valid_votes || cands.reduce((s, c) => s + (c.votes || 0), 0);
  // 남은 유효표 추정(개표율 기준, NEC 개표율은 투표수 대비라 신뢰 가능). 살짝 과대추정=보수적.
  const remaining = prog > 0 ? counted * (100 - prog) / prog : Infinity;
  if (prog >= 50 && margin > remaining * 0.7) return { cls: 'call-win', label: '당선 확실' };
  if (margin > remaining * 0.4) return { cls: 'call-lead', label: '당선 유력' };
  return null;
}

function watchStatus(race, cand) {
  const prog = race.progress_pct || 0;
  const cands = race.candidates || [];
  const rank = cand.current_rank;
  // 기초의원(구시군의회)은 중선거구제(여러 명 당선) → 단독 1위 판정 대신 순위만 중립 표기
  if (String(race.sg_type_code) === '6') {
    const cls = rank === 1 ? 'wc-lead' : (rank <= 3 ? 'wc-close' : 'wc-behind');
    const tail = prog >= 95 ? ' · 개표 거의 마감' : '';
    return { cls, label: `현재 ${rank}위 (중선거구)${tail}` };
  }
  if (rank === 1) {
    const call = electionCall(race);
    if (call) return { cls: call.cls === 'call-win' ? 'wc-win' : 'wc-lead', label: call.label };
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
  // '주목 후보' 섹션은 비표시(페이지 단순화). watchlist.json은 기초의원 타깃 수집용으로 유지.
  block.hidden = true;
  return;
  /* eslint-disable no-unreachable */
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
    const cs = race.candidates || [];
    let marginHTML = '';
    if (String(race.sg_type_code) !== '6' && cs.length >= 2) {
      const close = isCloseRace(race);
      const d = cand.current_rank === 1
        ? (cand.votes || 0) - (cs[1].votes || 0)
        : (cs[0].votes || 0) - (cand.votes || 0);
      const who = cand.current_rank === 1 ? '2위와' : '1위와';
      marginHTML = `<div class="watch-margin-row"><span class="watch-margin ${close ? 'margin-close' : ''}">${who} <b>${intComma(d)}표</b> 차${close ? ' · 박빙' : ''}</span></div>`;
    }
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
      ${marginHTML}
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
    // 후보 사진 룩업용 가상 race (시도지사 type 3=시도명, 재보궐 type 2=시도+시군구)
    const pr = { sg_type_code: race.sgType || '3', sd_name: race.sdName || race.region || '', sgg_name: race.sggName || null };
    const rows = cands.map((c, i) => {
      const color = partyColor(LATEST_PARTIES, c.party);
      const w = Math.max(0, Math.min(100, c.pct));
      return `<div class="ep-cand${i === 0 ? ' ep-lead' : ''}">` +
        candPhotoImg(pr, { name: c.name }, 'ep-photo') +
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
    asmRoot.innerHTML = asm.map(r => card({ label: r.region, region: r.region, sdName: r.sd, sggName: r.sgg, sgType: '2', candidates: r.candidates })).join('');
  }
}

// ── 출구조사·예측 3종 비교표 (방송3사 / JTBC / 뉴탐사) ──────────────
// 비교표 한 줄의 실제 개표 1위(당선) 후보를 현재 개표 데이터에서 찾는다.
function epcActual(row) {
  const races = LATEST_RACES || [];
  let r = null;
  if (row.type === 'gov') {
    r = races.find(x => String(x.sg_type_code) === '3' && x.sd_name === row.region);
  } else {  // 재보궐(asm) — 예측 후보 이름으로 해당 선거구를 찾음
    const names = [row.b3, row.jtbc, row.ours].filter(Boolean).map(p => p.name);
    r = races.find(x => String(x.sg_type_code) === '2' && (x.candidates || []).some(c => names.includes(c.name)));
  }
  if (!r || !(r.candidates || []).length) return null;
  const w = r.candidates[0];
  return { name: w.name, party: w.jd_name, pct: w.share_pct, prog: r.progress_pct || 0 };
}

function renderExitPollCompare(data) {
  const block = document.getElementById('epc-block');
  const root = document.getElementById('epc-table');
  if (!block || !root) return;
  const rows = (data && data.rows) || [];
  if (!rows.length) { block.hidden = true; return; }
  block.hidden = false;

  // 출처별 적중 집계(실제 1위와 예측 1위 이름 일치). 개표 80%↑인 선거만 채점.
  const score = { b3: 0, jtbc: 0, ours: 0 }, denom = { b3: 0, jtbc: 0, ours: 0 };
  const hit = (pred, act) => pred && act && act.prog >= 80 ? (pred.name === act.name ? 'hit' : 'miss') : '';

  const predCell = (e, act, kind) => {
    if (!e) return '<span class="epc-na">–</span>';
    const h = hit(e, act);
    const mark = h === 'hit' ? '<span class="epc-ok">✓</span>' : (h === 'miss' ? '<span class="epc-x">✗</span>' : '');
    if (kind === 'ours') {  // 뉴탐사: 이름만(확률은 척도 달라 제외) + 예측 날짜
      let dt = '';
      if (e.date) {
        const d = e.date.slice(5).replace('-', '.');
        dt = e.url
          ? ` <a class="epc-date" href="${esc(e.url)}" target="_blank" rel="noopener">${d} 예측 ↗</a>`
          : ` <span class="epc-date">${d} 예측</span>`;
      }
      return `<b>${esc(e.name)}</b>${mark}${dt}`;
    }
    const color = partyColor(LATEST_PARTIES, e.party);
    return `<span class="epc-dot" style="background:${color}"></span><b>${esc(e.name)}</b> <span class="epc-v">${fmt1(e.pct)}%</span>${mark}`;
  };
  const actCell = (act) => {
    if (!act) return '<span class="epc-na">개표 대기</span>';
    const color = partyColor(LATEST_PARTIES, act.party);
    const tag = act.prog >= 80 ? '' : ` <span class="epc-prog">개표 ${fmt1(act.prog)}%</span>`;
    return `<span class="epc-dot" style="background:${color}"></span><b>${esc(act.name)}</b> <span class="epc-v">${fmt1(act.pct)}%</span>${tag}`;
  };

  const head = `<div class="epc-row epc-head"><div>선거</div><div>방송3사 출구조사</div><div>JTBC 예측조사</div><div>뉴탐사 시뮬레이션<span class="epc-h-sub">예측 1위</span></div><div>실제 결과<span class="epc-h-sub">개표 1위</span></div></div>`;
  const body = rows.map(r => {
    const act = epcActual(r);
    for (const k of ['b3', 'jtbc', 'ours']) {
      const hv = hit(r[k], act);
      if (hv) { denom[k]++; if (hv === 'hit') score[k]++; }
    }
    return `<div class="epc-row">` +
      `<div class="epc-rg">${esc(r.label)}</div>` +
      `<div>${predCell(r.b3, act, 'm')}</div><div>${predCell(r.jtbc, act, 'm')}</div>` +
      `<div>${predCell(r.ours, act, 'ours')}</div><div class="epc-act">${actCell(act)}</div></div>`;
  }).join('');
  root.innerHTML = head + body;

  // 적중률 요약 + 가장 정확한 출처
  const sumEl = document.getElementById('epc-summary');
  if (sumEl) {
    const NAME = { b3: '방송3사', jtbc: 'JTBC', ours: '뉴탐사' };
    const parts = ['b3', 'jtbc', 'ours'].filter(k => denom[k]).map(k => `${NAME[k]} ${score[k]}/${denom[k]}`);
    if (parts.length) {
      const best = ['b3', 'jtbc', 'ours'].filter(k => denom[k])
        .sort((a, b) => (score[b] / denom[b]) - (score[a] / denom[a]) || denom[b] - denom[a])[0];
      sumEl.innerHTML = `적중 — ${parts.join(' · ')} <b style="color:#127a3e">· 가장 정확: ${NAME[best]}</b>`;
    } else {
      sumEl.textContent = '개표가 충분히 진행되면 적중 여부를 표시합니다.';
    }
  }
}

// ── 판세 그래픽 (뉴탐사 자체 제작 타일 지도) ────────────────────────
// 17개 시도(전남광주 통합 1) 대략 지리 배치. 색=판정(민주/국힘/경합). 사실 데이터 기반.
const PANSE_GRID = {
  '서울특별시': [2, 0], '강원특별자치도': [4, 0],
  '인천광역시': [1, 1], '경기도': [3, 1],
  '충청남도': [1, 2], '세종특별자치시': [2, 2], '충청북도': [3, 2], '경상북도': [4, 2],
  '전북특별자치도': [1, 3], '대전광역시': [2, 3], '대구광역시': [4, 3],
  '전남광주통합특별시': [1, 4], '경상남도': [3, 4], '울산광역시': [4, 4],
  '부산광역시': [4, 5], '제주특별자치도': [1, 5],
};
// 방송사 공식 '경합' 지역(우열 판정). 그 외엔 1위 정당으로 색칠.
const B3_TOSSUP = new Set(['부산광역시', '대구광역시', '강원특별자치도', '전북특별자치도']);
const JTBC_TOSSUP = new Set(['대구광역시', '충청북도', '충청남도', '전북특별자치도', '경상남도']);
function panseJudge(row, src) {
  const lead = row[src];
  if (!lead) return null;
  if ((src === 'b3' ? B3_TOSSUP : JTBC_TOSSUP).has(row.region)) return '경합';
  return lead.party === '더불어민주당' ? '민주' : (lead.party === '국민의힘' ? '국힘' : '기타');
}
function renderPanseBoard(data) {
  const block = document.getElementById('panse-block');
  const root = document.getElementById('panse-boards');
  if (!block || !root) return;
  const rows = (data && data.rows || []).filter(r => r.type === 'gov' && PANSE_GRID[r.region]);
  if (!rows.length) { block.hidden = true; return; }
  block.hidden = false;
  const COLOR = { '민주': '#2b6cb0', '국힘': '#e74c3c', '경합': '#8e7cc3', '기타': '#888' };
  const board = (src, title, sub) => {
    const cnt = { '민주': 0, '국힘': 0, '경합': 0, '기타': 0 };
    const tiles = rows.map(r => {
      const j = panseJudge(r, src); if (!j) return '';
      cnt[j]++;
      const pos = PANSE_GRID[r.region], lead = r[src];
      return `<div class="pb-tile" style="grid-column:${pos[0] + 1};grid-row:${pos[1] + 1};background:${COLOR[j]}">` +
        `<span class="pb-sd">${SIDO_SHORT[r.region] || r.region}</span><span class="pb-nm">${esc(lead.name)}</span></div>`;
    }).join('');
    const legend = `<div class="pb-legend"><span><i style="background:${COLOR['민주']}"></i>민주 ${cnt['민주']}</span>` +
      `<span><i style="background:${COLOR['국힘']}"></i>국힘 ${cnt['국힘']}</span>` +
      `<span><i style="background:${COLOR['경합']}"></i>경합 ${cnt['경합']}</span></div>`;
    return `<div class="pb-col"><div class="pb-title">${title}<span class="pb-sub">${sub}</span></div><div class="pb-grid">${tiles}</div>${legend}</div>`;
  };
  root.innerHTML = board('b3', '방송3사', '출구조사') + board('jtbc', 'JTBC', '예측조사');
}

function marginText(m) {
  if (m == null) return '—';
  const who = m > 0 ? '민주' : '국힘';
  return `${who} +${Math.abs(m).toFixed(1)}pp`;
}

// 정당별 우세(현재 1위) 집계 바 — 시도지사·국회의원 재보궐 공용
function partyTallyHTML(races, totalCount) {
  const counted = races.filter(r => (r.progress_pct || 0) > 0 && (r.candidates || []).length);
  if (!counted.length) return '';
  let dem = 0, con = 0, etc = 0, sure = 0;
  for (const r of counted) {
    const p = (r.candidates[0] || {}).jd_name;
    if (p === DEM) dem++; else if (p === CON) con++; else etc++;
    const call = electionCall(r);
    if (call && call.cls === 'call-win') sure++;
  }
  return `<div class="party-tally">
    <span class="pt-item pt-dem">민주 <b>${dem}</b></span>
    <span class="pt-item pt-con">국힘 <b>${con}</b></span>
    <span class="pt-item pt-etc">그외 <b>${etc}</b></span>
    <span class="pt-meta">현재 1위 기준 · 개표 ${counted.length}/${totalCount}곳${sure ? ` · 당선확실 ${sure}` : ''}</span>
  </div>`;
}

function renderChiefRaces(cur, predMap, parties) {
  const root = document.getElementById('chief-races');
  const chiefs = (cur?.races || []).filter(r => String(r.sg_type_code) === '3');
  const tallyEl = document.getElementById('chief-tally');
  if (tallyEl) tallyEl.innerHTML = partyTallyHTML(chiefs, 17);
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
      const mv = marginVotes(race);
      const mvText = mv != null
        ? ` <span class="rc-margin ${isCloseRace(race) ? 'margin-close' : ''}">${intComma(mv)}표차${isCloseRace(race) ? ' · 박빙' : ''}</span>`
        : '';
      compareHTML = `
        <span class="rc-item">실제 <b>${marginText(cls.actualMargin)}</b>${mvText}</span>
        ${predPart}
        <span class="rc-verdict v-${cls.verdict}">${cls.label}</span>`;
    } else {
      compareHTML = `<span class="rc-item">개표 진행 ${fmt1(race.progress_pct)}%</span>
        <span class="rc-verdict v-${cls.verdict}">${cls.label}</span>`;
    }

    const call = electionCall(race);
    const callHTML = call ? `<span class="call-chip ${call.cls}">${call.label}</span>` : '';
    return `<div class="race-card">
      <div class="race-card-head">
        <span class="race-sido">${race.sd_name}</span>
        <span class="race-progress">${callHTML}개표 <b>${fmt1(race.progress_pct)}%</b></span>
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
  const etcMode = (sm.con_mode || 0) + (sm.ind_mode || 0);   // 그외 = 국힘 + 무소속·기타
  const predLine = (sm.dem_mode != null)
    ? `<b style="color:var(--dem)">민주 ${sm.dem_mode}곳</b> · 그외 ${etcMode}곳 <span class="bh-sub">(민주 예상범위 ${ci[0]}~${ci[1]}곳)</span>`
    : '—';
  const acc = withPred ? Math.round(matched / withPred * 100) : null;
  const verdict = acc != null ? `예측 방향 적중 ${matched}/${withPred}곳 (${acc}%)` : '개표 20%+ 선거구부터 적중 집계';
  root.innerHTML = `
    <div class="bh-grid">
      <div class="bh-card" style="border-left:4px solid var(--dem)">
        <div class="bh-label">뉴탐사 예측 (시뮬레이션)</div>
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

// ── 국회의원 재·보궐 개표 ──────────────────────────────────────────
function renderRepoll(cur) {
  const block = document.getElementById('repoll-block');
  const root = document.getElementById('repoll-races');
  if (!block || !root) return;
  const races = (cur?.races || []).filter(r => String(r.sg_type_code) === '2');
  if (!races.length) { block.hidden = true; return; }
  // 개표율 높은 곳 → 접전(격차 작은) 순으로
  races.sort((a, b) =>
    (b.progress_pct || 0) - (a.progress_pct || 0) ||
    (a.rank1_minus_rank2_pp ?? 999) - (b.rank1_minus_rank2_pp ?? 999));
  block.hidden = false;
  const tallyEl = document.getElementById('repoll-tally');
  if (tallyEl) tallyEl.innerHTML = partyTallyHTML(races, races.length);
  root.innerHTML = raceTable(races.map(raceTableRow).join(''));
}

// ── 교육감 개표 (정당 없는 단독 선출) ──────────────────────────────
function renderEdu(cur) {
  const block = document.getElementById('edu-block');
  const root = document.getElementById('edu-races');
  if (!block || !root) return;
  const races = (cur?.races || []).filter(r => String(r.sg_type_code) === '11');
  if (!races.length) { block.hidden = true; return; }
  races.sort((a, b) =>
    (b.progress_pct || 0) - (a.progress_pct || 0) ||
    (a.rank1_minus_rank2_pp ?? 999) - (b.rank1_minus_rank2_pp ?? 999));
  block.hidden = false;
  root.innerHTML = raceTable(races.map(raceTableRow).join(''));
}

// ── 당선 확실·유력 종합 ────────────────────────────────────────────
function renderCalled(cur) {
  const block = document.getElementById('called-block');
  if (!block) return;
  const races = (cur?.races || []).filter(r => ['2', '3', '4'].includes(String(r.sg_type_code)));
  const tagged = races.map(r => ({ r, call: electionCall(r) })).filter(x => x.call);
  if (!tagged.length) { block.hidden = true; return; }
  block.hidden = false;
  const ord = { '3': 0, '2': 1, '4': 2 };   // 시도지사 → 국회의원 → 기초단체장
  const sure = tagged.filter(x => x.call.cls === 'call-win').map(x => x.r).sort((a, b) =>
    (ord[a.sg_type_code] - ord[b.sg_type_code]) ||
    (((b.candidates[0] || {}).share_pct || 0) - ((a.candidates[0] || {}).share_pct || 0)));
  const lead = tagged.filter(x => x.call.cls === 'call-lead').map(x => x.r).sort((a, b) =>
    (a.rank1_minus_rank2_pp ?? 99) - (b.rank1_minus_rank2_pp ?? 99));  // 박빙(근소) 먼저
  let dem = 0, con = 0, etc = 0;
  for (const r of sure.concat(lead)) {
    const p = (r.candidates[0] || {}).jd_name;
    if (p === DEM) dem++; else if (p === CON) con++; else etc++;
  }
  document.getElementById('called-summary').innerHTML = `<div class="party-tally">
    <span class="pt-item pt-dem">민주 <b>${dem}</b></span>
    <span class="pt-item pt-con">국힘 <b>${con}</b></span>
    <span class="pt-item pt-etc">그외 <b>${etc}</b></span>
    <span class="pt-meta">확실 ${sure.length} · 유력 ${lead.length} (현재 1위 기준)</span>
  </div>`;
  document.getElementById('called-sure-n').textContent = `${sure.length}곳`;
  document.getElementById('called-lead-n').textContent = `${lead.length}곳`;
  document.getElementById('called-sure').innerHTML = sure.length
    ? raceTable(sure.map(raceTableRow).join('')) : '<div class="state-empty" style="padding:12px 0">아직 없음</div>';
  document.getElementById('called-lead').innerHTML = lead.length
    ? raceTable(lead.map(raceTableRow).join('')) : '<div class="state-empty" style="padding:12px 0">아직 없음</div>';
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
  // 검색·필터를 적용하기 전에는 결과를 쏟아내지 않고 검색창만 보여 준다.
  if (!f.type && !f.sido && !f.party && !f.q) {
    countEl.textContent = '';
    root.innerHTML = `<div class="state-empty">후보·지역을 검색하거나 위 필터(선거 종류·시도·정당)를 선택하면 개표 결과가 나옵니다.</div>`;
    return;
  }
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
  const rp = document.getElementById('repoll-block'); if (rp) rp.hidden = true;
  const cb2 = document.getElementById('called-block'); if (cb2) cb2.hidden = true;
  const eb = document.getElementById('edu-block'); if (eb) eb.hidden = true;
  document.getElementById('chief-races').innerHTML = `<div class="state-empty">${msg}</div>`;
  const bh = document.getElementById('bh-compare'); if (bh) bh.innerHTML = `<div class="state-empty">${msg}</div>`;
  document.getElementById('search-results').innerHTML = '';
  document.getElementById('updated-at').textContent = '—';
}

// 투표율 섹션 접기/펴기 — 개표 모드에선 기본 접어 개표까지 스크롤 단축.
let _collapsibleInit = false;
function initCollapsible(beforeCount) {
  // 스크롤 압박↓ + 정보 보존(아카이빙): 부가 섹션을 접기 가능으로. 헤더 클릭으로 펼침.
  // 기본 펼침은 핵심 결과(주목 후보·당선 종합·시도지사)만, 나머지는 접어 둔다.
  const ids = [
    'trend-block', 'evd-block', 'histcmp-block', 'sigungu-block', 'corr-block',
    'search-block', 'exitpoll-block', 'epc-block', 'panse-block',
  ];
  // epc-block(예측 vs 실제 — 누가 맞혔나)은 뉴탐사 정확도를 보여주는 핵심이라 기본 펼침.
  const openByDefault = new Set(['trend-block', 'evd-block', 'histcmp-block', 'epc-block']);
  ids.forEach(id => { const s = document.getElementById(id); if (s) s.classList.add('collapsible'); });
  if (_collapsibleInit) return;
  _collapsibleInit = true;
  document.addEventListener('click', ev => {
    const h2 = ev.target.closest && ev.target.closest('h2');
    if (h2 && h2.parentElement && h2.parentElement.classList.contains('collapsible')) {
      h2.parentElement.classList.toggle('collapsed');
    }
  });
  if (!beforeCount) ids.forEach(id => {
    if (openByDefault.has(id)) return;
    const s = document.getElementById(id); if (s) s.classList.add('collapsed');
  });
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
  if (exitPoll && exitPoll.governor && exitPoll.governor.length) await ensurePhotos();
  renderExitPoll(exitPoll);
  loadJSON(PATHS.exitCompare).then(d => { renderExitPollCompare(d); renderPanseBoard(d); });
  // 투표 시간대(개표 전): 실제 투표율이 있으면 투표율만 표시, 개표 섹션은 대기.
  if (beforeCount) {
    const nat = cur && cur.turnout && cur.turnout.national;
    if (nat && nat.turnout_pct != null) {
      renderHero(cur, earlyVoting);
      initCollapsible(beforeCount);
      renderProjection(cur, histHourly);
      renderCompare2022(cur, histHourly);
      renderTurnoutTrend(cur, histHourly);
      renderEarlyVsDay(cur, earlyVoting);
      renderSigunguAll(cur);
      renderHistoryCompare(cur, histHourly);
      renderTurnoutCorr(cur);
      renderMultiCompare();
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
  initCollapsible(beforeCount);
  renderProjection(cur, histHourly);
  // 투표(turnout) 아카이브
  renderTurnoutTrend(cur, histHourly);
  renderEarlyVsDay(cur, earlyVoting);
  renderSigunguAll(cur);
  renderHistoryCompare(cur, histHourly);
  renderTurnoutCorr(cur);
  renderMultiCompare();
  renderWatchlist(watchlist);   // watch-block 숨김 처리만
  // 개표(counting) 아카이브 — 전체 선거구 검색
  populateFilters(LATEST_RACES);
  bindFilters();
  bindRaceExpand();
  renderSearch();
  // 당선 결과(시도지사·기초단체장·교육감·재보궐·당선 종합)는 /result/ 페이지로 분리 → 중복 섹션 숨김.
  ['called-block', 'chief-block', 'edu-block', 'bh-block', 'repoll-block', 'groups-block'].forEach(id => {
    const s = document.getElementById(id); if (s) s.hidden = true;
  });
}

// 접힌 섹션 헤더에도 핵심 숫자를 보여 줌(스크롤 없이 한눈에 + 아카이빙).
function setHeaderSummary(blockId, html) {
  const sec = document.getElementById(blockId);
  const h2 = sec && sec.querySelector('h2');
  if (!h2) return;
  let s = h2.querySelector('.block-sum');
  if (!s) { s = document.createElement('span'); s.className = 'block-sum'; h2.appendChild(s); }
  s.innerHTML = html;
}
function _tallyShort(races) {
  let d = 0, c = 0, e = 0;
  for (const r of races) { if (!(r.candidates || []).length) continue; const p = r.candidates[0].jd_name; if (p === DEM) d++; else if (p === CON) c++; else e++; }
  return { d, c, e };
}
function renderHeaderSummaries(cur) {
  const byT = t => (cur?.races || []).filter(r => String(r.sg_type_code) === t && (r.candidates || []).length);
  const dc = (t) => `<b style="color:var(--dem)">민주 ${t.d}</b> · <b style="color:var(--con)">국힘 ${t.c}</b>${t.e ? ` · 그외 ${t.e}` : ''}`;
  const ch = byT('3'), bh = byT('4'), rp = byT('2'), ed = byT('11');
  if (ch.length) setHeaderSummary('chief-block', dc(_tallyShort(ch)));
  if (bh.length) setHeaderSummary('bh-block', dc(_tallyShort(bh)));
  if (rp.length) setHeaderSummary('repoll-block', dc(_tallyShort(rp)));
  if (ed.length) setHeaderSummary('edu-block', `${ed.length}곳 집계`);
  // 당선 확실·유력 종합 — 접힌 헤더에 확실/유력 수
  const called = (cur?.races || []).filter(r => ['2', '3', '4'].includes(String(r.sg_type_code)))
    .map(r => electionCall(r)).filter(Boolean);
  const sure = called.filter(c => c.cls === 'call-win').length;
  const lead = called.filter(c => c.cls === 'call-lead').length;
  if (sure + lead) setHeaderSummary('called-block', `<b style="color:#127a3e">당선 확실 ${sure}</b> · 유력 ${lead}`);
}

render();
setInterval(render, REFRESH_MS);
