const ELECTION_DATE = '2026-06-03T00:00:00';

const SIDO_ALIASES = {
  '광주광역시': '전남광주통합특별시',
  '전라남도': '전남광주통합특별시',
};

const state = {
  data: null,
  parties: {},
  geo: null,
  nominations: null,
  dateStr: null,
  mapInstance: null,
};

const koSort = (a, b) => a.localeCompare(b, 'ko');

function calculateDDay() {
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const electionDay = new Date(ELECTION_DATE);
  const diffDays = Math.ceil((electionDay - today) / (1000 * 60 * 60 * 24));
  const el = document.getElementById('dday');
  if (diffDays > 0) el.textContent = `D-${diffDays}`;
  else if (diffDays === 0) el.textContent = 'D-DAY';
  else el.textContent = `D+${-diffDays}`;
}

async function loadParties() {
  try { const r = await fetch('data/parties.json'); return r.ok ? await r.json() : {}; }
  catch { return {}; }
}
async function loadNominations() {
  try { const r = await fetch('data/nominations.json'); return r.ok ? await r.json() : null; }
  catch { return null; }
}
async function loadGeo() {
  const r = await fetch('assets/geo/sido.geojson');
  return r.ok ? await r.json() : null;
}
async function loadLatestPreliminary() {
  const today = new Date();
  for (let i = 0; i < 14; i++) {
    const d = new Date(today);
    d.setDate(d.getDate() - i);
    const dateStr = `${d.getFullYear()}${String(d.getMonth()+1).padStart(2,'0')}${String(d.getDate()).padStart(2,'0')}`;
    try {
      const r = await fetch(`../data/preliminary/20260603/snapshot_${dateStr}.json`);
      if (r.ok) return { data: await r.json(), dateStr };
    } catch {}
  }
  throw new Error('최근 14일 내 스냅샷 파일을 찾지 못했습니다.');
}

// 중복 제거 (전남광주통합특별시 같은 통합 선거구 후보가 광주/전남 호출 양쪽에서 반환되는 이슈 대응)
function dedupeByHuboid(list) {
  const seen = new Set();
  const out = [];
  for (const c of list) {
    const id = c.huboid;
    if (!id) { out.push(c); continue; }
    if (seen.has(id)) continue;
    seen.add(id);
    out.push(c);
  }
  return out;
}

function partyColor(name) {
  return state.parties[name] || (name === '무소속' ? '#888' : '#bbb');
}

function isConfirmed(c) {
  if (!state.nominations) return false;
  const groups = state.nominations[`sgTypecode_${c.sgTypecode}`];
  if (!groups) return false;
  const region = c.sggName || c.sdName;
  const list = groups[region];
  if (!list) return false;
  return list.some(([name, party]) => name === c.name && party === c.jdName);
}

function sidoChiefCandidates(sidoName) {
  const alias = SIDO_ALIASES[sidoName];
  const matched = state.data.candidates.filter(c => {
    if (String(c.sgTypecode) !== '3') return false;
    const region = c.sggName || c.sdName;
    return region === sidoName || (alias && region === alias);
  });
  return dedupeByHuboid(matched);
}

function candidateRow(c) {
  const confirmed = isConfirmed(c);
  return `
    <div class="candidate${confirmed ? ' confirmed' : ''}">
      <div class="candidate-color" style="background:${partyColor(c.jdName)}"></div>
      <div class="candidate-name">${c.name}${confirmed ? '<span class="confirmed-badge">공천</span>' : ''}</div>
      <div class="candidate-party">${c.jdName}</div>
    </div>`;
}

function candidateCard(name, list) {
  return `
    <div class="candidate-card">
      <div class="cc-header">
        <div class="cc-name">${name}</div>
        <div class="cc-count">${list.length}명</div>
      </div>
      ${list.length === 0 ? '<div class="cc-empty">등록된 후보가 없습니다.</div>' : list.map(candidateRow).join('')}
    </div>`;
}

function destroyMap() {
  if (state.mapInstance) { state.mapInstance.remove(); state.mapInstance = null; }
}

function initHomeMap() {
  destroyMap();
  if (!state.geo) return;
  const map = L.map('map', { zoomControl: true, scrollWheelZoom: false, attributionControl: false }).setView([36.0, 127.7], 7);
  state.mapInstance = map;
  const baseStyle = { fillColor: '#e8e0d0', weight: 1, color: '#999', fillOpacity: 0.55 };
  const hoverStyle = { fillColor: '#f4d35e', weight: 2, color: '#1a1a1a', fillOpacity: 0.8 };
  const layer = L.geoJSON(state.geo, {
    style: baseStyle,
    onEachFeature: (feature, layer) => {
      const name = feature.properties.name;
      const chiefs = sidoChiefCandidates(name).length;
      const heads = dedupeByHuboid(state.data.candidates.filter(c => String(c.sgTypecode) === '4' && c.sdName === name)).length;
      layer.bindTooltip(`${name}<br><span style="opacity:0.75;font-weight:400">시도지사 ${chiefs} · 기초단체장 ${heads}</span>`, { sticky: true, className: 'sido-tooltip', direction: 'top' });
      layer.on('mouseover', e => e.target.setStyle(hoverStyle));
      layer.on('mouseout', e => layer.resetStyle ? layer.resetStyle(e.target) : e.target.setStyle(baseStyle));
      layer.on('click', () => { location.hash = '#' + encodeURIComponent(name); });
    },
  }).addTo(map);
  map.fitBounds(layer.getBounds(), { padding: [20, 20] });
}

function renderHome() {
  destroyMap();
  const cands = state.data.candidates;
  const byType = {};
  for (const c of cands) { const t = String(c.sgTypecode); byType[t] = (byType[t] || 0) + 1; }
  const totalParties = new Set(cands.map(c => c.jdName)).size;
  const sidos = Array.from(new Set(cands.map(c => c.sdName).filter(s => s && s !== '전국'))).sort(koSort);

  const nomSource = state.nominations
    ? `<p class="nominations-source">★ <strong>공천</strong> 배지: ${state.nominations.source}</p>`
    : '';

  const html = `
    <div class="stats">
      <div class="stat"><div class="stat-label">총 예비후보자</div><div class="stat-value">${cands.length.toLocaleString()}명</div><div class="stat-sub">${state.data.fetched_at.slice(0,10)} 기준</div></div>
      <div class="stat"><div class="stat-label">시도지사 후보</div><div class="stat-value">${(byType['3'] || 0).toLocaleString()}명</div><div class="stat-sub">16개 광역단체 선거 (중복 포함)</div></div>
      <div class="stat"><div class="stat-label">기초단체장 후보</div><div class="stat-value">${(byType['4'] || 0).toLocaleString()}명</div><div class="stat-sub">227개 시군구 선거</div></div>
      <div class="stat"><div class="stat-label">참여 정당</div><div class="stat-value">${totalParties}개</div><div class="stat-sub">무소속 포함</div></div>
    </div>
    <h2 class="section-title">전국 지도</h2>
    <p class="section-hint">시도를 클릭하면 해당 지역의 후보자 상세로 이동합니다.</p>
    <div id="map"></div>
    <h2 class="section-title">시도별 후보자</h2>
    ${nomSource}
    <div class="sido-grid">
      ${sidos.map(sido => {
        const chiefs = sidoChiefCandidates(sido).length;
        const heads = dedupeByHuboid(cands.filter(c => String(c.sgTypecode) === '4' && c.sdName === sido)).length;
        const edu = dedupeByHuboid(cands.filter(c => String(c.sgTypecode) === '11' && c.sdName === sido)).length;
        const sggvars = dedupeByHuboid(cands.filter(c => String(c.sgTypecode) === '5' && c.sdName === sido)).length;
        return `
          <a href="#${encodeURIComponent(sido)}" class="sido-card">
            <div class="sido-card-name">${sido}</div>
            <div class="sido-card-stats">
              <div>시도지사 <strong>${chiefs}</strong></div>
              <div>기초단체장 <strong>${heads}</strong></div>
              <div>시도의원 <strong>${sggvars}</strong></div>
              <div>교육감 <strong>${edu}</strong></div>
            </div>
          </a>`;
      }).join('')}
    </div>`;
  const app = document.getElementById('app');
  app.innerHTML = html;
  app.classList.remove('loading');
  initHomeMap();
}

function renderSidoDetail(sidoName) {
  destroyMap();
  const cands = state.data.candidates;
  const chiefs = sidoChiefCandidates(sidoName);
  const educators = dedupeByHuboid(cands.filter(c => String(c.sgTypecode) === '11' && c.sdName === sidoName));
  const heads = dedupeByHuboid(cands.filter(c => String(c.sgTypecode) === '4' && c.sdName === sidoName));

  const headsBySgg = {};
  for (const c of heads) {
    const sgg = c.sggName || c.wiwName;
    if (!headsBySgg[sgg]) headsBySgg[sgg] = [];
    headsBySgg[sgg].push(c);
  }
  const sortedSggs = Object.keys(headsBySgg).sort(koSort);
  const chiefName = chiefs.length > 0 ? (chiefs[0].sggName || sidoName) : sidoName;

  const html = `
    <nav class="breadcrumb">
      <a href="#">전체</a> <span class="sep">›</span> <span class="current">${sidoName}</span>
    </nav>
    <div class="detail-head">
      <h2 class="detail-title">${sidoName}</h2>
      <div class="detail-inline-stats">
        <div><strong>${chiefs.length}</strong> 시도지사</div>
        <div><strong>${heads.length}</strong> 기초단체장</div>
        <div><strong>${sortedSggs.length}</strong> 시군구</div>
        <div><strong>${educators.length}</strong> 교육감</div>
      </div>
    </div>
    <h3 class="section-title">시도지사</h3>
    <div class="single-section">${candidateCard(chiefName, chiefs)}</div>
    <h3 class="section-title">교육감</h3>
    <div class="single-section">${candidateCard(sidoName + ' 교육감', educators)}</div>
    <h3 class="section-title">기초단체장</h3>
    ${sortedSggs.length === 0 ? '<p class="cc-empty">등록된 후보가 없습니다.</p>' :
      `<div class="basic-grid">${sortedSggs.map(sgg => candidateCard(sgg, headsBySgg[sgg])).join('')}</div>`}
  `;
  const app = document.getElementById('app');
  app.innerHTML = html;
  app.classList.remove('loading');
  window.scrollTo({ top: 0, behavior: 'instant' });
}

function route() {
  const hash = decodeURIComponent(location.hash.slice(1));
  if (!hash) renderHome();
  else renderSidoDetail(hash);
}

async function main() {
  calculateDDay();
  try {
    const [{ data, dateStr }, parties, geo, nominations] = await Promise.all([
      loadLatestPreliminary(),
      loadParties(),
      loadGeo(),
      loadNominations(),
    ]);
    state.data = data;
    state.parties = parties;
    state.geo = geo;
    state.nominations = nominations;
    state.dateStr = dateStr;
    document.getElementById('last-updated').textContent =
      `${dateStr.slice(0,4)}.${dateStr.slice(4,6)}.${dateStr.slice(6,8)}`;
    window.addEventListener('hashchange', route);
    route();
  } catch (e) {
    document.getElementById('app').innerHTML =
      `<div class="loading">데이터 로딩 실패: ${e.message}</div>`;
  }
}

main();
