#!/usr/bin/env python3
"""
9회 시도지사 의석 분포 몬테카를로 시뮬레이션.

모델 (계층 분해):
    margin_{i,t} = year_effect_t + region_lean_i + noise_{i,t}

  · margin   = 민주 진영 득표율 - 국힘 진영 득표율 (단위 %p)
  · year_effect = 회차별 전국 평균 margin (시대 분위기)
  · region_lean = 시도가 전국 평균보다 얼마나 진보 쪽으로 치우쳤나
  · noise       = 시도·회차별 잔차 (외부 충격·후보 효과)

시뮬레이션 1회:
  1) 9회 year_effect를 과거 6회 year_effect 분포에서 sampling
  2) 17개 시도 각각:
       region_lean_i  ~ Normal(평균_i, SD_i)
       noise          ~ Normal(0, SD_global_residual)
       margin_i = year_effect + region_lean_i + noise
  3) margin > 0 → 민주, < 0 → 국힘

검증:
  - Leave-one-out: 한 회차 빼고 학습 → 그 회차 예측 → 적중률
  - 특히 8회(2022) 적중률을 강조

출력:
  exports/simulation_9th_sido/
    summary.json          — 의석 분포·기댓값·신뢰구간·백테스트
    sido_marginal.csv     — 시도별 민주 승리 확률
    seat_distribution.csv — 의석 수별 확률 (민주·국힘)
    raw_simulations.csv   — 1만 회 결과 (시도별 winner camp)

선거법 주의:
  · 6/3 18시 투표마감 전까지 결과 공표·인용보도 금지 (공직선거법 108조)
  · 6/3 18:00 KST 이후에만 공개할 것
"""

from __future__ import annotations

import csv
import json
import os
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "exports" / "simulation_9th_sido"
N_SIM = 10_000
SEED = 42

PROGRESSIVE = {
    "민주당", "새천년민주당", "열린우리당", "대통합민주신당",
    "통합민주당", "민주통합당", "새정치민주연합", "더불어민주당",
}
CONSERVATIVE = {
    "한나라당", "새누리당", "자유한국당", "바른정당", "미래통합당", "국민의힘",
}

# 시도명 정규화 (옛 ↔ 신, 제주 일관)
ALIASES = {
    "강원도": "강원특별자치도",
    "전라북도": "전북특별자치도",
    "제주도": "제주특별자치도",
}


def normalize_sido(name: str) -> str:
    return ALIASES.get(name, name)


def load_history() -> dict:
    """history_counting_results.json에서 시도지사 6회 양당 margin 매트릭스 추출.
    반환: {sido: {round: margin_pp, ...}, ...}, year_of_round
    """
    d = json.load((ROOT / "data" / "history_counting_results.json").open(encoding="utf-8"))
    sido_margin: dict[str, dict[int, float]] = defaultdict(dict)
    year_of: dict[int, int] = {}
    for elec in d["elections"]:
        rd = int(elec["round"])
        year_of[rd] = int(elec["year"])
        chief = next((r for r in elec["results"] if r["sgTypecode"] == "3"), None)
        if not chief:
            continue
        for dist in chief["districts"]:
            sido = normalize_sido(dist["sdName"])
            cands = dist.get("candidates") or []
            dem = sum(c.get("vote_share", 0) or 0 for c in cands if c.get("party") in PROGRESSIVE)
            con = sum(c.get("vote_share", 0) or 0 for c in cands if c.get("party") in CONSERVATIVE)
            sido_margin[sido][rd] = round(dem - con, 3)
    return dict(sido_margin), year_of


def decompose(margin: dict[str, dict[int, float]]) -> dict:
    """3단계 분해: year_effect, region_lean, residual.
    반환: {year_effect: {r: v}, region_mean: {s: v}, region_sd: {s: v}, residual_sd: float}
    """
    rounds = sorted({r for v in margin.values() for r in v.keys()})
    sidos = sorted(margin.keys())

    # year_effect = 그 회차 모든 시도 margin의 평균
    year_effect = {}
    for r in rounds:
        vals = [margin[s][r] for s in sidos if r in margin[s]]
        year_effect[r] = round(statistics.mean(vals), 3)

    # region_lean: 시도별 (margin - year_effect)의 회차 평균
    region_lean: dict[str, list[float]] = defaultdict(list)
    for s in sidos:
        for r, m in margin[s].items():
            region_lean[s].append(m - year_effect[r])

    region_mean = {s: round(statistics.mean(v), 3) for s, v in region_lean.items()}
    region_sd = {s: round(statistics.stdev(v), 3) if len(v) >= 2 else 0.0 for s, v in region_lean.items()}

    # residual (시도·회차 노이즈) — 시도별 (lean 평균에서의 편차)의 표준편차
    residuals = []
    for s, lst in region_lean.items():
        mean_s = statistics.mean(lst)
        for v in lst:
            residuals.append(v - mean_s)
    residual_sd = round(statistics.pstdev(residuals), 3) if residuals else 0.0

    return {
        "year_effect": year_effect,
        "region_mean": region_mean,
        "region_sd": region_sd,
        "residual_sd": residual_sd,
        "rounds": rounds,
        "sidos": sidos,
    }


def simulate_once(params: dict, year_effect_sampler, rng: random.Random) -> dict[str, int]:
    """1회 시뮬레이션. 시도별 winner camp ('D' or 'R') 반환."""
    ye = year_effect_sampler(rng)
    out = {}
    for s in params["sidos"]:
        rm = params["region_mean"][s]
        rs = params["region_sd"][s]
        lean = rng.gauss(rm, max(rs, 1e-6))
        noise = rng.gauss(0, max(params["residual_sd"], 1e-6))
        margin = ye + lean + noise
        out[s] = "D" if margin > 0 else "R"
    return out


def make_year_effect_sampler(params: dict, mode: str):
    """시나리오별 year_effect sampling 전략.
       baseline: 6회 전체에서 복원 추출
       normal  : 8회 직후 같은 보수 약세 환경 — 5·6·8회 평균±SD
       shakeup : 7회 같은 정권심판 환경 — 7회 값±전체 SD
    """
    ye = params["year_effect"]
    all_vals = list(ye.values())
    if mode == "baseline":
        return lambda rng: rng.choice(all_vals)
    if mode == "normal":
        # 격변기(7회) 제외 평균과 표준편차
        no_shake = [v for r, v in ye.items() if r != 7]
        mean = statistics.mean(no_shake)
        sd = statistics.stdev(no_shake) if len(no_shake) >= 2 else 5.0
        return lambda rng: rng.gauss(mean, sd)
    if mode == "shakeup":
        # 7회 평균을 중심으로 전체 SD
        center = ye.get(7, 30.0)
        sd = statistics.stdev(all_vals)
        return lambda rng: rng.gauss(center, sd)
    raise ValueError(mode)


def run_simulation(params: dict, n: int, seed: int, mode: str = "baseline") -> dict:
    rng = random.Random(seed)
    sampler = make_year_effect_sampler(params, mode)

    # 결과 누적
    sido_dem_wins = Counter()       # sido -> 민주 승리 count
    seat_dist_dem = Counter()        # 민주 의석 수 -> count
    seat_dist_con = Counter()
    raw: list[dict[str, str]] = []   # 1만 회 시도별 winner

    for i in range(n):
        winners = simulate_once(params, sampler, rng)
        d_seats = sum(1 for v in winners.values() if v == "D")
        r_seats = sum(1 for v in winners.values() if v == "R")
        seat_dist_dem[d_seats] += 1
        seat_dist_con[r_seats] += 1
        for s, v in winners.items():
            if v == "D":
                sido_dem_wins[s] += 1
        raw.append(winners)

    return {
        "n": n,
        "sido_dem_wins": dict(sido_dem_wins),
        "seat_dist_dem": dict(seat_dist_dem),
        "seat_dist_con": dict(seat_dist_con),
        "raw": raw,
    }


def credibility_interval(counter: dict[int, int], n: int, lo: float, hi: float) -> tuple[int, int]:
    """누적 분포에서 lo~hi percentile 의석 수."""
    items = sorted(counter.items())
    cum = 0
    lo_seat = hi_seat = items[0][0]
    target_lo = n * lo
    target_hi = n * hi
    found_lo = False
    for seat, c in items:
        cum += c
        if not found_lo and cum >= target_lo:
            lo_seat = seat
            found_lo = True
        if cum >= target_hi:
            hi_seat = seat
            break
    return lo_seat, hi_seat


def backtest(margin: dict, target_round: int) -> dict:
    """target_round를 제외한 회차로 학습 → target_round의 17개 시도 예측 → 실제와 비교."""
    train_margin = {s: {r: v for r, v in d.items() if r != target_round} for s, d in margin.items()}
    train_margin = {s: d for s, d in train_margin.items() if d}
    params = decompose(train_margin)
    rng = random.Random(SEED + target_round)
    sampler = make_year_effect_sampler(params, "baseline")

    # 다수 시뮬레이션 후 시도별 다수 결과 채택
    sido_dem_p = Counter()
    n = 5000
    for _ in range(n):
        winners = simulate_once(params, sampler, rng)
        for s, v in winners.items():
            if v == "D":
                sido_dem_p[s] += 1

    actual = {}
    for s, d in margin.items():
        if target_round in d:
            actual[s] = "D" if d[target_round] > 0 else "R"

    hits = 0
    mismatches = []
    for s, real in actual.items():
        if s not in params["sidos"]:
            continue
        prob_d = sido_dem_p[s] / n
        pred = "D" if prob_d >= 0.5 else "R"
        if pred == real:
            hits += 1
        else:
            mismatches.append({"sido": s, "actual": real, "pred": pred, "prob_d": round(prob_d, 3)})
    total = len([s for s in actual if s in params["sidos"]])
    return {
        "target_round": target_round,
        "hits": hits,
        "total": total,
        "accuracy_pct": round(hits / total * 100, 1) if total else 0,
        "mismatches": mismatches,
    }


def run_scenario(params, n, seed, mode):
    """한 시나리오 결과 집계 — sim + summary 통계."""
    sim = run_simulation(params, n, seed, mode)
    dem_seats_total = sum(s * c for s, c in sim["seat_dist_dem"].items())
    con_seats_total = sum(s * c for s, c in sim["seat_dist_con"].items())
    dem_mean = dem_seats_total / sim["n"]
    con_mean = con_seats_total / sim["n"]
    dem_mode = max(sim["seat_dist_dem"], key=sim["seat_dist_dem"].get)
    con_mode = max(sim["seat_dist_con"], key=sim["seat_dist_con"].get)
    dem_ci80 = credibility_interval(sim["seat_dist_dem"], sim["n"], 0.10, 0.90)
    con_ci80 = credibility_interval(sim["seat_dist_con"], sim["n"], 0.10, 0.90)
    dem_ci95 = credibility_interval(sim["seat_dist_dem"], sim["n"], 0.025, 0.975)
    sido_p = {s: round(sim["sido_dem_wins"].get(s, 0) / sim["n"], 4) for s in params["sidos"]}
    return {
        "mode": mode,
        "n": sim["n"],
        "dem_mean": round(dem_mean, 2),
        "dem_mode": dem_mode,
        "dem_80_ci": list(dem_ci80),
        "dem_95_ci": list(dem_ci95),
        "con_mean": round(con_mean, 2),
        "con_mode": con_mode,
        "con_80_ci": list(con_ci80),
        "seat_dist_dem": {int(k): v for k, v in sim["seat_dist_dem"].items()},
        "seat_dist_con": {int(k): v for k, v in sim["seat_dist_con"].items()},
        "sido_dem_prob": sido_p,
        "raw_sample_size": min(100, len(sim["raw"])),
    }


SCENARIO_META = {
    "baseline": {
        "title": "혼합 환경",
        "desc": "6회차(3~8회) 분위기를 모두 무작위로 추출. 시대 효과 불확실성을 그대로 반영.",
    },
    "normal": {
        "title": "보통 환경 (8회 직후 가정)",
        "desc": "5·6·8회처럼 평년 분위기가 9회에도 이어진다 가정. 격변기(7회) 제외.",
    },
    "shakeup": {
        "title": "정권심판 환경 (7회 직후 가정)",
        "desc": "7회(박근혜 탄핵 후) 같은 진보 압승 분위기를 9회에도 가정. 외부 충격 가정.",
    },
}


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    margin, year_of = load_history()
    params = decompose(margin)

    print("=== 모델 파라미터 ===")
    print(f"  회차 수: {len(params['rounds'])}")
    print(f"  시도 수: {len(params['sidos'])}")
    print(f"  year_effect: {params['year_effect']}")
    print(f"  residual SD: {params['residual_sd']}%p")
    print()

    # 세 시나리오 모두 실행
    scenarios = {}
    for mode in ["baseline", "normal", "shakeup"]:
        print(f"=== 시나리오: {mode} ===")
        sc = run_scenario(params, N_SIM, SEED, mode)
        scenarios[mode] = sc
        print(f"  민주 평균 {sc['dem_mean']}석, 최빈 {sc['dem_mode']}석, 80% CI {sc['dem_80_ci']}")
        print(f"  국힘 평균 {sc['con_mean']}석, 최빈 {sc['con_mode']}석, 80% CI {sc['con_80_ci']}")
        print()

    # baseline을 기본 결과로 사용 (요약 출력에)
    sim = run_simulation(params, N_SIM, SEED, "baseline")

    # 의석 분포 요약
    dem_seats = [s * c for s, c in sim["seat_dist_dem"].items()]
    dem_mean = sum(dem_seats) / sim["n"]
    con_seats = [s * c for s, c in sim["seat_dist_con"].items()]
    con_mean = sum(con_seats) / sim["n"]

    dem_mode = max(sim["seat_dist_dem"], key=sim["seat_dist_dem"].get)
    con_mode = max(sim["seat_dist_con"], key=sim["seat_dist_con"].get)
    dem_ci80 = credibility_interval(sim["seat_dist_dem"], sim["n"], 0.10, 0.90)
    con_ci80 = credibility_interval(sim["seat_dist_con"], sim["n"], 0.10, 0.90)
    dem_ci95 = credibility_interval(sim["seat_dist_dem"], sim["n"], 0.025, 0.975)

    print("=== 시뮬레이션 결과 (10,000회) ===")
    print(f"  민주 의석: 평균 {dem_mean:.2f}, 최빈 {dem_mode}석, 80% 구간 [{dem_ci80[0]}, {dem_ci80[1]}], 95% [{dem_ci95[0]}, {dem_ci95[1]}]")
    print(f"  국힘 의석: 평균 {con_mean:.2f}, 최빈 {con_mode}석, 80% 구간 [{con_ci80[0]}, {con_ci80[1]}]")
    print()

    # 백테스트 — 8회·7회·6회 각각
    print("=== 백테스트 (Leave-one-out) ===")
    backtests = []
    for r in [6, 7, 8]:
        bt = backtest(margin, r)
        print(f"  {r}회 ({year_of[r]}) 예측 적중: {bt['hits']}/{bt['total']} ({bt['accuracy_pct']}%)")
        if bt["mismatches"]:
            for m in bt["mismatches"]:
                print(f"     · 빗나감: {m['sido']} (실제 {m['actual']}, 예측 {m['pred']}, 민주확률 {m['prob_d']})")
        backtests.append(bt)
    print()

    # 시도별 민주 승리 확률
    print("=== 시도별 민주 승리 확률 ===")
    sido_marg = []
    for s in params["sidos"]:
        p = sim["sido_dem_wins"].get(s, 0) / sim["n"]
        sido_marg.append({"sido": s, "dem_win_prob": round(p, 4), "con_win_prob": round(1 - p, 4)})
    sido_marg.sort(key=lambda x: -x["dem_win_prob"])
    for r in sido_marg:
        bar_d = "█" * int(r["dem_win_prob"] * 30)
        print(f"  {r['sido']:14s}  D {r['dem_win_prob']:.3f}  {bar_d}")

    # 저장
    summary = {
        "generated_at": "2026-05-27",
        "model": "year_effect + region_lean + noise",
        "n_simulations": sim["n"],
        "seed": SEED,
        "year_effect": params["year_effect"],
        "region_mean": params["region_mean"],
        "region_sd": params["region_sd"],
        "residual_sd": params["residual_sd"],
        "scenarios": {
            mode: {**SCENARIO_META[mode], **sc}
            for mode, sc in scenarios.items()
        },
        "result": {
            "dem_mean_seats": round(dem_mean, 2),
            "dem_mode_seats": dem_mode,
            "dem_80_ci": list(dem_ci80),
            "dem_95_ci": list(dem_ci95),
            "con_mean_seats": round(con_mean, 2),
            "con_mode_seats": con_mode,
            "con_80_ci": list(con_ci80),
        },
        "backtests": backtests,
        "limitations": [
            "표본 6회차만 (1995~2022) — 통계적 표본 작음",
            "정당 진영 매핑의 자의성 (예: 새정치민주연합 → 진보)",
            "사전투표·당일투표 패턴 변화 미반영",
            "대선·탄핵·코로나 등 외부 충격 미반영",
            "후보 개별 효과 미반영",
            "예측이 아닌 과거 패턴 기반 시나리오",
        ],
        "legal_note": "공직선거법 108조 — 6/3 18시 투표마감 전 공표·인용보도 금지",
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    # 시도별 marginal CSV
    with (OUT_DIR / "sido_marginal.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["sido", "dem_win_prob", "con_win_prob"])
        w.writeheader()
        w.writerows(sido_marg)

    # 의석 분포 CSV
    with (OUT_DIR / "seat_distribution.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["seats", "dem_count", "dem_pct", "con_count", "con_pct"])
        all_seats = sorted(set(sim["seat_dist_dem"].keys()) | set(sim["seat_dist_con"].keys()))
        for s in all_seats:
            dc = sim["seat_dist_dem"].get(s, 0)
            cc = sim["seat_dist_con"].get(s, 0)
            w.writerow([s, dc, round(dc / sim["n"] * 100, 2), cc, round(cc / sim["n"] * 100, 2)])

    # raw 시뮬레이션 (10,000행)
    with (OUT_DIR / "raw_simulations.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["sim_id"] + params["sidos"])
        w.writeheader()
        for i, winners in enumerate(sim["raw"]):
            w.writerow({"sim_id": i, **winners})

    # HTML 시각화
    write_html(summary, scenarios, backtests, params)

    print(f"\n저장: {OUT_DIR.relative_to(ROOT)}/")


# ============ HTML 시각화 ============

def _bar_chart_html(dist: dict, label: str, color: str, max_count: int) -> str:
    """의석 수별 확률 가로 막대 차트."""
    rows = []
    for seat in sorted(dist.keys()):
        c = dist[seat]
        pct = c / sum(dist.values()) * 100
        w = c / max_count * 100
        rows.append(
            f'<div class="bar-row"><span class="bar-label">{seat}석</span>'
            f'<span class="bar-track"><span class="bar-fill" style="width:{w:.1f}%;background:{color}"></span></span>'
            f'<span class="bar-value">{pct:.1f}%</span></div>'
        )
    return f'<div class="bar-chart"><div class="bar-chart-title">{label}</div>{"".join(rows)}</div>'


def _scenario_block_html(mode: str, sc: dict) -> str:
    meta = SCENARIO_META[mode]
    max_d = max(sc["seat_dist_dem"].values()) if sc["seat_dist_dem"] else 1
    max_c = max(sc["seat_dist_con"].values()) if sc["seat_dist_con"] else 1
    dem_chart = _bar_chart_html(sc["seat_dist_dem"], "민주당 의석 분포", "#152484", max_d)
    con_chart = _bar_chart_html(sc["seat_dist_con"], "국민의힘 의석 분포", "#E61E2B", max_c)
    return f"""
    <section class="scenario">
      <h2 class="scenario-title">{meta['title']}</h2>
      <p class="scenario-desc">{meta['desc']}</p>
      <div class="scenario-stats">
        <div class="stat-pill stat-d">
          <span class="pill-label">민주</span>
          <strong class="pill-value">{sc['dem_mean']}석</strong>
          <span class="pill-sub">최빈 {sc['dem_mode']} · 80% [{sc['dem_80_ci'][0]}~{sc['dem_80_ci'][1]}]</span>
        </div>
        <div class="stat-pill stat-r">
          <span class="pill-label">국힘</span>
          <strong class="pill-value">{sc['con_mean']}석</strong>
          <span class="pill-sub">최빈 {sc['con_mode']} · 80% [{sc['con_80_ci'][0]}~{sc['con_80_ci'][1]}]</span>
        </div>
      </div>
      <div class="charts">{dem_chart}{con_chart}</div>
    </section>"""


def _sido_marginal_html(scenarios: dict) -> str:
    """시도별 민주 승리 확률 — 3개 시나리오 나란히 막대."""
    sidos = list(scenarios["baseline"]["sido_dem_prob"].keys())
    sidos.sort(key=lambda s: -scenarios["baseline"]["sido_dem_prob"][s])
    rows = []
    for s in sidos:
        p_b = scenarios["baseline"]["sido_dem_prob"][s]
        p_n = scenarios["normal"]["sido_dem_prob"][s]
        p_s = scenarios["shakeup"]["sido_dem_prob"][s]
        rows.append(f"""
        <tr>
          <td class="sido-name">{s}</td>
          <td><div class="prob-bar"><span style="width:{p_b*100:.0f}%"></span></div><span class="prob-num">{p_b*100:.0f}%</span></td>
          <td><div class="prob-bar"><span style="width:{p_n*100:.0f}%"></span></div><span class="prob-num">{p_n*100:.0f}%</span></td>
          <td><div class="prob-bar"><span style="width:{p_s*100:.0f}%"></span></div><span class="prob-num">{p_s*100:.0f}%</span></td>
        </tr>""")
    return f"""
    <section class="sido-marginal">
      <h2>시도별 민주당 승리 확률</h2>
      <table>
        <thead><tr><th>시도</th><th>혼합</th><th>보통</th><th>정권심판</th></tr></thead>
        <tbody>{"".join(rows)}</tbody>
      </table>
    </section>"""


def _backtest_html(backtests: list, year_of: dict) -> str:
    rows = []
    for bt in backtests:
        rd = bt["target_round"]
        year = year_of.get(rd, "")
        cls = "good" if bt["accuracy_pct"] >= 70 else "warn" if bt["accuracy_pct"] >= 50 else "bad"
        rows.append(
            f'<tr><td>{rd}회 ({year})</td><td>{bt["hits"]}/{bt["total"]}</td>'
            f'<td class="acc-{cls}">{bt["accuracy_pct"]}%</td></tr>'
        )
    return f"""
    <section class="backtest">
      <h2>모델 검증 (Leave-one-out)</h2>
      <p class="backtest-note">대상 회차를 제외하고 학습 → 그 회차 예측 → 실제와 비교.
      <strong>8회처럼 평년 환경엔 정확, 7회처럼 격변기엔 부정확.</strong></p>
      <table class="backtest-table">
        <thead><tr><th>대상</th><th>적중</th><th>정확도</th></tr></thead>
        <tbody>{"".join(rows)}</tbody>
      </table>
    </section>"""


def write_html(summary: dict, scenarios: dict, backtests: list, params: dict) -> None:
    year_of = {3:2002, 4:2006, 5:2010, 6:2014, 7:2018, 8:2022}
    scenario_blocks = "".join(_scenario_block_html(m, scenarios[m]) for m in ["baseline", "normal", "shakeup"])
    sido_block = _sido_marginal_html(scenarios)
    bt_block = _backtest_html(backtests, year_of)
    limit_items = "".join(f"<li>{x}</li>" for x in summary["limitations"])

    html = f"""<!doctype html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>9회 지방선거 시도지사 시뮬레이션 — 뉴탐사</title>
<style>
body {{ font-family: -apple-system, 'Pretendard', sans-serif; max-width: 1100px; margin: 0 auto; padding: 24px; color: #1a1a1a; line-height: 1.5; }}
h1 {{ font-size: 1.6rem; margin: 0 0 8px; }}
.intro {{ background: #fff8e3; border-left: 4px solid #b8860b; padding: 14px 16px; margin-bottom: 24px; border-radius: 4px; }}
.intro strong {{ color: #8b6500; }}
.scenario {{ border: 1px solid #ddd; border-radius: 8px; padding: 16px 20px; margin-bottom: 20px; background: #fff; }}
.scenario-title {{ font-size: 1.2rem; margin: 0 0 4px; }}
.scenario-desc {{ font-size: 0.85rem; color: #666; margin: 0 0 14px; }}
.scenario-stats {{ display: flex; gap: 10px; margin-bottom: 14px; flex-wrap: wrap; }}
.stat-pill {{ flex: 1; min-width: 200px; padding: 10px 14px; border-radius: 8px; }}
.stat-pill.stat-d {{ background: #eef2fb; border-left: 4px solid #152484; }}
.stat-pill.stat-r {{ background: #fdecee; border-left: 4px solid #E61E2B; }}
.pill-label {{ display: block; font-size: 0.78rem; color: #555; font-weight: 700; }}
.pill-value {{ display: block; font-size: 1.6rem; font-weight: 800; margin: 2px 0; }}
.pill-sub {{ font-size: 0.74rem; color: #555; }}
.charts {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
@media (max-width: 720px) {{ .charts {{ grid-template-columns: 1fr; }} }}
.bar-chart-title {{ font-size: 0.85rem; font-weight: 700; margin-bottom: 6px; color: #444; }}
.bar-row {{ display: grid; grid-template-columns: 38px 1fr 50px; align-items: center; gap: 8px; margin-bottom: 3px; font-size: 0.78rem; font-variant-numeric: tabular-nums; }}
.bar-label {{ color: #888; }}
.bar-track {{ background: #f3f3f3; height: 14px; border-radius: 3px; overflow: hidden; }}
.bar-fill {{ display: block; height: 100%; transition: width 0.3s; }}
.bar-value {{ font-weight: 600; color: #1a1a1a; text-align: right; }}
.sido-marginal {{ margin: 28px 0; }}
.sido-marginal table {{ width: 100%; border-collapse: collapse; font-size: 0.85rem; }}
.sido-marginal th, .sido-marginal td {{ padding: 6px 8px; border-bottom: 1px solid #eee; text-align: left; }}
.sido-marginal th {{ font-size: 0.78rem; color: #666; }}
.sido-name {{ font-weight: 700; width: 130px; }}
.prob-bar {{ display: inline-block; width: 160px; background: #f0f0f0; height: 8px; border-radius: 2px; overflow: hidden; vertical-align: middle; }}
.prob-bar span {{ display: block; height: 100%; background: #152484; }}
.prob-num {{ display: inline-block; margin-left: 8px; font-variant-numeric: tabular-nums; font-size: 0.78rem; color: #555; }}
.backtest table {{ width: 100%; border-collapse: collapse; max-width: 480px; }}
.backtest th, .backtest td {{ padding: 6px 10px; border-bottom: 1px solid #eee; text-align: left; font-variant-numeric: tabular-nums; }}
.acc-good {{ color: #126b3f; font-weight: 700; }}
.acc-warn {{ color: #8b6500; font-weight: 700; }}
.acc-bad {{ color: #b3261e; font-weight: 700; }}
.limits {{ background: #f6f6f6; padding: 14px 20px; border-radius: 4px; margin-top: 28px; font-size: 0.85rem; }}
.limits h2 {{ font-size: 1rem; margin: 0 0 8px; }}
.limits ul {{ margin: 0; padding-left: 20px; color: #555; }}
.legal {{ background: #fdecea; border-left: 4px solid #c41e3a; padding: 12px 16px; margin: 16px 0; font-size: 0.85rem; color: #b3261e; }}
</style>
</head>
<body>
<h1>9회 전국동시지방선거 시도지사 의석 시뮬레이션</h1>
<p style="color:#666;font-size:0.85rem;margin:0 0 16px;">2026-05-27 기준 · 과거 6회차(3~8회) 개표결과 기반 몬테카를로 1만회 · 뉴탐사</p>

<div class="legal">
  ⚠️ <strong>법적 주의</strong> — 공직선거법 제108조에 따라 선거 6일 전(2026-05-28)부터 투표마감(6/3 18:00)까지 본 시뮬레이션 결과는 <strong>공표·인용보도가 금지</strong>됩니다. 6/3 18:00 이후에만 사용할 수 있습니다.
</div>

<div class="intro">
  <strong>읽는 법</strong> — 9회 지선의 정치 환경이 어떨지 모르므로 세 시나리오로 분리해 보여줍니다. 9회 결과는 셋 중 어느 시나리오에 가깝게 나타나는지에 따라 달라질 것입니다. 단일 예측이 아닙니다.
</div>

{scenario_blocks}

{sido_block}

{bt_block}

<section class="limits">
  <h2>모델 한계</h2>
  <ul>{limit_items}</ul>
</section>

<p style="text-align:center;color:#aaa;font-size:0.75rem;margin-top:36px;">제9회 전국동시지방선거 시도지사 시뮬레이션 · 시민언론 뉴탐사</p>
</body>
</html>
"""
    (OUT_DIR / "index.html").write_text(html, encoding="utf-8")


if __name__ == "__main__":
    main()
