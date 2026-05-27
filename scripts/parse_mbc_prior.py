#!/usr/bin/env python3
"""
MBC 여론M 사이트(poll-mbc.co.kr)에서 다운로드한 16개 시도의 베이지안 추정치를
시뮬레이션 prior로 변환.

입력:
    tmp/mbc/Seoul_approve.js ~ Jeju_approve.js
    tmp/mbc/candidate_info.js

처리:
    1) 각 시도별로 .js 파일 안의 var X_approve = [...] 배열 파싱
    2) 가장 최근 date 항목 = MBC가 추정한 현재 시점 후보별 지지율
    3) candidate_info의 정당 매핑으로 (민주 후보 mean) - (국힘 후보 mean) = 시도 margin
    4) uncertainty = (upper - lower) / 4 정도 (95% CI 변환)

출력:
    data/mbc_prior.json  (시뮬에서 import해서 prior로 사용)

법적 주의:
    이 데이터는 시뮬레이션 모델의 prior로만 사용하며 사이트에 직접 표시 X.
    여론조사 결과의 인용보도가 아닌 모델 내부 변수 처리.
"""

from __future__ import annotations

import json
import re
import statistics
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MBC = ROOT / "tmp" / "mbc"
OUT = ROOT / "data" / "mbc_prior.json"

# en 파일명 → 한국어 시도명 (사이트 변수명에 맞춤)
SIDOS_EN_KO = {
    "Seoul": "서울특별시", "Busan": "부산광역시", "Daegu": "대구광역시",
    "Incheon": "인천광역시", "Daejeon": "대전광역시", "Ulsan": "울산광역시",
    "Sejong": "세종특별자치시", "Gyeonggi": "경기도",
    "Gangwon": "강원특별자치도", "Chungbuk": "충청북도", "Chungnam": "충청남도",
    "Jeonbuk": "전북특별자치도", "Gyeongbuk": "경상북도",
    "Gyeongnam": "경상남도", "Jeju": "제주특별자치도",
    # JeonnamGwangju 빈 응답이라 후처리에서 별도 다룸
}

PROGRESSIVE = {"더불어민주당"}
CONSERVATIVE = {"국민의힘"}


def _clean_js_to_json(raw: str) -> str:
    """JS literal을 JSON으로 정리: 빈 element(,,) 제거 + trailing comma 제거."""
    # 빈 element: `, ,` → `,`
    while re.search(r",(\s*),(\s*[\[{])", raw):
        raw = re.sub(r",(\s*),(\s*[\[{])", r",\2", raw)
    # `[,` 또는 `, ]` 같은 빈 첫/끝 element
    raw = re.sub(r"\[(\s*),", r"[", raw)
    raw = re.sub(r",(\s*\])", r"\1", raw)
    raw = re.sub(r",(\s*\})", r"\1", raw)
    return raw


def parse_js_array(text: str) -> list:
    """var X = [ ... ]; 형식에서 JSON 배열 부분 추출."""
    m = re.search(r"=\s*(\[.*?\])\s*;?\s*$", text.strip(), re.DOTALL)
    if not m:
        return []
    raw = m.group(1)
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        raw2 = _clean_js_to_json(raw)
        try:
            return json.loads(raw2)
        except Exception:
            return []


def load_candidate_info() -> dict[str, dict[str, str]]:
    """이름 → 정당 매핑 (시도별)."""
    text = (MBC / "candidate_info.js").read_text(encoding="utf-8")
    m = re.search(r"=\s*(\{.*\})\s*;?\s*$", text.strip(), re.DOTALL)
    if not m:
        return {}
    raw = m.group(1)
    try:
        d = json.loads(raw)
    except json.JSONDecodeError:
        d = json.loads(_clean_js_to_json(raw))
    out = {}
    for sido, cands in d.items():
        out[sido] = {c["name"]: c["party"] for c in cands if c.get("name")}
    return out


def latest_estimate(arr: list) -> dict | None:
    """date 기준 가장 최근 다자 entry."""
    if not arr:
        return None
    # type='다자'만 (일부 양자 entry 있을 수 있음)
    cand = [e for e in arr if e.get("type") in (None, "다자")]
    if not cand:
        cand = arr
    cand.sort(key=lambda e: e.get("date", ""))
    return cand[-1]


def margin_for_sido(entry: dict, name_party: dict[str, str]) -> dict | None:
    """가장 최근 추정에서 (민주 mean - 국힘 mean) 계산. uncertainty 합산."""
    if not entry:
        return None
    dem_mean = dem_unc = con_mean = con_unc = None
    dem_name = con_name = None
    for c in entry.get("approve", []):
        nm = c.get("name", "")
        if nm in ("없음", "기타", ""):
            continue
        party = name_party.get(nm)
        mean = c.get("mean")
        unc = (c.get("upper", 0) - c.get("lower", 0)) / 4  # 95% CI → 1σ 근사
        if party in PROGRESSIVE:
            dem_mean = mean
            dem_unc = unc
            dem_name = nm
        elif party in CONSERVATIVE:
            con_mean = mean
            con_unc = unc
            con_name = nm
    if dem_mean is None or con_mean is None:
        return None
    return {
        "date": entry.get("date"),
        "dem_candidate": dem_name,
        "con_candidate": con_name,
        "dem_share": round(dem_mean, 2),
        "con_share": round(con_mean, 2),
        "margin": round(dem_mean - con_mean, 2),
        # 두 후보 SD 합성 (독립 가정)
        "margin_sd": round((dem_unc ** 2 + con_unc ** 2) ** 0.5, 2),
    }


def main():
    name_party = load_candidate_info()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    sido_prior = {}
    for en, ko in SIDOS_EN_KO.items():
        path = MBC / f"{en}_approve.js"
        if not path.exists():
            continue
        arr = parse_js_array(path.read_text(encoding="utf-8"))
        if not arr:
            continue
        latest = latest_estimate(arr)
        cand_map = name_party.get(ko, {})
        m = margin_for_sido(latest, cand_map)
        if m:
            sido_prior[ko] = m

    payload = {
        "generated_at": "2026-05-27",
        "source": "poll-mbc.co.kr region_data/approve_data/*.js (베이지안 상태공간 모형)",
        "note": "각 시도 가장 최근(다자) 추정치에서 더불어민주당 - 국민의힘 mean 차이",
        "sido_prior": sido_prior,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"저장: {OUT.relative_to(ROOT)}  ({len(sido_prior)}개 시도)")
    print()
    for ko, p in sorted(sido_prior.items(), key=lambda x: -x[1]["margin"]):
        sign = "+" if p["margin"] >= 0 else ""
        winner = "D" if p["margin"] > 0 else "R"
        print(f"  {ko:14s}  {p['dem_candidate']:>5s}({p['dem_share']:5.1f}%) vs "
              f"{p['con_candidate']:>5s}({p['con_share']:5.1f}%)  "
              f"margin {sign}{p['margin']:+6.1f}%p ± {p['margin_sd']:4.1f}  [{winner}]")


if __name__ == "__main__":
    main()
