#!/usr/bin/env python3
"""
충청남도 prior만 5월 27일까지 보도된 5개 여론조사 시간가중 평균으로 업데이트.
다른 시도는 건드리지 않음.

가중치: half-life 7일 exponential decay
margin_sd: sqrt(시계열 가중분산 + 측정오차분산)
"""

from __future__ import annotations

import json
import math
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PRIOR = ROOT / "data" / "mbc_prior.json"

TODAY = date(2026, 5, 27)
HALF_LIFE_DAYS = 7.0
MEASUREMENT_SE = 5.0  # 양당 격차 측정 잡음(%p) — 한 조사 표본오차 ±3.5%p의 격차 변환

# 5/27까지 보도된 5개 충남도지사 조사 (사용자 명세 그대로)
POLLS = [
    {
        "date_start": "2026-04-26", "date_end": "2026-04-28",
        "client": "KBS대전총국", "house": "한국리서치",
        "method": "전화면접", "n": 800, "response_rate": "17.4%", "error": "±3.5%p (95% CI)",
        "dem_share": 44.0, "con_share": 23.0, "margin": 21.0,
    },
    {
        "date_start": "2026-05-08", "date_end": "2026-05-09",
        "client": "굿모닝충청", "house": "리얼미터",
        "method": "ARS", "n": 805, "response_rate": "8.0%", "error": "±3.5%p",
        "dem_share": 50.1, "con_share": 37.3, "margin": 12.8,
    },
    {
        "date_start": "2026-05-15", "date_end": "2026-05-17",
        "client": "대전MBC·충청투데이", "house": "코리아리서치인터내셔널",
        "method": "전화면접", "n": 800, "response_rate": "14.4%", "error": "±3.5%p",
        "dem_share": 45.0, "con_share": 37.0, "margin": 8.0,
    },
    {
        "date_start": "2026-05-16", "date_end": "2026-05-20",
        "client": "KBS", "house": "한국리서치",
        "method": "전화면접", "n": 800, "response_rate": "20.8%", "error": "±3.5%p",
        "dem_share": 41.0, "con_share": 37.0, "margin": 4.0,
    },
    {
        "date_start": "2026-05-18", "date_end": "2026-05-19",
        "client": "뉴스핌", "house": "리얼미터",
        "method": "ARS", "n": 806, "response_rate": "8.2%", "error": "±3.5%p",
        "dem_share": 43.5, "con_share": 43.9, "margin": -0.4,
    },
]


def midpoint_date(p):
    s = date.fromisoformat(p["date_start"])
    e = date.fromisoformat(p["date_end"])
    return s + (e - s) / 2


def main():
    lam = math.log(2) / HALF_LIFE_DAYS
    weights = []
    for p in POLLS:
        mid = midpoint_date(p)
        days = (TODAY - mid).days + ((TODAY - mid).seconds / 86400)  # 정확도
        w = math.exp(-lam * days)
        weights.append((p, days, w))

    total_w = sum(w for _, _, w in weights)

    print(f"=== 시간가중치 (today={TODAY}, half-life={HALF_LIFE_DAYS}일) ===")
    for p, d, w in weights:
        print(f"  {p['date_start']}~{p['date_end']}  중간일까지 {d:.1f}일 전  가중치 {w/total_w*100:.1f}%")

    dem_avg = sum(p["dem_share"] * w for p, _, w in weights) / total_w
    con_avg = sum(p["con_share"] * w for p, _, w in weights) / total_w
    margin_avg = dem_avg - con_avg

    # 가중 분산 (margin 시계열)
    var_w = sum((p["margin"] - margin_avg) ** 2 * w for p, _, w in weights) / total_w
    # 측정오차 합쳐서
    sd_combined = math.sqrt(var_w + MEASUREMENT_SE ** 2)

    print(f"\n=== 시간가중 평균 ===")
    print(f"  민주당 박수현 : {dem_avg:.2f}%")
    print(f"  국힘 김태흠   : {con_avg:.2f}%")
    print(f"  격차          : {margin_avg:+.2f}%p")
    print(f"  margin_sd     : {sd_combined:.2f}%p  (시계열 분산 {var_w:.2f} + 측정오차 분산 {MEASUREMENT_SE**2})")

    # mbc_prior.json 업데이트 — 충남만
    prior = json.loads(PRIOR.read_text(encoding="utf-8"))
    old = prior.get("sido_prior", {}).get("충청남도", {})
    new = {
        "date": TODAY.isoformat(),
        "dem_candidate": "박수현",
        "dem_party": "더불어민주당",
        "con_candidate": "김태흠",
        "con_party": "국민의힘",
        "dem_share": round(dem_avg, 2),
        "con_share": round(con_avg, 2),
        "margin": round(margin_avg, 2),
        "margin_sd": round(sd_combined, 2),
        "source_polls": [
            {
                "date_start": p["date_start"], "date_end": p["date_end"],
                "client": p["client"], "house": p["house"], "method": p["method"],
                "n": p["n"], "response_rate": p["response_rate"], "error": p["error"],
                "margin": p["margin"],  # 격차만 — dem_share/con_share는 5/28~6/3 인용 금지 대비 제외
            }
            for p in POLLS
        ],
    }
    prior["sido_prior"]["충청남도"] = new
    prior["chungnam_updated_at"] = TODAY.isoformat() + " (5개 조사 시간가중 평균)"
    PRIOR.write_text(json.dumps(prior, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n저장: {PRIOR.relative_to(ROOT)}")
    print(f"\n=== 신구 비교 ===")
    print(f"  구: 격차 {old.get('margin','?')}%p, sd {old.get('margin_sd','?')}%p")
    print(f"  신: 격차 {new['margin']:+.2f}%p, sd {new['margin_sd']}%p")


if __name__ == "__main__":
    main()
