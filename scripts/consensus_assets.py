# -*- coding: utf-8 -*-
"""평가액 3개 해상도(150·200·300dpi) OCR을 '다수결 합의'로 자동 확정.

단일 OCR은 큰 금액을 종종 오독한다(예: 150dpi가 최기영 80.1억을 29.8억으로).
서로 독립적인 3개 해상도 중 2개 이상이 일치(±2%)하면 그 값을 자동 채택 → 사람 확인 불필요.
모두 어긋나면 중앙값(median)을 best-estimate로 쓰고 confidence=low로 표시(소수만 남음).

출력: data/asset_value_consensus.json
  { huboid: {value_thousand, confidence(high/mid/low), votes:[...], n_ocr} }
사용: python scripts/consensus_assets.py
"""
import json
from pathlib import Path
from statistics import median

ROOT = Path(__file__).resolve().parent.parent
SRC = {  # 해상도 → 파일
    150: ROOT / "data" / "asset_value_150.json",
    200: ROOT / "data" / "asset_value.json",
    300: ROOT / "data" / "asset_value_300.json",
}
OUT = ROOT / "data" / "asset_value_consensus.json"
TOL = 0.02   # ±2% 이내 = 일치


def load(p):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def agree(a, b):
    if not a or not b:
        return False
    return abs(a - b) / max(a, b) <= TOL


def main():
    data = {dpi: load(p) for dpi, p in SRC.items()}
    avail = {dpi: d for dpi, d in data.items() if d}
    print("로드:", {dpi: len(d) for dpi, d in avail.items()})
    huboids = set()
    for d in avail.values():
        huboids |= set(d)

    out, by_conf = {}, {"high": 0, "mid": 0, "low": 0}
    for hb in huboids:
        votes = {}
        for dpi, d in avail.items():
            v = (d.get(hb) or {}).get("value_thousand") if isinstance(d.get(hb), dict) else None
            if v:
                votes[dpi] = v
        if not votes:
            continue
        vals = list(votes.values())
        # 일치 클러스터(2개 이상) 찾기
        best_cluster = []
        for i, vi in enumerate(vals):
            cl = [vj for vj in vals if agree(vi, vj)]
            if len(cl) > len(best_cluster):
                best_cluster = cl
        if len(best_cluster) >= 2:
            value = round(sum(best_cluster) / len(best_cluster))
            conf = "high" if len(best_cluster) >= 3 else "mid"
        else:
            value = round(median(vals))           # 합의 실패 → 중앙값
            conf = "low"
        # 메타(이름 등)는 아무 소스에서나
        meta = {}
        for d in avail.values():
            if isinstance(d.get(hb), dict):
                meta = d[hb]; break
        out[hb] = {"name": meta.get("name"), "office": meta.get("office"),
                   "party": meta.get("party"), "sido": meta.get("sido"),
                   "value_thousand": value, "confidence": conf,
                   "votes": votes, "n_ocr": len(votes)}
        by_conf[conf] += 1

    OUT.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"합의 완료: {len(out)}명 · high {by_conf['high']} · mid {by_conf['mid']} · low {by_conf['low']}")
    print(f"자동확정(high+mid): {by_conf['high']+by_conf['mid']} "
          f"({(by_conf['high']+by_conf['mid'])/max(1,len(out))*100:.0f}%) → {OUT.name}")
    lows = sorted([v for v in out.values() if v["confidence"] == "low"],
                  key=lambda x: -(x["value_thousand"] or 0))[:10]
    if lows:
        print("\n합의 실패(low) 상위 — 원본 확인 권장:")
        for v in lows:
            print(f"  {v['name']:6s} 중앙값 {(v['value_thousand'] or 0)/100000:6.1f}억  votes={ {k:round(x/100000,1) for k,x in v['votes'].items()} }")


if __name__ == "__main__":
    main()
