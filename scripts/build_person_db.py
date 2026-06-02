# -*- coding: utf-8 -*-
"""인물 DB 구축 — 재산·병역·납세·전과 + 아카이브 PDF + 사진을 인물 단위로 결합.
재출마 추적 키 = 이름 + 생년월일 (huboid는 선거마다 바뀜).
입력 : data/candidates/20260603/snapshot_*.json (기본정보·birthday·status)
       data/candidate_details/20260603/snapshot_*.json (disclosures·photo)
       data/criminal_ocr.json (전과 상세 죄목)
       data/disclosure_archive/{huboid}_{name}/manifest.json (PDF 경로)
출력 : data/person_db.json, data/person_db.csv, data/person_db.sqlite
"""
import json, os, glob, csv, hashlib, sqlite3, re

RID = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def P(*a): return os.path.join(RID, *a)
SGTYPE = {"2":"국회의원","3":"시도지사","4":"기초단체장","5":"시도의원","6":"구시군의회의원","8":"광역비례","9":"기초비례","11":"교육감"}
ARCH = P("data", "disclosure_archive")

def to_int(s):
    try: return int(str(s).replace(",", "").strip())
    except: return None

main = json.load(open(sorted(glob.glob(P("data/candidates/20260603/snapshot_*.json")))[-1], encoding="utf-8"))["candidates"]
det  = {c["huboid"]: c for c in json.load(open(sorted(glob.glob(P("data/candidate_details/20260603/snapshot_*.json")))[-1], encoding="utf-8"))["details"]}
ocr  = {r["huboid"]: r for r in json.load(open(P("data/criminal_ocr.json"), encoding="utf-8"))["records"]}

def archive_files(hid, name):
    mf = os.path.join(ARCH, f"{hid}_{re.sub(r'[^\\w가-힣]','',str(name))[:20]}", "manifest.json")
    if os.path.exists(mf):
        try: return json.load(open(mf, encoding="utf-8")).get("files", {})
        except: return {}
    return {}

people = {}
for c in main:
    if str(c.get("status")) != "등록":
        continue
    hid = c["huboid"]; name = c.get("name"); bday = c.get("birthday") or ""
    pid = hashlib.sha1(f"{name}|{bday}".encode()).hexdigest()[:12]
    dd = (det.get(hid) or {}).get("disclosures") or {}
    o = ocr.get(hid)
    offenses = (o or {}).get("offenses") or []
    candidacy = {
        "huboid": hid, "sgId": c.get("sgId"),
        "office": SGTYPE.get(str(c.get("sgTypecode")), str(c.get("sgTypecode"))),
        "party": c.get("jdName") or "무소속", "sido": c.get("sdName"),
        "sgg": c.get("sggName") or c.get("wiwName") or "", "num": c.get("num"),
        "status": c.get("status"),
        "assets_1k": to_int(dd.get("assets_thousand_krw")),
        "tax_paid_1k": to_int(dd.get("tax_paid_thousand_krw")),
        "arrears_cur_1k": to_int(dd.get("tax_arrears_current_thousand_krw")),
        "military": dd.get("military") or "",
        "criminal_summary": dd.get("criminal_record") or "",
        "offense_count": len(offenses),
        "offense_categories": sorted({cat for off in offenses for cat in (off.get("categories") or [])}),
        "offenses": [{"date": x.get("date"), "offense": x.get("offense"), "sentence": x.get("sentence")} for x in offenses],
        "nec_detail_url": (det.get(hid) or {}).get("nec_detail_url"),
        "pdf_archive": archive_files(hid, name),
        "candidacy_count": dd.get("candidacy_count") if False else (det.get(hid, {}).get("disclosures", {}) or {}).get("candidacy_count"),
    }
    p = people.setdefault(pid, {
        "person_id": pid, "name": name, "birthday": bday,
        "age": c.get("age"), "gender": c.get("gender"), "edu": c.get("edu"),
        "career1": c.get("career1"), "career2": c.get("career2"), "job": c.get("job"),
        "photo": ((det.get(hid) or {}).get("photo") or {}).get("url"),
        "candidacies": [],
    })
    p["candidacies"].append(candidacy)

plist = sorted(people.values(), key=lambda x: x["name"])
json.dump({"generated": "2026-06-03", "election": "20260603", "person_count": len(plist),
           "candidacy_count": sum(len(p["candidacies"]) for p in plist), "people": plist},
          open(P("data/person_db.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)

# CSV (인물 1행, 대표 출마 1건 평면화)
cols = ["person_id","name","birthday","age","gender","office","party","sido","sgg",
        "assets_1k","arrears_cur_1k","military","offense_count","offense_categories",
        "career1","photo","pdf_재산","pdf_전과","nec_detail_url"]
with open(P("data/person_db.csv"), "w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=cols); w.writeheader()
    for p in plist:
        c0 = p["candidacies"][0]; arc = c0["pdf_archive"]
        w.writerow({"person_id":p["person_id"],"name":p["name"],"birthday":p["birthday"],
            "age":p["age"],"gender":p["gender"],"office":c0["office"],"party":c0["party"],
            "sido":c0["sido"],"sgg":c0["sgg"],"assets_1k":c0["assets_1k"],
            "arrears_cur_1k":c0["arrears_cur_1k"],"military":c0["military"],
            "offense_count":c0["offense_count"],"offense_categories":"|".join(c0["offense_categories"]),
            "career1":p["career1"],"photo":p["photo"],
            "pdf_재산":len(arc.get("재산",[])),"pdf_전과":len(arc.get("전과",[])),
            "nec_detail_url":c0["nec_detail_url"]})

# SQLite (조회용)
db = P("data/person_db.sqlite")
if os.path.exists(db): os.remove(db)
con = sqlite3.connect(db); cur = con.cursor()
cur.execute("""CREATE TABLE person(person_id TEXT, name TEXT, birthday TEXT, age INT, gender TEXT,
    office TEXT, party TEXT, sido TEXT, sgg TEXT, assets_1k INT, arrears_cur_1k INT,
    military TEXT, offense_count INT, offense_categories TEXT, career1 TEXT, photo TEXT, nec_detail_url TEXT)""")
for p in plist:
    c0 = p["candidacies"][0]
    cur.execute("INSERT INTO person VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (p["person_id"],p["name"],p["birthday"],p["age"],p["gender"],c0["office"],c0["party"],
         c0["sido"],c0["sgg"],c0["assets_1k"],c0["arrears_cur_1k"],c0["military"],
         c0["offense_count"],"|".join(c0["offense_categories"]),p["career1"],p["photo"],c0["nec_detail_url"]))
con.commit()
dup = cur.execute("SELECT name,birthday,COUNT(*) c FROM person GROUP BY person_id HAVING c>1").fetchall()
con.close()

archived = sum(1 for p in plist for c in p["candidacies"] if c["pdf_archive"])
print(f"인물 {len(plist)}명 · 출마 {sum(len(p['candidacies']) for p in plist)}건 · 아카이브연결 {archived}건")
print(f"동일인 중복출마(이름+생일): {len(dup)}건")
print(f"산출: data/person_db.json · person_db.csv · person_db.sqlite")
