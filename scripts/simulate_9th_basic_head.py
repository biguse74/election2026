#!/usr/bin/env python3
"""
9회 기초단체장 226개 당선 분포 몬테카를로 시뮬레이션.

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
        print(f"  민주 평균 {sc['dem_mean']}곳, 최빈 {sc['dem_mode']}, 80% CI {sc['dem_80_ci']}")
        print(f"  국힘 평균 {sc['con_mean']}곳, 최빈 {sc['con_mode']}, 80% CI {sc['con_80_ci']}")
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
            "과거 6회차(1995~2022) 시군구별 데이터 — 표본 적음",
            "현직 이점·후보 효과·지역 토호 영향 미반영",
            "시군구 단위 공개 여론조사 자료 부족 — 시도지사·재보궐은 여론조사 반영",
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

    # 당선 분포 CSV
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
        <div class="stat-pill stat-d"><span class="pill-label">민주당</span><strong>{sc['dem_mode']}곳</strong><span class="pill-sub">예상 범위 {sc['dem_80_ci'][0]}~{sc['dem_80_ci'][1]}곳</span></div>
        <div class="stat-pill stat-r"><span class="pill-label">국힘·무소속 등</span><strong>{sc['con_mode']}곳</strong><span class="pill-sub">예상 범위 {sc['con_80_ci'][0]}~{sc['con_80_ci'][1]}곳</span></div>
      </div>
    </section>"""


def write_html(summary, scenarios, backtests, params, year_of):
    blocks = "".join(_scenario_block(m, scenarios[m]) for m in ["shakeup", "baseline", "normal"])

    # 시군구 전체 — 시도별 그룹 + 그 안에서 현재 환경(shakeup) 기준 정렬
    primary = "shakeup"
    by_sido_groups: dict[str, list] = {}
    for s in params["regions"]:
        by_sido_groups.setdefault(s[0], []).append(s)
    # 시도 정렬 (가나다 or 행정안전부 표준 순)
    SIDO_ORDER = [
        "서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시",
        "대전광역시", "울산광역시", "세종특별자치시", "경기도",
        "강원특별자치도", "충청북도", "충청남도", "전북특별자치도",
        "전라남도", "경상북도", "경상남도", "제주특별자치도",
        # 옛 이름 fallback
        "강원도", "전라북도", "제주도",
    ]
    sido_keys = sorted(by_sido_groups.keys(), key=lambda x: SIDO_ORDER.index(x) if x in SIDO_ORDER else 999)

    def row_html(s):
        key = f"{s[0]}/{s[1]}"
        ps = scenarios[primary]["sido_dem_prob"].get(key, 0)
        pb = scenarios["baseline"]["sido_dem_prob"].get(key, 0)
        pn = scenarios["normal"]["sido_dem_prob"].get(key, 0)
        d_pct = ps * 100
        r_pct = 100 - d_pct
        return (
            f'<tr><td class="sgg">{s[1]}</td>'
            f'<td><div class="stacked-bar">'
            f'<span class="stacked-d" style="width:{d_pct:.0f}%" title="민주당 진영 {d_pct:.0f}%"></span>'
            f'<span class="stacked-r" style="width:{r_pct:.0f}%" title="국민의힘 진영 {r_pct:.0f}%"></span>'
            f'</div></td>'
            f'<td class="num-d">{d_pct:.0f}%</td>'
            f'<td class="num-r">{r_pct:.0f}%</td>'
            f'<td class="num-sub hide-mobile">{pb*100:.0f}% / {(1-pb)*100:.0f}%</td>'
            f'<td class="num-sub hide-mobile">{pn*100:.0f}% / {(1-pn)*100:.0f}%</td>'
            f'</tr>'
        )

    sido_sections = []
    for sido in sido_keys:
        regs = by_sido_groups[sido]
        regs.sort(key=lambda s: -scenarios[primary]["sido_dem_prob"].get(f"{s[0]}/{s[1]}", 0))
        # 시도 통계 (그 시도 안에서 메인 시나리오 민주 확률 평균 + 시군구 수)
        avg_prob = sum(scenarios[primary]["sido_dem_prob"].get(f"{s[0]}/{s[1]}", 0) for s in regs) / len(regs)
        rows_html = "".join(row_html(s) for s in regs)
        sido_sections.append(f"""
        <section class="sido-group">
          <h3>{sido} <span class="sido-meta">{len(regs)}개 시군구 · 평균 민주 확률 {avg_prob*100:.0f}%</span></h3>
          <table class="sgg-table">
            <thead><tr>
              <th>시군구</th>
              <th>막대</th>
              <th>민주당</th>
              <th>그외</th>
              <th class="hide-mobile">혼합</th>
              <th class="hide-mobile">안정기</th>
            </tr></thead>
            <tbody>{rows_html}</tbody>
          </table>
        </section>""")
    sido_sections_html = "".join(sido_sections)

    bt_rows = "".join(f'<tr><td>{bt["target_round"]}회 ({year_of[bt["target_round"]]})</td><td>{bt["hits"]}/{bt["total"]}</td><td>{bt["accuracy_pct"]}%</td></tr>' for bt in backtests)
    limits = "".join(f"<li>{x}</li>" for x in summary["limitations"])

    html = f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>9회 지방선거 기초단체장 시뮬레이션 — 뉴탐사</title>
<style>
body {{ font-family: -apple-system, 'Pretendard', sans-serif; max-width: 1100px; margin: 0 auto; padding: 24px; color: #1a1a1a; line-height: 1.5; }}
h1 {{ font-size: 1.6rem; margin: 0 0 8px; }}
.legal {{ display: none; }}
.intro {{ background: transparent; border-left: 3px solid #ddd; padding: 8px 14px; margin: 4px 0 20px; font-size: 0.85rem; color: #666; }}
.intro strong {{ color: #444; font-weight: 700; }}
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

/* 시도 그룹 표 — 226개 시군구 풀 노출 */
.sido-group {{ margin: 18px 0 8px; padding: 12px 14px; border: 1px solid #e4e4e4; border-radius: 6px; background: #fafafa; }}
.sido-group h3 {{ font-size: 1rem; margin: 0 0 6px; color: #1a1a1a; display: flex; align-items: baseline; gap: 10px; flex-wrap: wrap; }}
.sido-group .sido-meta {{ font-size: 0.78rem; font-weight: 400; color: #666; }}
.sgg-table {{ font-size: 0.8rem; margin: 4px 0 0; }}
.sgg-table th {{ font-size: 0.74rem; font-weight: 600; color: #666; text-align: left; }}
.sgg-table td.sgg {{ font-weight: 600; }}
.stacked-bar {{
  display: flex; height: 12px; border-radius: 3px; overflow: hidden;
  background: #f0f0f0; min-width: 140px; max-width: 220px;
}}
.stacked-d {{ background: #152484; height: 100%; }}
.stacked-r {{ background: #E61E2B; height: 100%; }}
.num-d {{ color: #152484; font-weight: 700; font-variant-numeric: tabular-nums; }}
.num-r {{ color: #E61E2B; font-weight: 700; font-variant-numeric: tabular-nums; }}
.num-sub {{ color: #888; font-size: 0.74rem; font-variant-numeric: tabular-nums; }}

@media (max-width: 720px) {{
  body {{ padding: 14px 12px; }}
  h1 {{ font-size: 1.25rem; }}
  .scenario {{ padding: 12px 14px; }}
  .scenario-title {{ font-size: 1rem; }}
  .stat-pill {{ padding: 8px 10px; min-width: 150px; }}
  .stat-pill strong {{ font-size: 1.25rem; }}
  .sido-group {{ padding: 10px 10px; }}
  .sido-group h3 {{ font-size: 0.92rem; }}
  .sgg-table {{ font-size: 0.74rem; }}
  .sgg-table th, .sgg-table td {{ padding: 4px 4px; }}
  .sgg-table td.sgg {{ font-size: 0.78rem; }}
  .stacked-bar {{ min-width: 70px; max-width: 100px; height: 10px; }}
  .num-sub {{ font-size: 0.68rem; }}
  .hide-mobile {{ display: none; }}
}}
</style></head><body>
<h1>9회 전국동시지방선거 기초단체장 당선 시뮬레이션</h1>
<p style="color:#666;font-size:0.85rem;margin:0 0 16px;">2026-05-27 기준 · 226개 시군구 × 1만 회 몬테카를로 · 시도지사 시뮬레이션과 동일 모델 · 뉴탐사</p>
<div class="legal">⚠️ <strong>공직선거법 제108조</strong> — 6/3 18시 전 결과 공표·인용보도 금지.</div>
<div class="intro"><strong>시도지사·재보궐과 달리 이 페이지는 여론조사 자료 없이 과거 6회차(1995~2022) 개표 패턴만으로 시뮬레이션했습니다.</strong> 시군구는 후보 개별 효과·현직 이점·지역 영향이 훨씬 커서 모델 정확도가 떨어집니다. 시도지사·재보궐 결과를 더 신뢰하는 게 안전합니다.</div>
{blocks}
<section>
  <h2>시군구 전체 — 17개 시도별 민주당 승리 확률</h2>
  <p style="color:#666;font-size:0.85rem;margin:0 0 12px">현재 환경 추정(메인)·혼합·안정기 시나리오를 시군구별로 모두 표시. 시도 안에서 메인 확률 높은 순. 메인 막대는 민주 확률만 표시(높을수록 파랑 더 길게).</p>
  {sido_sections_html}
</section>
<section><h2>모델 검증 — 과거 선거로 되짚어보기</h2>
<p style="color:#666;font-size:0.85rem;margin:0 0 12px">과거 한 회차를 빼고 나머지 선거로 모델을 만든 뒤, 빼놓은 그 회차의 실제 결과를 얼마나 맞히는지 대조했습니다. <strong>평년 분위기였던 8회는 잘 맞혔고, 격변기였던 7회는 절반 수준에 그쳤습니다.</strong></p>
<table style="max-width:380px"><thead><tr><th>대상</th><th>적중</th><th>정확도</th></tr></thead><tbody>{bt_rows}</tbody></table></section>
<section class="limits"><h2>모델 한계</h2><ul>{limits}</ul></section>
</body></html>
"""
    (OUT_DIR / "index.html").write_text(html, encoding="utf-8")


if __name__ == "__main__":
    main()
