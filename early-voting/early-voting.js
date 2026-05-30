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

// (day, hour) → X축 fraction [0,1]. 투표 가능 시간(06~18시)만 사용해 밤샘 구간을 접는다.
//   day1 06~18 → [0, 0.5],  day2 06~18 → [0.5, 1.0]
// 1일차 18시와 2일차 06시가 같은 X 지점(0.5)에서 만나 라인이 바로 이어진다.
const TL_HOUR_START = 6, TL_HOUR_END = 18;
function dayHourToFrac(day, hour) {
  const h = Math.min(Math.max(hour, TL_HOUR_START), TL_HOUR_END);
  const within = (h - TL_HOUR_START) / (TL_HOUR_END - TL_HOUR_START);
  return (day === 2 ? 0.5 : 0) + within * 0.5;
}

// 과거 회차 hourly_national → frac 좌표 시리즈
function baselineFracSeries(baseline) {
  if (!baseline?.hourly_national) return [];
  const out = [];
  for (const row of (baseline.hourly_national.day1 || [])) out.push([dayHourToFrac(1, row.hour), row.cum]);
  for (const row of (baseline.hourly_national.day2 || [])) out.push([dayHourToFrac(2, row.hour), row.cum]);
  return out.sort((a, b) => a[0] - b[0]);
}

function renderTimeline(ts, baseline8, baseline7) {
  const svg = document.getElementById('timeline');
  svg.innerHTML = '';

  const W = 1000, H = 260;
  const padL = 50, padR = 20, padT = 18, padB = 36;
  const plotW = W - padL - padR;
  const plotH = H - padT - padB;

  // Y 스케일 0 ~ 25 (8회 최종 20.62% 여유 있게)
  const yMax = 25;
  const yToPx = v => padT + (1 - v / yMax) * plotH;
  // X 스케일: 투표 가능 시간만 (밤샘 구간 접음)
  const xToPx = frac => padL + frac * plotW;

  // 격자 + Y축 라벨
  const gridGroup = [];
  for (let y = 0; y <= yMax; y += 5) {
    const ypx = yToPx(y);
    gridGroup.push(`<line x1="${padL}" x2="${W - padR}" y1="${ypx}" y2="${ypx}" stroke="#eee" stroke-width="1"/>`);
    gridGroup.push(`<text x="${padL - 8}" y="${ypx + 4}" font-size="10" fill="#999" text-anchor="end">${y}%</text>`);
  }
  // X 시각 눈금 (투표 시간만 — 06·09·12·15·18, 2일차 06은 경계와 겹쳐 생략)
  const hourTicks = [[1, 6], [1, 9], [1, 12], [1, 15], [1, 18], [2, 9], [2, 12], [2, 15], [2, 18]];
  for (const [day, hr] of hourTicks) {
    const xpx = xToPx(dayHourToFrac(day, hr));
    gridGroup.push(`<line x1="${xpx}" x2="${xpx}" y1="${padT}" y2="${H - padB}" stroke="#f2f2f2" stroke-width="1"/>`);
    gridGroup.push(`<text x="${xpx}" y="${H - padB + 13}" font-size="9.5" fill="#aaa" text-anchor="middle">${String(hr).padStart(2,'0')}</text>`);
  }
  // 일자 라벨 (각 반쪽 중앙)
  gridGroup.push(`<text x="${xToPx(0.25).toFixed(1)}" y="${H - padB + 27}" font-size="10.5" fill="#777" font-weight="700" text-anchor="middle">5/29 (금)</text>`);
  gridGroup.push(`<text x="${xToPx(0.75).toFixed(1)}" y="${H - padB + 27}" font-size="10.5" fill="#777" font-weight="700" text-anchor="middle">5/30 (토)</text>`);
  // 일자 경계선 (frac 0.5) — 1일차 마감=2일차 시작, 밤샘 구간을 접은 지점
  const xMid = xToPx(0.5);
  gridGroup.push(`<line x1="${xMid}" x2="${xMid}" y1="${padT}" y2="${H - padB}" stroke="#bbb" stroke-width="1.2" stroke-dasharray="3 3"/>`);

  const lineGroup = [];

  // 7회·8회 라인 (과거) — labelDy로 끝점 라벨 상/하 분리
  function drawBaselineLine(baseline, color, dash, label, labelDy) {
    const series = baselineFracSeries(baseline);
    if (series.length < 2) return;
    const path = series.map((p, i) => (i === 0 ? 'M' : 'L') + xToPx(p[0]).toFixed(1) + ',' + yToPx(p[1]).toFixed(1)).join(' ');
    lineGroup.push(`<path d="${path}" stroke="${color}" stroke-width="1.8" fill="none" stroke-dasharray="${dash}" stroke-linecap="round" stroke-linejoin="round"/>`);
    const last = series[series.length - 1];
    lineGroup.push(`<text x="${(xToPx(last[0]) - 4).toFixed(1)}" y="${(yToPx(last[1]) + labelDy).toFixed(1)}" font-size="9.5" fill="${color}" text-anchor="end">${label} ${last[1].toFixed(2)}%</text>`);
  }
  if (baseline7) drawBaselineLine(baseline7, '#9aa4b2', '2 3', '7회', 14);
  if (baseline8) drawBaselineLine(baseline8, '#5f6a78', '6 4', '8회', -6);

  // 9회 라인 — (day, hour) 정시 기준으로 baseline과 정렬
  const idx9 = build9hRoundIndex(ts);
  const pts9 = [];
  for (const day of [1, 2]) {
    for (const [hour, v] of [...idx9[day].entries()].sort((a, b) => a[0] - b[0])) {
      pts9.push({ x: xToPx(dayHourToFrac(day, hour)), y: yToPx(v), v, day, hour });
    }
  }
  pts9.sort((a, b) => a.x - b.x);
  if (pts9.length >= 2) {
    const d = pts9.map((p, i) => (i === 0 ? 'M' : 'L') + p.x.toFixed(1) + ',' + p.y.toFixed(1)).join(' ');
    lineGroup.push(`<path d="${d}" stroke="#c41e3a" stroke-width="2.4" fill="none" stroke-linecap="round" stroke-linejoin="round"/>`);
  }
  for (const p of pts9) {
    lineGroup.push(`<circle cx="${p.x.toFixed(1)}" cy="${p.y.toFixed(1)}" r="3" fill="#c41e3a"><title>${p.day}일차 ${String(p.hour).padStart(2,'0')}시 · ${p.v.toFixed(2)}%</title></circle>`);
  }
  if (pts9.length === 0) {
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

// 단순선형회귀(OLS) — 과거 회차의 '같은 시점 사전투표율(x) → 최종(y)'을 직선으로 적합.
// 반환: {a,b,yhat,R2,n,s,lo,hi} (lo/hi = 80% 예측구간). 표본<3이면 null.
function olsForecast(points, x0) {
  const n = points.length;
  if (n < 3) return null;
  const xs = points.map(p => p.x), ys = points.map(p => p.y);
  const mx = xs.reduce((a, b) => a + b, 0) / n;
  const my = ys.reduce((a, b) => a + b, 0) / n;
  let Sxx = 0, Sxy = 0, Syy = 0;
  for (let i = 0; i < n; i++) {
    Sxx += (xs[i] - mx) ** 2; Sxy += (xs[i] - mx) * (ys[i] - my); Syy += (ys[i] - my) ** 2;
  }
  if (Sxx <= 0) return null;
  const b = Sxy / Sxx, a = my - b * mx;
  const yhat = a + b * x0;
  let SSE = 0;
  for (let i = 0; i < n; i++) { const e = ys[i] - (a + b * xs[i]); SSE += e * e; }
  const df = n - 2;
  const s = Math.sqrt(SSE / df);
  const SEpred = s * Math.sqrt(1 + 1 / n + (x0 - mx) ** 2 / Sxx);
  const R2 = Syy > 0 ? 1 - SSE / Syy : 1;
  const T80 = { 1: 3.078, 2: 1.886, 3: 1.638, 4: 1.533, 5: 1.476, 6: 1.440 }; // 80% 양측, df별
  const t = T80[df] || 1.44;
  return { a, b, yhat, R2, n, s, lo: yhat - t * SEpred, hi: yhat + t * SEpred };
}

// 최종 사전투표율(양일 누적) 예측 — 선형회귀(OLS) + 80% 예측구간.
//   과거 회차의 '같은 시점 사전투표율 → 최종'을 직선으로 적합해 현재값을 대입.
//   같은 시점이 진행될수록 x가 최종에 가까워져 예측이 실측으로 수렴.
function renderForecast(latest, baseline8, baseline7, baselineGen22, basePres21) {
  const root = document.getElementById('forecast');
  if (!root) return;
  const prog = progressFromLatest(latest);
  const cur = latest?.national?.turnout;
  if (!prog || cur == null) { root.hidden = true; root.innerHTML = ''; return; }

  const refs = [
    { key: '7회', kind: 'jiseon', b: baseline7 },
    { key: '8회', kind: 'jiseon', b: baseline8 },
    { key: '22대', kind: 'ref', b: baselineGen22 },
    { key: '21대', kind: 'ref', b: basePres21 },
  ];
  const points = [];
  for (const r of refs) {
    const x = baselineAt(r.b, prog.day, prog.hour);
    const y = r.b?.national_final;
    if (x && y && x > 0) points.push({ ...r, x, y });
  }
  if (points.length < 2) { root.hidden = true; root.innerHTML = ''; return; }

  const dayLabel = prog.day === 2 ? '2일차 진행 중' : (prog.hour >= 18 ? '1일차 마감' : '1일차 진행 중');
  const reg = olsForecast(points, cur);

  let center, lo, hi, explain;
  if (reg) {
    center = reg.yhat; lo = reg.lo; hi = reg.hi;
    explain =
      `과거 ${reg.n}개 선거의 '같은 시점 사전투표율 → 최종'을 <strong>선형회귀</strong>로 적합 ` +
      `(최종 = ${reg.a.toFixed(1)} + ${reg.b.toFixed(2)}×현재, R²=${reg.R2.toFixed(2)}). ` +
      `현재 <strong>${fmtPct(cur)}%</strong>(${dayLabel}) 대입 → <strong>${center.toFixed(1)}%</strong>. ` +
      `8회 최종(${fmtPct(baseline8?.national_final)}%)보다 ${center > (baseline8?.national_final ?? 0) ? '높은' : '낮은'} 건 9회가 그만큼 ${center > (baseline8?.national_final ?? 0) ? '빠르기' : '느리기'} 때문. ` +
      `표본 ${reg.n}회로 적어 구간이 넓습니다(±는 80% 예측구간).`;
  } else {
    const ratios = points.map(p => cur * (p.y / p.x));
    center = ratios.reduce((a, b) => a + b, 0) / ratios.length;
    lo = Math.min(...ratios); hi = Math.max(...ratios);
    explain = `현재 <strong>${fmtPct(cur)}%</strong>(${dayLabel}) · 과거 회차 비율 평균(표본 부족으로 회귀 대신).`;
  }

  const chips = points.map(p =>
    `<span class="fc-chip ${p.kind === 'jiseon' ? 'fc-chip-j' : ''}">${p.key} ${p.x.toFixed(1)}→${p.y.toFixed(1)}</span>`
  ).join('');

  root.hidden = false;
  root.innerHTML = `
    <div class="fc-head">
      <span class="fc-label">최종 사전투표율 예측 <span class="fc-sub2">(양일 누적 · 회귀)</span></span>
    </div>
    <div class="fc-body">
      <div class="fc-main">
        <span class="fc-big">${center.toFixed(1)}<span class="fc-pct">%</span></span>
        <span class="fc-range">80% 예측구간 ${lo.toFixed(1)}~${hi.toFixed(1)}%</span>
      </div>
      <div class="fc-explain">${explain}</div>
    </div>
    <div class="fc-chips"><span class="fc-chips-lbl">회귀 입력(현재→최종):</span>${chips}</div>`;
}

// 시간대별 표 기본 탭 — 현재 일차에 맞춰 1회만 설정(이후 자동 새로고침이 사용자 선택을 덮지 않게).
let hourlyDefaultSet = false;
function setDefaultHourlyDay(latest) {
  if (hourlyDefaultSet) return;
  const prog = progressFromLatest(latest);
  if (!prog) return;                 // 데이터 없으면 다음 갱신 때 재시도
  if (prog.day === 2) {              // 2일차면 기본을 오늘(2일차)로
    document.querySelectorAll('.hourly-tab').forEach(b =>
      b.classList.toggle('active', b.dataset.day === '2'));
  }
  hourlyDefaultSet = true;
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
  renderForecast(latest, baseline8, baseline7, baselineGen22, basePres21);
  renderSidoStats(latest, baseline8);
  renderSidoList(latest, baseline8);
  setDefaultHourlyDay(latest);
  renderHourlyTable(ts, baseline8, baseline7, baselineGen22, basePres21);
  bindHourlyTabs(ts, baseline8, baseline7, baselineGen22, basePres21);
  renderTimeline(ts, baseline8, baseline7);
}

main();

// 5분마다 자동 새로고침 — 워크플로우가 30분 간격으로 수집하므로 여유를 두고 다시 fetch.
setInterval(main, 5 * 60 * 1000);
