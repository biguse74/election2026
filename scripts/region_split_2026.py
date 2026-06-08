# -*- coding: utf-8 -*-
"""2026 지선(기초단체장) 시군구를 호남/비호남으로 나눠 투표율↔정당 상관 비교.

무소속·기타 정의: 유효투표 중 더불어민주당·국민의힘을 제외한 전부
  (= 무소속 + 진보당·정의당 등 제3정당 합산) = 100 − 민주% − 국힘%  (기존 패키지와 동일).

소스: data/live_counting/turnout_party.json (compare_elections.py가 2026 소스로 쓰는 파일,
       turnout_party_multi.json의 2026 점과 동일 출처·동일 224곳).
출력: 콘솔 표 + data/live_counting/turnout_party_2026_region_split.json
사용: python scripts/region_split_2026.py
"""
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "live_counting" / "turnout_party.json"
OUT = ROOT / "data" / "live_counting" / "turnout_party_2026_region_split.json"
HONAM = {"전북특별자치도", "전라남도", "광주광역시"}


def pearson(xs, ys):
    n = len(xs)
    if n < 3:
        return None
    mx, my = sum(xs) / n, sum(ys) / n
    cov = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    sx = sum((x - mx) ** 2 for x in xs) ** 0.5
    sy = sum((y - my) ** 2 for y in ys) ** 0.5
    return round(cov / (sx * sy), 3) if sx * sy else None


def etc(p):
    return round(max(0.0, 100 - p["dem"] - p["con"]), 1)


def corrset(pts):
    e = [p["early"] for p in pts]
    d = [p["day"] for p in pts]
    return {
        "n": len(pts),
        "사전_민주": pearson(e, [p["dem"] for p in pts]),
        "사전_국힘": pearson(e, [p["con"] for p in pts]),
        "사전_무소속기타": pearson(e, [etc(p) for p in pts]),
        "당일_국힘": pearson(d, [p["con"] for p in pts]),
    }


def main():
    pts = json.loads(SRC.read_text(encoding="utf-8"))["points"]
    H = [p for p in pts if p["sd"] in HONAM]
    N = [p for p in pts if p["sd"] not in HONAM]
    res = {"전국": corrset(pts), "호남": corrset(H), "비호남": corrset(N)}

    # 검증
    nat = res["전국"]
    expect = {"사전_민주": 0.06, "사전_국힘": -0.63, "당일_국힘": 0.82, "사전_무소속기타": 0.67, "n": 224}
    checks = []
    for k, v in expect.items():
        got = nat["n"] if k == "n" else nat[k]
        ok = (got == v) if k == "n" else (abs(got - v) <= 0.01)
        checks.append((k, v, got, ok))

    # 비호남 무소속·기타 상위 6
    top = sorted(N, key=lambda p: -etc(p))[:6]
    top_rows = [{"시도": p["sd"], "시군구": p["sgg"], "사전": p["early"], "당일": p["day"],
                 "민주": p["dem"], "국힘": p["con"], "무소속기타": etc(p)} for p in top]

    payload = {
        "기준": "2026 지선(기초단체장) 시군구",
        "무소속기타_정의": "유효투표 중 민주·국힘 제외 전부(무소속+진보당·정의당 등 제3정당) = 100−민주−국힘",
        "호남_정의": "시도가 전북특별자치도·전라남도·광주광역시인 시군구",
        "상관": res,
        "전국_검증": [{"지표": k, "패키지": v, "재계산": g, "일치": ok} for k, v, g, ok in checks],
        "비호남_무소속상위6": top_rows,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")

    # 콘솔 표
    print("무소속·기타 = 100 − 민주% − 국힘% (무소속 + 진보당·정의당 등 제3정당 합산)\n")
    hdr = f"{'그룹':6} {'n':>4} {'사전↔민주':>9} {'사전↔국힘':>9} {'사전↔무소속':>10} {'당일↔국힘':>9}"
    print(hdr); print("-" * len(hdr))
    f = lambda v: " n/a" if v is None else f"{v:+.2f}"
    for g in ("전국", "호남", "비호남"):
        c = res[g]
        print(f"{g:6} {c['n']:>4} {f(c['사전_민주']):>9} {f(c['사전_국힘']):>9} {f(c['사전_무소속기타']):>10} {f(c['당일_국힘']):>9}")
    print("\n[전국 검증 — 패키지 기준값 대비]")
    for k, v, g, ok in checks:
        print(f"  {k:12} 패키지 {v:+} · 재계산 {g:+} → {'일치 ✅' if ok else '불일치 ⚠️'}")
    if all(ok for *_, ok in checks):
        print("  ⇒ 전 단계 일치(동일 소스·동일 정의·동일 224곳).")
    print("\n[비호남 무소속·기타 상위 6곳]")
    h2 = f"  {'시도':10} {'시군구':8} {'사전':>5} {'당일':>5} {'민주':>5} {'국힘':>5} {'무소속+':>6}"
    print(h2)
    for r in top_rows:
        print(f"  {r['시도']:10} {r['시군구']:8} {r['사전']:>5} {r['당일']:>5} {r['민주']:>5} {r['국힘']:>5} {r['무소속기타']:>6}")
    print(f"\n→ {OUT}")


if __name__ == "__main__":
    main()
