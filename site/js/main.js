const ELECTION_DATE = '2026-06-03T00:00:00';

// 광주광역시·전라남도는 시도지사 선거에서만 '전남광주통합특별시' 하나로 통합됨
const SIDO_ALIASES = {
  '광주광역시': '전남광주통합특별시',
  '전라남도': '전남광주통합특별시',
};

// 행정안전부 표준 시도 정렬 순서 (서울 → 광역시 → 도 → 제주)
const SIDO_ORDER = [
  '서울특별시', '부산광역시', '대구광역시', '인천광역시', '광주광역시',
  '대전광역시', '울산광역시', '세종특별자치시', '경기도', '강원특별자치도',
  '충청북도', '충청남도', '전북특별자치도', '전라남도', '경상북도', '경상남도', '제주특별자치도',
];

const sidoSort = (a, b) => {
  const ai = SIDO_ORDER.indexOf(a);
  const bi = SIDO_ORDER.indexOf(b);
  if (ai === -1 && bi === -1) return a.localeCompare(b, 'ko');
  if (ai === -1) return 1;
  if (bi === -1) return -1;
  return ai - bi;
};


// 선거 종류별 정의 — 단일 소스. 신규 선거 추가 시 여기만 손대면 됨.
//   card    : 홈 시도 카드 통계에 노출
//   detail  : 시도 상세 페이지 섹션 정의 (없으면 상세에 미노출)
//     layout : 'single'(단일 카드) | 'grid'(시군구별 그리드)
//     groupBy: grid에서 그룹 키 추출 함수
//   useAlias: 통합특별시 alias 매핑 적용 여부
const SECTIONS = [
  { id: 'chief',    sgTypecode: '3',  title: '시도지사',   useAlias: true, card: true, detail: { layout: 'single' } },
  { id: 'head',     sgTypecode: '4',  title: '기초단체장', card: true, detail: { layout: 'grid', groupBy: c => c.sggName || c.wiwName } },
  { id: 'sidoMp',   sgTypecode: '5',  title: '시도의원',   card: true },
  { id: 'educator', sgTypecode: '11', title: '교육감',     card: true, detail: { layout: 'single' } },
];

// 행정구조상 선거 자체가 없는 경우의 컨텍스트 메시지.
// (데이터가 0이라서 단순 숨기면 "누락된 건가?" 오해 소지가 있는 케이스)
const ABSENCE_NOTES = {
  '제주특별자치도': {
    '4': '제주특별자치도는 기초자치단체가 없어 행정시(제주시·서귀포시)의 시장이 도지사로부터 임명됩니다. 기초단체장 선거가 실시되지 않습니다.',
  },
  '세종특별자치시': {
    '4': '세종특별자치시는 단층제 광역자치단체로 기초자치단체가 없습니다. 기초단체장 선거가 실시되지 않습니다.',
  },
};

const state = { data: null, parties: {}, geo: null, nominations: null, dateStr: null, source: null, mapInstance: null };
const koSort = (a, b) => a.localeCompare(b, 'ko');

// ============ Helpers ============
const partyColor = name => state.parties[name] || (name === '무소속' ? '#888' : '#bbb');

function dedupeByHuboid(list) {
  const seen = new Set();
  const out = [];
  for (const c of list) {
    const id = c.huboid;
    if (id && seen.has(id)) continue;
    if (id) seen.add(id);
    out.push(c);
  }
  return out;
}

// 후보 등록(5/14~) 이후엔 candidates 스냅샷이 로드된다 = 등록 자체가 공천 확정 의미.
// → 배지가 정보가치를 잃으므로 자동 숨김. (안전망으로 dateStr cutoff도 함께 검사)
const NOMINATION_CUTOFF = '20260514';

function isConfirmed(c) {
  if (!state.nominations) return false;
  if (state.source === 'candidates') return false;
  if (state.dateStr && state.dateStr >= NOMINATION_CUTOFF) return false;
  const groups = state.nominations[`sgTypecode_${c.sgTypecode}`];
  if (!groups) return false;
  const list = groups[c.sggName || c.sdName];
  if (!list) return false;
  return list.some(([name, party]) => name === c.name && party === c.jdName);
}

// 섹션 정의에 따라 후보 추출 (alias 처리 포함). 모든 화면이 공유.
function getSectionCandidates(section, sidoName) {
  const sgType = section.sgTypecode;
  if (section.useAlias) {
    const alias = SIDO_ALIASES[sidoName];
    return state.data.candidates.filter(c => {
      if (String(c.sgTypecode) !== sgType) return false;
      const region = c.sggName || c.sdName;
      return region === sidoName || (alias && region === alias);
    });
  }
  return state.data.candidates.filter(c =>
    String(c.sgTypecode) === sgType && c.sdName === sidoName
  );
}

// ============ D-day ============
function calculateDDay() {
  const today = new Date(); today.setHours(0, 0, 0, 0);
  const electionDay = new Date(ELECTION_DATE);
  const diffDays = Math.ceil((electionDay - today) / 86_400_000);
  const el = document.getElementById('dday');
  el.textContent = diffDays > 0 ? `D-${diffDays}` : diffDays === 0 ? 'D-DAY' : `D+${-diffDays}`;
}

// ============ Loaders ============
const safeJson = async (url, fallback) => {
  try { const r = await fetch(url); return r.ok ? await r.json() : fallback; }
  catch { return fallback; }
};
const loadParties = () => safeJson('data/parties.json', {});
const loadNominations = () => safeJson('data/nominations.json', null);
const loadGeo = () => safeJson('assets/geo/sido.geojson', null);

// 후보 등록 시작일. 이 날짜 이후로는 candidates 스냅샷이 우선.
const CANDIDATES_START = '20260514';

const SOURCE_LABEL = {
  preliminary: '예비후보',
  candidates: '후보 등록',
};

// 후보 등록(5/14) 이후엔 candidates를 먼저 시도, 못 찾으면 preliminary로 폴백.
// 두 데이터 모두 동일한 {candidates:[...]} 스키마라 호출부 변화 없음.
async function loadLatestSnapshot() {
  const today = new Date();
  const toDateStr = d => `${d.getFullYear()}${String(d.getMonth()+1).padStart(2,'0')}${String(d.getDate()).padStart(2,'0')}`;
  const tryFetch = async (source, dateStr) => {
    const r = await fetch(`../data/${source}/20260603/snapshot_${dateStr}.json`).catch(() => null);
    return r?.ok ? { data: await r.json(), dateStr, source } : null;
  };

  // 1단계: 5/14 이후 날짜의 candidates 스냅샷을 최대 30일까지 거꾸로 탐색
  for (let i = 0; i < 30; i++) {
    const d = new Date(today); d.setDate(d.getDate() - i);
    const dateStr = toDateStr(d);
    if (dateStr < CANDIDATES_START) break;
    const hit = await tryFetch('candidates', dateStr);
    if (hit) return hit;
  }

  // 2단계: preliminary 14일 폴백 (등록 전 기간 또는 candidates 부재 시)
  for (let i = 0; i < 14; i++) {
    const d = new Date(today); d.setDate(d.getDate() - i);
    const hit = await tryFetch('preliminary', toDateStr(d));
    if (hit) return hit;
  }
  throw new Error('최근 스냅샷 파일을 찾지 못했습니다.');
}

// ============ Render: 후보 row/card ============
function candidateRow(c) {
  const confirmed = isConfirmed(c);
  return `
    <div class="candidate${confirmed ? ' confirmed' : ''}">
      <div class="candidate-color" style="background:${partyColor(c.jdName)}"></div>
      <div class="candidate-name">${c.name}${confirmed ? '<span class="confirmed-badge">공천</span>' : ''}</div>
      <div class="candidate-party">${c.jdName}</div>
    </div>`;
}

function candidateCard(label, list) {
  return `
    <div class="candidate-card">
      <div class="cc-header">
        <div class="cc-name">${label}</div>
        <div class="cc-count">${list.length}명</div>
      </div>
      ${list.length === 0 ? '<div class="cc-empty">등록된 후보가 없습니다.</div>' : list.map(candidateRow).join('')}
    </div>`;
}

// ============ Render: 상세 섹션 ============
function renderDetailSection(section, sidoName) {
  if (!section.detail) return '';
  const candidates = getSectionCandidates(section, sidoName);

  // 비어있는 섹션: 컨텍스트 메시지가 있으면 노출, 없으면 완전 숨김
  if (candidates.length === 0) {
    const note = ABSENCE_NOTES[sidoName]?.[section.sgTypecode];
    return note
      ? `<h3 class="section-title">${section.title}</h3><p class="absence-note">${note}</p>`
      : '';
  }

  const { layout, groupBy } = section.detail;

  if (layout === 'single') {
    const label = section.id === 'chief'
      ? (candidates[0].sggName || sidoName)
      : `${sidoName} ${section.title}`;
    return `
      <h3 class="section-title">${section.title}</h3>
      <div class="single-section">${candidateCard(label, candidates)}</div>`;
  }

  if (layout === 'grid') {
    const groups = candidates.reduce((acc, c) => {
      const k = groupBy(c);
      (acc[k] ||= []).push(c);
      return acc;
    }, {});
    const keys = Object.keys(groups).sort(koSort);
    return `
      <h3 class="section-title">${section.title}</h3>
      <div class="basic-grid">
        ${keys.map(k => candidateCard(k, groups[k])).join('')}
      </div>`;
  }

  return '';
}

// ============ Render: 홈 ============
function destroyMap() {
  if (state.mapInstance) { state.mapInstance.remove(); state.mapInstance = null; }
}

function initHomeMap() {
  destroyMap();
  if (!state.geo) return;
  const map = L.map('map', { zoomControl: true, scrollWheelZoom: false, attributionControl: false })
    .setView([36.0, 127.7], 7);
  state.mapInstance = map;

  const base = { fillColor: '#e8e0d0', weight: 1, color: '#999', fillOpacity: 0.55 };
  const hover = { fillColor: '#f4d35e', weight: 2, color: '#1a1a1a', fillOpacity: 0.8 };

  const layer = L.geoJSON(state.geo, {
    style: base,
    onEachFeature: (feature, layer) => {
      const name = feature.properties.name;
      const chiefs = getSectionCandidates(SECTIONS[0], name).length;
      const heads = getSectionCandidates(SECTIONS[1], name).length;
      layer.bindTooltip(
        `${name}<br><span style="opacity:0.75;font-weight:400">시도지사 ${chiefs} · 기초단체장 ${heads}</span>`,
        { sticky: true, className: 'sido-tooltip', direction: 'top' }
      );
      layer.on('mouseover', e => e.target.setStyle(hover));
      layer.on('mouseout', e => layer.resetStyle?.(e.target) ?? e.target.setStyle(base));
      layer.on('click', () => { location.hash = '#' + encodeURIComponent(name); });
    },
  }).addTo(map);
  map.fitBounds(layer.getBounds(), { padding: [20, 20] });
}

function renderHome() {
  destroyMap();
  const cands = state.data.candidates;

  // 글로벌 카운트
  const countBy = sgType => cands.filter(c => String(c.sgTypecode) === sgType).length;
  const totalParties = new Set(cands.map(c => c.jdName)).size;

  // 시도 목록 (sdName 기준, '전국' 제외)
  const sidos = Array.from(new Set(cands.map(c => c.sdName).filter(s => s && s !== '전국'))).sort(sidoSort);

  const nomActive = state.nominations
    && state.source !== 'candidates'
    && (!state.dateStr || state.dateStr < NOMINATION_CUTOFF);
  const nomSrc = nomActive
    ? `<p class="nominations-source">★ <strong>공천</strong> 배지: ${state.nominations.source}</p>`
    : '';

  const html = `
    <div class="stats">
      <div class="stat"><div class="stat-label">총 예비후보자</div><div class="stat-value">${cands.length.toLocaleString()}명</div><div class="stat-sub">${state.data.fetched_at.slice(0,10)} 기준</div></div>
      <div class="stat"><div class="stat-label">시도지사 후보</div><div class="stat-value">${countBy('3').toLocaleString()}명</div><div class="stat-sub">16개 광역단체 선거</div></div>
      <div class="stat"><div class="stat-label">기초단체장 후보</div><div class="stat-value">${countBy('4').toLocaleString()}명</div><div class="stat-sub">226개 시군구 선거</div></div>
      <div class="stat"><div class="stat-label">참여 정당</div><div class="stat-value">${totalParties}개</div><div class="stat-sub">무소속 포함</div></div>
    </div>
    <h2 class="section-title">전국 지도</h2>
    <p class="section-hint">시도를 클릭하면 해당 지역의 후보자 상세로 이동합니다.</p>
    <div id="map"></div>
    <h2 class="section-title">시도별 후보자</h2>
    ${nomSrc}
    <div class="sido-grid">
      ${sidos.map(sido => {
        // 카드 통계는 SECTIONS 정의에서 자동 도출. 0인 항목은 숨김.
        const stats = SECTIONS
          .filter(s => s.card)
          .map(s => ({ label: s.title, count: getSectionCandidates(s, sido).length }))
          .filter(s => s.count > 0);
        if (stats.length === 0) return '';
        return `
          <a href="#${encodeURIComponent(sido)}" class="sido-card">
            <div class="sido-card-name">${sido}</div>
            <div class="sido-card-stats">
              ${stats.map(s => `<div>${s.label} <strong>${s.count}</strong></div>`).join('')}
            </div>
          </a>`;
      }).join('')}
    </div>`;

  const app = document.getElementById('app');
  app.innerHTML = html;
  app.classList.remove('loading');
  initHomeMap();
}

// ============ Render: 상세 ============
function renderSidoDetail(sidoName) {
  destroyMap();

  // 상세에서 그릴 섹션들의 후보 데이터를 한 번에 준비
  const sectionData = SECTIONS
    .filter(s => s.detail)
    .map(s => ({ section: s, candidates: getSectionCandidates(s, sidoName) }));

  // 인라인 통계: 후보가 있는 섹션만. + 기초단체장이 있으면 시군구 카운트 추가
  const stats = sectionData
    .filter(d => d.candidates.length > 0)
    .map(d => ({ label: d.section.title, count: d.candidates.length }));

  const headData = sectionData.find(d => d.section.id === 'head');
  if (headData && headData.candidates.length > 0) {
    const sggCount = new Set(headData.candidates.map(c => c.sggName || c.wiwName)).size;
    stats.push({ label: '시군구', count: sggCount });
  }

  const html = `
    <nav class="breadcrumb">
      <a href="#">전체</a> <span class="sep">›</span> <span class="current">${sidoName}</span>
    </nav>
    <div class="detail-head">
      <h2 class="detail-title">${sidoName}</h2>
      <div class="detail-inline-stats">
        ${stats.map(s => `<div><strong>${s.count}</strong> ${s.label}</div>`).join('')}
      </div>
    </div>
    ${SECTIONS.filter(s => s.detail).map(s => renderDetailSection(s, sidoName)).join('')}
  `;

  const app = document.getElementById('app');
  app.innerHTML = html;
  app.classList.remove('loading');
  window.scrollTo({ top: 0, behavior: 'instant' });
}

// ============ Routing ============
function route() {
  const hash = decodeURIComponent(location.hash.slice(1));
  if (!hash) renderHome();
  else renderSidoDetail(hash);
}

// ============ Bootstrap ============
async function main() {
  calculateDDay();
  try {
    const [{ data, dateStr, source }, parties, geo, nominations] = await Promise.all([
      loadLatestSnapshot(), loadParties(), loadGeo(), loadNominations(),
    ]);
    // 로딩 시점에 단 한 번 dedup. 이후 모든 화면은 깨끗한 데이터를 본다.
    state.data = { ...data, candidates: dedupeByHuboid(data.candidates) };
    state.parties = parties;
    state.geo = geo;
    state.nominations = nominations;
    state.dateStr = dateStr;
    state.source = source;
    const sourceLabel = SOURCE_LABEL[source] || source;
    document.getElementById('last-updated').textContent =
      `${dateStr.slice(0,4)}.${dateStr.slice(4,6)}.${dateStr.slice(6,8)} · ${sourceLabel}`;
    window.addEventListener('hashchange', route);
    route();
  } catch (e) {
    document.getElementById('app').innerHTML =
      `<div class="loading">데이터 로딩 실패: ${e.message}</div>`;
  }
}

main();
