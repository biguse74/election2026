#!/usr/bin/env python3
"""
선관위 '개표현황(투표구별)' xlsx 여러 회차를 long-format CSV로 통합.

입력 (수동 배치):
    tmp/nec_busan_buk_17.xlsx ~ 22.xlsx

출력:
    exports/busan_buk_history_dong.csv

long-format 스키마:
    회차, 연도, 선거일, 선거구명, 동, 투표구명, 분류,
    선거인수, 투표수, 유효표_계, 무효투표수, 기권자수,
    후보순번, 정당, 후보명, 득표수, 득표율_유효표대비
"""

from __future__ import annotations

import csv
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
NS_T = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t"

ROOT = Path(__file__).resolve().parent.parent
TMP = ROOT / "tmp"
OUT = ROOT / "exports" / "busan_buk_history_dong.csv"

# 회차 → (연도, 선거일)
ELECTIONS = {
    17: (2004, "2004-04-15"),
    18: (2008, "2008-04-09"),
    19: (2012, "2012-04-11"),
    20: (2016, "2016-04-13"),
    21: (2020, "2020-04-15"),
    22: (2024, "2024-04-10"),
}

DONG_PAT = re.compile(r"^(.+?동)제(\d+)투\s*$")
SPECIAL_NAMES = {
    # 사전투표 제도 도입(2014) 후
    "거소·선상투표", "관외사전투표", "관내사전투표", "국외부재자투표",
    # 사전투표 도입 전 — 부재자 통합
    "부재자투표", "관외부재자투표", "국외부재자",
    "거소투표", "선상투표", "재외선거",
    # 분류 라벨
    "소계",
}


def read_sheet_rows(path: Path) -> list[list]:
    with zipfile.ZipFile(path) as z:
        shared: list[str] = []
        try:
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("s:si", NS):
                shared.append("".join((t.text or "") for t in si.iter(NS_T)))
        except KeyError:
            pass
        sheet_xml = next(e for e in z.namelist() if "worksheets/sheet" in e.lower() and e.endswith(".xml"))
        sheet = ET.fromstring(z.read(sheet_xml))
        rows = []
        sd = sheet.find("s:sheetData", NS)
        if sd is None:
            return rows
        for row in sd.findall("s:row", NS):
            cells = []
            for c in row.findall("s:c", NS):
                t = c.get("t")
                v = c.find("s:v", NS)
                val = v.text if v is not None else None
                if t == "s" and val is not None:
                    val = shared[int(val)]
                cells.append(val)
            rows.append(cells)
        return rows


def to_int(v):
    if v in (None, "", "null"):
        return None
    s = str(v).replace(",", "").strip()
    if not s or s == "-":
        return None
    try:
        return int(float(s))
    except ValueError:
        return None


def classify(name: str) -> str:
    if not name:
        return "blank"
    if DONG_PAT.match(name):
        return "box"
    if name == "계":
        return "race_total"
    if name == "소계":
        return "subtotal"
    if name == "관내사전투표":
        return "early"
    # 알려진 특수투표 또는 '투표' 끝나는 모든 라벨 (회차마다 명칭 다름)
    if name in SPECIAL_NAMES or name.endswith("투표"):
        return "special"
    return "other"


def extract_candidates_from_row6(row6: list, cand_count: int) -> list[dict]:
    """row 6의 정당·후보 라벨에서 cand_count개 추출. 't'·빈셀·'계'는 제외."""
    raw = [(c or "").strip() for c in row6 if c is not None]
    raw = [s for s in raw if s and s != "t"]
    if raw and raw[-1] == "계":
        raw = raw[:-1]
    # 후보는 응답 끝에 정렬 (앞부분 잡음 컬럼은 무시)
    labels = raw[-cand_count:] if len(raw) >= cand_count else raw
    cands = []
    for lbl in labels:
        parts = [p.strip() for p in lbl.replace("\r\n", "\n").split("\n") if p.strip()]
        if len(parts) == 2:
            cands.append({"party": parts[0], "name": parts[1]})
        elif len(parts) == 1:
            cands.append({"party": "", "name": parts[0]})
        else:
            cands.append({"party": "", "name": lbl})
    return cands


def process_file(round_: int, path: Path) -> list[dict]:
    year, sg_date = ELECTIONS[round_]
    rows = read_sheet_rows(path)
    if len(rows) < 8:
        return []

    # row 7(첫 데이터)에서 cand_count 추정
    row6 = rows[5] if len(rows) > 5 else []
    row7 = rows[6] if len(rows) > 6 else []
    # row 7 길이 = 선거구명 + 투표구명 + 선거인수 + 투표수 + N후보 + 계 + 무효 + 기권 = 7 + N
    # 후행 빈 셀 trim
    while row7 and (row7[-1] is None or str(row7[-1]).strip() == ""):
        row7 = row7[:-1]
    cand_count = max(0, len(row7) - 7)
    cands = extract_candidates_from_row6(row6, cand_count)

    sgg_name = ""
    cur_dong = "전체"
    out = []

    # 선거구명 헤더 판정: '갑/을/구' 끝 + '투표'/'소계'/'계' 아닌 것
    def looks_like_sgg(s: str) -> bool:
        if not s:
            return False
        if DONG_PAT.match(s):
            return False
        if s.endswith("투표") or s.endswith("투") or s in ("계", "소계"):
            return False
        return s.endswith(("갑", "을", "구"))

    for r_idx in range(6, len(rows)):
        r = rows[r_idx]
        if not r:
            continue
        first = (r[0] or "").strip() if r[0] else ""
        if not first:
            continue

        if looks_like_sgg(first):
            sgg_name = first
            box_name = (r[1] or "").strip() if len(r) > 1 else ""
            offset = 2
        else:
            box_name = first
            offset = 1

        if not box_name:
            continue

        kind = classify(box_name)
        if kind == "box":
            m = DONG_PAT.match(box_name)
            if m:
                cur_dong = m.group(1)
        elif kind in ("race_total", "special"):
            cur_dong = "전체"

        # 데이터 — offset 위치부터 선거인수, 투표수, N후보, 계, 무효, 기권
        def cell(i):
            idx = offset + i
            return r[idx] if idx < len(r) else None

        eligible = to_int(cell(0))
        voted = to_int(cell(1))
        cand_votes = [to_int(cell(2 + i)) for i in range(cand_count)]
        total_valid = to_int(cell(2 + cand_count))
        invalid = to_int(cell(3 + cand_count))
        abstain = to_int(cell(4 + cand_count))

        for slot, (c, votes) in enumerate(zip(cands, cand_votes), 1):
            share = round(votes / total_valid * 100, 2) if (votes is not None and total_valid) else None
            out.append({
                "회차": round_,
                "연도": year,
                "선거일": sg_date,
                "선거구명": sgg_name,
                "동": cur_dong,
                "투표구명": box_name,
                "분류": kind,
                "선거인수": eligible,
                "투표수": voted,
                "유효표_계": total_valid,
                "무효투표수": invalid,
                "기권자수": abstain,
                "후보순번": slot,
                "정당": c["party"],
                "후보명": c["name"],
                "득표수": votes,
                "득표율_유효표대비": share,
            })

    return out


def main():
    all_rows: list[dict] = []
    for r in sorted(ELECTIONS):
        path = TMP / f"nec_busan_buk_{r}.xlsx"
        if not path.exists():
            print(f"  · {r}대 — 파일 없음 (skip): tmp/nec_busan_buk_{r}.xlsx")
            continue
        rows = process_file(r, path)
        print(f"  · {r}대 — {len(rows)}행 (행수 추출)")
        all_rows.extend(rows)

    if not all_rows:
        sys.exit("어느 회차에서도 데이터 없음")

    fieldnames = list(all_rows[0].keys())
    OUT.parent.mkdir(parents=True, exist_ok=True)
    with OUT.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(all_rows)

    print(f"\n저장: {OUT.relative_to(ROOT)}  ({len(all_rows)}행)")


if __name__ == "__main__":
    main()
