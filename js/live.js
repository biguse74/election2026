// js/live.js — #live 라우트 독립 모듈.
// js/main.js의 state·route·render에 의존하지 않는다. main.js의 route()가
// 해시가 'live'로 시작하면 window.renderLiveRoute(hash)를 호출한다.

(function () {
  'use strict';

  const POLL_INTERVAL_MS = 60_000;       // 클라이언트 폴링 주기
  const STALE_AFTER_MS = 5 * 60_000;     // 이 시간 이상 미갱신이면 stale 배지

  // 정당 색상. site/data/parties.json도 있지만 라이브 모듈은 의존성 최소화를 위해 자체 보유.
  const PARTY_COLORS = {
    '더불어민주당': '#152484',
    '국민의힘':     '#E61E2B',
    '조국혁신당':   '#06294D',
    '정의당':       '#FFCC00',
    '녹색당':       '#6E9F1A',
    '진보당':       '#D6001C',
    '개혁신당':     '#FF8C00',
    '무소속':       '#888888',
  };
  const partyColor = (name) => PARTY_COLORS[name] || (name ? '#666' : '#888');

  const liveState = {
    current: null,
    meta: null,
    history: null,
    historyLoaded: false,
    timeseries: null,
    pollTimer: null,
    lastPolledAt: null,
    listenersAttached: false,
  };

  // 8회(2022) 데이터는 옛 시도명을 쓴다. 9회 신명칭 → 옛명칭 매핑.
  const SIDO_HISTORY_ALIAS = {
    '강원특별자치도': '강원도',
    '전북특별자치도': '전라북도',
  };

  function fmtTime(iso) {
    if (!iso) return '—';
    const d = new Date(iso);
    if (Number.isNaN(d.getTime())) return iso;
    const yyyy = d.getFullYear();
    const mm = String(d.getMonth() + 1).padStart(2, '0');
    const dd = String(d.getDate()).padStart(2, '0');
    const hh = String(d.getHours()).padStart(2, '0');
    const mi = String(d.getMinutes()).padStart(2, '0');
    return `${yyyy}.${mm}.${dd} ${hh}:${mi}`;
  }
  function fmtPct(v) {
    if (v == null || Number.isNaN(v)) return '—';
    return `${Number(v).toFixed(2)}%`;
  }
  function fmtVotes(v) {
    if (v == null) return '—';
    return `${Number(v).toLocaleString('ko-KR')}표`;
  }
  function escapeHtml(s) {
    return String(s ?? '').replace(/[&<>"']/g, c =>
      ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  }

  function fmtCompare(current, prev) {
    if (current == null || prev == null) return '';
    const diff = Number(current) - Number(prev);
    const sign = diff > 0 ? '+' : (diff < 0 ? '−' : '±');
    return `${Number(prev).toFixed(1)}% · ${sign}${Math.abs(diff).toFixed(1)}%p`;
  }

  function lookupHistoryRate(sdName, history) {
    if (!history) return null;
    const alias = SIDO_HISTORY_ALIAS[sdName] || sdName;
    const entry = history.by_sido[alias];
    return entry ? entry.rate : null;
  }

  async function loadJson(url) {
    try {
      const sep = url.includes('?') ? '&' : '?';
      const r = await fetch(`${url}${sep}t=${Date.now()}`, { cache: 'no-store' });
      if (!r.ok) return null;
      return await r.json();
    } catch {
      return null;
    }
  }

  async function ensureHistory() {
    if (liveState.historyLoaded) return liveState.history;
    liveState.historyLoaded = true;
    const data = await loadJson('data/history_turnout.json');
    if (!data || !Array.isArray(data.elections) || !data.elections.length) {
      liveState.history = null;
      return null;
    }
    // 가장 최근 회차 = 직전 지방선거. by_sido는 시도+시군구 섞여 있어 sunsu 최댓값 = 시도 합계.
    const last = data.elections[data.elections.length - 1];
    const top = {};
    for (const s of last.by_sido || []) {
      const name = s.sdName;
      if (!name) continue;
      if (!top[name] || (s.sunsu || 0) > (top[name].sunsu || 0)) top[name] = s;
    }
    liveState.history = {
      round: last.round,
      year: last.year,
      national: last.total,
      by_sido: top,
    };
    return liveState.history;
  }

  function detectFreshness(polledAtIso) {
    if (!polledAtIso) return { label: '데이터 없음', tone: 'stale' };
    const polled = new Date(polledAtIso).getTime();
    const now = Date.now();
    if (polled > now) return { label: '데모 미리보기', tone: 'demo' };
    const age = now - polled;
    if (age > STALE_AFTER_MS) {
      const mins = Math.floor(age / 60_000);
      return { label: `갱신 지연 (${mins}분 전)`, tone: 'stale' };
    }
    return { label: `${fmtTime(polledAtIso)} 갱신`, tone: 'fresh' };
  }

  function renderLoading() {
    const app = document.getElementById('app');
    if (!app) return;
    app.className = '';
    app.innerHTML = `
      <div class="live-root">
        <h1 class="live-title">실시간 개표</h1>
        <p class="live-empty">불러오는 중…</p>
      </div>`;
  }

  function renderEmpty() {
    const app = document.getElementById('app');
    if (!app) return;
    app.className = '';
    app.innerHTML = `
      <div class="live-root">
        <h1 class="live-title">실시간 개표</h1>
        <p class="live-empty">개표 데이터가 아직 없습니다. 6월 3일 본투표 마감(18시) 이후 갱신됩니다.</p>
      </div>`;
  }

  function renderCandRow(c) {
    const share = c.share_pct == null ? 0 : Math.max(0, Math.min(c.share_pct, 100));
    const color = partyColor(c.jd_name);
    const partyTxt = c.jd_name ? escapeHtml(c.jd_name) : '—';
    return `
      <div class="live-cand">
        <div class="live-cand-rank">${c.current_rank ?? '·'}</div>
        <div class="live-cand-body">
          <div class="live-cand-line1">
            <span class="live-cand-name">${escapeHtml(c.name || '—')}</span>
            <span class="live-cand-party" style="color:${color}">${partyTxt}</span>
          </div>
          <div class="live-cand-bar-wrap">
            <div class="live-cand-bar" style="width:${share}%;background:${color}"></div>
          </div>
          <div class="live-cand-line3">
            <span class="live-cand-votes">${fmtVotes(c.votes)}</span>
            <span class="live-cand-share">${fmtPct(c.share_pct)}</span>
          </div>
        </div>
      </div>`;
  }

  function renderRaceCard(race) {
    const cands = (race.candidates || []).slice(0, 6);
    const region = race.sgg_name
      ? `${escapeHtml(race.sd_name)} · ${escapeHtml(race.sgg_name)}`
      : escapeHtml(race.sd_name || '—');
    const rows = cands.map(renderCandRow).join('') ||
      '<p class="live-empty-mini">후보 데이터 없음</p>';

    const gap = race.rank1_minus_rank2_pp;
    let gapHtml;
    if (gap == null) {
      gapHtml = `<div class="live-gap">단일 후보</div>`;
    } else {
      const cls = gap < 1 ? 'live-gap-tight' : 'live-gap';
      gapHtml = `<div class="${cls}">현재 1·2위 격차 ${Number(gap).toFixed(2)}%p</div>`;
    }

    return `
      <article class="live-race">
        <header class="live-race-head">
          <div class="live-race-region">${region}</div>
          <div class="live-race-progress">개표율 ${fmtPct(race.progress_pct)}</div>
        </header>
        <div class="live-race-cands">${rows}</div>
        ${gapHtml}
      </article>`;
  }

  function renderSection(sgTypeCode, races) {
    const label = escapeHtml((races[0] && races[0].sg_type_label) || sgTypeCode);
    const cards = races.map(renderRaceCard).join('');
    return `
      <section class="live-section">
        <h2 class="live-section-title">${label}<span class="live-section-count">${races.length}개</span></h2>
        <div class="live-grid">${cards}</div>
      </section>`;
  }

  function renderChart(timeseries, history) {
    if (!timeseries || !Array.isArray(timeseries.national) || timeseries.national.length < 2) {
      return '';
    }
    const data = timeseries.national.slice().sort((a, b) =>
      new Date(a.polled_at).getTime() - new Date(b.polled_at).getTime()
    );

    const W = 800, H = 260;
    const padL = 44, padR = 70, padT = 16, padB = 28;
    const innerW = W - padL - padR;
    const innerH = H - padT - padB;

    const startTs = Date.parse('2026-06-03T06:00:00+09:00');
    const endTsBase = Date.parse('2026-06-03T18:00:00+09:00');
    const lastTs = new Date(data[data.length - 1].polled_at).getTime();
    const xEnd = Math.max(endTsBase, lastTs);

    const refRate = history?.national?.rate;
    const dataMax = Math.max(...data.map(d => d.turnout_pct || 0));
    const yMax = Math.max(60, Math.ceil(Math.max(dataMax, refRate || 0) / 10) * 10 + 5);

    const xScale = ts => padL + (ts - startTs) / (xEnd - startTs) * innerW;
    const yScale = v => padT + (1 - v / yMax) * innerH;

    const points = data
      .map(d => `${xScale(new Date(d.polled_at).getTime()).toFixed(1)},${yScale(d.turnout_pct).toFixed(1)}`)
      .join(' ');

    let refLine = '';
    if (refRate != null) {
      const y = yScale(refRate);
      refLine = `
        <line class="chart-ref" x1="${padL}" x2="${padL + innerW}" y1="${y}" y2="${y}" />
        <text class="chart-ref-label" x="${padL + innerW - 4}" y="${y - 5}" text-anchor="end">${history.round}회 최종 ${refRate.toFixed(1)}%</text>`;
    }

    const last = data[data.length - 1];
    const lastX = xScale(new Date(last.polled_at).getTime());
    const lastY = yScale(last.turnout_pct);
    const endAnno = `
      <circle class="chart-dot" cx="${lastX}" cy="${lastY}" r="4.5" />
      <text class="chart-end-label" x="${lastX + 7}" y="${lastY + 4}">${Number(last.turnout_pct).toFixed(2)}%</text>`;

    const hourMarks = [];
    const hourLabels = [];
    [6, 8, 10, 12, 14, 16, 18].forEach(h => {
      const ts = Date.parse(`2026-06-03T${String(h).padStart(2, '0')}:00:00+09:00`);
      if (ts > xEnd + 60_000) return;
      const x = xScale(ts);
      hourMarks.push(`<line class="chart-tick" x1="${x}" x2="${x}" y1="${padT}" y2="${padT + innerH}" />`);
      hourLabels.push(`<text class="chart-axis-label" x="${x}" y="${H - padB + 18}" text-anchor="middle">${h}시</text>`);
    });

    const pctMarks = [];
    const pctLabels = [];
    for (let p = 0; p <= yMax; p += 20) {
      const y = yScale(p);
      pctMarks.push(`<line class="chart-tick" x1="${padL}" x2="${padL + innerW}" y1="${y}" y2="${y}" />`);
      pctLabels.push(`<text class="chart-axis-label" x="${padL - 8}" y="${y + 3}" text-anchor="end">${p}%</text>`);
    }

    return `
      <div class="live-chart-wrap">
        <div class="live-chart-title">투표율 진행 — 전국</div>
        <svg class="live-chart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="전국 투표율 시간대별 진행 차트">
          ${pctMarks.join('')}${hourMarks.join('')}
          ${pctLabels.join('')}${hourLabels.join('')}
          ${refLine}
          <polyline class="chart-line" points="${points}" />
          ${endAnno}
        </svg>
      </div>`;
  }

  function renderTurnoutSection(turnout, history, showCompare, timeseries) {
    if (!turnout) return '';
    const national = turnout.national || {};
    const sido = turnout.by_sido || [];
    const histLabel = history ? `${history.round}회` : '';
    const histNationalRate = history?.national?.rate;

    const nationalCompare = (showCompare && histNationalRate != null && national.turnout_pct != null)
      ? `<span class="live-turnout-national-compare">${histLabel} ${fmtCompare(national.turnout_pct, histNationalRate)}</span>`
      : '';

    const nationalHtml = national.turnout_pct != null ? `
      <div class="live-turnout-national">
        <span class="live-turnout-national-label">전국 투표율</span>
        <span class="live-turnout-national-pct">${Number(national.turnout_pct).toFixed(2)}%</span>
        ${nationalCompare}
        <span class="live-turnout-national-votes">${fmtVotes(national.voters_so_far)} / 선거인 ${Number(national.eligible_voters || 0).toLocaleString('ko-KR')}명</span>
      </div>` : '';

    const chartHtml = renderChart(timeseries, history);

    const cards = sido.map(s => {
      const pct = s.turnout_pct == null ? 0 : Math.max(0, Math.min(s.turnout_pct, 100));
      const prevRate = lookupHistoryRate(s.sd_name, history);
      const compareTxt = (showCompare && prevRate != null && s.turnout_pct != null)
        ? `<div class="live-turnout-compare">${histLabel} ${fmtCompare(s.turnout_pct, prevRate)}</div>`
        : '';
      return `
        <article class="live-turnout-card">
          <div class="live-turnout-region">${escapeHtml(s.sd_name || '—')}</div>
          <div class="live-turnout-bar-wrap"><div class="live-turnout-bar" style="width:${pct}%"></div></div>
          <div class="live-turnout-meta">
            <span class="live-turnout-pct">${fmtPct(s.turnout_pct)}</span>
            <span class="live-turnout-votes">${fmtVotes(s.voters_so_far)}</span>
          </div>
          ${compareTxt}
        </article>`;
    }).join('');

    const countSuffix = (history && showCompare) ? ` · ${histLabel} 비교` : '';
    return `
      <section class="live-section">
        <h2 class="live-section-title">투표율<span class="live-section-count">시도별 ${sido.length}개${countSuffix}</span></h2>
        ${nationalHtml}
        ${chartHtml}
        <div class="live-turnout-grid">${cards}</div>
      </section>`;
  }

  function renderBoard() {
    const app = document.getElementById('app');
    if (!app) return;
    app.className = '';

    const current = liveState.current;
    if (!current || !Array.isArray(current.races)) { renderEmpty(); return; }
    const meta = liveState.meta || {};
    const fresh = detectFreshness(current.polled_at);

    // sg_type_code별로 묶고 표시 우선순위(시도지사 → 교육감 → 기초단체장 → 시도의원 → 구시군의회의원) 적용
    const sgGroups = new Map();
    for (const race of current.races) {
      const k = String(race.sg_type_code);
      if (!sgGroups.has(k)) sgGroups.set(k, []);
      sgGroups.get(k).push(race);
    }
    const ORDER = ['3', '11', '4', '5', '6'];
    const ordered = ORDER.filter(k => sgGroups.has(k))
      .concat([...sgGroups.keys()].filter(k => !ORDER.includes(k)));
    const sectionsHtml = ordered.map(k => renderSection(k, sgGroups.get(k))).join('');
    const turnoutHtml = renderTurnoutSection(current.turnout, liveState.history, current.phase !== 'pre', liveState.timeseries);

    const demoBanner = fresh.tone === 'demo' ? `
        <div class="live-demo-banner" role="alert">
          <strong class="live-demo-banner-title">데모 데이터입니다 — 실제 개표 결과가 아닙니다</strong>
          <span class="live-demo-banner-body">실제 개표 데이터는 2026년 6월 3일 18시 본투표 마감 이후 자동으로 갱신됩니다. 아래 후보 이름·득표수·득표율은 모두 화면 검증용 가짜 값입니다.</span>
        </div>` : '';

    app.innerHTML = `
      <div class="live-root">
        <nav class="breadcrumb"><a href="#">전국</a><span class="sep">›</span><span class="current">실시간 개표</span></nav>
        ${demoBanner}
        <div class="live-hero">
          <h1 class="live-title">실시간 개표</h1>
          <div class="live-hero-meta">
            <span class="live-badge live-badge-${fresh.tone}">${escapeHtml(fresh.label)}</span>
            <span class="live-stat">평균 개표율 ${fmtPct(meta.avg_progress_pct)}</span>
            <span class="live-stat">${meta.races_total ?? current.races.length}개 선거구</span>
          </div>
          <p class="live-disclaimer">예측·전망이 아닌 선관위 개표 데이터 기준 현재 시점 누계입니다.</p>
        </div>
        ${turnoutHtml}
        ${sectionsHtml || '<p class="live-empty">집계된 선거구가 없습니다.</p>'}
      </div>`;
  }

  async function refresh() {
    const [current, meta, timeseries] = await Promise.all([
      loadJson('data/live_counting/current.json'),
      loadJson('data/live_counting/meta.json'),
      loadJson('data/live_counting/timeseries.json'),
    ]);
    if (!current) { renderEmpty(); return; }
    if (current.polled_at === liveState.lastPolledAt) return; // 깜빡임 방지
    liveState.current = current;
    liveState.meta = meta;
    liveState.timeseries = timeseries;
    liveState.lastPolledAt = current.polled_at;
    renderBoard();
  }

  function isLiveHash() {
    const h = decodeURIComponent(location.hash.slice(1));
    return h === 'live' || h.startsWith('live/');
  }

  function startPolling() {
    if (liveState.pollTimer) return;
    refresh();
    liveState.pollTimer = setInterval(refresh, POLL_INTERVAL_MS);
  }
  function stopPolling() {
    if (liveState.pollTimer) { clearInterval(liveState.pollTimer); liveState.pollTimer = null; }
  }

  function attachListenersOnce() {
    if (liveState.listenersAttached) return;
    liveState.listenersAttached = true;
    document.addEventListener('visibilitychange', () => {
      if (document.hidden) stopPolling();
      else if (isLiveHash()) startPolling();
    });
    window.addEventListener('hashchange', () => {
      if (!isLiveHash()) stopPolling();
    });
  }

  function renderLiveRoute(/* hash */) {
    renderLoading();
    attachListenersOnce();
    // 과거 투표율은 한 번만 받아 캐시. 도착하면 라이브 화면을 다시 그려 비교 텍스트 채움.
    ensureHistory().then(() => {
      if (isLiveHash() && liveState.current) renderBoard();
    }).catch(() => {});
    startPolling();
  }

  window.renderLiveRoute = renderLiveRoute;
})();
