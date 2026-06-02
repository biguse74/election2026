# -*- coding: utf-8 -*-
"""최종 본선 후보(등록) 기준 재산·병역·납세·전과 마스터 조인 + 헤드라인 통계.
입력: 본선 스냅샷(status), candidate_details(disclosures), criminal_ocr(죄목 detail)
출력: exports/disclosure_master/master.csv, summary.json
"""
import json, glob, csv, os, statistics
from collections import Counter, defaultdict

RID = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def P(*a): return os.path.join(RID, *a)

SGTYPE = {"2":"국회의원(재보선)","3":"시도지사","4":"기초단체장","5":"시도의원",
          "6":"구시군의회의원","8":"광역비례","9":"기초비례","11":"교육감"}

main = {c["huboid"]: c for c in json.load(open(sorted(glob.glob(P("data/candidates/20260603/snapshot_*.json")))[-1], encoding="utf-8"))["candidates"]}
det  = {c["huboid"]: c for c in json.load(open(sorted(glob.glob(P("data/candidate_details/20260603/snapshot_*.json")))[-1], encoding="utf-8"))["details"]}
ocr  = {r["huboid"]: r for r in json.load(open(P("data/criminal_ocr.json"), encoding="utf-8"))["records"]}

def to_int(s):
    try: return int(str(s).replace(",", "").strip())
    except: return None

rows = []
for hid, c in main.items():
    if str(c.get("status")) != "등록":   # 본선 투표용지 후보만
        continue
    dd = (det.get(hid) or {}).get("disclosures") or {}
    o  = ocr.get(hid)
    offenses = (o or {}).get("offenses") or []
    cats = sorted({cat for off in offenses for cat in (off.get("categories") or [])})
    assets = to_int(dd.get("assets_thousand_krw"))            # 천원
    tax_paid = to_int(dd.get("tax_paid_thousand_krw"))
    arr_cur = to_int(dd.get("tax_arrears_current_thousand_krw"))
    arr_5y  = to_int(dd.get("tax_arrears_5y_thousand_krw"))
    crim = (dd.get("criminal_record") or "").strip()
    has_crime = bool(crim and crim != "없음")
    rows.append({
        "huboid": hid, "name": c.get("name"), "party": c.get("jdName") or "무소속",
        "sgType": SGTYPE.get(str(c.get("sgTypecode")), str(c.get("sgTypecode"))),
        "sido": c.get("sdName"), "sgg": c.get("sggName") or c.get("wiwName") or "",
        "assets_1k": assets, "tax_paid_1k": tax_paid,
        "arrears_cur_1k": arr_cur, "arrears_5y_1k": arr_5y,
        "military": dd.get("military") or "",
        "criminal_summary": crim, "has_crime": has_crime,
        "offense_count": len(offenses),
        "offense_categories": "|".join(cats),
        "offenses_raw": " ; ".join(f"{x.get('date','')} {x.get('offense','')} {x.get('sentence','')}" for x in offenses),
    })

os.makedirs(P("exports/disclosure_master"), exist_ok=True)
cols = list(rows[0].keys())
with open(P("exports/disclosure_master/master.csv"), "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)

def agg(key):
    g = defaultdict(list)
    for r in rows: g[r[key]].append(r)
    out = []
    for k, rs in g.items():
        n = len(rs); nc = sum(1 for r in rs if r["has_crime"])
        oc = [r["offense_count"] for r in rs if r["has_crime"]]
        arr = sum(1 for r in rs if (r["arrears_cur_1k"] or 0) > 0)
        assets = [r["assets_1k"] for r in rs if r["assets_1k"] is not None]
        out.append({key: k, "후보수": n, "전과자": nc, "전과율%": round(100*nc/n,1),
                    "평균전과건수": round(statistics.mean(oc),2) if oc else 0,
                    "현체납자": arr,
                    "재산중위(억)": round(statistics.median(assets)/100000,2) if assets else None})
    return sorted(out, key=lambda x: -x["후보수"])

summary = {
    "generated": "2026-06-03", "본선등록후보": len(rows),
    "전과보유": sum(1 for r in rows if r["has_crime"]),
    "by_party": [x for x in agg("party") if x["후보수"] >= 20],
    "by_sgType": agg("sgType"),
    "by_sido": agg("sido"),
    "죄목카테고리": Counter(cat for r in rows for cat in r["offense_categories"].split("|") if cat).most_common(25),
    "현체납자수": sum(1 for r in rows if (r["arrears_cur_1k"] or 0) > 0),
}
json.dump(summary, open(P("exports/disclosure_master/summary.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

print(f"본선 등록 후보 {len(rows)}명 | 전과보유 {summary['전과보유']}명 ({round(100*summary['전과보유']/len(rows),1)}%)")
print("\n[선거종류별 전과율]")
for x in summary["by_sgType"]:
    print(f"  {x['sgType']:14s} 후보{x['후보수']:5d} 전과{x['전과자']:4d} ({x['전과율%']:4.1f}%) 평균{x['평균전과건수']}건")
print("\n[주요 정당별 전과율]")
for x in summary["by_party"][:8]:
    print(f"  {x['party']:12s} 후보{x['후보수']:5d} 전과율{x['전과율%']:5.1f}% 현체납{x['현체납자']:3d} 재산중위{x['재산중위(억)']}억")
print("\n[죄목 카테고리 top15]")
for cat,n in summary["죄목카테고리"][:15]:
    print(f"  {cat:12s} {n}")
print(f"\n현 체납자 총 {summary['현체납자수']}명 | 저장: exports/disclosure_master/")
