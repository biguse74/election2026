# -*- coding: utf-8 -*-
"""주식 평가액 자동 검수(기자 수동 검토 없이 의심값 자동 적발).

서로 독립적인 신호를 교차해 각 인물에 신뢰도 등급을 매기고 리포트를 남긴다.
사이트 데이터는 건드리지 않는다(리포트 전용).

검사:
  ① 2차 독립 OCR 대조 — 1차(200dpi)와 2차(150dpi) 추출값을 비교.
       두 독립 읽기가 어긋나면(상대오차 큼) OCR 불안정 → 의심.
  ② 수량↔가액 혼입 — 보유종목 수량주에 1천만주 초과(마이크론 6백만주 class)가 있으면
       가액칸이 수량칸으로 밀렸을 가능성 → 평가액도 의심.
  ③ 이상치/비율 — 종목당 평가액이 비정상적으로 크거나 상위 고액이면 점검 권장.

등급:
  확인필요  — 2차 대조 20%↑ 불일치 · 수량혼입 동반 · 한쪽만 추출됐는데 고액
  주의      — 2차 대조 2~20% 불일치 · 부분추출 · 중간 이상치
  정상      — 2차 대조 2% 이내 일치

사용:  python scripts/audit_stocks.py
출력:  data/stock_audit.json (요약+의심목록) · data/stock_audit_suspects.csv (기자 점검용)
"""
import csv
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SLIM = ROOT / "stocks" / "stock_holdings.json"
AV1 = ROOT / "data" / "asset_value.json"           # 1차 200dpi
AV2 = ROOT / "data" / "asset_value_150.json"       # 2차 150dpi
OUT_JSON = ROOT / "data" / "stock_audit.json"
OUT_CSV = ROOT / "data" / "stock_audit_suspects.csv"

# 임계값
AGREE_TOL = 0.02       # 2% 이내 = 일치
WARN_TOL = 0.20        # 2~20% = 주의, 20%↑ = 확인필요
QTY_BLEED = 10_000_000  # 1천만주 초과 = 수량↔가액 혼입 의심
BIG_VALUE = 3_000_000  # 30억(천원) 이상 = 고액(원본 점검 권장)
PER_STOCK_HIGH = 2_000_000  # 종목당 20억(천원) 초과 = 비율 이상


def load(p, default):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def main():
    slim = load(SLIM, {"people": []})
    av1 = load(AV1, {})
    av2 = load(AV2, {})
    if not av2:
        print("⚠ 2차 추출(asset_value_150.json)이 아직 없습니다 — 2차 OCR 완료 후 다시 실행하세요.")

    # 슬림: huboid → (수량주 목록, 종목수, 메타)
    meta = {}
    for p in slim.get("people", []):
        hb = str(p["huboid"])
        qtys = [h.get("수량주") or 0 for h in p.get("holdings", [])]
        meta[hb] = {
            "name": p.get("name"), "party": p.get("party"), "office": p.get("office"),
            "sido": p.get("sido"), "sgg": p.get("sgg"),
            "n_stocks": len(p.get("holdings", [])),
            "max_qty": max(qtys, default=0),
            "needs_review": bool(p.get("needs_review")),
            "asset_thousand": p.get("asset_thousand"),
        }

    rows = []
    n_assessed = 0
    for hb, m in meta.items():
        v1 = (av1.get(hb) or {}).get("value_thousand") if isinstance(av1.get(hb), dict) else None
        v2 = (av2.get(hb) or {}).get("value_thousand") if isinstance(av2.get(hb), dict) else None
        if not (v1 or v2):
            continue   # 평가액이 한 번도 산출 안 됨 = 공개 대상 아님 → 검수 범위 밖
        n_assessed += 1
        reasons, grade = [], "정상"

        def bump(g):
            nonlocal grade
            order = {"정상": 0, "주의": 1, "확인필요": 2}
            if order[g] > order[grade]:
                grade = g

        # ① 2차 독립 OCR 대조
        if v1 and v2:
            diff = abs(v1 - v2) / max(v1, v2)
            if diff > WARN_TOL:
                reasons.append(f"2차대조 {diff*100:.0f}% 불일치(1차 {v1/100000:.1f}억·2차 {v2/100000:.1f}억)")
                bump("확인필요")
            elif diff > AGREE_TOL:
                reasons.append(f"2차대조 {diff*100:.0f}% 차이")
                bump("주의")
        elif v1 or v2:
            only = v1 or v2
            reasons.append(f"한쪽 해상도만 추출({(only or 0)/100000:.1f}억)")
            bump("확인필요" if (only or 0) >= BIG_VALUE else "주의")
        # v1·v2 둘 다 없음 = 평가액 미산출(보유종목은 있음) → 검수 대상 아님(공개도 안 됨)

        # ② 수량↔가액 혼입
        if m["max_qty"] > QTY_BLEED:
            reasons.append(f"수량 {m['max_qty']:,}주(>1천만) — 가액칸 혼입 의심")
            bump("확인필요")
        if m["needs_review"]:
            reasons.append("OCR 칸뭉침(needs_review)")
            bump("주의")

        # ③ 이상치/비율
        v = v1 or v2
        if v:
            if v >= BIG_VALUE:
                reasons.append(f"고액 {v/100000:.1f}억 — 원본 점검 권장")
                bump("주의")
            per = v / max(1, m["n_stocks"])
            if per > PER_STOCK_HIGH:
                reasons.append(f"종목당 {per/100000:.1f}억 — 비율 이상")
                bump("주의")

        if grade != "정상":
            rows.append({**m, "huboid": hb, "v1_thousand": v1, "v2_thousand": v2,
                         "grade": grade, "reasons": reasons})

    order = {"확인필요": 0, "주의": 1}
    rows.sort(key=lambda r: (order.get(r["grade"], 9), -((r["v1_thousand"] or r["v2_thousand"] or 0))))

    # 통계 — 평가액이 한 번이라도 산출된 인물(=공개 대상)
    by_grade = {"확인필요": 0, "주의": 0}
    for r in rows:
        by_grade[r["grade"]] = by_grade.get(r["grade"], 0) + 1
    n_agree = n_assessed - len(rows)

    report = {
        "generated": slim.get("generated"),
        "summary": {
            "평가액_보유": n_assessed,
            "정상(자동통과)": n_agree,
            "주의": by_grade["주의"],
            "확인필요": by_grade["확인필요"],
            "자동통과율": round(n_agree / n_assessed * 100, 1) if n_assessed else None,
        },
        "checks": {
            "dual_ocr": bool(av2), "agree_tol": AGREE_TOL, "warn_tol": WARN_TOL,
            "qty_bleed": QTY_BLEED, "big_value_thousand": BIG_VALUE,
        },
        "suspects": rows,
    }
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")

    with OUT_CSV.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["등급", "이름", "정당", "직책", "지역", "시군구",
                    "1차(억)", "2차(억)", "종목수", "사유", "huboid"])
        for r in rows:
            w.writerow([r["grade"], r["name"], r["party"], r["office"], r["sido"], r.get("sgg") or "",
                        f"{(r['v1_thousand'] or 0)/100000:.1f}" if r["v1_thousand"] else "",
                        f"{(r['v2_thousand'] or 0)/100000:.1f}" if r["v2_thousand"] else "",
                        r["n_stocks"], " · ".join(r["reasons"]), r["huboid"]])

    s = report["summary"]
    print(f"검수 완료: 평가액 보유 {s['평가액_보유']}명")
    print(f"  ✅ 정상(자동통과) {s['정상(자동통과)']}  ·  🟡 주의 {s['주의']}  ·  🔴 확인필요 {s['확인필요']}")
    print(f"  자동통과율 {s['자동통과율']}%")
    print(f"→ {OUT_JSON.name} · {OUT_CSV.name}")
    print("\n확인필요 TOP10:")
    for r in [r for r in rows if r["grade"] == "확인필요"][:10]:
        print(f"  {r['name']:6s} {(r['v1_thousand'] or 0)/100000:6.1f}억 | {' · '.join(r['reasons'])}")


if __name__ == "__main__":
    main()
