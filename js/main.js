const ELECTION_DATE = '2026-06-03T00:00:00';

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

const state = { data: null, parties: {}, nominations: null, dateStr: null, source: null, articles: null, articleMap: {}, constituencies: null, jointConstituencySdMap: {}, changelog: null, timeseries: null, history: null, historyTurnout: null };
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
const loadConstituencies = () => safeJson('data/constituencies.json', null);
const loadChangelog = () => safeJson('data/changelog.json', null);
const loadTimeseries = () => safeJson('data/timeseries.json', null);
const loadHistory = () => safeJson('data/history.json', null);
const loadHistoryTurnout = () => safeJson('data/history_turnout.json', null);

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
  if (!sgg || sgg === sd) return sd || sgg;
  const sdShort = (SIDO_TAGS[sd] || [sd])[0] || sd;
  // 통합특별시 같은 특수 케이스는 합쳐진 이름 그대로 표시
  if (sd === JOINT_SIDO || sgg === JOINT_SIDO) return sgg || sd;
  return `${sdShort} ${sgg}`;
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
    if (!isActiveCandidate(c)) continue;
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
// 일부 미달(1명 이상·정원 미만)·0명도 함께 수집 — 사용자는 박스 안에서 카테고리별로 본다.
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
  return `
    <div class="candidate${confirmed ? ' confirmed' : ''}${statusInfo ? ' candidate-inactive' : ''}">
      <div class="candidate-color" style="background:${partyColor(c.jdName)}"></div>
      <button type="button" class="candidate-name candidate-detail-trigger" data-huboid="${c.huboid}" title="${c.name} 상세 정보">${c.name}${statusBadge}${confirmed ? '<span class="confirmed-badge">공천</span>' : ''}</button>
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

function openCandidateModal(huboid) {
  const c = state.data.candidates.find(x => x.huboid === huboid);
  if (!c) return;
  const root = document.getElementById('modal-root');
  if (!root) return;

  const confirmed = isConfirmed(c);
  const articles = state.articleMap?.[c.huboid] || [];
  const titleMap = Object.fromEntries(SECTIONS.map(s => [s.sgTypecode, s.title]));
  const sectionTitle = titleMap[c.sgTypecode] || '';
  const region = formatRegionLabel(c);
  const birth = formatBirthday(c.birthday);
  const regdate = formatRegdate(c.regdate);

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
  ].filter(([, v]) => v);

  const fieldsHtml = fields.map(([k, v]) =>
    `<div class="modal-field"><dt>${k}</dt><dd>${v}</dd></div>`
  ).join('');

  const articlesHtml = articles.length ? `
    <section class="modal-section">
      <h3 class="modal-section-title">관련 보도 <span class="modal-section-sub">${articles.length}건 · 뉴탐사 공천대란 매칭</span></h3>
      <ul class="modal-articles">${articleListHtml(articles)}</ul>
    </section>` : '';

  const tipUrl = tipoffUrl(c);

  root.innerHTML = `
    <div class="modal-backdrop" data-modal-close></div>
    <div class="modal-dialog" role="dialog" aria-modal="true" aria-labelledby="modal-name">
      <button type="button" class="modal-close" data-modal-close aria-label="닫기">×</button>
      <header class="modal-head" style="border-left-color:${partyColor(c.jdName)}">
        <p class="modal-region">${region} · ${sectionTitle}</p>
        <h2 id="modal-name" class="modal-name">${c.name}
          ${confirmed ? '<span class="confirmed-badge">공천</span>' : ''}
        </h2>
        <p class="modal-subline">${c.jdName || '무소속'}${c.status ? ` · ${c.status}` : ''}</p>
      </header>
      <dl class="modal-fields">${fieldsHtml}</dl>
      ${articlesHtml}
      <footer class="modal-foot">
        <div class="modal-actions">
          <a class="modal-tip" href="${tipUrl}" target="_blank" rel="noopener">📮 이 후보 제보하기</a>
          <button type="button" class="modal-share" data-share-cand="${c.huboid}" data-share-title="${c.name} (${c.jdName || '무소속'}) — ${region}">🔗 링크 공유</button>
        </div>
        <p class="modal-source">기준: 중앙선관위 OpenAPI · ${state.dateStr ? `${state.dateStr.slice(0,4)}.${state.dateStr.slice(4,6)}.${state.dateStr.slice(6,8)} ${SOURCE_LABEL[state.source] || state.source}` : ''}</p>
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
    const gridId = `cg-${section.id}`;
    return `
      <h3 class="section-title">${section.title}
        <span class="section-count">${candidates.length.toLocaleString()}명 · ${keys.length}개 선거구</span>
        <span class="section-toolbar">
          <button type="button" class="expand-toggle" data-target="${gridId}" data-open="false">모두 펼치기</button>
        </span>
      </h3>
      <div id="${gridId}" class="collapsible-grid">
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
    return `<tr><th>${sd}</th>${cells}${deltaCell}</tr>`;
  }).join('');

  return `
    <section class="trend-section">
      <h3 class="trend-section-title">시도별 투표율 추이 <small>3~8회 · 선관위 OpenAPI</small></h3>
      ${groupChart}
      <ul class="trend-legend">${groupLegend}</ul>
      <p class="forecast-context" style="margin-top:1rem">
        <strong>주목할 패턴</strong>: 호남(광주·전북·전남)은 3~7회 동안 일관되게 최고 투표율을 유지했지만, <strong>8회(2022)에 영남·수도권보다 낮아지는 역전</strong>이 발생. 특히 광주는 7회 59.2% → 8회 37.7%로 21.5%p 급락. 6/3 9회 결과가 다시 호남 상승으로 돌아갈지가 관전 포인트.
      </p>
    </section>

    <section class="trend-section">
      <h3 class="trend-section-title">시도별 회차 표</h3>
      <div class="table-scroll">
        <table class="hist-table hist-table-sido">
          <thead>
            <tr><th>시도</th>${rounds.map(r => `<th>${r.round}회</th>`).join('')}<th>7→8 변화</th></tr>
          </thead>
          <tbody>${tableRows}</tbody>
        </table>
      </div>
      <p class="trend-meta">8회 대비 7회 변화량 · "—" 표시는 데이터 미제공(2회 미참여 시도 등)</p>
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
  const h = state.history;
  if (!h?.elections?.length) {
    app.innerHTML = `
      <nav class="breadcrumb"><a href="#">전국</a><span class="sep">›</span><span class="current">과거 회차</span></nav>
      <div class="detail-head"><h1 class="detail-title">과거 지방선거 비교</h1></div>
      <p class="absence-note">과거 데이터가 아직 없습니다.</p>`;
    return;
  }

  const elections = h.elections;
  const turnouts = elections.map(e => e.turnout);
  const avg = turnouts.reduce((a, b) => a + b, 0) / turnouts.length;
  const maxT = Math.max(...turnouts);
  const minT = Math.min(...turnouts);

  // 회차별 막대 그래프
  const w = 800, h_ = 180, pad = 30;
  const stepX = (w - pad * 2) / (elections.length - 1);
  const barWidth = Math.min(40, stepX * 0.55);
  const yScale = v => h_ - pad - ((v - 40) / 35) * (h_ - pad * 2);  // 40~75% 범위
  const bars = elections.map((e, i) => {
    const x = pad + i * stepX;
    const y = yScale(e.turnout);
    return `
      <rect x="${(x - barWidth/2).toFixed(1)}" y="${y.toFixed(1)}"
            width="${barWidth.toFixed(1)}" height="${(h_ - pad - y).toFixed(1)}"
            fill="#c41e3a" opacity="0.85"/>
      <text x="${x.toFixed(1)}" y="${(y - 6).toFixed(1)}" font-size="11" fill="#1a1a1a" text-anchor="middle" font-weight="700">${e.turnout}%</text>
      <text x="${x.toFixed(1)}" y="${h_ - 10}" font-size="10" fill="#888" text-anchor="middle">${e.round}회</text>
      <text x="${x.toFixed(1)}" y="${h_ - 22}" font-size="9" fill="#aaa" text-anchor="middle">${e.year}</text>
    `;
  }).join('');
  const avgLine = `
    <line x1="${pad}" y1="${yScale(avg)}" x2="${w - pad}" y2="${yScale(avg)}"
          stroke="#888" stroke-width="1" stroke-dasharray="4 3"/>
    <text x="${w - pad + 4}" y="${yScale(avg) + 4}" font-size="9" fill="#888">평균 ${avg.toFixed(1)}%</text>`;
  const chartSvg = `
    <svg viewBox="0 0 ${w} ${h_}" class="trend-chart" aria-label="역대 투표율">
      <line x1="${pad}" y1="${h_ - pad}" x2="${w - pad}" y2="${h_ - pad}" stroke="#d8d2c8"/>
      ${bars}${avgLine}
    </svg>`;

  // 회차별 표
  const tableRows = elections.map(e => {
    const winners = historyWinnersSummary(e.winners);
    return `
      <tr>
        <td class="hist-round">${e.round}회</td>
        <td class="hist-year">${e.year}</td>
        <td class="hist-turn"><strong>${e.turnout}%</strong>${e.early_turnout ? `<small>사전 ${e.early_turnout}%</small>` : ''}</td>
        <td class="hist-seats">${winners}</td>
        <td class="hist-context">${e.context}</td>
      </tr>`;
  }).join('');

  // 슬라이더 매칭 영역 (초기값: 8회 50.9 + 평균의 평균쯤)
  const initial = 55;
  const initialMatch = findClosestPastElection(initial);
  const initWinners = historyWinnersSummary(initialMatch.match.winners);

  app.innerHTML = `
    <nav class="breadcrumb"><a href="#">전국</a><span class="sep">›</span><span class="current">과거 회차 비교</span></nav>
    <div class="detail-head">
      <h1 class="detail-title">과거 지방선거 비교</h1>
      <div class="detail-inline-stats">
        <span>1~8회 · 평균 투표율 ${avg.toFixed(1)}%</span>
      </div>
    </div>
    <p class="page-intro">역대 8번의 전국동시지방선거 투표율과 광역단체장 결과입니다. <strong>아래는 단정적 예측이 아닌 과거 패턴 비교</strong>입니다 — 6/3 투표율 시나리오를 가정해 가장 비슷한 과거 회차를 찾아볼 수 있습니다.</p>

    <section class="trend-section">
      <h3 class="trend-section-title">회차별 투표율</h3>
      ${chartSvg}
    </section>

    <section class="trend-section">
      <h3 class="trend-section-title">6·3 투표율 시나리오 매칭</h3>
      <div class="forecast">
        <label class="forecast-label" for="forecast-turnout">가정 투표율</label>
        <div class="forecast-input-row">
          <input id="forecast-turnout" type="range" min="40" max="75" step="0.1" value="${initial}">
          <output id="forecast-output" class="forecast-output">${initial.toFixed(1)}%</output>
        </div>
        <div id="forecast-match" class="forecast-match">
          <p>가장 가까운 과거 회차: <strong>${initialMatch.match.round}회 (${initialMatch.match.year}, ${initialMatch.match.turnout}%)</strong> · 차이 ${initialMatch.diff.toFixed(1)}%p</p>
          <p class="forecast-context">${initialMatch.match.context}</p>
          <p class="forecast-winners">광역단체장 결과: <strong>${initWinners}</strong></p>
        </div>
        <p class="forecast-caveat">※ 단정적 예측이 아닙니다. 후보·시기·외부 변수가 모두 달라 참고용 비교입니다.</p>
      </div>
    </section>

    ${renderTurnoutBySidoSection()}

    <section class="trend-section">
      <h3 class="trend-section-title">회차별 상세</h3>
      <table class="hist-table">
        <thead>
          <tr><th>회차</th><th>연도</th><th>투표율</th><th>광역단체장</th><th>맥락</th></tr>
        </thead>
        <tbody>${tableRows}</tbody>
      </table>
      <p class="trend-meta">출처: 중앙선거관리위원회 통계 + 위키피디아 종합</p>
    </section>`;

  // 슬라이더 인터랙티브
  const input = document.getElementById('forecast-turnout');
  const output = document.getElementById('forecast-output');
  const matchEl = document.getElementById('forecast-match');
  input.addEventListener('input', () => {
    const v = parseFloat(input.value);
    output.textContent = v.toFixed(1) + '%';
    const r = findClosestPastElection(v);
    const winners = historyWinnersSummary(r.match.winners);
    matchEl.innerHTML = `
      <p>가장 가까운 과거 회차: <strong>${r.match.round}회 (${r.match.year}, ${r.match.turnout}%)</strong> · 차이 ${r.diff.toFixed(1)}%p</p>
      <p class="forecast-context">${r.match.context}</p>
      <p class="forecast-winners">광역단체장 결과: <strong>${winners}</strong></p>`;
  });

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

function renderTrendBox() {
  if (!state.data) return '';
  const s = buildProfileStats();
  const womenPct = s.byGender['여'] ? (s.byGender['여'] / s.total * 100) : 0;
  const topParty = s.parties[0];
  return `
    <a class="trend-card" href="#trend">
      <div class="trend-card-head">
        <span class="trend-card-label">출마자 한눈에</span>
        <span class="trend-card-period">정당·연령·성별</span>
      </div>
      <div class="trend-summary">
        <div class="trend-summary-stat"><strong>${s.ageAvg.toFixed(1)}</strong>세<small>평균 연령</small></div>
        <div class="trend-summary-stat"><strong>${womenPct.toFixed(0)}</strong>%<small>여성 비율</small></div>
        <div class="trend-summary-stat"><strong>${topParty ? topParty[1].toLocaleString() : 0}</strong>명<small>${topParty ? topParty[0] : '-'}</small></div>
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

// 출마자 한눈에 페이지 (#trend) — 정당·연령·성별·직업 통계
function renderTrendFull() {
  const app = document.getElementById('app');
  app.className = '';
  if (!state.data) {
    app.innerHTML = '<div class="loading">불러오는 중…</div>';
    return;
  }
  const s = buildProfileStats();
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

  // 시계열 — 페이지 하단에 작은 sparkline으로 유지(완전 제거 X, 보조 정보)
  const ts = state.timeseries;
  let trendSparkline = '';
  if (ts?.series?.length >= 2) {
    const series = ts.series;
    const totals = series.map(r => r.total);
    const first = series[0].date, last = series[series.length - 1].date;
    const fmt = d => `${d.slice(4,6)}/${d.slice(6,8)}`;
    const min = Math.min(...totals), max = Math.max(...totals), range = max - min || 1;
    const w = 600, h = 80;
    const stepX = w / (totals.length - 1);
    const pts = totals.map((v, i) =>
      `${(i*stepX).toFixed(1)},${(h - ((v-min)/range)*(h-10) - 5).toFixed(1)}`
    ).join(' ');
    trendSparkline = `
      <section class="trend-section">
        <h3 class="trend-section-title">최근 ${series.length}일 출마자 수 추이</h3>
        <svg viewBox="0 0 ${w} ${h}" class="trend-chart" aria-label="출마자 수 변화">
          <polyline fill="none" stroke="#c41e3a" stroke-width="2" points="${pts}"/>
        </svg>
        <p class="trend-meta">${fmt(first)} ${totals[0].toLocaleString()}명 → ${fmt(last)} ${totals[totals.length-1].toLocaleString()}명</p>
      </section>`;
  }

  app.innerHTML = `
    <nav class="breadcrumb"><a href="#">전국</a><span class="sep">›</span><span class="current">출마자 한눈에</span></nav>
    <div class="detail-head">
      <h1 class="detail-title">출마자 한눈에</h1>
      <div class="detail-inline-stats">
        <span>총 ${s.total.toLocaleString()}명 · 평균 ${s.ageAvg.toFixed(1)}세 · 여성 ${womenPct.toFixed(0)}%</span>
      </div>
    </div>
    <p class="page-intro">선관위 등록 데이터를 기반으로 정당·연령·성별·직업 분포를 정리했습니다. 재산·전과·병역 정보는 후보 등록(5/14) 이후 추가 공개될 예정.</p>

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
    </section>

    ${trendSparkline}`;
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
    const detail = linked ? `${stage} <strong>${list.length}</strong>명` : `${stage} 미등록`;
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

  // 관전 포인트 — 디테일은 별도 페이지로 위임. 홈은 한눈에 보이는 카드 2개.
  const ranking = buildCompetitionRanking();
  const top = ranking[0];
  const uc = buildUncontestedList();
  const ucTotal = uc.tied.length + uc.short.length + uc.zero.length;
  const summaryBox = (top || ucTotal) ? `
    <div class="summary-row">
      ${top ? `
        <a class="summary-card" href="#competition">
          <span class="summary-card-label">경쟁이 가장 치열한 선거구</span>
          <span class="summary-card-value"><strong>${top.ratio.toFixed(1)}</strong><span class="summary-card-unit">:1</span></span>
          <span class="summary-card-sub">${formatRegionLabel(top)} ${top.title} · ${ranking.length.toLocaleString()}개 선거구 전체 보기 →</span>
        </a>` : ''}
      ${ucTotal ? `
        <a class="summary-card" href="#uncontested">
          <span class="summary-card-label">경쟁 없는 선거구</span>
          <span class="summary-card-value"><strong>${ucTotal.toLocaleString()}</strong>곳</span>
          <span class="summary-card-sub">단독 ${uc.tied.length} · 일부 미달 ${uc.short.length} · 0명 ${uc.zero.length} · 모두 보기 →</span>
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
}

// ============ Render: 상세 ============
function renderSidoDetail(sidoName, focusSgg) {

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
      <div>
        <h2 class="detail-title">${sidoName}</h2>
        <button type="button" class="page-share" data-share-page data-share-title="${sidoName} 출마자 현황 — 6·3 지방선거">🔗 이 페이지 공유</button>
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

function route() {
  const hash = decodeURIComponent(location.hash.slice(1));
  updateSidoNavActive(hash);
  if (!hash) return renderHome();
  if (hash === 'competition') return renderCompetitionFull();
  if (hash === 'changes') return renderChangesFull();
  if (hash === 'trend') return renderTrendFull();
  if (hash === 'history') return renderHistoryFull();
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

// ============ 경쟁 없는 선거구 (공용 헬퍼) ============
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
      <span class="uc-detail">${r.count}/${r.seat}</span>
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

// 경쟁 없는 선거구 전체 페이지 (#uncontested 또는 #uncontested/{cat})
function renderUncontestedFull(category) {
  const uc = buildUncontestedList();
  const cats = [
    { key: 'tied',  label: '단독 출마·정원 충원 (후보 수 = 정원)',  items: uc.tied,  cls: 'tied' },
    { key: 'short', label: '정원 일부 미달 (1명 이상·후보 수 < 정원)', items: uc.short, cls: 'short' },
    { key: 'zero',  label: '후보 0명',                            items: uc.zero,  cls: 'zero' },
  ];
  const filtered = category ? cats.filter(c => c.key === category) : cats;
  const titleSuffix = category
    ? ` · ${cats.find(c => c.key === category)?.label || category}`
    : '';
  const html = `
    <nav class="breadcrumb">
      <a href="#">전국</a>
      <span class="sep">›</span>
      <span class="current">경쟁 없는 선거구${titleSuffix}</span>
    </nav>
    <div class="detail-head">
      <h1 class="detail-title">경쟁 없는 선거구</h1>
      <div class="detail-inline-stats">
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
  const rows = ranking.map((r, i) => {
    const target = r.sgg || r.sd;
    const href = `#${encodeURIComponent(sidoFor(r))}::${encodeURIComponent(target)}`;
    return `
      <li>
        <span class="comp-rank">${i + 1}</span>
        <a class="comp-region" href="${href}">${formatRegionLabel(r)}</a>
        <span class="comp-type">${r.title}</span>
        <span class="comp-ratio"><strong>${r.ratio.toFixed(1)}</strong>:1</span>
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
    return chip('sd', sd, sd, n, candidatesFilter.sd.has(sd));
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
    const region = c.sggName && c.sggName !== c.sdName
      ? `${c.sdName} · ${c.sggName}` : (c.sdName || '');
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
      }
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
