# -*- coding: utf-8 -*-
"""무투표 당선 기초단체장 3곳을 current.json에 보완 추가.

광주 서구·남구, 경기 시흥시는 단독후보 무투표 당선이라 개표가 없어
라이브 수집(개표 API)에서 빠졌다. 후보등록 데이터의 단독 당선자를 무투표 race로 추가.
votes=None → 사이트가 '무투표 당선'으로 렌더. idempotent(이미 있으면 건너뜀).
사용: python scripts/add_uncontested_heads.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CUR = ROOT / "data" / "live_counting" / "current.json"

# 후보등록 스냅샷에서 확인한 단독(무투표) 당선자
UNCONTESTED = [
    ("광주광역시", "서구", "김이강", "더불어민주당"),
    ("광주광역시", "남구", "김병내", "더불어민주당"),
    ("경기도", "시흥시", "임병택", "더불어민주당"),
]


def main():
    c = json.loads(CUR.read_text(encoding="utf-8"))
    have = {(str(r.get("sg_type_code")), r.get("sd_name"), r.get("sgg_name")) for r in c["races"]}
    added = 0
    for sd, sgg, name, party in UNCONTESTED:
        if ("4", sd, sgg) in have:
            continue
        c["races"].append({
            "race_key": f"4|{sd}|{sgg}", "sg_type_code": "4", "sg_type_label": "기초단체장",
            "sd_name": sd, "sgg_name": sgg, "wiw_name": None,
            "eligible_voters": None, "valid_votes": None, "invalid_votes": None,
            "progress_pct": 100.0, "rank1_minus_rank2_pp": None, "uncontested": True,
            "candidates": [{"name": name, "jd_name": party, "votes": None,
                            "share_pct": None, "current_rank": 1}],
        })
        added += 1
        print(f"  추가: {sd} {sgg} 무투표 당선 {name}({party})")
    if added:
        CUR.write_text(json.dumps(c, ensure_ascii=False), encoding="utf-8")
    n4 = sum(1 for r in c["races"] if str(r.get("sg_type_code")) == "4")
    print(f"추가 {added}건 · 기초단체장 총 {n4}곳")


if __name__ == "__main__":
    main()
