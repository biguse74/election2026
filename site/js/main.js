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
//     layout : 'single'(단일 카드) | 'grid'(시군구별 그리드) | 'collapsible'(선거구별 details 접힘)
//     groupBy: grid/collapsible에서 그룹 키 추출 함수
//   useAlias: 통합특별시 alias 매핑 적용 여부
const SECTIONS = [
  { id: 'chief',    sgTypecode: '3',  title: '시도지사',       useAlias: true, card: true, detail: { layout: 'single' } },
  { id: 'head',     sgTypecode: '4',  title: '기초단체장',     card: true, detail: { layout: 'grid', groupBy: c => c.sggName || c.wiwName } },
  { id: 'sidoMp',   sgTypecode: '5',  title: '시도의원',       card: true, detail: { layout: 'collapsible', groupBy: c => c.sggName || c.wiwName || '(미지정)' } },
  { id: 'wiwMp',    sgTypecode: '6',  title: '구시군의회의원', card: true, detail: { layout: 'collapsible', groupBy: c => c.sggName || c.wiwName || '(미지정)' } },
  { id: 'educator', sgTypecode: '11', title: '교육감',         card: true, detail: { layout: 'single' } },
];

// 행정구조상 선거 자체가 없는 경우의 컨텍스트 메시지.
// (데이터가 0이라서 단순 숨기면 "누락된 건가?" 오해 소지가 있는 케이스)
const ABSENCE_NOTES = {
  '제주특별자치도': {
    '4': '제주특별자치도는 기초자치단체가 없어 행정시(제주시·서귀포시)의 시장이 도지사로부터 임명됩니다. 기초단체장 선거가 실시되지 않습니다.',
    '6': '제주특별자치도는 기초자치단체가 없어 구시군의회 자체가 없습니다. 기초의원 선거가 실시되지 않습니다.',
  },
  '세종특별자치시': {
    '4': '세종특별자치시는 단층제 광역자치단체로 기초자치단체가 없습니다. 기초단체장 선거가 실시되지 않습니다.',
    '6': '세종특별자치시는 단층제로 기초자치단체가 없어 구시군의회 자체가 없습니다. 기초의원 선거가 실시되지 않습니다.',
  },
};

const state = { data: null, parties: {}, geo: null, nominations: null, dateStr: null, source: null, articles: null, articleMap: {}, constituencies: null, mapInstance: null };
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

// 시도·정당 약칭 사전 (시트 태그가 줄임말로 적힌 케이스 매칭용)
const SIDO_TAGS = {
  '서울특별시': ['서울'],
  '부산광역시': ['부산'],
  '대구광역시': ['대구'],
  '인천광역시': ['인천'],
  '광주광역시': ['광주'],
  '대전광역시': ['대전'],
  '울산광역시': ['울산'],
  '세종특별자치시': ['세종'],
  '경기도': ['경기'],
  '강원특별자치도': ['강원', '강원도'],
  '충청북도': ['충북'],
  '충청남도': ['충남'],
  '전북특별자치도': ['전북', '전라북도'],
  '전라남도': ['전남'],
  '경상북도': ['경북'],
  '경상남도': ['경남'],
  '제주특별자치도': ['제주', '제주도'],
  '전남광주통합특별시': ['전남', '광주', '전남광주'],
};
const PARTY_TAGS = {
  '더불어민주당': ['민주당', '민주'],
  '국민의힘': ['국힘'],
  '조국혁신당': ['혁신당', '조국당'],
  '개혁신당': ['개혁'],
  '진보당': [],
  '정의당': [],
  '녹색정의당': ['정의'],
};

// 뉴탐사 보도 태그 ↔ 후보 매칭. 정확도 최우선.
//   - 이름만 일치는 동명이인 오연결 다발(이재명·한동훈·윤석열 등).
//   - 시트 기사 태그에 후보의 정당 AND 지역 단서가 모두 함께 있어야 매칭.
//   - 그렇게 좁혀서 후보가 1명일 때만 연결, 그래도 모호하면 보류.
function tagsForCandidate(c) {
  const sd = c.sdName || '';
  const sgg = c.sggName || '';
  const wiw = c.wiwName || '';
  const jd  = c.jdName  || '';
  return {
    region: new Set([sd, sgg, wiw, ...(SIDO_TAGS[sd] || [])].filter(Boolean)),
    party:  new Set([jd, ...(PARTY_TAGS[jd] || [])].filter(Boolean)),
  };
}
function hasIntersection(a, b) {
  for (const x of a) if (b.has(x)) return true;
  return false;
}

function buildArticleMap(articles, candidates) {
  if (!articles?.length || !candidates?.length) return {};
  const byName = candidates.reduce((acc, c) => {
    if (!c.name) return acc;
    (acc[c.name] ||= []).push(c);
    return acc;
  }, {});
  const map = {};
  for (const art of articles) {
    const tagSet = new Set(art.tags || []);
    for (const tag of art.tags || []) {
      const candList = byName[tag];
      if (!candList?.length) continue;
      // 정당 AND 지역 단서가 모두 시트 태그에 있는 후보만 (유명 동명이인 차단)
      const qualified = candList.filter(c => {
        const t = tagsForCandidate(c);
        return hasIntersection(t.party, tagSet) && hasIntersection(t.region, tagSet);
      });
      if (qualified.length !== 1) continue; // 0명: 단서 없음 / 2명 이상: 모호
      const c = qualified[0];
      if (!c.huboid) continue;
      (map[c.huboid] ||= []).push(art);
    }
  }
  // 후보별 url 중복 제거 + 날짜 내림차순
  for (const k of Object.keys(map)) {
    const seen = new Set();
    map[k] = map[k]
      .filter(a => !seen.has(a.url) && seen.add(a.url))
      .sort((a, b) => (b.date || '').localeCompare(a.date || ''));
  }
  return map;
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
const loadArticles = () => safeJson('data/articles.json', null);
const loadConstituencies = () => safeJson('data/constituencies.json', null);

// 라우팅용: 통합특별시는 광주/전남 중 광주로 진입 (alias 매핑이 양쪽 수용)
const sidoFor = obj => obj.sdName === '전남광주통합특별시' || obj.sd === '전남광주통합특별시'
  ? '광주광역시'
  : (obj.sdName || obj.sd);

// 경쟁률(후보 수 / 의석 수) 계산. SECTIONS의 sgTypecode만 대상.
const seatKey = c => `${c.sgTypecode}|${c.sdName}|${c.sggName}`;

// 의석수 인덱스 + 선거구별 후보 수. 경쟁률·무투표 두 박스에서 공유.
function buildSeatStats() {
  const constituencies = state.constituencies;
  if (!constituencies?.length) return null;
  const allowedTypes = new Set(SECTIONS.map(s => s.sgTypecode));
  const seats = {};
  for (const s of constituencies) {
    if (!allowedTypes.has(String(s.sgTypecode))) continue;
    seats[seatKey(s)] = parseInt(s.sggJungsu, 10) || 1;
  }
  const counts = {};
  for (const c of state.data.candidates) {
    if (!allowedTypes.has(String(c.sgTypecode))) continue;
    counts[seatKey(c)] = (counts[seatKey(c)] || 0) + 1;
  }
  return { seats, counts };
}

function buildCompetitionRanking() {
  const stats = buildSeatStats();
  if (!stats) return [];
  const titleMap = Object.fromEntries(SECTIONS.map(s => [s.sgTypecode, s.title]));
  const rows = Object.entries(stats.counts).map(([k, count]) => {
    const [sgType, sd, sgg] = k.split('|');
    const seat = stats.seats[k] || 1;
    return { sgType, sd, sgg, count, seat, ratio: count / seat, title: titleMap[sgType] || sgType };
  });
  rows.sort((a, b) => b.ratio - a.ratio || b.count - a.count);
  return rows;
}

// 이대로 가면 무투표 당선될 가능성이 있는 곳 (정원 = 후보 수).
// 정원 > 후보(미달)·0명도 함께 수집 — 사용자는 박스 안에서 카테고리별로 본다.
function buildUncontestedList() {
  const stats = buildSeatStats();
  if (!stats) return { tied: [], short: [], zero: [] };
  const titleMap = Object.fromEntries(SECTIONS.map(s => [s.sgTypecode, s.title]));
  const tied = [], short = [], zero = [];
  for (const [k, seat] of Object.entries(stats.seats)) {
    const count = stats.counts[k] || 0;
    if (count > seat) continue;
    const [sgType, sd, sgg] = k.split('|');
    const row = { sgType, sd, sgg, count, seat, title: titleMap[sgType] || sgType };
    if (count === 0) zero.push(row);
    else if (count < seat) short.push(row);
    else tied.push(row);
  }
  const cmp = (a, b) => sidoSort(a.sd, b.sd) || koSort(a.sgg || '', b.sgg || '');
  return { tied: tied.sort(cmp), short: short.sort(cmp), zero: zero.sort(cmp) };
}

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
function articleListHtml(articles) {
  return articles.map(a => `
    <li>
      <a href="${a.url}" target="_blank" rel="noopener noreferrer">${a.title}</a>
      <span class="article-meta">${a.date || ''}${a.author ? ' · ' + a.author : ''}</span>
    </li>`).join('');
}

function candidateRow(c) {
  const confirmed = isConfirmed(c);
  const articles = state.articleMap?.[c.huboid] || [];
  const hasArt = articles.length > 0;
  const aid = hasArt ? `art-${c.huboid}` : '';
  return `
    <div class="candidate${confirmed ? ' confirmed' : ''}">
      <div class="candidate-color" style="background:${partyColor(c.jdName)}"></div>
      <div class="candidate-name">${c.name}${confirmed ? '<span class="confirmed-badge">공천</span>' : ''}</div>
      <div class="candidate-party">${c.jdName}</div>
      ${hasArt ? `<button type="button" class="article-toggle" data-target="${aid}" title="뉴탐사 관련 보도 ${articles.length}건">📰 ${articles.length}</button>` : ''}
    </div>
    ${hasArt ? `<ul class="article-list" id="${aid}" hidden>${articleListHtml(articles)}</ul>` : ''}`;
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

  if (layout === 'collapsible') {
    // 선거구 수가 많은 시도의원·구시군의회의원용. 선거구별 details(기본 접힘)로 묶음.
    const groups = candidates.reduce((acc, c) => {
      const k = groupBy(c);
      (acc[k] ||= []).push(c);
      return acc;
    }, {});
    const keys = Object.keys(groups).sort(koSort);
    return `
      <h3 class="section-title">${section.title}
        <span class="section-count">${candidates.length.toLocaleString()}명 · ${keys.length}개 선거구</span>
      </h3>
      <div class="collapsible-grid">
        ${keys.map(k => `
          <details class="electoral-district">
            <summary>
              <span class="ed-name">${k}</span>
              <span class="ed-count">${groups[k].length}명</span>
            </summary>
            <div class="ed-body">${groups[k].map(candidateRow).join('')}</div>
          </details>`).join('')}
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

  const artCount = Object.values(state.articleMap || {}).reduce((n, arr) => n + arr.length, 0);
  const matchedCount = Object.keys(state.articleMap || {}).length;
  const artSrc = state.articles && matchedCount
    ? `<p class="nominations-source">📰 <strong>관련 보도</strong>: 뉴탐사 <a href="${state.articles.source_url}" target="_blank" rel="noopener">공천대란 페이지</a>의 인물 태그 ↔ 후보 매칭. 동명이인 오연결(이재명·한동훈 등) 방지를 위해 시트 기사 태그에 후보의 <strong>정당과 지역</strong>이 모두 함께 있을 때만 연결합니다. 매칭 후보 ${matchedCount.toLocaleString()}명, 연결 보도 ${artCount.toLocaleString()}건.</p>`
    : '';

  // source('preliminary' | 'candidates')에 따라 라벨 자동 전환
  const totalLabel = state.source === 'candidates' ? '총 후보자' : '총 예비후보자';
  const candidateSuffix = state.source === 'candidates' ? '후보' : '예비후보';

  // 경쟁률 상위 선거구 (sggJungsu=의석수 기준)
  const ranking = buildCompetitionRanking();
  const topRanking = ranking.slice(0, 8);
  const competitionBox = topRanking.length ? `
    <section class="competition">
      <h2 class="section-title">경쟁이 가장 치열한 선거구
        <span class="section-count">의석 1자리당 후보 수 기준 · 상위 ${topRanking.length}개</span>
      </h2>
      <ol class="competition-list">
        ${topRanking.map((r, i) => `
          <li>
            <span class="comp-rank">${i+1}</span>
            <a class="comp-region" href="#${encodeURIComponent(sidoFor(r))}">${r.sgg || r.sd}</a>
            <span class="comp-type">${r.title}</span>
            <span class="comp-ratio"><strong>${r.ratio.toFixed(1)}</strong>:1</span>
            <span class="comp-detail">${r.count}명 / ${r.seat}석</span>
          </li>`).join('')}
      </ol>
    </section>` : '';

  // 무투표 가능·정원 미달·예비후보 미등록 (사실 진단)
  const uc = buildUncontestedList();
  const stageNote = state.source === 'candidates'
    ? '후보 등록 기준 — 등록 마감이라 사실상 확정.'
    : '예비후보 등록 기준 — 5/14~15 후보 등록 시 변동 가능.';
  const ucRowHtml = r => `
    <li>
      <a class="uc-region" href="#${encodeURIComponent(sidoFor(r))}">${r.sgg || r.sd}</a>
      <span class="uc-type">${r.title}</span>
      <span class="uc-detail">${r.count}/${r.seat}</span>
      <span class="uc-sido">${r.sd}</span>
    </li>`;
  const ucBlock = (label, items, limit, cls) => {
    if (!items.length) return '';
    const shown = items.slice(0, limit);
    const more = items.length - shown.length;
    return `
      <div class="uc-block ${cls}">
        <h3 class="uc-block-title">${label} <span class="uc-count">${items.length.toLocaleString()}곳</span></h3>
        <ul class="uc-list">${shown.map(ucRowHtml).join('')}</ul>
        ${more > 0 ? `<p class="uc-more">+${more.toLocaleString()}곳 더 (시도 상세 페이지에서 확인)</p>` : ''}
      </div>`;
  };
  const ucBox = (uc.tied.length || uc.short.length || uc.zero.length) ? `
    <section class="uncontested">
      <h2 class="section-title">이대로 가면 무투표 당선·정원 미달
        <span class="section-count">${stageNote}</span>
      </h2>
      ${ucBlock('무투표 당선 가능 (정원 = 후보)', uc.tied, 12, 'tied')}
      ${ucBlock('정원 미달 (정원 &gt; 후보)', uc.short, 8, 'short')}
      ${ucBlock('후보 0명', uc.zero, 8, 'zero')}
    </section>` : '';

  const html = `
    <div class="stats">
      <div class="stat"><div class="stat-label">${totalLabel}</div><div class="stat-value">${cands.length.toLocaleString()}명</div><div class="stat-sub">${state.data.fetched_at.slice(0,10)} 기준</div></div>
      ${SECTIONS.filter(s => s.card).map(s => `
        <div class="stat">
          <div class="stat-label">${s.title} ${candidateSuffix}</div>
          <div class="stat-value">${countBy(s.sgTypecode).toLocaleString()}명</div>
        </div>`).join('')}
      <div class="stat"><div class="stat-label">참여 정당</div><div class="stat-value">${totalParties}개</div><div class="stat-sub">무소속 포함</div></div>
    </div>
    ${competitionBox}
    ${ucBox}
    <h2 class="section-title">전국 지도</h2>
    <p class="section-hint">시도를 클릭하면 해당 지역의 후보자 상세로 이동합니다.</p>
    <div id="map"></div>
    <h2 class="section-title">시도별 후보자</h2>
    ${nomSrc}
    ${artSrc}
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

// ============ 검색 (헤더 input → 결과 dropdown) ============
function runSearch(q) {
  const norm = (q || '').trim();
  const results = document.getElementById('search-results');
  if (!results) return;
  if (norm.length < 1) {
    results.hidden = true;
    results.innerHTML = '';
    return;
  }
  const titleMap = Object.fromEntries(SECTIONS.map(s => [s.sgTypecode, s.title]));
  const matches = state.data.candidates.filter(c => c.name && c.name.includes(norm));
  if (matches.length === 0) {
    results.innerHTML = '<div class="sr-empty">일치하는 후보가 없습니다</div>';
    results.hidden = false;
    return;
  }
  // 정확 일치 우선, 그 다음 시도 기본 정렬
  matches.sort((a, b) => (a.name === norm ? -1 : 0) - (b.name === norm ? -1 : 0)
    || sidoSort(a.sdName, b.sdName));
  const top = matches.slice(0, 30);
  const items = top.map(c => {
    const region = c.sggName && c.sggName !== c.sdName
      ? `${c.sdName} · ${c.sggName}` : (c.sdName || '');
    return `
      <a class="sr-item" href="#${encodeURIComponent(sidoFor(c))}">
        <span class="sr-name">${c.name}</span>
        <span class="sr-meta">${c.jdName || '무소속'} · ${titleMap[c.sgTypecode] || ''} · ${region}</span>
      </a>`;
  }).join('');
  const more = matches.length > 30
    ? `<div class="sr-more">+${(matches.length - 30).toLocaleString()}건 더 (검색어를 더 정확히 입력)</div>`
    : '';
  results.innerHTML = items + more;
  results.hidden = false;
}

function initSearch() {
  const input = document.getElementById('search-input');
  const results = document.getElementById('search-results');
  if (!input || !results) return;
  let timer = null;
  input.addEventListener('input', e => {
    clearTimeout(timer);
    const q = e.target.value;
    timer = setTimeout(() => runSearch(q), 100);
  });
  input.addEventListener('focus', () => {
    if (input.value.trim()) runSearch(input.value);
  });
  document.addEventListener('click', e => {
    if (!e.target.closest('.search')) {
      results.hidden = true;
    }
  });
  // 결과 클릭 시 닫기 + input 비우기 (라우팅은 href가 처리)
  results.addEventListener('click', e => {
    if (e.target.closest('.sr-item')) {
      results.hidden = true;
      input.value = '';
    }
  });
  // ESC로 닫기
  input.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
      input.value = '';
      results.hidden = true;
      input.blur();
    }
  });
}

// ============ Bootstrap ============
async function main() {
  calculateDDay();
  try {
    const [{ data, dateStr, source }, parties, geo, nominations, articles, constituencies] = await Promise.all([
      loadLatestSnapshot(), loadParties(), loadGeo(), loadNominations(), loadArticles(), loadConstituencies(),
    ]);
    // 로딩 시점에 단 한 번 dedup. 이후 모든 화면은 깨끗한 데이터를 본다.
    state.data = { ...data, candidates: dedupeByHuboid(data.candidates) };
    state.parties = parties;
    state.geo = geo;
    state.nominations = nominations;
    state.dateStr = dateStr;
    state.source = source;
    state.articles = articles;
    state.articleMap = buildArticleMap(articles?.articles, state.data.candidates);
    state.constituencies = constituencies;
    const sourceLabel = SOURCE_LABEL[source] || source;
    document.getElementById('last-updated').textContent =
      `${dateStr.slice(0,4)}.${dateStr.slice(4,6)}.${dateStr.slice(6,8)} · ${sourceLabel}`;
    // 후보 행의 보도 배지 토글 (이벤트 위임 — 행이 동적으로 다시 그려져도 OK)
    document.addEventListener('click', e => {
      const btn = e.target.closest('.article-toggle');
      if (!btn) return;
      e.preventDefault();
      const panel = document.getElementById(btn.dataset.target);
      if (!panel) return;
      panel.hidden = !panel.hidden;
      btn.classList.toggle('open', !panel.hidden);
    });
    initSearch();
    window.addEventListener('hashchange', route);
    route();
  } catch (e) {
    document.getElementById('app').innerHTML =
      `<div class="loading">데이터 로딩 실패: ${e.message}</div>`;
  }
}

main();
