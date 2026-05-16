#!/usr/bin/env python3
"""
행정동 GeoJSON에서 주소 자동추천용 경량 인덱스를 만든다.

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
OUT_FILE = ROOT / "data" / "address_index.json"


def latest_geojson() -> Path:
    files = sorted(RAW_DIR.glob("HangJeongDong_*.geojson"))
    if not files:
        sys.exit(f"행정동 GeoJSON이 없습니다: {RAW_DIR}")
    return files[-1]


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
    OUT_FILE.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"주소 인덱스: {len(rows):,}개 -> {OUT_FILE.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
