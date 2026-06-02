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

# 주식 섹션만 잘라 노이즈 축소
SEC_START = ("유가증권", "상장주식", "비상장주식", "출자지분", "증권")
SEC_END = ("채무", "신고인", "서약", "재산신고사항없음", "본인은공직")
# (종목명)(수량)주  — 종목명은 한글/영문/괄호/·, 2~22자
STOCK_RE = re.compile(r"([가-힣A-Za-z][가-힣A-Za-z0-9()·\.]{1,21}?)\s*([\d,]{1,12})\s*주")
NONNAME = re.compile(r"^[\d,]+$|소계|합계|가액|수량|종류|성명|관계|비고|천원|배우자|본인|장남|장녀|차남")

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

def parse_stocks(text):
    comp = re.sub(r"\s+", "", text)
    # 섹션 추출
    starts = [comp.find(k) for k in SEC_START if comp.find(k) >= 0]
    seg = comp[min(starts):] if starts else comp
    ends = [seg.find(k) for k in SEC_END if seg.find(k) > 0]
    if ends: seg = seg[:min(ends)]
    holdings = []
    for m in STOCK_RE.finditer(seg):
        name = m.group(1).strip("().·")
        qty = m.group(2).replace(",", "")
        if NONNAME.search(name) or len(name) < 2 or not qty.isdigit(): continue
        holdings.append({"종목": name, "수량주": int(qty)})
    # 종목 중복 합산
    agg = {}
    for h in holdings:
        agg[h["종목"]] = agg.get(h["종목"], 0) + h["수량주"]
    return [{"종목": k, "수량주": v} for k, v in agg.items()], seg[:600]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--offices", default="3,4,2", help="선거종류코드 CSV 또는 all")
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    main_snap = json.load(open(sorted(glob.glob(os.path.join(RID, "data/candidates/20260603/snapshot_*.json")))[-1], encoding="utf-8"))["candidates"]
    want = None if args.offices == "all" else set(args.offices.split(","))
    cands = [c for c in main_snap if str(c.get("status")) == "등록" and (want is None or str(c.get("sgTypecode")) in want)]
    if args.limit: cands = cands[:args.limit]
    print(f"대상 {len(cands)}명 (offices={args.offices})", flush=True)

    out = []
    for i, c in enumerate(cands, 1):
        txt = ocr_assets(c["huboid"])
        stocks, raw = parse_stocks(txt) if txt else ([], "")
        if stocks:
            out.append({"huboid": c["huboid"], "name": c.get("name"),
                        "party": c.get("jdName") or "무소속", "office": SGTYPE.get(str(c.get("sgTypecode"))),
                        "sido": c.get("sdName"), "sgg": c.get("sggName") or c.get("wiwName") or "",
                        "종목수": len(stocks), "holdings": stocks, "raw_section": raw})
        if i % 50 == 0: print(f"...{i}/{len(cands)} · 주식보유 {len(out)}명", flush=True)

    os.makedirs(os.path.join(RID, "data"), exist_ok=True)
    json.dump({"generated": "2026-06-03", "offices": args.offices, "count": len(out),
               "note": "스캔 재산서식 OCR 자동추출. 기사 전 raw_section 원문 대조 필수.", "people": out},
              open(os.path.join(RID, "data/stock_holdings.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    import csv as C
    with open(os.path.join(RID, "data/stock_holdings.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = C.writer(f); w.writerow(["huboid","name","party","office","sido","sgg","종목","수량주"])
        for p in out:
            for h in p["holdings"]:
                w.writerow([p["huboid"],p["name"],p["party"],p["office"],p["sido"],p["sgg"],h["종목"],h["수량주"]])
    print(f"DONE 주식보유 {len(out)}명 → data/stock_holdings.json/.csv")

if __name__ == "__main__":
    main()
