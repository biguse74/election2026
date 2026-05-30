// 실시간 개표 페이지 로직
// 데이터 소스:
//   data/live_counting/current.json  — 선관위 OpenAPI 가공본 (투표율 + races[])
//   data/prediction_sido.json        — 뉴탐사 자체 시뮬레이션 (시도별 민주 당선확률 %)
//   data/parties.json                — 정당 색상

const PATHS = {
  current:     '../data/live_counting/current.json',
  prediction:  '../data/prediction_sido.json',
  parties:     '../data/parties.json',
};

const DEM = '더불어민주당';
const CON = '국민의힘';
const REFRESH_MS = 60 * 1000;  // 1분마다 재로딩 (개표일에만 의미)

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

function fmtKST(iso) {
  if (!iso) return '—';
  try {
    const d = new Date(iso); // iso already +09:00
    const mm = `${d.getMonth() + 1}`.padStart(2, '0');
    const dd = `${d.getDate()}`.padStart(2, '0');
    const hh = `${d.getHours()}`.padStart(2, '0');
    const mi = `${d.getMinutes()}`.padStart(2, '0');
    return `${mm}/${dd} ${hh}:${mi}`;
  } catch (e) { return iso; }
}

// ── Hero ──────────────────────────────────────────────────────────
function renderHero(cur) {
  const nat = cur?.turnout?.national;
  const badge = document.getElementById('live-badge');
  if (cur?.phase === 'live') badge.hidden = false;

  // 전국 투표율
  const t = document.getElementById('hero-turnout');
  const tm = document.getElementById('hero-turnout-meta');
  if (nat?.turnout_pct != null) {
    t.innerHTML = `${fmt1(nat.turnout_pct)}<span class="pct">%</span>`;
    tm.textContent = `투표자 ${intComma(nat.voters_so_far)} / 선거인 ${intComma(nat.eligible_voters)}`;
  }

  // 개표 진행률 — races progress의 선거인 가중 평균
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

  // 사전투표 비중
  const e = document.getElementById('hero-early');
  if (nat?.early_share_of_total_pct != null) {
    e.innerHTML = `${fmt1(nat.early_share_of_total_pct)}<span class="pct">%</span>`;
    document.getElementById('hero-early-meta').textContent =
      `사전 ${intComma(nat.early_voters_so_far)} · 당일 ${intComma(nat.day_voters_so_far)}`;
  }

  document.getElementById('updated-at').textContent = fmtKST(cur?.polled_at) + ' (KST)';
}

// ── 시도지사 예측 vs 실제 ──────────────────────────────────────────
// race.candidates에서 민주/국힘 후보를 정당으로 식별, 실제격차(민주-국힘) 계산.
function partyShare(race, party) {
  const c = (race.candidates || []).find(c => c.jd_name === party);
  return c ? { share: c.share_pct, name: c.name } : null;
}

// demProb = 뉴탐사 시뮬레이션의 '민주 당선확률(%)' 또는 null.
function classifyRace(race, demProb) {
  const dem = partyShare(race, DEM);
  const con = partyShare(race, CON);
  const prog = race.progress_pct || 0;
  const actualMargin = (dem && con) ? (dem.share - con.share) : null;

  if (prog < 5) return { verdict: 'early', label: '개표 초반', actualMargin, demProb };
  if (demProb == null) return { verdict: 'none', label: '예측 없음', actualMargin, demProb };
  if (actualMargin == null) return { verdict: 'none', label: '양자 비교 불가', actualMargin, demProb };

  const predDem = demProb >= 50;        // 우리 예측이 우세로 본 진영
  const actualDem = actualMargin > 0;   // 실제 우세 진영
  const confident = demProb >= 80 || demProb <= 20;
  const tossup = demProb > 35 && demProb < 65;

  if (predDem !== actualDem) {
    return { verdict: 'upset', label: '이변 — 예측과 반대', actualMargin, demProb, predDem };
  }
  if (tossup) return { verdict: 'band', label: '접전 예측 적중', actualMargin, demProb, predDem };
  if (confident) return { verdict: 'hit', label: '예측 적중', actualMargin, demProb, predDem };
  return { verdict: 'hit', label: '예측 부합', actualMargin, demProb, predDem };
}

// 우리 예측을 '우세 진영 + 당선확률'로 표기. demProb는 민주 기준 %.
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
  // 격차 작은(접전) 순으로 — 접전 지역이 위로
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

// ── 그 외 개표 ─────────────────────────────────────────────────────
function renderOtherRaces(cur) {
  const root = document.getElementById('other-races');
  const others = (cur?.races || []).filter(r => String(r.sg_type_code) !== '3');
  if (!others.length) { root.innerHTML = `<div class="state-empty">그 외 수집된 개표 데이터가 없습니다.</div>`; return; }

  const rows = others.map(r => {
    const c1 = (r.candidates || [])[0];
    const c2 = (r.candidates || [])[1];
    const place = [r.sgg_name, r.wiw_name].filter(x => x && x !== '합계').join(' ') || r.sd_name;
    const lead = c1 ? `<span class="lead-chip">${c1.name} <span class="cand-party">${c1.jd_name || ''}</span> ${fmt1(c1.share_pct)}%</span>` : '—';
    const second = c2 ? `${c2.name} ${fmt1(c2.share_pct)}%` : '—';
    return `<tr>
      <td>${r.sg_type_label}</td>
      <td>${r.sd_name} ${place === r.sd_name ? '' : place}</td>
      <td>${lead}</td>
      <td>${second}</td>
      <td class="num">${fmt1(r.rank1_minus_rank2_pp)}pp</td>
      <td class="num">${fmt1(r.progress_pct)}%</td>
    </tr>`;
  }).join('');

  root.innerHTML = `<table class="other">
    <thead><tr><th>선거</th><th>지역</th><th>1위</th><th>2위</th><th>격차</th><th>개표</th></tr></thead>
    <tbody>${rows}</tbody>
  </table>`;
}

// 개표일 이전엔 보관용/테스트 데이터가 실제 결과처럼 보이지 않도록 대기 화면.
// ?preview=1 이면 가드 우회(내부 확인용).
function showWaiting(msg) {
  document.getElementById('live-badge').hidden = true;
  document.getElementById('hero-turnout').innerHTML = `대기<span class="pct"></span>`;
  document.getElementById('hero-turnout-meta').textContent = msg;
  document.getElementById('hero-progress').innerHTML = `—<span class="pct"></span>`;
  document.getElementById('hero-progress-meta').textContent = '투표 마감(18시) 후 개표 시작';
  document.getElementById('hero-early').innerHTML = `—<span class="pct"></span>`;
  document.getElementById('chief-races').innerHTML = `<div class="state-empty">${msg}</div>`;
  document.getElementById('other-races').innerHTML = '';
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
  const [cur, prediction, parties] = await Promise.all([
    loadJSON(PATHS.current), loadJSON(PATHS.prediction), loadJSON(PATHS.parties),
  ]);
  if (!cur) {
    document.getElementById('chief-races').innerHTML =
      `<div class="state-empty">개표 데이터가 아직 없습니다. 6/3 18시 투표 마감 후 수집이 시작됩니다.</div>`;
    document.getElementById('other-races').innerHTML = '';
    return;
  }
  const predMap = (prediction && prediction.sido_dem_win_prob) || {};
  renderHero(cur);
  renderChiefRaces(cur, predMap, parties || {});
  renderOtherRaces(cur);
}

render();
setInterval(render, REFRESH_MS);
