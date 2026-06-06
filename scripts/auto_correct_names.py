# -*- coding: utf-8 -*-
"""종목명 OCR 오타 '사전 기반 안전 자동교정' 제안 생성.

검증된 실재명(KRX 상장사 2,877 + 우리 데이터 고빈도 비-KRX=실재 해외/ETF)을 사전으로 삼아:
  · 사전에 있는 이름  → 진짜다. 건드리지 않음(농심홀딩스·삼성전자우·엔비디아 보존).
  · 사전에 없는 이름  → garble 후보. 사전에서 가장 가까운 실재명을 찾아, 충분히 유사하면 교정.
교정 '대상(target)'은 항상 검증된 실재명 → 없는 이름을 지어내지 않는다.

안전장치: 높은 유사도(0.85+) · 길이차≤2 · 4글자+ · 우선주/클래스 접미사 보존 ·
          유일 매칭(모호 제외) · 두 종목 합쳐진 행(잡음이 또 다른 실재명) 제외.

기본은 드라이런. --apply 시 data/auto_name_corrections.csv 생성.
사전 생성:  python -c "import FinanceDataReader as fdr,json; \
  json.dump(sorted(set(fdr.StockListing('KRX')['Name'].dropna())), \
  open('data/krx_listed_names.json','w',encoding='utf-8'),ensure_ascii=False)"
"""
import argparse
import csv
import json
import re
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SH = ROOT / "stocks" / "stock_holdings.json"
KRX = ROOT / "data" / "krx_listed_names.json"
OUT = ROOT / "data" / "auto_name_corrections.csv"

WHITELIST = {"삼지전자", "삼화전자", "삼영전자", "에이프로"}
PREF = re.compile(r"(우|보|우B|[0-9]우B?|전환|신형|스팩|[0-9]호|[ABC])$")  # 우선주·클래스
SAFE_MIN = 5      # 비-KRX라도 보유자 N명+ = 실재(해외·ETF) → 보호(source 제외)
RATIO = 0.88      # 최소 유사도
MARGIN = 0.05     # best - 2nd가 이 이상이거나 best≥0.93이어야(모호 매칭 차단)
NAME_MIN = 4      # 교정 대상 최소 글자수(짧은 부분명 충돌 방지)

# KRX에 없는 실재 해외/ETF '교정 대상' — 직접 엄선(garble·집계·구표기 제외).
CURATED_FOREIGN = {
    "엔비디아", "테슬라", "애플", "마이크로소프트", "알파벳A", "브로드컴", "인텔",
    "아이온큐", "팔란티어", "오라클", "코카콜라", "넷플릭스", "로켓랩", "리게티컴퓨팅",
    "뉴스케일파워", "오클로", "아마존닷컴", "조비에비에이션",
    "농협은행", "우리은행", "신한은행", "중소기업은행",
}
# 사전을 써도 틀리는 알려진 짝(이름변경·모자회사) — 강제 제외.
DENY = {
    ("삼성엔지니어링", "주성엔지니어링"), ("SCO홀딩스", "KISCO홀딩스"),
    ("HD현대건설기계", "HD건설기계"), ("알파벳", "알파벳A"),
    ("엠젠플러스", "엠플러스"),   # 서로 다른 실재사(엠젠플러스는 KRX 미수록일 뿐)
}


def norm(s):
    return re.sub(r"\s+", "", str(s or ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    krx = json.loads(KRX.read_text(encoding="utf-8"))
    d = json.loads(SH.read_text(encoding="utf-8"))
    people = [p for p in d["people"] if p["holdings"]]
    holder = Counter()
    for p in people:
        for nm in {h["종목"] for h in p["holdings"]}:
            holder[nm] += 1

    # 보호집합(=source가 되면 안 됨): KRX + 보유 5명+. 실재 해외/공통명 보존.
    protect = {n for n, c in holder.items() if c >= SAFE_MIN}
    valid_norm = {norm(n) for n in krx} | {norm(n) for n in protect}
    # 교정 대상(target): KRX + 엄선 해외/ETF만 — garble·집계가 target이 되는 것 방지.
    target = {}
    for n in list(krx) + sorted(CURATED_FOREIGN):
        target.setdefault(norm(n), n)
    target_norm = list(target)

    def looks_like_name(junk):
        if len(junk) < 2:
            return False
        return any(t.startswith(junk) or junk.startswith(t) for t in target_norm if len(t) >= 3)

    props = []
    for n, cnt in holder.items():
        nn = norm(n)
        if nn in valid_norm or n in WHITELIST or len(nn) < 3:
            continue                                                # 이미 실재명/보호
        best, br, second = None, 0.0, 0.0
        for tnorm in target_norm:
            if len(tnorm) < NAME_MIN or abs(len(nn) - len(tnorm)) > 2:
                continue
            r = SequenceMatcher(None, nn, tnorm).ratio()
            if r > br:
                br, second, best = r, br, tnorm
            elif r > second:
                second = r
        if not best or br < RATIO:
            continue
        if br < 0.93 and (br - second) < MARGIN:      # 모호(2순위와 근접) 차단
            continue
        if (n, target[best]) in DENY:
            continue
        # 우선주/클래스 접미사 보존
        if PREF.search(n) and not PREF.search(target[best]):
            continue
        # 두 종목 합쳐진 행(남는 잡음이 또 다른 실재명) 제외
        if best in nn:
            junk = nn.replace(best, "", 1)
            if looks_like_name(junk):
                continue
        props.append((br, n, target[best], cnt))

    props.sort(key=lambda x: (-x[0], -x[3]))
    print(f"사전 기반 자동교정 제안: {len(props)}건  (KRX {len(krx)} + 보호 {len(protect)} · 대상 {len(target_norm)})")
    for r, n, b, c in props:
        print(f"  {r:.2f}  {n!r} → {b!r}")

    if args.apply:
        with OUT.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["종목", "정정종목", "메모"])
            for r, n, b, c in props:
                w.writerow([n, b, f"사전기반 자동교정(유사도{r:.2f})"])
        print(f"→ {OUT} 저장({len(props)}건)")


if __name__ == "__main__":
    main()
