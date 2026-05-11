#!/usr/bin/env python3
"""
행정구역 GeoJSON 수집 + 시도/시군구 단위 dissolve.

데이터 소스: vuski/admdongkor (ver20260201, 2026.2.1 기준)

사용:
    pip install -r requirements.txt
    python scripts/fetch_geo.py

산출물:
    data/geo/raw/HangJeongDong_ver20260201.geojson
    site/assets/geo/sido.geojson      (17개)
    site/assets/geo/sigungu.geojson   (~260개)
"""

from __future__ import annotations

import json
from pathlib import Path
from urllib.request import urlretrieve

from shapely.geometry import mapping, shape
from shapely.ops import unary_union

VERSION = "ver20260201"
SOURCE_URL = (
    f"https://raw.githubusercontent.com/vuski/admdongkor/master/"
    f"{VERSION}/HangJeongDong_{VERSION}.geojson"
)

ROOT = Path(__file__).resolve().parent.parent
RAW_DIR = ROOT / "data" / "geo" / "raw"
OUT_DIR = ROOT / "site" / "assets" / "geo"

SIMPLIFY_TOLERANCE = {
    "sido": 0.001,
    "sigungu": 0.0003,
}


def download_source() -> Path:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    target = RAW_DIR / f"HangJeongDong_{VERSION}.geojson"

    if target.exists():
        size_mb = target.stat().st_size / (1024 * 1024)
        print(f"  이미 받아져 있음: {target.name} ({size_mb:.1f} MB)")
        return target

    print(f"  다운로드: {SOURCE_URL}")
    urlretrieve(SOURCE_URL, target)
    size_mb = target.stat().st_size / (1024 * 1024)
    print(f"  완료: {target.name} ({size_mb:.1f} MB)")
    return target


def dissolve(features, code_len, simplify):
    groups = {}
    name_map = {}

    for feat in features:
        props = feat["properties"]
        adm_cd = str(props.get("adm_cd", ""))
        adm_nm = str(props.get("adm_nm", ""))

        if len(adm_cd) < code_len:
            continue

        key = adm_cd[:code_len]
        groups.setdefault(key, []).append(shape(feat["geometry"]))

        parts = adm_nm.split(" ")
        if code_len == 2:
            name_map[key] = parts[0] if parts else ""
        elif code_len == 5:
            name_map[key] = " ".join(parts[:2]) if len(parts) >= 2 else parts[0]

    result = []
    for key in sorted(groups.keys()):
        merged = unary_union(groups[key])
        if simplify > 0:
            merged = merged.simplify(simplify, preserve_topology=True)
        result.append({
            "type": "Feature",
            "properties": {
                "code": key,
                "name": name_map.get(key, ""),
            },
            "geometry": mapping(merged),
        })

    return result


def save_geojson(path, features):
    path.parent.mkdir(parents=True, exist_ok=True)
    fc = {"type": "FeatureCollection", "features": features}
    path.write_text(json.dumps(fc, ensure_ascii=False), encoding="utf-8")
    size_mb = path.stat().st_size / (1024 * 1024)
    print(f"  → {path.relative_to(ROOT)} ({len(features)}개, {size_mb:.2f} MB)")


def main():
    print("=" * 60)
    print(f"행정구역 GeoJSON 수집 + dissolve ({VERSION})")
    print("=" * 60)

    print("\n[1/3] 원본 다운로드")
    source = download_source()

    print("\n[2/3] 행정동 데이터 로드")
    geojson = json.loads(source.read_text(encoding="utf-8"))
    features = geojson.get("features", [])
    print(f"  행정동: {len(features):,}개")

    print("\n[3/3] dissolve + simplify")
    print(f"  시도 (앞 2자리, tolerance={SIMPLIFY_TOLERANCE['sido']})")
    sido = dissolve(features, 2, SIMPLIFY_TOLERANCE["sido"])
    save_geojson(OUT_DIR / "sido.geojson", sido)

    print(f"  시군구 (앞 5자리, tolerance={SIMPLIFY_TOLERANCE['sigungu']})")
    sigungu = dissolve(features, 5, SIMPLIFY_TOLERANCE["sigungu"])
    save_geojson(OUT_DIR / "sigungu.geojson", sigungu)

    print(f"\n완료. 산출물: {OUT_DIR.relative_to(ROOT)}/")


if __name__ == "__main__":
    main()
