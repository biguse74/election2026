// 당선 결과 페이지 — data/live_counting/current.json 기반.
// 실시간 개표 페이지(live.js)의 검증된 후보 카드 폼을 그대로 사용한다.
const PATHS = {
  current:   '../data/live_counting/current.json',
  prediction:'../data/prediction_sido_v2.json',
  parties:   '../data/parties.json',
  photos:    '../live/candidate_photos.json',
  cards:     '../data/candidate_cards.json',
  eduOrient: '../data/edu_orientation.json',
  covered:   '../data/newtamsa_covered.json',
};
let EDU_ORIENT = {};
let COVERED = null;
const DEM = '더불어민주당';
const CON = '국민의힘';
const REFRESH_MS = 60 * 1000;
const SIDO_ORDER = [
  '서울특별시', '부산광역시', '대구광역시', '인천광역시', '광주광역시',
  '대전광역시', '울산광역시', '세종특별자치시', '경기도', '강원특별자치도',
  '충청북도', '충청남도', '전북특별자치도', '전라남도', '경상북도',
  '경상남도', '제주특별자치도', '전남광주통합특별시',
];
const sidoIdx = sd => { const i = SIDO_ORDER.indexOf(sd); return i < 0 ? 99 : i; };

let PARTIES = {}, PHOTO_MAP = null;

async function loadJSON(p) {
  try { const r = await fetch(p + '?t=' + Date.now(), { cache: 'no-store' }); return r.ok ? await r.json() : null; }
  catch (e) { return null; }
}
const esc = s => String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
const fmt1 = v => (v == null || isNaN(v)) ? '—' : Number(v).toFixed(1);
const intComma = v => (v == null || isNaN(v)) ? '—' : Number(v).toLocaleString('ko-KR');
const partyColor = name => PARTIES[name] || '#888';
const partyShare = (race, party) => { const c = (race.candidates || []).find(x => x.jd_name === party); return c ? { share: c.share_pct, name: c.name } : null; };

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

// 후보 huboid 맵 (이름 → 기존 후보 카드 /#cand/{huboid}). 키 = 'type|sd|sgg|name' (사진맵과 동일).
let HUBOID = { by_full: {}, by_sd: {} };
function candHuboid(r, c) {
  const t = r.sg_type_code || '', sd = r.sd_name || '', sgg = r.sgg_name || sd, nm = (c.name || '').trim();
  const f = HUBOID.by_full || {}, s = HUBOID.by_sd || {};
  return f[`${t}|${sd}|${sgg}|${nm}`] || f[`${t}|${sd}|${sd}|${nm}`] || s[`${t}|${sd}|${nm}`] || null;
}
// 당선자 이름 → 메인 사이트 후보 카드(새 탭). huboid 없으면 일반 텍스트.
function nameLink(r, c, cls) {
  const hb = candHuboid(r, c), nm = esc(c.name) || '—';
  return hb
    ? `<a class="${cls} cand-link" href="/#cand/${esc(hb)}" target="_blank" rel="noopener">${nm}</a>`
    : `<span class="${cls}">${nm}</span>`;
}

// 표차·박빙
const marginVotes = r => { const c = r.candidates || []; return c.length < 2 ? null : Math.abs((c[0].votes || 0) - (c[1].votes || 0)); };
const isClose = r => { const pp = r.rank1_minus_rank2_pp; return pp != null && pp < 2.0 && (r.progress_pct || 0) >= 1; };

// 당선 판정: 확정(개표 99.5%↑)·확실·유력
function callResult(r) {
  const c = r.candidates || []; const c1 = c[0]; if (!c1) return null;
  const prog = r.progress_pct || 0;
  const v1 = c1.votes || 0, v2 = c[1] ? (c[1].votes || 0) : 0;
  const margin = v1 - v2;
  if (margin <= 0 && prog < 99.5) return null;
  if (prog >= 99.5 && margin > 0) return { cls: 'call-fix', label: '당선' };
  if (prog < 30) return null;
  const counted = r.valid_votes || c.reduce((s, x) => s + (x.votes || 0), 0);
  const remaining = prog > 0 ? counted * (100 - prog) / prog : Infinity;
  if (prog >= 50 && margin > remaining) return { cls: 'call-win', label: '당선 확실' };
  if (margin > remaining * 0.6) return { cls: 'call-lead', label: '당선 유력' };
  return null;
}

function classifyRace(race, demProb) {
  const dem = partyShare(race, DEM), con = partyShare(race, CON);
  const prog = race.progress_pct || 0;
  const actualMargin = (dem && con) ? (dem.share - con.share) : null;
  if (prog < 5) return { verdict: 'none', label: '개표 초반', actualMargin };
  if (demProb == null) return { verdict: 'none', label: '예측 없음', actualMargin };
  if (actualMargin == null) return { verdict: 'none', label: '양자 비교 불가', actualMargin };
  const predDem = demProb >= 50, actualDem = actualMargin > 0;
  const confident = demProb >= 80 || demProb <= 20, tossup = demProb > 35 && demProb < 65;
  if (predDem !== actualDem) return { verdict: 'upset', label: '이변 — 예측과 반대', actualMargin };
  if (tossup) return { verdict: 'band', label: '접전 예측 적중', actualMargin };
  if (confident) return { verdict: 'hit', label: '예측 적중', actualMargin };
  return { verdict: 'hit', label: '예측 부합', actualMargin };
}
const predText = p => p == null ? '—' : (p >= 50 ? `민주 ${Math.round(p)}%` : `국힘 ${Math.round(100 - p)}%`);
const marginText = m => { if (m == null) return '—'; return `${m > 0 ? '민주' : '국힘'} +${Math.abs(m).toFixed(1)}pp`; };

function candRow(c, isLead) {
  const color = partyColor(c.jd_name);
  const w = Math.max(0, Math.min(100, c.share_pct || 0));
  return `<div class="cand-row ${isLead ? 'cand-rank1' : ''}">
    ${candPhotoImg(c._race, c, 'cand-photo')}
    <span class="cand-dot" style="background:${color}"></span>
    ${nameLink(c._race, c, 'cand-name')}
    <span class="cand-party">${esc(c.jd_name || '')}</span>
    <span class="cand-bar-wrap"><span class="cand-bar" style="width:${w}%;background:${color}"></span></span>
    <span class="cand-share">${fmt1(c.share_pct)}%</span>
  </div>`;
}

// 후보 카드. opts.place(부가 지명) / opts.predMap(시도지사 예측)
function resultCard(race, opts = {}) {
  const cands = (race.candidates || []).slice(0, 2).map(c => ({ ...c, _race: race }));
  const call = callResult(race);
  const callHTML = call ? `<span class="call-chip ${call.cls}">${call.label}</span>` : '';
  // 제목: 선거구(시군구)가 있는 선거(재보궐2·기초단체장4·기초의원6)는 선거구명(+시도), 시도지사·교육감은 시도명
  const hasSgg = ['2', '4', '6'].includes(String(race.sg_type_code));
  const title = opts.title || (hasSgg ? (race.sgg_name || race.sd_name) : race.sd_name);
  const whereTxt = hasSgg ? race.sd_name : '';
  const where = whereTxt ? `<span class="rs-where">${esc(whereTxt)}</span>` : '';

  // 하단 비교줄
  let cmp = '';
  const mv = marginVotes(race), close = isClose(race);
  const mvText = mv != null ? ` <span class="rc-margin ${close ? 'margin-close' : ''}">${intComma(mv)}표차${close ? ' · 박빙' : ''}</span>` : '';
  if (opts.predMap) {
    const demProb = opts.predMap[race.sd_name] != null ? opts.predMap[race.sd_name] : null;
    const cls = classifyRace(race, demProb);
    if (cls.actualMargin != null) {
      const predPart = demProb != null
        ? `<span class="rc-item">뉴탐사 예측 <b>${predText(demProb)}</b> 당선확률</span>`
        : `<span class="rc-item">예측 <b>—</b></span>`;
      cmp = `<span class="rc-item">실제 <b>${marginText(cls.actualMargin)}</b>${mvText}</span>${predPart}
        <span class="rc-verdict v-${cls.verdict}">${cls.label}</span>`;
    } else {
      cmp = `<span class="rc-item">개표 진행 ${fmt1(race.progress_pct)}%</span>`;
    }
  } else if (mv != null) {
    const c1 = cands[0], c2 = cands[1];
    const lead = (c1 && c2) ? `${esc(c1.jd_name || c1.name)} +${fmt1(race.rank1_minus_rank2_pp)}pp` : '';
    cmp = `<span class="rc-item">실제 <b>${lead}</b>${mvText}</span>`;
  }

  return `<div class="race-card">
    <div class="race-card-head">
      <span class="race-sido">${esc(title)}${where}</span>
      <span class="race-progress">${callHTML}개표 <b>${fmt1(race.progress_pct)}%</b></span>
    </div>
    ${cands.map((c, i) => candRow(c, i === 0)).join('')}
    ${cmp ? `<div class="race-compare">${cmp}</div>` : ''}
  </div>`;
}

// ── 당선 집계 ──
function tallyByLeader(races) {
  let dem = 0, con = 0, etc = 0;
  for (const r of races) {
    if (!(r.candidates || []).length) continue;
    const p = r.candidates[0].jd_name;
    if (p === DEM) dem++; else if (p === CON) con++; else etc++;
  }
  return { dem, con, etc, total: dem + con + etc };
}

function renderHero(cur, chiefs, edu, repoll, bh) {
  const nat = cur.turnout && cur.turnout.national;
  const polled = (cur.polled_at || '').replace('T', ' ').slice(0, 16);
  const ld = document.getElementById('rs-livedot');
  if (ld) ld.hidden = (cur.phase === 'final');
  document.getElementById('rs-sub').innerHTML =
    `${cur.phase === 'final' ? '<b>최종 집계</b>' : '<b>개표 진행 중</b>'} · 전국 투표율 <b>${nat ? fmt1(nat.turnout_pct) : '—'}%</b> · 갱신 ${esc(polled)} (1분마다 자동)`;

  const ct = tallyByLeader(chiefs);
  document.getElementById('sb-dem').textContent = ct.dem;
  document.getElementById('sb-con').textContent = ct.con;
  const tot = ct.total || 1;
  document.getElementById('seat-bar').innerHTML =
    `<i class="s-dem" style="width:${ct.dem / tot * 100}%"></i>` +
    `<i class="s-etc" style="width:${ct.etc / tot * 100}%"></i>` +
    `<i class="s-con" style="width:${ct.con / tot * 100}%"></i>`;
  document.getElementById('seat-legend').innerHTML =
    `<span><i style="background:var(--dem)"></i>민주 ${ct.dem}</span>` +
    `<span><i style="background:#6b6b78"></i>그외 ${ct.etc}</span>` +
    `<span><i style="background:var(--con)"></i>국힘 ${ct.con}</span>` +
    `<span style="margin-left:auto">집계 ${ct.total}곳</span>`;

  const bt = tallyByLeader(bh), rt = tallyByLeader(repoll);
  const tile = (name, t, sub) => `<div class="ot"><div class="ot-name">${name}</div>
    <div class="ot-fig"><span class="d">민주 ${t.dem}</span> · <span class="c">국힘 ${t.con}</span>${t.etc ? ` · <span class="e">그외 ${t.etc}</span>` : ''}</div>
    <div class="ot-sub">${sub}</div></div>`;
  document.getElementById('office-tiles').innerHTML =
    tile('광역단체장', ct, `집계 ${ct.total}곳`) +
    tile('기초단체장', bt, `집계 ${bt.total}곳`) +
    tile('국회의원 재보궐', rt, `집계 ${rt.total}곳`) +
    `<div class="ot"><div class="ot-name">교육감</div><div class="ot-fig"><span class="e">${edu.length}곳</span></div><div class="ot-sub">정당 없는 단독 선출</div></div>`;
}

// 역대 광역단체장(시도지사) 정당 계열별 당선 — 중앙선관위 개표결과 기반(계열 통합).
//   민주 계열=새천년민주당·민주당·열린우리당·새정치민주연합·더불어민주당
//   보수 계열=한나라당·새누리당·자유한국당·국민의힘 / 그 외=자민련·자유선진당·무소속 등
const HIST_CHIEF = [
  { year: 2002, round: 3, total: 16, dem: 4, con: 11, etc: 1 },
  { year: 2006, round: 4, total: 16, dem: 3, con: 12, etc: 1 },
  { year: 2010, round: 5, total: 16, dem: 7, con: 6, etc: 3 },
  { year: 2014, round: 6, total: 17, dem: 9, con: 8, etc: 0 },
  { year: 2018, round: 7, total: 17, dem: 14, con: 2, etc: 1 },
  { year: 2022, round: 8, total: 17, dem: 5, con: 12, etc: 0 },
];

function renderHistory(chiefs) {
  const cur = tallyByLeader(chiefs);
  const rows = HIST_CHIEF.concat([{ year: 2026, round: 9, total: cur.total, dem: cur.dem, con: cur.con, etc: cur.etc, now: true }]);
  const maxTotal = Math.max(...rows.map(r => r.total)) || 17;
  document.getElementById('hist-rows').innerHTML = rows.map(r => {
    const seg = (cls, n) => n ? `<i class="${cls}" style="width:${n / maxTotal * 100}%">${n}</i>` : '';
    return `<div class="hist-row ${r.now ? 'now' : ''}">
      <div class="hist-yr"><b>${r.year}</b><small>${r.round}회 · ${r.total}곳</small></div>
      <div class="hist-bar">${seg('h-dem', r.dem)}${seg('h-etc', r.etc)}${seg('h-con', r.con)}</div>
    </div>`;
  }).join('');
}

function renderGrid(id, races, opts) {
  const el = document.getElementById(id);
  if (!races.length) { el.innerHTML = '<div class="state-empty">아직 개표 데이터가 없습니다.</div>'; return; }
  el.innerHTML = races.map(r => resultCard(r, opts)).join('');
}

// 기초의원(중선거구) — 뉴탐사가 주목한 후보 한 명의 결과만 보여 주는 카드
function memberCard(race, name) {
  const cands = race.candidates || [];
  const c = cands.find(x => x.name === name);
  if (!c) return '';
  const color = partyColor(c.jd_name);
  const w = Math.max(0, Math.min(100, c.share_pct || 0));
  const cc = { ...c, _race: race };
  return `<div class="race-card">
    <div class="race-card-head">
      <span class="race-sido">${esc(race.sgg_name || '')}<span class="rs-where">${esc(race.sd_name)} · 기초의원</span></span>
      <span class="race-progress">개표 <b>${fmt1(race.progress_pct)}%</b></span>
    </div>
    <div class="cand-row cand-rank1">
      ${candPhotoImg(race, cc, 'cand-photo')}
      <span class="cand-dot" style="background:${color}"></span>
      ${nameLink(race, cc, 'cand-name')}
      <span class="cand-party">${esc(c.jd_name || '')}</span>
      <span class="cand-bar-wrap"><span class="cand-bar" style="width:${w}%;background:${color}"></span></span>
      <span class="cand-share">${fmt1(c.share_pct)}%</span>
    </div>
    <div class="race-compare"><span class="rc-item">중선거구(여러 명 당선) · 현재 <b>${c.current_rank}위 / ${cands.length}명</b></span></div>
  </div>`;
}

// 뉴탐사 보도 지역 — 페이지 기본 순서(시도지사3→재보궐2→기초단체장4→기초의원6)로 정렬
function renderCovered(cur, covered, predMap) {
  const block = document.getElementById('sec-covered');
  const el = document.getElementById('covered-grid');
  if (!block || !el) return;
  const list = (covered && covered.races) || [];
  const ORD = { '3': 0, '2': 1, '4': 2, '6': 3 };
  const items = list.map(e => {
    const t = String(e.sgType);
    const r = t === '3'
      ? cur.races.find(x => String(x.sg_type_code) === '3' && x.sd_name === e.sd)
      : cur.races.find(x => String(x.sg_type_code) === t && x.sd_name === e.sd && x.sgg_name === e.sgg);
    return { e, r };
  }).filter(x => x.r);
  if (!items.length) { block.style.display = 'none'; return; }
  items.sort((a, b) =>
    (ORD[String(a.e.sgType)] - ORD[String(b.e.sgType)]) ||
    (sidoIdx(a.r.sd_name) - sidoIdx(b.r.sd_name)) ||
    (a.r.sgg_name || '').localeCompare(b.r.sgg_name || '', 'ko'));
  el.innerHTML = items.map(({ e, r }) => {
    if (String(e.sgType) === '6' && e.name) return memberCard(r, e.name);
    return resultCard(r, String(e.sgType) === '3' ? { predMap } : {});
  }).join('');
  document.getElementById('cnt-covered').textContent = `${items.length}곳`;
  block.style.display = '';
}

// 정당별 실제 당선자 수 — 큰 숫자(방송 가독성) + 가로 막대
function labeledSeatBar(t) {
  const tot = t.total || 1;
  return `<div class="bar-counts">
      <div class="bc dem"><b>${t.dem}</b><span>더불어민주당</span></div>
      ${t.etc ? `<div class="bc etc"><b>${t.etc}</b><span>그 외</span></div>` : ''}
      <div class="bc con"><b>${t.con}</b><span>국민의힘</span></div>
    </div>
    <div class="seat-bar labeled">
      <i class="s-dem" style="width:${t.dem / tot * 100}%"></i>
      <i class="s-etc" style="width:${t.etc / tot * 100}%"></i>
      <i class="s-con" style="width:${t.con / tot * 100}%"></i>
    </div>
    <div class="bar-sub">당선자 <b>${t.total}</b>명 · 정당별 실제 당선자 수</div>`;
}

// 교육감 성향(진보/보수) 집계 바 — 당선자 기준
function renderEduTally(eduRaces) {
  const el = document.getElementById('edu-tally');
  if (!el) return;
  let prog = 0, cons = 0, etc = 0;
  for (const r of eduRaces) {
    const w = (r.candidates || [])[0]; if (!w) continue;
    const o = EDU_ORIENT[w.name];
    if (o === '진보') prog++; else if (o === '보수') cons++; else etc++;
  }
  const tot = prog + cons + etc || 1;
  const BLUE = '#2b6cb0', RED = '#c0392b';
  el.innerHTML = `<div class="bar-counts">
      <div class="bc"><b style="color:${BLUE}">${prog}</b><span>진보</span></div>
      ${etc ? `<div class="bc etc"><b>${etc}</b><span>그 외</span></div>` : ''}
      <div class="bc con"><b style="color:${RED}">${cons}</b><span>보수</span></div>
    </div>
    <div class="seat-bar labeled">
      <i style="width:${prog / tot * 100}%;background:${BLUE}"></i>
      <i style="width:${etc / tot * 100}%;background:#8a8a96"></i>
      <i style="width:${cons / tot * 100}%;background:${RED}"></i>
    </div>
    <div class="bar-sub">진보 <b>${prog}</b> : 보수 <b>${cons}</b>${etc ? ` · 그 외 ${etc}` : ''} · 당선 ${tot}곳 (교육단체 추천·언론 분류 기준)</div>`;
}

function renderBH(bh) {
  document.getElementById('bh-tally').innerHTML = labeledSeatBar(tallyByLeader(bh));
  const byS = {};
  for (const r of bh) (byS[r.sd_name] = byS[r.sd_name] || []).push(r);
  const order = Object.keys(byS).sort((a, b) => sidoIdx(a) - sidoIdx(b));
  document.getElementById('bh-sido-wrap').innerHTML = order.map(sd => {
    const races = byS[sd].sort((a, b) => (a.sgg_name || '').localeCompare(b.sgg_name || '', 'ko'));
    const t = tallyByLeader(races);
    const chips = races.map(r => {
      const c1 = (r.candidates || [])[0]; if (!c1) return '';
      const call = callResult(r);
      const fix = call && call.cls === 'call-fix' ? '<span class="wc-fix">당선</span>' : '';
      return `<div class="wchip ${isClose(r) ? 'close' : ''}" style="border-left-color:${partyColor(c1.jd_name)}">
        ${candPhotoImg(r, c1, 'wc-photo')}
        <span class="wc-place">${esc(r.sgg_name || '')}</span>
        ${nameLink(r, c1, 'wc-name')}${fix}
        <span class="wc-share">${fmt1(c1.share_pct)}%</span></div>`;
    }).join('');
    return `<div class="bh-sido"><div class="bh-sido-h">${esc(sd)}
      <span class="bh-sido-tally">민주 ${t.dem} · 국힘 ${t.con}${t.etc ? ` · 그외 ${t.etc}` : ''}</span></div>
      <div class="chip-grid">${chips}</div></div>`;
  }).join('');
}

let _huboidLoaded = false;
async function render() {
  const [cur, prediction, parties, photos, huboids, eduOri, covered] = await Promise.all([
    loadJSON(PATHS.current), loadJSON(PATHS.prediction), loadJSON(PATHS.parties), loadJSON(PATHS.photos),
    _huboidLoaded ? Promise.resolve(null) : loadJSON(PATHS.cards),
    _huboidLoaded ? Promise.resolve(null) : loadJSON(PATHS.eduOrient),
    _huboidLoaded ? Promise.resolve(COVERED) : loadJSON(PATHS.covered),
  ]);
  if (!cur || !cur.races) { document.getElementById('rs-sub').textContent = '데이터를 불러오지 못했습니다.'; return; }
  if (huboids) { HUBOID = huboids; _huboidLoaded = true; }
  if (eduOri) EDU_ORIENT = eduOri.by_name || {};
  if (covered) COVERED = covered;
  PARTIES = parties || {};
  PHOTO_MAP = photos || { by_full: {}, by_sd: {} };
  const predMap = (prediction && prediction.sido_dem_win_prob) || {};

  const byType = t => cur.races.filter(r => String(r.sg_type_code) === t);
  const chiefs = byType('3').sort((a, b) => sidoIdx(a.sd_name) - sidoIdx(b.sd_name));
  const edu = byType('11').sort((a, b) => sidoIdx(a.sd_name) - sidoIdx(b.sd_name));
  const repoll = byType('2').sort((a, b) => (b.progress_pct || 0) - (a.progress_pct || 0));
  const bh = byType('4');

  renderHero(cur, chiefs, edu, repoll, bh);
  renderCovered(cur, COVERED, predMap);
  renderHistory(chiefs);
  renderGrid('grid-chief', chiefs, { predMap });
  renderEduTally(edu);
  renderGrid('grid-edu', edu, {});
  renderGrid('grid-repoll', repoll, {});
  renderBH(bh);

  document.getElementById('cnt-chief').textContent = `${chiefs.length}곳`;
  document.getElementById('cnt-edu').textContent = `${edu.length}곳`;
  document.getElementById('cnt-repoll').textContent = `${repoll.length}곳`;
  document.getElementById('cnt-bh').textContent = `${bh.length}곳`;
  document.getElementById('rs-foot-meta').textContent = `갱신 ${(cur.polled_at || '').replace('T', ' ').slice(0, 16)}.`;
  document.getElementById('sec-edu').style.display = edu.length ? '' : 'none';
  document.getElementById('sec-repoll').style.display = repoll.length ? '' : 'none';
  document.getElementById('sec-bh').style.display = bh.length ? '' : 'none';
}

render();
setInterval(render, REFRESH_MS);
