# -*- coding: utf-8 -*-
"""종목명 OCR 오타 '안전 자동 교정' 제안 생성.

블라인드 교정은 실재 종목을 망가뜨린다(농심홀딩스→홀딩스, 카카오페이→카카오 등).
그래서 '증명 가능하게 안전한' 패턴만 제안한다:
  · 확실한 실재명(보유자 3명+) = canonical
  · source가 [잡음≤2자] + canonical  또는  canonical + [잡음≤2자] (통째 포함)
  · 일반어/모회사명(BLOCK)은 교정 대상 금지 — 하위 종목 오병합 방지
  · 우선주/보통주 접미사 보존
  · 남는 잡음이 그 자체로 실재명(또는 그 시작)이면 = 두 종목 합쳐진 행 → 제외
  · 매칭 canonical이 둘 이상이면(모호) 제외

기본은 드라이런(제안만 출력). --apply 시 data/auto_name_corrections.csv 생성.
이 파일은 build_stock_watch.py가 stock_corrections.csv와 함께 적용한다.
"""
import argparse
import csv
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SH = ROOT / "stocks" / "stock_holdings.json"
OUT = ROOT / "data" / "auto_name_corrections.csv"

# 교정 '대상(target)'이 되면 안 되는 일반어·모회사명(하위 종목을 잡아먹음).
BLOCK = {
    # 일반어(하위 종목을 잡아먹는 접미/접두)
    "홀딩스", "지주", "제약", "증권", "은행", "금융", "화학", "전자", "중공업",
    "건설", "생명", "보험", "손해보험", "우체국", "보통주", "우선주", "그룹",
    "하이닉스",  # 불완전형(SK하이닉스)
    # 모회사/브랜드(하위 종목 있음)
    "카카오", "에코프로", "HLB", "에이치엘비", "한화", "현대", "삼성", "엘지",
    "LG", "SK", "신한", "하나", "우리", "KB", "NH", "포스코", "두산", "현대차",
    # ETF 브랜드(뒤에 상품명이 붙어야 의미)
    "KODEX", "TIGER", "ACE", "KBSTAR", "ARIRANG", "SOL", "RISE", "PLUS",
    "KOSEF", "HANARO", "TIMEFOLIO", "WON", "히어로즈",
    # 이미 깨진 canonical(오타가 다수표가 됨) — 교정 대상에서 제외
    "셀트리은", "아이은큐", "SCO홀딩스",
    # 부분명(앞 회사명이 빠진 불완전형) — 모회사 다름
    "생명과학", "에너지솔루션", "테크놀로지그룹", "이노엔",
}
WHITELIST = {"삼지전자", "삼화전자", "삼영전자", "현대건설", "에이프로"}
PREF = re.compile(r"(우|보|우B|[0-9]우B?|전환|신형|스팩|[0-9]호)$")  # 우선주 등 접미사
# 2글자+ 잡음이 이 목록이면 '진짜 접미어'(안전). 아니면 다른 종목일 수 있어 제외.
SUFFIX_OK = {"상장", "공사", "우량", "보통", "보통주", "한주", "본주", "주식", "주권"}


def norm(s):
    return re.sub(r"\s+", "", str(s or ""))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="제안을 CSV로 저장")
    args = ap.parse_args()

    d = json.loads(SH.read_text(encoding="utf-8"))
    people = [p for p in d["people"] if p["holdings"]]
    holder = Counter()
    for p in people:
        for nm in {h["종목"] for h in p["holdings"]}:
            holder[nm] += 1
    # 교정 대상(canonical)은 5명+ 보유 & 4글자+ — 깨진 canonical·3글자 부분명 트랩 제거
    canon = {n for n, c in holder.items() if c >= 5 and len(norm(n)) >= 4 and n not in BLOCK}
    canon_norm = {norm(c): c for c in canon}
    # 잡음 판정용: 어떤 canonical의 시작과 일치하는 2자+ 토큰이면 '다른 종목'일 수 있음
    canon_starts = sorted({cn for cn in canon_norm}, key=len, reverse=True)

    def looks_like_name(junk):
        """남는 잡음이 그 자체로 실재명(또는 시작)이면 True → 두 종목 합쳐진 행."""
        if len(junk) < 2:
            return False
        if junk in canon_norm:
            return True
        return any(cs.startswith(junk) or junk.startswith(cs) for cs in canon_starts if len(cs) >= 2)

    props = []
    for n, cnt in holder.items():
        if cnt > 2 or n in canon or n in WHITELIST:
            continue
        nn = norm(n)
        matches = []
        for cnorm, cname in canon_norm.items():
            if len(cnorm) < 3:
                continue
            if cnorm in nn and 0 < len(nn) - len(cnorm) <= 2:
                junk = nn.replace(cnorm, "", 1)
                if len(junk) >= 2 and junk not in SUFFIX_OK:   # 다른 종목 합쳐짐 가능 → 제외
                    continue
                if looks_like_name(junk):           # 두 종목 합쳐진 행
                    continue
                if PREF.search(n) and not PREF.search(cname):   # 우선주 보존
                    continue
                matches.append(cname)
        matches = list(set(matches))
        if len(matches) == 1:                       # 모호하지 않을 때만
            props.append((n, matches[0], cnt, holder[matches[0]]))

    props.sort(key=lambda x: -x[3])
    print(f"안전 자동교정 제안: {len(props)}건")
    for n, b, c, bc in props:
        print(f"  {n!r} → {b!r}  (실재명 보유 {bc}명)")

    if args.apply:
        with OUT.open("w", encoding="utf-8-sig", newline="") as f:
            w = csv.writer(f)
            w.writerow(["종목", "정정종목", "메모"])
            for n, b, c, bc in props:
                w.writerow([n, b, f"자동교정(실재명 {bc}명, 잡음제거)"])
        print(f"→ {OUT} 저장({len(props)}건)")


if __name__ == "__main__":
    main()
