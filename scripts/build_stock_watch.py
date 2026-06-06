# -*- coding: utf-8 -*-
"""당선 의원 주식·이해충돌 감시 데이터 빌드.

stocks/stock_holdings.json(공개 슬림본) + data/winner_huboids.json을 결합해:
  - 각 인물에 won(당선) 플래그
  - 각 인물에 cats(이해충돌 카테고리 키 목록) + 보유종목에 매칭된 카테고리
  - 상단 watch 요약(당선자만 기준): 카테고리별 인원, 정당 분포, 최다보유 랭킹
을 stocks/stock_holdings.json에 in-place로 덧붙인다(기존 키 유지 → 페이지 호환).

⚠️ 카테고리는 종목명 '키워드 자동 분류'다. OCR 노이즈를 견디려 부분일치를 쓰므로
   오분류 가능성이 있다 → UI에서 '자동 분류'임을 명시하고, 칩으로 원종목을 보이게 한다.
사용: python scripts/build_stock_watch.py
"""
import json, re, sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SH = ROOT / "stocks" / "stock_holdings.json"
WH = ROOT / "data" / "winner_huboids.json"
AV = ROOT / "data" / "asset_value.json"   # 좌표 OCR로 추출한 인물별 주식 평가액(천원)

# 정책영역별 이해충돌 카테고리. 종목명 정규화(공백제거) 후 부분일치.
# tier: 직책 권한과의 직접성 — 이 데이터는 지자체장(시도지사·기초단체장)이 대부분이므로
#   direct  = 단체장 인허가·개발·발주 권한과 직접 충돌
#   region  = 지역경제·금고 등 간접 연관
#   national= 국방·에너지 등 국가정책 영역(지방권한과 거리 멂, '보유 사실 공개'에 의미)
# label/icon: 화면표시, why: 직책 맥락 설명, kw: 매칭 키워드(OCR 변형 포함), excl: 제외 키워드
CATS = [
    {"key": "realestate", "label": "건설·부동산", "icon": "🏗️", "tier": "direct",
     "why": "단체장 인허가·관급공사, 지방의원 도시계획 심의·조례 권한과 직접 충돌",
     "kw": ["건설","이앤씨","산업개발","동국개발","자이에스엔디","리츠","맥쿼리인프라",
            "NICE인프라","nice인프라","대우건설","현대건설","포스코이앤씨"],
     "excl": ["건설팅","컨설팅"]},
    {"key": "finance", "label": "은행·금융", "icon": "🏦", "tier": "region",
     "why": "지자체 금고 지정·지역 금융과 연관 소지",
     "kw": ["은행","금융지주","증권","생명보험","화재","손해보험","캐피탈","카드",
            "iM금융","im금융","카카오뱅크","카카오페이","미래에셋","NH투자","삼성생명",
            "한화생명","동양생명","우리금융","신한금융","하나금융","KB금융","기업은행"],
     "excl": ["생명과학","생명괴","생명공학","진원생명","에이치엘비생명"]},
    {"key": "defense", "label": "방산·조선", "icon": "🛡️", "tier": "national",
     "why": "국방·방위사업(국가정책). 단체장 권한과는 거리, 보유 사실 공개 의미",
     "kw": ["한화오션","한화오선","한화에어로","한화시스템","한화엔진","한화비전",
            "현대로템","현대위아","삼성중공업","현대중공업","조선해양","HJ중공업",
            "STX엔진","넥스원","풍산","항공우주","우주항공","대한항공"],
     "excl": ["한화솔루션","한화생명","한화손해","한화갤러리","한화길러리"]},
    {"key": "nuclear", "label": "원전·전력", "icon": "⚡", "tier": "national",
     "why": "에너지·전력(국가정책). 원전 입지 지자체 외엔 직접 권한 약함",
     "kw": ["에너빌","한국전력","한전기술","한전KPS","한전kps","비에이치아이",
            "센트러스","뉴스케일","컨스털레이션","대한전선","일진파워","두산에너"],
     "excl": []},
    {"key": "overseas", "label": "해외주식", "icon": "🌐", "tier": "national",
     "why": "국내 신고서식 외 해외 직접보유. 권한 무관, 보유 규모 공개 의미",
     "kw": ["엔비디아","엔비니아","테슬라","애플","에플","마이크로소프트","브로드컴",
            "팔란티어","아이온큐","넷플릭스","메타플랫폼","메타","알파벳","코카콜라",
            "샌디스크","아처에비에이션","에머슨","디웨이브","플러그파워","센트러스",
            "뉴스케일","컨스털레이션","마이크론","구글","아마존","버크셔","퀄컴",
            "AMD","TSMC"],
     "excl": ["엔켐"]},
]

TIERS = [
    {"key": "direct", "label": "지방권력과 직접 충돌",
     "desc": "인허가·재개발·관급공사(단체장)·도시계획 심의·조례(지방의원)"},
    {"key": "region", "label": "지역경제·예산 연관",
     "desc": "지자체 금고·지역 금융, 예산 심의 등 간접 연관"},
    {"key": "national", "label": "국가정책 영역(직접 권한 약함)",
     "desc": "국방·에너지·해외 — 지방권한과 거리. 보유 사실 공개에 의미"},
]


# 이해충돌 최소 보유 기준 — 10주 미만(1~9주)은 명목 보유로 보고 카테고리에서 제외.
MIN_SHARES = 10

# OCR 오인식 종목명 교정(명백한 건만). 가액·수량 합산엔 영향 없음(이름만 통일).
STOCK_FIX = {
    "엔비니아": "엔비디아",   # NVIDIA OCR 오인식 — '엔비니아'는 존재하지 않는 종목
    "ilBC": "iMBC",          # iMBC(코스닥) OCR 오인식 — m→l. 'ilBC'는 존재하지 않는 종목
    "IMBC": "iMBC",          # 표기 통일
}


def fix_name(name):
    n = str(name or "")
    for bad, good in STOCK_FIX.items():
        if bad in n:
            n = n.replace(bad, good)
    return n


def load_corrections():
    """기자 수동 교정표 data/stock_corrections.csv 로드.
    컬럼: huboid, 종목(현재 표시명), 정정종목, 정정수량, 삭제(Y), 메모.
    (huboid, 현재 종목명) 키로 매칭해 종목명/수량 교체 또는 행 삭제."""
    import csv as _csv
    path = ROOT / "data" / "stock_corrections.csv"
    corr = {}
    if not path.exists():
        return corr
    for row in _csv.DictReader(path.open(encoding="utf-8-sig")):
        hb = (row.get("huboid") or "").strip()
        stk = (row.get("종목") or "").strip()
        if not hb or not stk or hb.startswith("#"):
            continue
        corr[(hb, stk)] = {
            "종목": (row.get("정정종목") or "").strip(),
            "수량": (row.get("정정수량") or "").strip(),
            "삭제": (row.get("삭제") or "").strip().upper() == "Y",
        }
    return corr


# 실재 종목 보호(자동 퍼지 교정 금지) — 고빈도 종목과 1글자 차이지만 실제 상장사인 것.
WHITELIST_REAL = {
    "삼지전자", "삼화전자", "삼영전자",   # 삼성전자(407)와 1자 차이지만 실재 코스닥
    "현대건설", "현대重공업",            # 현대차 등과 혼동 방지(부분)
    "에이프로",                          # 에코프로와 혼동되나 실재(에이프로 APR 아님 주의) → 보호
}


def _lev1(a, b):
    """길이 같고 정확히 1글자만 다르면 True (편집거리=치환 1)."""
    if len(a) != len(b):
        return False
    diff = sum(1 for x, y in zip(a, b) if x != y)
    return diff == 1


def fuzzy_typo_map(people):
    """저빈도 종목이 초고빈도 종목과 1글자 차이면 OCR 오타로 보고 교정 맵 생성.
    실재 종목(WHITELIST_REAL)은 제외. 보수적으로 저빈도≤3 · 고빈도≥20 · 20배 이상만."""
    freq = Counter(h["종목"] for p in people for h in p["holdings"])
    normal = {s: c for s, c in freq.items() if c >= 20 and len(s) >= 3}
    tmap = {}
    for s, c in freq.items():
        if c > 3 or len(s) < 3 or s in normal or s in WHITELIST_REAL:
            continue
        for nm, nc in sorted(normal.items(), key=lambda kv: -kv[1]):
            if nc >= c * 20 and _lev1(s, nm):
                tmap[s] = nm
                break
    return tmap


def norm(s):
    return re.sub(r"\s+", "", str(s or ""))


def match_cats(stock_name):
    n = norm(stock_name)
    out = []
    for c in CATS:
        if any(x in n for x in c["excl"]):
            continue
        if any(norm(k) in n for k in c["kw"]):
            out.append(c["key"])
    return out


def main():
    data = json.loads(SH.read_text(encoding="utf-8"))
    winners = set(json.loads(WH.read_text(encoding="utf-8"))["huboids"])

    # 감시용 → 낙선자는 아예 제외(당선자만 보존). raw 원본은 data/stock_holdings.json에 남음.
    before = len(data["people"])
    data["people"] = [p for p in data["people"] if str(p["huboid"]) in winners]
    print(f"낙선자 제외: {before} → {len(data['people'])}명(당선자만)", file=sys.stderr)

    # 종목명 교정 2단계: ① STOCK_FIX(수동) ② 퍼지 오타(저빈도→초고빈도 1글자, 실재종목 보호)
    for p in data["people"]:
        for h in p["holdings"]:
            h["종목"] = fix_name(h["종목"])
    typo = fuzzy_typo_map(data["people"])
    for p in data["people"]:
        for h in p["holdings"]:
            h["종목"] = typo.get(h["종목"], h["종목"])
    print(f"퍼지 오타 교정: {len(typo)}종 → 정상 통일", file=sys.stderr)

    # ③ 기자 수동 교정(data/stock_corrections.csv) — 원본 대조 후 확정값. 최우선 적용.
    corr = load_corrections()
    if corr:
        nfix = 0
        for p in data["people"]:
            new = []
            for h in p["holdings"]:
                c = corr.get((str(p["huboid"]), h["종목"]))
                if c:
                    nfix += 1
                    if c["삭제"]:
                        continue
                    if c["종목"]:
                        h["종목"] = c["종목"]
                    if c["수량"].isdigit():
                        h["수량주"] = int(c["수량"])
                new.append(h)
            p["holdings"] = new
        print(f"기자 수동 교정: {nfix}건 적용(stock_corrections.csv)", file=sys.stderr)

    # 주식 평가액(천원) 병합 — 좌표 OCR 자동 추출값(미검증). 값 없으면 None.
    asset = {}
    if AV.exists():
        av = json.loads(AV.read_text(encoding="utf-8"))
        asset = {str(hb): (v.get("value_thousand") if isinstance(v, dict) else None)
                 for hb, v in av.items()}
        print(f"평가액 병합: {sum(1 for x in asset.values() if x)}명 추출값 로드", file=sys.stderr)

    cat_people = {c["key"]: [] for c in CATS}     # 당선자만
    party_count = {}                               # 보유 당선자 정당 분포
    office_count = {}                              # 보유 당선자 직책 분포
    stock_holders = {}                             # 종목 → 보유 당선자 수
    n_winner_holders = 0

    for p in data["people"]:
        p.pop("nec_url", None)   # 선거 후 404·미사용 선관위 링크 제거(방침)
        p["won"] = True
        p["asset_thousand"] = asset.get(str(p["huboid"]))   # 주식 평가액(천원) · 미추출=None
        # 보유종목별 카테고리 태깅 — 10주 미만 명목 보유는 이해충돌에서 제외
        pcats = set()
        for h in p["holdings"]:
            hc = match_cats(h["종목"]) if (h.get("수량주") or 0) >= MIN_SHARES else []
            h["cats"] = hc
            pcats.update(hc)
        p["cats"] = sorted(pcats)
        if p["holdings"]:
            n_winner_holders += 1
            party_count[p["party"]] = party_count.get(p["party"], 0) + 1
            office_count[p["office"]] = office_count.get(p["office"], 0) + 1
            for k in pcats:
                cat_people[k].append({"huboid": p["huboid"], "name": p["name"],
                                      "party": p["party"], "office": p["office"],
                                      "sido": p["sido"]})
            seen = set()
            for h in p["holdings"]:
                if h["종목"] not in seen:
                    seen.add(h["종목"])
                    stock_holders[h["종목"]] = stock_holders.get(h["종목"], 0) + 1

    # 직책 → 그룹(권한 성격별)
    def office_group(office):
        if office in ("시도지사", "기초단체장"):
            return "단체장"
        if office in ("시도의원", "구시군의회의원", "구시군의원"):
            return "지방의원"
        if office == "국회의원":
            return "국회의원"
        if office == "교육감":
            return "교육감"
        return "기타"

    # 카테고리별 직책 분포(직접성 강조용): 건설·부동산을 단체장/지방의원이 몇 명 보유했나
    def office_split(key):
        oc = {}
        for x in cat_people[key]:
            grp = office_group(x["office"])
            oc[grp] = oc.get(grp, 0) + 1
        return oc
    cats_summary = [{"key": c["key"], "label": c["label"], "icon": c["icon"],
                     "tier": c["tier"], "why": c["why"], "count": len(cat_people[c["key"]]),
                     "by_office": office_split(c["key"])} for c in CATS]
    # 종목 최다 랭킹(가짓수) — 검토필요(OCR 칸뭉침) 건 제외.
    # ※수량 합계는 OCR이 수량·평가액을 혼입해 신뢰 불가(예: 마이크론 6주→636만주) → 제공하지 않음.
    rich = sorted([{"huboid": p["huboid"], "name": p["name"], "party": p["party"],
                    "office": p["office"], "sido": p["sido"], "n": len(p["holdings"])}
                   for p in data["people"] if p["won"] and p["holdings"] and not p.get("needs_review")],
                  key=lambda x: -x["n"])[:20]
    most_held = sorted(stock_holders.items(), key=lambda x: -x[1])[:20]

    # 주식 평가액(富) 순위 — 자동 추출값 있는 당선 보유자 전원, 내림차순.
    asset_rank = sorted(
        [{"huboid": p["huboid"], "name": p["name"], "party": p["party"],
          "office": p["office"], "sido": p["sido"], "sgg": p.get("sgg"),
          "value_thousand": p["asset_thousand"], "n": len(p["holdings"])}
         for p in data["people"] if p["won"] and p["holdings"] and p.get("asset_thousand")],
        key=lambda x: -(x["value_thousand"] or 0))
    n_asset = len(asset_rank)
    n_no_asset = sum(1 for p in data["people"] if p["won"] and p["holdings"] and not p.get("asset_thousand"))

    # 직책 그룹별 집계
    office_grp = {}
    for o, n in office_count.items():
        g = office_group(o)
        office_grp[g] = office_grp.get(g, 0) + n
    # scope: 실제 포함된 직책으로 자동 생성
    present = [g for g in ("단체장", "지방의원", "국회의원", "교육감") if office_grp.get(g)]
    scope = "·".join(present) + " 당선자" if present else "당선자"

    data["watch"] = {
        "winner_holders": n_winner_holders,
        "parties": sorted(party_count.items(), key=lambda x: -x[1]),
        "offices": sorted(office_count.items(), key=lambda x: -x[1]),
        "office_groups": office_grp,
        "scope": scope,
        "tiers": TIERS,
        "cats": cats_summary,
        "cat_people": cat_people,
        "rich": rich,
        "most_held": [{"종목": k, "n": v} for k, v in most_held],
        "asset_rank": asset_rank,
        "asset_meta": {"with_value": n_asset, "no_value": n_no_asset},
        "asset_note": "주식 평가액은 재산신고서 '가액(천원)' 칸을 좌표 OCR로 자동 추출한 값입니다. "
                      "수기 검증을 거치지 않아 일부 OCR 오류가 있을 수 있으며, 신고 시점(후보등록 2026-05) "
                      "기준입니다. 정확한 금액은 관보·정부공직자윤리위 재산공개를 확인하세요.",
        "note": "당선자 한정 집계. 카테고리는 종목명 자동(키워드) 분류로 오분류 가능. "
                "보유 종목 칩으로 원종목 확인 가능. 공개 재산신고 OCR 기반.",
    }
    SH.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"당선 보유자 {n_winner_holders}명")
    for c in cats_summary:
        print(f"  {c['icon']} {c['label']}: {c['count']}명")
    print("정당:", data["watch"]["parties"])
    print("종목최다 TOP5:", [(r["name"], r["n"]) for r in rich[:5]])
    print(f"평가액 보유 {n_asset}명 · 미추출 {n_no_asset}명")
    print("평가액 TOP5:", [(r["name"], f"{(r['value_thousand'] or 0)/100000:.1f}억") for r in asset_rank[:5]])


if __name__ == "__main__":
    main()
