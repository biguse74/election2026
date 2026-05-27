#!/usr/bin/env python3
"""
9회 기초단체장 226개 의석 분포 몬테카를로 시뮬레이션.

모델은 시도지사 시뮬레이션과 동일 — year_effect + region_lean + noise.
다만 region 단위가 (시도, 시군구) 페어이고 시군구 226개의 회차별 매트릭스를 사용한다.

선거구 변동(통합·분리)은 매칭 안 되는 행을 자동 무시. 회차별 데이터 부족한
선거구는 SD 추정 어려움 → residual_sd로 fallback.

출력:
  exports/simulation_9th_basic_head/
    summary.json
    sigungu_marginal.csv  — 226개 시군구별 D 승리 확률
    seat_distribution.csv
    raw_simulations.csv
    index.html
"""

from __future__ import annotations

import csv
import json
import random
import statistics
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "exports" / "simulation_9th_basic_head"
N_SIM = 10_000
SEED = 42
SG_TYPE = "4"  # 기초단체장 (구시군장)

PROGRESSIVE = {
    "민주당", "새천년민주당", "열린우리당", "대통합민주신당",
    "통합민주당", "민주통합당", "새정치민주연합", "더불어민주당",
}
CONSERVATIVE = {
    "한나라당", "새누리당", "자유한국당", "바른정당", "미래통합당", "국민의힘",
}
SIDO_ALIASES = {
    "강원도": "강원특별자치도",
    "전라북도": "전북특별자치도",
    "제주도": "제주특별자치도",
}


def normalize_sido(name: str) -> str:
    return SIDO_ALIASES.get(name, name)


def load_history() -> tuple[dict, dict]:
    """history_counting_results.json에서 기초단체장 양당 margin 매트릭스 추출.
    반환: {(sd, sgg): {round: margin, ...}}, year_of_round
    """
    d = json.load((ROOT / "data" / "history_counting_results.json").open(encoding="utf-8"))
    margin: dict[tuple[str, str], dict[int, float]] = defaultdict(dict)
    year_of: dict[int, int] = {}
    for elec in d["elections"]:
        rd = int(elec["round"])
        year_of[rd] = int(elec["year"])
        head = next((r for r in elec["results"] if r["sgTypecode"] == SG_TYPE), None)
        if not head:
            continue
        for dist in head["districts"]:
            sd = normalize_sido(dist["sdName"])
            sgg = (dist.get("sggName") or "").strip()
            if not sgg:
                continue
            cands = dist.get("candidates") or []
            dem = sum(c.get("vote_share", 0) or 0 for c in cands if c.get("party") in PROGRESSIVE)
            con = sum(c.get("vote_share", 0) or 0 for c in cands if c.get("party") in CONSERVATIVE)
            margin[(sd, sgg)][rd] = round(dem - con, 3)
    return dict(margin), year_of


def decompose(margin: dict) -> dict:
    rounds = sorted({r for v in margin.values() for r in v.keys()})
    regions = sorted(margin.keys())

    year_effect = {}
    for r in rounds:
        vals = [margin[s][r] for s in regions if r in margin[s]]
        if vals:
            year_effect[r] = round(statistics.mean(vals), 3)

    region_lean = {}
    for s in regions:
        residuals = []
        for r, m in margin[s].items():
            if r in year_effect:
                residuals.append(m - year_effect[r])
        if not residuals:
            continue
        region_lean[s] = residuals

    region_mean = {s: round(statistics.mean(v), 3) for s, v in region_lean.items()}
    region_sd = {s: round(statistics.stdev(v), 3) if len(v) >= 2 else None for s, v in region_lean.items()}

    # global residual (시군구·회차 잔차)
    glb_resid = []
    for s, lst in region_lean.items():
        m = statistics.mean(lst)
        for v in lst:
            glb_resid.append(v - m)
    residual_sd = round(statistics.pstdev(glb_resid), 3) if glb_resid else 10.0

    return {
        "year_effect": year_effect,
        "region_mean": region_mean,
        "region_sd": region_sd,
        "residual_sd": residual_sd,
        "rounds": rounds,
        "regions": regions,
    }


def make_year_effect_sampler(params, mode):
    ye = params["year_effect"]
    all_vals = list(ye.values())
    if mode == "baseline":
        return lambda rng: rng.choice(all_vals)
    if mode == "normal":
        no_shake = [v for r, v in ye.items() if r != 7]
        mean = statistics.mean(no_shake)
        sd = statistics.stdev(no_shake) if len(no_shake) >= 2 else 5.0
        return lambda rng: rng.gauss(mean, sd)
    if mode == "shakeup":
        center = ye.get(7, 30.0)
        sd = statistics.stdev(all_vals)
        return lambda rng: rng.gauss(center, sd)
    raise ValueError(mode)


def simulate_once(params, sampler, rng):
    ye = sampler(rng)
    out = {}
    for s in params["regions"]:
        rm = params["region_mean"][s]
        rs = params["region_sd"].get(s)
        # SD 없으면 (1회만 출현한 선거구) global residual로 대체
        sd_lean = rs if (rs is not None and rs > 0) else params["residual_sd"]
        lean = rng.gauss(rm, sd_lean)
        noise = rng.gauss(0, params["residual_sd"])
        margin = ye + lean + noise
        out[s] = "D" if margin > 0 else "R"
    return out


def credibility_interval(counter, n, lo, hi):
    items = sorted(counter.items())
    cum = 0
    lo_seat = hi_seat = items[0][0]
    found_lo = False
    for seat, c in items:
        cum += c
        if not found_lo and cum >= n * lo:
            lo_seat = seat
            found_lo = True
        if cum >= n * hi:
            hi_seat = seat
            break
    return lo_seat, hi_seat


def run_scenario(params, n, seed, mode):
    rng = random.Random(seed)
    sampler = make_year_effect_sampler(params, mode)
    sido_dem_wins = Counter()
    seat_dist_dem = Counter()
    seat_dist_con = Counter()
    for _ in range(n):
        winners = simulate_once(params, sampler, rng)
        d_seats = sum(1 for v in winners.values() if v == "D")
        r_seats = sum(1 for v in winners.values() if v == "R")
        seat_dist_dem[d_seats] += 1
        seat_dist_con[r_seats] += 1
        for s, v in winners.items():
            if v == "D":
                sido_dem_wins[s] += 1

    dem_seats_total = sum(s * c for s, c in seat_dist_dem.items())
    con_seats_total = sum(s * c for s, c in seat_dist_con.items())
    dem_mean = dem_seats_total / n
    con_mean = con_seats_total / n
    dem_mode = max(seat_dist_dem, key=seat_dist_dem.get)
    con_mode = max(seat_dist_con, key=seat_dist_con.get)
    dem_ci80 = credibility_interval(seat_dist_dem, n, 0.10, 0.90)
    con_ci80 = credibility_interval(seat_dist_con, n, 0.10, 0.90)

    return {
        "mode": mode,
        "n": n,
        "dem_mean": round(dem_mean, 2),
        "dem_mode": dem_mode,
        "dem_80_ci": list(dem_ci80),
        "con_mean": round(con_mean, 2),
        "con_mode": con_mode,
        "con_80_ci": list(con_ci80),
        "seat_dist_dem": {int(k): v for k, v in seat_dist_dem.items()},
        "seat_dist_con": {int(k): v for k, v in seat_dist_con.items()},
        "sido_dem_prob": {f"{s[0]}/{s[1]}": round(sido_dem_wins.get(s, 0) / n, 4) for s in params["regions"]},
    }


def backtest(margin, target_round):
    train = {s: {r: v for r, v in d.items() if r != target_round} for s, d in margin.items()}
    train = {s: d for s, d in train.items() if d}
    params = decompose(train)
    rng = random.Random(SEED + target_round)
    sampler = make_year_effect_sampler(params, "baseline")
    n = 3000
    sido_dem_p = Counter()
    for _ in range(n):
        winners = simulate_once(params, sampler, rng)
        for s, v in winners.items():
            if v == "D":
                sido_dem_p[s] += 1
    actual = {}
    for s, d in margin.items():
        if target_round in d and s in params["regions"]:
            actual[s] = "D" if d[target_round] > 0 else "R"
    hits = 0
    for s, real in actual.items():
        prob_d = sido_dem_p[s] / n
        pred = "D" if prob_d >= 0.5 else "R"
        if pred == real:
            hits += 1
    total = len(actual)
    return {
        "target_round": target_round,
        "hits": hits,
        "total": total,
        "accuracy_pct": round(hits / total * 100, 1) if total else 0,
    }


SCENARIO_META = {
    "shakeup": {
        "title": "정권 출범 1년차 환경 — 9회 추정 환경",
        "desc": "이재명 정부 출범 1년차. 7회(2018) 지선과 유사한 환경 가정.",
        "primary": True,
    },
    "baseline": {
        "title": "혼합 환경 (참고)",
        "desc": "6회차 분위기를 모두 무작위 추출. 외부 환경 무관 분포.",
        "primary": False,
    },
    "normal": {
        "title": "정권 안정기 환경 (대안 가설)",
        "desc": "5·6·8회처럼 정권 중반 평년 분위기가 9회에도 이어졌다고 가정.",
        "primary": False,
    },
}


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    margin, year_of = load_history()
    params = decompose(margin)

    print(f"=== 모델 파라미터 ===")
    print(f"  회차 수: {len(params['rounds'])}")
    print(f"  시군구 수: {len(params['regions'])}")
    print(f"  year_effect: {params['year_effect']}")
    print(f"  residual SD: {params['residual_sd']}%p")
    print(f"  SD 없는 시군구 (1회만 출현): {sum(1 for v in params['region_sd'].values() if v is None or v == 0)}")
    print()

    scenarios = {}
    for mode in ["shakeup", "baseline", "normal"]:
        print(f"=== 시나리오: {mode} ===")
        sc = run_scenario(params, N_SIM, SEED, mode)
        scenarios[mode] = sc
        print(f"  민주 평균 {sc['dem_mean']}석, 최빈 {sc['dem_mode']}, 80% CI {sc['dem_80_ci']}")
        print(f"  국힘 평균 {sc['con_mean']}석, 최빈 {sc['con_mode']}, 80% CI {sc['con_80_ci']}")
        print()

    print("=== 백테스트 ===")
    backtests = []
    for r in [7, 8]:
        bt = backtest(margin, r)
        print(f"  {r}회 ({year_of[r]}): {bt['hits']}/{bt['total']} ({bt['accuracy_pct']}%)")
        backtests.append(bt)
    print()

    summary = {
        "generated_at": "2026-05-27",
        "sg_type": SG_TYPE,
        "office": "기초단체장",
        "n_simulations": N_SIM,
        "year_effect": params["year_effect"],
        "residual_sd": params["residual_sd"],
        "n_regions": len(params["regions"]),
        "scenarios": {m: {**SCENARIO_META[m], **sc} for m, sc in scenarios.items()},
        "backtests": backtests,
        "limitations": [
            "표본 6회차만 (1995~2022) — 시군구당 평균 4~6회",
            "선거구 통합·분리 변동 (5회→6회 226→222 등) 매칭 안 되는 행 무시",
            "정당 진영 매핑의 자의성 (예: 새정치민주연합 → 진보)",
            "현직 이점·후보 효과·지역 토호 영향 미반영",
            "사전투표·당일투표 패턴 변화 미반영",
            "공직선거법 108조 — 6/3 18시 투표마감 전 공표 금지",
        ],
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    # 시군구 marginal CSV
    sigungu_rows = []
    for s in params["regions"]:
        key = f"{s[0]}/{s[1]}"
        sigungu_rows.append({
            "시도": s[0],
            "시군구": s[1],
            "민주_확률_혼합": scenarios["baseline"]["sido_dem_prob"][key],
            "민주_확률_보통": scenarios["normal"]["sido_dem_prob"][key],
            "민주_확률_정권심판": scenarios["shakeup"]["sido_dem_prob"][key],
        })
    sigungu_rows.sort(key=lambda r: -r["민주_확률_혼합"])
    with (OUT_DIR / "sigungu_marginal.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(sigungu_rows[0].keys()))
        w.writeheader()
        w.writerows(sigungu_rows)

    # 의석 분포 CSV
    with (OUT_DIR / "seat_distribution.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["scenario", "seats", "dem_count", "dem_pct", "con_count", "con_pct"])
        for mode in ["baseline", "normal", "shakeup"]:
            sc = scenarios[mode]
            all_seats = sorted(set(sc["seat_dist_dem"].keys()) | set(sc["seat_dist_con"].keys()))
            for s in all_seats:
                dc = sc["seat_dist_dem"].get(s, 0)
                cc = sc["seat_dist_con"].get(s, 0)
                w.writerow([mode, s, dc, round(dc / sc["n"] * 100, 3), cc, round(cc / sc["n"] * 100, 3)])

    # HTML
    write_html(summary, scenarios, backtests, params, year_of)
    print(f"저장: {OUT_DIR.relative_to(ROOT)}/")


def _scenario_block(mode, sc):
    meta = SCENARIO_META[mode]
    is_primary = meta.get("primary", False)
    badge = '<span class="scenario-primary-badge">현재 환경 추정</span>' if is_primary else ''
    cls = "scenario scenario-primary" if is_primary else "scenario"
    return f"""
    <section class="{cls}">
      <h2 class="scenario-title">{meta['title']} {badge}</h2>
      <p class="scenario-desc">{meta['desc']}</p>
      <div class="scenario-stats">
        <div class="stat-pill stat-d"><span class="pill-label">민주</span><strong>{sc['dem_mean']}석</strong><span class="pill-sub">최빈 {sc['dem_mode']} · 80% [{sc['dem_80_ci'][0]}~{sc['dem_80_ci'][1]}]</span></div>
        <div class="stat-pill stat-r"><span class="pill-label">국힘</span><strong>{sc['con_mean']}석</strong><span class="pill-sub">최빈 {sc['con_mode']} · 80% [{sc['con_80_ci'][0]}~{sc['con_80_ci'][1]}]</span></div>
      </div>
    </section>"""


def write_html(summary, scenarios, backtests, params, year_of):
    blocks = "".join(_scenario_block(m, scenarios[m]) for m in ["shakeup", "baseline", "normal"])
    # 시군구 표 — 상위 15 + 하위 15
    sigungu_sorted = sorted(params["regions"], key=lambda s: -scenarios["baseline"]["sido_dem_prob"][f"{s[0]}/{s[1]}"])
    def rows(rng):
        out = []
        for s in rng:
            key = f"{s[0]}/{s[1]}"
            pb = scenarios["baseline"]["sido_dem_prob"][key]
            pn = scenarios["normal"]["sido_dem_prob"][key]
            ps = scenarios["shakeup"]["sido_dem_prob"][key]
            out.append(f'<tr><td>{s[0]}</td><td>{s[1]}</td><td>{pb*100:.0f}%</td><td>{pn*100:.0f}%</td><td>{ps*100:.0f}%</td></tr>')
        return "".join(out)
    top_rows = rows(sigungu_sorted[:20])
    bot_rows = rows(sigungu_sorted[-20:])

    bt_rows = "".join(f'<tr><td>{bt["target_round"]}회 ({year_of[bt["target_round"]]})</td><td>{bt["hits"]}/{bt["total"]}</td><td>{bt["accuracy_pct"]}%</td></tr>' for bt in backtests)
    limits = "".join(f"<li>{x}</li>" for x in summary["limitations"])

    html = f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>9회 지방선거 기초단체장 시뮬레이션 — 뉴탐사</title>
<style>
body {{ font-family: -apple-system, 'Pretendard', sans-serif; max-width: 1100px; margin: 0 auto; padding: 24px; color: #1a1a1a; line-height: 1.5; }}
h1 {{ font-size: 1.6rem; margin: 0 0 8px; }}
.legal {{ background: #fdecea; border-left: 4px solid #c41e3a; padding: 12px 16px; margin: 16px 0; font-size: 0.85rem; color: #b3261e; }}
.intro {{ background: #fff8e3; border-left: 4px solid #b8860b; padding: 14px 16px; margin-bottom: 24px; border-radius: 4px; font-size: 0.9rem; }}
.scenario {{ border: 1px solid #ddd; border-radius: 8px; padding: 14px 18px; margin-bottom: 14px; background: #fff; }}
.scenario-primary {{ border: 2px solid #152484; box-shadow: 0 2px 12px rgba(21,36,132,0.08); }}
.scenario-primary-badge {{ display: inline-block; background: #152484; color: #fff; font-size: 0.7rem; padding: 3px 9px; border-radius: 999px; vertical-align: middle; margin-left: 6px; font-weight: 700; }}
.scenario-title {{ font-size: 1.1rem; margin: 0 0 4px; }}
.scenario-desc {{ font-size: 0.84rem; color: #666; margin: 0 0 12px; }}
.scenario-stats {{ display: flex; gap: 10px; flex-wrap: wrap; }}
.stat-pill {{ flex: 1; min-width: 200px; padding: 10px 14px; border-radius: 6px; }}
.stat-pill.stat-d {{ background: #eef2fb; border-left: 4px solid #152484; }}
.stat-pill.stat-r {{ background: #fdecee; border-left: 4px solid #E61E2B; }}
.pill-label {{ display: block; font-size: 0.74rem; color: #555; font-weight: 700; }}
.stat-pill strong {{ display: inline-block; font-size: 1.5rem; font-weight: 800; margin: 2px 8px 2px 0; }}
.pill-sub {{ font-size: 0.74rem; color: #555; }}
table {{ width: 100%; border-collapse: collapse; font-size: 0.82rem; margin: 8px 0 20px; }}
th, td {{ padding: 5px 8px; border-bottom: 1px solid #eee; text-align: left; font-variant-numeric: tabular-nums; }}
th {{ font-size: 0.78rem; color: #666; }}
.limits {{ background: #f6f6f6; padding: 14px 20px; border-radius: 4px; margin-top: 28px; font-size: 0.85rem; }}
.limits h2 {{ font-size: 1rem; margin: 0 0 8px; }}
.limits ul {{ margin: 0; padding-left: 20px; color: #555; }}
</style></head><body>
<h1>9회 전국동시지방선거 기초단체장 의석 시뮬레이션</h1>
<p style="color:#666;font-size:0.85rem;margin:0 0 16px;">2026-05-27 기준 · 226개 시군구 × 1만 회 몬테카를로 · 시도지사 시뮬레이션과 동일 모델 · 뉴탐사</p>
<div class="legal">⚠️ <strong>공직선거법 제108조</strong> — 6/3 18시 전 결과 공표·인용보도 금지.</div>
<div class="intro"><strong>시도지사 시뮬레이션</strong>에 비해 시군구는 후보 개별 효과·현직 이점·지역 토호 영향이 훨씬 커서 모델 정확도가 떨어집니다. 환경별 의석 분포 예측에는 시도지사 결과를 더 신뢰하는 게 안전합니다.</div>
{blocks}
<section><h2>시군구별 민주당 승리 확률 — 상위 20</h2>
<table><thead><tr><th>시도</th><th>시군구</th><th>혼합</th><th>보통</th><th>정권심판</th></tr></thead><tbody>{top_rows}</tbody></table></section>
<section><h2>시군구별 민주당 승리 확률 — 하위 20</h2>
<table><thead><tr><th>시도</th><th>시군구</th><th>혼합</th><th>보통</th><th>정권심판</th></tr></thead><tbody>{bot_rows}</tbody></table></section>
<section><h2>모델 검증 (Leave-one-out)</h2>
<table style="max-width:380px"><thead><tr><th>대상</th><th>적중</th><th>정확도</th></tr></thead><tbody>{bt_rows}</tbody></table></section>
<section class="limits"><h2>모델 한계</h2><ul>{limits}</ul></section>
</body></html>
"""
    (OUT_DIR / "index.html").write_text(html, encoding="utf-8")


if __name__ == "__main__":
    main()
