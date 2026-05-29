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
  baseline7:  `../data/early_voting/baseline_7th.json`,
  baselineGen22:  `../data/early_voting/baseline_general22nd.json`,
  basePres21:     `../data/early_voting/baseline_president21st.json`,
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

// 막대 100% width 상한 — 현재 데이터에 맞춰 동적으로 계산 (renderSidoList에서 결정)
// 시간대 비교라 이른 시각엔 1~5%, 마감 임박엔 25%+ 까지 변동

// 8회 시도별 같은 시간대 — 선관위 통계시스템 엑셀 실측치.
// baseline_8th.json의 by_sido_hourly에서 직접 조회:
//   day1[sdName][hour] = 1일차만 누적 (%), day2[sdName][hour] = 양일 누적 (%)
// 그 시각에 데이터가 없으면 null.
function lookup8SidoAt(baseline8, sdName, day, hour) {
  const key = day === 2 ? 'day2' : 'day1';
  const t = baseline8?.by_sido_hourly?.[key]?.[sdName]?.[String(hour)];
  return (t == null) ? null : t;
}

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

// baseline의 hourly_national에서 (day, hour) 시점의 양일 누적값 조회.
// day=1, hour=8 이면 day1[h=8].cum (1일차만)
// day=2, hour=8 이면 day2[h=8].cum (양일 누적)
function baselineAt(baseline, day, hour) {
  if (!baseline || !baseline.hourly_national) return null;
  const key = day === 2 ? 'day2' : 'day1';
  const arr = baseline.hourly_national[key] || [];
  const row = arr.find(r => r.hour === hour);
  return row ? row.cum : null;
}

// 9회 latest의 진행 상태 → (day, hour) 도출.
// day2_time_code 있으면 2일차 진행 중, 없으면 1일차 진행 중.
function progressFromLatest(latest) {
  if (!latest) return null;
  const t2 = latest.day2_time_code;
  const t1 = latest.day1_time_code;
  if (t2) return { day: 2, hour: parseInt(t2, 10) };
  if (t1) return { day: 1, hour: parseInt(t1, 10) };
  return null;
}

function renderHero(latest, baseline8, baseline7) {
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
  const prog = progressFromLatest(latest);
  h9.innerHTML = `${fmtPct(v9)}<span class="pct">%</span>`;
  h9m.textContent = prog
    ? `${prog.day}일차 ${String(prog.hour).padStart(2,'0')}시 기준 · KST ${fmtKST(latest.fetched_at)} 갱신`
    : `${fmtKST(latest.fetched_at)} 기준 · 양일 누적`;

  // 8회 같은 시각 비교 (가능하면)
  const v8sameTime = prog ? baselineAt(baseline8, prog.day, prog.hour) : null;
  const v7sameTime = prog ? baselineAt(baseline7, prog.day, prog.hour) : null;

  if (v8sameTime != null) {
    h8.innerHTML = `${fmtPct(v8sameTime)}<span class="pct">%</span>`;
    h8m.innerHTML = `8회(2022) 같은 시각 (${prog.day}일차 ${String(prog.hour).padStart(2,'0')}시)`
      + (v7sameTime != null ? `<br><span style="color:rgba(255,255,255,0.6);font-size:0.95em;">· 7회(2018) 같은 시각 ${fmtPct(v7sameTime)}%</span>` : '');

    const diff = v9 - v8sameTime;
    const sign = diff > 0 ? '+' : (diff < 0 ? '' : '±');
    hd.textContent = `8회 같은 시각 대비 ${sign}${diff.toFixed(2)}%p`;
    hd.className = 'hero-delta ' + (diff > 0.05 ? 'hero-delta-up' : diff < -0.05 ? 'hero-delta-down' : 'hero-delta-flat');
  } else {
    // 8회 시간대별 데이터에 없는 시각(예: 06시·19시 등) — 최종 비교로 fallback
    const v8final = baseline8?.national_final ?? null;
    h8.innerHTML = `${fmtPct(v8final)}<span class="pct">%</span>`;
    h8m.textContent = '8회 최종(2022.5.28 18시)';
    if (v8final != null) {
      const diff = v9 - v8final;
      const sign = diff > 0 ? '+' : (diff < 0 ? '' : '±');
      hd.textContent = `8회 최종 대비 ${sign}${diff.toFixed(2)}%p`;
      hd.className = 'hero-delta ' + (diff > 0.05 ? 'hero-delta-up' : diff < -0.05 ? 'hero-delta-down' : 'hero-delta-flat');
    }
  }
  ua.textContent = fmtKST(latest.fetched_at) + ' (KST)';
}

function renderSidoStats(latest, baseline8) {
  const root = document.getElementById('sido-stats');
  if (!root) return;
  if (!latest?.by_sido || latest.by_sido.length === 0 || latest.national?.turnout == null) {
    root.innerHTML = '';
    return;
  }

  const prog = progressFromLatest(latest);

  // 9회 현재 최고/최저
  const sorted = [...latest.by_sido].sort((a, b) => b.turnout - a.turnout);
  const top = sorted[0];
  const bottom = sorted[sorted.length - 1];

  // 8회 같은 시각(실측) 대비 Δ — 가속/감속이 가장 큰 시도
  let bestUp = null, bestDown = null;
  if (prog) {
    const withDelta = latest.by_sido
      .map(s => {
        const v8 = lookup8SidoAt(baseline8, s.sdName, prog.day, prog.hour);
        if (v8 == null) return null;
        return { sd: s.sdName, cur: s.turnout, prev: v8, delta: s.turnout - v8 };
      })
      .filter(Boolean);
    if (withDelta.length) {
      withDelta.sort((a, b) => b.delta - a.delta);
      bestUp = withDelta[0];
      bestDown = withDelta[withDelta.length - 1];
    }
  }

  const short = (sd) => SIDO_SHORT[sd] || sd;
  const sign = (d) => d > 0 ? '+' : (d < 0 ? '' : '±');

  root.innerHTML = `
    <div class="sido-stat-card">
      <span class="sido-stat-label">현재 최고</span>
      <div><span class="sido-stat-value">${short(top.sdName)}</span><span class="sido-stat-pct">${fmtPct(top.turnout)}%</span></div>
      <span class="sido-stat-sub">9회 현재 1위</span>
    </div>
    <div class="sido-stat-card">
      <span class="sido-stat-label">현재 최저</span>
      <div><span class="sido-stat-value">${short(bottom.sdName)}</span><span class="sido-stat-pct sido-stat-pct-low">${fmtPct(bottom.turnout)}%</span></div>
      <span class="sido-stat-sub">9회 현재 17위</span>
    </div>
    ${bestUp ? `<div class="sido-stat-card">
      <span class="sido-stat-label">8회 대비 가속 1위</span>
      <div><span class="sido-stat-value">${short(bestUp.sd)}</span><span class="sido-stat-pct">${sign(bestUp.delta)}${bestUp.delta.toFixed(2)}%p</span></div>
      <span class="sido-stat-sub">현재 ${fmtPct(bestUp.cur)}% · 8회 같은 시각 ${fmtPct(bestUp.prev)}%</span>
    </div>` : ''}
    ${bestDown ? `<div class="sido-stat-card">
      <span class="sido-stat-label">8회 대비 감속 1위</span>
      <div><span class="sido-stat-value">${short(bestDown.sd)}</span><span class="sido-stat-pct sido-stat-pct-low">${sign(bestDown.delta)}${bestDown.delta.toFixed(2)}%p</span></div>
      <span class="sido-stat-sub">현재 ${fmtPct(bestDown.cur)}% · 8회 같은 시각 ${fmtPct(bestDown.prev)}%</span>
    </div>` : ''}
  `;
}

function renderSidoList(latest, baseline8) {
  const root = document.getElementById('sido-list');

  const map9 = new Map((latest?.by_sido || []).map(s => [s.sdName, s]));
  const prog = progressFromLatest(latest);

  // 각 시도의 (9회 현재, 8회 같은 시각 실측, Δ) 계산
  const rows = SIDO_ORDER.map(sd => {
    const cur = map9.get(sd);
    const v9 = cur ? cur.turnout : null;
    const v8 = prog ? lookup8SidoAt(baseline8, sd, prog.day, prog.hour) : null;
    const delta = (v9 != null && v8 != null) ? v9 - v8 : null;
    return { sd, v9, v8, delta };
  });

  // 동적 막대 상한: 현재 시도 최고 누적치의 1.3배(최소 5%) — 시간대마다 자동 스케일
  const maxObserved = Math.max(
    ...rows.map(r => Math.max(r.v9 ?? 0, r.v8 ?? 0))
  );
  const BAR_MAX = Math.max(5, Math.ceil(maxObserved * 1.3));

  // Δ 큰 순으로 정렬 — 8회 대비 가장 빠른 시도가 위로
  rows.sort((a, b) => {
    if (a.delta == null && b.delta == null) return 0;
    if (a.delta == null) return 1;
    if (b.delta == null) return -1;
    return b.delta - a.delta;
  });

  const sign = (d) => d > 0 ? '+' : (d < 0 ? '' : '±');
  const html = rows.map(({ sd, v9, v8, delta }) => {
    const short = SIDO_SHORT[sd] || sd;
    const w9 = v9 != null ? Math.min(100, (v9 / BAR_MAX) * 100) : 0;
    const w8 = v8 != null ? Math.min(100, (v8 / BAR_MAX) * 100) : 0;
    const headValue = v9 != null
      ? `${fmtPct(v9)}<span style="font-size:0.8em;color:var(--muted);font-weight:600;">%</span>`
      : `<span style="color:var(--muted);font-weight:600;font-size:0.85em;">시작 대기</span>`;
    const deltaBadge = delta != null
      ? `<span class="sido-delta ${delta > 0.05 ? 'sido-delta-up' : delta < -0.05 ? 'sido-delta-down' : 'sido-delta-flat'}">${sign(delta)}${delta.toFixed(2)}%p</span>`
      : '';
    return `
      <div class="sido-row">
        <div class="sido-row-head">
          <span class="sido-name">${short}</span>
          <span class="sido-pct">${headValue}${deltaBadge}</span>
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

// 과거 회차의 hourly_national을 2026 좌표계로 매핑.
// 1일차 N시 → 2026-05-29 N시, 2일차 N시 → 2026-05-30 N시.
function baselineSeriesTo2026(baseline) {
  if (!baseline?.hourly_national) return [];
  const out = [];
  for (const row of (baseline.hourly_national.day1 || [])) {
    const t = new Date(`2026-05-29T${String(row.hour).padStart(2,'0')}:00:00+09:00`).getTime();
    out.push([t, row.cum]);
  }
  for (const row of (baseline.hourly_national.day2 || [])) {
    const t = new Date(`2026-05-30T${String(row.hour).padStart(2,'0')}:00:00+09:00`).getTime();
    out.push([t, row.cum]);
  }
  return out.sort((a, b) => a[0] - b[0]);
}

function renderTimeline(ts, baseline8, baseline7) {
  const svg = document.getElementById('timeline');
  svg.innerHTML = '';

  const W = 1000, H = 260;
  const padL = 50, padR = 20, padT = 18, padB = 30;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;

  // Y 스케일 0 ~ 25 (8회 최종 20.62% 여유 있게)
  const yMax = 25;
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
  // X축 라벨
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
  // 1일차 마감(18시) 세로선
  for (const t of [new Date('2026-05-29T18:00:00+09:00').getTime(), new Date('2026-05-30T18:00:00+09:00').getTime()]) {
    const x = xToPx(t);
    gridGroup.push(`<line x1="${x}" x2="${x}" y1="${padT}" y2="${H - padB}" stroke="#ccc" stroke-width="1" stroke-dasharray="2 3"/>`);
  }

  const lineGroup = [];

  // 7회·8회 라인 (과거)
  function drawBaselineLine(baseline, color, dash, label) {
    const series = baselineSeriesTo2026(baseline);
    if (series.length < 2) return;
    const path = series.map((p, i) => (i === 0 ? 'M' : 'L') + xToPx(p[0]).toFixed(1) + ',' + yToPx(p[1]).toFixed(1)).join(' ');
    lineGroup.push(`<path d="${path}" stroke="${color}" stroke-width="1.8" fill="none" stroke-dasharray="${dash}" stroke-linecap="round" stroke-linejoin="round"/>`);
    // 마지막 점 라벨
    const last = series[series.length - 1];
    lineGroup.push(`<text x="${(xToPx(last[0]) + 4).toFixed(1)}" y="${(yToPx(last[1]) + 3).toFixed(1)}" font-size="9.5" fill="${color}">${label} ${last[1].toFixed(2)}%</text>`);
  }
  if (baseline7) drawBaselineLine(baseline7, '#9aa4b2', '2 3', '7회');
  if (baseline8) drawBaselineLine(baseline8, '#5f6a78', '6 4', '8회');

  // 9회 시계열 라인 (현재)
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
  if (points.length >= 2) {
    const d = points.map((p, i) => (i === 0 ? 'M' : 'L') + p[0].toFixed(1) + ',' + p[1].toFixed(1)).join(' ');
    lineGroup.push(`<path d="${d}" stroke="#c41e3a" stroke-width="2.4" fill="none" stroke-linecap="round" stroke-linejoin="round"/>`);
  }
  for (const p of points) {
    lineGroup.push(`<circle cx="${p[0].toFixed(1)}" cy="${p[1].toFixed(1)}" r="3" fill="#c41e3a"><title>${fmtKST(p[3])} · ${p[2].toFixed(2)}%</title></circle>`);
  }
  if (points.length === 0) {
    lineGroup.push(`<text x="${W / 2}" y="${H / 2}" font-size="12" fill="#999" text-anchor="middle">9회 라인은 첫 수집 후 그려집니다.</text>`);
  }

  svg.innerHTML = gridGroup.join('') + lineGroup.join('');
}

// 9회 timeseries에서 각 일차×시각의 NEC 발표 누적값 추출.
// 같은 시각이 여러 번 수집됐다면 가장 마지막(가장 큰 누적)을 채택.
function build9hRoundIndex(ts) {
  const idx = { 1: new Map(), 2: new Map() }; // day → Map(hour → turnout)
  if (!ts?.snapshots) return idx;
  for (const s of ts.snapshots) {
    const v = s.national?.turnout;
    if (v == null) continue;
    // day1_time_code/day2_time_code가 있으면 그 시각에 매칭
    // 단 day2_time_code가 있으면 day1은 이미 마감, day2 진행 중이므로
    // day1은 1일차 18시(마감) 값으로 사용
    const t1 = s.day1_time_code;
    const t2 = s.day2_time_code;
    if (t2) {
      const h2 = parseInt(t2, 10);
      // 9회 양일 누적(v)에서 1일차 마감값을 빼면 2일차 누적값이 되지만,
      // NEC가 day2 누적률을 양일 합산 기준으로 발표하므로 그대로 사용 가능
      // 단순화: 양일 합산 v를 day2.hour로 매핑
      idx[2].set(h2, Math.max(idx[2].get(h2) ?? 0, v));
    } else if (t1) {
      const h1 = parseInt(t1, 10);
      idx[1].set(h1, Math.max(idx[1].get(h1) ?? 0, v));
    }
  }
  return idx;
}

function renderHourlyTable(ts, baseline8, baseline7, baselineGen22, basePres21) {
  const tbody = document.getElementById('hourly-tbody');
  if (!tbody) return;
  const day = parseInt(document.querySelector('.hourly-tab.active')?.dataset?.day || '1', 10);

  const idx9 = build9hRoundIndex(ts);
  const pick = (b) => b?.hourly_national?.[`day${day}`] || [];
  const arr8 = pick(baseline8);
  const arr7 = pick(baseline7);
  const arrGen22 = pick(baselineGen22);
  const arrPres21 = pick(basePres21);

  const hours = [];
  for (let h = 7; h <= 18; h++) hours.push(h);

  let currentHour = null;
  for (let h = 18; h >= 7; h--) {
    if (idx9[day].has(h)) { currentHour = h; break; }
  }

  const rows = hours.map(h => {
    const v9 = idx9[day].get(h);
    const v8 = arr8.find(r => r.hour === h)?.cum;
    const v7 = arr7.find(r => r.hour === h)?.cum;
    const vGen22 = arrGen22.find(r => r.hour === h)?.cum;
    const vPres21 = arrPres21.find(r => r.hour === h)?.cum;
    // 18시는 사전투표 마감 시각 — '마감' 표기 유지. 06시 실제 시작이지만 NEC 발표는 07시부터라
    // 07시에 '개시'라 쓰면 오해 소지 → 표기 제거.
    const mark = (h === 18) ? `<span class="col-mark"> · 마감</span>` : '';
    const trClass = (h === currentHour) ? ' class="row-9-current"' : '';

    const cell9 = v9 != null
      ? `<td class="col-9">${fmtPct(v9)}%</td>`
      : `<td class="col-pending">${h <= (currentHour ?? -1) ? '—' : '대기'}</td>`;

    let deltaCell = '<td class="delta-flat">—</td>';
    if (v9 != null && v8 != null) {
      const d = v9 - v8;
      const sign = d > 0 ? '+' : (d < 0 ? '' : '±');
      const cls = d > 0.05 ? 'delta-up' : d < -0.05 ? 'delta-down' : 'delta-flat';
      deltaCell = `<td class="${cls}">${sign}${d.toFixed(2)}%p</td>`;
    }

    const cell = (v) => `<td>${v != null ? fmtPct(v) + '%' : '—'}</td>`;
    return `<tr${trClass}>
      <td>${String(h).padStart(2,'0')}시${mark}</td>
      ${cell9}
      ${cell(v8)}
      ${cell(v7)}
      ${cell(vPres21)}
      ${cell(vGen22)}
      ${deltaCell}
    </tr>`;
  }).join('');

  tbody.innerHTML = rows;
}

function bindHourlyTabs(ts, baseline8, baseline7, baselineGen22, basePres21) {
  document.querySelectorAll('.hourly-tab').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('.hourly-tab').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      renderHourlyTable(ts, baseline8, baseline7, baselineGen22, basePres21);
    });
  });
}

async function main() {
  const [latest, ts, baseline8, baseline7, baselineGen22, basePres21] = await Promise.all([
    loadJSON(PATHS.latest),
    loadJSON(PATHS.timeseries),
    loadJSON(PATHS.baseline8),
    loadJSON(PATHS.baseline7),
    loadJSON(PATHS.baselineGen22),
    loadJSON(PATHS.basePres21),
  ]);

  renderHero(latest, baseline8, baseline7);
  renderSidoStats(latest, baseline8);
  renderSidoList(latest, baseline8);
  renderHourlyTable(ts, baseline8, baseline7, baselineGen22, basePres21);
  bindHourlyTabs(ts, baseline8, baseline7, baselineGen22, basePres21);
  renderTimeline(ts, baseline8, baseline7);
}

main();

// 5분마다 자동 새로고침 — 워크플로우가 30분 간격으로 수집하므로 여유를 두고 다시 fetch.
setInterval(main, 5 * 60 * 1000);
