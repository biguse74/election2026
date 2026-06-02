# -*- coding: utf-8 -*-
"""후보 공개자료 스캔 PDF를 인물별로 영구 아카이브한다.
입력 : data/candidate_details.json (scan_files 포함, fetch_candidate_details.py 선행)
       data/candidates/20260603/snapshot_*.json (status·birthday 조인)
출력 : data/disclosure_archive/{huboid}_{이름}/{종류}/*.PDF + manifest.json
       data/disclosure_archive/_index.json
선거 후 info.nec.go.kr 소실 대비 원본 보존. 재실행 안전(이미 받은 파일 skip).
"""
import json, os, re, glob, sys, time, threading
from concurrent.futures import ThreadPoolExecutor, as_completed
import urllib.request, urllib.error

RID = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
def P(*a): return os.path.join(RID, *a)
ARCH = P("data", "disclosure_archive")
DOCTYPE_KR = {"assets": "재산", "tax": "납세", "military": "병역", "criminal": "전과"}
HEADERS = {"User-Agent": "newtamsa-election2026/1.0 (+https://github.com/biguse74/election2026)",
           "Referer": "https://info.nec.go.kr/"}
_lock = threading.Lock()
done_files = [0]; done_people = [0]; fails = []

def safe(s): return re.sub(r"[^\w가-힣]", "", str(s or ""))[:20]

def download(url, dest):
    if os.path.exists(dest) and os.path.getsize(dest) > 0:
        return True
    try:
        rq = urllib.request.Request(url, headers=HEADERS)
        b = urllib.request.urlopen(rq, timeout=40).read()
        if not b or b[:4] not in (b"%PDF", b"\xff\xd8\xff\xe0", b"\xff\xd8\xff\xe1"):
            # PDF or JPEG magic; otherwise still save (NEC pdf wrappers)
            pass
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as f: f.write(b)
        return True
    except Exception as e:
        with _lock: fails.append({"url": url, "err": str(e)[:80]})
        return False

def main():
    det = json.load(open(P("data", "candidate_details.json"), encoding="utf-8"))["details"]
    main_snap = {c["huboid"]: c for c in json.load(open(sorted(glob.glob(P("data/candidates/20260603/snapshot_*.json")))[-1], encoding="utf-8"))["candidates"]}
    os.makedirs(ARCH, exist_ok=True)
    index = []

    def handle(c):
        hid = c["huboid"]; m = main_snap.get(hid, {})
        if str(m.get("status") or c.get("status")) not in ("등록", ""):  # 본선만
            if m and str(m.get("status")) != "등록":
                return None
        folder = os.path.join(ARCH, f"{hid}_{safe(c.get('name'))}")
        files_map = {}
        for dtype, items in (c.get("scan_files") or {}).items():
            kr = DOCTYPE_KR.get(dtype, dtype)
            paths = []
            for i, it in enumerate(items, 1):
                url = it.get("pdf_url")
                if not url: continue
                dest = os.path.join(folder, kr, f"{kr}_{i:02d}.PDF")
                if download(url, dest):
                    paths.append(os.path.relpath(dest, ARCH).replace("\\", "/"))
                    with _lock: done_files[0] += 1
            if paths: files_map[kr] = paths
        # 사진
        photo = (c.get("photo") or {}).get("url")
        if photo:
            pdest = os.path.join(folder, "photo.jpg")
            if download(photo, pdest): files_map["사진"] = ["photo.jpg"]
        manifest = {
            "huboid": hid, "name": c.get("name"), "party": c.get("jdName") or m.get("jdName") or "무소속",
            "office": m.get("sgTypecode"), "sido": c.get("sdName"), "sgg": c.get("sggName") or m.get("wiwName") or "",
            "birthday": m.get("birthday"), "status": m.get("status"),
            "nec_detail_url": c.get("nec_detail_url"),
            "disclosures": c.get("disclosures"), "files": files_map,
        }
        if files_map:
            os.makedirs(folder, exist_ok=True)
            json.dump(manifest, open(os.path.join(folder, "manifest.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        with _lock:
            done_people[0] += 1
            if done_people[0] % 200 == 0:
                print(f"...{done_people[0]}/{len(det)}명 · 파일 {done_files[0]} · 실패 {len(fails)}", flush=True)
        return {k: manifest[k] for k in ("huboid","name","party","office","sido","sgg","birthday")} | {"has": list(files_map)}

    with ThreadPoolExecutor(max_workers=10) as ex:
        futs = [ex.submit(handle, c) for c in det]
        for f in as_completed(futs):
            r = f.result()
            if r: index.append(r)

    json.dump({"generated": "2026-06-03", "count": len(index), "people": index},
              open(os.path.join(ARCH, "_index.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(fails, open(os.path.join(ARCH, "_failures.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"DONE 인물 {len(index)} · PDF {done_files[0]} · 실패 {len(fails)} → {ARCH}")

if __name__ == "__main__":
    main()
