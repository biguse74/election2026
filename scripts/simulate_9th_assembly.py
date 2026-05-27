#!/usr/bin/env python3
"""
9회 동시 국회의원 재·보궐 14개 선거구 시뮬레이션.

데이터 출처:
    tmp/mbc/assembly_boxplot_data.js — 14개 선거구 후보별 일별 mean·lower·upper

모델:
    각 선거구별 (민주 mean - 국힘 mean) ± 합성 SD를 prior로 사용.
    잡음 SD = sqrt(MBC_SD² + global_residual²)

시도지사 시뮬과 달리 historical 매트릭스 없이 MBC 데이터만으로 시뮬.
대신 unsertainty를 크게 둬서 (residual 6~8%p) 안전 측 분포.

출력:
    exports/simulation_9th_assembly/
      summary.json
      seat_distribution.csv
      raw.csv
      index.html
"""

from __future__ import annotations

import csv
import json
import random
import re
import statistics
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MBC = ROOT / "tmp" / "mbc"
OUT_DIR = ROOT / "exports" / "simulation_9th_assembly"

N_SIM = 10_000
SEED = 42
RESIDUAL_SD = 6.0  # 보수적: 6%p — MBC SD 외 추가 모델 잡음

PROGRESSIVE = {"더불어민주당"}
CONSERVATIVE = {"국민의힘"}


def _clean_js_to_json(raw: str) -> str:
    """JS literal → JSON. 빈 element·trailing comma 제거."""
    while re.search(r",(\s*),(\s*[\[{])", raw):
        raw = re.sub(r",(\s*),(\s*[\[{])", r",\2", raw)
    raw = re.sub(r"\[(\s*),", r"[", raw)
    raw = re.sub(r",(\s*\])", r"\1", raw)
    raw = re.sub(r",(\s*\})", r"\1", raw)
    return raw


def parse_boxplot() -> list[dict]:
    text = (MBC / "assembly_boxplot_data.js").read_text(encoding="utf-8")
    m = re.search(r"=\s*(\[.*\])\s*;?\s*$", text.strip(), re.DOTALL)
    if not m:
        return []
    raw = m.group(1)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return json.loads(_clean_js_to_json(raw))


def parse_repoll() -> list[dict]:
    text = (MBC / "assembly_repoll.js").read_text(encoding="utf-8")
    m = re.search(r"=\s*(\[.*\])\s*;?\s*$", text.strip(), re.DOTALL)
    if not m:
        return []
    raw = m.group(1)
    # JS 객체 → JSON (key를 따옴표로)
    raw = re.sub(r"(\w+):", r'"\1":', raw)
    # boolean·null·trailing
    raw = raw.replace("true,", "true,").replace("false,", "false,")
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return json.loads(_clean_js_to_json(raw))


# 선거구명 정규화 (boxplot ↔ repoll 매칭용)
def canon(name: str) -> str:
    s = (name or "").replace(" ", "").replace("·", "")
    # 약식 ↔ 풀이름 매핑 (지역명)
    s = s.replace("광주광산을", "광주광역시광산구을")
    s = s.replace("대구달성군", "대구광역시달성군")
    s = s.replace("부산북구갑", "부산광역시북구갑")
    return s


def extract_priors(boxplot_arr: list[dict], repoll_arr: list[dict]) -> list[dict]:
    """14개 선거구 각각에서 prior 추출.
    1) boxplot에 graph_data 있으면 마지막 시점 mean·SD 사용
    2) graph_data 없거나 boxplot에 항목 없으면 repoll의 22대 당선 정당 기반 fallback
       (D 당선 → margin +18%p, R 당선 → -18%p, 합산 SD 12%p — 보수적)
    """
    # repoll 기준 14개 선거구 매트릭스 (consti canonical → repoll entry)
    repoll_by_canon = {canon(r["consti"]): r for r in repoll_arr}
    # boxplot 매칭 (canon)
    box_by_canon = {}
    for race in boxplot_arr:
        c = canon(race.get("consti"))
        if c in box_by_canon:
            # 중복(대구 달성군 등) — graph_data 더 있는 쪽 우선
            existing = box_by_canon[c]
            if len(race.get("graph_data") or []) > len(existing.get("graph_data") or []):
                box_by_canon[c] = race
        else:
            box_by_canon[c] = race

    out = []
    for r_canon, rep in repoll_by_canon.items():
        race = box_by_canon.get(r_canon, {})
        consti = rep.get("consti")
        region1 = rep.get("region1_site")
        region2 = rep.get("region2_site")
        state = race.get("state") or rep.get("state_2") or ""
        candis = race.get("candis") or []
        gdata = race.get("graph_data") or []

        dem = con = None
        used_fallback = False

        if gdata:
            last = gdata[-1]
            for c in candis:
                party = c.get("party")
                name = c.get("name")
                base = f"{name}_{party}"
                mean = last.get(f"{base}_mean")
                lo = last.get(f"{base}_lower")
                up = last.get(f"{base}_upper")
                if mean is None:
                    continue
                unc = (up - lo) / 4 if (lo is not None and up is not None) else 1.5
                entry = {"name": name, "party": party, "mean": round(mean, 2), "sd": round(unc, 2)}
                if party in PROGRESSIVE and dem is None:
                    dem = entry
                elif party in CONSERVATIVE and con is None:
                    con = entry

        if not dem or not con:
            # Fallback: repoll의 22대 당선 정당 기반
            used_fallback = True
            elected = rep.get("elected_party") or rep.get("party")
            # 22대 당선 정당 → margin 가정
            if elected in PROGRESSIVE:
                fb_margin = 18.0   # D 우세 (다소 보수적)
                fb_sd = 4.0        # MBC SD 자리 — 큰 잡음
            elif elected in CONSERVATIVE:
                fb_margin = -18.0  # R 우세
                fb_sd = 4.0
            else:
                fb_margin = 0.0
                fb_sd = 6.0
            # 후보 정보가 있으면 채우고, 없으면 22대 인물 채움
            dem_name = (rep.get("elected_name") if elected in PROGRESSIVE
                        else rep.get("name") if rep.get("party") in PROGRESSIVE
                        else "—")
            con_name = (rep.get("elected_name") if elected in CONSERVATIVE
                        else rep.get("name") if rep.get("party") in CONSERVATIVE
                        else "—")
            # 후보 명단에서 보강
            for c in candis:
                if c.get("party") in PROGRESSIVE and not dem:
                    dem_name = c.get("name") or dem_name
                if c.get("party") in CONSERVATIVE and not con:
                    con_name = c.get("name") or con_name
            dem = {"name": dem_name, "party": "더불어민주당", "mean": None, "sd": None}
            con = {"name": con_name, "party": "국민의힘", "mean": None, "sd": None}
            out.append({
                "consti": consti,
                "region1": region1,
                "region2": region2,
                "state_label": state + " (자료 부족 — 22대 당선 기반 추정)",
                "last_date": None,
                "dem": dem,
                "con": con,
                "margin": fb_margin,
                "margin_sd": fb_sd,
                "fallback": True,
            })
            continue

        margin = dem["mean"] - con["mean"]
        margin_sd = (dem["sd"] ** 2 + con["sd"] ** 2) ** 0.5
        out.append({
            "consti": consti,
            "region1": region1,
            "region2": region2,
            "state_label": state,
            "last_date": last.get("date"),
            "dem": dem,
            "con": con,
            "margin": round(margin, 2),
            "margin_sd": round(margin_sd, 2),
            "fallback": False,
        })
    return out


def simulate(priors: list[dict], n: int, seed: int) -> dict:
    rng = random.Random(seed)
    seat_dem = Counter()
    seat_con = Counter()
    race_dem_wins = Counter()
    for _ in range(n):
        d = c = 0
        for r in priors:
            sd = (r["margin_sd"] ** 2 + RESIDUAL_SD ** 2) ** 0.5
            m = rng.gauss(r["margin"], sd)
            if m > 0:
                d += 1
                race_dem_wins[r["consti"]] += 1
            else:
                c += 1
        seat_dem[d] += 1
        seat_con[c] += 1
    return {"seat_dem": seat_dem, "seat_con": seat_con, "race_dem_wins": race_dem_wins, "n": n}


def credibility_interval(counter, n, lo, hi):
    items = sorted(counter.items())
    cum = 0
    lo_s = hi_s = items[0][0]
    found = False
    for s, c in items:
        cum += c
        if not found and cum >= n * lo:
            lo_s = s
            found = True
        if cum >= n * hi:
            hi_s = s
            break
    return lo_s, hi_s


def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    arr = parse_boxplot()
    if not arr:
        raise SystemExit("boxplot_data.js 파싱 실패 — tmp/mbc/assembly_boxplot_data.js 확인")
    repoll = parse_repoll()
    if not repoll:
        raise SystemExit("repoll.js 파싱 실패 — tmp/mbc/assembly_repoll.js 확인")

    priors = extract_priors(arr, repoll)
    print(f"=== 14개 재보궐 선거구 prior (총 {len(priors)}개) ===")
    for p in sorted(priors, key=lambda x: -x["margin"]):
        sign = "+" if p["margin"] >= 0 else ""
        win = "D" if p["margin"] > 0 else "R"
        dm = f"{p['dem']['mean']:5.1f}%" if p['dem']['mean'] is not None else "  —  "
        cm = f"{p['con']['mean']:5.1f}%" if p['con']['mean'] is not None else "  —  "
        tag = "[fb]" if p.get("fallback") else "   "
        print(f"  {p['region1']:>4s} {p['region2']:<14s} {tag}  "
              f"{p['dem']['name']:>5s}({dm}) vs "
              f"{p['con']['name']:>5s}({cm})  "
              f"margin {sign}{p['margin']:+5.1f}%p ± {p['margin_sd']:4.1f}  "
              f"[{win}]  {p['state_label']}")

    sim = simulate(priors, N_SIM, SEED)
    n = sim["n"]
    dem_mean = sum(s * c for s, c in sim["seat_dem"].items()) / n
    con_mean = sum(s * c for s, c in sim["seat_con"].items()) / n
    dem_mode = max(sim["seat_dem"], key=sim["seat_dem"].get)
    con_mode = max(sim["seat_con"], key=sim["seat_con"].get)
    dem_ci80 = credibility_interval(sim["seat_dem"], n, 0.10, 0.90)
    con_ci80 = credibility_interval(sim["seat_con"], n, 0.10, 0.90)

    print(f"\n=== 시뮬 결과 (10,000회) ===")
    print(f"  민주: 평균 {dem_mean:.2f}, 최빈 {dem_mode}, 80% CI {dem_ci80}")
    print(f"  국힘: 평균 {con_mean:.2f}, 최빈 {con_mode}, 80% CI {con_ci80}")

    # CSV·summary
    summary = {
        "generated_at": "2026-05-27",
        "source": "poll-mbc.co.kr region_data/assembly/boxplot_data.js",
        "model": "MBC 베이지안 추정치 prior + Normal noise (residual SD 6%p)",
        "n_simulations": n,
        "races": priors,
        "result": {
            "dem_mean": round(dem_mean, 2),
            "dem_mode": dem_mode,
            "dem_80_ci": list(dem_ci80),
            "con_mean": round(con_mean, 2),
            "con_mode": con_mode,
            "con_80_ci": list(con_ci80),
            "seat_dist_dem": {int(k): v for k, v in sim["seat_dem"].items()},
            "seat_dist_con": {int(k): v for k, v in sim["seat_con"].items()},
            "race_dem_prob": {k: round(v / n, 4) for k, v in sim["race_dem_wins"].items()},
        },
        "limitations": [
            "14개 선거구 각각 표본 작음 — 특히 'null' 분류 선거구는 여론조사 누적 적음",
            "현직 이점·후보 효과·정당 변동 미반영",
            "MBC SD 외 모델 잡음 SD 6%p 가정 — 보수적 추정",
            "MBC 데이터가 갱신되면 결과도 갱신해야 함",
            "여론조사 인용보도 아닌 모델 내부 변수로만 사용",
        ],
    }
    (OUT_DIR / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    with (OUT_DIR / "seat_distribution.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["seats", "dem_count", "dem_pct", "con_count", "con_pct"])
        for s in sorted(set(sim["seat_dem"].keys()) | set(sim["seat_con"].keys())):
            dc = sim["seat_dem"].get(s, 0)
            cc = sim["seat_con"].get(s, 0)
            w.writerow([s, dc, round(dc / n * 100, 2), cc, round(cc / n * 100, 2)])

    write_html(summary, priors, sim)
    print(f"\n저장: {OUT_DIR.relative_to(ROOT)}/")


def write_html(summary, priors, sim):
    n = sim["n"]
    races_sorted = sorted(priors, key=lambda x: -x["margin"])
    race_rows = []
    for p in races_sorted:
        prob_d = sim["race_dem_wins"].get(p["consti"], 0) / n
        bar_color = "#152484" if prob_d >= 0.5 else "#E61E2B"
        dem_mean = f"{p['dem']['mean']}%" if p['dem']['mean'] is not None else "—"
        con_mean = f"{p['con']['mean']}%" if p['con']['mean'] is not None else "—"
        fb_mark = ' <span style="font-size:0.7rem;color:#999">(fb)</span>' if p.get("fallback") else ""
        race_rows.append(f"""
        <tr>
          <td>{p['region1']}</td>
          <td class="sgg">{p['region2']}{fb_mark}</td>
          <td>{p['dem']['name']}<br><span class="party-d">{dem_mean}</span></td>
          <td>{p['con']['name']}<br><span class="party-r">{con_mean}</span></td>
          <td class="margin">{p['margin']:+.1f}%p ±{p['margin_sd']}</td>
          <td><div class="prob-cell"><span class="prob-bar"><span style="width:{prob_d*100:.0f}%;background:{bar_color}"></span></span><span class="prob-num">{prob_d*100:.0f}%</span></div></td>
          <td class="state">{p['state_label'] or '—'}</td>
        </tr>""")
    rows_html = "".join(race_rows)

    # 의석 분포 막대
    max_d = max(sim["seat_dem"].values())
    max_c = max(sim["seat_con"].values())
    def dist_html(dist, color, title, max_v):
        bars = []
        for s in sorted(dist.keys()):
            c = dist[s]
            pct = c / n * 100
            w = c / max_v * 100
            bars.append(f'<div class="bar-row"><span class="bar-label">{s}석</span><span class="bar-track"><span class="bar-fill" style="width:{w:.1f}%;background:{color}"></span></span><span class="bar-value">{pct:.1f}%</span></div>')
        return f'<div class="dist-block"><div class="dist-title">{title}</div>{"".join(bars)}</div>'
    dem_chart = dist_html(sim["seat_dem"], "#152484", "민주당 의석 분포", max_d)
    con_chart = dist_html(sim["seat_con"], "#E61E2B", "국민의힘 의석 분포", max_c)

    r = summary["result"]

    DISCLAIMER = """<div style="max-width:880px;margin:0 auto 20px;padding:14px 18px;background:#fdecea;border-left:4px solid #c41e3a;border-radius:4px;font-size:0.86rem;line-height:1.6">
  <strong style="color:#b3261e;display:block;margin-bottom:4px;font-size:0.92rem">⚠️ 자료의 성격 안내</strong>
  · 본 자료는 <strong>여론조사·예측조사가 아닙니다</strong>. MBC 여론M 시도별 베이지안 추정치를 prior로 한 시뮬레이션.<br>
  · 특정 후보·정당의 당락을 <strong>단정하지 않습니다</strong>.<br>
  · MBC 베이지안 모형의 신뢰구간을 prior 입력, 추가 잡음 SD 6%p를 부여한 보수적 추정.<br>
  · 14개 선거구 각각 표본이 작아 신뢰구간이 넓음. 인용·재가공 시 한계 함께 표기 부탁.
</div>"""

    limits = "".join(f"<li>{x}</li>" for x in summary["limitations"])

    html = f"""<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>9회 동시 국회의원 재·보궐 시뮬레이션 — 뉴탐사</title>
<style>
body {{ font-family: -apple-system, 'Pretendard', sans-serif; max-width: 1100px; margin: 0 auto; padding: 24px; color: #1a1a1a; line-height: 1.55; }}
h1 {{ font-size: 1.55rem; margin: 0 0 8px; }}
.sub {{ color: #666; font-size: 0.88rem; margin: 0 0 18px; }}
.summary-pills {{ display: flex; gap: 12px; margin: 16px 0 22px; flex-wrap: wrap; }}
.pill {{ flex: 1; min-width: 220px; padding: 12px 16px; border-radius: 8px; }}
.pill.d {{ background: #eef2fb; border-left: 4px solid #152484; }}
.pill.r {{ background: #fdecee; border-left: 4px solid #E61E2B; }}
.pill .lbl {{ display: block; font-size: 0.75rem; color: #555; font-weight: 700; }}
.pill .val {{ display: inline-block; font-size: 1.7rem; font-weight: 800; margin: 2px 8px 2px 0; }}
.pill .sub {{ font-size: 0.74rem; color: #555; margin: 0; display: inline; }}
.charts {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin: 20px 0; }}
@media (max-width: 720px) {{ .charts {{ grid-template-columns: 1fr; }} }}
.dist-block {{ border: 1px solid #e0e0e0; border-radius: 8px; padding: 12px 14px; background: #fff; }}
.dist-title {{ font-weight: 700; font-size: 0.92rem; margin-bottom: 8px; }}
.bar-row {{ display: grid; grid-template-columns: 38px 1fr 50px; align-items: center; gap: 8px; margin-bottom: 3px; font-size: 0.78rem; font-variant-numeric: tabular-nums; }}
.bar-label {{ color: #888; }}
.bar-track {{ background: #f3f3f3; height: 14px; border-radius: 3px; overflow: hidden; }}
.bar-fill {{ display: block; height: 100%; }}
.bar-value {{ font-weight: 600; text-align: right; }}
table.races {{ width: 100%; border-collapse: collapse; font-size: 0.82rem; margin: 12px 0 24px; }}
table.races th, table.races td {{ padding: 7px 8px; border-bottom: 1px solid #eee; text-align: left; vertical-align: top; }}
table.races th {{ font-size: 0.74rem; color: #555; }}
.sgg {{ font-weight: 700; }}
.party-d {{ color: #152484; font-weight: 700; font-variant-numeric: tabular-nums; }}
.party-r {{ color: #E61E2B; font-weight: 700; font-variant-numeric: tabular-nums; }}
.margin {{ font-variant-numeric: tabular-nums; font-weight: 600; }}
.state {{ font-size: 0.78rem; color: #777; }}
.prob-cell {{ display: flex; align-items: center; gap: 6px; }}
.prob-bar {{ display: inline-block; flex: 1; min-width: 60px; max-width: 120px; height: 8px; background: #f0f0f0; border-radius: 2px; overflow: hidden; }}
.prob-bar > span {{ display: block; height: 100%; }}
.prob-num {{ font-variant-numeric: tabular-nums; font-weight: 700; min-width: 36px; text-align: right; font-size: 0.84rem; }}
.limits {{ background: #f6f6f6; padding: 14px 20px; border-radius: 4px; margin-top: 28px; font-size: 0.85rem; }}
.limits h2 {{ font-size: 1rem; margin: 0 0 8px; }}
.limits ul {{ margin: 0; padding-left: 20px; color: #555; }}
</style></head><body>
{DISCLAIMER}
<h1>9회 동시 국회의원 재·보궐 14개 선거구 시뮬레이션</h1>
<p class="sub">2026-05-27 기준 · MBC 베이지안 추정치 prior + 1만 회 몬테카를로 · 시민언론 뉴탐사</p>

<div class="summary-pills">
  <div class="pill d"><span class="lbl">민주당</span> <strong class="val">{r['dem_mean']}석</strong><p class="sub">최빈 {r['dem_mode']}석 · 80% CI [{r['dem_80_ci'][0]}~{r['dem_80_ci'][1]}]</p></div>
  <div class="pill r"><span class="lbl">국민의힘</span> <strong class="val">{r['con_mean']}석</strong><p class="sub">최빈 {r['con_mode']}석 · 80% CI [{r['con_80_ci'][0]}~{r['con_80_ci'][1]}]</p></div>
</div>

<div class="charts">{dem_chart}{con_chart}</div>

<section>
  <h2 style="font-size:1.1rem">14개 선거구별 민주 우세도</h2>
  <table class="races">
    <thead><tr><th>시도</th><th>선거구</th><th>민주 후보 · 추정 지지율</th><th>국힘 후보 · 추정 지지율</th><th>격차 (민주-국힘)</th><th>민주 승리 확률</th><th>MBC 분류</th></tr></thead>
    <tbody>{rows_html}</tbody>
  </table>
</section>

<section class="limits"><h2>모델 한계</h2><ul>{limits}</ul></section>
</body></html>
"""
    (OUT_DIR / "index.html").write_text(html, encoding="utf-8")


if __name__ == "__main__":
    main()
