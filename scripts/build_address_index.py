#!/usr/bin/env python3
"""
행정동 GeoJSON과 후보자 주소에서 주소 자동추천용 경량 인덱스를 만든다.

산출물:
    data/address_index.json
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "geo" / "raw"
CANDIDATE_DIR = ROOT / "data" / "candidates" / "20260603"
OUT_FILE = ROOT / "data" / "address_index.json"


def latest_geojson() -> Path:
    files = sorted(RAW_DIR.glob("HangJeongDong_*.geojson"))
    if not files:
        sys.exit(f"행정동 GeoJSON이 없습니다: {RAW_DIR}")
    return files[-1]


def latest_candidate_snapshot() -> Path | None:
    files = sorted(CANDIDATE_DIR.glob("snapshot_*.json"))
    return files[-1] if files else None


def emd_name(adm_nm: str, sgg_nm: str) -> str:
    parts = adm_nm.split()
    if len(parts) <= 2:
        return parts[-1] if parts else ""
    sgg_parts = sgg_nm.split()
    skip = 1 + len(sgg_parts)
    return " ".join(parts[skip:]) or parts[-1]


def display_sgg_name(sgg_nm: str) -> str:
    if " " in sgg_nm:
        return sgg_nm
    match = re.match(r"^(.+시)(.+구)$", sgg_nm)
    if match:
        return f"{match.group(1)} {match.group(2)}"
    return sgg_nm


def is_road_token(token: str) -> bool:
    text = re.sub(r"[^\w가-힣·.-]", "", token.strip())
    if len(text) < 2:
        return False
    return bool(
        re.search(r"(대로|로|길)$", text)
        or re.search(r"(대로|로)\d", text)
        or re.search(r"(대로|로)[가-힣A-Za-z]*\d.*길$", text)
    )


def strip_road_local_tail(parts: list[str]) -> list[str]:
    out = parts[:]
    while out and re.search(r"(읍|면|동|리|가)$", out[-1]):
        out.pop()
    return out


def road_parts(addr: str, sido_names: set[str]) -> tuple[str, str, str] | None:
    parts = [p.strip() for p in str(addr or "").split() if p.strip()]
    if len(parts) < 2 or parts[0] not in sido_names:
        return None

    road_idx = -1
    for i in range(len(parts) - 1, 0, -1):
        if is_road_token(parts[i]):
            road_idx = i
            break
    if road_idx < 1:
        return None

    sd = parts[0]
    road = re.sub(r"[^\w가-힣·.-]", "", parts[road_idx].strip())
    middle = strip_road_local_tail(parts[1:road_idx])
    if sd == "세종특별자치시" and not middle:
        sgg = "세종시"
    elif len(middle) >= 2 and middle[-1].endswith("구") and middle[-2].endswith("시"):
        sgg = f"{middle[-2]} {middle[-1]}"
    elif middle:
        sgg = middle[-1]
    else:
        return None

    return sd, display_sgg_name(sgg), road


def road_rows(sido_names: set[str]) -> list[dict]:
    source = latest_candidate_snapshot()
    if not source:
        return []

    payload = json.loads(source.read_text(encoding="utf-8"))
    roads: dict[tuple[str, str, str], int] = {}
    for cand in payload.get("candidates", []):
        parts = road_parts(cand.get("addr", ""), sido_names)
        if not parts:
            continue
        roads[parts] = roads.get(parts, 0) + 1

    rows = []
    for (sd, sgg, road), count in roads.items():
        rows.append({
            "sdName": sd,
            "sggName": sgg,
            "emdName": road,
            "roadName": road,
            "fullName": f"{sd} {sgg} {road}",
            "code": "",
            "kind": "road",
            "sourceCount": count,
        })
    rows.sort(key=lambda r: (r["sdName"], r["sggName"], r["roadName"]))
    return rows


def main() -> None:
    source = latest_geojson()
    payload = json.loads(source.read_text(encoding="utf-8"))
    features = payload.get("features", [])
    rows = []
    seen = set()

    for feat in features:
        props = feat.get("properties", {})
        sd = props.get("sidonm", "")
        raw_sgg = props.get("sggnm", "")
        sgg = display_sgg_name(raw_sgg)
        adm = props.get("adm_nm", "")
        emd = emd_name(adm, raw_sgg)
        code = str(props.get("adm_cd2") or props.get("adm_cd") or "")
        if not (sd and sgg and emd and code):
            continue
        key = (sd, sgg, emd, code)
        if key in seen:
            continue
        seen.add(key)
        rows.append({
            "sdName": sd,
            "sggName": sgg,
            "emdName": emd,
            "fullName": f"{sd} {sgg} {emd}",
            "code": code,
        })

    rows.sort(key=lambda r: (r["sdName"], r["sggName"], r["emdName"], r["code"]))
    road_index = road_rows({r["sdName"] for r in rows})
    rows.extend(road_index)
    OUT_FILE.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(
        f"주소 인덱스: {len(rows) - len(road_index):,}개 행정동"
        f" + {len(road_index):,}개 도로명 -> {OUT_FILE.relative_to(ROOT)}"
    )


if __name__ == "__main__":
    main()
