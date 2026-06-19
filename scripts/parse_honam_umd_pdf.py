#!/usr/bin/env python3
"""호남 기초단체장 '개표단위별 개표결과' PDF(선거통계시스템 출력) → 읍·면·동별 CSV.

입력:  tmp/honam_umd_pdf/*.pdf  (시군별 PDF, 파일명 무관 — 내부 헤더로 시군 판정)
출력:  data/honam_umd/<시도>_<시군>.csv  +  data/honam_umd/_manifest.json

CSV 스키마(부산 xlsx 변환기와 동일 계열):
  선거구명,동,투표구명,분류,선거인수,투표수,<정당_후보...>,유효표_계,무효투표수,기권자수
  분류: race_total(합계) / special(거소·관외사전·국외·잘못투입) / subtotal(읍면동 계) / ballot(관내사전·선거일)

검증(보정 없이 기록):
  1) subtotal(동 계)+special 투표수 합 == race_total(합계) 투표수
  2) 각 행 후보 득표수 합 == 유효표_계
"""
from __future__ import annotations
import csv, json, re, sys, unicodedata, glob, os
from pathlib import Path
import pdfplumber

ROOT = Path(__file__).resolve().parent.parent
IN_DIR = ROOT / "tmp/honam_umd_pdf"
OUT_DIR = ROOT / "data/honam_umd"

GWANGJU = ["동구", "서구", "남구", "북구", "광산구"]
JEONNAM = ["목포시", "여수시", "순천시", "나주시", "광양시", "담양군", "곡성군", "구례군", "고흥군", "보성군",
           "화순군", "장흥군", "강진군", "해남군", "영암군", "무안군", "함평군", "영광군", "장성군", "완도군", "진도군", "신안군"]
JEONBUK = ["전주시", "군산시", "익산시", "정읍시", "남원시", "김제시", "완주군", "진안군", "무주군", "장수군",
           "임실군", "순창군", "고창군", "부안군"]
CANON = [("광주광역시", g) for g in GWANGJU] + [("전라남도", g) for g in JEONNAM] + [("전북특별자치도", g) for g in JEONBUK]
SD_STD = {"전라북도": "전북특별자치도", "강원도": "강원특별자치도"}
nfc = lambda s: unicodedata.normalize("NFC", s or "")

# 시군명 → (시도,시군). 광주 자치구는 시군명만으로 유일. 전주 완산/덕진 → 전주시.
SGG2 = {nfc(g): (sd, g) for sd, g in CANON}
SGG2[nfc("전주시완산구")] = ("전북특별자치도", "전주시")
SGG2[nfc("전주시덕진구")] = ("전북특별자치도", "전주시")
SGG2[nfc("완산구")] = ("전북특별자치도", "전주시")
SGG2[nfc("덕진구")] = ("전북특별자치도", "전주시")

GUBUN_DONG = {"계", "소계", "관내사전투표", "선거일투표"}          # 읍면동명 뒤에 붙는 구분
SPECIAL_WHOLE = {"거소투표", "거소·선상투표", "관외사전투표", "국외부재자투표"}
NUM = re.compile(r"^-?[\d,]+$")

def to_int(t):
    t = t.replace(",", "")
    return int(t) if re.fullmatch(r"-?\d+", t) else None

def parse_pdf(path):
    pages = []
    with pdfplumber.open(path) as pdf:
        for pg in pdf.pages:
            pages.append((pg.extract_text() or "").split("\n"))
    lines = [l.strip() for pglines in pages for l in pglines if l.strip()]

    # 시도·시군 (조회조건 라인)
    head = " ".join(lines[:30])
    m = re.search(r"시도\s+(\S+).*?선거구\(구시군\)\s+(\S+)", head)
    sd_raw = m.group(1) if m else ""
    sgg_raw = m.group(2) if m else ""
    sd = SD_STD.get(sd_raw, sd_raw)

    # 무투표 선거구 — 개표 데이터 없음
    if any("무투표선거구" in l for l in lines):
        return sd, sgg_raw, [], [], "무투표"

    # 후보 컬럼: 단독 '계' 헤더 줄을 찾아 직전=정당, 직후=후보명
    parties = names = None
    for i, l in enumerate(lines):
        if l == "계" and i >= 1 and i + 1 < len(lines):
            cand_parties = lines[i - 1].split()
            cand_names = lines[i + 1].split()
            if cand_parties and len(cand_parties) == len(cand_names) and \
               all(re.match(r"[가-힣]+$", p) for p in cand_parties):
                parties, names = cand_parties, cand_names
                break
    if not parties:
        raise ValueError("후보 헤더 파싱 실패")
    N = len(parties)
    candcols = [f"{p}_{n}" for p, n in zip(parties, names)]

    # 데이터 행: 끝에서 N+5개 정수 토큰 + 앞쪽 라벨
    rows = []
    NEED = N + 5
    for l in lines:
        toks = l.split()
        if len(toks) < NEED:
            continue
        tail = toks[-NEED:]
        if not all(NUM.match(t) for t in tail):
            continue
        label = toks[:-NEED]
        nums = [to_int(t) for t in tail]
        if any(v is None for v in nums):
            continue
        eligible, voted = nums[0], nums[1]
        cvotes = nums[2:2 + N]
        valid, invalid, abstain = nums[2 + N], nums[3 + N], nums[4 + N]

        if not label:                                   # 잘못투입(라벨 줄바꿈) — 숫자만
            dong, box, kind = "전체", "잘못투입·구분된투표지", "special"
        elif label == ["합계"]:
            dong, box, kind = "전체", "합계", "race_total"
        elif nfc(" ".join(label)) in {nfc(x) for x in SPECIAL_WHOLE}:
            dong, box, kind = "전체", " ".join(label), "special"
        elif label[-1] in GUBUN_DONG:
            dong = " ".join(label[:-1]) or "전체"
            box = label[-1]
            kind = "subtotal" if box in ("계", "소계") else "ballot"
        else:
            dong, box, kind = " ".join(label), "기타", "other"

        d = {"선거구명": sgg_raw, "동": dong, "투표구명": box, "분류": kind,
             "선거인수": eligible, "투표수": voted}
        for c, v in zip(candcols, cvotes):
            d[c] = v
        d["유효표_계"] = valid; d["무효투표수"] = invalid; d["기권자수"] = abstain
        rows.append(d)
    return sd, sgg_raw, candcols, rows, "ok"

def verify(rows, candcols):
    row_bad = []
    for r in rows:
        cs = sum(r.get(c) or 0 for c in candcols)
        if r.get("유효표_계") is not None and cs != r["유효표_계"]:
            row_bad.append((r["동"], r["투표구명"], cs, r["유효표_계"]))
    rt = next((r["투표수"] for r in rows if r["분류"] == "race_total"), None)
    sub = sum(r["투표수"] or 0 for r in rows if r["분류"] in ("subtotal", "special"))
    return {"race_total_투표수": rt, "subtotal+special_합": sub,
            "합계검증_통과": (rt is not None and rt == sub),
            "후보합_불일치행수": len(row_bad), "불일치샘플": row_bad[:5]}

def write_csv(path, rows, candcols):
    fields = ["선거구명", "동", "투표구명", "분류", "선거인수", "투표수", *candcols, "유효표_계", "무효투표수", "기권자수"]
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)

def merge_jeonju(groups):
    """완산+덕진 → 전주시. 합계행은 합산, 나머지(읍면동/특수) 이어붙임. candcols 동일 가정."""
    candcols = groups[0][0]
    rt = {"선거구명": "전주시", "동": "전체", "투표구명": "합계", "분류": "race_total",
          "선거인수": 0, "투표수": 0, **{c: 0 for c in candcols}, "유효표_계": 0, "무효투표수": 0, "기권자수": 0}
    body = []
    for cc, rows in groups:
        for r in rows:
            r = dict(r); r["선거구명"] = "전주시"
            if r["분류"] == "race_total":
                for k in ("선거인수", "투표수", "유효표_계", "무효투표수", "기권자수", *candcols):
                    rt[k] = (rt.get(k) or 0) + (r.get(k) or 0)
            else:
                body.append(r)
    return candcols, [rt] + body

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    files = sorted(glob.glob(str(IN_DIR / "*.pdf")))
    groups = {}; muvote = {}; unrouted = []
    for p in files:
        try:
            sd, sgg_raw, candcols, rows, status = parse_pdf(p)
        except Exception as e:
            unrouted.append((os.path.basename(p), f"파싱오류 {e}")); continue
        key = SGG2.get(nfc(sgg_raw))
        if not key:
            for k, v in SGG2.items():
                if k in nfc(sgg_raw) or nfc(sgg_raw) in k:
                    key = v; break
        if not key:
            unrouted.append((os.path.basename(p), f"라우팅실패 선거구명={sgg_raw}")); continue
        if status == "무투표":
            muvote[key] = os.path.basename(p); continue
        groups.setdefault(key, []).append((candcols, rows))

    manifest = {"generated_by": "parse_honam_umd_pdf.py", "단위": "읍·면·동(개표단위별)",
                "분류값": "race_total/special/subtotal/ballot", "rows": {}}
    done = miss = muv = 0
    for sd, sgg in CANON:
        out_csv = OUT_DIR / f"{sd}_{sgg}.csv"
        grp = groups.get((sd, sgg))
        if (sd, sgg) in muvote and not grp:
            with out_csv.open("w", encoding="utf-8-sig", newline="") as f:
                f.write("선거구명,동,투표구명,분류,비고\n")
                f.write(f"{sgg},전체,,무투표,\"무투표선거구 — 개표 없음(무투표 당선)\"\n")
            manifest["rows"][f"{sd}_{sgg}"] = {"status": "무투표", "pdf": muvote[(sd, sgg)]}
            muv += 1; print(f"  ◻ {sd} {sgg}: 무투표선거구")
            continue
        if not grp:
            with out_csv.open("w", encoding="utf-8-sig", newline="") as f:
                f.write("선거구명,동,투표구명,분류,비고\n")
                f.write(f"{sgg},전체,,미수집,\"PDF 없음 — 미수집(재다운로드 필요)\"\n")
            manifest["rows"][f"{sd}_{sgg}"] = {"status": "미수집"}
            miss += 1; print(f"  ⚠ {sd} {sgg}: PDF 없음(미수집)")
            continue
        try:
            if len(grp) >= 2:
                candcols, rows = merge_jeonju(grp)
            else:
                candcols, rows = grp[0]
            write_csv(out_csv, rows, candcols)
            v = verify(rows, candcols)
            manifest["rows"][f"{sd}_{sgg}"] = {"status": "ok", "행수": len(rows), "후보": candcols, **v}
            done += 1
            ok = v["합계검증_통과"] and v["후보합_불일치행수"] == 0
            print(f"  {'✓' if ok else '✗검증주의'} {sd} {sgg}: {len(rows)}행 합계검증={v['합계검증_통과']} 후보합불일치={v['후보합_불일치행수']}")
        except Exception as e:
            manifest["rows"][f"{sd}_{sgg}"] = {"status": "error", "error": str(e)}
            print(f"  ✗ {sd} {sgg}: 오류 {e}")
    if unrouted:
        manifest["라우팅실패"] = unrouted
        print("\n⚠ 라우팅/파싱 실패:", unrouted)
    manifest["요약"] = {"총시군": len(CANON), "개표처리": done, "무투표": muv, "미수집": miss, "입력PDF": len(files)}
    (OUT_DIR / "_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n총 {len(CANON)}시군 | 개표처리 {done} | 무투표 {muv} | 미수집 {miss} | 입력PDF {len(files)}")

if __name__ == "__main__":
    main()
