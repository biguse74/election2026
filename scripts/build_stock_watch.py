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
import json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SH = ROOT / "stocks" / "stock_holdings.json"
WH = ROOT / "data" / "winner_huboids.json"

# 정책영역별 이해충돌 카테고리. 종목명 정규화(공백제거) 후 부분일치.
# tier: 직책 권한과의 직접성 — 이 데이터는 지자체장(시도지사·기초단체장)이 대부분이므로
#   direct  = 단체장 인허가·개발·발주 권한과 직접 충돌
#   region  = 지역경제·금고 등 간접 연관
#   national= 국방·에너지 등 국가정책 영역(지방권한과 거리 멂, '보유 사실 공개'에 의미)
# label/icon: 화면표시, why: 직책 맥락 설명, kw: 매칭 키워드(OCR 변형 포함), excl: 제외 키워드
CATS = [
    {"key": "realestate", "label": "건설·부동산", "icon": "🏗️", "tier": "direct",
     "why": "단체장의 인허가·재개발·용도변경·관급공사 권한과 직접 충돌",
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
    {"key": "direct", "label": "단체장 권한과 직접 충돌",
     "desc": "인허가·재개발·관급공사 등 단체장이 직접 결정하는 영역"},
    {"key": "region", "label": "지역경제·예산 연관",
     "desc": "지자체 금고·지역 금융 등 간접 연관"},
    {"key": "national", "label": "국가정책 영역(직접 권한 약함)",
     "desc": "국방·에너지·해외 — 지방권한과 거리. 보유 사실 공개에 의미"},
]


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

    cat_people = {c["key"]: [] for c in CATS}     # 당선자만
    party_count = {}                               # 보유 당선자 정당 분포
    office_count = {}                              # 보유 당선자 직책 분포
    stock_holders = {}                             # 종목 → 보유 당선자 수
    n_winner_holders = 0

    for p in data["people"]:
        p.pop("nec_url", None)   # 선거 후 404·미사용 선관위 링크 제거(방침)
        won = str(p["huboid"]) in winners
        p["won"] = won
        # 보유종목별 카테고리 태깅
        pcats = set()
        for h in p["holdings"]:
            hc = match_cats(h["종목"])
            h["cats"] = hc
            pcats.update(hc)
        p["cats"] = sorted(pcats)
        if won and p["holdings"]:
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

    # 카테고리별 직책 분포(직접성 강조용): 건설·부동산을 단체장이 몇 명 보유했나 등
    def office_split(key):
        oc = {}
        for x in cat_people[key]:
            grp = "교육감" if x["office"] == "교육감" else "단체장"
            oc[grp] = oc.get(grp, 0) + 1
        return oc
    cats_summary = [{"key": c["key"], "label": c["label"], "icon": c["icon"],
                     "tier": c["tier"], "why": c["why"], "count": len(cat_people[c["key"]]),
                     "by_office": office_split(c["key"])} for c in CATS]
    # 종목부자 랭킹(당선자, 종목 수 기준)
    rich = sorted([{"huboid": p["huboid"], "name": p["name"], "party": p["party"],
                    "office": p["office"], "sido": p["sido"], "n": len(p["holdings"])}
                   for p in data["people"] if p["won"] and p["holdings"]],
                  key=lambda x: -x["n"])[:20]
    most_held = sorted(stock_holders.items(), key=lambda x: -x[1])[:20]

    # 직책 그룹: 단체장(시도지사+기초단체장) vs 교육감
    office_grp = {"단체장": 0, "교육감": 0}
    for o, n in office_count.items():
        office_grp["교육감" if o == "교육감" else "단체장"] += n

    data["watch"] = {
        "winner_holders": n_winner_holders,
        "parties": sorted(party_count.items(), key=lambda x: -x[1]),
        "offices": sorted(office_count.items(), key=lambda x: -x[1]),
        "office_groups": office_grp,
        "scope": "시도지사·기초단체장·교육감 당선자 (지방의원·국회의원은 재산신고서 OCR 미추출)",
        "tiers": TIERS,
        "cats": cats_summary,
        "cat_people": cat_people,
        "rich": rich,
        "most_held": [{"종목": k, "n": v} for k, v in most_held],
        "note": "당선자 한정 집계. 카테고리는 종목명 자동(키워드) 분류로 오분류 가능. "
                "보유 종목 칩으로 원종목 확인 가능. 공개 재산신고 OCR 기반.",
    }
    SH.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"당선 보유자 {n_winner_holders}명")
    for c in cats_summary:
        print(f"  {c['icon']} {c['label']}: {c['count']}명")
    print("정당:", data["watch"]["parties"])
    print("부자 TOP5:", [(r["name"], r["n"]) for r in rich[:5]])


if __name__ == "__main__":
    main()
