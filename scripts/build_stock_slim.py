# -*- coding: utf-8 -*-
"""raw OCR 결과(data/stock_holdings.json) → 공개 슬림본(stocks/stock_holdings.json).

raw에는 raw_section(원문 OCR 전문) 등 비공개·대용량 필드가 있어 공개본에서 제거한다.
사진은 candidate_details.json의 thumbnail_url(https)로 채운다.
이후 scripts/build_stock_watch.py가 won/이해충돌 카테고리/통계를 덧붙인다.

사용: python scripts/build_stock_slim.py
"""
import json, sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RAW = ROOT / "data" / "stock_holdings.json"
DET = ROOT / "data" / "candidate_details.json"
OUT = ROOT / "stocks" / "stock_holdings.json"


def photo_map():
    det = json.loads(DET.read_text(encoding="utf-8")).get("details", [])
    m = {}
    for d in det:
        ph = d.get("photo") or {}
        url = ph.get("thumbnail_url") or ph.get("url")
        if url:
            m[str(d.get("huboid"))] = url.replace("http://", "https://")
    return m


def main():
    raw = json.loads(RAW.read_text(encoding="utf-8"))
    photos = photo_map()
    people = []
    for p in raw.get("people", []):
        people.append({
            "huboid": p["huboid"],
            "name": p.get("name"),
            "party": p.get("party") or "무소속",
            "office": p.get("office"),
            "sido": p.get("sido"),
            "sgg": p.get("sgg") or "",
            "needs_review": bool(p.get("needs_review")),
            "holdings": [{"종목": h["종목"], "수량주": h["수량주"]} for h in p.get("holdings", [])],
            "photo": photos.get(str(p["huboid"]), ""),
        })
    out = {
        "generated": raw.get("generated"),
        "count": len(people),
        "clean": sum(1 for p in people if p["holdings"]),
        "review_only": sum(1 for p in people if not p["holdings"]),
        "note": "당선자 재산신고서 OCR 자동추출(슬림 공개본). 카테고리·통계는 build_stock_watch.py가 덧붙임.",
        "people": people,
    }
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    nphoto = sum(1 for p in people if p["photo"])
    print(f"슬림본 {len(people)}명 (보유 {out['clean']} · 사진 {nphoto}) → {OUT}", file=sys.stderr)


if __name__ == "__main__":
    main()
