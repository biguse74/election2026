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
CANDIDATES_DIR = ROOT / "data" / "candidates" / "20260603"

# 14개 재보궐 선거구 — repoll consti와 매칭 시 우리 사이트 candidates snapshot 키 매핑
REPOLL_TO_CANDS = {
    "부산광역시북구갑":           ("부산광역시",       "북구갑"),
    "대구광역시달성군":           ("대구광역시",       "달성군"),
    "인천광역시연수구갑":         ("인천광역시",       "연수구갑"),
    "인천광역시계양구을":         ("인천광역시",       "계양구을"),
    "광주광역시광산구을":         ("광주광역시",       "광산구을"),
    "울산광역시남구갑":           ("울산광역시",       "남구갑"),
    "경기도평택시을":             ("경기도",          "평택시을"),
    "경기도안산시갑":             ("경기도",          "안산시갑"),
    "경기도하남시갑":             ("경기도",          "하남시갑"),
    "충청남도공주시부여군청양군": ("충청남도",        "공주시부여군청양군"),
    "충청남도아산시을":           ("충청남도",        "아산시을"),
    "전라북도군산시김제시부안군갑": ("전북특별자치도", "군산시김제시부안군갑"),
    "전라북도군산시김제시부안군을": ("전북특별자치도", "군산시김제시부안군을"),
    "제주특별자치도서귀포시":     ("제주특별자치도",  "서귀포시"),
}

N_SIM = 10_000
SEED = 42
RESIDUAL_SD = 6.0  # 보수적: 6%p — MBC SD 외 추가 모델 잡음

# 정당 진영 매핑 (정당명 기준)
PROGRESSIVE = {"더불어민주당", "조국혁신당", "진보당", "정의당", "기본소득당", "녹색당"}
CONSERVATIVE = {"국민의힘", "자유와혁신", "자유통일당", "공화당", "대한국민당"}

# 무소속 후보 중 진영 분류 (이름 기반 — 출마 정황상 명확한 경우)
CONSERVATIVE_INDEPS = {"한동훈"}     # 보수계 무소속
PROGRESSIVE_INDEPS = set()            # 진보계 무소속 (필요시 추가)


def camp_of(party: str, name: str) -> str:
    """'P'(progressive)/'C'(conservative)/'O'(other) 진영 분류."""
    if party in PROGRESSIVE:
        return "P"
    if party in CONSERVATIVE:
        return "C"
    if name in CONSERVATIVE_INDEPS:
        return "C"
    if name in PROGRESSIVE_INDEPS:
        return "P"
    return "O"


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


def load_9th_candidates() -> dict[str, list[dict]]:
    """우리 사이트 candidates snapshot에서 sgTypecode=2 후보 추출.
    반환: {consti(repoll 키): [{name, party}, ...], ...}
    9회 출마자 정확 매칭 — fallback에서 22대 후보 대신 9회 후보 이름 사용.
    """
    import glob
    snaps = sorted(glob.glob(str(CANDIDATES_DIR / "snapshot_*.json")))
    if not snaps:
        return {}
    d = json.load(open(snaps[-1], encoding="utf-8"))
    cands_by_sd_sgg: dict[tuple, list] = {}
    for c in d.get("candidates", []):
        if str(c.get("sgTypecode")) != "2":
            continue
        st = c.get("status") or ""
        if st and st not in ("등록", "확정"):
            continue
        key = (c.get("sdName"), c.get("sggName"))
        cands_by_sd_sgg.setdefault(key, []).append({
            "name": c.get("name") or c.get("hbjnm"),
            "party": c.get("jdName") or "",
        })
    return {consti: cands_by_sd_sgg.get(sd_sgg, []) for consti, sd_sgg in REPOLL_TO_CANDS.items()}


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


def extract_priors(boxplot_arr: list[dict], repoll_arr: list[dict], cands_9th: dict = None) -> list[dict]:
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

        # 모델: 진보 진영 1위 vs 보수 진영 1위 매치업
        # 진보 = 민주당·조국혁신당·진보당·정의당 등
        # 보수 = 국민의힘·자유와혁신·자유통일당 + 한동훈 같은 보수계 무소속
        # 기타(개혁신당 중도, 무소속 비분류)는 con·dem 어느 쪽도 안 됨
        if gdata:
            last = gdata[-1]
            prog_cands = []
            cons_cands = []
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
                camp = camp_of(party, name)
                if camp == "P":
                    prog_cands.append(entry)
                elif camp == "C":
                    cons_cands.append(entry)
            # 진영 1위 후보 매치업
            if prog_cands:
                dem = max(prog_cands, key=lambda x: x["mean"])
                # 진보 진영 2위 이상 후보가 있으면 메타 표시용
                others_p = [c for c in prog_cands if c is not dem]
                if others_p:
                    dem["others"] = others_p
            if cons_cands:
                con = max(cons_cands, key=lambda x: x["mean"])
                others_c = [c for c in cons_cands if c is not con]
                if others_c:
                    con["others"] = others_c

        # graph_data 없거나 부족하면 bar_data의 raw 여론조사 사용
        # 진영 1위 매치업으로 통일
        if (not dem or not con) and race.get("bar_data"):
            bar = race.get("bar_data") or []
            cand_party = {c["name"]: c["party"] for c in candis}
            # 후보명별 mean 누적
            per_cand_means = {}
            for bd in bar:
                for sv in (bd.get("survey_data") or []):
                    for name, vals in sv.items():
                        m = vals.get("mean")
                        if m is None:
                            continue
                        per_cand_means.setdefault(name, []).append(m)
            cand_avg = {n: sum(v)/len(v) for n, v in per_cand_means.items() if v}
            # 진영별 후보
            prog_picks = {n: m for n, m in cand_avg.items() if camp_of(cand_party.get(n, ""), n) == "P"}
            cons_picks = {n: m for n, m in cand_avg.items() if camp_of(cand_party.get(n, ""), n) == "C"}
            if prog_picks and cons_picks:
                dem_name = max(prog_picks, key=prog_picks.get)
                con_name = max(cons_picks, key=cons_picks.get)
                dem_party = cand_party[dem_name]
                con_party = cand_party[con_name]
                dem_vals = per_cand_means[dem_name]
                con_vals = per_cand_means[con_name]
                dem_mean = sum(dem_vals) / len(dem_vals)
                con_mean = sum(con_vals) / len(con_vals)
                # 조사 수 적을 때 SD 크게 (적은 표본은 불확실)
                base_sd = 4.0 if len(dem_vals) < 4 else 2.5
                dem_sd = (statistics.stdev(dem_vals) if len(dem_vals) >= 2 else base_sd)
                con_sd = (statistics.stdev(con_vals) if len(con_vals) >= 2 else base_sd)
                # SD 하한
                dem_sd = max(dem_sd, base_sd)
                con_sd = max(con_sd, base_sd)
                dem = {"name": dem_name, "party": dem_party,
                       "mean": round(dem_mean, 2), "sd": round(dem_sd, 2)}
                con = {"name": con_name, "party": con_party,
                       "mean": round(con_mean, 2), "sd": round(con_sd, 2)}
                # bar_data 사용 표시 (fallback과 구분)
                margin = dem["mean"] - con["mean"]
                margin_sd = (dem["sd"] ** 2 + con["sd"] ** 2) ** 0.5
                out.append({
                    "consti": consti,
                    "region1": region1,
                    "region2": region2,
                    "state_label": (state or "") + f" (raw 여론조사 {len(dem_vals)}회 평균)",
                    "last_date": None,
                    "dem": dem,
                    "con": con,
                    "margin": round(margin, 2),
                    "margin_sd": round(margin_sd, 2),
                    "fallback": False,
                    "bar_data_count": len(dem_vals),
                })
                continue

        if not dem or not con:
            # Fallback: 22대 결과 기반 + 9회 실제 후보(candidates snapshot)로 표시
            used_fallback = True
            elected = rep.get("elected_party") or rep.get("party")
            if elected in PROGRESSIVE:
                fb_margin = 18.0
                fb_sd = 4.0
            elif elected in CONSERVATIVE:
                fb_margin = -18.0
                fb_sd = 4.0
            else:
                fb_margin = 0.0
                fb_sd = 6.0
            # 9회 후보 명단에서 진영별 후보 찾기
            ninth = (cands_9th or {}).get(consti, [])
            dem_name = "—"; con_name = "—"; dem_party = "더불어민주당"; con_party = "국민의힘"
            # 9회 민주당 진영 후보
            for c in ninth:
                if camp_of(c.get("party",""), c.get("name","")) == "P":
                    dem_name = c.get("name") or dem_name
                    dem_party = c.get("party") or dem_party
                    break
            # 9회 비민주당 진영 후보
            for c in ninth:
                if camp_of(c.get("party",""), c.get("name","")) == "C":
                    con_name = c.get("name") or con_name
                    con_party = c.get("party") or con_party
                    break
            # 비민주당 진영 후보가 없으면 무소속 등 비민주당 1명 채택
            if con_name == "—":
                for c in ninth:
                    p = c.get("party") or ""
                    if p not in PROGRESSIVE:
                        con_name = c.get("name") or con_name
                        con_party = p or "무소속"
                        break
            dem = {"name": dem_name, "party": dem_party, "mean": None, "sd": None}
            con = {"name": con_name, "party": con_party, "mean": None, "sd": None}
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

    cands_9th = load_9th_candidates()
    priors = extract_priors(arr, repoll, cands_9th)
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
        "source": "2026-05-27까지 보도된 공개 여론조사 (언론 종합)",
        "model": "공개 여론조사 추정치 prior + Normal noise (residual SD 6%p)",
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
            "14개 선거구 각각 표본 적음 — 일부 선거구는 여론조사 자료 부족",
            "현직 이점·후보 효과·정당 변동 미반영",
            "5/27 이후 여론 변화 미반영 — 데이터 갱신 시 결과도 갱신",
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
    def other_cands_html(side):
        """진영 내 1위 외 다른 후보들 — 작은 메타 텍스트."""
        others = side.get("others") or []
        if not others:
            return ""
        parts = [f'<span style="color:#888;font-size:0.72rem">{o["name"]}({o["party"]}) {o["mean"]}%</span>'
                 for o in others]
        return "<br>" + " · ".join(parts)

    for p in races_sorted:
        prob_d = sim["race_dem_wins"].get(p["consti"], 0) / n
        d_pct = prob_d * 100
        r_pct = 100 - d_pct
        dem_mean = f"{p['dem']['mean']}%" if p['dem']['mean'] is not None else "—"
        con_mean = f"{p['con']['mean']}%" if p['con']['mean'] is not None else "—"
        fb_mark = ' <span style="font-size:0.7rem;color:#999">(자료 부족, 22대 결과 기반)</span>' if p.get("fallback") else ""
        dem_party = p['dem'].get('party') or ''
        con_party = p['con'].get('party') or ''
        dem_party_label = f' <span style="font-size:0.72rem;color:#888">{dem_party}</span>' if dem_party and dem_party != '더불어민주당' else ''
        con_party_label = f' <span style="font-size:0.72rem;color:#888">{con_party}</span>' if con_party and con_party != '국민의힘' else ''
        # 비민주당 1위가 무소속이면 회색, 국힘이면 빨강
        right_color = "#E61E2B" if con_party == '국민의힘' else "#888"
        right_class = "right-r" if con_party == '국민의힘' else "right-i"
        race_rows.append(f"""
        <tr>
          <td>{p['region1']}</td>
          <td class="sgg">{p['region2']}{fb_mark}</td>
          <td>{p['dem']['name']}{dem_party_label}<br><span class="party-d">{dem_mean}</span>{other_cands_html(p['dem'])}</td>
          <td>{p['con']['name']}{con_party_label}<br><span class="{right_class}">{con_mean}</span>{other_cands_html(p['con'])}</td>
          <td class="margin">{p['margin']:+.1f}%p</td>
          <td>
            <div class="stacked-bar">
              <span class="stacked-d" style="width:{d_pct:.0f}%" title="민주당 진영 {d_pct:.0f}%"></span>
              <span style="background:{right_color};width:{r_pct:.0f}%;height:100%;display:block" title="{con_party or '비민주당'} {r_pct:.0f}%"></span>
            </div>
            <div style="font-size:0.74rem;margin-top:2px;font-variant-numeric:tabular-nums">
              <span class="num-d">{d_pct:.0f}%</span> · <span style="color:{right_color};font-weight:700">{r_pct:.0f}%</span>
            </div>
          </td>
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

    DISCLAIMER = ""  # build_sim_site.py가 상단에 공통 안내문을 자동 삽입

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
@media (max-width: 720px) {{
  .charts {{ grid-template-columns: 1fr; }}
  body {{ padding: 14px 12px; }}
  h1 {{ font-size: 1.2rem; }}
  .pill {{ padding: 10px 12px; min-width: 150px; }}
  .pill .val {{ font-size: 1.35rem; }}
  table.races {{ font-size: 0.72rem; }}
  table.races th, table.races td {{ padding: 5px 4px; }}
  .stacked-bar {{ min-width: 70px; max-width: 100px; height: 10px; }}
  .state {{ font-size: 0.68rem; }}
  table.races th:last-child, table.races td:last-child {{ display: none; }}
}}
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
.right-r {{ color: #E61E2B; font-weight: 700; font-variant-numeric: tabular-nums; }}
.right-i {{ color: #888; font-weight: 700; font-variant-numeric: tabular-nums; }}
.margin {{ font-variant-numeric: tabular-nums; font-weight: 600; }}
.state {{ font-size: 0.78rem; color: #777; }}
.stacked-bar {{ display: flex; height: 12px; border-radius: 3px; overflow: hidden; background: #f0f0f0; min-width: 100px; max-width: 160px; }}
.stacked-d {{ background: #152484; height: 100%; }}
.num-d {{ color: #152484; font-weight: 700; }}
.limits {{ background: #f6f6f6; padding: 14px 20px; border-radius: 4px; margin-top: 28px; font-size: 0.85rem; }}
.limits h2 {{ font-size: 1rem; margin: 0 0 8px; }}
.limits ul {{ margin: 0; padding-left: 20px; color: #555; }}
</style></head><body>
{DISCLAIMER}
<h1>9회 동시 국회의원 재·보궐 14개 선거구 시뮬레이션</h1>
<p class="sub">2026-05-27 기준 · 5/27까지 보도된 공개 여론조사 참고 + 1만 회 시뮬레이션 · 시민언론 뉴탐사</p>

<div class="summary-pills">
  <div class="pill d"><span class="lbl">민주당</span> <strong class="val">{r['dem_mode']}석</strong><p class="sub">예상 범위 {r['dem_80_ci'][0]}~{r['dem_80_ci'][1]}석</p></div>
  <div class="pill r"><span class="lbl">국힘·무소속 등</span> <strong class="val">{r['con_mode']}석</strong><p class="sub">예상 범위 {r['con_80_ci'][0]}~{r['con_80_ci'][1]}석</p></div>
</div>

<div class="charts">{dem_chart}{con_chart}</div>

<section>
  <h2 style="font-size:1.1rem">14개 선거구별 민주당 승리 확률</h2>
  <p style="color:#666;font-size:0.84rem;margin:0 0 8px"><strong>민주당 진영 1위 vs 비민주당 진영 1위</strong> 매치업.<br>민주당 진영 = 더불어민주당·조국혁신당·진보당·정의당. 비민주당 진영 = 국민의힘·자유와혁신·자유통일당 + 한동훈(비민주당 무소속). 작은 글자는 같은 진영의 2위 이상 후보.</p>
  <table class="races">
    <thead><tr><th>시도</th><th>선거구</th><th>민주당 진영 1위</th><th>비민주당 진영 1위</th><th>격차</th><th>민주당 승리 확률</th><th>분류</th></tr></thead>
    <tbody>{rows_html}</tbody>
  </table>
</section>

<section class="limits"><h2>모델 한계</h2><ul>{limits}</ul></section>
</body></html>
"""
    (OUT_DIR / "index.html").write_text(html, encoding="utf-8")


if __name__ == "__main__":
    main()
