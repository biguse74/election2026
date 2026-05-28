// 사전투표율 실시간 페이지 로직
// 데이터 소스:
//   data/early_voting/20260603/timeseries.json  — 시점별 시도 누적 (9회)
//   data/early_voting/20260603/latest.json      — 최신 1건 (9회)
//   data/early_voting/baseline_8th.json         — 8회(2022) 최종 baseline

const SG_ID = '20260603';
const PATHS = {
  timeseries: `../data/early_voting/${SG_ID}/timeseries.json`,
  latest:     `../data/early_voting/${SG_ID}/latest.json`,
  baseline8:  `../data/early_voting/baseline_8th.json`,
};

// 시도 표준 순서 (행정안전부) — 그리드 정렬용
const SIDO_ORDER = [
  '서울특별시', '부산광역시', '대구광역시', '인천광역시',
  '광주광역시', '대전광역시', '울산광역시', '세종특별자치시',
  '경기도', '강원특별자치도', '충청북도', '충청남도',
  '전북특별자치도', '전라남도', '경상북도', '경상남도', '제주특별자치도',
];

// 시도 짧은 이름 (좁은 화면용)
const SIDO_SHORT = {
  '서울특별시': '서울', '부산광역시': '부산', '대구광역시': '대구', '인천광역시': '인천',
  '광주광역시': '광주', '대전광역시': '대전', '울산광역시': '울산', '세종특별자치시': '세종',
  '경기도': '경기', '강원특별자치도': '강원', '충청북도': '충북', '충청남도': '충남',
  '전북특별자치도': '전북', '전라남도': '전남', '경상북도': '경북', '경상남도': '경남',
  '제주특별자치도': '제주',
};

const BAR_MAX_PCT = 35; // 막대 100% width가 가리키는 사전투표율 상한 (8회 전남 31% 커버)

async function loadJSON(path) {
  try {
    const res = await fetch(path + '?t=' + Date.now(), { cache: 'no-store' });
    if (!res.ok) return null;
    return await res.json();
  } catch (e) {
    return null;
  }
}

function fmtPct(v) {
  if (v == null || isNaN(v)) return '—';
  return Number(v).toFixed(2);
}

function fmtKST(iso) {
  if (!iso) return '—';
  // ISO with +09:00 — Date 객체로 변환 후 KST 포맷
  try {
    const d = new Date(iso);
    const m = `${d.getUTCMonth() + 1}`.padStart(2, '0');
    const day = `${d.getUTCDate()}`.padStart(2, '0');
    // ISO 문자열이 +09:00이라면, UTC ms에서 +9시간이 KST.
    const kst = new Date(d.getTime() + 9 * 3600 * 1000);
    const mm = `${kst.getUTCMonth() + 1}`.padStart(2, '0');
    const dd = `${kst.getUTCDate()}`.padStart(2, '0');
    const hh = `${kst.getUTCHours()}`.padStart(2, '0');
    const mi = `${kst.getUTCMinutes()}`.padStart(2, '0');
    return `${mm}/${dd} ${hh}:${mi}`;
  } catch (e) {
    return iso;
  }
}

function renderHero(latest, baseline8) {
  const h9 = document.getElementById('hero-9');
  const h9m = document.getElementById('hero-9-meta');
  const h8 = document.getElementById('hero-8');
  const h8m = document.getElementById('hero-8-meta');
  const hd = document.getElementById('hero-delta');
  const ua = document.getElementById('updated-at');

  if (!latest || !latest.national) {
    h9.innerHTML = '대기 중<span class="pct"></span>';
    h9m.textContent = '선관위는 보통 매 정시(09:00, 10:00…)에 누적 통계를 발표합니다. 첫 발표가 들어오는 대로 자동 갱신.';
    h8.innerHTML = `${fmtPct(baseline8?.national_final)}<span class="pct">%</span>`;
    h8m.textContent = '8회 최종(2022.5.28 18시)';
    hd.textContent = '시작 대기';
    hd.className = 'hero-delta hero-delta-flat';
    ua.textContent = '아직 없음';
    return;
  }

  const v9 = latest.national.turnout;
  h9.innerHTML = `${fmtPct(v9)}<span class="pct">%</span>`;
  h9m.textContent = `${fmtKST(latest.fetched_at)} 기준 · 양일 누적`;

  const v8 = baseline8?.national_final ?? null;
  h8.innerHTML = `${fmtPct(v8)}<span class="pct">%</span>`;
  h8m.textContent = '8회 최종(2022.5.27~28 양일 합산)';

  if (v8 != null && v9 != null) {
    const diff = v9 - v8;
    const sign = diff > 0 ? '+' : (diff < 0 ? '' : '±');
    hd.textContent = `8회 최종 대비 ${sign}${diff.toFixed(2)}%p`;
    hd.className = 'hero-delta ' + (diff > 0.05 ? 'hero-delta-up' : diff < -0.05 ? 'hero-delta-down' : 'hero-delta-flat');
  }
  ua.textContent = fmtKST(latest.fetched_at) + ' (KST)';
}

function renderSidoList(latest, baseline8) {
  const root = document.getElementById('sido-list');

  // 시도 인덱스 — 9회 데이터 (없으면 빈 맵)
  const map9 = new Map((latest?.by_sido || []).map(s => [s.sdName, s]));
  // 시도 인덱스 — 8회 baseline
  const map8 = new Map((baseline8?.by_sido || []).map(s => [s.sdName, s.final]));

  const html = SIDO_ORDER.map(sd => {
    const cur = map9.get(sd);
    const prev = map8.get(sd);
    const v9 = cur ? cur.turnout : null;
    const v8 = prev != null ? prev : null;
    const w9 = v9 != null ? Math.min(100, (v9 / BAR_MAX_PCT) * 100) : 0;
    const w8 = v8 != null ? Math.min(100, (v8 / BAR_MAX_PCT) * 100) : 0;
    const short = SIDO_SHORT[sd] || sd;
    const headValue = v9 != null
      ? `${fmtPct(v9)}<span style="font-size:0.8em;color:var(--muted);font-weight:600;">%</span>`
      : `<span style="color:var(--muted);font-weight:600;font-size:0.85em;">시작 대기</span>`;
    return `
      <div class="sido-row">
        <div class="sido-row-head">
          <span class="sido-name">${short}</span>
          <span class="sido-pct">${headValue}<span class="sido-pct-prev">${v8 != null ? '8회 ' + fmtPct(v8) + '%' : ''}</span></span>
        </div>
        <div class="sido-bars">
          <div class="sido-bar-line"><span class="sido-bar-label">9회</span><div class="sido-bar-wrap"><div class="sido-bar-9" style="width:${w9}%"></div></div></div>
          <div class="sido-bar-line"><span class="sido-bar-label">8회</span><div class="sido-bar-wrap"><div class="sido-bar-8" style="width:${w8}%"></div></div></div>
        </div>
      </div>
    `;
  }).join('');
  root.innerHTML = html;
}

function renderTimeline(ts, baseline8) {
  const svg = document.getElementById('timeline');
  svg.innerHTML = '';

  const W = 1000, H = 260;
  const padL = 50, padR = 20, padT = 18, padB = 30;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;

  // Y 스케일 0 ~ 30 (사전투표율 일반 범위)
  const yMax = 30;
  const yToPx = v => padT + (1 - v / yMax) * plotH;

  // X 스케일: 5/29 06:00 ~ 5/30 19:00 (37시간)
  const X_START = new Date('2026-05-29T06:00:00+09:00').getTime();
  const X_END   = new Date('2026-05-30T19:00:00+09:00').getTime();
  const xToPx = t => padL + ((t - X_START) / (X_END - X_START)) * plotW;

  // 격자 + Y축 라벨
  const gridGroup = [];
  for (let y = 0; y <= yMax; y += 5) {
    const ypx = yToPx(y);
    gridGroup.push(`<line x1="${padL}" x2="${W - padR}" y1="${ypx}" y2="${ypx}" stroke="#eee" stroke-width="1"/>`);
    gridGroup.push(`<text x="${padL - 8}" y="${ypx + 4}" font-size="10" fill="#999" text-anchor="end">${y}%</text>`);
  }
  // X축 라벨 (KST 시각 표시: 5/29 06·12·18 / 5/30 06·12·18)
  const xticks = [
    ['5/29 06', new Date('2026-05-29T06:00:00+09:00').getTime()],
    ['12',      new Date('2026-05-29T12:00:00+09:00').getTime()],
    ['18',      new Date('2026-05-29T18:00:00+09:00').getTime()],
    ['5/30 06', new Date('2026-05-30T06:00:00+09:00').getTime()],
    ['12',      new Date('2026-05-30T12:00:00+09:00').getTime()],
    ['18',      new Date('2026-05-30T18:00:00+09:00').getTime()],
  ];
  for (const [label, t] of xticks) {
    const xpx = xToPx(t);
    gridGroup.push(`<line x1="${xpx}" x2="${xpx}" y1="${padT}" y2="${H - padB}" stroke="#eee" stroke-width="1"/>`);
    gridGroup.push(`<text x="${xpx}" y="${H - padB + 14}" font-size="10" fill="#999" text-anchor="middle">${label}</text>`);
  }

  // 8회 최종(20.62%) 점선
  const y8 = yToPx(baseline8?.national_final ?? 20.62);
  gridGroup.push(`<line x1="${padL}" x2="${W - padR}" y1="${y8}" y2="${y8}" stroke="#bbb" stroke-width="1.5" stroke-dasharray="4 4"/>`);
  gridGroup.push(`<text x="${W - padR - 6}" y="${y8 - 4}" font-size="10" fill="#888" text-anchor="end">8회 최종 20.62%</text>`);

  // 점심 마감(18시) 세로선
  for (const t of [new Date('2026-05-29T18:00:00+09:00').getTime(), new Date('2026-05-30T18:00:00+09:00').getTime()]) {
    const x = xToPx(t);
    gridGroup.push(`<line x1="${x}" x2="${x}" y1="${padT}" y2="${H - padB}" stroke="#ccc" stroke-width="1" stroke-dasharray="2 3"/>`);
  }

  // 9회 시계열 라인
  const points = [];
  if (ts && ts.snapshots && ts.snapshots.length > 0) {
    for (const s of ts.snapshots) {
      const t = new Date(s.at).getTime();
      if (isNaN(t)) continue;
      const v = s.national?.turnout;
      if (v == null) continue;
      points.push([xToPx(t), yToPx(v), v, s.at]);
    }
  }
  const lineGroup = [];
  if (points.length >= 2) {
    const d = points.map((p, i) => (i === 0 ? 'M' : 'L') + p[0].toFixed(1) + ',' + p[1].toFixed(1)).join(' ');
    lineGroup.push(`<path d="${d}" stroke="#c41e3a" stroke-width="2.2" fill="none" stroke-linecap="round" stroke-linejoin="round"/>`);
  }
  for (const p of points) {
    lineGroup.push(`<circle cx="${p[0].toFixed(1)}" cy="${p[1].toFixed(1)}" r="3" fill="#c41e3a"><title>${fmtKST(p[3])} · ${p[2].toFixed(2)}%</title></circle>`);
  }
  if (points.length === 0) {
    lineGroup.push(`<text x="${W / 2}" y="${H / 2}" font-size="12" fill="#999" text-anchor="middle">사전투표 시작 후 데이터가 누적됩니다.</text>`);
  }

  svg.innerHTML = gridGroup.join('') + lineGroup.join('');
}

async function main() {
  const [latest, ts, baseline8] = await Promise.all([
    loadJSON(PATHS.latest),
    loadJSON(PATHS.timeseries),
    loadJSON(PATHS.baseline8),
  ]);

  renderHero(latest, baseline8);
  renderSidoList(latest, baseline8);
  renderTimeline(ts, baseline8);
}

main();

// 5분마다 자동 새로고침 — 워크플로우가 30분 간격으로 수집하므로 여유를 두고 다시 fetch.
setInterval(main, 5 * 60 * 1000);
