const ELECTION_DATE = '2026-06-03T00:00:00';
const DISCLOSURE_LINK_END = '2026-06-04T00:00:00+09:00';

// 제9회 전국동시지방선거 공식 일정 (선관위 안내 기준)
const ELECTION_SCHEDULE = [
  { start: '2026-05-14', end: '2026-05-15', label: '후보자 등록',     note: '시·도지사, 단체장, 의원, 교육감, 국회의원 재·보궐' },
  { start: '2026-05-21', end: '2026-06-02', label: '선거운동 기간',   note: '13일간 공식 선거운동' },
  { start: '2026-05-29', end: '2026-05-30', label: '사전투표',         note: '오전 6시 ~ 오후 6시' },
  { start: '2026-06-03', end: '2026-06-03', label: '본투표',           note: '오전 6시 ~ 오후 6시' },
  { start: '2026-07-01', end: '2026-07-01', label: '당선인 임기 시작', note: '4년 임기' },
];

function nextElectionMilestone(now) {
  now = now || new Date();
  for (const m of ELECTION_SCHEDULE) {
    const end = new Date(m.end + 'T23:59:59+09:00');
    if (now <= end) {
      const start = new Date(m.start + 'T00:00:00+09:00');
      return { ...m, _now: now >= start };
    }
  }
  return null;
}

function renderScheduleBar() {
  const bar = document.getElementById('schedule-bar');
  if (!bar) return;
  const now = new Date();
  const m = nextElectionMilestone(now);
  if (!m) { bar.hidden = true; return; }
  bar.hidden = false;

  const fmt = d => `${d.slice(5,7)}/${d.slice(8,10)}`;
  const periodText = m.start === m.end ? fmt(m.start) : `${fmt(m.start)}~${fmt(m.end)}`;

  document.getElementById('schedule-label').textContent = m._now ? '진행 중' : '다음 일정';
  document.getElementById('schedule-event').textContent = m.label;
  document.getElementById('schedule-period').textContent = periodText;

  const startDate = new Date(m.start + 'T00:00:00+09:00');
  startDate.setHours(0,0,0,0);
  const today = new Date(now); today.setHours(0,0,0,0);
  const days = Math.ceil((startDate - today) / 86_400_000);
  const dEl = document.getElementById('schedule-dday');
  if (m._now) dEl.textContent = '오늘';
  else if (days > 0) dEl.textContent = `D-${days}`;
  else dEl.textContent = '';
}

// 전체 일정 페이지
function renderScheduleFull() {
  const app = document.getElementById('app');
  app.className = '';
  const now = new Date();
  const next = nextElectionMilestone(now);
  const rows = ELECTION_SCHEDULE.map(m => {
    const start = new Date(m.start + 'T00:00:00+09:00');
    const end = new Date(m.end + 'T23:59:59+09:00');
    const isPast = now > end;
    const isNow = now >= start && now <= end;
    const cls = isPast ? 'sched-past' : isNow ? 'sched-now' : 'sched-future';
    const status = isPast ? '종료' : isNow ? '진행 중' : '예정';
    const period = m.start === m.end ? m.start : `${m.start} ~ ${m.end}`;
    return `
      <tr class="${cls}">
        <td class="sched-status">${status}</td>
        <td class="sched-period">${period}</td>
        <td class="sched-label"><strong>${m.label}</strong></td>
        <td class="sched-note">${m.note || ''}</td>
      </tr>`;
  }).join('');

  app.innerHTML = `
    <nav class="breadcrumb"><a href="#">전국</a><span class="sep">›</span><span class="current">선거 일정</span></nav>
    <div class="detail-head">
      <h1 class="detail-title">제9회 전국동시지방선거 공식 일정</h1>
      <div class="detail-inline-stats">
        <span>${next ? `${next._now ? '오늘' : '다음'}: ${next.label}` : '모든 일정 종료'}</span>
      </div>
    </div>
    <p class="page-intro">중앙선거관리위원회 공식 안내 기준. 6월 3일 본투표를 향한 주요 마일스톤.</p>
    <section class="trend-section">
      <table class="hist-table sched-table">
        <thead>
          <tr><th>상태</th><th>일정</th><th>이벤트</th><th>비고</th></tr>
        </thead>
        <tbody>${rows}</tbody>
      </table>
    </section>`;
  window.scrollTo({ top: 0, behavior: 'instant' });
}

// 광주광역시·전라남도 일부 후보 데이터는 API에서 '전남광주통합특별시'로 반환됨.
// 선거구 코드와 대조해 시도의원은 실제 시도로 되돌리고, 단일 통합 선거는 alias로 양쪽 페이지에 노출한다.
const JOINT_SIDO = '전남광주통합특별시';
const JOINT_SIDO_MEMBERS = ['광주광역시', '전라남도'];
const SIDO_ALIASES = {
  '광주광역시': JOINT_SIDO,
  '전라남도': JOINT_SIDO,
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
  // sgTypecode=2: 6/3 지방선거와 동시 시행되는 국회의원 재·보궐 (결원 의석만)
  { id: 'mp',       sgTypecode: '2',  title: '국회의원(재·보궐)', card: true, detail: { layout: 'grid', groupBy: c => c.sggName || c.wiwName } },
  { id: 'chief',    sgTypecode: '3',  title: '시도지사',       useAlias: true, card: true, detail: { layout: 'single' } },
  { id: 'head',     sgTypecode: '4',  title: '기초단체장',     card: true, detail: { layout: 'grid', groupBy: c => c.sggName || c.wiwName } },
  { id: 'sidoMp',   sgTypecode: '5',  title: '시도의원',       card: true, detail: { layout: 'collapsible', groupBy: c => c.sggName || c.wiwName || '(미지정)' } },
  { id: 'wiwMp',    sgTypecode: '6',  title: '구시군의회의원', card: true, detail: { layout: 'collapsible', groupBy: c => c.sggName || c.wiwName || '(미지정)' } },
  { id: 'educator', sgTypecode: '11', title: '교육감',         useAlias: true, card: true, detail: { layout: 'single' } },
];
const SG_TITLE = {
  '2': '국회의원(재·보궐)',
  '3': '시도지사',
  '4': '기초단체장',
  '5': '시도의원',
  '6': '구시군의회의원',
  '8': '광역의원비례',
  '9': '기초의원비례',
  '11': '교육감',
};

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

const state = { data: null, parties: {}, nominations: null, dateStr: null, source: null, articles: null, articleMap: {}, candidateDetails: {}, candidateDetailsMeta: null, constituencies: null, addressIndex: null, jointConstituencySdMap: {}, changelog: null, timeseries: null, history: null, historyTurnout: null, historyCounting: null, criminalOcr: null, criminalOcrMap: {}, uncontestedCandidateSet: null, historyBattleFilter: 'top' };
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

function jointConstituencyKey(item) {
  return `${item.sgTypecode}|${item.sggName}`;
}

function buildJointConstituencySdMap(constituencies) {
  const out = {};
  for (const s of constituencies || []) {
    if (JOINT_SIDO_MEMBERS.includes(s.sdName) || s.sggName === JOINT_SIDO) {
      out[jointConstituencyKey(s)] = s.sdName;
    }
  }
  return out;
}

function normalizeCandidateRegions(candidates, constituencies) {
  const jointMap = buildJointConstituencySdMap(constituencies);
  return candidates.map(c => {
    if (c.sdName !== JOINT_SIDO || c.sggName === JOINT_SIDO) return c;
    const sdName = jointMap[jointConstituencyKey(c)];
    return sdName ? { ...c, sdName, sourceSdName: c.sdName } : c;
  });
}

function buildCandidateDetailsMap(payload) {
  const out = {};
  for (const d of payload?.details || []) {
    if (d.huboid) out[String(d.huboid)] = d;
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
function sidoDisplayName(label) {
  const value = String(label || '').trim();
  if (!value) return value;
  if (value === JOINT_SIDO) return '전남광주';
  const direct = SIDO_TAGS[value]?.[0];
  if (direct) return direct;
  const hit = Object.entries(SIDO_TAGS)
    .find(([sd, tags]) => tags.includes(value) || shortLocalName(sd) === value);
  return hit ? hit[1][0] : value;
}
const PARTY_TAGS = {
  '더불어민주당': ['민주당', '민주'],
  '국민의힘': ['국힘'],
  '조국혁신당': ['혁신당', '조국당'],
  '개혁신당': ['개혁'],
  '진보당': [],
  '정의당': [],
  '녹색정의당': ['정의'],
};

// 시트 태그에 등장하지만 후보 매칭에 쓰면 위험한 이름들.
// (1) 뉴탐사 공천대란 페이지의 NOT_PERSON 리스트를 기반으로 — 시트 운영자가 "후보가 아닌 인물·키워드"로 분류한 것.
// (2) 박지원·한동훈처럼 시트에선 일반 정치인을 가리키지만 후보 데이터엔 동명이인이 잡히는 케이스 보강.
// 시트엔 일반 정치인으로 등장하지만 출마자 데이터엔 동명이인이 잡히는 케이스.
// 본인 출마자(한동훈·송영길·박지원 등)는 제외 — 본인 보도가 본인에게 매칭되게.
const ARTICLE_IGNORE_NAMES = new Set([
  '이재명','이화영','백정화','박상용','장인수','함돈균','유시민','전우용','김성훈',
  '정천수','탁현민','박홍근','윤석열','이낙연','이제일','남성우','김성태',
  '김건희','방시혁','박대용','민희진','김두일',
]);

// 선거 직책 키워드 (시트가 "서울시장"·"강남구청장"처럼 직책으로 적는 케이스 대응).
function positionTagsForCandidate(c) {
  const type = String(c.sgTypecode || '');
  const sd = c.sdName || '';
  const sdShort = (SIDO_TAGS[sd] || [sd])[0] || sd;
  const wiw = c.wiwName || c.sggName || '';
  const out = [];
  if (type === '3') {
    if (sd.includes('특별시') || sd.includes('광역시')) out.push(`${sdShort}시장`);
    else out.push(`${sdShort}지사`, `${sdShort}도지사`);
  } else if (type === '4' && wiw) {
    if (wiw.endsWith('시')) out.push(`${wiw}장`, `${wiw}시장`);
    else if (wiw.endsWith('군')) out.push(`${wiw}수`, `${wiw}군수`);
    else if (wiw.endsWith('구')) out.push(`${wiw}청장`, `${wiw}장`);
    else out.push(`${wiw}장`);
  } else if (type === '11') {
    out.push(`${sdShort}교육감`, `${sd}교육감`);
  }
  return out.filter(Boolean);
}

// 뉴탐사 보도 태그 ↔ 후보 매칭. 다음 중 하나라도 만족하면 매칭(후보가 1명으로 좁혀질 때만):
//   ① 시트 태그에 후보의 직책 키워드(예: "서울시장","강남구청장")가 있음 — 강한 단서
//   ② 시트 태그에 후보의 정당과 지역이 모두 있음
//   ③ 후보 데이터에 같은 이름이 1명뿐 + 시트 태그에 지역 단서가 있음
// + ARTICLE_IGNORE_NAMES에 든 이름은 매칭 후보에서 제외(유명 정치인의 동명이인 차단).
function tagsForCandidate(c) {
  const sd = c.sdName || '', sgg = c.sggName || '', wiw = c.wiwName || '', jd = c.jdName || '';
  return {
    region: new Set([sd, sgg, wiw, ...(SIDO_TAGS[sd] || [])].filter(Boolean)),
    party:  new Set([jd, ...(PARTY_TAGS[jd] || [])].filter(Boolean)),
  };
}
function hasIntersection(a, b) { for (const x of a) if (b.has(x)) return true; return false; }

function buildArticleMap(articles, candidates) {
  if (!articles?.length || !candidates?.length) return {};
  const byName = {};
  for (const c of candidates) {
    if (!c.name || ARTICLE_IGNORE_NAMES.has(c.name)) continue;
    (byName[c.name] ||= []).push(c);
  }
  const nameCount = {};
  for (const k of Object.keys(byName)) nameCount[k] = byName[k].length;

  const map = {};
  for (const art of articles) {
    const tagSet = new Set(art.tags || []);
    for (const tag of art.tags || []) {
      const candList = byName[tag];
      if (!candList?.length) continue;
      const sole = nameCount[tag] === 1;
      const qualified = candList.filter(c => {
        // ① 직책 키워드 단독
        if (positionTagsForCandidate(c).some(p => tagSet.has(p))) return true;
        const t = tagsForCandidate(c);
        // ② 정당 + 지역
        if (hasIntersection(t.party, tagSet) && hasIntersection(t.region, tagSet)) return true;
        // ③ 후보가 데이터에 1명 + 지역
        if (sole && hasIntersection(t.region, tagSet)) return true;
        return false;
      });
      if (qualified.length !== 1) continue;
      const c = qualified[0];
      if (!c.huboid) continue;
      (map[c.huboid] ||= []).push(art);
    }
  }
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
  // 무소속은 정당 공천 개념 자체가 성립 안 함 — 배지 부여 금지
  if (!c.jdName || c.jdName === '무소속') return false;
  const groups = state.nominations[`sgTypecode_${c.sgTypecode}`];
  if (!groups) return false;
  // 두 형태 지원:
  //   ① 평면 {지역명:[...]}  — 시도지사용(시도명이 곧 선거구)
  //   ② 중첩 {시도명:{선거구명:[...]}}  — 동명 자치구 충돌 방지(국회의원·기초단체장 등)
  const flat = groups[c.sggName || c.sdName];
  let list = Array.isArray(flat) ? flat : null;
  if (!list) {
    const inner = groups[c.sdName];
    list = inner && typeof inner === 'object' ? inner[c.sggName] : null;
  }
  if (!Array.isArray(list)) return false;
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
const loadArticles = () => safeJson('data/articles.json', null);
const loadCandidateDetails = () => safeJson('data/candidate_details.json', null);
const loadConstituencies = () => safeJson('data/constituencies.json', null);
const loadAddressIndex = () => safeJson('data/address_index.json?v=202605161245', []);
const loadChangelog = () => safeJson('data/changelog.json', null);
const loadTimeseries = () => safeJson('data/timeseries.json', null);
const loadHistory = () => safeJson('data/history.json', null);
const loadHistoryTurnout = () => safeJson('data/history_turnout.json', null);
const loadHistoryCounting = () => safeJson('data/history_counting_results.json?v=202605180330', null);
const loadCriminalOcr = () => safeJson('data/criminal_ocr.json?v=202605171015', null);
let candidateDetailsPromise = null;
let addressIndexPromise = null;
let criminalOcrPromise = null;
let historyCountingPromise = null;

async function ensureCandidateDetails() {
  if (state.candidateDetailsMeta) return state.candidateDetailsMeta;
  if (!candidateDetailsPromise) {
    candidateDetailsPromise = loadCandidateDetails().then(payload => {
      state.candidateDetails = buildCandidateDetailsMap(payload);
      state.candidateDetailsMeta = payload || { details: [] };
      return state.candidateDetailsMeta;
    });
  }
  return candidateDetailsPromise;
}

async function ensureAddressIndex() {
  if (Array.isArray(state.addressIndex)) return state.addressIndex;
  if (!addressIndexPromise) {
    addressIndexPromise = loadAddressIndex().then(payload => {
      state.addressIndex = Array.isArray(payload) ? payload : [];
      return state.addressIndex;
    });
  }
  return addressIndexPromise;
}

async function ensureCriminalOcr() {
  if (state.criminalOcr) return state.criminalOcr;
  if (!criminalOcrPromise) {
    criminalOcrPromise = loadCriminalOcr().then(payload => {
      state.criminalOcr = payload || { records: [], categories: [], meta: {} };
      state.criminalOcrMap = buildCriminalOcrMap(state.criminalOcr);
      return state.criminalOcr;
    });
  }
  return criminalOcrPromise;
}

async function ensureHistoryCounting() {
  if (state.historyCounting) return state.historyCounting;
  if (!historyCountingPromise) {
    historyCountingPromise = loadHistoryCounting().then(payload => {
      state.historyCounting = payload || { elections: [] };
      return state.historyCounting;
    });
  }
  return historyCountingPromise;
}

// 라우팅용: 통합특별시는 광주/전남 중 광주로 진입 (alias 매핑이 양쪽 수용)
const sidoFor = obj => obj.sdName === JOINT_SIDO || obj.sd === JOINT_SIDO
  ? '광주광역시'
  : (obj.sdName || obj.sd);

// 합동 선거구명을 가독성 있게 분리 ("공주시부여군청양군" → "공주시·부여군·청양군").
// 규칙: (한글)(시|군|구)(한글) 패턴에서 다음 글자가 후속 식별자(갑·을·병·정·선·거·구)가 아닐 때만 분리.
// lookbehind로 prev 한글을 강제해 "군산", "구로" 같은 단어 시작의 군·구는 보존.
function prettifySgg(sgg) {
  if (!sgg) return sgg;
  return sgg.replace(/(?<=[가-힣])(시|군|구)(?=[가-힣])/g, (m, _p1, offset, full) => {
    const next = full[offset + 1];
    if (next && /[갑을병정선거구]/.test(next)) return m;
    return m + '·';
  });
}

// 선거구 라벨에 시도 약칭을 붙여 동명 구(서구·중구·동구 등) 모호함 제거.
// 예: "서구바선거구" → "광주 서구바선거구"
function formatRegionLabel(item) {
  const sd = item.sdName || item.sd || '';
  const sgg = item.sggName || item.sgg || '';
  // 통합특별시 같은 특수 케이스는 합쳐진 이름 그대로 표시
  if (sd === JOINT_SIDO || sgg === JOINT_SIDO) return sidoDisplayName(sgg || sd);
  if (!sgg || sgg === sd) return sidoDisplayName(sd || sgg);
  const sdShort = sidoDisplayName(sd);
  return `${sdShort} ${sgg}`;
}

function canonicalSidoName(label) {
  const value = String(label || '').trim();
  if (!value) return value;
  if (SIDO_ORDER.includes(value) || value === JOINT_SIDO) return value;
  const hit = Object.entries(SIDO_TAGS)
    .find(([sd, tags]) => tags.includes(value) || shortLocalName(sd) === value);
  return hit ? hit[0] : value;
}

// 경쟁률(후보 수 / 의석 수) 계산. SECTIONS의 sgTypecode만 대상.
const seatKey = c => {
  const sdName = c.sdName === JOINT_SIDO
    ? (state.jointConstituencySdMap[jointConstituencyKey(c)] || c.sdName)
    : c.sdName;
  return `${c.sgTypecode}|${sdName}|${c.sggName}`;
};

// 의석수 인덱스 + 선거구별 후보 수. 경쟁률·무투표 두 박스에서 공유.
// 사퇴·등록무효·사망은 '활성 후보'에서 제외(실질 경쟁률 정확도).
function isActiveCandidate(c) {
  return !c.status || c.status === '등록';
}
function buildSeatStats(allowedTypes = new Set(SECTIONS.map(s => s.sgTypecode))) {
  const constituencies = state.constituencies;
  if (!constituencies?.length) return null;
  const seats = {};
  for (const s of constituencies) {
    if (!allowedTypes.has(String(s.sgTypecode))) continue;
    seats[seatKey(s)] = parseInt(s.sggJungsu, 10) || 1;
  }
  const counts = {};
  const candidatesByKey = {};
  for (const c of state.data.candidates) {
    if (!allowedTypes.has(String(c.sgTypecode))) continue;
    if (!isActiveCandidate(c)) continue;
    const key = seatKey(c);
    counts[key] = (counts[key] || 0) + 1;
    (candidatesByKey[key] ||= []).push(c);
  }
  return { seats, counts, candidatesByKey };
}

function seatCountForCandidateGroup(list, stats = null) {
  if (!list?.length) return null;
  const seatStats = stats || buildSeatStats(new Set(list.map(c => String(c.sgTypecode)).filter(Boolean)));
  if (!seatStats) return null;
  const keys = new Set(list.map(c => seatKey(c)));
  let total = 0;
  for (const key of keys) total += seatStats.seats[key] || 0;
  return total || null;
}

function districtCompetitionMeta(list, stats = null) {
  const activeList = (list || []).filter(isActiveCandidate);
  const seat = seatCountForCandidateGroup(list, stats);
  const count = activeList.length;
  return {
    count,
    seat,
    ratio: seat ? count / seat : null,
    uncontested: !!seat && count > 0 && count <= seat,
  };
}

function districtCompetitionLabelFromValues(countValue, seatValue) {
  const count = Number(countValue) || 0;
  const seat = Number(seatValue) || 0;
  if (!seat) return `<span class="district-meta"><span>후보 ${count}명</span></span>`;
  const ratio = `${formatCompetitionRatio(count / seat)}:1`;
  const uncontested = count > 0 && count <= seat;
  return `<span class="district-meta"><span>후보 ${count.toLocaleString()}명</span><span>· 정원 ${seat.toLocaleString()}석</span><span class="district-ratio">· ${ratio}</span>${uncontested ? '<span class="district-flag">무투표</span>' : ''}</span>`;
}

function districtCompetitionLabel(list, stats = null) {
  const meta = districtCompetitionMeta(list, stats);
  return districtCompetitionLabelFromValues(meta.count, meta.seat);
}

function formatCompetitionRatio(value) {
  const num = Number(value) || 0;
  return Number.isInteger(num) ? String(num) : num.toFixed(1);
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

function buildCompetitionSummary() {
  const stats = buildSeatStats();
  if (!stats) return null;
  const bySido = {};
  let seats = 0;
  let candidates = 0;
  let districts = 0;

  for (const [k, seat] of Object.entries(stats.seats)) {
    const [, sd] = k.split('|');
    const count = stats.counts[k] || 0;
    seats += seat;
    candidates += count;
    districts += 1;
    const row = bySido[sd] || { sd, seats: 0, candidates: 0, districts: 0 };
    row.seats += seat;
    row.candidates += count;
    row.districts += 1;
    bySido[sd] = row;
  }

  const regions = Object.values(bySido).map(r => ({
    ...r,
    ratio: r.seats ? r.candidates / r.seats : 0,
  })).sort((a, b) => b.ratio - a.ratio || sidoSort(a.sd, b.sd));

  return {
    national: {
      seats,
      candidates,
      districts,
      ratio: seats ? candidates / seats : 0,
    },
    regions,
  };
}

// 무투표 당선 집계. 비례대표는 한 정당 명부만 등록된 경우도 선관위 보도 집계와 맞춘다.
const UNCONTESTED_SG_TYPES = new Set(['4', '5', '6', '8', '9']);
function buildUncontestedList() {
  const stats = buildSeatStats(UNCONTESTED_SG_TYPES);
  if (!stats) return {
    tied: [], short: [], singlePartyPr: [], zero: [],
    totalCandidates: 0, totalDistricts: 0, proportionalCandidates: 0, nonProportionalCandidates: 0,
  };
  const tied = [], short = [], singlePartyPr = [], zero = [];
  for (const [k, seat] of Object.entries(stats.seats)) {
    const count = stats.counts[k] || 0;
    const [sgType, sd, sgg] = k.split('|');
    const isProportional = ['8', '9'].includes(String(sgType));
    const parties = new Set((stats.candidatesByKey[k] || []).map(c => c.jdName || c.party || '무소속'));
    const isSinglePartyPr = isProportional && count > seat && count > 0 && parties.size === 1;
    if (count > seat && !isSinglePartyPr) continue;
    const row = {
      sgType,
      sd,
      sgg,
      count,
      seat,
      title: SG_TITLE[sgType] || sgType,
      isProportional,
      isSinglePartyPr,
    };
    if (count === 0) zero.push(row);
    else if (isSinglePartyPr) singlePartyPr.push(row);
    else if (count < seat) short.push(row);
    else tied.push(row);
  }
  const cmp = (a, b) => sidoSort(a.sd, b.sd) || koSort(a.sgg || '', b.sgg || '');
  tied.sort(cmp);
  short.sort(cmp);
  singlePartyPr.sort(cmp);
  zero.sort(cmp);
  const candidateRows = [...tied, ...short, ...singlePartyPr];
  const totalCandidates = candidateRows.reduce((sum, r) => sum + r.count, 0);
  const proportionalCandidates = candidateRows
    .filter(r => r.isProportional)
    .reduce((sum, r) => sum + r.count, 0);
  return {
    tied,
    short,
    singlePartyPr,
    zero,
    totalCandidates,
    totalDistricts: candidateRows.length,
    proportionalCandidates,
    nonProportionalCandidates: totalCandidates - proportionalCandidates,
  };
}

function uncontestedCandidateSet() {
  if (state.uncontestedCandidateSet) return state.uncontestedCandidateSet;
  const out = new Set();
  const stats = buildSeatStats(UNCONTESTED_SG_TYPES);
  if (!stats) {
    state.uncontestedCandidateSet = out;
    return out;
  }
  for (const [key, seat] of Object.entries(stats.seats)) {
    const candidates = stats.candidatesByKey[key] || [];
    const count = stats.counts[key] || 0;
    if (!count) continue;
    const [sgType] = key.split('|');
    const isProportional = ['8', '9'].includes(String(sgType));
    const parties = new Set(candidates.map(c => c.jdName || c.party || '무소속'));
    const isSinglePartyPr = isProportional && count > seat && parties.size === 1;
    if (count <= seat || isSinglePartyPr) {
      candidates.forEach(c => {
        if (c.huboid) out.add(String(c.huboid));
      });
    }
  }
  state.uncontestedCandidateSet = out;
  return out;
}

function isUncontestedCandidate(c) {
  return isActiveCandidate(c) && uncontestedCandidateSet().has(String(c.huboid || ''));
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
    const r = await fetch(`data/${source}/20260603/snapshot_${dateStr}.json`).catch(() => null);
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

// 후보 → 뉴탐사 제보 페이지로 직접 연결. 후보명·지역구·정당을 제목에 미리 채워 보냄.
function tipoffUrl(c) {
  const region = [c.sdName, c.sggName].filter(Boolean).join(' ');
  const titleMap = { '2': '국회의원(재·보궐)', '3': '시도지사', '4': '기초단체장', '5': '시도의원', '6': '구시군의회의원', '11': '교육감' };
  const sect = titleMap[String(c.sgTypecode)] || '';
  const subject = `[제보] ${c.name} (${c.jdName || '무소속'}) · ${region} ${sect}`.trim();
  return `https://tipoff.newtamsa.org/?subject=${encodeURIComponent(subject)}`;
}

// 후보 등록 상태 분류: '등록' 외에는 비활성으로 시각 표시
const STATUS_BADGE = {
  '사퇴':    { cls: 'withdrawn', label: '사퇴', tip: '후보 본인의 자진 사퇴' },
  '등록무효': { cls: 'invalid',   label: '무효', tip: '선관위 직권 등록무효 (자격 결격·서류 미비 등)' },
  '사망':    { cls: 'deceased',  label: '사망', tip: '후보자 사망 (자동 등록무효)' },
};

function candidateRow(c) {
  const confirmed = isConfirmed(c);
  const articles = state.articleMap?.[c.huboid] || [];
  const hasArt = articles.length > 0;
  const aid = hasArt ? `art-${c.huboid}` : '';
  const tipTitle = `${c.name} 후보 관련 제보 — 뉴탐사`;
  const statusInfo = STATUS_BADGE[c.status];
  const statusBadge = statusInfo
    ? `<span class="status-badge status-${statusInfo.cls}" title="${statusInfo.tip}" data-tip="${statusInfo.tip}">${statusInfo.label}</span>`
    : '';
  const uncontestedBadge = isUncontestedCandidate(c)
    ? `<span class="uncontested-badge" title="등록 후보 수가 의원정수 이하인 무투표 당선 선거구 후보">무투표 당선</span>`
    : '';
  return `
    <div class="candidate${confirmed ? ' confirmed' : ''}${statusInfo ? ' candidate-inactive' : ''}">
      <div class="candidate-color" style="background:${partyColor(c.jdName)}"></div>
      <button type="button" class="candidate-name candidate-detail-trigger" data-huboid="${c.huboid}" title="${c.name} 상세 정보">${c.name}${uncontestedBadge}${statusBadge}${confirmed ? '<span class="confirmed-badge">공천</span>' : ''}</button>
      <div class="candidate-party">${c.jdName}</div>
      <span class="candidate-actions">
        ${hasArt ? `<button type="button" class="article-toggle" data-target="${aid}" title="뉴탐사 관련 보도 ${articles.length}건">📰 ${articles.length}</button>` : ''}
        <a class="tip-button" href="${tipoffUrl(c)}" target="_blank" rel="noopener" aria-label="${tipTitle}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 6h16a1 1 0 0 1 1 1v10a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1Z"/><path d="m3 7 9 6 9-6"/></svg></a>
      </span>
    </div>
    ${hasArt ? `<ul class="article-list" id="${aid}" hidden>${articleListHtml(articles)}</ul>` : ''}`;
}

// ============ 공유 (Web Share API + clipboard fallback) ============
function showToast(msg) {
  let toast = document.getElementById('toast');
  if (!toast) {
    toast = document.createElement('div');
    toast.id = 'toast';
    toast.className = 'toast';
    document.body.appendChild(toast);
  }
  toast.textContent = msg;
  toast.classList.add('show');
  clearTimeout(showToast._t);
  showToast._t = setTimeout(() => toast.classList.remove('show'), 1800);
}

async function shareLink(title, url) {
  if (navigator.share) {
    try { await navigator.share({ title, url }); return; }
    catch (e) { if (e.name === 'AbortError') return; /* 사용자 취소 */ }
  }
  try {
    await navigator.clipboard.writeText(url);
    showToast('링크가 복사되었습니다');
  } catch {
    // 매우 오래된 브라우저: prompt로 직접 노출
    window.prompt('링크 복사:', url);
  }
}

function candidateShareUrl(huboid) {
  return `${location.origin}${location.pathname}#cand/${huboid}`;
}

// ============ 후보 상세 모달 ============
function formatBirthday(s) {
  if (!s || s.length < 8) return '';
  return `${s.slice(0,4)}.${s.slice(4,6)}.${s.slice(6,8)}`;
}
function formatRegdate(s) {
  return s && s.length >= 8 ? `${s.slice(0,4)}.${s.slice(4,6)}.${s.slice(6,8)}` : '';
}
function moneyDisclosure(value) {
  const thousandKrw = parseDisclosureNumber(value);
  if (thousandKrw == null) return '';
  if (thousandKrw === 0) return '0원';
  const abs = Math.abs(thousandKrw);
  if (abs >= 100000) return formatEok(thousandKrw);
  if (abs >= 10) {
    const manwon = thousandKrw / 10;
    const digits = Number.isInteger(manwon) || Math.abs(manwon) >= 100 ? 0 : 1;
    return `${manwon.toLocaleString('ko-KR', { maximumFractionDigits: digits })}만원`;
  }
  return `${(thousandKrw * 1000).toLocaleString('ko-KR')}원`;
}

const CRIME_CATEGORY_META = {
  '사기': { group: '공직 검증', tone: 'priority', order: 10 },
  '횡령': { group: '공직 검증', tone: 'priority', order: 11 },
  '배임': { group: '공직 검증', tone: 'priority', order: 12 },
  '뇌물': { group: '공직 검증', tone: 'priority', order: 13 },
  '정치자금법': { group: '공직 검증', tone: 'priority', order: 14 },
  '공직선거법': { group: '공직 검증', tone: 'priority', order: 15 },
  '청탁금지법': { group: '공직 검증', tone: 'priority', order: 16 },
  '직권남용': { group: '공직 검증', tone: 'priority', order: 17 },
  '허위공문서·문서위조·공용서류': { group: '공직 검증', tone: 'priority', order: 18 },
  '성범죄': { group: '공직 검증', tone: 'priority', order: 22 },
  '특가법': { group: '공직 검증', tone: 'priority', order: 24 },
  '음주·위험운전': { group: '공직 검증', tone: 'priority', order: 25 },
  '무면허운전': { group: '공직 검증', tone: 'priority', order: 26 },
  '절도': { group: '공직 검증', tone: 'priority', order: 28 },
  '조세': { group: '공직 검증', tone: 'priority', order: 29 },
  '보조금': { group: '공직 검증', tone: 'priority', order: 30 },
  '폭력': { group: '폭력·질서', tone: 'standard', order: 40 },
  '공무집행방해': { group: '폭력·질서', tone: 'standard', order: 41 },
  '업무방해': { group: '폭력·질서', tone: 'standard', order: 42 },
  '재물손괴': { group: '폭력·질서', tone: 'standard', order: 43 },
  '주거침입': { group: '폭력·질서', tone: 'standard', order: 44 },
  '범인도피': { group: '폭력·질서', tone: 'standard', order: 45 },
  '사법방해': { group: '폭력·질서', tone: 'standard', order: 46 },
  '입찰방해': { group: '폭력·질서', tone: 'standard', order: 47 },
  '교통사고': { group: '교통·안전 법규', tone: 'standard', order: 50 },
  '도로교통': { group: '교통·안전 법규', tone: 'standard', order: 51 },
  '자동차관리': { group: '교통·안전 법규', tone: 'standard', order: 52 },
  '보험·금융': { group: '경제·금융 법규', tone: 'standard', order: 60 },
  '환경': { group: '생활·안전 법규', tone: 'standard', order: 70 },
  '식품·보건': { group: '생활·안전 법규', tone: 'standard', order: 71 },
  '교육·청소년': { group: '생활·안전 법규', tone: 'standard', order: 72 },
  '노동': { group: '생활·안전 법규', tone: 'standard', order: 73 },
  '농수산': { group: '생활·안전 법규', tone: 'standard', order: 74 },
  '건축·건설·부동산': { group: '생활·안전 법규', tone: 'standard', order: 75 },
  '총포·화약': { group: '생활·안전 법규', tone: 'standard', order: 76 },
  '야생생물': { group: '생활·안전 법규', tone: 'standard', order: 77 },
  '국가공무원법': { group: '공직·행정 법규', tone: 'standard', order: 80 },
  '지방공무원법': { group: '공직·행정 법규', tone: 'standard', order: 81 },
  '국가보안법': { group: '시국·안보 관련', tone: 'context', order: 90 },
  '집시법': { group: '집회·시위 관련', tone: 'context', order: 91 },
  '명예훼손': { group: '기타', tone: 'standard', order: 100 },
  '모욕': { group: '기타', tone: 'standard', order: 101 },
  '저작권법': { group: '기타', tone: 'standard', order: 102 },
  '마약': { group: '기타', tone: 'standard', order: 103 },
  '도박': { group: '기타', tone: 'standard', order: 104 },
};

function crimeCategoryMeta(category) {
  return CRIME_CATEGORY_META[category] || { group: '기타', tone: 'standard', order: 999 };
}

function compareCrimeCategories(a, b) {
  const am = crimeCategoryMeta(a.category || a);
  const bm = crimeCategoryMeta(b.category || b);
  return am.order - bm.order || (b.count || 0) - (a.count || 0) || koSort(a.category || a, b.category || b);
}

function necDetailUrlForHuboid(huboid) {
  return state.candidateDetails?.[String(huboid || '')]?.nec_detail_url || '';
}

function criminalDisclosureValue(record, necDetailUrl) {
  const text = String(record || '').trim();
  if (!text || parseCriminalCount(text) <= 0 || !necDetailUrl) return text;
  return `<a class="modal-field-link" href="${escapeHtml(necDetailUrl)}" target="_blank" rel="noopener" title="선관위 후보자 정보공개에서 전과 상세 확인">${escapeHtml(text)} 선관위에서 확인</a>`;
}

function buildCriminalOcrMap(payload) {
  return Object.fromEntries((payload?.records || [])
    .filter(r => r?.huboid)
    .map(r => [String(r.huboid), r]));
}

function criminalOcrRecords() {
  return Array.isArray(state.criminalOcr?.records) ? state.criminalOcr.records : [];
}

function criminalOcrRecordFor(huboid) {
  return state.criminalOcrMap[String(huboid || '')] || null;
}

function criminalCategoryHref(category) {
  return `#criminal/${encodeURIComponent(category)}`;
}

function criminalOcrCategoriesHtml(record, currentCategory = '') {
  const categories = (record?.categories || []).filter(Boolean).sort(compareCrimeCategories);
  if (!categories.length) return '';
  return `<span class="crime-tags">${categories.map(cat => `
    <a class="crime-tag crime-tag-${crimeCategoryMeta(cat).tone}${cat === currentCategory ? ' active' : ''}" href="${criminalCategoryHref(cat)}">${escapeHtml(cat)}</a>
  `).join('')}</span>`;
}

function findCandidateByHuboid(huboid) {
  const id = String(huboid || '');
  return (state.data?.candidates || []).find(c => String(c.huboid) === id) || null;
}

async function openCandidateModal(huboid) {
  const c = state.data.candidates.find(x => x.huboid === huboid);
  if (!c) return;
  const root = document.getElementById('modal-root');
  if (!root) return;
  root.innerHTML = `
    <div class="modal-backdrop" data-modal-close></div>
    <div class="modal-dialog" role="dialog" aria-modal="true">
      <button type="button" class="modal-close" data-modal-close aria-label="닫기">×</button>
      <p class="loading">후보자 공개정보를 불러오는 중입니다.</p>
    </div>`;
  root.hidden = false;
  document.body.classList.add('modal-open');
  await ensureCandidateDetails();

  const confirmed = isConfirmed(c);
  const modalUncontestedBadge = isUncontestedCandidate(c)
    ? `<span class="uncontested-badge modal-uncontested-badge" title="등록 후보 수가 의원정수 이하인 무투표 당선 선거구 후보">무투표 당선</span>`
    : '';
  const articles = state.articleMap?.[c.huboid] || [];
  const titleMap = Object.fromEntries(SECTIONS.map(s => [s.sgTypecode, s.title]));
  const sectionTitle = titleMap[c.sgTypecode] || '';
  const region = formatRegionLabel(c);
  const birth = formatBirthday(c.birthday);
  const regdate = formatRegdate(c.regdate);
  const nec = state.candidateDetails?.[String(c.huboid)] || null;
  const disclosures = nec?.disclosures || {};
  const photo = nec?.photo || {};
  const photoSrc = photo.cached_thumbnail_url || photo.thumbnail_url || '';
  const photoUrl = photo.url || photo.thumbnail_url || photoSrc;
  const photoHtml = photoSrc ? `
    <figure class="modal-photo">
      <a href="${photoUrl}" target="_blank" rel="noopener" title="후보자 사진 보기">
        <img src="${photoSrc}" alt="${c.name} 후보자 사진" loading="eager" decoding="async" fetchpriority="high">
      </a>
    </figure>` : '';
  const necDetailUrl = nec?.nec_detail_url || '';
  const hasCriminalRecord = parseCriminalCount(disclosures.criminal_record) > 0;
  if (hasCriminalRecord) await ensureCriminalOcr();
  const criminalOcrRecord = criminalOcrRecordFor(c.huboid);

  // 필드 정의: 값이 있는 것만 표시
  const fields = [
    ['정당',   c.jdName || '무소속'],
    ['선거',   sectionTitle],
    ['선거구', region],
    ['상태',   c.status ? `${c.status}${STATUS_BADGE[c.status] ? ` <small style="color:var(--ink-sub)">— ${STATUS_BADGE[c.status].tip}</small>` : ''}` : ''],
    ['성별',   c.gender || ''],
    ['생년',   birth ? `${birth}${c.age ? ` (만 ${c.age}세)` : ''}` : ''],
    ['한자',   c.hanjaName || ''],
    ['직업',   c.job || ''],
    ['학력',   c.edu || ''],
    ['경력 ①', c.career1 || ''],
    ['경력 ②', c.career2 || ''],
    ['주소',   c.addr || ''],
    ['등록일', regdate],
    ['재산',   moneyDisclosure(disclosures.assets_thousand_krw)],
    ['병역',   disclosures.military || ''],
    ['납부액', moneyDisclosure(disclosures.tax_paid_thousand_krw)],
    ['체납',   disclosures.tax_arrears_5y_thousand_krw || disclosures.tax_arrears_current_thousand_krw
      ? `최근 5년 ${moneyDisclosure(disclosures.tax_arrears_5y_thousand_krw) || '0원'} · 현재 ${moneyDisclosure(disclosures.tax_arrears_current_thousand_krw) || '0원'}`
      : ''],
    ['전과',   criminalDisclosureValue(disclosures.criminal_record, necDetailUrl)],
    ['전과 유형', criminalOcrCategoriesHtml(criminalOcrRecord)],
    ['입후보', disclosures.candidacy_count || ''],
  ].filter(([, v]) => v);

  const fieldsHtml = fields.map(([k, v]) =>
    `<div class="modal-field"><dt>${k}</dt><dd>${v}</dd></div>`
  ).join('');

  const articlesHtml = articles.length ? `
    <section class="modal-section">
      <h3 class="modal-section-title">관련 보도 <span class="modal-section-sub">${articles.length}건 · 뉴탐사 공천대란 매칭</span></h3>
      <ul class="modal-articles">${articleListHtml(articles)}</ul>
    </section>` : '';
  const criminalHtml = hasCriminalRecord && necDetailUrl ? `
    <section class="modal-section">
      <h3 class="modal-section-title">전과 상세 <span class="modal-section-sub">선관위 후보자 정보공개</span></h3>
      <p class="trend-meta">PDF 파일을 직접 제공하지 않고 선관위 후보자 상세 페이지로 연결합니다. 원문 열람 여부와 공개 범위는 선관위 페이지 기준입니다.</p>
      <ul class="modal-articles">
        <li><a href="${escapeHtml(necDetailUrl)}" target="_blank" rel="noopener">선관위에서 전과 원문 확인</a></li>
      </ul>
    </section>` : '';

  const tipUrl = tipoffUrl(c);
  const necLink = necDetailUrl
    ? `<a class="modal-share modal-link" href="${escapeHtml(necDetailUrl)}" target="_blank" rel="noopener">선관위 상세</a>`
    : '';

  root.innerHTML = `
    <div class="modal-backdrop" data-modal-close></div>
    <div class="modal-dialog" role="dialog" aria-modal="true" aria-labelledby="modal-name">
      <button type="button" class="modal-close" data-modal-close aria-label="닫기">×</button>
      <div class="modal-profile">
        ${photoHtml}
        <header class="modal-head" style="border-left-color:${partyColor(c.jdName)}">
          <p class="modal-region">${region} · ${sectionTitle}</p>
          <h2 id="modal-name" class="modal-name">${c.name}
            ${confirmed ? '<span class="confirmed-badge">공천</span>' : ''}
            ${modalUncontestedBadge}
          </h2>
          <p class="modal-subline">${c.jdName || '무소속'}${c.status ? ` · ${c.status}` : ''}</p>
        </header>
      </div>
      <dl class="modal-fields">${fieldsHtml}</dl>
      ${articlesHtml}
      ${criminalHtml}
      <footer class="modal-foot">
        <div class="modal-actions">
          <a class="modal-tip" href="${tipUrl}" target="_blank" rel="noopener">📮 이 후보 제보하기</a>
          ${necLink}
          <button type="button" class="modal-share" data-share-cand="${c.huboid}" data-share-title="${c.name} (${c.jdName || '무소속'}) — ${region}">🔗 링크 공유</button>
        </div>
        <p class="modal-source">기준: 중앙선관위 후보자 공개정보 · ${state.dateStr ? `${state.dateStr.slice(0,4)}.${state.dateStr.slice(4,6)}.${state.dateStr.slice(6,8)} ${SOURCE_LABEL[state.source] || state.source}` : ''}</p>
      </footer>
    </div>`;
  root.hidden = false;
  document.body.classList.add('modal-open');
  // 닫기 버튼에 포커스
  root.querySelector('.modal-close')?.focus();
}

function closeCandidateModal() {
  const root = document.getElementById('modal-root');
  if (!root) return;
  root.hidden = true;
  root.innerHTML = '';
  document.body.classList.remove('modal-open');
}

function candidateCard(label, list, opts = {}) {
  const countHtml = opts.showCompetition
    ? districtCompetitionLabel(list, opts.seatStats)
    : `<span class="district-meta"><span>${list.length.toLocaleString()}명</span></span>`;
  return `
    <div class="candidate-card">
      <div class="cc-header">
        <div class="cc-name">${label}</div>
        <div class="cc-count">${countHtml}</div>
      </div>
      ${list.length === 0 ? '<div class="cc-empty">등록된 후보가 없습니다.</div>' : list.map(candidateRow).join('')}
    </div>`;
}

// ============ 내 주소로 후보 찾기 ============
function compactAddressText(value) {
  return String(value || '')
    .replace(/[()\[\],.·ㆍ-]/g, '')
    .replace(/\s+/g, '')
    .trim();
}

function escapeHtml(value) {
  return String(value ?? '').replace(/[&<>"']/g, ch => ({
    '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;',
  }[ch]));
}

function shortLocalName(name) {
  return String(name || '').replace(/(특별시|광역시|특별자치시|특별자치도|자치도|시|군|구)$/g, '');
}

function localNameVariants(name) {
  const raw = String(name || '').trim();
  if (!raw) return [];
  const compact = compactAddressText(raw);
  const out = new Set([compact]);
  out.add(shortLocalName(compact));

  const cityWard = compact.match(/^(.+시)(.+구)$/);
  if (cityWard) {
    const cityShort = shortLocalName(cityWard[1]);
    out.add(`${cityShort}${cityWard[2]}`);
    out.add(cityWard[2]);
    out.add(shortLocalName(cityWard[2]));
  }

  return [...out].filter(Boolean).sort((a, b) => b.length - a.length);
}

function buildAddressUnits() {
  const bySd = {};
  const add = (sd, kind, name) => {
    if (!sd || !name || sd === JOINT_SIDO) return;
    (bySd[sd] ||= { base: new Set(), wiw: new Set() });
    bySd[sd][kind].add(name);
  };

  for (const s of state.constituencies || []) {
    const code = String(s.sgTypecode || '');
    if (code === '4' || code === '9') add(s.sdName, 'base', s.sggName);
    if (s.wiwName) add(s.sdName, 'wiw', s.wiwName);
  }
  for (const c of state.data?.candidates || []) {
    const code = String(c.sgTypecode || '');
    if (code === '4' || code === '9') add(c.sdName, 'base', c.sggName);
    if (c.wiwName) add(c.sdName, 'wiw', c.wiwName);
  }

  for (const units of Object.values(bySd)) {
    for (const base of units.base) units.wiw.add(base);
  }
  return bySd;
}

function findSidoInAddress(query) {
  const compact = compactAddressText(query);
  let best = null;
  for (const sd of SIDO_ORDER) {
    const aliases = [sd, ...(SIDO_TAGS[sd] || [])];
    for (const alias of aliases) {
      const hit = compactAddressText(alias);
      if (!hit || !compact.includes(hit)) continue;
      if (!best || hit.length > best.len) best = { sd, len: hit.length };
    }
  }
  return best?.sd || '';
}

function findBestLocalName(names, query) {
  const compact = compactAddressText(query);
  let best = null;
  for (const name of names || []) {
    for (const variant of localNameVariants(name)) {
      if (!variant || !compact.includes(variant)) continue;
      const score = variant.length * 10 + compactAddressText(name).length;
      if (!best || score > best.score) best = { name, score };
    }
  }
  return best?.name || '';
}

function inferBaseWiw(units, detailWiw, query) {
  const bases = [...(units?.base || [])].sort((a, b) => b.length - a.length);
  if (!bases.length) return detailWiw || '';
  if (detailWiw) {
    const exact = bases.find(b => b === detailWiw);
    if (exact) return exact;
    const prefix = bases.find(b => compactAddressText(detailWiw).startsWith(compactAddressText(b)));
    if (prefix) return prefix;
  }
  return findBestLocalName(bases, query) || '';
}

function extractEmdName(query, sd, detailWiw, baseWiw) {
  let text = String(query || '');
  for (const part of [sd, ...(SIDO_TAGS[sd] || []), detailWiw, baseWiw]) {
    if (part) text = text.replace(part, ' ');
  }
  const tokens = text.split(/\s+/).map(t => t.trim()).filter(Boolean);
  const hit = [...tokens].reverse().find(t => /[읍면동가리]$/.test(t));
  return hit || '';
}

function isRoadNameToken(token) {
  const text = compactAddressText(token);
  if (text.length < 2) return false;
  return /(대로|로|길)$/.test(text)
    || /(대로|로)\d/.test(text)
    || /(대로|로)[가-힣A-Za-z]*\d.*길$/.test(text);
}

function extractRoadName(query, sd, detailWiw, baseWiw) {
  let text = String(query || '');
  for (const part of [sd, ...(SIDO_TAGS[sd] || []), detailWiw, baseWiw]) {
    if (part) text = text.replace(part, ' ');
  }
  const tokens = text.split(/\s+/).map(t => t.trim()).filter(Boolean);
  const hit = [...tokens].reverse().find(isRoadNameToken);
  return hit || '';
}

function parseAddressQuery(query) {
  const sd = findSidoInAddress(query);
  const unitsBySd = buildAddressUnits();
  const units = sd ? unitsBySd[sd] : null;
  const detailWiw = units ? findBestLocalName([...(units.wiw || [])], query) : '';
  const baseWiw = units ? inferBaseWiw(units, detailWiw, query) : '';
  return {
    raw: String(query || '').trim(),
    sd,
    detailWiw,
    baseWiw,
    emd: extractEmdName(query, sd, detailWiw, baseWiw),
    road: extractRoadName(query, sd, detailWiw, baseWiw),
  };
}

function emdShortName(name) {
  return String(name || '').replace(/(읍|면|동|리)$/g, '');
}

function addressUnitKind(unit) {
  return unit?.kind === 'road' ? 'road' : 'emd';
}

function addressUnitName(unit) {
  return addressUnitKind(unit) === 'road'
    ? (unit.roadName || unit.emdName || '')
    : (unit.emdName || '');
}

function addressSearchEntries(unit) {
  const sdNames = [unit.sdName, ...(SIDO_TAGS[unit.sdName] || []), shortLocalName(unit.sdName)];
  const sggNames = [unit.sggName, ...localNameVariants(unit.sggName)];
  const isRoad = addressUnitKind(unit) === 'road';
  const unitName = addressUnitName(unit);
  const unitNames = isRoad
    ? [unitName]
    : [unitName, emdShortName(unitName)];
  const entries = [];
  const add = (value, weight) => {
    const text = compactAddressText(value);
    if (text) entries.push({ text, weight });
  };

  for (const name of unitNames) add(name, isRoad ? 11000 : 10000);
  for (const sgg of sggNames) {
    for (const name of unitNames) add(`${sgg}${name}`, isRoad ? 9000 : 8200);
  }
  for (const sd of sdNames) {
    for (const name of unitNames) add(`${sd}${name}`, isRoad ? 8400 : 7600);
    for (const sgg of sggNames) {
      for (const name of unitNames) add(`${sd}${sgg}${name}`, isRoad ? 7800 : 7000);
    }
  }
  add(unit.fullName, isRoad ? 7200 : 6400);

  return entries;
}

function addressSuggestionScore(unit, query) {
  const q = compactAddressText(query);
  if (q.length < 2) return 0;
  let best = 0;
  for (const { text, weight } of addressSearchEntries(unit)) {
    if (text === q) best = Math.max(best, weight + 1000);
    else if (text.startsWith(q)) best = Math.max(best, weight - text.length);
    else {
      const idx = text.indexOf(q);
      if (idx >= 0) best = Math.max(best, weight - 2000 - idx);
    }
  }
  return best;
}

function searchAddressUnits(query, limit = 8) {
  const q = compactAddressText(query);
  if (q.length < 2 || !Array.isArray(state.addressIndex)) return [];
  return state.addressIndex
    .map(unit => ({ unit, score: addressSuggestionScore(unit, q) }))
    .filter(x => x.score > 0)
    .sort((a, b) => {
      if (b.score !== a.score) return b.score - a.score;
      const sdDiff = sidoSort(a.unit.sdName, b.unit.sdName);
      if (sdDiff) return sdDiff;
      const sggDiff = koSort(a.unit.sggName, b.unit.sggName);
      if (sggDiff) return sggDiff;
      return koSort(addressUnitName(a.unit), addressUnitName(b.unit));
    })
    .slice(0, limit);
}

function addressSuggestionHtml(unit) {
  const isRoad = addressUnitKind(unit) === 'road';
  const kindText = isRoad ? ' · 도로명' : '';
  return `
    <button type="button" class="address-suggestion" data-address-full="${escapeHtml(unit.fullName)}">
      <strong>${escapeHtml(addressUnitName(unit))}</strong>
      <span>${escapeHtml(unit.fullName)}${kindText}</span>
    </button>`;
}

function clearAddressSuggestions() {
  const box = document.getElementById('address-suggestions');
  if (!box) return;
  box.hidden = true;
  box.innerHTML = '';
}

function renderAddressSuggestions(query, force = false) {
  const box = document.getElementById('address-suggestions');
  if (!box) return [];
  const matches = searchAddressUnits(query, force ? 12 : 8);
  if (!matches.length || (!force && compactAddressText(query).length < 2)) {
    clearAddressSuggestions();
    return [];
  }
  box.hidden = false;
  box.innerHTML = matches.map(x => addressSuggestionHtml(x.unit)).join('');
  return matches.map(x => x.unit);
}

function chooseAddressSuggestion(fullName) {
  const input = document.getElementById('address-input');
  if (input) input.value = fullName;
  clearAddressSuggestions();
  renderAddressLookup(fullName);
}

function resolveAddressLookup(query) {
  const raw = String(query || '').trim();
  const lookup = parseAddressQuery(raw);
  if (lookup.sd || !raw) return { raw, lookup, matches: [] };
  const matches = searchAddressUnits(raw, 12).map(x => x.unit);
  if (matches.length === 1) {
    return { raw: matches[0].fullName, lookup: parseAddressQuery(matches[0].fullName), matches: [], matchedUnit: matches[0] };
  }
  return { raw, lookup, matches };
}

function matchSidoCandidate(c, sd) {
  const alias = SIDO_ALIASES[sd];
  const region = c.sggName || c.sdName;
  return c.sdName === sd || region === sd || (alias && (c.sdName === alias || region === alias));
}

function matchBaseCandidate(c, lookup) {
  if (!lookup.baseWiw || !matchSidoCandidate(c, lookup.sd)) return false;
  const base = compactAddressText(lookup.baseWiw);
  return [c.sggName, c.wiwName]
    .filter(Boolean)
    .some(name => compactAddressText(name) === base || compactAddressText(name).startsWith(base));
}

function matchDetailWiwCandidate(c, lookup) {
  if (!lookup.detailWiw && !lookup.baseWiw) return false;
  if (!matchSidoCandidate(c, lookup.sd)) return false;
  const target = compactAddressText(lookup.detailWiw || lookup.baseWiw);
  const base = compactAddressText(lookup.baseWiw);
  const hasSubWiw = lookup.detailWiw && lookup.baseWiw
    && compactAddressText(lookup.detailWiw) !== compactAddressText(lookup.baseWiw);
  if (hasSubWiw) {
    const wiw = compactAddressText(c.wiwName);
    return wiw === target || wiw.startsWith(target);
  }
  return [c.wiwName, c.sggName]
    .filter(Boolean)
    .some(name => {
      const n = compactAddressText(name);
      return n === target || (base && n.startsWith(base));
    });
}

function groupCandidatesByDistrict(list) {
  return list.reduce((acc, c) => {
    const key = c.sggName || c.wiwName || c.sdName || '(미지정)';
    (acc[key] ||= []).push(c);
    return acc;
  }, {});
}

function buildAddressCandidateSections(lookup) {
  const candidates = (state.data?.candidates || []).filter(isActiveCandidate);
  const byCode = code => candidates.filter(c => String(c.sgTypecode) === code);
  const sections = [
    { code: '3', title: SG_TITLE['3'], note: '시도 단위', list: byCode('3').filter(c => matchSidoCandidate(c, lookup.sd)) },
    { code: '11', title: SG_TITLE['11'], note: '시도 단위', list: byCode('11').filter(c => matchSidoCandidate(c, lookup.sd)) },
    { code: '8', title: SG_TITLE['8'], note: '정당명부 · 시도 단위', list: byCode('8').filter(c => matchSidoCandidate(c, lookup.sd)) },
  ];

  if (lookup.baseWiw) {
    sections.push(
      { code: '4', title: SG_TITLE['4'], note: lookup.baseWiw, list: byCode('4').filter(c => matchBaseCandidate(c, lookup)) },
      { code: '9', title: SG_TITLE['9'], note: `${lookup.baseWiw} 정당명부`, list: byCode('9').filter(c => matchBaseCandidate(c, lookup)) },
      { code: '5', title: SG_TITLE['5'], note: `${lookup.detailWiw || lookup.baseWiw} 관할 선거구`, list: byCode('5').filter(c => matchDetailWiwCandidate(c, lookup)), grouped: true },
      { code: '6', title: SG_TITLE['6'], note: `${lookup.detailWiw || lookup.baseWiw} 관할 선거구`, list: byCode('6').filter(c => matchDetailWiwCandidate(c, lookup)), grouped: true },
      { code: '2', title: SG_TITLE['2'], note: '동시 재·보궐이 있는 경우만', list: byCode('2').filter(c => matchBaseCandidate(c, lookup)), grouped: true }
    );
  }

  return sections.filter(s => s.list.length > 0);
}

function addressSectionHtml(section) {
  if (section.grouped) {
    const groups = groupCandidatesByDistrict(section.list);
    const keys = Object.keys(groups).sort(koSort);
    return `
      <section class="address-result-block">
        <h3 class="address-result-title">${section.title}
          <span>${section.note} · ${section.list.length.toLocaleString()}명 · ${keys.length}개 선거구</span>
        </h3>
        <div class="address-result-grid">${keys.map(k => candidateCard(k, groups[k])).join('')}</div>
      </section>`;
  }
  const label = section.code === '8' || section.code === '9' ? section.note : section.title;
  return `
    <section class="address-result-block">
      <h3 class="address-result-title">${section.title}
        <span>${section.note} · ${section.list.length.toLocaleString()}명</span>
      </h3>
      <div class="address-result-grid">${candidateCard(label, section.list)}</div>
    </section>`;
}

function renderAddressFinder() {
  return `
    <section id="address-finder" class="address-finder">
      <div class="address-finder-head">
        <div>
          <p class="address-kicker">내 투표용지에 가까운 후보 보기</p>
          <h2>주소로 후보 찾기</h2>
        </div>
        <p>동 이름이나 도로명만 입력해도 후보 지역을 추천합니다. 같은 이름이 여러 곳이면 전체 주소를 골라 주세요.</p>
      </div>
      <form class="address-form" data-address-form>
        <div class="address-input-wrap">
          <input id="address-input" name="address" type="search" autocomplete="off" placeholder="예: 사직동, 상도로, 서울 종로구 사직로" aria-label="주소, 동 이름 또는 도로명 입력" aria-controls="address-suggestions">
          <div id="address-suggestions" class="address-suggestions" hidden></div>
        </div>
        <button type="submit">후보 보기</button>
      </form>
      <div id="address-lookup-results" class="address-results" hidden></div>
    </section>`;
}

function renderAddressLoading() {
  const box = document.getElementById('address-suggestions');
  if (box) {
    box.hidden = false;
    box.innerHTML = '<div class="address-suggestion"><span>주소 색인을 불러오는 중입니다.</span></div>';
  }
}

function renderAddressLookup(query) {
  const out = document.getElementById('address-lookup-results');
  if (!out) return;
  const resolved = resolveAddressLookup(query);
  const { lookup, matches, matchedUnit } = resolved;
  if (matchedUnit) {
    const input = document.getElementById('address-input');
    if (input) input.value = matchedUnit.fullName;
  }
  if (!lookup.raw) {
    out.hidden = false;
    out.innerHTML = '<p class="address-error">주소, 동 이름 또는 도로명을 입력해 주세요. 예: 사직동, 상도로, 서울 종로구 사직로</p>';
    return;
  }
  if (!lookup.sd) {
    out.hidden = false;
    if (matches.length) {
      renderAddressSuggestions(query, true);
      out.innerHTML = `<p class="address-error">같은 이름의 지역이 여러 곳입니다. 추천 목록에서 전체 주소를 선택해 주세요.</p>`;
      return;
    }
    clearAddressSuggestions();
    out.innerHTML = '<p class="address-error">지역을 찾지 못했습니다. 동 이름, 도로명이나 시군구를 조금 더 정확히 입력해 주세요.</p>';
    return;
  }
  clearAddressSuggestions();

  const sections = buildAddressCandidateSections(lookup);
  const addressBits = [lookup.sd, lookup.detailWiw || lookup.baseWiw, lookup.road || lookup.emd].filter(Boolean);
  const addressLabel = addressBits.map(escapeHtml).join(' ');
  const candidateCount = sections.reduce((sum, s) => sum + s.list.length, 0);
  const localNote = lookup.baseWiw
    ? '광역·기초의원은 현재 공개된 읍면동별 선거구 매핑이 확정 전이라, 입력한 시군구/구 관할 선거구를 함께 보여줍니다.'
    : '시군구까지 입력하면 기초단체장·지방의원 후보도 함께 볼 수 있습니다.';

  out.hidden = false;
  out.innerHTML = `
    <div class="address-result-head">
      <div>
        <p class="address-result-label">조회 주소</p>
        <h3>${addressLabel}</h3>
      </div>
      <span>${candidateCount.toLocaleString()}명</span>
    </div>
    <p class="address-note">${localNote}</p>
    ${sections.length
      ? sections.map(addressSectionHtml).join('')
      : '<p class="address-error">이 주소 조건에 맞는 후보를 찾지 못했습니다.</p>'}`;
}

// ============ Render: 상세 섹션 ============
function renderDetailSection(section, sidoName) {
  if (!section.detail) return '';
  const candidates = getSectionCandidates(section, sidoName);
  const sidoLabel = sidoDisplayName(sidoName);

  // 비어있는 섹션: 컨텍스트 메시지가 있으면 노출, 없으면 완전 숨김
  if (candidates.length === 0) {
    const note = ABSENCE_NOTES[sidoName]?.[section.sgTypecode];
    return note
      ? `<h3 class="section-title">${section.title}</h3><p class="absence-note">${note}</p>`
      : '';
  }

  const { layout, groupBy } = section.detail;
  const seatStats = buildSeatStats(new Set([String(section.sgTypecode)]));

  if (layout === 'single') {
    const label = section.id === 'chief'
      ? (candidates[0].sggName === sidoName ? sidoLabel : (candidates[0].sggName || sidoLabel))
      : `${sidoLabel} ${section.title}`;
    return `
      <h3 class="section-title">${section.title}</h3>
      <div class="single-section">${candidateCard(label, candidates, { showCompetition: true, seatStats })}</div>`;
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
        ${keys.map(k => candidateCard(k, groups[k], { showCompetition: true, seatStats })).join('')}
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
    const gridId = `cg-${section.id}`;
    const totalSeats = keys.reduce((sum, k) => sum + (seatCountForCandidateGroup(groups[k], seatStats) || 0), 0);
    const seatSummary = totalSeats ? ` · 정원 ${totalSeats.toLocaleString()}석` : '';
    return `
      <h3 class="section-title">${section.title}
        <span class="section-count">후보 ${candidates.length.toLocaleString()}명${seatSummary} · ${keys.length}개 선거구</span>
        <span class="section-toolbar">
          <button type="button" class="expand-toggle" data-target="${gridId}" data-open="false">모두 펼치기</button>
        </span>
      </h3>
      <div id="${gridId}" class="collapsible-grid">
        ${keys.map(k => `
          <details class="electoral-district">
            <summary>
              <span class="ed-name" title="${escapeHtml(k)}">${escapeHtml(k)}</span>
              <span class="ed-count">${districtCompetitionLabel(groups[k], seatStats)}</span>
            </summary>
            <div class="ed-body">${groups[k].map(candidateRow).join('')}</div>
          </details>`).join('')}
      </div>`;
  }

  return '';
}

// 지역 그룹·시도별 라인 그래프 SVG. 같은 차트 안에 여러 라인.
function lineChartSvg(rounds, lines, opts = {}) {
  // rounds: [{round, year}], lines: [{label, color, values: [v|null...]}]
  const w = opts.w || 760, h = opts.h || 220, pad = opts.pad || 36;
  const allVals = lines.flatMap(l => l.values.filter(v => v != null));
  if (!allVals.length) return '';
  const min = Math.floor(Math.min(...allVals) / 5) * 5;
  const max = Math.ceil(Math.max(...allVals) / 5) * 5;
  const range = max - min || 1;
  const stepX = (w - pad * 1.4) / (rounds.length - 1 || 1);
  const x = i => pad + i * stepX;
  const y = v => h - pad - ((v - min) / range) * (h - pad * 2);

  const grid = [];
  const ticks = 4;
  for (let i = 0; i <= ticks; i++) {
    const val = min + (range * i / ticks);
    const yy = y(val);
    grid.push(`<line x1="${pad}" y1="${yy.toFixed(1)}" x2="${w - pad * 0.4}" y2="${yy.toFixed(1)}" stroke="#ece6dc" stroke-width="1"/>`);
    grid.push(`<text x="${(pad - 6).toFixed(1)}" y="${(yy + 3).toFixed(1)}" font-size="10" fill="#888" text-anchor="end">${val.toFixed(0)}%</text>`);
  }
  const xLabels = rounds.map((r, i) =>
    `<text x="${x(i).toFixed(1)}" y="${h - 10}" font-size="10" fill="#888" text-anchor="middle">${r.round}회</text>`
  ).join('');

  const polylines = lines.map(l => {
    const pts = l.values.map((v, i) => v == null ? null : `${x(i).toFixed(1)},${y(v).toFixed(1)}`).filter(Boolean).join(' ');
    const circles = l.values.map((v, i) => v == null ? '' :
      `<circle cx="${x(i).toFixed(1)}" cy="${y(v).toFixed(1)}" r="3" fill="${l.color}"/>`
    ).join('');
    return `<polyline fill="none" stroke="${l.color}" stroke-width="2.4" stroke-linecap="round" stroke-linejoin="round" points="${pts}"/>${circles}`;
  }).join('');

  return `
    <svg viewBox="0 0 ${w} ${h}" class="trend-chart" aria-label="시도별 투표율 추이">
      ${grid.join('')}${xLabels}${polylines}
    </svg>`;
}

function renderTurnoutBySidoSection() {
  const ht = state.historyTurnout;
  if (!ht?.elections?.length) return '';
  const agg = aggregateTurnoutBySido(ht);
  const rounds = ht.elections.map(e => ({ round: e.round, year: e.year }));

  // 지역 그룹 평균 라인 차트
  const groupLines = Object.entries(SIDO_GROUPS).map(([label, sds]) => ({
    label,
    color: GROUP_COLORS[label],
    values: rounds.map(r => {
      const vs = sds.map(sd => agg[r.round]?.[sd]).filter(v => v != null && v > 0);
      return vs.length ? +(vs.reduce((a,b) => a+b, 0) / vs.length).toFixed(2) : null;
    }),
  }));
  const groupChart = lineChartSvg(rounds, groupLines);
  const groupLegend = groupLines.map(l => {
    const last = l.values[l.values.length - 1];
    return `<li><span class="legend-swatch" style="background:${l.color}"></span>${l.label} <small>${last != null ? last.toFixed(1) + '%' : '-'}</small></li>`;
  }).join('');

  // 시도별 표 (지역 그룹순 + 8회 대비 7회 변화량)
  const allSidos = Object.values(SIDO_GROUPS).flat();
  const tableRows = allSidos.map(sd => {
    const cells = rounds.map(r => {
      const v = agg[r.round]?.[sd];
      return v == null || v === 0 ? '<td>—</td>' : `<td>${v.toFixed(1)}%</td>`;
    }).join('');
    // 7→8 변화량
    const r7 = agg[7]?.[sd], r8 = agg[8]?.[sd];
    const delta = (r7 && r8) ? r8 - r7 : null;
    const deltaCell = delta == null
      ? '<td>—</td>'
      : `<td class="delta ${delta >= 0 ? 'up' : 'down'}">${delta >= 0 ? '+' : ''}${delta.toFixed(1)}p</td>`;
    return `<tr><th>${sidoDisplayName(sd)}</th>${cells}${deltaCell}</tr>`;
  }).join('');

  return `
    <section class="trend-section">
      <h3 class="trend-section-title">시도별 투표율 추이 <small>제3~8회 지방선거</small></h3>
      ${groupChart}
      <ul class="trend-legend">${groupLegend}</ul>
      <p class="forecast-context" style="margin-top:1rem">
        <strong>주목할 패턴</strong>: 호남(광주·전북·전남)은 3~7회 동안 일관되게 최고 투표율을 유지했지만, <strong>8회(2022)에 영남·수도권보다 낮아지는 역전</strong>이 발생. 특히 광주는 7회 59.2% → 8회 37.7%로 21.5%p 급락. 6/3 9회 결과가 다시 호남 상승으로 돌아갈지가 관전 포인트.
      </p>
    </section>

    <section class="trend-section">
      <h3 class="trend-section-title">시도별 투표율 표</h3>
      <div class="table-scroll">
        <table class="hist-table hist-table-sido">
          <thead>
            <tr><th>시도</th>${rounds.map(r => `<th>제${r.round}회</th>`).join('')}<th>7→8 변화</th></tr>
          </thead>
          <tbody>${tableRows}</tbody>
        </table>
      </div>
      <p class="trend-meta">제8회와 제7회 투표율 차이 · "—" 표시는 데이터 미제공(2회 미참여 시도 등)</p>
    </section>`;
}

// 시도별 시계열 집계 (시군구 행 합산 → 시도 단위)
function aggregateTurnoutBySido(turnout) {
  // 반환: { round: { sd: rate } }
  const out = {};
  if (!turnout?.elections) return out;
  for (const e of turnout.elections) {
    const sums = {};
    for (const r of e.by_sido || []) {
      const sd = r.sdName;
      if (!sd) continue;
      const cur = sums[sd] || { sunsu: 0, tusu: 0 };
      cur.sunsu += r.sunsu || 0;
      cur.tusu += r.tusu || 0;
      sums[sd] = cur;
    }
    const rates = {};
    for (const [sd, v] of Object.entries(sums)) {
      rates[sd] = v.sunsu > 0 ? +(v.tusu / v.sunsu * 100).toFixed(2) : null;
    }
    out[e.round] = rates;
  }
  return out;
}

const SIDO_GROUPS = {
  '호남':  ['광주광역시', '전라북도', '전라남도'],
  '영남':  ['부산광역시', '대구광역시', '울산광역시', '경상북도', '경상남도'],
  '수도권': ['서울특별시', '인천광역시', '경기도'],
  '충청':  ['대전광역시', '세종특별자치시', '충청북도', '충청남도'],
  '강원·제주': ['강원도', '제주특별자치도'],
};
const GROUP_COLORS = {
  '호남':   '#152484',  // 민주당 색 — 호남 강조
  '영남':   '#E61E2B',
  '수도권': '#888',
  '충청':   '#FF7800',
  '강원·제주': '#0A3CA2',
};

// 역대 지방선거 투표율 — 단정적 예측 X, 과거 패턴 비교 도구
function historyWinnersSummary(winners) {
  return Object.entries(winners).sort((a,b) => b[1]-a[1])
    .map(([p, n]) => `${p} ${n}`).join(' · ');
}
function historyGovernorResult(election) {
  return election?.results?.find(r => String(r.sgTypecode) === '3') || null;
}
function historyLocalHeadResult(election) {
  return election?.results?.find(r => String(r.sgTypecode) === '4') || null;
}
function historyCountingSummary(result) {
  return (result?.party_wins || [])
    .map(row => `${row.party} ${row.wins}`)
    .join(' · ');
}
function historyTurnoutText(election, legacy) {
  const old = legacy.get(Number(election?.round));
  return old?.turnout ? `${old.turnout}%` : '-';
}
function historyLegacyByRound() {
  return new Map((state.history?.elections || []).map(e => [Number(e.round), e]));
}
function normalizeHistorySidoName(sd) {
  const map = {
    '강원도': '강원특별자치도',
    '전라북도': '전북특별자치도',
    '제주도': '제주특별자치도',
  };
  return map[sd] || sd;
}
function historyWinnerCell(district) {
  const winner = district?.winner;
  if (!winner?.name) return '<span class="hist-empty">-</span>';
  return `
    <span class="history-winner-party">${winner.party || '무소속'}</span>
    <strong>${winner.name}</strong>
    <small>${winner.vote_share != null ? winner.vote_share.toFixed(2) + '%' : '-'}</small>`;
}
function historyWinnerLine(district) {
  const winner = district?.winner;
  if (!winner?.name) return '-';
  return `${winner.party || '무소속'} ${winner.name}${winner.vote_share != null ? ` ${winner.vote_share.toFixed(1)}%` : ''}`;
}
function historyDistrictMargin(district) {
  const candidates = [...(district?.candidates || [])].sort((a, b) => (b.votes || 0) - (a.votes || 0));
  const first = candidates[0], second = candidates[1];
  if (!first || !second || !district?.valid_votes) return null;
  return {
    first,
    second,
    marginVotes: first.votes - second.votes,
    marginPct: (first.votes - second.votes) / district.valid_votes * 100,
  };
}
function historyCloseRaces(result, limit = 6) {
  const districts = result?.districts || [];
  return districts.map(d => {
    const candidates = [...(d.candidates || [])].sort((a, b) => (b.votes || 0) - (a.votes || 0));
    const first = candidates[0], second = candidates[1];
    if (!first || !second || !d.valid_votes) return null;
    const marginVotes = first.votes - second.votes;
    const marginPct = marginVotes / d.valid_votes * 100;
    return { district: d, first, second, marginVotes, marginPct };
  }).filter(Boolean).sort((a, b) => a.marginPct - b.marginPct).slice(0, limit);
}
function historyDistrictLabel(d, sgTypecode) {
  const sd = normalizeHistorySidoName(d?.sdName || '');
  const sgg = d?.sggName || '';
  const sdLabel = sidoDisplayName(sd);
  if (String(sgTypecode) === '3' || !sgg || sgg === sd) return sdLabel || sgg || '-';
  return `${sdLabel} ${sgg}`.trim();
}
function historyDistrictTurnout(d) {
  if (!d?.eligible_voters || !d?.turnout_votes) return null;
  return d.turnout_votes / d.eligible_voters * 100;
}
function historyCurrentRegion(d) {
  const sgg = d?.sggName || '';
  if (normalizeHistorySidoName(d?.sdName || '') === '경상북도' && sgg === '군위군') {
    return { sd: '대구광역시', sgg };
  }
  return { sd: normalizeHistorySidoName(d?.sdName || ''), sgg };
}
function historyNameKey(name) {
  return String(name || '').replace(/\s+/g, '');
}
function currentCandidatesForHistoryDistrict(d, sgTypecode) {
  const { sd, sgg } = historyCurrentRegion(d);
  return (state.data?.candidates || [])
    .filter(isActiveCandidate)
    .filter(c => String(c.sgTypecode) === String(sgTypecode))
    .filter(c => c.sdName === sd)
    .filter(c => String(sgTypecode) === '3' || c.sggName === sgg)
    .sort((a, b) => Number(a.giho || 999) - Number(b.giho || 999) || koSort(a.name || '', b.name || ''));
}
function historyBattlefieldItems(election, limit = 12) {
  const targets = [
    { result: election?.governor, office: '시도지사', sgTypecode: '3' },
    { result: election?.localHead, office: '기초단체장', sgTypecode: '4' },
  ];
  const rows = [];
  for (const target of targets) {
    for (const d of target.result?.districts || []) {
      const margin = historyDistrictMargin(d);
      if (!margin) continue;
      const currentCandidates = currentCandidatesForHistoryDistrict(d, target.sgTypecode);
      const firstKey = historyNameKey(margin.first.name);
      const secondKey = historyNameKey(margin.second.name);
      const returningWinner = currentCandidates.find(c => historyNameKey(c.name) === firstKey) || null;
      const returningRunnerUp = currentCandidates.find(c => historyNameKey(c.name) === secondKey) || null;
      rows.push({
        ...margin,
        district: d,
        office: target.office,
        sgTypecode: target.sgTypecode,
        currentCandidates,
        returningWinner,
        returningRunnerUp,
        turnoutPct: historyDistrictTurnout(d),
      });
    }
  }
  const sorted = rows.sort((a, b) => a.marginPct - b.marginPct || koSort(historyDistrictLabel(a.district, a.sgTypecode), historyDistrictLabel(b.district, b.sgTypecode)));
  return limit === Infinity ? sorted : sorted.slice(0, limit);
}
function historyBattleReason(item) {
  const reasons = [];
  if (item.marginPct < 1) reasons.push('1%p 미만 접전');
  else if (item.marginPct < 3) reasons.push('3%p 미만 접전');
  else if (item.marginPct < 5) reasons.push('5%p 미만 접전');
  if (item.returningWinner && item.returningRunnerUp) reasons.push('지난 1·2위 재출마');
  else if (item.returningWinner) reasons.push('지난 당선자 재출마');
  else if (item.returningRunnerUp) reasons.push('지난 2위 재출마');
  if (item.currentCandidates.length <= 1) reasons.push('후보 1명 이하');
  return reasons.slice(0, 3).join(' · ') || '과거 격차 기준';
}
function historyCurrentCandidatePills(item) {
  const highlight = new Set([historyNameKey(item.first.name), historyNameKey(item.second.name)]);
  if (!item.currentCandidates.length) return '<p class="history-current-empty">이번 후보 등록 데이터가 없습니다.</p>';
  return `
    <ul class="history-current-candidates">
      ${item.currentCandidates.map(c => {
        const isPastTop = highlight.has(historyNameKey(c.name));
        return `
          <li class="${isPastTop ? 'is-past-top' : ''}">
            <span class="hist-cand-color" style="background:${partyColor(c.jdName)}"></span>
            <button type="button" class="candidate-detail-trigger" data-huboid="${escapeHtml(c.huboid)}" title="${escapeHtml(c.name)} 상세 정보">${escapeHtml(c.name || '-')}</button>
            <small>${escapeHtml(c.jdName || '무소속')}</small>
          </li>`;
      }).join('')}
    </ul>`;
}
function historyBattlefieldCard(item) {
  const turnout = item.turnoutPct == null ? '-' : `${item.turnoutPct.toFixed(1)}%`;
  return `
    <article class="history-battle-card">
      <header class="history-battle-head">
        <span>${escapeHtml(item.office)}</span>
        <strong>${escapeHtml(historyDistrictLabel(item.district, item.sgTypecode))}</strong>
        <em>${escapeHtml(historyBattleReason(item))}</em>
      </header>
      <div class="history-battle-past">
        <div>
          <span>지난 1위</span>
          <strong>${escapeHtml(item.first.name)}</strong>
          <small>${escapeHtml(item.first.party || '무소속')} · ${item.first.vote_share.toFixed(2)}%</small>
        </div>
        <div>
          <span>지난 2위</span>
          <strong>${escapeHtml(item.second.name)}</strong>
          <small>${escapeHtml(item.second.party || '무소속')} · ${item.second.vote_share.toFixed(2)}%</small>
        </div>
      </div>
      <div class="history-battle-metrics">
        <span>격차 <strong>${item.marginPct.toFixed(2)}%p</strong></span>
        <span>표차 <strong>${item.marginVotes.toLocaleString()}표</strong></span>
        <span>투표율 <strong>${turnout}</strong></span>
      </div>
      <div class="history-battle-current">
        <div class="history-battle-current-title">이번 후보 등록 <strong>${item.currentCandidates.length.toLocaleString()}명</strong></div>
        ${historyCurrentCandidatePills(item)}
      </div>
    </article>`;
}
function historyBattlefieldFilterItems(battlefields, filter) {
  if (filter === 'closeUnder3') return battlefields.filter(item => item.marginPct < 3);
  if (filter === 'returningWinner') return battlefields.filter(item => item.returningWinner);
  if (filter === 'rematch') return battlefields.filter(item => item.returningWinner && item.returningRunnerUp);
  return battlefields.slice(0, 12);
}
function historyBattlefieldPanelHtml(battlefields, filter = 'top') {
  const filters = [
    { key: 'top', label: '최접전', items: historyBattlefieldFilterItems(battlefields, 'top') },
    { key: 'closeUnder3', label: '3%p 미만', items: historyBattlefieldFilterItems(battlefields, 'closeUnder3') },
    { key: 'returningWinner', label: '지난 당선자 재출마', items: historyBattlefieldFilterItems(battlefields, 'returningWinner') },
    { key: 'rematch', label: '지난 1·2위 재출마', items: historyBattlefieldFilterItems(battlefields, 'rematch') },
  ];
  const active = filters.find(item => item.key === filter) || filters[0];
  const cards = active.items.map(historyBattlefieldCard).join('');
  return `
    <div class="history-battle-summary" role="group" aria-label="접전지 조건 선택">
      ${filters.map(item => `
        <button type="button" class="${item.key === active.key ? 'active' : ''}" data-history-battle-filter="${item.key}" aria-pressed="${item.key === active.key ? 'true' : 'false'}">
          <span>${item.label}</span><strong>${item.items.length.toLocaleString()}곳</strong>
        </button>`).join('')}
    </div>
    <p class="history-battle-filter-note">${escapeHtml(active.label)} ${active.items.length.toLocaleString()}곳을 표시합니다.</p>
    <div class="history-battle-grid">${cards || '<p class="absence-note">표시할 선거구가 없습니다.</p>'}</div>`;
}
function updateHistoryBattlefieldFilter(filter) {
  state.historyBattleFilter = filter || 'top';
  const hc = state.historyCounting;
  const countingElections = (hc?.elections || [])
    .map(e => ({ ...e, governor: historyGovernorResult(e), localHead: historyLocalHeadResult(e) }))
    .filter(e => e.governor?.districts?.length);
  const latest = countingElections[countingElections.length - 1];
  if (!latest) return;
  const battlefields = historyBattlefieldItems(latest, Infinity);
  const panel = document.querySelector('[data-history-battle-panel]');
  if (!panel) return;
  panel.innerHTML = historyBattlefieldPanelHtml(battlefields, state.historyBattleFilter);
}
function historyLocalGroupsHtml(result) {
  const districts = [...(result?.districts || [])].sort((a, b) =>
    sidoSort(normalizeHistorySidoName(a.sdName), normalizeHistorySidoName(b.sdName))
    || koSort(a.sggName || '', b.sggName || '')
  );
  if (!districts.length) return '<p class="trend-meta">표시할 시군구 당선자 데이터가 없습니다.</p>';

  const groups = new Map();
  for (const d of districts) {
    const sd = normalizeHistorySidoName(d.sdName);
    if (!groups.has(sd)) groups.set(sd, []);
    groups.get(sd).push(d);
  }

  return [...groups.entries()].map(([sd, items], idx) => {
    const partyCounts = {};
    for (const d of items) {
      const party = d.winner?.party || '기타';
      partyCounts[party] = (partyCounts[party] || 0) + 1;
    }
    const summary = Object.entries(partyCounts)
      .sort((a, b) => b[1] - a[1] || koSort(a[0], b[0]))
      .map(([party, count]) => `${party} ${count}`)
      .join(' · ');
    const cards = items.map(d => {
      const margin = historyDistrictMargin(d);
      const marginText = margin
        ? `${margin.second.name}와 ${margin.marginPct.toFixed(2)}%p 차`
        : '상대 후보 없음 또는 격차 미상';
      return `
        <li class="history-local-card">
          <span class="history-local-district">${escapeHtml(d.sggName || '-')}</span>
          <strong>${escapeHtml(historyWinnerLine(d))}</strong>
          <small>${escapeHtml(marginText)}</small>
        </li>`;
    }).join('');
    return `
      <details class="history-local-group" ${idx < 2 ? 'open' : ''}>
        <summary>
          <strong>${escapeHtml(sidoDisplayName(sd))}</strong>
          <span>${items.length.toLocaleString()}곳 · ${escapeHtml(summary)}</span>
        </summary>
        <ul class="history-local-list">${cards}</ul>
      </details>`;
  }).join('');
}
function findClosestPastElection(turnout) {
  const elections = state.history?.elections || [];
  if (!elections.length) return null;
  let best = elections[0], bestDiff = Math.abs(elections[0].turnout - turnout);
  for (const e of elections) {
    const d = Math.abs(e.turnout - turnout);
    if (d < bestDiff) { best = e; bestDiff = d; }
  }
  return { match: best, diff: bestDiff };
}

function renderHistoryFull() {
  const app = document.getElementById('app');
  app.className = '';
  const hc = state.historyCounting;
  const countingElections = (hc?.elections || [])
    .map(e => ({ ...e, governor: historyGovernorResult(e), localHead: historyLocalHeadResult(e) }))
    .filter(e => e.governor?.districts?.length);
  if (!countingElections.length) {
    app.innerHTML = `
      <nav class="breadcrumb"><a href="#">전국</a><span class="sep">›</span><span class="current">지난 선거</span></nav>
      <div class="detail-head"><h1 class="detail-title">지난 선거 결과</h1></div>
      <p class="absence-note">지난 선거 개표 결과 데이터가 아직 없습니다.</p>`;
    return;
  }

  const legacy = historyLegacyByRound();
  const latest = countingElections[countingElections.length - 1];
  const latestTop = latest.governor.party_wins?.[0];
  const latestLocalTop = latest.localHead?.party_wins?.[0];
  const latestTurnout = historyTurnoutText(latest, legacy);
  const sweep = countingElections.map(e => {
    const top = e.governor.party_wins?.[0] || { party: '-', wins: 0 };
    return {
      election: e,
      top,
      share: e.governor.district_count ? top.wins / e.governor.district_count : 0,
    };
  }).sort((a, b) => b.share - a.share)[0];
  const localClose = historyCloseRaces(latest.localHead, 1)[0];
  const localCloseText = localClose
    ? `${sidoDisplayName(normalizeHistorySidoName(localClose.district.sdName))} ${localClose.district.sggName} · ${localClose.first.name} ${localClose.marginPct.toFixed(2)}%p 차`
    : '-';
  const battlefields = historyBattlefieldItems(latest, Infinity);
  const battlefieldPanel = historyBattlefieldPanelHtml(battlefields, state.historyBattleFilter);

  const resultByRoundAndSido = new Map();
  for (const e of countingElections) {
    const rows = new Map();
    for (const d of e.governor.districts || []) {
      rows.set(normalizeHistorySidoName(d.sdName), d);
    }
    resultByRoundAndSido.set(Number(e.round), rows);
  }
  const orderedSidos = SIDO_ORDER;
  const regionRows = orderedSidos.map(sd => {
    const cells = countingElections.map(e => {
      const d = resultByRoundAndSido.get(Number(e.round))?.get(sd);
      return `<td class="history-result-cell" data-label="제${e.round}회 ${e.year}">${historyWinnerCell(d)}</td>`;
    }).join('');
    return `<tr><th class="history-region-name">${sidoDisplayName(sd)}</th>${cells}</tr>`;
  }).join('');

  const summaryRows = countingElections.map(e => {
    const close = historyCloseRaces(e.governor, 1)[0];
    const closeText = close
      ? `${sidoDisplayName(normalizeHistorySidoName(close.district.sdName))} ${close.first.name} ${close.marginPct.toFixed(2)}%p 차`
      : '-';
    return `
      <tr>
        <td class="hist-round" data-label="선거">제${e.round}회</td>
        <td class="hist-year" data-label="연도">${e.year}</td>
        <td data-label="투표율"><strong>${historyTurnoutText(e, legacy)}</strong></td>
        <td data-label="광역단체장">${e.governor.district_count}곳<br><small>${historyCountingSummary(e.governor)}</small></td>
        <td data-label="기초단체장">${e.localHead?.district_count ? `${e.localHead.district_count}곳<br><small>${historyCountingSummary(e.localHead)}</small>` : '-'}</td>
        <td class="hist-context" data-label="광역 최접전">${closeText}</td>
      </tr>`;
  }).join('');

  const latestCloseRows = historyCloseRaces(latest.governor, 8).map(r => `
    <tr>
      <td data-label="시도">${sidoDisplayName(normalizeHistorySidoName(r.district.sdName))}</td>
      <td data-label="1위"><strong>${r.first.name}</strong><small>${r.first.party}</small></td>
      <td data-label="1위 득표율">${r.first.vote_share.toFixed(2)}%</td>
      <td data-label="2위">${r.second.name}<small>${r.second.party}</small></td>
      <td data-label="2위 득표율">${r.second.vote_share.toFixed(2)}%</td>
      <td data-label="격차"><strong>${r.marginPct.toFixed(2)}%p</strong></td>
    </tr>`).join('');

  app.innerHTML = `
    <nav class="breadcrumb"><a href="#">전국</a><span class="sep">›</span><span class="current">지난 선거</span></nav>
    <div class="detail-head">
      <h1 class="detail-title">지난 선거 결과</h1>
      <div class="detail-inline-stats">
        <span>제3~8회 지방선거 · 광역·기초단체장 개표 결과</span>
      </div>
    </div>
    <p class="page-intro">역대 지방선거 결과를 먼저 큰 흐름으로 보고, 필요한 경우 시도와 시군구 당선자까지 내려가 확인할 수 있게 정리했습니다.</p>

    <section class="history-result-cards">
      <div class="history-result-card">
        <span>${latest.year}년 광역단체장</span>
        <strong>${latestTop.party} ${latestTop.wins}곳</strong>
        <small>${historyCountingSummary(latest.governor)}</small>
      </div>
      <div class="history-result-card">
        <span>${latest.year}년 기초단체장</span>
        <strong>${latestLocalTop ? `${latestLocalTop.party} ${latestLocalTop.wins}곳` : '-'}</strong>
        <small>${historyCountingSummary(latest.localHead)}</small>
      </div>
      <div class="history-result-card">
        <span>${latest.year}년 투표율</span>
        <strong>${latestTurnout}</strong>
        <small>같은 선거의 투표율과 개표 결과를 함께 봅니다.</small>
      </div>
      <div class="history-result-card">
        <span>가장 큰 쏠림</span>
        <strong>${sweep.election.year}년 ${sweep.top.party}</strong>
        <small>${sweep.top.wins}/${sweep.election.governor.district_count}곳 · ${(sweep.share * 100).toFixed(1)}%</small>
      </div>
    </section>

    <section class="trend-section history-battle-section" data-history-battle-section>
      <div class="trend-section-head">
        <h3 class="trend-section-title">지난 접전지, 이번 후보 등록</h3>
        <span class="trend-section-kicker">${latest.year}년 광역·기초단체장 접전지</span>
      </div>
      <div data-history-battle-panel>${battlefieldPanel}</div>
      <p class="trend-meta">과거 득표 격차, 당시 투표율, 이번 후보 등록 현황을 나란히 둔 관전 지표입니다. 특정 후보의 당락을 예측하지 않습니다.</p>
    </section>

    <section class="trend-section">
      <h3 class="trend-section-title">선거별 주요 결과 <small>투표율과 당선 분포</small></h3>
      <div class="table-scroll">
        <table class="hist-table hist-summary-table">
          <thead>
            <tr><th>선거</th><th>연도</th><th>투표율</th><th>광역단체장</th><th>기초단체장</th><th>광역 최접전</th></tr>
          </thead>
          <tbody>${summaryRows}</tbody>
        </table>
      </div>
      <p class="trend-meta">투표율은 같은 선거 전체 투표율입니다. 당선 분포는 선거구 합계행 기준이며, 정당별 숫자는 당선 지역 수입니다.</p>
    </section>

    <section class="trend-section">
      <h3 class="trend-section-title">시도별 당선자와 득표율</h3>
      <div class="table-scroll">
        <table class="hist-table history-region-table">
          <thead>
            <tr><th>시도</th>${countingElections.map(e => `<th>${e.round}회<br><small>${e.year}</small></th>`).join('')}</tr>
          </thead>
          <tbody>${regionRows}</tbody>
        </table>
      </div>
    </section>

    <section class="trend-section">
      <h3 class="trend-section-title">${latest.year}년 시군구 당선자 <small>기초단체장 ${latest.localHead?.district_count?.toLocaleString() || 0}곳</small></h3>
      <p class="page-intro">처음에는 지역별 요약만 보고, 필요한 시도를 펼쳐 시군구 당선자와 득표율·격차를 확인할 수 있습니다.</p>
      <div class="history-local-groups">${historyLocalGroupsHtml(latest.localHead)}</div>
    </section>

    <section class="trend-section">
      <h3 class="trend-section-title">${latest.year}년 접전 지역 <small>광역단체장</small></h3>
      <div class="table-scroll">
        <table class="hist-table history-close-table">
          <thead>
            <tr><th>시도</th><th>1위</th><th>득표율</th><th>2위</th><th>득표율</th><th>격차</th></tr>
          </thead>
          <tbody>${latestCloseRows}</tbody>
        </table>
      </div>
      <p class="trend-meta">기초단체장 최접전: ${escapeHtml(localCloseText)}</p>
      <p class="trend-meta">후보별 득표율은 유효투표수 기준입니다. 자료 출처: 중앙선거관리위원회 선거통계시스템 개표 결과.</p>
    </section>`;

  window.scrollTo({ top: 0, behavior: 'instant' });
}

// 출마자 한눈에 — 정당·연령·성별·직업 통계
function buildProfileStats() {
  const cs = state.data.candidates;
  // 정당
  const byParty = {};
  cs.forEach(c => { const j = c.jdName || '무소속'; byParty[j] = (byParty[j] || 0) + 1; });
  const parties = Object.entries(byParty).sort((a,b) => b[1] - a[1]);
  // 연령대 (10단위)
  const ageBuckets = {20:0,30:0,40:0,50:0,60:0,70:0,80:0};
  let ageSum = 0, ageCount = 0;
  cs.forEach(c => {
    const a = parseInt(c.age, 10);
    if (!isNaN(a) && a > 0) {
      ageSum += a; ageCount++;
      const b = Math.max(20, Math.min(80, Math.floor(a / 10) * 10));
      ageBuckets[b] = (ageBuckets[b] || 0) + 1;
    }
  });
  const ageAvg = ageCount ? ageSum / ageCount : 0;
  // 성별
  const byGender = {};
  cs.forEach(c => { const g = c.gender || '미기재'; byGender[g] = (byGender[g] || 0) + 1; });
  // 직업
  const byJob = {};
  cs.forEach(c => { const j = c.job || '미기재'; byJob[j] = (byJob[j] || 0) + 1; });
  const jobs = Object.entries(byJob).sort((a,b) => b[1] - a[1]).slice(0, 10);
  return { total: cs.length, parties, ageBuckets, ageAvg, ageCount, byGender, jobs };
}

function parseDisclosureNumber(value) {
  if (value == null || value === '') return null;
  const n = Number(String(value).replace(/,/g, '').trim());
  return Number.isFinite(n) ? n : null;
}

function parseCriminalCount(value) {
  const text = String(value || '').trim();
  if (!text || text === '없음') return 0;
  const m = text.match(/-?\d+/);
  return m ? Math.max(0, parseInt(m[0], 10)) : 0;
}

function militaryBucket(value) {
  const text = String(value || '').trim();
  if (!text) return 'unknown';
  if (text.includes('해당없음')) return 'nonTarget';
  if (text.includes('마치지 아니') || text.includes('병적기록')) return 'notServed';
  if (text.includes('마친')) return 'served';
  return 'unknown';
}

function formatEok(thousandKrw) {
  if (thousandKrw == null || !Number.isFinite(thousandKrw)) return '-';
  const eok = thousandKrw / 100000;
  const abs = Math.abs(eok);
  const digits = abs >= 100 ? 0 : 1;
  return `${eok.toLocaleString('ko-KR', { maximumFractionDigits: digits, minimumFractionDigits: digits })}억`;
}

function formatPct(value, digits = 1) {
  return `${(value || 0).toFixed(digits)}%`;
}

function summarizeNumbers(values) {
  const nums = values.filter(v => Number.isFinite(v)).sort((a, b) => a - b);
  if (!nums.length) return { count: 0, avg: 0, median: 0, min: 0, max: 0 };
  const sum = nums.reduce((a, b) => a + b, 0);
  const mid = Math.floor(nums.length / 2);
  const median = nums.length % 2 ? nums[mid] : (nums[mid - 1] + nums[mid]) / 2;
  return {
    count: nums.length,
    avg: sum / nums.length,
    median,
    min: nums[0],
    max: nums[nums.length - 1],
  };
}

function disclosureRows() {
  return (state.data?.candidates || [])
    .filter(isActiveCandidate)
    .map(c => {
      const detail = state.candidateDetails?.[String(c.huboid)] || null;
      const disclosures = detail?.disclosures || {};
      const assets = parseDisclosureNumber(disclosures.assets_thousand_krw);
      const criminal = parseCriminalCount(disclosures.criminal_record);
      const military = militaryBucket(disclosures.military);
      const taxPaid = parseDisclosureNumber(disclosures.tax_paid_thousand_krw);
      const taxArrears5y = parseDisclosureNumber(disclosures.tax_arrears_5y_thousand_krw) || 0;
      const taxArrearsCurrent = parseDisclosureNumber(disclosures.tax_arrears_current_thousand_krw) || 0;
      return {
        candidate: c,
        party: c.jdName || '무소속',
        sd: sidoFor(c),
        disclosures,
        assets,
        criminal,
        hasCriminal: criminal > 0,
        military,
        taxPaid,
        taxArrears5y,
        taxArrearsCurrent,
        hasTaxArrears: taxArrears5y > 0,
        hasCurrentTaxArrears: taxArrearsCurrent > 0,
      };
    })
    .filter(r => r.disclosures && Object.keys(r.disclosures).length);
}

function groupDisclosureRows(rows, keyFn) {
  return rows.reduce((acc, row) => {
    const key = keyFn(row) || '미기재';
    (acc[key] ||= []).push(row);
    return acc;
  }, {});
}

function rankedAssetGroups(rows, keyFn, minCount = 20) {
  return Object.entries(groupDisclosureRows(rows.filter(r => Number.isFinite(r.assets)), keyFn))
    .map(([label, items]) => ({ label, count: items.length, ...summarizeNumbers(items.map(r => r.assets)) }))
    .filter(r => r.count >= minCount)
    .sort((a, b) => b.avg - a.avg || b.count - a.count);
}

function rankedCriminalGroups(rows, keyFn, minCount = 20) {
  return Object.entries(groupDisclosureRows(rows, keyFn))
    .map(([label, items]) => {
      const holders = items.filter(r => r.hasCriminal).length;
      const cases = items.reduce((sum, r) => sum + r.criminal, 0);
      return { label, count: items.length, holders, cases, rate: items.length ? holders / items.length * 100 : 0 };
    })
    .filter(r => r.count >= minCount)
    .sort((a, b) => b.rate - a.rate || b.holders - a.holders);
}

function rankedMilitaryGroups(rows, keyFn, minEligible = 10) {
  const militaryRows = rows.filter(r => r.candidate?.gender === '남');
  return Object.entries(groupDisclosureRows(militaryRows, keyFn))
    .map(([label, items]) => {
      const served = items.filter(r => r.military === 'served').length;
      const notServed = items.filter(r => r.military === 'notServed').length;
      const nonTarget = items.filter(r => r.military === 'nonTarget').length;
      const eligible = served + notServed;
      return {
        label,
        count: items.length,
        served,
        notServed,
        nonTarget,
        eligible,
        rate: eligible ? notServed / eligible * 100 : 0,
      };
    })
    .filter(r => r.eligible >= minEligible)
    .sort((a, b) => b.rate - a.rate || b.notServed - a.notServed);
}

function rankedSidoMilitaryGroups(rows) {
  const byLabel = new Map(
    rankedMilitaryGroups(rows, r => canonicalSidoName(r.sd), 0)
      .map(row => [canonicalSidoName(row.label), row])
  );
  return SIDO_ORDER.map(sd => byLabel.get(sd) || {
    label: sd,
    count: 0,
    served: 0,
    notServed: 0,
    nonTarget: 0,
    eligible: 0,
    rate: 0,
  }).sort((a, b) =>
    b.rate - a.rate ||
    b.notServed - a.notServed ||
    b.eligible - a.eligible ||
    SIDO_ORDER.indexOf(a.label) - SIDO_ORDER.indexOf(b.label)
  );
}

function rankedTaxArrearsGroups(rows, keyFn, field = 'taxArrears5y', minCount = 20) {
  return Object.entries(groupDisclosureRows(rows, keyFn))
    .map(([label, items]) => {
      const holders = items.filter(r => (r[field] || 0) > 0).length;
      const total = items.reduce((sum, r) => sum + (r[field] || 0), 0);
      return { label, count: items.length, holders, total, rate: items.length ? holders / items.length * 100 : 0 };
    })
    .filter(r => r.count >= minCount)
    .sort((a, b) => b.rate - a.rate || b.holders - a.holders || b.total - a.total);
}

function sortCandidateRows(a, b) {
  const sdDiff = sidoSort(a.sd, b.sd);
  if (sdDiff) return sdDiff;
  const regionDiff = koSort(a.candidate?.sggName || '', b.candidate?.sggName || '');
  if (regionDiff) return regionDiff;
  return koSort(a.candidate?.name || '', b.candidate?.name || '');
}

function rankedAssetCandidates(rows, limit = 5) {
  return rows
    .filter(r => Number.isFinite(r.assets))
    .sort((a, b) => b.assets - a.assets || sortCandidateRows(a, b))
    .slice(0, limit);
}

function rankedCriminalCandidates(rows, limit = 5) {
  return rows
    .filter(r => r.criminal > 0)
    .sort((a, b) => b.criminal - a.criminal || sortCandidateRows(a, b))
    .slice(0, limit);
}

function rankedTaxArrearsCandidates(rows, limit = 5, field = 'taxArrearsCurrent') {
  const ranked = rows
    .filter(r => (r[field] || 0) > 0)
    .sort((a, b) => (b[field] || 0) - (a[field] || 0) || sortCandidateRows(a, b));
  return limit == null ? ranked : ranked.slice(0, limit);
}

function taxArrearsModeConfig(mode = 'current') {
  const key = String(mode || '').toLowerCase();
  if (['5y', 'five-year', 'recent'].includes(key)) {
    return {
      slug: '5y',
      field: 'taxArrears5y',
      title: '최근 5년 체납 후보 전체',
      label: '최근 5년 체납',
      amountLabel: '최근 5년 체납액',
      otherLabel: '현 체납',
      otherField: 'taxArrearsCurrent',
      holdersKey: 'holders',
      totalKey: 'total5y',
      rateKey: 'rate',
    };
  }
  return {
    slug: 'current',
    field: 'taxArrearsCurrent',
    title: '현 체납 후보 전체',
    label: '현 체납',
    amountLabel: '현 체납액',
    otherLabel: '최근 5년 체납',
    otherField: 'taxArrears5y',
    holdersKey: 'currentHolders',
    totalKey: 'totalCurrent',
    rateKey: 'currentRate',
  };
}

function taxArrearsListHref(mode = 'current') {
  return `#tax-arrears/${taxArrearsModeConfig(mode).slug}`;
}

function rankedCandidateRegions(rows, rankFn, limit = 5) {
  return Object.entries(groupDisclosureRows(rows, r => r.sd))
    .map(([label, items]) => ({ label, items: rankFn(items, limit) }))
    .filter(r => r.items.length)
    .sort((a, b) => sidoSort(a.label, b.label));
}

function buildDisclosureStats() {
  const rows = disclosureRows();
  const assetRows = rows.filter(r => Number.isFinite(r.assets));
  const militaryRows = rows.filter(r => r.candidate?.gender === '남');
  const assets = summarizeNumbers(assetRows.map(r => r.assets));
  const criminalHolders = rows.filter(r => r.hasCriminal).length;
  const criminalCases = rows.reduce((sum, r) => sum + r.criminal, 0);
  const taxArrearsHolders = rows.filter(r => r.hasTaxArrears).length;
  const currentTaxArrearsHolders = rows.filter(r => r.hasCurrentTaxArrears).length;
  const taxArrears5yTotal = rows.reduce((sum, r) => sum + (r.taxArrears5y || 0), 0);
  const taxArrearsCurrentTotal = rows.reduce((sum, r) => sum + (r.taxArrearsCurrent || 0), 0);
  const served = militaryRows.filter(r => r.military === 'served').length;
  const notServed = militaryRows.filter(r => r.military === 'notServed').length;
  const nonTarget = militaryRows.filter(r => r.military === 'nonTarget').length;
  const militaryEligible = served + notServed;

  return {
    rows,
    assets,
    criminal: {
      count: rows.length,
      holders: criminalHolders,
      cases: criminalCases,
      rate: rows.length ? criminalHolders / rows.length * 100 : 0,
    },
    taxArrears: {
      count: rows.length,
      holders: taxArrearsHolders,
      currentHolders: currentTaxArrearsHolders,
      total5y: taxArrears5yTotal,
      totalCurrent: taxArrearsCurrentTotal,
      rate: rows.length ? taxArrearsHolders / rows.length * 100 : 0,
      currentRate: rows.length ? currentTaxArrearsHolders / rows.length * 100 : 0,
    },
    military: {
      count: militaryRows.length,
      served,
      notServed,
      nonTarget,
      eligible: militaryEligible,
      notServedRate: militaryEligible ? notServed / militaryEligible * 100 : 0,
    },
    byParty: {
      assets: rankedAssetGroups(rows, r => r.party),
      criminal: rankedCriminalGroups(rows, r => r.party),
      taxArrears5y: rankedTaxArrearsGroups(rows, r => r.party, 'taxArrears5y'),
      taxArrearsCurrent: rankedTaxArrearsGroups(rows, r => r.party, 'taxArrearsCurrent'),
      military: rankedMilitaryGroups(rows, r => r.party),
    },
    byRegion: {
      assets: rankedAssetGroups(rows, r => r.sd),
      criminal: rankedCriminalGroups(rows, r => r.sd),
      taxArrears5y: rankedTaxArrearsGroups(rows, r => r.sd, 'taxArrears5y'),
      taxArrearsCurrent: rankedTaxArrearsGroups(rows, r => r.sd, 'taxArrearsCurrent'),
      military: rankedSidoMilitaryGroups(rows),
    },
    leaders: {
      assetsOverall: rankedAssetCandidates(rows, 5),
      criminalOverall: rankedCriminalCandidates(rows, 5),
      taxArrearsCurrentOverall: rankedTaxArrearsCandidates(rows, 5, 'taxArrearsCurrent'),
      taxArrears5yOverall: rankedTaxArrearsCandidates(rows, 5, 'taxArrears5y'),
      assetsByRegion: rankedCandidateRegions(rows, rankedAssetCandidates, 5),
      criminalByRegion: rankedCandidateRegions(rows, rankedCriminalCandidates, 5),
    },
  };
}

function renderTrendBox() {
  if (!state.data) return '';
  const s = buildProfileStats();
  const ds = buildDisclosureStats();
  const womenPct = s.byGender['여'] ? (s.byGender['여'] / s.total * 100) : 0;
  const topParty = s.parties[0];
  const detailBits = ds.rows.length ? `
        <div class="trend-summary-stat"><strong>${formatEok(ds.assets.median)}</strong><small>재산 중앙값</small></div>
        <div class="trend-summary-stat"><strong>${formatPct(ds.criminal.rate)}</strong><small>전과 보유율</small></div>
        <div class="trend-summary-stat"><strong>${ds.taxArrears.holders.toLocaleString()}</strong>명<small>최근 5년 체납</small></div>
        <div class="trend-summary-stat"><strong>${formatPct(ds.military.notServedRate)}</strong><small>남성 병역 미필률</small></div>` : '';
  return `
    <a class="trend-card" href="#trend">
      <div class="trend-card-head">
        <span class="trend-card-label">출마자 한눈에</span>
        <span class="trend-card-period">정당·연령·재산·전과·체납·병역</span>
      </div>
      <div class="trend-summary">
        <div class="trend-summary-stat"><strong>${s.ageAvg.toFixed(1)}</strong>세<small>평균 연령</small></div>
        <div class="trend-summary-stat"><strong>${womenPct.toFixed(0)}</strong>%<small>여성 비율</small></div>
        <div class="trend-summary-stat"><strong>${topParty ? topParty[1].toLocaleString() : 0}</strong>명<small>${topParty ? topParty[0] : '-'}</small></div>
        ${detailBits}
        <span class="trend-card-link">전체 통계 →</span>
      </div>
    </a>`;
}

// 가로 바 차트 — count 기반 horizontal bar
function statBar(label, count, max, color) {
  const pct = max > 0 ? (count / max * 100) : 0;
  return `
    <div class="stat-bar">
      <div class="stat-bar-label">${label}</div>
      <div class="stat-bar-track"><div class="stat-bar-fill" style="width: ${pct.toFixed(1)}%; background: ${color || 'var(--accent)'}"></div></div>
      <div class="stat-bar-value">${count.toLocaleString()}</div>
    </div>`;
}

function trendRegionHref(label) {
  return `#trend/${encodeURIComponent(canonicalSidoName(label))}`;
}

function trendLocalHref(sd, label) {
  return `#trend/${encodeURIComponent(canonicalSidoName(sd))}/${encodeURIComponent(label)}`;
}

function trendMilitaryRegionHref(label) {
  return `#trend/military/${encodeURIComponent(canonicalSidoName(label))}`;
}

function trendMilitaryLocalHref(sd, label) {
  return `#trend/military/${encodeURIComponent(canonicalSidoName(sd))}/${encodeURIComponent(label)}`;
}

function disclosureRegionFocusHref(focus, label) {
  return `#trend/${encodeURIComponent(focus)}/${encodeURIComponent(canonicalSidoName(label))}`;
}

function disclosureLocalFocusHref(focus, sd, label) {
  return `#trend/${encodeURIComponent(focus)}/${encodeURIComponent(canonicalSidoName(sd))}/${encodeURIComponent(label)}`;
}

function metricLinkHref(label, options = {}) {
  if (options.focus === 'military' && options.localLinksSd) return trendMilitaryLocalHref(options.localLinksSd, label);
  if (options.focus === 'military' && options.regionLinks) return trendMilitaryRegionHref(label);
  if (['assets', 'criminal', 'tax5y', 'taxCurrent'].includes(options.focus) && options.localLinksSd) {
    return disclosureLocalFocusHref(options.focus, options.localLinksSd, label);
  }
  if (['assets', 'criminal', 'tax5y', 'taxCurrent'].includes(options.focus) && options.regionLinks) {
    return disclosureRegionFocusHref(options.focus, label);
  }
  if (options.localLinksSd) return trendLocalHref(options.localLinksSd, label);
  if (options.regionLinks) return trendRegionHref(label);
  return '';
}

function metricBar(label, value, max, color, valueText, subText, href = '') {
  const pct = max > 0 ? Math.min(100, Math.max(0, value / max * 100)) : 0;
  const labelHtml = href
    ? `<a class="metric-bar-label metric-bar-link" href="${href}">${escapeHtml(label)}</a>`
    : `<div class="metric-bar-label">${escapeHtml(label)}</div>`;
  return `
    <div class="metric-bar">
      ${labelHtml}
      <div class="metric-bar-track"><div class="metric-bar-fill" style="width: ${pct.toFixed(1)}%; background: ${color || 'var(--accent)'}"></div></div>
      <div class="metric-bar-value">${valueText}${subText ? `<small>${subText}</small>` : ''}</div>
    </div>`;
}

function disclosureOverviewHtml(ds) {
  if (!ds.rows.length) return '<p class="absence-note">후보자 상세 공개정보를 아직 불러오지 못했습니다.</p>';
  return `
    <div class="disclosure-overview disclosure-overview-four">
      <div class="disclosure-card">
        <span class="disclosure-label">전체 재산</span>
        <strong>${formatEok(ds.assets.median)}</strong>
        <small>중앙값 · 평균 ${formatEok(ds.assets.avg)} · ${ds.assets.count.toLocaleString()}명</small>
      </div>
      <div class="disclosure-card">
        <span class="disclosure-label">전체 전과</span>
        <strong>${formatPct(ds.criminal.rate)}</strong>
        <small>전과 1건 이상 ${ds.criminal.holders.toLocaleString()}명 / 전체 ${ds.criminal.count.toLocaleString()}명 · 총 ${ds.criminal.cases.toLocaleString()}건</small>
      </div>
      <div class="disclosure-card">
        <span class="disclosure-label">전체 체납</span>
        <strong>${ds.taxArrears.holders.toLocaleString()}명</strong>
        <small>최근 5년 체납 · 현 체납 ${ds.taxArrears.currentHolders.toLocaleString()}명 / 전체 ${ds.taxArrears.count.toLocaleString()}명</small>
      </div>
      <div class="disclosure-card">
        <span class="disclosure-label">남성 병역 미필률</span>
        <strong>${formatPct(ds.military.notServedRate)}</strong>
        <small>미필 ${ds.military.notServed.toLocaleString()}명 / 병역 대상 남성 ${ds.military.eligible.toLocaleString()}명</small>
      </div>
    </div>`;
}

function disclosureFocusHref(kind) {
  return `#disclosure/${encodeURIComponent(kind)}`;
}

function disclosureFocusCardsHtml(ds) {
  if (!ds.rows.length) return '';
  const cards = [
    {
      kind: 'assets',
      label: '재산',
      value: formatEok(ds.assets.median),
      detail: `중앙값 · 평균 ${formatEok(ds.assets.avg)}`,
      note: '정당별·지역별 재산 분포',
    },
    {
      kind: 'criminal',
      label: '전과',
      value: formatPct(ds.criminal.rate),
      detail: `전과 1건 이상 ${ds.criminal.holders.toLocaleString()}명`,
      note: '전과 건수와 범죄 유형',
    },
    {
      kind: 'tax',
      label: '체납',
      value: `${ds.taxArrears.holders.toLocaleString()}명`,
      detail: `최근 5년 체납 · 현 체납 ${ds.taxArrears.currentHolders.toLocaleString()}명`,
      note: '최근 5년 이력과 현 체납 분리',
    },
    {
      kind: 'military',
      label: '병역',
      value: formatPct(ds.military.notServedRate),
      detail: `미필 ${ds.military.notServed.toLocaleString()}명 / 대상 ${ds.military.eligible.toLocaleString()}명`,
      note: '남성 병역 대상 기준',
    },
  ];
  return `
    <section class="trend-section disclosure-focus-section">
      <h3 class="trend-section-title">공개정보별로 보기 <small>재산·전과·체납·병역</small></h3>
      <div class="disclosure-focus-grid">
        ${cards.map(card => `
          <a class="disclosure-focus-card disclosure-focus-${card.kind}" href="${disclosureFocusHref(card.kind)}">
            <span>${escapeHtml(card.label)}</span>
            <strong>${card.value}</strong>
            <small>${escapeHtml(card.detail)}</small>
            <em>${escapeHtml(card.note)} →</em>
          </a>`).join('')}
      </div>
    </section>`;
}

function disclosureFocusTabsHtml(currentKey) {
  const tabs = [
    ['assets', '재산'],
    ['criminal', '전과'],
    ['tax', '체납'],
    ['military', '병역'],
  ];
  return `
    <div class="tax-mode-tabs disclosure-mode-tabs" aria-label="공개정보 보기 기준">
      ${tabs.map(([key, label]) => `
        <a href="${disclosureFocusHref(key)}" class="${key === currentKey ? 'active' : ''}">
          <strong>${escapeHtml(label)}</strong>
        </a>`).join('')}
    </div>`;
}

function assetBars(items, options = {}) {
  const defaultLimit = options.regionLinks ? items.length : 10;
  const shown = items.slice(0, options.limit ?? defaultLimit);
  const max = Math.max(...shown.map(x => x.avg), 1);
  return shown.map(x => metricBar(
    options.regionLinks ? sidoDisplayName(x.label) : x.label,
    x.avg,
    max,
    'var(--accent)',
    formatEok(x.avg),
    `${x.count.toLocaleString()}명`,
    metricLinkHref(x.label, options)
  )).join('');
}

function criminalBars(items, options = {}) {
  const defaultLimit = options.regionLinks ? items.length : 10;
  const shown = items.slice(0, options.limit ?? defaultLimit);
  const max = Math.max(...shown.map(x => x.rate), 1);
  return shown.map(x => metricBar(
    options.regionLinks ? sidoDisplayName(x.label) : x.label,
    x.rate,
    max,
    '#b25c00',
    formatPct(x.rate),
    `전과 ${x.holders.toLocaleString()}명 / ${x.count.toLocaleString()}명`,
    metricLinkHref(x.label, options)
  )).join('');
}

function militaryBars(items, options = {}) {
  const defaultLimit = options.regionLinks ? items.length : 10;
  const shown = items.slice(0, options.limit ?? defaultLimit);
  const max = Math.max(...shown.map(x => x.rate), 1);
  return shown.map(x => metricBar(
    options.regionLinks ? sidoDisplayName(x.label) : x.label,
    x.rate,
    max,
    '#2c5d8f',
    formatPct(x.rate),
    `미필 ${x.notServed.toLocaleString()}명 / 대상 남성 ${x.eligible.toLocaleString()}명`,
    metricLinkHref(x.label, options)
  )).join('');
}

function taxArrearsBars(items, options = {}) {
  const defaultLimit = options.regionLinks ? items.length : 10;
  const shown = items.slice(0, options.limit ?? defaultLimit);
  const max = Math.max(...shown.map(x => x.rate), 1);
  return shown.map(x => metricBar(
    options.regionLinks ? sidoDisplayName(x.label) : x.label,
    x.rate,
    max,
    '#8f3d5a',
    formatPct(x.rate),
    `체납 ${x.holders.toLocaleString()}명 / ${x.count.toLocaleString()}명 · 합계 ${moneyDisclosure(x.total) || '0원'}`,
    metricLinkHref(x.label, options)
  )).join('');
}

function candidateRankContext(c, includeRegion = true) {
  const parts = [
    includeRegion ? sidoDisplayName(sidoFor(c)) : '',
    SG_TITLE[String(c.sgTypecode)] || '',
    c.sggName && c.sggName !== c.sdName ? c.sggName : '',
    c.wiwName && c.wiwName !== c.sggName ? c.wiwName : '',
  ].filter(Boolean);
  return [...new Set(parts)].join(' · ');
}

function normalizeLocalDistrictName(name) {
  const raw = String(name || '').trim();
  if (!raw) return '';
  const tokenDistrict = raw.split(/\s+/).reverse().find(token =>
    /(시|군|구)$/.test(token) && !/(특별시|광역시|특별자치시)$/.test(token)
  );
  if (tokenDistrict) return tokenDistrict;
  const numberedDistrict = raw.match(/^(.+(?:시|군|구))(?:제?\d+|[가-힣])선거구$/);
  if (numberedDistrict) return numberedDistrict[1];
  const plainDistrict = raw.match(/^(.+(?:시|군|구))선거구$/);
  if (plainDistrict) return plainDistrict[1];
  return raw;
}

function isBaseLocalDistrictName(name) {
  return !!name && /(시|군|구)$/.test(name) && !name.includes('선거구');
}

function localDistrictName(row) {
  const c = row?.candidate || {};
  const sgg = normalizeLocalDistrictName(c.sggName);
  if (isBaseLocalDistrictName(sgg) && sgg !== c.sdName && sgg !== row.sd) return sgg;
  const wiw = normalizeLocalDistrictName(c.wiwName);
  if (isBaseLocalDistrictName(wiw) && wiw !== c.sdName && wiw !== row.sd) return wiw;
  return '';
}

function disclosureSummaryFromRows(rows) {
  const assetRows = rows.filter(r => Number.isFinite(r.assets));
  const militaryRows = rows.filter(r => r.candidate?.gender === '남');
  const criminalHolders = rows.filter(r => r.hasCriminal).length;
  const criminalCases = rows.reduce((sum, r) => sum + r.criminal, 0);
  const taxArrearsHolders = rows.filter(r => r.hasTaxArrears).length;
  const currentTaxArrearsHolders = rows.filter(r => r.hasCurrentTaxArrears).length;
  const taxArrears5yTotal = rows.reduce((sum, r) => sum + (r.taxArrears5y || 0), 0);
  const taxArrearsCurrentTotal = rows.reduce((sum, r) => sum + (r.taxArrearsCurrent || 0), 0);
  const served = militaryRows.filter(r => r.military === 'served').length;
  const notServed = militaryRows.filter(r => r.military === 'notServed').length;
  const nonTarget = militaryRows.filter(r => r.military === 'nonTarget').length;
  const militaryEligible = served + notServed;
  return {
    rows,
    assets: summarizeNumbers(assetRows.map(r => r.assets)),
    criminal: {
      count: rows.length,
      holders: criminalHolders,
      cases: criminalCases,
      rate: rows.length ? criminalHolders / rows.length * 100 : 0,
    },
    taxArrears: {
      count: rows.length,
      holders: taxArrearsHolders,
      currentHolders: currentTaxArrearsHolders,
      total5y: taxArrears5yTotal,
      totalCurrent: taxArrearsCurrentTotal,
      rate: rows.length ? taxArrearsHolders / rows.length * 100 : 0,
      currentRate: rows.length ? currentTaxArrearsHolders / rows.length * 100 : 0,
    },
    military: {
      count: militaryRows.length,
      served,
      notServed,
      nonTarget,
      eligible: militaryEligible,
      notServedRate: militaryEligible ? notServed / militaryEligible * 100 : 0,
    },
  };
}

function candidateRankList(items, type, includeRegion = true) {
  if (!items?.length) return '<p class="trend-meta">표시할 후보가 없습니다.</p>';
  return `
    <ol class="candidate-rank-list">
      ${items.map((r, i) => {
        const c = r.candidate || {};
        const value = type === 'asset'
          ? formatEok(r.assets)
          : type === 'taxCurrent'
            ? moneyDisclosure(r.taxArrearsCurrent)
            : type === 'tax5y'
              ? moneyDisclosure(r.taxArrears5y)
              : `${r.criminal.toLocaleString()}건`;
        const context = candidateRankContext(c, includeRegion);
        return `
          <li class="candidate-rank-item">
            <span class="candidate-rank-no">${i + 1}</span>
            <button type="button" class="candidate-rank-name candidate-detail-trigger" data-huboid="${escapeHtml(c.huboid)}" title="${escapeHtml(c.name)} 상세 정보">${escapeHtml(c.name)}</button>
            <span class="candidate-rank-party" style="border-color:${partyColor(c.jdName)}">${escapeHtml(c.jdName || '무소속')}</span>
            <span class="candidate-rank-context">${escapeHtml(context)}</span>
            <strong class="candidate-rank-value">${value}</strong>
          </li>`;
      }).join('')}
    </ol>`;
}

function militaryStatusLabel(bucket) {
  if (bucket === 'served') return '군필';
  if (bucket === 'notServed') return '미필';
  if (bucket === 'nonTarget') return '비대상';
  return '미확인';
}

function militaryCandidateRows(rows, bucket = 'notServed') {
  return rows
    .filter(r => r.candidate?.gender === '남' && r.military === bucket)
    .sort(sortCandidateRows);
}

function militaryCandidateListHtml(items, options = {}) {
  if (!items?.length) {
    return `<p class="trend-meta">${escapeHtml(options.emptyText || '병역 미필 후보가 없습니다.')}</p>`;
  }
  return `
    <ul class="military-candidate-list">
      ${items.map(r => {
        const c = r.candidate || {};
        const context = candidateRankContext(c, options.includeRegion ?? false);
        const raw = r.disclosures?.military || militaryStatusLabel(r.military);
        return `
          <li class="military-candidate-item" title="${escapeHtml(raw)}">
            <div class="military-candidate-main">
              <button type="button" class="candidate-rank-name candidate-detail-trigger" data-huboid="${escapeHtml(c.huboid)}" title="${escapeHtml(c.name)} 상세 정보">${escapeHtml(c.name || '-')}</button>
              <strong class="military-candidate-status">${militaryStatusLabel(r.military)}</strong>
            </div>
            <div class="military-candidate-meta">
              <span class="candidate-rank-party" style="border-color:${partyColor(c.jdName)}">${escapeHtml(c.jdName || '무소속')}</span>
              <span class="military-candidate-context">${escapeHtml(context)}</span>
            </div>
          </li>`;
      }).join('')}
    </ul>`;
}

function findRegionRank(regions, label) {
  return regions.find(r => r.label === label)?.items || [];
}

function candidateRegionRanksHtml(ds) {
  const labels = [...new Set([
    ...ds.leaders.assetsByRegion.map(r => r.label),
    ...ds.leaders.criminalByRegion.map(r => r.label),
  ])].sort(sidoSort);
  if (!labels.length) return '';
  return `
    <div class="region-rank-grid">
      ${labels.map(label => `
        <details class="region-rank">
          <summary>${escapeHtml(sidoDisplayName(label))} <span>재산·전과 TOP 5</span></summary>
          <div class="region-rank-body">
            <div>
              <h5 class="rank-subtitle">재산 1~5위</h5>
              ${candidateRankList(findRegionRank(ds.leaders.assetsByRegion, label), 'asset', false)}
            </div>
            <div>
              <h5 class="rank-subtitle">전과 1~5위</h5>
              ${candidateRankList(findRegionRank(ds.leaders.criminalByRegion, label), 'criminal', false)}
            </div>
          </div>
        </details>`).join('')}
    </div>`;
}

function disclosureLeaderHtml(ds) {
  if (!ds.rows.length) return '';
  return `
    <section class="trend-section">
      <h3 class="trend-section-title">후보별 최다 순위 <small>전체·지역별 1~5위</small></h3>
      <div class="candidate-leader-grid">
        <div class="candidate-leader-card">
          <h4 class="metric-title">전체 재산 1~5위</h4>
          ${candidateRankList(ds.leaders.assetsOverall, 'asset', true)}
        </div>
        <div class="candidate-leader-card">
          <h4 class="metric-title">전체 전과 1~5위</h4>
          ${candidateRankList(ds.leaders.criminalOverall, 'criminal', true)}
        </div>
      </div>
      <h4 class="metric-title region-rank-heading">지역별 후보 순위 <small>시도별 1~5위</small></h4>
      ${candidateRegionRanksHtml(ds)}
      <p class="trend-meta">재산은 선관위 재산신고액 기준, 전과는 전과기록유무(건수)의 건수 기준입니다. 후보 이름을 누르면 상세 공개정보를 볼 수 있습니다.</p>
    </section>`;
}

function disclosureRegionOverviewHtml(sd, summary) {
  return `
    <div class="disclosure-overview">
      <div class="disclosure-card">
        <span class="disclosure-label">${escapeHtml(sd)} 재산</span>
        <strong>${formatEok(summary.assets.median)}</strong>
        <small>중앙값 · 평균 ${formatEok(summary.assets.avg)} · ${summary.assets.count.toLocaleString()}명</small>
      </div>
      <div class="disclosure-card">
        <span class="disclosure-label">${escapeHtml(sd)} 전과</span>
        <strong>${formatPct(summary.criminal.rate)}</strong>
        <small>전과 1건 이상 ${summary.criminal.holders.toLocaleString()}명 / ${summary.criminal.count.toLocaleString()}명 · 총 ${summary.criminal.cases.toLocaleString()}건</small>
      </div>
      <div class="disclosure-card">
        <span class="disclosure-label">${escapeHtml(sd)} 남성 병역 미필률</span>
        <strong>${formatPct(summary.military.notServedRate)}</strong>
        <small>미필 ${summary.military.notServed.toLocaleString()}명 / 병역 대상 남성 ${summary.military.eligible.toLocaleString()}명</small>
      </div>
    </div>`;
}

function militaryRegionOverviewHtml(label, summary) {
  return `
    <div class="disclosure-overview">
      <div class="disclosure-card disclosure-focus-military">
        <span class="disclosure-label">${escapeHtml(label)} 남성 후보</span>
        <strong>${summary.military.count.toLocaleString()}명</strong>
        <small>병역 공개 대상 후보 기준</small>
      </div>
      <div class="disclosure-card disclosure-focus-military">
        <span class="disclosure-label">병역 대상 남성</span>
        <strong>${summary.military.eligible.toLocaleString()}명</strong>
        <small>군필 ${summary.military.served.toLocaleString()}명 · 미필 ${summary.military.notServed.toLocaleString()}명</small>
      </div>
      <div class="disclosure-card disclosure-focus-military">
        <span class="disclosure-label">미필률</span>
        <strong>${formatPct(summary.military.notServedRate)}</strong>
        <small>병역 대상 남성 중 미필 비율</small>
      </div>
    </div>`;
}

function renderTrendRegionFull(sd) {
  sd = canonicalSidoName(sd);
  const sdLabel = sidoDisplayName(sd);
  const app = document.getElementById('app');
  app.className = '';
  if (!state.data) {
    app.innerHTML = '<div class="loading">불러오는 중…</div>';
    return;
  }
  const ds = buildDisclosureStats();
  const rows = ds.rows.filter(r => r.sd === sd);
  if (!rows.length) {
    app.innerHTML = `
      <nav class="breadcrumb"><a href="#trend">출마자 한눈에</a><span class="sep">›</span><span class="current">${escapeHtml(sdLabel || '지역')}</span></nav>
      <div class="error-banner"><strong>지역 통계를 찾지 못했습니다.</strong> 다시 지역을 선택해 주세요.</div>`;
    return;
  }

  const summary = disclosureSummaryFromRows(rows);
  const localRows = rows.filter(localDistrictName);
  const sggAssets = rankedAssetGroups(localRows, localDistrictName, 1);
  const sggCriminal = rankedCriminalGroups(localRows, localDistrictName, 1);
  const sggMilitary = rankedMilitaryGroups(localRows, localDistrictName, 1);
  const militaryNotServedRows = militaryCandidateRows(rows);
  const maxLocalItems = 99;

  app.innerHTML = `
    <nav class="breadcrumb"><a href="#trend">출마자 한눈에</a><span class="sep">›</span><span class="current">${escapeHtml(sdLabel)} 상세 통계</span></nav>
    <div class="detail-head">
      <div>
        <h1 class="detail-title">${escapeHtml(sdLabel)} 공개정보 상세</h1>
        <button type="button" class="page-share" data-share-page data-share-title="${escapeHtml(sdLabel)} 공개정보 상세 — 6·3 선거 출마자 2026">🔗 이 페이지 공유</button>
      </div>
      <div class="detail-inline-stats">
        <span>공개정보 ${summary.rows.length.toLocaleString()}명</span>
        <span>전과 ${formatPct(summary.criminal.rate)}</span>
        <span>병역 미필 ${formatPct(summary.military.notServedRate)}</span>
      </div>
    </div>
    <p class="page-intro">시도별 막대에서 한 단계 내려온 화면입니다. 먼저 ${escapeHtml(sdLabel)} 전체 요약을 보고, 아래에서 후보별 최다 순위와 시군구별 차이를 함께 확인할 수 있습니다.</p>

    ${disclosureRegionOverviewHtml(sdLabel, summary)}

    <section class="trend-section">
      <h3 class="trend-section-title">${escapeHtml(sdLabel)} 후보별 최다 순위 <small>재산·전과 1~5위</small></h3>
      <div class="candidate-leader-grid">
        <div class="candidate-leader-card">
          <h4 class="metric-title">재산 1~5위</h4>
          ${candidateRankList(rankedAssetCandidates(rows, 5), 'asset', false)}
        </div>
        <div class="candidate-leader-card">
          <h4 class="metric-title">전과 1~5위</h4>
          ${candidateRankList(rankedCriminalCandidates(rows, 5), 'criminal', false)}
        </div>
      </div>
      <p class="trend-meta">후보 이름을 누르면 선관위 공개정보와 후보 상세를 볼 수 있습니다.</p>
    </section>

    <section class="trend-section">
      <h3 class="trend-section-title">시군구별 통계 <small>재산·전과·병역</small></h3>
      <div class="metric-grid metric-grid-three">
        <div>
          <h4 class="metric-title">시군구별 평균 재산 <small>지역명 클릭</small></h4>
          <div class="bar-list">${assetBars(sggAssets, { limit: maxLocalItems, localLinksSd: sd }) || '<p class="trend-meta">표시할 시군구가 없습니다.</p>'}</div>
        </div>
        <div>
          <h4 class="metric-title">시군구별 전과 보유율 <small>지역명 클릭</small></h4>
          <div class="bar-list">${criminalBars(sggCriminal, { limit: maxLocalItems, localLinksSd: sd }) || '<p class="trend-meta">표시할 시군구가 없습니다.</p>'}</div>
        </div>
        <div>
          <h4 class="metric-title">시군구별 병역 미필률 <small>지역명 클릭</small></h4>
          <div class="bar-list">${militaryBars(sggMilitary, { limit: maxLocalItems, localLinksSd: sd, focus: 'military' }) || '<p class="trend-meta">표시할 시군구가 없습니다.</p>'}</div>
        </div>
      </div>
      <p class="trend-meta">시군구별 통계는 해당 시군구 선거구로 분류되는 후보 기준입니다. 시도지사·교육감처럼 시도 전체 선거 후보는 시군구 막대에서는 제외했습니다.</p>
    </section>

    <section class="trend-section">
      <h3 class="trend-section-title">${escapeHtml(sdLabel)} 병역 미필 후보 <small>${militaryNotServedRows.length.toLocaleString()}명 전체</small></h3>
      ${militaryCandidateListHtml(militaryNotServedRows, {
        includeRegion: false,
        emptyText: `${sdLabel}에서 병역 미필로 표시된 남성 후보가 없습니다.`,
      })}
      <p class="trend-meta">남성 후보 중 선관위 병역 항목이 “군복무를 마치지 아니한 사람” 또는 병적기록 관련 미필 표기로 분류된 후보입니다. 후보 이름을 누르면 상세 공개정보의 병역 원문을 확인할 수 있습니다.</p>
    </section>`;
  window.scrollTo({ top: 0, behavior: 'instant' });
}

function renderTrendLocalFull(sd, local) {
  sd = canonicalSidoName(sd);
  const sdLabel = sidoDisplayName(sd);
  const app = document.getElementById('app');
  app.className = '';
  if (!state.data) {
    app.innerHTML = '<div class="loading">불러오는 중…</div>';
    return;
  }
  const ds = buildDisclosureStats();
  const rows = ds.rows.filter(r => r.sd === sd && localDistrictName(r) === local);
  if (!rows.length) {
    app.innerHTML = `
      <nav class="breadcrumb"><a href="#trend">출마자 한눈에</a><span class="sep">›</span><a href="${trendRegionHref(sd)}">${escapeHtml(sdLabel || '지역')}</a><span class="sep">›</span><span class="current">${escapeHtml(local || '시군구')}</span></nav>
      <div class="error-banner"><strong>시군구 통계를 찾지 못했습니다.</strong> 다시 지역을 선택해 주세요.</div>`;
    return;
  }

  const summary = disclosureSummaryFromRows(rows);
  const militaryNotServedRows = militaryCandidateRows(rows);
  const title = `${sdLabel} ${local}`;
  app.innerHTML = `
    <nav class="breadcrumb"><a href="#trend">출마자 한눈에</a><span class="sep">›</span><a href="${trendRegionHref(sd)}">${escapeHtml(sdLabel)} 상세 통계</a><span class="sep">›</span><span class="current">${escapeHtml(local)}</span></nav>
    <div class="detail-head">
      <div>
        <h1 class="detail-title">${escapeHtml(title)} 공개정보 상세</h1>
        <button type="button" class="page-share" data-share-page data-share-title="${escapeHtml(title)} 공개정보 상세 - 6·3 선거 출마자 2026">🔗 이 페이지 공유</button>
      </div>
      <div class="detail-inline-stats">
        <span>공개정보 ${summary.rows.length.toLocaleString()}명</span>
        <span>재산 중앙값 ${formatEok(summary.assets.median)}</span>
        <span>전과 ${formatPct(summary.criminal.rate)}</span>
        <span>병역 미필 ${formatPct(summary.military.notServedRate)}</span>
      </div>
    </div>
    <p class="page-intro">${escapeHtml(sdLabel)} 상세 통계에서 한 단계 내려온 시군구 화면입니다. 해당 시군구 선거구로 분류되는 후보의 재산·전과 상위 후보와 병역 미필 명단을 함께 확인할 수 있습니다.</p>

    ${disclosureRegionOverviewHtml(title, summary)}

    <section class="trend-section">
      <h3 class="trend-section-title">${escapeHtml(local)} 병역 미필 후보 <small>${militaryNotServedRows.length.toLocaleString()}명 전체</small></h3>
      ${militaryCandidateListHtml(militaryNotServedRows, {
        includeRegion: false,
        emptyText: `${local}에서 병역 미필로 표시된 남성 후보가 없습니다.`,
      })}
      <p class="trend-meta">병역 미필률은 병역 대상 남성만 분모로 계산합니다. 여성 후보와 “해당없음(비대상)”으로 공개된 남성 후보는 분모에서 제외됩니다.</p>
    </section>

    <section class="trend-section">
      <h3 class="trend-section-title">${escapeHtml(local)} 후보별 최다 순위 <small>재산·전과 1~5위</small></h3>
      <div class="candidate-leader-grid">
        <div class="candidate-leader-card">
          <h4 class="metric-title">재산 1~5위</h4>
          ${candidateRankList(rankedAssetCandidates(rows, 5), 'asset', false)}
        </div>
        <div class="candidate-leader-card">
          <h4 class="metric-title">전과 1~5위</h4>
          ${candidateRankList(rankedCriminalCandidates(rows, 5), 'criminal', false)}
        </div>
      </div>
      <p class="trend-meta">시도지사·교육감처럼 시도 전체 선거 후보는 시군구 후보 순위에서 제외됩니다. 후보 이름을 누르면 선관위 공개정보와 후보 상세를 볼 수 있습니다.</p>
    </section>`;
  window.scrollTo({ top: 0, behavior: 'instant' });
}

function disclosureRegionFocusConfig(focus) {
  const key = String(focus || '').trim();
  const configs = {
    assets: {
      key: 'assets',
      nav: '재산',
      title: '재산 공개정보',
      subject: '재산',
      rankTitle: '재산 상위 후보',
      localTitle: '시군구별 평균 재산',
      rankType: 'asset',
      rankRows: rows => rankedAssetCandidates(rows, 10),
      localRows: rows => rankedAssetGroups(rows.filter(localDistrictName), localDistrictName, 1),
      bars: (items, sd) => assetBars(items, { limit: 99, localLinksSd: sd, focus: 'assets' }),
      summary: (summary) => [
        ['재산 중앙값', formatEok(summary.assets.median), `평균 ${formatEok(summary.assets.avg)} · ${summary.assets.count.toLocaleString()}명`],
        ['재산 평균', formatEok(summary.assets.avg), '선관위 재산신고액 기준'],
        ['공개정보', `${summary.rows.length.toLocaleString()}명`, '후보자 상세 공개정보 기준'],
      ],
      note: '재산은 선관위 후보자 정보공개의 재산신고액을 억원 단위로 환산했습니다.',
    },
    criminal: {
      key: 'criminal',
      nav: '전과',
      title: '전과 공개정보',
      subject: '전과',
      rankTitle: '전과 상위 후보',
      localTitle: '시군구별 전과 보유율',
      rankType: 'criminal',
      rankRows: rows => rankedCriminalCandidates(rows, 10),
      localRows: rows => rankedCriminalGroups(rows.filter(localDistrictName), localDistrictName, 1),
      bars: (items, sd) => criminalBars(items, { limit: 99, localLinksSd: sd, focus: 'criminal' }),
      summary: (summary) => [
        ['전과 보유율', formatPct(summary.criminal.rate), `전과 1건 이상 ${summary.criminal.holders.toLocaleString()}명 / ${summary.criminal.count.toLocaleString()}명`],
        ['전과 총 건수', `${summary.criminal.cases.toLocaleString()}건`, '전과기록유무(건수) 합산'],
        ['공개정보', `${summary.rows.length.toLocaleString()}명`, '후보자 상세 공개정보 기준'],
      ],
      note: '전과 보유율은 전과기록유무(건수)가 1건 이상인 후보 비율입니다.',
    },
    taxCurrent: {
      key: 'taxCurrent',
      nav: '체납',
      title: '현 체납 공개정보',
      subject: '현 체납',
      rankTitle: '현 체납 상위 후보',
      localTitle: '시군구별 현 체납 후보율',
      rankType: 'taxCurrent',
      rankRows: rows => rankedTaxArrearsCandidates(rows, 10, 'taxArrearsCurrent'),
      localRows: rows => rankedTaxArrearsGroups(rows.filter(localDistrictName), localDistrictName, 'taxArrearsCurrent', 1),
      bars: (items, sd) => taxArrearsBars(items, { limit: 99, localLinksSd: sd, focus: 'taxCurrent' }),
      summary: (summary) => [
        ['현 체납 후보', `${summary.taxArrears.currentHolders.toLocaleString()}명`, `공개정보 ${summary.taxArrears.count.toLocaleString()}명 중 ${formatPct(summary.taxArrears.currentRate)}`],
        ['현 체납 합계', moneyDisclosure(summary.taxArrears.totalCurrent) || '0원', '현재 남아 있는 체납액'],
        ['최근 5년 이력', `${summary.taxArrears.holders.toLocaleString()}명`, '과거 체납 이력 별도 기준'],
      ],
      note: '현 체납은 현재 남아 있는 체납액 기준입니다.',
    },
    tax5y: {
      key: 'tax5y',
      nav: '체납',
      title: '최근 5년 체납 공개정보',
      subject: '최근 5년 체납',
      rankTitle: '최근 5년 체납 상위 후보',
      localTitle: '시군구별 최근 5년 체납 후보율',
      rankType: 'tax5y',
      rankRows: rows => rankedTaxArrearsCandidates(rows, 10, 'taxArrears5y'),
      localRows: rows => rankedTaxArrearsGroups(rows.filter(localDistrictName), localDistrictName, 'taxArrears5y', 1),
      bars: (items, sd) => taxArrearsBars(items, { limit: 99, localLinksSd: sd, focus: 'tax5y' }),
      summary: (summary) => [
        ['최근 5년 체납 후보', `${summary.taxArrears.holders.toLocaleString()}명`, `공개정보 ${summary.taxArrears.count.toLocaleString()}명 중 ${formatPct(summary.taxArrears.rate)}`],
        ['최근 5년 체납 합계', moneyDisclosure(summary.taxArrears.total5y) || '0원', '과거 체납 이력 합산'],
        ['현 체납 후보', `${summary.taxArrears.currentHolders.toLocaleString()}명`, '현재 남아 있는 체납액 별도 기준'],
      ],
      note: '최근 5년 체납은 과거 체납 이력 기준입니다. 현 체납과 함께 보되 서로 다른 기준입니다.',
    },
  };
  return configs[key] || configs.assets;
}

function disclosureRegionFocusSummaryHtml(cards) {
  return `
    <div class="disclosure-overview">
      ${cards.map(([label, value, detail]) => `
        <div class="disclosure-card">
          <span class="disclosure-label">${escapeHtml(label)}</span>
          <strong>${value}</strong>
          <small>${escapeHtml(detail)}</small>
        </div>`).join('')}
    </div>`;
}

function renderDisclosureRegionFocusFull(focus, sd, local = '') {
  sd = canonicalSidoName(sd);
  const sdLabel = sidoDisplayName(sd);
  const config = disclosureRegionFocusConfig(focus);
  const app = document.getElementById('app');
  app.className = '';
  if (!state.data) {
    app.innerHTML = '<div class="loading">불러오는 중…</div>';
    return;
  }
  const ds = buildDisclosureStats();
  const rows = ds.rows.filter(r => r.sd === sd && (!local || localDistrictName(r) === local));
  const title = `${sdLabel}${local ? ` ${local}` : ''} ${config.title}`;
  if (!rows.length) {
    app.innerHTML = `
      <nav class="breadcrumb"><a href="#trend">출마자 한눈에</a><span class="sep">›</span><a href="${disclosureFocusHref(config.key === 'tax5y' || config.key === 'taxCurrent' ? 'tax' : config.key)}">${escapeHtml(config.nav)}</a><span class="sep">›</span><span class="current">${escapeHtml(sdLabel || '지역')}</span></nav>
      <div class="error-banner"><strong>${escapeHtml(config.subject)} 지역 통계를 찾지 못했습니다.</strong> 다시 지역을 선택해 주세요.</div>`;
    return;
  }

  const summary = disclosureSummaryFromRows(rows);
  const rankRows = config.rankRows(rows);
  const localItems = local ? [] : config.localRows(rows);
  const focusHref = disclosureFocusHref(config.key === 'tax5y' || config.key === 'taxCurrent' ? 'tax' : config.key);
  app.innerHTML = `
    <nav class="breadcrumb"><a href="#trend">출마자 한눈에</a><span class="sep">›</span><a href="${focusHref}">${escapeHtml(config.nav)}</a><span class="sep">›</span><span class="current">${escapeHtml(sdLabel)}${local ? ` ${escapeHtml(local)}` : ''}</span></nav>
    <div class="detail-head">
      <div>
        <h1 class="detail-title">${escapeHtml(title)}</h1>
        <button type="button" class="page-share" data-share-page data-share-title="${escapeHtml(title)} - 6·3 선거 출마자 2026">🔗 이 페이지 공유</button>
      </div>
      <div class="detail-inline-stats">
        <span>${escapeHtml(config.subject)}</span>
        <span>공개정보 ${summary.rows.length.toLocaleString()}명</span>
      </div>
    </div>
    <p class="page-intro">${escapeHtml(sdLabel)}${local ? ` ${escapeHtml(local)}` : ''} 후보의 ${escapeHtml(config.subject)} 지표만 따로 보는 화면입니다.</p>

    ${disclosureRegionFocusSummaryHtml(config.summary(summary))}

    <section class="trend-section">
      <h3 class="trend-section-title">${escapeHtml(config.rankTitle)} <small>${rankRows.length.toLocaleString()}명</small></h3>
      ${candidateRankList(rankRows, config.rankType, !local)}
      <p class="trend-meta">${escapeHtml(config.note)}</p>
    </section>

    ${!local ? `
      <section class="trend-section">
        <h3 class="trend-section-title">${escapeHtml(config.localTitle)} <small>시군구명 클릭</small></h3>
        <div class="bar-list">${config.bars(localItems, sd) || '<p class="trend-meta">표시할 시군구가 없습니다.</p>'}</div>
      </section>` : ''}`;
  window.scrollTo({ top: 0, behavior: 'instant' });
}

function renderTrendMilitaryRegionFull(sd) {
  sd = canonicalSidoName(sd);
  const sdLabel = sidoDisplayName(sd);
  const app = document.getElementById('app');
  app.className = '';
  if (!state.data) {
    app.innerHTML = '<div class="loading">불러오는 중…</div>';
    return;
  }
  const ds = buildDisclosureStats();
  const rows = ds.rows.filter(r => r.sd === sd);
  if (!rows.length) {
    app.innerHTML = `
      <nav class="breadcrumb"><a href="#trend">출마자 한눈에</a><span class="sep">›</span><a href="#disclosure/military">병역</a><span class="sep">›</span><span class="current">${escapeHtml(sdLabel || '지역')}</span></nav>
      <div class="error-banner"><strong>지역 병역 통계를 찾지 못했습니다.</strong> 다시 지역을 선택해 주세요.</div>`;
    return;
  }

  const summary = disclosureSummaryFromRows(rows);
  const localRows = rows.filter(localDistrictName);
  const sggMilitary = rankedMilitaryGroups(localRows, localDistrictName, 1);
  const militaryNotServedRows = militaryCandidateRows(rows);
  const maxLocalItems = 99;

  app.innerHTML = `
    <nav class="breadcrumb"><a href="#trend">출마자 한눈에</a><span class="sep">›</span><a href="#disclosure/military">병역</a><span class="sep">›</span><span class="current">${escapeHtml(sdLabel)}</span></nav>
    <div class="detail-head">
      <div>
        <h1 class="detail-title">${escapeHtml(sdLabel)} 병역 미필 후보</h1>
        <button type="button" class="page-share" data-share-page data-share-title="${escapeHtml(sdLabel)} 병역 미필 후보 - 6·3 선거 출마자 2026">🔗 이 페이지 공유</button>
      </div>
      <div class="detail-inline-stats">
        <span>미필 ${militaryNotServedRows.length.toLocaleString()}명</span>
        <span>대상 ${summary.military.eligible.toLocaleString()}명</span>
        <span>미필률 ${formatPct(summary.military.notServedRate)}</span>
      </div>
    </div>
    <p class="page-intro">병역 대상 남성 기준의 미필률과 후보 명단을 지역별로 봅니다.</p>

    ${militaryRegionOverviewHtml(sdLabel, summary)}

    <section class="trend-section">
      <h3 class="trend-section-title">${escapeHtml(sdLabel)} 병역 미필 후보 <small>${militaryNotServedRows.length.toLocaleString()}명 전체</small></h3>
      ${militaryCandidateListHtml(militaryNotServedRows, {
        includeRegion: false,
        emptyText: `${sdLabel}에서 병역 미필로 표시된 남성 후보가 없습니다.`,
      })}
      <p class="trend-meta">후보 이름을 누르면 상세 공개정보의 병역 원문을 확인할 수 있습니다.</p>
    </section>

    <section class="trend-section">
      <h3 class="trend-section-title">시군구별 병역 미필률 <small>지역명 클릭</small></h3>
      <div class="bar-list">${militaryBars(sggMilitary, { limit: maxLocalItems, localLinksSd: sd, focus: 'military' }) || '<p class="trend-meta">표시할 시군구가 없습니다.</p>'}</div>
      <p class="trend-meta">시군구별 통계는 해당 시군구 선거구로 분류되는 후보 기준입니다. 시도 전체 선거 후보는 시군구 막대에서는 제외했습니다.</p>
    </section>`;
  window.scrollTo({ top: 0, behavior: 'instant' });
}

function renderTrendMilitaryLocalFull(sd, local) {
  sd = canonicalSidoName(sd);
  const sdLabel = sidoDisplayName(sd);
  const app = document.getElementById('app');
  app.className = '';
  if (!state.data) {
    app.innerHTML = '<div class="loading">불러오는 중…</div>';
    return;
  }
  const ds = buildDisclosureStats();
  const rows = ds.rows.filter(r => r.sd === sd && localDistrictName(r) === local);
  if (!rows.length) {
    app.innerHTML = `
      <nav class="breadcrumb"><a href="#trend">출마자 한눈에</a><span class="sep">›</span><a href="#disclosure/military">병역</a><span class="sep">›</span><a href="${trendMilitaryRegionHref(sd)}">${escapeHtml(sdLabel || '지역')}</a><span class="sep">›</span><span class="current">${escapeHtml(local || '시군구')}</span></nav>
      <div class="error-banner"><strong>시군구 병역 통계를 찾지 못했습니다.</strong> 다시 지역을 선택해 주세요.</div>`;
    return;
  }

  const summary = disclosureSummaryFromRows(rows);
  const militaryNotServedRows = militaryCandidateRows(rows);
  const title = `${sdLabel} ${local}`;
  app.innerHTML = `
    <nav class="breadcrumb"><a href="#trend">출마자 한눈에</a><span class="sep">›</span><a href="#disclosure/military">병역</a><span class="sep">›</span><a href="${trendMilitaryRegionHref(sd)}">${escapeHtml(sdLabel)}</a><span class="sep">›</span><span class="current">${escapeHtml(local)}</span></nav>
    <div class="detail-head">
      <div>
        <h1 class="detail-title">${escapeHtml(title)} 병역 미필 후보</h1>
        <button type="button" class="page-share" data-share-page data-share-title="${escapeHtml(title)} 병역 미필 후보 - 6·3 선거 출마자 2026">🔗 이 페이지 공유</button>
      </div>
      <div class="detail-inline-stats">
        <span>미필 ${militaryNotServedRows.length.toLocaleString()}명</span>
        <span>대상 ${summary.military.eligible.toLocaleString()}명</span>
        <span>미필률 ${formatPct(summary.military.notServedRate)}</span>
      </div>
    </div>
    <p class="page-intro">병역 대상 남성 중 미필 후보를 시군구 단위로 확인합니다.</p>

    ${militaryRegionOverviewHtml(title, summary)}

    <section class="trend-section">
      <h3 class="trend-section-title">${escapeHtml(local)} 병역 미필 후보 <small>${militaryNotServedRows.length.toLocaleString()}명 전체</small></h3>
      ${militaryCandidateListHtml(militaryNotServedRows, {
        includeRegion: false,
        emptyText: `${local}에서 병역 미필로 표시된 남성 후보가 없습니다.`,
      })}
      <p class="trend-meta">병역 미필률은 병역 대상 남성만 분모로 계산합니다. 여성 후보와 병역 비대상 남성 후보는 분모에서 제외됩니다.</p>
    </section>`;
  window.scrollTo({ top: 0, behavior: 'instant' });
}

function disclosureStatsHtml(ds) {
  if (!ds.rows.length) return '';
  return `${assetFocusHtml(ds)}${criminalFocusHtml(ds)}${taxArrearsFocusHtml(ds)}${militaryFocusHtml(ds)}`;
}

function assetFocusHtml(ds) {
  return `
    <section class="trend-section">
      <h3 class="trend-section-title">재산 상위 후보 <small>전체 1~5위</small></h3>
      ${candidateRankList(ds.leaders.assetsOverall, 'asset', true)}
      <p class="trend-meta">재산은 선관위 재산신고액(천원)을 억원으로 환산했습니다. 후보 이름을 누르면 후보 상세 공개정보를 볼 수 있습니다.</p>
    </section>

    <section class="trend-section">
      <h3 class="trend-section-title">재산 통계 <small>정당별·지역별</small></h3>
      <div class="metric-grid">
        <div>
          <h4 class="metric-title">정당별 평균 재산 <small>20명 이상</small></h4>
          <div class="bar-list">${assetBars(ds.byParty.assets) || '<p class="trend-meta">표시할 정당이 없습니다.</p>'}</div>
        </div>
        <div>
          <h4 class="metric-title">지역별 평균 재산 <small>지역명 클릭</small></h4>
          <div class="bar-list">${assetBars(ds.byRegion.assets, { regionLinks: true, focus: 'assets' }) || '<p class="trend-meta">표시할 지역이 없습니다.</p>'}</div>
        </div>
      </div>
    </section>`;
}

function criminalFocusHtml(ds) {
  return `
    <section class="trend-section">
      <h3 class="trend-section-title">전과 상위 후보 <small>전체 1~5위</small></h3>
      ${candidateRankList(ds.leaders.criminalOverall, 'criminal', true)}
      <p class="trend-meta">전과 건수는 선관위 후보자 정보공개의 전과기록유무(건수) 기준입니다. 범죄 유형은 아래 전과 원문 분류에서 따로 확인할 수 있습니다.</p>
    </section>

    <section class="trend-section">
      <h3 class="trend-section-title">전과 통계 <small>정당별·지역별</small></h3>
      <div class="metric-grid">
        <div>
          <h4 class="metric-title">정당별 전과 보유율 <small>20명 이상</small></h4>
          <div class="bar-list">${criminalBars(ds.byParty.criminal) || '<p class="trend-meta">표시할 정당이 없습니다.</p>'}</div>
        </div>
        <div>
          <h4 class="metric-title">지역별 전과 보유율 <small>지역명 클릭</small></h4>
          <div class="bar-list">${criminalBars(ds.byRegion.criminal, { regionLinks: true, focus: 'criminal' }) || '<p class="trend-meta">표시할 지역이 없습니다.</p>'}</div>
        </div>
      </div>
      <p class="trend-meta">전과 보유율은 전과기록유무(건수)가 1건 이상인 후보 비율입니다. 예: 전체 전과 ${formatPct(ds.criminal.rate)}는 전체 ${ds.criminal.count.toLocaleString()}명 중 ${ds.criminal.holders.toLocaleString()}명이 전과 1건 이상이라는 뜻입니다.</p>
    </section>

    ${criminalOcrOverviewHtml()}`;
}

function taxArrearsFocusHtml(ds) {
  return `
    <section class="trend-section">
      <div class="section-title-row">
        <h3 class="trend-section-title">체납 상위 후보 <small>최근 5년·현 체납</small></h3>
        <div class="section-actions">
          <a href="${taxArrearsListHref('5y')}">최근 5년 명단</a>
          <a href="${taxArrearsListHref('current')}">현 체납 명단</a>
        </div>
      </div>
      <div class="candidate-leader-grid">
        <div class="candidate-leader-card">
          <h4 class="metric-title">최근 5년 체납 상위 1~5위</h4>
          ${candidateRankList(ds.leaders.taxArrears5yOverall, 'tax5y', true)}
          <a class="rank-more-link" href="${taxArrearsListHref('5y')}">${ds.taxArrears.holders.toLocaleString()}명 전체 명단</a>
        </div>
        <div class="candidate-leader-card">
          <h4 class="metric-title">현 체납 상위 1~5위</h4>
          ${candidateRankList(ds.leaders.taxArrearsCurrentOverall, 'taxCurrent', true)}
          <a class="rank-more-link" href="${taxArrearsListHref('current')}">${ds.taxArrears.currentHolders.toLocaleString()}명 전체 명단</a>
        </div>
      </div>
    </section>

    <section class="trend-section">
      <h3 class="trend-section-title">정당별 체납 후보율 <small>좌: 현 체납 · 우: 최근 5년</small></h3>
      <div class="metric-grid">
        <div>
          <h4 class="metric-title">정당별 현 체납 후보율 <small>20명 이상</small></h4>
          <div class="bar-list">${taxArrearsBars(ds.byParty.taxArrearsCurrent) || '<p class="trend-meta">표시할 정당이 없습니다.</p>'}</div>
        </div>
        <div>
          <h4 class="metric-title">정당별 최근 5년 체납 후보율 <small>20명 이상</small></h4>
          <div class="bar-list">${taxArrearsBars(ds.byParty.taxArrears5y) || '<p class="trend-meta">표시할 정당이 없습니다.</p>'}</div>
        </div>
      </div>
    </section>

    <section class="trend-section">
      <h3 class="trend-section-title">지역별 체납 후보율 <small>좌: 현 체납 · 우: 최근 5년</small></h3>
      <div class="metric-grid">
        <div>
          <h4 class="metric-title">지역별 현 체납 후보율 <small>지역명 클릭</small></h4>
          <div class="bar-list">${taxArrearsBars(ds.byRegion.taxArrearsCurrent, { regionLinks: true, focus: 'taxCurrent' }) || '<p class="trend-meta">표시할 지역이 없습니다.</p>'}</div>
        </div>
        <div>
          <h4 class="metric-title">지역별 최근 5년 체납 후보율 <small>지역명 클릭</small></h4>
          <div class="bar-list">${taxArrearsBars(ds.byRegion.taxArrears5y, { regionLinks: true, focus: 'tax5y' }) || '<p class="trend-meta">표시할 지역이 없습니다.</p>'}</div>
        </div>
      </div>
      <p class="trend-meta">체납은 선관위 후보자 정보공개의 납세 자료 기준입니다. 현 체납은 현재 남아 있는 체납액, 최근 5년 체납은 과거 체납 이력을 뜻하므로 둘을 나누어 봐야 합니다.</p>
    </section>`;
}

function militaryFocusHtml(ds) {
  return `
    <section class="trend-section">
      <h3 class="trend-section-title">병역 통계 <small>정당별·지역별</small></h3>
      <div class="metric-grid">
        <div>
          <h4 class="metric-title">정당별 미필률 <small>병역 대상 10명 이상</small></h4>
          <div class="bar-list">${militaryBars(ds.byParty.military) || '<p class="trend-meta">표시할 정당이 없습니다.</p>'}</div>
        </div>
        <div>
          <h4 class="metric-title">지역별 미필률 <small>높은 순 · 지역명 클릭</small></h4>
          <div class="bar-list">${militaryBars(ds.byRegion.military, { regionLinks: true, focus: 'military' }) || '<p class="trend-meta">표시할 지역이 없습니다.</p>'}</div>
        </div>
      </div>
      <p class="trend-meta">남성 병역 미필률 ${formatPct(ds.military.notServedRate)}는 병역 대상 남성 ${ds.military.eligible.toLocaleString()}명 중 ${ds.military.notServed.toLocaleString()}명이 미필이라는 뜻입니다. 여성 후보는 병역 통계에서 제외했고, 남성 후보 중 병역 비대상도 분모에서 제외했습니다.</p>
    </section>`;
}

function disclosureFocusPageConfig(kind, ds) {
  const key = String(kind || 'assets').toLowerCase();
  const configs = {
    assets: {
      key: 'assets',
      title: '재산 집중 보기',
      stats: [`중앙값 ${formatEok(ds.assets.median)}`, `평균 ${formatEok(ds.assets.avg)}`, `${ds.assets.count.toLocaleString()}명`],
      intro: '선관위 후보자 정보공개의 재산신고액을 정당별·지역별 평균과 후보별 상위 순위로 분리해 봅니다.',
      body: assetFocusHtml(ds),
    },
    criminal: {
      key: 'criminal',
      title: '전과 집중 보기',
      stats: [`전과 ${formatPct(ds.criminal.rate)}`, `${ds.criminal.holders.toLocaleString()}명`, `총 ${ds.criminal.cases.toLocaleString()}건`],
      intro: '전과 보유율과 전과 PDF 죄명 영역 분류를 한 화면에서 봅니다. 직책과 범죄 유형을 함께 확인해야 합니다.',
      body: criminalFocusHtml(ds),
    },
    tax: {
      key: 'tax',
      title: '체납 집중 보기',
      stats: [`최근 5년 ${ds.taxArrears.holders.toLocaleString()}명`, `현 체납 ${ds.taxArrears.currentHolders.toLocaleString()}명`, `최근 5년 합계 ${moneyDisclosure(ds.taxArrears.total5y) || '0원'}`],
      intro: '체납은 전과와 별도의 검증 축입니다. 최근 5년 체납 이력을 먼저 보고, 현재 남아 있는 체납액도 함께 확인합니다.',
      body: taxArrearsFocusHtml(ds),
    },
    military: {
      key: 'military',
      title: '병역 집중 보기',
      stats: [`미필 ${formatPct(ds.military.notServedRate)}`, `대상 ${ds.military.eligible.toLocaleString()}명`, `미필 ${ds.military.notServed.toLocaleString()}명`],
      intro: '남성 후보 중 병역 대상자를 기준으로 정당별·지역별 미필률을 분리해 봅니다.',
      body: militaryFocusHtml(ds),
    },
  };
  return configs[key] || configs.assets;
}

function renderDisclosureFocusFull(kind = 'assets') {
  const app = document.getElementById('app');
  app.className = '';
  if (!state.data) {
    app.innerHTML = '<div class="loading">불러오는 중…</div>';
    return;
  }
  const ds = buildDisclosureStats();
  const config = disclosureFocusPageConfig(kind, ds);
  app.innerHTML = `
    <nav class="breadcrumb"><a href="#trend">출마자 한눈에</a><span class="sep">›</span><span class="current">${escapeHtml(config.title)}</span></nav>
    <div class="detail-head">
      <div>
        <h1 class="detail-title">${escapeHtml(config.title)}</h1>
        <button type="button" class="page-share" data-share-page data-share-title="${escapeHtml(config.title)} - 6·3 선거 출마자 2026">🔗 이 페이지 공유</button>
      </div>
      <div class="detail-inline-stats">
        ${config.stats.map(stat => `<span>${escapeHtml(stat)}</span>`).join('')}
      </div>
    </div>
    <p class="page-intro">${escapeHtml(config.intro)}</p>
    ${disclosureFocusTabsHtml(config.key)}
    ${config.body}`;
  window.scrollTo({ top: 0, behavior: 'instant' });
}

function criminalOcrCategoryItems() {
  const fromPayload = Array.isArray(state.criminalOcr?.categories)
    ? state.criminalOcr.categories
        .filter(item => item?.category && item.count > 0)
        .map(item => ({ ...crimeCategoryMeta(item.category), ...item, count: item.count }))
    : [];
  if (fromPayload.length) return fromPayload.sort(compareCrimeCategories);

  const counts = {};
  for (const record of criminalOcrRecords()) {
    for (const category of record.categories || []) {
      counts[category] = (counts[category] || 0) + 1;
    }
  }
  return Object.entries(counts)
    .map(([category, count]) => ({ ...crimeCategoryMeta(category), category, count }))
    .sort(compareCrimeCategories);
}

function crimeHasPriority(categories = []) {
  return categories.some(category => crimeCategoryMeta(category).tone === 'priority');
}

function electionOfficeTitle(item) {
  return SG_TITLE[String(item?.sgTypecode || '')] || '';
}

function criminalOfficeLine(candidate, record) {
  const source = candidate || record || {};
  const office = electionOfficeTitle(candidate);
  const region = formatRegionLabel(source);
  return [...new Set([office, region].filter(Boolean))].join(' · ');
}

function criminalAuditRows() {
  return (state.data?.candidates || [])
    .filter(isActiveCandidate)
    .map(candidate => {
      const id = String(candidate.huboid || '');
      const detail = state.candidateDetails?.[id] || null;
      const disclosures = detail?.disclosures || {};
      const record = criminalOcrRecordFor(id);
      const categories = (record?.categories || []).filter(Boolean);
      const criminal = parseCriminalCount(disclosures.criminal_record);
      return {
        candidate,
        record,
        party: candidate.jdName || '무소속',
        sd: sidoFor(candidate) || '지역 미상',
        officeType: electionOfficeTitle(candidate) || '선거 구분 미상',
        criminal,
        hasCriminal: criminal > 0,
        categories,
        categorized: categories.length > 0,
        priority: crimeHasPriority(categories),
      };
    });
}

function summarizeCrimeAuditGroups(rows, keyFn, minCount = 20, category = '') {
  return Object.entries(groupDisclosureRows(rows, keyFn))
    .map(([label, items]) => {
      const criminalHolders = items.filter(row => row.hasCriminal).length;
      const categorized = items.filter(row => row.categorized).length;
      const priority = items.filter(row => row.priority).length;
      const categoryHits = category
        ? items.filter(row => row.categories.includes(category)).length
        : 0;
      const categoryCounts = {};
      for (const row of items) {
        for (const cat of row.categories) categoryCounts[cat] = (categoryCounts[cat] || 0) + 1;
      }
      const topCategories = Object.entries(categoryCounts)
        .map(([cat, count]) => ({ cat, count }))
        .sort((a, b) => b.count - a.count || compareCrimeCategories(a.cat, b.cat))
        .slice(0, 3);
      return {
        label,
        count: items.length,
        criminalHolders,
        categorized,
        priority,
        categoryHits,
        criminalRate: items.length ? criminalHolders / items.length * 100 : 0,
        priorityRate: items.length ? priority / items.length * 100 : 0,
        categoryRate: items.length ? categoryHits / items.length * 100 : 0,
        topCategories,
      };
    })
    .filter(row => row.count >= minCount)
    .sort((a, b) => {
      const aMetric = category ? a.categoryRate : a.priorityRate;
      const bMetric = category ? b.categoryRate : b.priorityRate;
      return bMetric - aMetric || b.priority - a.priority || b.criminalRate - a.criminalRate || b.count - a.count;
    });
}

function crimeAuditBars(items, options = {}) {
  const shown = items.slice(0, options.limit ?? 8);
  const metric = options.category ? 'categoryRate' : 'priorityRate';
  const max = Math.max(...shown.map(x => x[metric]), 1);
  return shown.map(x => {
    const label = options.regionLinks ? sidoDisplayName(x.label) : x.label;
    const subText = options.category
      ? `${x.categoryHits.toLocaleString()}명 / ${x.count.toLocaleString()}명 · 전과 ${formatPct(x.criminalRate)}`
      : `검증 ${x.priority.toLocaleString()}명 · 전과 ${formatPct(x.criminalRate)} · ${x.count.toLocaleString()}명`;
    return metricBar(
      label,
      x[metric],
      max,
      options.category ? '#7a4a00' : 'var(--accent)',
      formatPct(x[metric]),
      subText,
      metricLinkHref(x.label, options)
    );
  }).join('');
}

const CRIME_COMPOSITION_COLORS = ['#c41e3a', '#2c5d8f', '#3c7a57', '#b36b00', '#7357a4', '#00747a', '#8f3d5a', '#5b6570'];

function summarizeCrimeComposition(rows, keyFn, options = {}) {
  const total = rows.length;
  const limit = options.limit ?? 8;
  const entries = Object.entries(groupDisclosureRows(rows, keyFn))
    .map(([label, items]) => ({ label, count: items.length }))
    .sort((a, b) => b.count - a.count || koSort(a.label, b.label));
  const shown = entries.slice(0, limit);
  const otherCount = entries.slice(limit).reduce((sum, item) => sum + item.count, 0);
  const items = shown.map((item, idx) => ({
    ...item,
    pct: total ? item.count / total * 100 : 0,
    color: options.colorFor ? options.colorFor(item.label, idx) : CRIME_COMPOSITION_COLORS[idx % CRIME_COMPOSITION_COLORS.length],
  }));
  if (otherCount) {
    items.push({
      label: '그 외',
      count: otherCount,
      pct: total ? otherCount / total * 100 : 0,
      color: '#c9c1b6',
      other: true,
    });
  }
  return { total, items, groupCount: entries.length };
}

function crimePieStyle(items) {
  if (!items.length) return 'background: var(--bg);';
  let cursor = 0;
  const segments = items.map(item => {
    const start = cursor;
    const end = cursor + item.pct;
    cursor = end;
    return `${item.color} ${start.toFixed(2)}% ${end.toFixed(2)}%`;
  });
  return `background: conic-gradient(${segments.join(', ')});`;
}

function crimeCompositionPanelHtml(title, composition, options = {}) {
  const { total, items } = composition;
  if (!total || !items.length) return '';
  const list = items.map(item => {
    const href = options.regionLinks && !item.other ? metricLinkHref(item.label, { regionLinks: true }) : '';
    const label = options.regionLinks && !item.other ? sidoDisplayName(item.label) : item.label;
    const labelHtml = href
      ? `<a href="${href}" class="crime-share-link">${escapeHtml(label)}</a>`
      : `<span class="crime-share-label">${escapeHtml(label)}</span>`;
    return `
      <li class="crime-share-item">
        <span class="crime-share-dot" style="background:${item.color}"></span>
        ${labelHtml}
        <strong>${item.count.toLocaleString()}명 <small>${formatPct(item.pct)}</small></strong>
      </li>`;
  }).join('');
  return `
    <div class="crime-share-panel">
      <div class="crime-share-head">
        <h4 class="metric-title">${escapeHtml(title)}</h4>
      </div>
      <div class="crime-share-body">
        <div class="crime-pie" style="${crimePieStyle(items)}" role="img" aria-label="${escapeHtml(title)} 구성 파이 차트">
          <div class="crime-pie-center"><strong>${total.toLocaleString()}</strong><span>명</span></div>
        </div>
        <ol class="crime-share-list">${list}</ol>
      </div>
    </div>`;
}

function crimeAuditSnapshotHtml(rows, records, meta) {
  const processed = meta.processed || records.length;
  const failures = meta.failures || 0;
  const totalTarget = Number(meta.total_candidates_with_criminal_pdf) || processed;
  const categorized = records.filter(record => (record.categories || []).length).length;
  const priority = records.filter(record => crimeHasPriority(record.categories || [])).length;
  const unclassified = Math.max(0, processed - categorized);
  return `
    <div class="crime-stat-grid">
      <div class="crime-stat">
        <span>분류 대상</span>
        <strong>${processed.toLocaleString()}명</strong>
        <small>전과 PDF 대상 ${totalTarget.toLocaleString()}명 중${failures ? ` · 미확인 ${failures.toLocaleString()}건` : ''}</small>
      </div>
      <div class="crime-stat">
        <span>검증 유형</span>
        <strong>${priority.toLocaleString()}명</strong>
        <small>부패·공직윤리·성범죄·음주·위험운전 등</small>
      </div>
      <div class="crime-stat">
        <span>분류 완료</span>
        <strong>${categorized.toLocaleString()}명</strong>
        <small>미분류 ${unclassified.toLocaleString()}명은 원문 확인 우선</small>
      </div>
    </div>`;
}

function crimeAuditLeadersHtml(rows) {
  if (!rows.length) return '';
  const priorityRows = rows.filter(row => row.priority);
  if (!priorityRows.length) return '';
  const byParty = summarizeCrimeComposition(priorityRows, row => row.party, { limit: 8, colorFor: label => partyColor(label) });
  const byOffice = summarizeCrimeComposition(priorityRows, row => row.officeType, { limit: 6 });
  const byRegion = summarizeCrimeComposition(priorityRows, row => row.sd, { limit: 8 });
  return `
    <div class="crime-share-grid">
      ${crimeCompositionPanelHtml('검증 유형 정당 구성', byParty)}
      ${crimeCompositionPanelHtml('검증 유형 직책 구성', byOffice)}
      ${crimeCompositionPanelHtml('검증 유형 지역 구성', byRegion, { regionLinks: true })}
    </div>`;
}

function crimeCategoryAuditPanelHtml(category) {
  if (!category) return '';
  const rows = criminalAuditRows().filter(row => row.categories.includes(category));
  if (!rows.length) return '';
  const byParty = summarizeCrimeComposition(rows, row => row.party, { limit: 8, colorFor: label => partyColor(label) });
  const byOffice = summarizeCrimeComposition(rows, row => row.officeType, { limit: 6 });
  const byRegion = summarizeCrimeComposition(rows, row => row.sd, { limit: 8 });
  return `
    <section class="trend-section crime-category-audit">
      <h3 class="trend-section-title">${escapeHtml(category)} 후보 구성 <small>이 유형 ${rows.length.toLocaleString()}명 중 비중</small></h3>
      <div class="crime-share-grid">
        ${crimeCompositionPanelHtml('정당별 구성', byParty)}
        ${crimeCompositionPanelHtml('직책별 구성', byOffice)}
        ${crimeCompositionPanelHtml('지역별 구성', byRegion, { regionLinks: true })}
      </div>
      <p class="trend-meta">후보 전체 대비율이 아니라, 이 범죄 유형으로 분류된 후보 안에서 누가 얼마나 차지하는지 보는 구성비입니다. 공천 규모가 큰 정당·지역은 비중이 커질 수 있으므로 아래 명단의 직책과 원문을 함께 확인해야 합니다.</p>
    </section>`;
}

function crimeChipHtml(item, currentCategory = '') {
  const meta = crimeCategoryMeta(item.category);
  const badge = meta.tone === 'context' ? '맥락' : '';
  return `
    <a class="crime-chip crime-chip-${meta.tone}${item.category === currentCategory ? ' active' : ''}" href="${criminalCategoryHref(item.category)}">
      <strong>${escapeHtml(item.category)}</strong>
      <span>${item.count.toLocaleString()}명</span>
      ${badge ? `<em>${badge}</em>` : ''}
    </a>`;
}

function criminalCategoryChipsHtml(currentCategory = '') {
  const items = criminalOcrCategoryItems();
  if (!items.length) return '';
  const groups = [
    { group: '공직 검증', note: '사기, 횡령, 배임, 뇌물, 청탁금지, 직권남용, 허위공문서·문서위조, 성범죄, 음주·위험운전 등' },
    { group: '폭력·질서', note: '폭력·공무집행방해·업무방해 등' },
    { group: '교통·안전 법규', note: '일반 교통사고·도로교통·자동차 관련 법규 위반' },
    { group: '경제·금융 법규', note: '보험·대부·수표·전자금융 등 경제거래 관련 법규 위반' },
    { group: '생활·안전 법규', note: '환경·식품·건축·건설 관련 법규 위반' },
    { group: '공직·행정 법규', note: '국가공무원법·지방공무원법 등 행정·공직 관련 법규 위반' },
    { group: '시국·안보 관련', note: '국가보안법은 시대·사건 맥락 확인 필요' },
    { group: '집회·시위 관련', note: '집시법 등 집회·시위 관련 법규 위반' },
    { group: '기타', note: '명예훼손·모욕·저작권·마약·도박 등' },
  ].map(def => ({ ...def, items: items.filter(item => crimeCategoryMeta(item.category).group === def.group) }))
    .filter(def => def.items.length);

  return `<div class="crime-chip-groups">${groups.map(def => `
    <div class="crime-chip-group">
      <h4 class="crime-chip-heading">${escapeHtml(def.group)}${def.note ? ` <small>${escapeHtml(def.note)}</small>` : ''}</h4>
      <div class="crime-chip-list">${def.items.map(item => crimeChipHtml(item, currentCategory)).join('')}</div>
    </div>
  `).join('')}</div>`;
}

function criminalOcrOverviewHtml() {
  const records = criminalOcrRecords();
  const chips = criminalCategoryChipsHtml();
  if (!records.length || !chips) return '';

  const meta = state.criminalOcr?.meta || {};
  const rows = criminalAuditRows();
  const partialText = meta.partial ? ' 일부 PDF는 선관위 오류 응답 등으로 분류에서 제외됐습니다.' : '';
  return `
    <section class="trend-section">
      <h3 class="trend-section-title">전과 원문 분류 <small>선관위 PDF 기준</small></h3>
      <div class="crime-overview">
        ${crimeAuditSnapshotHtml(rows, records, meta)}
        ${crimeAuditLeadersHtml(rows)}
        ${chips}
      </div>
      <p class="trend-meta">선관위 전과 PDF의 죄명 영역을 넓은 범죄 유형으로 묶었습니다. 횡령과 배임, 명예훼손과 모욕처럼 서로 다른 죄명은 따로 표시하고, 일반 교통사고·보험/금융 법규 등은 공직 검증 묶음과 분리했습니다. 정당·직책·지역 구성은 공직 검증 유형 후보 안에서의 비중입니다. 최종 판단은 후보 상세의 선관위 원문으로 확인해야 합니다.${partialText}</p>
    </section>`;
}

function criminalFallbackCandidateRow(record) {
  return `
    <div class="candidate">
      <div class="candidate-color" style="background:var(--ink-sub)"></div>
      <span class="candidate-name">${escapeHtml(record.name || record.huboid || '후보')}</span>
      <div class="candidate-party">${escapeHtml(record.party || '정당 미상')}</div>
      <span class="candidate-actions"></span>
    </div>`;
}

function criminalCandidateEntry(item, category) {
  const record = item.record;
  const candidate = item.candidate;
  const terms = (record.matched_terms?.[category] || []).filter(Boolean);
  const officeLine = criminalOfficeLine(candidate, record);
  const necDetailUrl = record.nec_detail_url || necDetailUrlForHuboid(record.huboid);
  const sourceLink = necDetailUrl
    ? `<a class="crime-source-link" href="${escapeHtml(necDetailUrl)}" target="_blank" rel="noopener">선관위 상세 확인</a>`
    : '';
  const termText = terms.length
    ? `분류 근거: ${terms.map(escapeHtml).join(', ')}`
    : '죄명 영역 기준 분류';
  return `
    <div class="crime-candidate-entry">
      ${candidate ? candidateRow(candidate) : criminalFallbackCandidateRow(record)}
      <div class="crime-row-detail">
        ${officeLine ? `<span class="crime-row-office">${escapeHtml(officeLine)}</span>` : ''}
        <span>${termText}</span>
        ${criminalOcrCategoriesHtml(record, category)}
        ${sourceLink}
      </div>
    </div>`;
}

function renderCriminalCategoryFull(category) {
  const app = document.getElementById('app');
  app.className = '';
  const categoryLabel = String(category || '').trim();
  const records = criminalOcrRecords();
  const allChips = criminalCategoryChipsHtml(categoryLabel);
  const auditPanel = crimeCategoryAuditPanelHtml(categoryLabel);
  const matches = records
    .filter(record => (record.categories || []).includes(categoryLabel))
    .map(record => ({ record, candidate: findCandidateByHuboid(record.huboid) }));

  const byRegion = matches.reduce((acc, item) => {
    const region = sidoFor(item.candidate || item.record) || '지역 미상';
    (acc[region] ||= []).push(item);
    return acc;
  }, {});
  const groups = Object.entries(byRegion).sort((a, b) => sidoSort(a[0], b[0]) || b[1].length - a[1].length);
  for (const [, items] of groups) {
    items.sort((a, b) => {
      const aRegion = formatRegionLabel(a.candidate || a.record);
      const bRegion = formatRegionLabel(b.candidate || b.record);
      return koSort(aRegion, bRegion) || koSort(a.candidate?.name || a.record.name || '', b.candidate?.name || b.record.name || '');
    });
  }

  const groupsHtml = groups.map(([region, items]) => `
    <section class="candidate-card crime-region-card">
      <div class="cc-header">
        <div class="cc-name">${escapeHtml(sidoDisplayName(region))}</div>
        <div class="cc-count">${items.length.toLocaleString()}명</div>
      </div>
      ${items.map(item => criminalCandidateEntry(item, categoryLabel)).join('')}
    </section>
  `).join('');

  const bodyHtml = records.length
    ? (matches.length ? groupsHtml : `<p class="absence-note">${escapeHtml(categoryLabel)} 유형으로 분류된 후보가 아직 없습니다.</p>`)
    : '<p class="absence-note">전과 원문 분류 색인이 아직 생성되지 않았습니다.</p>';

  app.innerHTML = `
    <nav class="breadcrumb"><a href="#trend">출마자 한눈에</a><span class="sep">›</span><span class="current">범죄 유형별 전과</span></nav>
    <div class="detail-head">
      <div>
        <h1 class="detail-title">${escapeHtml(categoryLabel || '범죄 유형')} 전과 후보</h1>
        <button type="button" class="page-share" data-share-page data-share-title="${escapeHtml(categoryLabel || '범죄 유형')} 전과 후보 - 6·3 선거 출마자 2026">🔗 이 페이지 공유</button>
      </div>
      <div class="detail-inline-stats">
        <span>${matches.length.toLocaleString()}명</span>
        <span>${groups.length.toLocaleString()}개 시도</span>
      </div>
    </div>
    <p class="page-intro">전과 PDF의 죄명 영역에서 ${escapeHtml(categoryLabel || '선택한 유형')} 관련 표현이 확인된 후보입니다. 인용·보도 시에는 선관위 후보자 상세 페이지의 원문을 함께 확인해 주세요.</p>
    ${allChips}
    ${auditPanel}
    ${bodyHtml}`;
  window.scrollTo({ top: 0, behavior: 'instant' });
}

function taxArrearsTabsHtml(ds, currentSlug) {
  const tabs = [
    { mode: '5y', count: ds.taxArrears.holders },
    { mode: 'current', count: ds.taxArrears.currentHolders },
  ];
  return `
    <div class="tax-mode-tabs" aria-label="체납 명단 기준">
      ${tabs.map(tab => {
        const cfg = taxArrearsModeConfig(tab.mode);
        return `<a href="${taxArrearsListHref(tab.mode)}" class="${cfg.slug === currentSlug ? 'active' : ''}">${cfg.label} <strong>${tab.count.toLocaleString()}명</strong></a>`;
      }).join('')}
    </div>`;
}

function taxArrearsAmountBands(rows, field) {
  const bands = [
    { label: '1억원 이상', min: 100000, max: Infinity },
    { label: '5천만~1억원', min: 50000, max: 100000 },
    { label: '1천만~5천만원', min: 10000, max: 50000 },
    { label: '100만~1천만원', min: 1000, max: 10000 },
    { label: '100만원 미만', min: 0, max: 1000 },
  ];
  return bands.map(band => {
    const items = rows.filter(row => {
      const value = row[field] || 0;
      return value >= band.min && value < band.max;
    });
    const total = items.reduce((sum, row) => sum + (row[field] || 0), 0);
    const max = items[0]?.[field] || 0;
    return { ...band, items, total, max };
  }).filter(band => band.items.length);
}

function taxArrearsCandidateTableHtml(rows, config) {
  if (!rows.length) return '<p class="absence-note">표시할 체납 후보가 없습니다.</p>';
  const rowsHtml = rows.map((row, index) => {
    const c = row.candidate || {};
    const huboid = String(c.huboid || '');
    const amount = moneyDisclosure(row[config.field]) || '0원';
    const otherAmount = moneyDisclosure(row[config.otherField]) || '0원';
    const paid = moneyDisclosure(row.taxPaid) || '-';
    const office = electionOfficeTitle(c) || '-';
    const region = formatRegionLabel(c) || '-';
    const necDetailUrl = necDetailUrlForHuboid(huboid);
    const sourceLink = necDetailUrl
      ? `<a class="crime-source-link" href="${escapeHtml(necDetailUrl)}" target="_blank" rel="noopener">선관위</a>`
      : '';
    return `
      <tr>
        <td class="tax-rank">${(row.taxRank || index + 1).toLocaleString()}</td>
        <td>
          <button type="button" class="tax-candidate-name candidate-detail-trigger" data-huboid="${escapeHtml(huboid)}" title="${escapeHtml(c.name || '후보')} 상세 정보">${escapeHtml(c.name || '후보')}</button>
        </td>
        <td><span class="tax-party" style="border-color:${partyColor(c.jdName)}">${escapeHtml(c.jdName || '무소속')}</span></td>
        <td>${escapeHtml(office)}</td>
        <td>${escapeHtml(region)}</td>
        <td class="tax-amount"><strong>${amount}</strong></td>
        <td class="tax-secondary"><span>${escapeHtml(config.otherLabel)}</span>${otherAmount}</td>
        <td>${paid}</td>
        <td>${sourceLink}</td>
      </tr>`;
  }).join('');
  return `
    <div class="table-scroll">
      <table class="tax-table">
        <thead>
          <tr>
            <th>순위</th>
            <th>후보</th>
            <th>정당</th>
            <th>직책</th>
            <th>선거구</th>
            <th>${escapeHtml(config.amountLabel)}</th>
            <th>함께 볼 체납</th>
            <th>납부액</th>
            <th>확인</th>
          </tr>
        </thead>
        <tbody>${rowsHtml}</tbody>
      </table>
    </div>`;
}

function taxArrearsTieredTablesHtml(rows, config) {
  if (!rows.length) return '<p class="absence-note">표시할 체납 후보가 없습니다.</p>';
  const rankedRows = rows.map((row, index) => ({ ...row, taxRank: index + 1 }));
  const bands = taxArrearsAmountBands(rankedRows, config.field);
  let opened = false;
  return `
    <div class="tax-tier-list">
      ${bands.map(band => {
        const isOpen = !opened;
        if (isOpen) opened = true;
        return `
          <details class="tax-tier" ${isOpen ? 'open' : ''}>
            <summary>
              <span class="tax-tier-label">${escapeHtml(band.label)}</span>
              <strong>${band.items.length.toLocaleString()}명</strong>
              <small>합계 ${moneyDisclosure(band.total) || '0원'} · 최고 ${moneyDisclosure(band.max) || '0원'}</small>
            </summary>
            ${taxArrearsCandidateTableHtml(band.items, config)}
          </details>`;
      }).join('')}
    </div>`;
}

function renderTaxArrearsFull(mode = 'current') {
  const app = document.getElementById('app');
  app.className = '';
  if (!state.data) {
    app.innerHTML = '<div class="loading">불러오는 중…</div>';
    return;
  }

  const ds = buildDisclosureStats();
  const config = taxArrearsModeConfig(mode);
  const rows = rankedTaxArrearsCandidates(ds.rows, null, config.field);
  const total = ds.taxArrears[config.totalKey] || 0;
  const holderCount = ds.taxArrears[config.holdersKey] || rows.length;
  const rate = ds.taxArrears[config.rateKey] || 0;
  const leader = rows[0];
  const partyComposition = summarizeCrimeComposition(rows, row => row.party, { limit: 8, colorFor: label => partyColor(label) });
  const officeComposition = summarizeCrimeComposition(rows, row => electionOfficeTitle(row.candidate) || '선거 구분 미상', { limit: 6 });
  const regionComposition = summarizeCrimeComposition(rows, row => row.sd || '지역 미상', { limit: 8 });

  app.innerHTML = `
    <nav class="breadcrumb"><a href="#trend">출마자 한눈에</a><span class="sep">›</span><span class="current">체납 명단</span></nav>
    <div class="detail-head">
      <div>
        <h1 class="detail-title">${escapeHtml(config.title)}</h1>
        <button type="button" class="page-share" data-share-page data-share-title="${escapeHtml(config.title)} - 6·3 선거 출마자 2026">🔗 이 페이지 공유</button>
      </div>
      <div class="detail-inline-stats">
        <span>${holderCount.toLocaleString()}명</span>
        <span>합계 ${moneyDisclosure(total) || '0원'}</span>
        <span>전체 ${formatPct(rate)}</span>
      </div>
    </div>
    <p class="page-intro">선관위 후보자 정보공개의 납세 자료에서 ${escapeHtml(config.label)} 금액이 0원보다 큰 후보 전체입니다. 이름만 나열하지 않고 직책·선거구·정당·선관위 상세 링크를 함께 붙여 공직 검증 맥락을 바로 볼 수 있게 했습니다.</p>

    ${taxArrearsTabsHtml(ds, config.slug)}

    <div class="disclosure-overview">
      <div class="disclosure-card">
        <span class="disclosure-label">${escapeHtml(config.label)} 후보</span>
        <strong>${holderCount.toLocaleString()}명</strong>
        <small>공개정보 ${ds.taxArrears.count.toLocaleString()}명 중 ${formatPct(rate)}</small>
      </div>
      <div class="disclosure-card">
        <span class="disclosure-label">체납 합계</span>
        <strong>${moneyDisclosure(total) || '0원'}</strong>
        <small>선관위 공개 금액 합산</small>
      </div>
      <div class="disclosure-card">
        <span class="disclosure-label">최고액</span>
        <strong>${leader ? moneyDisclosure(leader[config.field]) : '0원'}</strong>
        <small>${leader ? `${escapeHtml(leader.candidate?.name || '')} · ${escapeHtml(candidateRankContext(leader.candidate, true))}` : '표시할 후보 없음'}</small>
      </div>
    </div>

    <section class="trend-section">
      <h3 class="trend-section-title">${escapeHtml(config.label)} 구성 <small>해당 후보 안에서의 비중</small></h3>
      <div class="crime-share-grid">
        ${crimeCompositionPanelHtml('정당별 구성', partyComposition)}
        ${crimeCompositionPanelHtml('직책별 구성', officeComposition)}
        ${crimeCompositionPanelHtml('지역별 구성', regionComposition, { regionLinks: true })}
      </div>
      <p class="trend-meta">아래 명단은 ${escapeHtml(config.amountLabel)} 내림차순입니다. 최근 5년 체납은 과거 이력, 현 체납은 현재 남아 있는 체납액이므로 두 기준을 함께 봐야 합니다.</p>
    </section>

    <section class="trend-section">
      <h3 class="trend-section-title">${escapeHtml(config.label)} 명단 <small>${rows.length.toLocaleString()}명 전체 · 체납액 규모별</small></h3>
      ${taxArrearsTieredTablesHtml(rows, config)}
    </section>`;
  window.scrollTo({ top: 0, behavior: 'instant' });
}

// 출마자 한눈에 페이지 (#trend) — 정당·연령·성별·직업 통계
function renderTrendFull() {
  const app = document.getElementById('app');
  app.className = '';
  if (!state.data) {
    app.innerHTML = '<div class="loading">불러오는 중…</div>';
    return;
  }
  const s = buildProfileStats();
  const ds = buildDisclosureStats();
  const womenPct = s.byGender['여'] ? (s.byGender['여'] / s.total * 100) : 0;

  // 정당 (상위 10) — horizontal bar
  const partyTop = s.parties.slice(0, 10);
  const partyMax = partyTop[0] ? partyTop[0][1] : 1;
  const partyBars = partyTop.map(([p, n]) => {
    const color = state.parties[p] || (p === '무소속' ? '#888' : '#bbb');
    return statBar(p, n, partyMax, color);
  }).join('');

  // 연령대 (vertical bar)
  const ageOrder = [20, 30, 40, 50, 60, 70, 80];
  const ageMax = Math.max(...Object.values(s.ageBuckets), 1);
  const ageBars = ageOrder.map(b => {
    const n = s.ageBuckets[b] || 0;
    const pct = (n / ageMax * 100).toFixed(1);
    return `
      <div class="age-bar">
        <div class="age-bar-track">
          <div class="age-bar-fill" style="height: ${pct}%"></div>
        </div>
        <div class="age-bar-value">${n.toLocaleString()}</div>
        <div class="age-bar-label">${b}대</div>
      </div>`;
  }).join('');

  // 성별
  const male = s.byGender['남'] || 0;
  const female = s.byGender['여'] || 0;
  const genderMax = Math.max(male, female, 1);
  const genderBars = `
    ${statBar('남성', male, genderMax, '#2c5d8f')}
    ${statBar('여성', female, genderMax, '#c41e3a')}
  `;

  // 직업 top 10
  const jobMax = s.jobs[0] ? s.jobs[0][1] : 1;
  const jobBars = s.jobs.map(([j, n]) => statBar(j || '미기재', n, jobMax, 'var(--ink-sub)')).join('');

  app.innerHTML = `
    <nav class="breadcrumb"><a href="#">전국</a><span class="sep">›</span><span class="current">출마자 한눈에</span></nav>
    <div class="detail-head">
      <h1 class="detail-title">출마자 한눈에</h1>
      <div class="detail-inline-stats">
        <span>총 ${s.total.toLocaleString()}명 · 평균 ${s.ageAvg.toFixed(1)}세 · 여성 ${womenPct.toFixed(0)}%</span>
      </div>
    </div>
    <p class="page-intro">선관위 등록 데이터와 후보자 정보공개 자료를 기반으로 정당·연령·성별·직업·재산·전과·체납·병역 분포를 정리했습니다.</p>

    ${disclosureFocusCardsHtml(ds)}

    <section class="trend-section">
      <h3 class="trend-section-title">정당별 분포 <small>상위 10</small></h3>
      <div class="bar-list">${partyBars}</div>
    </section>

    <div class="trend-grid">
      <section class="trend-section">
        <h3 class="trend-section-title">연령대 분포</h3>
        <div class="age-chart">${ageBars}</div>
        <p class="trend-meta">평균 ${s.ageAvg.toFixed(1)}세 · ${s.ageCount.toLocaleString()}명 응답</p>
      </section>
      <section class="trend-section">
        <h3 class="trend-section-title">성별 분포</h3>
        <div class="bar-list">${genderBars}</div>
        <p class="trend-meta">여성 비율 ${womenPct.toFixed(1)}%</p>
      </section>
    </div>

    <section class="trend-section">
      <h3 class="trend-section-title">직업 분포 <small>상위 10</small></h3>
      <div class="bar-list">${jobBars}</div>
    </section>`;
  window.scrollTo({ top: 0, behavior: 'instant' });
}

// 오늘의 변경 — 어제·오늘 스냅샷 diff. data/changelog.json 사용.
function renderChangesBox() {
  const cl = state.changelog;
  if (!cl || !cl.previous_date) return '';
  const s = cl.summary;
  const total = s.new + s.gone + s.party + s.status;
  if (total === 0) return '';
  const fmt = d => d ? `${d.slice(0,4)}.${d.slice(4,6)}.${d.slice(6,8)}` : '';
  return `
    <section class="changes">
      <h2 class="section-title">오늘의 변경
        <span class="section-count">${fmt(cl.previous_date)} → ${fmt(cl.today_date)} · 어제와 달라진 ${total.toLocaleString()}건</span>
      </h2>
      <a class="changes-row" href="#changes">
        <span class="changes-stat changes-new"><strong>${s.new.toLocaleString()}</strong>명<small>신규 등록</small></span>
        <span class="changes-stat changes-gone"><strong>${s.gone.toLocaleString()}</strong>명<small>명단 이탈</small></span>
        <span class="changes-stat changes-party"><strong>${s.party.toLocaleString()}</strong>건<small>정당 변경</small></span>
        <span class="changes-stat changes-status"><strong>${s.status.toLocaleString()}</strong>건<small>상태 변경</small></span>
        <span class="changes-arrow">자세히 보기 →</span>
      </a>
    </section>`;
}

// 변경 내역 전체 페이지 (#changes)
function renderChangesFull() {
  const cl = state.changelog;
  const fmt = d => d ? `${d.slice(0,4)}.${d.slice(4,6)}.${d.slice(6,8)}` : '';
  if (!cl || !cl.previous_date) {
    const app = document.getElementById('app');
    app.className = '';
    app.innerHTML = `
      <nav class="breadcrumb"><a href="#">전국</a><span class="sep">›</span><span class="current">오늘의 변경</span></nav>
      <div class="detail-head"><h1 class="detail-title">오늘의 변경</h1></div>
      <p class="absence-note">비교할 어제 스냅샷이 아직 없습니다.</p>`;
    return;
  }
  const titleMap = Object.fromEntries(SECTIONS.map(s => [s.sgTypecode, s.title]));
  const sectionLabel = c => titleMap[c.sgTypecode] || '';
  const fullRow = (c, extra) => {
    const region = formatRegionLabel({ sdName: c.sdName, sggName: c.sggName });
    return `<li>
      <span class="cl-name">${c.name}</span>
      <span class="cl-party">${c.jdName || '무소속'}</span>
      <span class="cl-region">${region}</span>
      <span class="cl-type">${sectionLabel(c)}</span>
      ${extra ? `<span class="cl-extra">${extra}</span>` : ''}
    </li>`;
  };
  const block = (label, items, render, cls) => items.length ? `
    <div class="cl-block ${cls}">
      <h3 class="uc-block-title">${label} <span class="uc-count">${items.length.toLocaleString()}건</span></h3>
      <ul class="cl-list">${items.map(render).join('')}</ul>
    </div>` : '';
  const html = `
    <nav class="breadcrumb"><a href="#">전국</a><span class="sep">›</span><span class="current">오늘의 변경</span></nav>
    <div class="detail-head">
      <h1 class="detail-title">오늘의 변경</h1>
      <div class="detail-inline-stats"><span>${fmt(cl.previous_date)} → ${fmt(cl.today_date)} 스냅샷 비교</span></div>
    </div>
    ${block('신규 등록', cl.full.new, c => fullRow(c), 'tied')}
    ${block('명단 이탈 (사퇴·등록무효 등)', cl.full.gone, c => fullRow(c), 'zero')}
    ${block('정당 변경', cl.full.party, c => fullRow(c, `${c.jdName_prev || '무소속'} → ${c.jdName || '무소속'}`), 'short')}
    ${block('상태 변경', cl.full.status, c => fullRow(c, `${c.status_prev || ''} → ${c.status_now || ''}`), 'short')}`;
  const app = document.getElementById('app');
  app.className = '';
  app.innerHTML = html;
  window.scrollTo({ top: 0, behavior: 'instant' });
}

// 국회의원 재·보궐 14개 선거구 전용 박스 (홈 페이지).
// 결원 의석만 다시 뽑는 케이스라 시도별 카드 옆에 묻혀버리는 것보다,
// 14개를 한 자리에 따로 펴 두는 게 정보가치 높음.
function renderMpBox() {
  const constituencies = (state.constituencies || []).filter(s => String(s.sgTypecode) === '2');
  if (!constituencies.length) return '';
  const candidates = state.data.candidates.filter(c => String(c.sgTypecode) === '2' && isActiveCandidate(c));
  // sd → sgg 그룹화 (constituencies 기준 — 후보 0명 케이스도 보여주려고)
  const grouped = constituencies.reduce((acc, s) => {
    (acc[s.sdName] ||= []).push(s);
    return acc;
  }, {});
  const sdKeys = Object.keys(grouped).sort(sidoSort);
  const sumCount = candidates.length;
  const stage = state.source === 'candidates' ? '후보' : '예비후보';

  const cards = sdKeys.flatMap(sd => grouped[sd].map(s => {
    const sgg = s.sggName;
    const list = candidates.filter(c => c.sdName === sd && c.sggName === sgg);
    const sdShort = (SIDO_TAGS[sd] || [sd])[0];
    const linked = list.length > 0;
    const href = `#${encodeURIComponent(sidoFor({ sdName: sd }))}::${encodeURIComponent(sgg)}`;
    const seat = parseInt(s.sggJungsu, 10) || 1;
    const detail = linked
      ? districtCompetitionLabelFromValues(list.filter(isActiveCandidate).length, seat)
      : `<span class="district-meta"><span>${stage} 미등록</span><span>· 정원 ${seat.toLocaleString()}석</span></span>`;
    const inner = `
      <div class="mp-card-region">
        <span class="mp-card-sido">${sdShort}</span>
        <span class="mp-card-sgg">${prettifySgg(sgg)}</span>
      </div>
      <div class="mp-card-detail">${detail}</div>`;
    return linked
      ? `<a class="mp-card" href="${href}">${inner}</a>`
      : `<span class="mp-card mp-card-empty" title="해당 선거구에 ${stage}가 아직 없어 시도 페이지에 표시되지 않습니다">${inner}</span>`;
  })).join('');

  return `
    <h2 class="section-title">국회의원 재·보궐
      <span class="section-count">${constituencies.length}개 선거구 · ${stage} ${sumCount.toLocaleString()}명 · 카드를 클릭하면 선거구로 이동</span>
    </h2>
    <div class="mp-grid">${cards}</div>`;
}

// ============ Render: 홈 ============
// (전국 지도는 정보 박스가 풍부해진 시점에 제거. 시도 카드 그리드가 진입 역할 수행.)
function renderHome() {
  const cands = state.data.candidates;
  const activeCands = cands.filter(isActiveCandidate);
  const inactiveCount = cands.length - activeCands.length;
  // 상태별 카운트
  const byStatus = cands.reduce((acc, c) => {
    const s = c.status && c.status !== '등록' ? c.status : null;
    if (s) acc[s] = (acc[s] || 0) + 1;
    return acc;
  }, {});

  // 글로벌 카운트 — 활성 후보만
  const countBy = sgType => activeCands.filter(c => String(c.sgTypecode) === sgType).length;
  const totalParties = new Set(activeCands.map(c => c.jdName)).size;

  // 시도 목록 (sdName 기준, '전국'·통합 alias 제외)
  const sidos = Array.from(new Set(cands.map(c => c.sdName).filter(s => s && s !== '전국' && s !== JOINT_SIDO))).sort(sidoSort);

  const nomActive = state.nominations
    && state.source !== 'candidates'
    && (!state.dateStr || state.dateStr < NOMINATION_CUTOFF);
  const nomSrc = nomActive
    ? `<p class="nominations-source">★ <strong>공천</strong> 배지: ${state.nominations.source}</p>`
    : '';

  const artCount = Object.values(state.articleMap || {}).reduce((n, arr) => n + arr.length, 0);
  const matchedCount = Object.keys(state.articleMap || {}).length;
  const artSrc = state.articles && matchedCount
    ? `<p class="nominations-source">📰 후보 옆 배지는 뉴탐사 <a href="${state.articles.source_url}" target="_blank" rel="noopener">공천대란</a> 코너의 관련 보도입니다. 후보 ${matchedCount.toLocaleString()}명에 보도 ${artCount.toLocaleString()}건 연결.</p>`
    : '';

  // source('preliminary' | 'candidates')에 따라 라벨 자동 전환
  const totalLabel = state.source === 'candidates' ? '총 후보자' : '총 예비후보자';
  const candidateSuffix = state.source === 'candidates' ? '후보' : '예비후보';

  // 관전 포인트 — 디테일은 별도 페이지로 위임하고, 홈에는 핵심 카드만 둔다.
  const ranking = buildCompetitionRanking();
  const top = ranking[0];
  const competition = buildCompetitionSummary();
  const regionTop = competition?.regions?.[0];
  const regionNext = competition?.regions?.slice(1, 4) || [];
  const uc = buildUncontestedList();
  const ucLabel = state.source === 'candidates' ? '무투표 당선' : '무투표 가능 후보';
  const summaryBox = (top || uc.totalCandidates || competition) ? `
    <div class="summary-row">
      ${competition ? `
        <a class="summary-card" href="#competition">
          <span class="summary-card-label">전체 평균 경쟁률</span>
          <span class="summary-card-value"><strong>${formatCompetitionRatio(competition.national.ratio)}</strong><span class="summary-card-unit">:1</span></span>
          <span class="summary-card-sub">${competition.national.candidates.toLocaleString()}명 / ${competition.national.seats.toLocaleString()}석 · ${competition.national.districts.toLocaleString()}개 선거구 전체 기준 →</span>
        </a>` : ''}
      ${regionTop ? `
        <a class="summary-card" href="#competition">
          <span class="summary-card-label">지역별 평균 경쟁률</span>
          <span class="summary-card-value"><strong>${formatCompetitionRatio(regionTop.ratio)}</strong><span class="summary-card-unit">:1</span></span>
          <span class="summary-card-sub">1위 ${sidoDisplayName(regionTop.sd)} · ${regionNext.map(r => `${sidoDisplayName(r.sd)} ${formatCompetitionRatio(r.ratio)}:1`).join(' · ')} →</span>
        </a>` : ''}
      ${top ? `
        <a class="summary-card" href="#competition">
          <span class="summary-card-label">경쟁이 가장 치열한 선거구</span>
          <span class="summary-card-value"><strong>${formatCompetitionRatio(top.ratio)}</strong><span class="summary-card-unit">:1</span></span>
          <span class="summary-card-sub">${formatRegionLabel(top)} ${top.title} · ${ranking.length.toLocaleString()}개 선거구 전체 보기 →</span>
        </a>` : ''}
      ${uc.totalCandidates ? `
        <a class="summary-card" href="#uncontested">
          <span class="summary-card-label">${ucLabel}</span>
          <span class="summary-card-value"><strong>${uc.totalCandidates.toLocaleString()}</strong>명</span>
          <span class="summary-card-sub">${uc.totalDistricts.toLocaleString()}개 선거구 · 지역구·단체장 ${uc.nonProportionalCandidates.toLocaleString()}명 · 비례 ${uc.proportionalCandidates.toLocaleString()}명 →</span>
        </a>` : ''}
    </div>` : '';

  const html = `
    <div class="stats">
      <div class="stat"><div class="stat-label">${totalLabel}</div><div class="stat-value">${activeCands.length.toLocaleString()}명</div><div class="stat-sub">${inactiveCount > 0 ? `사퇴·무효 ${inactiveCount.toLocaleString()} 제외` : `${state.data.fetched_at.slice(0,10)} 기준`}</div></div>
      ${SECTIONS.filter(s => s.card).map(s => `
        <div class="stat">
          <div class="stat-label">${s.title} ${candidateSuffix}</div>
          <div class="stat-value">${countBy(s.sgTypecode).toLocaleString()}명</div>
        </div>`).join('')}
      <div class="stat"><div class="stat-label">참여 정당</div><div class="stat-value">${totalParties}개</div><div class="stat-sub">무소속 포함</div></div>
    </div>
    ${renderAddressFinder()}
    ${summaryBox}
    ${renderTrendBox()}
    ${renderChangesBox()}
    ${renderMpBox()}
    <h2 class="section-title">시도별 후보자
      <span class="section-count">카드를 클릭하면 해당 지역 상세 · <a class="section-link" href="#candidates">정당·지역으로 필터 검색 →</a></span>
    </h2>
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
            <div class="sido-card-name">${sidoDisplayName(sido)}</div>
            <div class="sido-card-stats">
              ${stats.map(s => `<div>${s.label} <strong>${s.count}</strong></div>`).join('')}
            </div>
          </a>`;
      }).join('')}
    </div>`;

  const app = document.getElementById('app');
  app.innerHTML = html;
  app.classList.remove('loading');
}

// ============ Render: 상세 ============
function renderSidoDetail(sidoName, focusSgg) {
  sidoName = canonicalSidoName(sidoName);
  const sidoLabel = sidoDisplayName(sidoName);

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
      <a href="#">전체</a> <span class="sep">›</span> <span class="current">${sidoLabel}</span>
    </nav>
    <div class="detail-head">
      <div>
        <h2 class="detail-title">${sidoLabel}</h2>
        <button type="button" class="page-share" data-share-page data-share-title="${sidoLabel} 출마자 현황 — 6·3 지방선거">🔗 이 페이지 공유</button>
      </div>
      <div class="detail-inline-stats">
        ${stats.map(s => `<div><strong>${s.count}</strong> ${s.label}</div>`).join('')}
      </div>
    </div>
    ${SECTIONS.filter(s => s.detail).map(s => renderDetailSection(s, sidoName)).join('')}
  `;

  const app = document.getElementById('app');
  app.innerHTML = html;
  app.classList.remove('loading');

  // focus가 있으면 해당 선거구를 펼치고 스크롤. 없으면 페이지 최상단.
  if (focusSgg) {
    focusConstituency(focusSgg);
  } else {
    window.scrollTo({ top: 0, behavior: 'instant' });
  }
}

// 시도 상세 페이지에서 특정 선거구를 펼치고 스크롤. collapsible 묻힘 해소.
function focusConstituency(sggName) {
  requestAnimationFrame(() => {
    // collapsible details 안의 ed-name 텍스트로 찾는다
    const target = [...document.querySelectorAll('.electoral-district')]
      .find(d => d.querySelector('.ed-name')?.textContent === sggName);
    if (target) {
      target.open = true;
      target.classList.add('focused');
      target.scrollIntoView({ block: 'center', behavior: 'smooth' });
      // 잠깐 강조 후 제거
      setTimeout(() => target.classList.remove('focused'), 2400);
      return;
    }
    // 기초단체장 그리드 카드도 시도
    const card = [...document.querySelectorAll('.basic-grid .candidate-card')]
      .find(el => el.querySelector('.cc-name')?.textContent === sggName);
    if (card) {
      card.classList.add('focused');
      card.scrollIntoView({ block: 'center', behavior: 'smooth' });
      setTimeout(() => card.classList.remove('focused'), 2400);
      return;
    }
    // 못 찾으면 그냥 최상단
    window.scrollTo({ top: 0, behavior: 'instant' });
  });
}

// ============ Routing ============
function updateSidoNavActive(hash) {
  // 통합특별시 alias 처리: 광주광역시·전라남도 페이지 → 시도지사 진입이면 둘 다 강조 가능,
  // 다만 hash가 한쪽이므로 그 한쪽만 강조.
  const target = hash.includes('::') ? hash.split('::')[0] : hash;
  document.querySelectorAll('.sido-chip').forEach(el => {
    const href = decodeURIComponent(el.getAttribute('href').slice(1));
    el.classList.toggle('active', href === target && target !== '');
  });
}

function siteNavSectionForHash(hash) {
  if (hash === 'address') return 'address';
  if (hash === 'candidates' || hash.startsWith('cand/')) return 'candidates';
  if (hash === 'disclosure/military' || hash.startsWith('trend/military/')) return 'military';
  if (hash === 'trend' || hash.startsWith('trend/')) return 'trend';
  if (hash === 'disclosure/criminal' || hash.startsWith('criminal/')) return 'criminal';
  if (hash === 'disclosure/tax' || hash === 'tax-arrears' || hash.startsWith('tax-arrears/')) return 'tax';
  if (hash.startsWith('disclosure/')) return 'trend';
  if (hash === 'changes') return 'changes';
  if (hash === 'history') return 'history';
  if (hash === 'schedule') return 'schedule';
  return '';
}

function updateSiteNavActive(hash) {
  const section = siteNavSectionForHash(hash);
  document.querySelectorAll('.site-nav-link').forEach(el => {
    el.classList.toggle('active', el.dataset.siteSection === section && section !== '');
  });
}

let routeRunId = 0;

function renderRouteLoading(label = '데이터') {
  const app = document.getElementById('app');
  app.className = '';
  app.innerHTML = `<div class="loading">${escapeHtml(label)} 불러오는 중…</div>`;
}

async function renderAfterData(label, loaders, renderFn, runId) {
  renderRouteLoading(label);
  await Promise.all(loaders.map(loader => loader()));
  if (runId !== routeRunId) return;
  renderFn();
}

async function route() {
  const runId = ++routeRunId;
  const hash = decodeURIComponent(location.hash.slice(1));
  if (!hash.startsWith('cand/')) closeCandidateModal();
  updateSidoNavActive(hash);
  updateSiteNavActive(hash);
  if (!hash) return renderHome();
  if (hash === 'address') {
    renderHome();
    requestAnimationFrame(() => {
      const finder = document.getElementById('address-finder');
      finder?.scrollIntoView({ block: 'start', behavior: 'smooth' });
      finder?.querySelector('input')?.focus();
      ensureAddressIndex();
    });
    return;
  }
  if (hash === 'competition') return renderCompetitionFull();
  if (hash === 'changes') return renderChangesFull();
  if (hash === 'trend') return renderAfterData('후보자 공개정보', [ensureCandidateDetails], renderTrendFull, runId);
  if (hash.startsWith('disclosure/')) {
    const kind = hash.slice('disclosure/'.length);
    const loaders = kind === 'criminal' ? [ensureCandidateDetails, ensureCriminalOcr] : [ensureCandidateDetails];
    return renderAfterData('후보자 공개정보', loaders, () => renderDisclosureFocusFull(kind), runId);
  }
  if (hash === 'tax-arrears') return renderAfterData('체납 공개정보', [ensureCandidateDetails], () => renderTaxArrearsFull('5y'), runId);
  if (hash.startsWith('tax-arrears/')) return renderAfterData('체납 공개정보', [ensureCandidateDetails], () => renderTaxArrearsFull(hash.slice('tax-arrears/'.length)), runId);
  if (hash.startsWith('criminal/')) return renderAfterData('전과 원문 분류', [ensureCandidateDetails, ensureCriminalOcr], () => renderCriminalCategoryFull(hash.slice('criminal/'.length)), runId);
  if (hash.startsWith('trend/')) {
    const parts = hash.split('/');
    if (['assets', 'criminal', 'tax5y', 'taxCurrent'].includes(parts[1])) {
      if (parts.length >= 4) {
        return renderAfterData('후보자 공개정보', [ensureCandidateDetails], () => renderDisclosureRegionFocusFull(parts[1], parts[2], parts.slice(3).join('/')), runId);
      }
      return renderAfterData('후보자 공개정보', [ensureCandidateDetails], () => renderDisclosureRegionFocusFull(parts[1], parts[2]), runId);
    }
    if (parts[1] === 'military') {
      if (parts.length >= 4) return renderAfterData('병역 공개정보', [ensureCandidateDetails], () => renderTrendMilitaryLocalFull(parts[2], parts.slice(3).join('/')), runId);
      return renderAfterData('병역 공개정보', [ensureCandidateDetails], () => renderTrendMilitaryRegionFull(parts[2]), runId);
    }
    if (parts.length >= 3) return renderAfterData('후보자 공개정보', [ensureCandidateDetails], () => renderTrendLocalFull(parts[1], parts.slice(2).join('/')), runId);
    return renderAfterData('후보자 공개정보', [ensureCandidateDetails], () => renderTrendRegionFull(parts[1]), runId);
  }
  if (hash === 'history') return renderAfterData('지난 선거 개표 결과', [ensureHistoryCounting], renderHistoryFull, runId);
  if (hash === 'schedule') return renderScheduleFull();
  if (hash === 'candidates') return renderCandidatesFull();
  if (hash.startsWith('cand/')) {
    // 후보 영구 링크: 홈을 배경에 그리고 모달 자동 오픈
    renderHome();
    openCandidateModal(hash.slice('cand/'.length));
    return;
  }
  if (hash === 'uncontested') return renderUncontestedFull(null);
  if (hash.startsWith('uncontested/')) {
    return renderUncontestedFull(hash.slice('uncontested/'.length));
  }
  // "{시도명}" 또는 "{시도명}::{선거구명}" (구분자 :: — 시도명에 ':' 포함되지 않음을 가정)
  const sepIdx = hash.indexOf('::');
  if (sepIdx > 0) {
    return renderSidoDetail(hash.slice(0, sepIdx), hash.slice(sepIdx + 2));
  }
  return renderSidoDetail(hash);
}

// ============ 무투표 당선 선거구 (공용 헬퍼) ============
function uncontestedStageNote() {
  return state.source === 'candidates'
    ? '후보 등록 기준 — 사실상 확정'
    : '예비후보 등록 기준 — 5/14~15 본후보 등록 시 변동 가능';
}
function uncontestedRow(r) {
  // 후보 0명은 시도 페이지에 해당 선거구가 그려지지 않음 → 링크 비활성화.
  // 후보가 1명 이상이면 시도 상세에서 자동 펼침·스크롤되도록 focus 해시 부여.
  const label = formatRegionLabel(r);
  const target = r.sgg || r.sd;
  const linked = r.count > 0;
  const hash = linked
    ? `#${encodeURIComponent(sidoFor(r))}::${encodeURIComponent(target)}`
    : null;
  const regionEl = linked
    ? `<a class="uc-region" href="${hash}">${label}</a>`
    : `<span class="uc-region uc-region-dead" title="해당 선거구에 후보가 없어 별도 페이지에 표시되지 않습니다">${label}</span>`;
  return `
    <li>
      ${regionEl}
      <span class="uc-type">${r.title}</span>
      <span class="uc-detail">${r.isSinglePartyPr ? `${r.count}명` : `${r.count}/${r.seat}`}</span>
    </li>`;
}
function uncontestedBlock(items, totalCount, label, cls) {
  if (totalCount === 0) return '';
  const shown = items;
  const more = totalCount - shown.length;
  return `
    <div class="uc-block ${cls}">
      <h3 class="uc-block-title">${label} <span class="uc-count">${totalCount.toLocaleString()}곳</span></h3>
      <ul class="uc-list">${shown.map(uncontestedRow).join('')}</ul>
      ${more > 0 ? `<p class="uc-more"><a href="#uncontested/${cls}">+${more.toLocaleString()}곳 더 보기 →</a></p>` : ''}
    </div>`;
}

// 무투표 당선 선거구 전체 페이지 (#uncontested 또는 #uncontested/{cat})
function renderUncontestedFull(category) {
  const uc = buildUncontestedList();
  const cats = [
    { key: 'tied',          label: '후보 수와 정원이 같은 선거구',              items: uc.tied,          cls: 'tied' },
    { key: 'singlePartyPr', label: '비례대표 단일 정당 명부',                   items: uc.singlePartyPr, cls: 'singlePartyPr' },
    { key: 'short',         label: '정원 일부 미달 (1명 이상·후보 수 < 정원)', items: uc.short,         cls: 'short' },
    { key: 'zero',          label: '후보 0명',                                  items: uc.zero,          cls: 'zero' },
  ];
  const filtered = category ? cats.filter(c => c.key === category) : cats;
  const titleSuffix = category
    ? ` · ${cats.find(c => c.key === category)?.label || category}`
    : '';
  const html = `
    <nav class="breadcrumb">
      <a href="#">전국</a>
      <span class="sep">›</span>
      <span class="current">무투표 당선 선거구${titleSuffix}</span>
    </nav>
    <div class="detail-head">
      <h1 class="detail-title">무투표 당선 선거구</h1>
      <div class="detail-inline-stats">
        <span>${uc.totalCandidates.toLocaleString()}명</span>
        <span>${uc.totalDistricts.toLocaleString()}개 선거구</span>
        <span>${uncontestedStageNote()}</span>
      </div>
    </div>
    ${filtered.map(c =>
      `<div class="uc-block ${c.cls}">
        <h3 class="uc-block-title">${c.label} <span class="uc-count">${c.items.length.toLocaleString()}곳</span></h3>
        ${c.items.length === 0
          ? '<p class="uc-more">해당 사항 없음.</p>'
          : `<ul class="uc-list">${c.items.map(uncontestedRow).join('')}</ul>`}
      </div>`
    ).join('')}
  `;
  const app = document.getElementById('app');
  app.className = '';
  app.innerHTML = html;
  window.scrollTo({ top: 0, behavior: 'instant' });
}

// 경쟁률 전체 페이지 (#competition)
function renderCompetitionFull() {
  const ranking = buildCompetitionRanking();
  const summary = buildCompetitionSummary();
  const regionRows = summary?.regions || [];
  const maxRegionRatio = Math.max(...regionRows.map(r => r.ratio), 1);
  const regionBars = regionRows.map(r =>
    metricBar(sidoDisplayName(r.sd), r.ratio, maxRegionRatio, 'var(--accent)', `${formatCompetitionRatio(r.ratio)}:1`, `${r.candidates.toLocaleString()}명 / ${r.seats.toLocaleString()}석`)
  ).join('');
  const rows = ranking.map((r, i) => {
    const target = r.sgg || r.sd;
    const href = `#${encodeURIComponent(sidoFor(r))}::${encodeURIComponent(target)}`;
    return `
      <li>
        <span class="comp-rank">${i + 1}</span>
        <a class="comp-region" href="${href}">${formatRegionLabel(r)}</a>
        <span class="comp-type">${r.title}</span>
        <span class="comp-ratio"><strong>${formatCompetitionRatio(r.ratio)}</strong>:1</span>
        <span class="comp-detail">${r.count}명 / ${r.seat}석</span>
      </li>`;
  }).join('');
  const html = `
    <nav class="breadcrumb">
      <a href="#">전국</a>
      <span class="sep">›</span>
      <span class="current">경쟁이 치열한 선거구</span>
    </nav>
    <div class="detail-head">
      <h1 class="detail-title">경쟁이 치열한 선거구</h1>
      <div class="detail-inline-stats">
        <span>의석 1자리당 후보 수 기준 · ${ranking.length.toLocaleString()}개 선거구</span>
      </div>
    </div>
    ${summary ? `
      <section class="trend-section">
        <h3 class="trend-section-title">전체·지역별 경쟁률</h3>
        <div class="competition-overview">
          <div class="disclosure-card">
            <span class="disclosure-label">전체 평균</span>
            <strong>${formatCompetitionRatio(summary.national.ratio)}:1</strong>
            <small>${summary.national.candidates.toLocaleString()}명 / ${summary.national.seats.toLocaleString()}석 · ${summary.national.districts.toLocaleString()}개 선거구</small>
          </div>
          <div class="competition-region-bars">
            <h4 class="metric-title">지역별 평균 경쟁률</h4>
            <div class="bar-list">${regionBars}</div>
          </div>
        </div>
      </section>` : ''}
    <ol class="competition-list">${rows}</ol>`;
  const app = document.getElementById('app');
  app.className = '';
  app.innerHTML = html;
  window.scrollTo({ top: 0, behavior: 'instant' });
}

// ============ 후보 전체 목록 + 다중 필터 (#candidates) ============
const candidatesFilter = { sd: new Set(), sg: new Set(), jd: new Set(), st: new Set() };

function buildFacets() {
  const cs = state.data.candidates;
  // 통합특별시는 API 보정용 가상 시도 — 광주·전남으로 흡수해 17개로 일관성 유지.
  const sds = Array.from(new Set(cs.map(c => c.sdName)
    .filter(s => s && s !== '전국' && s !== JOINT_SIDO))).sort(sidoSort);
  const sgs = SECTIONS.map(s => ({ code: s.sgTypecode, title: s.title }));
  // 정당: 등장 빈도 내림차순
  const partyCount = {};
  cs.forEach(c => { const j = c.jdName || '무소속'; partyCount[j] = (partyCount[j] || 0) + 1; });
  const jds = Object.entries(partyCount).sort((a, b) => b[1] - a[1]).map(([j, n]) => ({ name: j, count: n }));
  // 상태
  const statusCount = {};
  cs.forEach(c => { const s = c.status || '등록'; statusCount[s] = (statusCount[s] || 0) + 1; });
  const sts = Object.entries(statusCount).sort((a, b) => b[1] - a[1]).map(([s, n]) => ({ name: s, count: n }));
  return { sds, sgs, jds, sts };
}

function applyCandidatesFilter() {
  // 광주·전남 선택 시 통합특별시(시도지사) 후보도 포함 — 사용자 입장에선 자기 시도
  const sdMatch = candidatesFilter.sd.size
    ? new Set([
        ...candidatesFilter.sd,
        ...(candidatesFilter.sd.has('광주광역시') || candidatesFilter.sd.has('전라남도')
            ? [JOINT_SIDO] : []),
      ])
    : null;
  return state.data.candidates.filter(c => {
    if (sdMatch && !sdMatch.has(c.sdName)) return false;
    if (candidatesFilter.sg.size && !candidatesFilter.sg.has(String(c.sgTypecode))) return false;
    if (candidatesFilter.jd.size && !candidatesFilter.jd.has(c.jdName || '무소속')) return false;
    if (candidatesFilter.st.size && !candidatesFilter.st.has(c.status || '등록')) return false;
    return true;
  });
}

function renderCandidatesFull() {
  const facets = buildFacets();
  const titleMap = Object.fromEntries(SECTIONS.map(s => [s.sgTypecode, s.title]));

  const chip = (kind, key, label, count, active) =>
    `<button type="button" class="filter-chip${active ? ' active' : ''}" data-kind="${kind}" data-key="${encodeURIComponent(key)}">${label}<small>${count.toLocaleString()}</small></button>`;

  const sdChips = facets.sds.map(sd => {
    // 광주·전남 칩은 통합특별시 단일 선거 후보까지 카운트에 포함
    const extra = (sd === '광주광역시' || sd === '전라남도') ? JOINT_SIDO : null;
    const n = state.data.candidates.filter(c => c.sdName === sd || c.sdName === extra).length;
    return chip('sd', sd, sidoDisplayName(sd), n, candidatesFilter.sd.has(sd));
  }).join('');
  const sgChips = facets.sgs.map(s => {
    const n = state.data.candidates.filter(c => String(c.sgTypecode) === s.code).length;
    return chip('sg', s.code, s.title, n, candidatesFilter.sg.has(s.code));
  }).join('');
  const jdChips = facets.jds.slice(0, 20).map(j =>
    chip('jd', j.name, j.name, j.count, candidatesFilter.jd.has(j.name))
  ).join('');
  const stChips = facets.sts.map(s =>
    chip('st', s.name, s.name, s.count, candidatesFilter.st.has(s.name))
  ).join('');

  const filtered = applyCandidatesFilter();
  const total = state.data.candidates.length;
  const activeCount = [
    ...candidatesFilter.sd, ...candidatesFilter.sg, ...candidatesFilter.jd, ...candidatesFilter.st,
  ].length;

  const rowsHtml = filtered.slice(0, 300).map(c => {
    const region = formatRegionLabel(c);
    const sgTitle = titleMap[c.sgTypecode] || '';
    return `
      <li class="cand-row">
        <span class="cand-color" style="background:${partyColor(c.jdName)}"></span>
        <button type="button" class="cand-name candidate-detail-trigger" data-huboid="${c.huboid}">${c.name}</button>
        <span class="cand-party">${c.jdName || '무소속'}</span>
        <span class="cand-region">${region}</span>
        <span class="cand-type">${sgTitle}</span>
      </li>`;
  }).join('');
  const overflow = filtered.length > 300
    ? `<p class="filter-overflow">+${(filtered.length - 300).toLocaleString()}명 더. 필터를 더 좁히면 모두 표시됩니다.</p>`
    : '';

  const html = `
    <nav class="breadcrumb"><a href="#">전국</a><span class="sep">›</span><span class="current">후보 찾기</span></nav>
    <div class="detail-head">
      <h1 class="detail-title">후보 찾기</h1>
      <div class="detail-inline-stats">
        <span><strong>${filtered.length.toLocaleString()}</strong> / ${total.toLocaleString()}명</span>
        ${activeCount ? `<button type="button" class="filter-reset" data-filter-reset>필터 초기화 (${activeCount})</button>` : ''}
      </div>
    </div>
    <p class="page-intro">조건을 클릭해 후보를 좁혀보세요. 같은 그룹 안에서는 여러 개 선택 가능, 그룹 사이는 모두 만족해야 결과에 포함됩니다.</p>
    <section class="filter-section">
      <div class="filter-group filter-group-wide">
        <h3 class="filter-group-title">시도 <small>${facets.sds.length}곳</small></h3>
        <div class="filter-chips">${sdChips}</div>
      </div>
      <div class="filter-group">
        <h3 class="filter-group-title">선거 종류</h3>
        <div class="filter-chips">${sgChips}</div>
      </div>
      <div class="filter-group filter-group-wide">
        <h3 class="filter-group-title">정당 <small>등장 빈도 상위 20</small></h3>
        <div class="filter-chips">${jdChips}</div>
      </div>
      <div class="filter-group">
        <h3 class="filter-group-title">등록 상태</h3>
        <div class="filter-chips">${stChips}</div>
      </div>
    </section>
    <ul class="cand-list">${rowsHtml || '<li class="cand-empty">조건에 맞는 후보가 없습니다.</li>'}</ul>
    ${overflow}`;
  const app = document.getElementById('app');
  app.className = '';
  app.innerHTML = html;
  window.scrollTo({ top: 0, behavior: 'instant' });
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
    const region = formatRegionLabel(c).replace(' ', ' · ');
    // 기초단체장(그리드)·시도의원·기초의원(collapsible)은 페이지에 묻혀 있으므로
    // focus 해시로 자동 펼침·스크롤·강조
    const needsFocus = ['4', '5', '6'].includes(String(c.sgTypecode))
      && c.sggName && c.sggName !== c.sdName;
    const href = needsFocus
      ? `#${encodeURIComponent(sidoFor(c))}::${encodeURIComponent(c.sggName)}`
      : `#${encodeURIComponent(sidoFor(c))}`;
    return `
      <a class="sr-item" href="${href}">
        <span class="sr-name">${c.name}</span>
        <span class="sr-meta">${c.jdName || '무소속'} · ${titleMap[c.sgTypecode] || ''} · ${region}</span>
      </a>`;
  }).join('');
  const more = matches.length > 30
    ? `<div class="sr-more">+${(matches.length - 30).toLocaleString()}건 더 (검색어를 더 정확히 입력)</div>`
    : '';
  const filterLink = '<a class="sr-filter-link" href="#candidates">정당·지역·선거로 필터 검색 →</a>';
  results.innerHTML = items + more + filterLink;
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
  // 키보드 네비게이션: ↑↓로 이동, Enter로 이동, ESC로 닫기
  input.addEventListener('keydown', e => {
    if (e.key === 'Escape') {
      input.value = '';
      results.hidden = true;
      input.blur();
      return;
    }
    if (results.hidden) return;
    const items = [...results.querySelectorAll('.sr-item')];
    if (!items.length) return;
    const current = items.findIndex(el => el.classList.contains('selected'));
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      const next = current < 0 ? 0 : Math.min(current + 1, items.length - 1);
      items.forEach((el, i) => el.classList.toggle('selected', i === next));
      items[next].scrollIntoView({ block: 'nearest' });
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      const prev = current <= 0 ? items.length - 1 : current - 1;
      items.forEach((el, i) => el.classList.toggle('selected', i === prev));
      items[prev].scrollIntoView({ block: 'nearest' });
    } else if (e.key === 'Enter') {
      const sel = items.find(el => el.classList.contains('selected')) || items[0];
      if (sel?.href) {
        e.preventDefault();
        location.href = sel.href;
        results.hidden = true;
        input.value = '';
      }
    }
  });
}

// ============ Bootstrap ============
async function main() {
  calculateDDay();
  renderScheduleBar();
  try {
    const [{ data, dateStr, source }, parties, nominations, articles, constituencies, changelog, timeseries, history, historyTurnout] = await Promise.all([
      loadLatestSnapshot(), loadParties(), loadNominations(), loadArticles(), loadConstituencies(),
      loadChangelog(), loadTimeseries(), loadHistory(), loadHistoryTurnout(),
    ]);
    state.constituencies = constituencies;
    state.jointConstituencySdMap = buildJointConstituencySdMap(constituencies);
    // 로딩 시점에 단 한 번 dedup + 지역 보정. 이후 모든 화면은 깨끗한 데이터를 본다.
    const candidates = normalizeCandidateRegions(dedupeByHuboid(data.candidates), constituencies);
    state.data = { ...data, candidates };
    state.uncontestedCandidateSet = null;
    state.parties = parties;
    state.nominations = nominations;
    state.dateStr = dateStr;
    state.source = source;
    state.articles = articles;
    state.articleMap = buildArticleMap(articles?.articles, state.data.candidates);
    state.changelog = changelog;
    state.timeseries = timeseries;
    state.history = history;
    state.historyTurnout = historyTurnout;
    const sourceLabel = SOURCE_LABEL[source] || source;
    document.getElementById('last-updated').textContent =
      `${dateStr.slice(0,4)}.${dateStr.slice(4,6)}.${dateStr.slice(6,8)} · ${sourceLabel}`;
    // 클릭 위임: 보도 배지 / collapsible 일괄 토글 / 후보 상세 모달 / 모달 닫기
    document.addEventListener('click', e => {
      if (e.target.closest('[data-modal-close]')) {
        closeCandidateModal();
        return;
      }
      const shareCand = e.target.closest('[data-share-cand]');
      if (shareCand) {
        e.preventDefault();
        const huboid = shareCand.dataset.shareCand;
        const title = `${shareCand.dataset.shareTitle} — 6·3 선거 출마자 2026`;
        shareLink(title, candidateShareUrl(huboid));
        return;
      }
      const sharePage = e.target.closest('[data-share-page]');
      if (sharePage) {
        e.preventDefault();
        const title = `${sharePage.dataset.shareTitle}`;
        shareLink(title, location.href);
        return;
      }
      const detail = e.target.closest('.candidate-detail-trigger');
      if (detail) {
        e.preventDefault();
        openCandidateModal(detail.dataset.huboid);
        return;
      }
      const addressSuggestion = e.target.closest('.address-suggestion');
      if (addressSuggestion) {
        e.preventDefault();
        chooseAddressSuggestion(addressSuggestion.dataset.addressFull);
        return;
      }
      const articleBtn = e.target.closest('.article-toggle');
      if (articleBtn) {
        e.preventDefault();
        const panel = document.getElementById(articleBtn.dataset.target);
        if (panel) {
          panel.hidden = !panel.hidden;
          articleBtn.classList.toggle('open', !panel.hidden);
        }
        return;
      }
      const chip = e.target.closest('.filter-chip');
      if (chip) {
        const kind = chip.dataset.kind;
        const key = decodeURIComponent(chip.dataset.key);
        const set = candidatesFilter[kind];
        if (set) {
          if (set.has(key)) set.delete(key); else set.add(key);
          renderCandidatesFull();
        }
        return;
      }
      if (e.target.closest('[data-filter-reset]')) {
        Object.values(candidatesFilter).forEach(s => s.clear());
        renderCandidatesFull();
        return;
      }
      const expandBtn = e.target.closest('.expand-toggle');
      if (expandBtn) {
        const grid = document.getElementById(expandBtn.dataset.target);
        if (!grid) return;
        const opening = expandBtn.dataset.open !== 'true';
        grid.querySelectorAll('details').forEach(d => { d.open = opening; });
        expandBtn.dataset.open = opening ? 'true' : 'false';
        expandBtn.textContent = opening ? '모두 접기' : '모두 펼치기';
        return;
      }
      const battleFilter = e.target.closest('[data-history-battle-filter]');
      if (battleFilter) {
        e.preventDefault();
        updateHistoryBattlefieldFilter(battleFilter.dataset.historyBattleFilter);
      }
    });
    document.addEventListener('submit', async e => {
      const form = e.target.closest('[data-address-form]');
      if (!form) return;
      e.preventDefault();
      const input = form.querySelector('[name="address"]');
      renderAddressLoading();
      await ensureAddressIndex();
      renderAddressLookup(input?.value || '');
    });
    document.addEventListener('input', async e => {
      if (e.target.matches('#address-input')) {
        const query = e.target.value;
        if (!Array.isArray(state.addressIndex) && compactAddressText(query).length >= 2) renderAddressLoading();
        await ensureAddressIndex();
        const input = document.getElementById('address-input');
        if (input?.value === query) renderAddressSuggestions(query);
      }
    });
    document.addEventListener('focusin', e => {
      if (e.target.matches('#address-input')) ensureAddressIndex();
    });
    // ESC로 모달 닫기
    document.addEventListener('keydown', e => {
      if (e.key === 'Escape' && !document.getElementById('modal-root').hidden) {
        closeCandidateModal();
      }
    });
    initSearch();
    window.addEventListener('hashchange', route);
    route();
  } catch (e) {
    console.error(e);
    const app = document.getElementById('app');
    app.classList.remove('loading');
    app.innerHTML = `
      <div class="error-banner">
        <strong>데이터를 불러오지 못했습니다.</strong>
        잠시 후 새로고침해 보시거나, 문제가 계속되면
        <a href="mailto:news@newtamsa.org">news@newtamsa.org</a>로 알려 주세요.
        <br><small style="color:var(--ink-sub)">기술 메시지: ${e.message}</small>
      </div>`;
  }
}

main();
