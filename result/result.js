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
  council:   '../data/live_counting/council_seats.json',
  councilCands: '../data/live_counting/council_candidates.json',
};
let EDU_ORIENT = {};
let COVERED = null;
let PRED_OPP = {};  // 시도지사 예측 상대후보(이름·정당) — 예: 전북 김관영(국힘)
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
  if (prog >= 50 && margin > remaining * 0.7) return { cls: 'call-win', label: '당선 확실' };  // 2위가 남은표 85%↑ 가져가야 역전
  if (margin > remaining * 0.4) return { cls: 'call-lead', label: '당선 유력' };  // 2위가 남은표 70%↑ 필요
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
  let color = partyColor(c.jd_name);
  let partyHTML = esc(c.jd_name || '');
  // 교육감(정당 없음) → 정당명 자리에 성향(진보/보수) 표시 + 색
  if (c._race && String(c._race.sg_type_code) === '11') {
    const o = EDU_ORIENT[c.name];
    if (o === '보수') { color = '#c0392b'; partyHTML = '<b style="color:#c0392b">보수</b>'; }
    else if (o === '진보') { color = '#2b6cb0'; partyHTML = '<b style="color:#2b6cb0">진보</b>'; }
    else { color = '#8a8a96'; partyHTML = ''; }  // 교육감은 기본이 무소속 → 미분류는 라벨 없음
  }
  const w = Math.max(0, Math.min(100, c.share_pct || 0));
  return `<div class="cand-row ${isLead ? 'cand-rank1' : ''}">
    ${candPhotoImg(c._race, c, 'cand-photo')}
    <span class="cand-dot" style="background:${color}"></span>
    ${nameLink(c._race, c, 'cand-name')}
    <span class="cand-party">${partyHTML}</span>
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
  const t = String(race.sg_type_code);
  const hasSgg = ['2', '4', '6'].includes(t);
  const title = opts.title || (hasSgg ? (race.sgg_name || race.sd_name) : race.sd_name);
  const whereTxt = t === '11' ? '교육감' : (hasSgg ? race.sd_name : '');  // 교육감은 시장과 구분되게 표시
  const where = whereTxt ? `<span class="rs-where">${esc(whereTxt)}</span>` : '';

  // 하단 비교줄
  let cmp = '';
  const mv = marginVotes(race), close = isClose(race);
  const mvText = mv != null ? ` <span class="rc-margin ${close ? 'margin-close' : ''}">${intComma(mv)}표차${close ? ' · 박빙' : ''}</span>` : '';
  if (opts.predMap) {
    const demProb = opts.predMap[race.sd_name] != null ? opts.predMap[race.sd_name] : null;
    const cls = classifyRace(race, demProb);
    if (cls.actualMargin != null) {
      const opp = PRED_OPP[race.sd_name];
      const predLabel = (demProb != null && demProb < 50 && opp)
        ? `${esc(opp.name)}(${esc(opp.party)}) ${Math.round(100 - demProb)}%`
        : predText(demProb);
      const predPart = demProb != null
        ? `<span class="rc-item">뉴탐사 예측 <b>${predLabel}</b> 당선확률</span>`
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

function renderHero(cur, chiefs, edu, repoll, bh, council) {
  const nat = cur.turnout && cur.turnout.national;
  const polled = (cur.polled_at || '').replace('T', ' ').slice(0, 16);
  const ld = document.getElementById('rs-livedot');
  if (ld) ld.hidden = (cur.phase === 'final');
  // '최종 집계'는 단독 1인 선출이 모두 사실상 확정(99.5%↑)일 때만. 일부 미확정이면 '개표 집계'.
  const singles = (cur.races || []).filter(r => ['2', '3', '4', '11'].includes(String(r.sg_type_code)));
  const allFinal = singles.length > 0 && singles.every(r => (r.progress_pct || 0) >= 99.5);
  const phaseLabel = cur.phase === 'final'
    ? (allFinal ? '최종 집계' : '개표 집계 (일부 선거구 진행)')
    : '개표 진행 중';
  document.getElementById('rs-sub').innerHTML =
    `<b>${phaseLabel}</b> · 전국 투표율 <b>${nat ? fmt1(nat.turnout_pct) : '—'}%</b> · 갱신 ${esc(polled)} (1분마다 자동)`;

  const ct = tallyByLeader(chiefs);        // 시도지사
  const bt = tallyByLeader(bh);            // 기초단체장
  const rt = tallyByLeader(repoll);        // 국회의원 재보궐
  const c5 = council?.offices?.['5'] ? _partyTally(council.offices['5'].party) : { dem: 0, con: 0, etc: 0, total: 0 };
  const c6 = council?.offices?.['6'] ? _partyTally(council.offices['6'].party) : { dem: 0, con: 0, etc: 0, total: 0 };
  const c8 = council?.offices?.['8'] ? _partyTally(council.offices['8'].party) : { dem: 0, con: 0, etc: 0, total: 0 };
  const c9 = council?.offices?.['9'] ? _partyTally(council.offices['9'].party) : { dem: 0, con: 0, etc: 0, total: 0 };
  // 광역의원·기초의원 = 지역구 + 비례 합산(진짜 총의석)
  const sum2 = (a, b) => ({ dem: a.dem + b.dem, con: a.con + b.con, etc: a.etc + b.etc, total: a.total + b.total });
  const cMetro = sum2(c5, c8);   // 광역의원(지역구+비례)
  const cBasic = sum2(c6, c9);   // 기초의원(지역구+비례)
  // 헤드라인 = 전체 선출직 당선자 합산(교육감은 비정당이라 제외). 국민의 총선택.
  const grand = {
    dem: ct.dem + bt.dem + rt.dem + cMetro.dem + cBasic.dem,
    con: ct.con + bt.con + rt.con + cMetro.con + cBasic.con,
    etc: ct.etc + bt.etc + rt.etc + cMetro.etc + cBasic.etc,
  };
  grand.total = grand.dem + grand.con + grand.etc;
  const tot = grand.total || 1;
  const pc = n => (n / tot * 100).toFixed(1);
  document.getElementById('sb-dem').textContent = intComma(grand.dem);
  document.getElementById('sb-con').textContent = intComma(grand.con);
  const dpct = document.getElementById('sb-dem-pct'), cpct = document.getElementById('sb-con-pct');
  if (dpct) dpct.textContent = `${pc(grand.dem)}%`;
  if (cpct) cpct.textContent = `${pc(grand.con)}%`;
  const mid = document.getElementById('sb-mid');
  if (mid) mid.innerHTML = `전체 당선자<br><b style="color:rgba(255,255,255,0.8)">${intComma(grand.total)}명</b>`;
  document.getElementById('seat-bar').innerHTML =
    `<i class="s-dem" style="width:${grand.dem / tot * 100}%"></i>` +
    `<i class="s-etc" style="width:${grand.etc / tot * 100}%"></i>` +
    `<i class="s-con" style="width:${grand.con / tot * 100}%"></i>`;
  document.getElementById('seat-legend').innerHTML =
    `<span><i style="background:var(--dem)"></i>민주 ${intComma(grand.dem)} (${pc(grand.dem)}%)</span>` +
    `<span><i style="background:#6b6b78"></i>그외 ${intComma(grand.etc)} (${pc(grand.etc)}%)</span>` +
    `<span><i style="background:var(--con)"></i>국힘 ${intComma(grand.con)} (${pc(grand.con)}%)</span>` +
    `<span style="margin-left:auto">시도지사·단체장·지방의원(지역구+비례)·재보궐 합산 · 교육감(비정당) 제외</span>`;

  const tile = (name, t, sub) => {
    const tt = t.total || 1;
    return `<div class="ot"><div class="ot-name">${name}</div>
      <div class="ot-fig"><span class="d">민주 ${intComma(t.dem)}</span> · <span class="c">국힘 ${intComma(t.con)}</span>${t.etc ? ` · <span class="e">그외 ${intComma(t.etc)}</span>` : ''}</div>
      <div class="ot-sub">${sub} · 민주 ${(t.dem / tt * 100).toFixed(0)}%</div></div>`;
  };
  // 교육감 진보/보수 당선 집계(성향 분류 기준)
  let eduProg = 0, eduCons = 0, eduEtc = 0;
  for (const r of edu) { const w = (r.candidates || [])[0]; if (!w) continue; const o = EDU_ORIENT[w.name]; if (o === '진보') eduProg++; else if (o === '보수') eduCons++; else eduEtc++; }
  const eduFig = `<span class="d">진보 ${eduProg}</span> · <span class="c">보수 ${eduCons}</span>${eduEtc ? ` · <span class="e">그외 ${eduEtc}</span>` : ''}`;
  document.getElementById('office-tiles').innerHTML =
    tile('광역단체장', ct, `${ct.total}곳`) +
    tile('광역의원', cMetro, `${cMetro.total}석 = 지역구 ${c5.total}+비례 ${c8.total}`) +
    tile('기초단체장', bt, `${bt.total}곳`) +
    tile('기초의원', cBasic, `${cBasic.total}석 = 지역구 ${c6.total}+비례 ${c9.total}`) +
    tile('국회의원 재보궐', rt, `${rt.total}곳`) +
    `<div class="ot"><div class="ot-name">교육감</div><div class="ot-fig">${eduFig}</div><div class="ot-sub">${edu.length}곳 · 비정당(진보/보수)</div></div>`;
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
  const ORD = { '3': 0, '11': 1, '2': 2, '4': 3, '6': 4 };  // 시도지사·교육감·재보궐·기초단체장·기초의원
  const items = list.map(e => {
    const t = String(e.sgType);
    const r = e.sgg
      ? cur.races.find(x => String(x.sg_type_code) === t && x.sd_name === e.sd && x.sgg_name === e.sgg)
      : cur.races.find(x => String(x.sg_type_code) === t && x.sd_name === e.sd);
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
  const pc = n => (n / tot * 100).toFixed(1);
  return `<div class="bar-counts">
      <div class="bc dem"><b>${t.dem}</b><em class="bc-pct">${pc(t.dem)}%</em><span>더불어민주당</span></div>
      ${t.etc ? `<div class="bc etc"><b>${t.etc}</b><em class="bc-pct">${pc(t.etc)}%</em><span>그 외</span></div>` : ''}
      <div class="bc con"><b>${t.con}</b><em class="bc-pct">${pc(t.con)}%</em><span>국민의힘</span></div>
    </div>
    <div class="seat-bar labeled">
      <i class="s-dem" style="width:${t.dem / tot * 100}%"></i>
      <i class="s-etc" style="width:${t.etc / tot * 100}%"></i>
      <i class="s-con" style="width:${t.con / tot * 100}%"></i>
    </div>
    <div class="bar-sub">당선자 <b>${t.total}</b>명 · 민주 <b>${pc(t.dem)}%</b> · 국힘 <b>${pc(t.con)}%</b>${t.etc ? ` · 그 외 ${pc(t.etc)}%` : ''}</div>`;
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
// 광역의원·기초의원 정당별 의석(지역구) — council_seats.json 기반
const _PARTY_ORDER = ['더불어민주당', '국민의힘', '조국혁신당', '진보당', '정의당', '개혁신당', '녹색당', '무소속'];
function _partyTally(party) {
  // 큰 바용: 민주/국힘/그외
  const dem = party['더불어민주당'] || 0, con = party['국민의힘'] || 0;
  const total = Object.values(party).reduce((a, b) => a + b, 0);
  return { dem, con, etc: total - dem - con, total };
}
function _mergeParty(a, b) {
  const out = { ...(a || {}) };
  for (const [k, v] of Object.entries(b || {})) out[k] = (out[k] || 0) + v;
  return out;
}
function renderCouncilOffice(elId, office, prOffice) {
  const el = document.getElementById(elId);
  if (!el || !office) return;
  // 정당별 의석 = 지역구 + 비례 합산(전체 정당별 통계)
  const party = _mergeParty(office.party, prOffice?.party);
  const t = _partyTally(party);
  const totSeats = t.total || 1;
  const dSeats = office.total_seats || 0, pSeats = prOffice?.total_seats || 0;
  // 상세 정당 칩(0이 아닌 정당만, 정해진 순서) — 의석수 + 점유율%
  const chips = _PARTY_ORDER.filter(p => party[p]).map(p =>
    `<span class="pchip" style="border-color:${partyColor(p)}"><i style="background:${partyColor(p)}"></i>${esc(p)} <b>${party[p]}</b> <em>${(party[p] / totSeats * 100).toFixed(1)}%</em></span>`).join('');
  // 시도별 미니바(지역구 기준 — 광역비례는 통합특별시라 시도 분할 불가)
  const sidos = Object.keys(office.by_sido).sort((a, b) => sidoIdx(a) - sidoIdx(b));
  const rows = sidos.map(sd => {
    const p = office.by_sido[sd];
    const st = _partyTally(p);
    const tot = st.total || 1;
    return `<div class="cs-row"><span class="cs-sd">${esc(sd)}</span>
      <span class="cs-bar"><i class="s-dem" style="width:${st.dem / tot * 100}%"></i><i class="s-etc" style="width:${st.etc / tot * 100}%"></i><i class="s-con" style="width:${st.con / tot * 100}%"></i></span>
      <span class="cs-num"><b class="d">${st.dem}</b>·<b class="c">${st.con}</b>${st.etc ? `·<b class="e">${st.etc}</b>` : ''}</span></div>`;
  }).join('');
  const splitNote = prOffice ? `<div class="cs-split" style="font-size:0.78rem;color:var(--muted,#666);margin:6px 0 2px;font-weight:700">정당별 의석 = 지역구 ${dSeats} + 비례 ${pSeats} = <b style="color:var(--ink,#1a1a1a)">${dSeats + pSeats}석</b> 합산</div>` : '';
  el.innerHTML = `${labeledSeatBar(t)}${splitNote}
    <div class="pchips">${chips}</div>
    <div class="cs-sido"><div class="cs-sido-h">시도별 (지역구 기준 · 민주·국힘·그외)</div>${rows}</div>`;
}
function renderCouncil(council) {
  const sec = document.getElementById('sec-council');
  if (!sec) return;
  if (!council || !council.offices) { sec.style.display = 'none'; return; }
  sec.style.display = '';
  renderCouncilOffice('council-sido', council.offices['5'], council.offices['8']);
  renderCouncilOffice('council-basic', council.offices['6'], council.offices['9']);
  const o5 = council.offices['5'], o6 = council.offices['6'];
  const o8 = council.offices['8'], o9 = council.offices['9'];
  if (o5) document.getElementById('cnt-council-sido').textContent =
    `${o5.total_seats + (o8?.total_seats || 0)}석` + (o8 ? ` (지역구 ${o5.total_seats}+비례 ${o8.total_seats})` : '');
  if (o6) document.getElementById('cnt-council-basic').textContent =
    `${o6.total_seats + (o9?.total_seats || 0)}석` + (o9 ? ` (지역구 ${o6.total_seats}+비례 ${o9.total_seats})` : '');
  const when = (council.generated_at || '').replace('T', ' ').slice(0, 16);
  const fm = document.getElementById('council-foot');
  if (fm) fm.textContent = `아래 상세는 지역구 기준 · 비례대표(광역 ${o8?.total_seats || 0}·기초 ${o9?.total_seats || 0}석, 헤어식 배분)는 상단 '전체 당선자'에 합산 · 경합=개표 상위, 무투표=등록후보 · 중앙선관위 · 집계 ${when}`;
}

// ── 당선자 검색 (전 직책: 시도지사·단체장·광역/기초의원·교육감·재보궐) ──
// SINGLE_IDX(단독선출, 60초마다 재생성) + COUNCIL_IDX(의원, 1회 지연 로드) → SEARCH_IDX
let SEARCH_IDX = [], SINGLE_IDX = [], COUNCIL_IDX = [];
let _searchWired = false;
const _WS_ORANK = { '시도지사': 0, '국회의원 재보궐': 1, '기초단체장': 2, '교육감': 3, '시도의원': 4, '기초의원': 5 };
const _eduColor = o => o === '보수' ? '#c0392b' : o === '진보' ? '#2b6cb0' : '#8a8a96';
function buildSearchIndex(cur) {
  const CUR_OFFICE = { '3': '시도지사', '4': '기초단체장', '11': '교육감', '2': '국회의원 재보궐' };
  const idx = [];
  // 단독 1인 선출(3·4·11·2)은 전 후보 색인 — 낙선 주요 후보도 검색되게(예: 하정우).
  // 광역·기초의원(5·6)은 양이 많아 검색창 첫 사용 시 지연 로드(ensureCouncilLoaded).
  for (const r of (cur.races || [])) {
    const t = String(r.sg_type_code);
    if (!CUR_OFFICE[t]) continue;
    const cs = r.candidates || [];
    if (!cs.length) continue;
    const winner = cs[0], runner = cs[1] || null;
    const oppOf = (c, won) => {
      const o = won ? runner : winner;
      if (!o || !o.name || o.name === c.name) return null;
      let ojd = o.jd_name || '';
      if (t === '11') ojd = EDU_ORIENT[o.name] || '';
      return { name: o.name, jd: ojd, share: o.share_pct };
    };
    cs.forEach((c, i) => {
      if (!c.name) return;
      const won = c.current_rank ? c.current_rank === 1 : i === 0;
      let jd = c.jd_name || '';
      if (t === '11') jd = EDU_ORIENT[c.name] || '';
      const mode = (cs.length < 2 && c.votes == null) ? '무투표' : null;
      idx.push({ name: c.name, jd, sd: r.sd_name || '', sgg: r.sgg_name || '', office: CUR_OFFICE[t], t,
                 hb: candHuboid(r, c), r: { sg_type_code: t, sd_name: r.sd_name, sgg_name: r.sgg_name },
                 votes: c.votes, share: c.share_pct, rank: c.current_rank || (i + 1), won, mode, opp: oppOf(c, won) });
    });
  }
  SINGLE_IDX = idx;
  SEARCH_IDX = SINGLE_IDX.concat(COUNCIL_IDX);
}
// 광역·기초의원 전 후보(당락 포함)를 검색 인덱스에 합침 — 검색창 첫 사용 시 1회 지연 로드.
let _councilLoading = null, _councilReady = false;
const _OFFICE_BY_T = { '5': '시도의원', '6': '기초의원' };
function ensureCouncilLoaded() {
  if (_councilLoading) return _councilLoading;
  _councilLoading = loadJSON(PATHS.councilCands).then(data => {
    const list = (data && data.cands) || [];
    COUNCIL_IDX = list.map(c => ({
      name: c.n, jd: c.j, sd: c.sd, sgg: c.sg, office: _OFFICE_BY_T[c.t] || '지방의원', t: c.t,
      hb: candHuboid({ sg_type_code: c.t, sd_name: c.sd, sgg_name: c.sg }, { name: c.n }),
      r: { sg_type_code: c.t, sd_name: c.sd, sgg_name: c.sg },
      votes: c.v, share: c.s, rank: c.r, won: !!c.w,
      mode: (c.v == null && c.w) ? '무투표' : null, seats: c.m, opp: null,
    }));
    SEARCH_IDX = SINGLE_IDX.concat(COUNCIL_IDX);
    _councilReady = true;
    return true;
  }).catch(() => { _councilReady = true; return false; });
  return _councilLoading;
}
function _wsColor(e) { return e.t === '11' ? _eduColor(e.jd) : partyColor(e.jd); }
// 검색 결과 한 줄(자유검색·분류검색 공용)
function _wsRow(e) {
  const color = _wsColor(e);
  const region = [e.sd, (e.sgg && e.sgg !== e.sd) ? e.sgg : ''].filter(Boolean).join(' ');
  const nm = e.hb
    ? `<a href="/#cand/${esc(e.hb)}" target="_blank" rel="noopener" class="ws-name cand-link">${esc(e.name)}</a>`
    : `<span class="ws-name">${esc(e.name)}</span>`;
  const party = e.jd ? `<span class="ws-party" style="color:${color}">${esc(e.jd)}</span>` : '';
  const photo = candPhotoImg(e.r, { name: e.name }, 'ws-photo');
  const badge = e.won
    ? `<span class="ws-badge won">당선</span>`
    : `<span class="ws-badge lost">낙선${e.rank ? ` ${e.rank}위` : ''}</span>`;
  let vt;
  if (e.mode === '무투표') vt = `<b class="ws-vt">무투표 당선</b>`;
  else if (e.votes != null) vt = `<b class="ws-vt">${intComma(e.votes)}표</b> (${fmt1(e.share)}%)`;
  else vt = '';
  let oppTxt = '';
  const op = e.opp;
  if (op && op.name) {  // 단독 1인 선출(시도지사·단체장·교육감·재보궐)만 상대후보 표시
    const oc = e.t === '11' ? _eduColor(op.jd) : partyColor(op.jd);
    const lbl = e.won ? '2위' : '당선';
    oppTxt = `${lbl} ${esc(op.name)}${op.jd ? `<i style="color:${oc};font-style:normal;font-weight:700"> ${esc(op.jd)}</i>` : ''}${op.share != null ? ` ${fmt1(op.share)}%` : ''}`;
  }
  const seatTxt = (e.seats && e.seats > 1) ? `정수 ${e.seats}명 선출` : '';  // 중선거구
  const l2 = [esc(region), vt, oppTxt, seatTxt].filter(Boolean).join('  ·  ');
  return `<div class="ws-row">${photo}<div class="ws-main">
    <div class="ws-l1">${badge}<span class="ws-dot" style="background:${color}"></span>${nm}<span class="ws-office">${esc(e.office)}</span>${party}</div>
    <div class="ws-l2">${l2}</div>
  </div></div>`;
}
function _wsFilters() {
  const v = id => { const el = document.getElementById(id); return el ? el.value : ''; };
  return { q: ((document.getElementById('ws-input') || {}).value || '').trim(), t: v('ws-type'), sd: v('ws-sido'), party: v('ws-party'), won: v('ws-won') };
}
const _WS_CAP = 120;
function runWinnerSearch() {
  const box = document.getElementById('ws-results');
  if (!box) return;
  const f = _wsFilters();
  if (!(f.q || f.t || f.sd || f.party || f.won)) {
    box.innerHTML = `<div class="ws-hint">이름·지역을 입력하거나, 아래 <b>분류 검색</b>(선거 종류·시도·정당·당락)으로 좁혀 보세요. 당선·낙선 후보 모두 나옵니다.</div>`;
    return;
  }
  const hits = SEARCH_IDX.filter(e => {
    if (f.q && !(e.name.includes(f.q) || e.sgg.includes(f.q) || e.sd.includes(f.q))) return false;
    if (f.t && e.t !== f.t) return false;
    if (f.sd && e.sd !== f.sd) return false;
    if (f.party && e.jd !== f.party) return false;
    if (f.won === 'win' && !e.won) return false;
    if (f.won === 'lose' && e.won) return false;
    return true;
  });
  // 직책 → 시도 → 선거구 → 당선우선 → 순위
  hits.sort((a, b) => (_WS_ORANK[a.office] - _WS_ORANK[b.office]) || (sidoIdx(a.sd) - sidoIdx(b.sd))
    || (a.sgg || '').localeCompare(b.sgg || '', 'ko') || ((a.won ? 0 : 1) - (b.won ? 0 : 1)) || ((a.rank || 99) - (b.rank || 99)));
  const total = hits.length, shown = hits.slice(0, _WS_CAP);
  if (!total) {
    if (!_councilReady) { box.innerHTML = `<div class="ws-hint">의원 후보 명단 불러오는 중…</div>`; ensureCouncilLoaded().then(runWinnerSearch); return; }
    box.innerHTML = `<div class="ws-hint">조건에 맞는 후보가 없습니다. 검색어나 분류를 바꿔 보세요.</div>`; return;
  }
  box.innerHTML = `<div class="ws-count">${intComma(total)}명${total > _WS_CAP ? ` · 상위 ${_WS_CAP}명 표시(조건을 좁혀 보세요)` : ''}${!_councilReady ? ' · 의원 명단 불러오는 중…' : ''}</div>` +
    shown.map(_wsRow).join('');
}
const _WS_TYPES = [['3', '시도지사'], ['5', '광역의원'], ['4', '기초단체장'], ['6', '기초의원'], ['11', '교육감'], ['2', '국회의원 재보궐']];
const _WS_PARTIES = ['더불어민주당', '국민의힘', '조국혁신당', '진보당', '정의당', '개혁신당', '무소속'];
function populateDetailFilters() {
  const typeSel = document.getElementById('ws-type'), sidoSel = document.getElementById('ws-sido'), partySel = document.getElementById('ws-party');
  if (!typeSel || typeSel.dataset.filled) return;
  _WS_TYPES.forEach(([t, l]) => typeSel.add(new Option(l, t)));
  SIDO_ORDER.filter(s => s !== '전남광주통합특별시').forEach(s => sidoSel.add(new Option(s, s)));
  _WS_PARTIES.forEach(p => partySel.add(new Option(p, p)));
  typeSel.dataset.filled = '1';
}
function renderSearchUI() {
  if (_searchWired) return;
  const inp = document.getElementById('ws-input');
  if (!inp) return;
  _searchWired = true;
  populateDetailFilters();
  // 의원 전 후보는 첫 상호작용 때 지연 로드 → 페이지 첫 로딩 가볍게. 로드 끝나면 결과 갱신.
  const kick = () => ensureCouncilLoaded().then(runWinnerSearch);
  const onChange = () => { runWinnerSearch(); kick(); };
  inp.addEventListener('input', onChange);
  inp.addEventListener('focus', kick);
  ['ws-type', 'ws-sido', 'ws-party', 'ws-won'].forEach(id => { const el = document.getElementById(id); if (el) el.addEventListener('change', onChange); });
  const reset = document.getElementById('ws-reset');
  if (reset) reset.addEventListener('click', () => {
    inp.value = '';
    ['ws-type', 'ws-sido', 'ws-party', 'ws-won'].forEach(id => { const el = document.getElementById(id); if (el) el.value = ''; });
    inp.focus();
    runWinnerSearch();
  });
  runWinnerSearch();
}

async function render() {
  const [cur, prediction, parties, photos, huboids, eduOri, covered, council] = await Promise.all([
    loadJSON(PATHS.current), loadJSON(PATHS.prediction), loadJSON(PATHS.parties), loadJSON(PATHS.photos),
    _huboidLoaded ? Promise.resolve(null) : loadJSON(PATHS.cards),
    _huboidLoaded ? Promise.resolve(null) : loadJSON(PATHS.eduOrient),
    _huboidLoaded ? Promise.resolve(COVERED) : loadJSON(PATHS.covered),
    loadJSON(PATHS.council),
  ]);
  if (!cur || !cur.races) { document.getElementById('rs-sub').textContent = '데이터를 불러오지 못했습니다.'; return; }
  if (huboids) { HUBOID = huboids; _huboidLoaded = true; }
  if (eduOri) EDU_ORIENT = eduOri.by_name || {};
  if (covered) COVERED = covered;
  PARTIES = parties || {};
  PHOTO_MAP = photos || { by_full: {}, by_sd: {} };
  const predMap = (prediction && prediction.sido_dem_win_prob) || {};
  PRED_OPP = (prediction && prediction.pred_opponent) || {};

  const byType = t => cur.races.filter(r => String(r.sg_type_code) === t);
  const chiefs = byType('3').sort((a, b) => sidoIdx(a.sd_name) - sidoIdx(b.sd_name));
  const edu = byType('11').sort((a, b) => sidoIdx(a.sd_name) - sidoIdx(b.sd_name));
  const repoll = byType('2').sort((a, b) => (b.progress_pct || 0) - (a.progress_pct || 0));
  const bh = byType('4');

  renderHero(cur, chiefs, edu, repoll, bh, council);
  buildSearchIndex(cur);
  renderSearchUI();
  renderCovered(cur, COVERED, predMap);
  renderHistory(chiefs);
  renderGrid('grid-chief', chiefs, { predMap });
  renderEduTally(edu);
  renderGrid('grid-edu', edu, {});
  renderGrid('grid-repoll', repoll, {});
  renderBH(bh);
  renderCouncil(council);

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
