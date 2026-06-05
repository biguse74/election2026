# -*- coding: utf-8 -*-
"""재산 PDF(스캔)를 OCR해 후보별 보유 주식(종목·수량)을 추출한다.
- 아카이브(data/disclosure_archive/{huboid}_{name}/재산/*.PDF)에서 읽음
- 임베드 JPEG 추출 → Windows OCR(ko) → 유가증권 섹션 파싱
- 신뢰 추출: '(종목명)(수량)주' 패턴 / 가액은 best-effort
- OCR 캐시: data/.assets_ocr_cache/{huboid}.txt (재실행 빠름)
- ⚠️ 자동 추출값은 기사 전 원문(raw_section) 대조 필수
사용: python scripts/extract_stocks.py --offices 3,4,2   (기본: 주요 선출직)
      python scripts/extract_stocks.py --offices all
"""
import sys, os, re, json, glob, argparse
from pathlib import Path

RID = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(RID, "scripts"))
import ocr_criminal_records as O

ARCH = Path(RID) / "data" / "disclosure_archive"
OCR_CACHE = Path(RID) / "data" / ".assets_ocr_cache"
OCR_CACHE.mkdir(parents=True, exist_ok=True)
HELPER = OCR_CACHE / "win_ocr.ps1"
if not HELPER.exists(): HELPER.write_text(O.WIN_OCR_SCRIPT, encoding="utf-8")
SGTYPE = {"2":"국회의원","3":"시도지사","4":"기초단체장","5":"시도의원","6":"구시군의회의원","8":"광역비례","9":"기초비례","11":"교육감"}

# (종목명)(수량)주  — 종목명은 한글/영문/괄호/·, 2~22자
# 스캔 재산서식은 OCR 후 '본인은공직…서약문'이 holdings보다 앞 페이지에 와서
# 섹션 자르기가 holdings를 잘라먹는다(0건 오류). → 전체 텍스트를 스캔하고
# 강한 노이즈 필터 + 원문(raw) 전량 보존으로 대응한다.
STOCK_RE = re.compile(r"([가-힣A-Za-z][가-힣A-Za-z0-9()·\.]{1,21}?)\s*([\d,]{1,12})\s*주")
NONNAME = re.compile(
    r"^[\d,]+$|소계|합계|가액|수량|종류|성명|관계|비고|천원|배우자|본인|장남|장녀|차남|"
    r"지분|공유|분의|소재지|권리명세|후보자|정당명|선거|면적|취득|관할|아파트|토지|건물"
)

def ocr_assets(hid):
    cache = OCR_CACHE / f"{hid}.txt"
    if cache.exists(): return cache.read_text(encoding="utf-8")
    folder = next(iter(glob.glob(str(ARCH / f"{hid}_*" / "재산"))), None)
    if not folder: return ""
    texts = []
    for pdf in sorted(glob.glob(os.path.join(folder, "*.PDF"))):
        for jpg in O.extract_jpegs(Path(pdf), OCR_CACHE):
            try: texts.append(O.windows_ocr(jpg, HELPER))
            except Exception as e: texts.append(f"[OCR_ERR {e}]")
            finally:
                try: os.remove(jpg)
                except: pass
    txt = "\n".join(texts)
    cache.write_text(txt, encoding="utf-8")
    return txt

def valid_name(name):
    """종목명 타당성 — 정밀도 우선. OCR이 보험·예금 칸을 뭉쳐 만든 깨진 이름을 거른다."""
    if not (2 <= len(name) <= 12): return False
    if re.search(r"\d", name): return False           # 국내 종목명엔 숫자 거의 없음
    if NONNAME.search(name): return False
    if len(re.sub(r"[^가-힣A-Za-z]", "", name)) < 2: return False  # 글자 2자 이상
    return True

def parse_stocks(text):
    comp = re.sub(r"\s+", "", text)
    accepted, raw_matches, rejected = [], 0, 0
    for m in STOCK_RE.finditer(comp):
        name = m.group(1).strip("().·")
        qty = m.group(2).replace(",", "")
        if not qty.isdigit(): continue
        raw_matches += 1                               # 'N주' 패턴 총개수
        if valid_name(name):
            accepted.append({"종목": name, "수량주": int(qty)})
        else:
            rejected += 1                              # 깨진 종목명(칸뭉침·소수점분할주 등)
    # OCR이 같은 셀을 연속 중복 인식하는 경우만 1회로 축약(서로 다른 수량은 본인/배우자
    # 별도 보유일 수 있어 보존). 종목 합산은 하지 않는다 — 원문 대조가 쉽도록 발견 순서 유지.
    dedup = []
    for h in accepted:
        if dedup and dedup[-1] == h: continue
        dedup.append(h)
    # 검토필요: 깨진 'N주' 패턴이 하나라도 있었던 경우(원문 수동 대조 필요)
    needs_review = rejected > 0
    return dedup, comp, needs_review, raw_matches

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offices", default="3,4,2", help="선거종류코드 CSV 또는 all")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--winners", action="store_true", help="당선자(data/winner_huboids.json)만 대상")
    args = ap.parse_args()

    main_snap = json.load(open(sorted(glob.glob(os.path.join(RID, "data/candidates/20260603/snapshot_*.json")))[-1], encoding="utf-8"))["candidates"]
    want = None if args.offices == "all" else set(args.offices.split(","))
    cands = [c for c in main_snap if str(c.get("status")) == "등록" and (want is None or str(c.get("sgTypecode")) in want)]
    if args.winners:
        wh = set(json.load(open(os.path.join(RID, "data/winner_huboids.json"), encoding="utf-8"))["huboids"])
        cands = [c for c in cands if str(c.get("huboid")) in wh]
    if args.limit: cands = cands[:args.limit]
    print(f"대상 {len(cands)}명 (offices={args.offices}, winners={args.winners})", flush=True)

    out = []
    review_only = 0
    for i, c in enumerate(cands, 1):
        txt = ocr_assets(c["huboid"])
        stocks, raw, needs_review, raw_matches = parse_stocks(txt) if txt else ([], "", False, 0)
        # 깨끗한 보유가 있거나, 'N주' 패턴이 잡혔는데 못 뽑은(검토필요) 경우만 수록
        if stocks or raw_matches:
            if not stocks: review_only += 1
            out.append({"huboid": c["huboid"], "name": c.get("name"),
                        "party": c.get("jdName") or "무소속", "office": SGTYPE.get(str(c.get("sgTypecode"))),
                        "sido": c.get("sdName"), "sgg": c.get("sggName") or c.get("wiwName") or "",
                        "종목수": len(stocks), "needs_review": needs_review,
                        "raw_matches": raw_matches, "holdings": stocks, "raw_section": raw})
        if i % 50 == 0: print(f"...{i}/{len(cands)} · 수록 {len(out)}명(검토필요만 {review_only})", flush=True)

    os.makedirs(os.path.join(RID, "data"), exist_ok=True)
    clean = [p for p in out if p["holdings"]]
    review = [p for p in out if not p["holdings"]]
    json.dump({"generated": "2026-06-03", "offices": args.offices,
               "count": len(out), "clean": len(clean), "review_only": len(review),
               "note": "스캔 재산서식 OCR 자동추출. needs_review=true는 'N주' 패턴은 잡혔으나 "
                       "OCR 칸뭉침·소수점분할주 등으로 깨끗이 못 뽑은 건 → raw_section 원문 수동 대조 필수. "
                       "기사화 전 전건 원문 대조 권장.", "people": out},
              open(os.path.join(RID, "data/stock_holdings.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    import csv as C
    with open(os.path.join(RID, "data/stock_holdings.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = C.writer(f); w.writerow(["huboid","name","party","office","sido","sgg","종목","수량주","검토필요"])
        for p in out:
            if p["holdings"]:
                for h in p["holdings"]:
                    w.writerow([p["huboid"],p["name"],p["party"],p["office"],p["sido"],p["sgg"],h["종목"],h["수량주"],"Y" if p["needs_review"] else ""])
            else:  # 검토필요 전용(깨끗한 추출 0)
                w.writerow([p["huboid"],p["name"],p["party"],p["office"],p["sido"],p["sgg"],"(검토필요)","","Y"])
    print(f"DONE 수록 {len(out)}명 = 깨끗 {len(clean)} + 검토필요 {len(review)} → data/stock_holdings.json/.csv")

if __name__ == "__main__":
    main()
