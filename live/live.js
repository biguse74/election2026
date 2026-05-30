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
  prediction:  '../data/prediction_sido.json',
  parties:     '../data/parties.json',
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
const TYPE_ORDER = ['3', '4', '5', '6', '11'];

let LATEST_RACES = [];
let LATEST_PARTIES = {};
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
    document.querySelectorAll('tr.rd-row').forEach(d => {
      if (d.getAttribute('data-rk') === rk) d.hidden = !on;
    });
    document.querySelectorAll('tr.race-sum').forEach(s => {
      if (s.getAttribute('data-rk') === rk) {
        const ca = s.querySelector('.rd-caret');
        if (ca) ca.textContent = on ? '▴' : '▾';
      }
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
function matcherHit(r, m) {
  if (m.type && String(r.sg_type_code) !== m.type) return false;
  if (m.sido && r.sd_name !== m.sido) return false;
  if (m.where) {
    const place = [r.sd_name, r.sgg_name, r.wiw_name].filter(Boolean).join(' ');
    if (!place.includes(m.where)) return false;
  }
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
  document.getElementById('chief-races').innerHTML = `<div class="state-empty">${msg}</div>`;
  document.getElementById('search-results').innerHTML = '';
  document.getElementById('updated-at').textContent = '—';
}

// ── main ──────────────────────────────────────────────────────────
async function render() {
  const preview = location.search.includes('preview');
  const COUNT_START = Date.parse('2026-06-03T18:00:00+09:00');
  if (!preview && Date.now() < COUNT_START) {
    showWaiting('개표는 6월 3일(수) 18시 투표 마감 후 시작됩니다. 마감 후 자동으로 결과가 표시됩니다.');
    return;
  }
  const [cur, watchlist, groups, prediction, parties] = await Promise.all([
    loadJSON(PATHS.current), loadJSON(PATHS.watchlist), loadJSON(PATHS.groups),
    loadJSON(PATHS.prediction), loadJSON(PATHS.parties),
  ]);
  if (!cur) {
    document.getElementById('chief-races').innerHTML =
      `<div class="state-empty">개표 데이터가 아직 없습니다. 6/3 18시 투표 마감 후 수집이 시작됩니다.</div>`;
    document.getElementById('search-results').innerHTML = '';
    return;
  }
  const predMap = (prediction && prediction.sido_dem_win_prob) || {};
  LATEST_RACES = cur.races || [];
  LATEST_PARTIES = parties || {};

  renderHero(cur);
  renderWatchlist(watchlist);
  renderGroups(groups);
  renderChiefRaces(cur, predMap, LATEST_PARTIES);
  populateFilters(LATEST_RACES);
  bindFilters();
  bindRaceExpand();
  renderSearch();
}

render();
setInterval(render, REFRESH_MS);
