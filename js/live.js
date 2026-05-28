// js/live.js — #live 라우트 독립 모듈.
// js/main.js의 state·route·render에 의존하지 않는다. main.js의 route()가
// 해시가 'live'로 시작하면 window.renderLiveRoute(hash)를 호출한다.

(function () {
  'use strict';

  const POLL_INTERVAL_MS = 60_000;       // 클라이언트 자동 새로고침 주기
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
    historyHourly: null,
    historyHourlyLoaded: false,
    timeseries: null,
    exitPoll: null,
    exitPollLoaded: false,
    countingHistory: null,
    countingHistoryLoaded: false,
    pollTimer: null,
    lastPolledAt: null,
    listenersAttached: false,
    expandedSido: new Set(),
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

  // 8회(2022) 시도지사·기초단체장 개표 결과 district 단위 lookup.
  // 라이브 race ↔ history district 매칭 후 후보 카드에 비교 영역 표시.
  async function ensureCountingHistory() {
    if (liveState.countingHistoryLoaded) return liveState.countingHistory;
    liveState.countingHistoryLoaded = true;
    const data = await loadJson('data/history_counting_results.json');
    if (!data || !Array.isArray(data.elections) || !data.elections.length) {
      liveState.countingHistory = null;
      return null;
    }
    const last = data.elections[data.elections.length - 1];
    // 옛 ↔ 신 시도명 양방향 매핑. lookup에 신·옛 두 키 모두 등록해 어느 쪽 입력도 매칭.
    const NEW_TO_OLD = SIDO_HISTORY_ALIAS;          // {신: 옛}
    const OLD_TO_NEW = Object.fromEntries(
      Object.entries(NEW_TO_OLD).map(([n, o]) => [o, n])
    );
    const lookup = new Map();
    for (const res of (last.results || [])) {
      const sgType = String(res.sgTypecode || res.sg_type_code || '');
      for (const dist of (res.districts || [])) {
        const sdRaw = (dist.sdName || dist.sd_name || '').trim();
        const sgg = (dist.sggName || dist.sgg_name || '').trim();
        const sds = new Set([sdRaw]);
        if (OLD_TO_NEW[sdRaw]) sds.add(OLD_TO_NEW[sdRaw]);
        if (NEW_TO_OLD[sdRaw]) sds.add(NEW_TO_OLD[sdRaw]);
        for (const sd of sds) {
          let s = sgg;
          if (s && s === sd) s = '';
          lookup.set([sgType, sd, s].join('|'), dist);
        }
      }
    }
    liveState.countingHistory = {
      round: last.round,
      year: last.year,
      date: last.date,
      _lookup: lookup,
    };
    return liveState.countingHistory;
  }

  function historyForRace(race) {
    const ch = liveState.countingHistory;
    if (!ch) return null;
    const sgType = String(race.sg_type_code || race.sgTypecode || '');
    const sd = (race.sd_name || '').trim();
    let sgg = (race.sgg_name || '').trim();
    if (sgg && sgg === sd) sgg = '';
    return ch._lookup.get([sgType, sd, sgg].join('|')) || null;
  }

  // 시간대별 누계 투표율 (8회 + 7회 지선). history_turnout.json보다 풍부.
  // 시도명은 신표준명(강원특별자치도·전북특별자치도)으로 정규화되어 있어 alias 불필요.
  async function ensureHistoryHourly() {
    if (liveState.historyHourlyLoaded) return liveState.historyHourly;
    liveState.historyHourlyLoaded = true;
    const data = await loadJson('data/history_turnout_hourly.json');
    if (!data || !Array.isArray(data.rounds) || !data.rounds.length) {
      liveState.historyHourly = null;
      return null;
    }
    liveState.historyHourly = data;
    return data;
  }

  // 출구조사 — 6/3 18:00 방송 3사 발표 후 표시. released_at 이전엔 노출 금지(선거법).
  // 최초 1회 fetch만 하고 그 이후엔 시각 게이트만 재평가 → released_at 통과 시점에
  // 페이지 새로고침 없이 자동 노출.
  async function ensureExitPoll() {
    if (!liveState.exitPollLoaded) {
      liveState.exitPollLoaded = true;
      liveState._exitPollRaw = await loadJson('data/exit_poll.json');
    }
    return reevaluateExitPoll();
  }

  // race 매칭 키. 시도지사(sgTypecode=3) 응답은 sggName이 sdName과 같은 값으로 옴 →
  // 공백으로 정규화해 exit_poll의 sgg_name=null과 매칭. 시도 단일 선거 일반화.
  function _raceMatchKey(race) {
    const sgType = String(race.sg_type_code || race.sgTypecode || '');
    const sd = (race.sd_name || '').trim();
    let sgg = (race.sgg_name || '').trim();
    if (sgg && sgg === sd) sgg = '';
    return [sgType, sd, sgg].join('|');
  }

  function reevaluateExitPoll() {
    const data = liveState._exitPollRaw;
    if (!data || !data.released_at) { liveState.exitPoll = null; return null; }
    const t = new Date(data.released_at).getTime();
    if (Number.isNaN(t) || Date.now() < t) { liveState.exitPoll = null; return null; }
    if (liveState.exitPoll && liveState.exitPoll._lookup) return liveState.exitPoll;
    const lookup = new Map();
    for (const r of data.races || []) {
      if (r && !r._example) {
        lookup.set(_raceMatchKey(r), r);
      }
    }
    liveState.exitPoll = { ...data, _lookup: lookup };
    return liveState.exitPoll;
  }

  function exitPollForRace(race) {
    const ep = liveState.exitPoll;
    if (!ep) return null;
    return ep._lookup.get(_raceMatchKey(race)) || null;
  }

  function exitPollEstimateFor(candName, jdName, exitRace) {
    if (!exitRace || !exitRace.candidates) return null;
    const trim = s => String(s || '').trim();
    // 이름+정당 우선, 없으면 이름만, 그래도 없으면 정당만으로 fallback.
    const byNamePartyExact = exitRace.candidates.find(c => trim(c.name) === trim(candName) && trim(c.jd_name) === trim(jdName));
    if (byNamePartyExact) return byNamePartyExact;
    const byName = exitRace.candidates.find(c => trim(c.name) === trim(candName));
    if (byName) return byName;
    const byParty = exitRace.candidates.find(c => trim(c.jd_name) === trim(jdName));
    return byParty || null;
  }

  // 시도명을 시간대별 데이터의 키로 변환 (신이름 그대로 + 옛이름 fallback).
  // earlyFinalPct/Voters는 회차별 사전+거소 최종 누계 — 사전투표율(%)·절대수.
  function hourlyForSido(historyHourly, sdName) {
    if (!historyHourly || !sdName) return [];
    const alias = SIDO_HISTORY_ALIAS[sdName] || sdName;
    return historyHourly.rounds.map(r => {
      const points = r.by_sido[sdName] || r.by_sido[alias] || [];
      const earlyData = (r.early_vote_final && r.early_vote_final.by_sido)
        ? (r.early_vote_final.by_sido[sdName] || r.early_vote_final.by_sido[alias] || null)
        : null;
      return {
        round: r.round,
        year: r.year,
        points,
        earlyFinalPct: earlyData ? earlyData.early_pct : null,
        earlyFinalVoters: earlyData ? earlyData.early_voters : null,
      };
    }).filter(r => r.points.length >= 2);
  }
  function hourlyNational(historyHourly) {
    if (!historyHourly) return [];
    return historyHourly.rounds.map(r => {
      const earlyData = (r.early_vote_final && r.early_vote_final.national) || null;
      return {
        round: r.round,
        year: r.year,
        points: r.national || [],
        earlyFinalPct: earlyData ? earlyData.early_pct : null,
        earlyFinalVoters: earlyData ? earlyData.early_voters : null,
      };
    }).filter(r => r.points.length >= 2);
  }

  // phase + 마지막 수집 시각을 보고 사용자에게 보여줄 상태 메시지 결정.
  // fetch_live_counting.py의 phase: pre / live / official-pending / final
  // 우리는 시각 정보로 'live'를 'voting'(06~17:55)과 'counting'(18:00~)으로 더 쪼갠다.
  function describePhase(phase, polledAtIso) {
    const polled = polledAtIso ? new Date(polledAtIso).getTime() : Date.now();
    const tElectionStart = Date.parse('2026-06-03T06:00:00+09:00');
    const tCountingStart = Date.parse('2026-06-03T18:00:00+09:00');
    const tNextDay06     = Date.parse('2026-06-04T06:00:00+09:00');

    if (phase === 'final') {
      return { tone: 'final', title: '최종 결과', body: '선관위 OpenAPI 정식 개표 결과입니다.' };
    }
    if (phase === 'pre' || polled < tElectionStart) {
      return { tone: 'pre', title: '투표 시작 전',
        body: '6월 3일 오전 6시 본투표 시작 후 투표율이 자동 갱신됩니다. 개표는 오후 6시부터.' };
    }
    if (polled < tCountingStart) {
      return { tone: 'voting', title: '본투표 진행 중',
        body: '시간대별 투표율을 5분마다 갱신합니다. 개표는 오후 6시 본투표 마감 직후 시작.' };
    }
    if (phase === 'official-pending') {
      if (polled > tNextDay06) {
        return { tone: 'pending', title: '개표 진행 중 · 정식 결과 대기',
          body: '선관위 OpenAPI 정식 결과를 30분 간격으로 자동 확인하고 있습니다.' };
      }
      return { tone: 'pending', title: '개표 데이터 수신 대기',
        body: '오후 6시 본투표 마감 직후 첫 개표 응답이 들어옵니다.' };
    }
    // phase === 'live' & 18시 이후
    return { tone: 'live', title: '개표 진행 중',
      body: '평균 개표율과 후보별 누적 득표를 5~10분마다 갱신합니다.' };
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

  function renderCandRow(c, exitRace) {
    const share = c.share_pct == null ? 0 : Math.max(0, Math.min(c.share_pct, 100));
    const color = partyColor(c.jd_name);
    const partyTxt = c.jd_name ? escapeHtml(c.jd_name) : '—';

    // 출구조사 추정치 — 매칭되면 후보 막대 위에 작은 표식.
    let exitOverlay = '';
    let exitLine = '';
    const est = exitPollEstimateFor(c.name, c.jd_name, exitRace);
    if (est && est.estimate_pct != null) {
      const ePct = Math.max(0, Math.min(Number(est.estimate_pct), 100));
      exitOverlay = `<div class="live-cand-exit-marker" style="left:${ePct}%;border-color:${color}" title="출구조사 ${ePct}%"></div>`;
      const range = (est.low != null && est.high != null)
        ? ` <span class="live-cand-exit-range">[${Number(est.low).toFixed(1)}~${Number(est.high).toFixed(1)}]</span>`
        : '';
      exitLine = `<div class="live-cand-exit-line">출구조사 <strong>${ePct.toFixed(1)}%</strong>${range}</div>`;
    }

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
            ${exitOverlay}
          </div>
          <div class="live-cand-line3">
            <span class="live-cand-votes">${fmtVotes(c.votes)}</span>
            <span class="live-cand-share">${fmtPct(c.share_pct)}</span>
          </div>
          ${exitLine}
        </div>
      </div>`;
  }

  function renderRaceCard(race) {
    const cands = (race.candidates || []).slice(0, 6);
    const region = race.sgg_name
      ? `${escapeHtml(race.sd_name)} · ${escapeHtml(race.sgg_name)}`
      : escapeHtml(race.sd_name || '—');
    const exitRace = exitPollForRace(race);
    const rows = cands.map(c => renderCandRow(c, exitRace)).join('') ||
      '<p class="live-empty-mini">후보 데이터 없음</p>';

    const gap = race.rank1_minus_rank2_pp;
    let gapHtml;
    if (gap == null) {
      gapHtml = `<div class="live-gap">단일 후보</div>`;
    } else {
      const cls = gap < 1 ? 'live-gap-tight' : 'live-gap';
      gapHtml = `<div class="${cls}">현재 1·2위 격차 ${Number(gap).toFixed(2)}%p</div>`;
    }

    const exitBadge = exitRace
      ? '<span class="live-race-exit-badge" title="이 선거구 출구조사 표시 중">출구조사</span>'
      : '';

    const historyFooter = renderHistoryFooter(race);

    return `
      <article class="live-race${exitRace ? ' has-exit' : ''}">
        <header class="live-race-head">
          <div class="live-race-region">${region}${exitBadge}</div>
          <div class="live-race-progress">개표율 ${fmtPct(race.progress_pct)}</div>
        </header>
        <div class="live-race-cands">${rows}</div>
        ${gapHtml}
        ${historyFooter}
      </article>`;
  }

  // 라이브 race 카드 하단 '8회 당선' 한 줄 — 당선자·정당색·득표율·1·2위 격차·정권 유지/탈환 추세.
  function renderHistoryFooter(race) {
    const dist = historyForRace(race);
    if (!dist || !dist.winner) return '';
    const w = dist.winner;
    const ch = liveState.countingHistory;
    const round = ch ? ch.round : 8;
    const color = partyColor(w.party);

    // 1·2위 격차 계산 (history candidates에서)
    let gapTxt = '';
    const sorted = (dist.candidates || []).slice().filter(c => c.vote_share != null);
    sorted.sort((a, b) => (b.vote_share || 0) - (a.vote_share || 0));
    if (sorted.length >= 2) {
      const diff = (sorted[0].vote_share - sorted[1].vote_share);
      gapTxt = `격차 ${diff.toFixed(1)}%p`;
    }

    // 현 라이브 1위 정당과 비교 — 개표 10% 이상 진행됐을 때만 추세 표시 (조기 단정 방지)
    let regime = '';
    const liveTop = (race.candidates || [])[0];
    if (liveTop && liveTop.jd_name && race.progress_pct != null && race.progress_pct >= 10) {
      regime = (liveTop.jd_name === w.party)
        ? `<span class="live-race-history-regime regime-hold">정당 유지 추세</span>`
        : `<span class="live-race-history-regime regime-flip">${escapeHtml(liveTop.jd_name)} 탈환 추세</span>`;
    }

    const pct = w.vote_share != null ? `${Number(w.vote_share).toFixed(1)}%` : '';
    const gapHtml = gapTxt ? `<span class="live-race-history-gap">${gapTxt}</span>` : '';

    return `
      <div class="live-race-history" title="${round}회 (${ch?.year ?? ''}) 개표 결과">
        <span class="live-race-history-label">${round}회 당선</span>
        <span class="live-race-history-dot" style="background:${color}"></span>
        <span class="live-race-history-name">${escapeHtml(w.name || '—')}</span>
        <span class="live-race-history-party" style="color:${color}">${escapeHtml(w.party || '')}</span>
        <span class="live-race-history-pct">${pct}</span>
        ${gapHtml}
        ${regime}
      </div>`;
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

  // 시간대별 회차 시리즈를 9회 X축 timestamp로 매핑해 polyline points 문자열로.
  function historyPolylinePoints(points, xScale, yScale) {
    return points.map(p => {
      const [hh, mm] = p.time.split(':').map(Number);
      const ts = Date.parse(`2026-06-03T${String(hh).padStart(2,'0')}:${String(mm).padStart(2,'0')}:00+09:00`);
      return `${xScale(ts).toFixed(1)},${yScale(p.turnout_pct).toFixed(1)}`;
    }).join(' ');
  }

  // 12시→13시 점프 = 사전투표 합산 효과. 데이터 부족하면 null.
  function historyEarlyVoteJump(points) {
    if (!points) return null;
    const before = points.find(p => p.time === '12:00');
    const after  = points.find(p => p.time === '13:00');
    if (!before || !after) return null;
    return {
      before: before.turnout_pct,
      after:  after.turnout_pct,
      diff:   Math.round((after.turnout_pct - before.turnout_pct) * 10) / 10,
    };
  }
  function liveEarlyVoteJump(series) {
    if (!series || series.length < 2) return null;
    const cutoff = Date.parse('2026-06-03T13:00:00+09:00');
    const before = series.filter(p => new Date(p.polled_at).getTime() < cutoff).slice(-1)[0];
    const after  = series.find(p => new Date(p.polled_at).getTime() >= cutoff);
    if (!before || !after) return null;
    return {
      before: before.turnout_pct,
      after:  after.turnout_pct,
      diff:   Math.round((after.turnout_pct - before.turnout_pct) * 10) / 10,
    };
  }

  // 라이브 시계열 + 8회/7회 시간대별 점선을 한 차트에. variant: 'national' | 'sido'
  function renderChart(opts) {
    const {
      live = [],
      historyHourlySeries = [],   // [{round, year, points: [...], earlyFinalPct, earlyFinalVoters}]
      title,
      variant = 'national',
      ariaLabel,
      liveEarlyRate = null,        // 9회 라이브 사전+거소 비율 (%) — 데이터 들어왔을 때만
    } = opts;

    const liveSorted = (live || []).slice().sort((a, b) =>
      new Date(a.polled_at).getTime() - new Date(b.polled_at).getTime()
    );
    const histSeries = (historyHourlySeries || []).filter(h => h.points && h.points.length >= 2);

    if (liveSorted.length < 2 && !histSeries.length) return '';

    const isMini = variant === 'sido';
    const W = isMini ? 520 : 800;
    const H = isMini ? 180 : 260;
    const padL = isMini ? 36 : 44;
    const padR = isMini ? 18 : 70;
    const padT = isMini ? 12 : 16;
    const padB = isMini ? 24 : 28;
    const innerW = W - padL - padR;
    const innerH = H - padT - padB;

    const startTs = Date.parse('2026-06-03T06:00:00+09:00');
    const endTsBase = Date.parse('2026-06-03T20:00:00+09:00'); // 8회 19:30까지 보이게 확장
    const lastLiveTs = liveSorted.length
      ? new Date(liveSorted[liveSorted.length - 1].polled_at).getTime()
      : startTs;
    const xEnd = Math.max(endTsBase, lastLiveTs);

    const allMax = Math.max(
      ...liveSorted.map(d => d.turnout_pct || 0),
      ...histSeries.flatMap(h => h.points.map(p => p.turnout_pct || 0)),
      40,
    );
    const yMax = Math.ceil(allMax / 10) * 10 + 5;

    const xScale = ts => padL + (ts - startTs) / (xEnd - startTs) * innerW;
    const yScale = v => padT + (1 - v / yMax) * innerH;

    // 회차별 점선 스타일: 8회는 진한 회색, 7회는 더 옅게.
    const HIST_CLASS = { 8: 'chart-line-hist-8', 7: 'chart-line-hist-7' };
    const historyPolys = histSeries.map(h => {
      const pts = historyPolylinePoints(h.points, xScale, yScale);
      const cls = HIST_CLASS[h.round] || 'chart-line-hist-other';
      return `<polyline class="chart-line-hist ${cls}" points="${pts}" />
        <title>${h.round}회 (${h.year}) 시간대별</title>`;
    }).join('');

    // 라이브 polyline + 끝점 도트·라벨
    let livePoly = '';
    let endAnno = '';
    if (liveSorted.length >= 2) {
      const points = liveSorted
        .map(d => `${xScale(new Date(d.polled_at).getTime()).toFixed(1)},${yScale(d.turnout_pct).toFixed(1)}`)
        .join(' ');
      livePoly = `<polyline class="chart-line" points="${points}" />`;
      const last = liveSorted[liveSorted.length - 1];
      const lastX = xScale(new Date(last.polled_at).getTime());
      const lastY = yScale(last.turnout_pct);
      endAnno = `
        <circle class="chart-dot" cx="${lastX}" cy="${lastY}" r="${isMini ? 3.5 : 4.5}" />
        <text class="chart-end-label" x="${lastX + 6}" y="${lastY + 4}">${Number(last.turnout_pct).toFixed(2)}%</text>`;
    }

    // 축 눈금
    const hourMarks = [];
    const hourLabels = [];
    const xTicks = isMini ? [6, 9, 12, 15, 18] : [6, 8, 10, 12, 14, 16, 18];
    xTicks.forEach(h => {
      const ts = Date.parse(`2026-06-03T${String(h).padStart(2, '0')}:00:00+09:00`);
      if (ts > xEnd + 60_000) return;
      const x = xScale(ts);
      hourMarks.push(`<line class="chart-tick" x1="${x}" x2="${x}" y1="${padT}" y2="${padT + innerH}" />`);
      hourLabels.push(`<text class="chart-axis-label" x="${x}" y="${H - padB + 16}" text-anchor="middle">${h}시</text>`);
    });

    // 13시 강조선 — 사전투표 합산 시점
    const ts13 = Date.parse('2026-06-03T13:00:00+09:00');
    const x13 = xScale(ts13);
    const earlyVoteMark = `
      <line class="chart-early-vote-line" x1="${x13}" x2="${x13}" y1="${padT}" y2="${padT + innerH}" />
      ${isMini ? '' : `<text class="chart-early-vote-label" x="${x13 + 4}" y="${padT + 10}">13시 — 사전투표 합산</text>`}
    `;

    const pctMarks = [];
    const pctLabels = [];
    const pctStep = isMini ? 20 : 20;
    for (let p = 0; p <= yMax; p += pctStep) {
      const y = yScale(p);
      pctMarks.push(`<line class="chart-tick" x1="${padL}" x2="${padL + innerW}" y1="${y}" y2="${y}" />`);
      pctLabels.push(`<text class="chart-axis-label" x="${padL - 6}" y="${y + 3}" text-anchor="end">${p}%</text>`);
    }

    // 범례 (메인 차트에만)
    let legend = '';
    if (!isMini) {
      const items = [];
      if (liveSorted.length >= 2) {
        items.push('<span class="chart-legend-item"><span class="chart-legend-swatch chart-legend-swatch-live"></span>9회 라이브</span>');
      }
      histSeries.forEach(h => {
        items.push(`<span class="chart-legend-item"><span class="chart-legend-swatch chart-legend-swatch-${h.round}"></span>${h.round}회 (${h.year})</span>`);
      });
      if (items.length) {
        legend = `<div class="live-chart-legend">${items.join('')}</div>`;
      }
    }

    // 사전투표 비교 — 회차별: ① 12→13시 점프량(시간대 효과), ② 최종 사전투표율(절대 비중)
    const earlyVoteRows = [];
    const liveJump = liveEarlyVoteJump(liveSorted);
    if (liveJump || liveEarlyRate != null) {
      earlyVoteRows.push({
        label: '9회 라이브',
        diff: liveJump ? liveJump.diff : null,
        finalPct: liveEarlyRate,
        cls: 'early-vote-live',
      });
    }
    histSeries.forEach(h => {
      const j = historyEarlyVoteJump(h.points);
      earlyVoteRows.push({
        label: `${h.round}회 (${h.year})`,
        diff: j ? j.diff : null,
        finalPct: h.earlyFinalPct != null ? h.earlyFinalPct : null,
        cls: `early-vote-${h.round}`,
      });
    });
    const hasAnyEarly = earlyVoteRows.some(r => r.diff != null || r.finalPct != null);

    let earlyVoteBox = '';
    if (hasAnyEarly && !isMini) {
      const fmtCol = v => v == null ? '<span class="early-vote-na">—</span>' : `<strong>${v.toFixed(1)}%${v ? (v < 5 ? 'p' : '') : 'p'}</strong>`;
      // diff는 +%p, finalPct는 % — 별도 포매팅
      const rows = earlyVoteRows.map(r => {
        const diffTxt = r.diff == null
          ? '<span class="early-vote-na">—</span>'
          : `<strong class="early-vote-diff">+${r.diff.toFixed(1)}%p</strong>`;
        const finalTxt = r.finalPct == null
          ? '<span class="early-vote-na">—</span>'
          : `<strong class="early-vote-final-pct">${r.finalPct.toFixed(2)}%</strong>`;
        return `<div class="early-vote-row">
          <span class="early-vote-dot ${r.cls}"></span>
          <span class="early-vote-label">${r.label}</span>
          <span class="early-vote-col" data-label="12→13시 점프">${diffTxt}</span>
          <span class="early-vote-col" data-label="사전+거소 최종">${finalTxt}</span>
        </div>`;
      }).join('');
      earlyVoteBox = `
        <div class="early-vote-box">
          <div class="early-vote-title">사전투표 비교</div>
          <div class="early-vote-header">
            <span class="early-vote-label"></span>
            <span class="early-vote-col">12→13시 점프</span>
            <span class="early-vote-col">사전+거소 최종</span>
          </div>
          ${rows}
        </div>`;
    } else if (hasAnyEarly && isMini) {
      const parts = earlyVoteRows.filter(r => r.finalPct != null || r.diff != null).map(r => {
        const a = r.diff != null ? `+${r.diff.toFixed(1)}%p` : '—';
        const b = r.finalPct != null ? `사전 ${r.finalPct.toFixed(1)}%` : '';
        return `<span class="${r.cls}-text">${r.label} ${a}${b ? ' / ' + b : ''}</span>`;
      }).join(' · ');
      earlyVoteBox = `<div class="early-vote-mini">사전투표 ${parts}</div>`;
    }

    const titleHtml = title ? `<div class="live-chart-title">${escapeHtml(title)}</div>` : '';
    return `
      <div class="live-chart-wrap${isMini ? ' live-chart-wrap-mini' : ''}">
        ${titleHtml}
        <svg class="live-chart" viewBox="0 0 ${W} ${H}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="${escapeHtml(ariaLabel || title || '투표율 차트')}">
          ${pctMarks.join('')}${hourMarks.join('')}
          ${pctLabels.join('')}${hourLabels.join('')}
          ${earlyVoteMark}
          ${historyPolys}
          ${livePoly}
          ${endAnno}
        </svg>
        ${legend}
        ${earlyVoteBox}
      </div>`;
  }

  function renderTurnoutSection(turnout, history, showCompare, timeseries, historyHourly) {
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

    const nationalChart = renderChart({
      live: timeseries?.national || [],
      historyHourlySeries: hourlyNational(historyHourly),
      title: '투표율 진행 — 전국',
      variant: 'national',
      ariaLabel: '전국 투표율 시간대별 진행 차트 (9회 라이브 + 8회 + 7회 점선 비교)',
      liveEarlyRate: national.early_vote_rate_pct ?? null,
    });

    const cards = sido.map(s => {
      const sdName = s.sd_name || '';
      const pct = s.turnout_pct == null ? 0 : Math.max(0, Math.min(s.turnout_pct, 100));
      const prevRate = lookupHistoryRate(sdName, history);
      const compareTxt = (showCompare && prevRate != null && s.turnout_pct != null)
        ? `<div class="live-turnout-compare">${histLabel} ${fmtCompare(s.turnout_pct, prevRate)}</div>`
        : '';
      const isExpanded = liveState.expandedSido.has(sdName);
      const histSeries = hourlyForSido(historyHourly, sdName);
      const liveSidoSeries = (timeseries && timeseries.by_sido && timeseries.by_sido[sdName]) || [];
      const canExpand = histSeries.length > 0 || liveSidoSeries.length >= 2;
      const expandIcon = isExpanded ? '▾' : '▸';

      let expandedHtml = '';
      if (isExpanded && canExpand) {
        const miniChart = renderChart({
          live: liveSidoSeries,
          historyHourlySeries: histSeries,
          title: '',
          variant: 'sido',
          ariaLabel: `${sdName} 시간대별 투표율 비교 차트`,
          liveEarlyRate: s.early_vote_rate_pct ?? null,
        });
        expandedHtml = `<div class="live-turnout-expanded">${miniChart || '<p class="live-empty-mini">차트를 그릴 데이터가 부족합니다.</p>'}</div>`;
      }

      const clsExpand = canExpand ? ' is-expandable' : '';
      const clsOpen = isExpanded ? ' is-open' : '';
      const ariaExpanded = canExpand ? `aria-expanded="${isExpanded ? 'true' : 'false'}"` : '';
      const dataAttr = canExpand ? `data-sido="${escapeHtml(sdName)}"` : '';
      const role = canExpand ? 'role="button" tabindex="0"' : '';

      return `
        <article class="live-turnout-card${clsExpand}${clsOpen}" ${dataAttr} ${role} ${ariaExpanded}>
          <div class="live-turnout-region">
            <span>${escapeHtml(sdName || '—')}</span>
            ${canExpand ? `<span class="live-turnout-expand-icon" aria-hidden="true">${expandIcon}</span>` : ''}
          </div>
          <div class="live-turnout-bar-wrap"><div class="live-turnout-bar" style="width:${pct}%"></div></div>
          <div class="live-turnout-meta">
            <span class="live-turnout-pct">${fmtPct(s.turnout_pct)}</span>
            <span class="live-turnout-votes">${fmtVotes(s.voters_so_far)}</span>
          </div>
          ${compareTxt}
          ${expandedHtml}
        </article>`;
    }).join('');

    const countSuffix = (history && showCompare) ? ` · ${histLabel} 비교` : '';
    const expandHint = historyHourly ? `<p class="live-turnout-hint">시도 카드를 누르면 그 시도의 시간대별 8회·7회 비교 차트가 펼쳐집니다.</p>` : '';
    return `
      <section class="live-section">
        <h2 class="live-section-title">투표율<span class="live-section-count">시도별 ${sido.length}개${countSuffix}</span></h2>
        ${nationalHtml}
        ${nationalChart}
        ${expandHint}
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
    const turnoutHtml = renderTurnoutSection(
      current.turnout,
      liveState.history,
      current.phase !== 'pre',
      liveState.timeseries,
      liveState.historyHourly,
    );

    const demoBanner = fresh.tone === 'demo' ? `
        <div class="live-demo-banner" role="alert">
          <strong class="live-demo-banner-title">데모 데이터입니다 — 실제 개표 결과가 아닙니다</strong>
          <span class="live-demo-banner-body">실제 개표 데이터는 2026년 6월 3일 18시 본투표 마감 이후 자동으로 갱신됩니다. 아래 후보 이름·득표수·득표율은 모두 화면 검증용 가짜 값입니다.</span>
        </div>` : '';

    const phaseInfo = describePhase(current.phase, current.polled_at);
    const phaseBanner = `
        <div class="live-phase-banner live-phase-${phaseInfo.tone}" role="status">
          <strong class="live-phase-title">${escapeHtml(phaseInfo.title)}</strong>
          <span class="live-phase-body">${escapeHtml(phaseInfo.body)}</span>
        </div>`;

    // 시뮬 페이지는 여론조사·예측조사가 아닌 패턴 자료이므로 상시 노출.
    const simLinkBox = `
        <a class="live-sim-link" href="/sim/" target="_blank" rel="noopener">
          <span class="live-sim-link-icon">🎲</span>
          <span class="live-sim-link-body">
            <strong>의석 시뮬레이션 (과거 6회차 기반)</strong>
            <span>몬테카를로 1만 회 — 시도지사 17·기초단체장 226 · 단정 예측 아님</span>
          </span>
          <span class="live-sim-link-arrow">→</span>
        </a>`;

    // 출구조사 면책 박스 (출구조사 데이터가 로드되어 있을 때만)
    let exitNotice = '';
    const ep = liveState.exitPoll;
    if (ep && ep._lookup && ep._lookup.size) {
      exitNotice = `
        <div class="live-exit-notice" role="note">
          <strong class="live-exit-notice-title">📊 출구조사 표시 중 — ${escapeHtml(ep.source || '방송 3사 컨소시엄')}</strong>
          <span class="live-exit-notice-body">${escapeHtml(ep.note || '추정치이며 실제 개표 결과와 다를 수 있습니다.')} 각 후보 막대 위 표식은 출구조사 추정 득표율입니다.</span>
        </div>`;
    }

    // 개표 카드(sectionsHtml)는 18시 이전 또는 개표 데이터 없는 경우 phase별 안내로 대체.
    let countingArea;
    if (sectionsHtml && current.races && current.races.length) {
      countingArea = sectionsHtml;
    } else if (phaseInfo.tone === 'pre' || phaseInfo.tone === 'voting') {
      countingArea = `
        <section class="live-section">
          <h2 class="live-section-title">개표 결과<span class="live-section-count">대기 중</span></h2>
          <p class="live-empty">${phaseInfo.tone === 'pre'
            ? '6월 3일 오후 6시 본투표 마감 후 개표가 시작됩니다.'
            : '본투표 마감(오후 6시) 직후 첫 개표 데이터가 들어오면 자동으로 표시됩니다.'}</p>
        </section>`;
    } else {
      countingArea = `
        <section class="live-section">
          <h2 class="live-section-title">개표 결과<span class="live-section-count">대기 중</span></h2>
          <p class="live-empty">${escapeHtml(phaseInfo.body)}</p>
        </section>`;
    }

    app.innerHTML = `
      <div class="live-root">
        <nav class="breadcrumb"><a href="#">전국</a><span class="sep">›</span><span class="current">실시간 개표</span></nav>
        ${demoBanner}
        ${phaseBanner}
        ${exitNotice}
        ${simLinkBox}
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
        ${countingArea}
      </div>`;
  }

  async function refresh() {
    const [current, meta, timeseries] = await Promise.all([
      loadJson('data/live_counting/current.json'),
      loadJson('data/live_counting/meta.json'),
      loadJson('data/live_counting/timeseries.json'),
    ]);
    if (!current) { renderEmpty(); return; }
    // 출구조사 시각 게이트 재평가 (released_at 통과 시점 자동 노출)
    reevaluateExitPoll();
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

  function toggleSido(sdName) {
    if (!sdName) return;
    if (liveState.expandedSido.has(sdName)) {
      liveState.expandedSido.delete(sdName);
    } else {
      liveState.expandedSido.add(sdName);
    }
    if (liveState.current) renderBoard();
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
    // 시도 카드 클릭/키보드로 펼침 토글. 라이브 화면일 때만 반응.
    document.addEventListener('click', (e) => {
      if (!isLiveHash()) return;
      const card = e.target.closest && e.target.closest('.live-turnout-card.is-expandable');
      if (!card) return;
      toggleSido(card.getAttribute('data-sido'));
    });
    document.addEventListener('keydown', (e) => {
      if (!isLiveHash()) return;
      if (e.key !== 'Enter' && e.key !== ' ') return;
      const card = e.target.closest && e.target.closest('.live-turnout-card.is-expandable');
      if (!card) return;
      e.preventDefault();
      toggleSido(card.getAttribute('data-sido'));
    });
  }

  function renderLiveRoute(/* hash */) {
    renderLoading();
    attachListenersOnce();
    // 과거 투표율 + 시간대별 + 출구조사를 병렬로 받고, 도착하면 화면 재렌더.
    Promise.all([ensureHistory(), ensureHistoryHourly(), ensureExitPoll(), ensureCountingHistory()]).then(() => {
      if (isLiveHash() && liveState.current) renderBoard();
    }).catch(() => {});
    startPolling();
  }

  window.renderLiveRoute = renderLiveRoute;
})();
