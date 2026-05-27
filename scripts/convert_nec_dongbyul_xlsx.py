#!/usr/bin/env python3
"""
선관위 선거통계시스템에서 다운로드한 '개표현황(투표구별)' xlsx를
한 줄 한 줄 동 컨텍스트 포함 CSV로 변환.

xlsx 구조 (제22대 부산 북구 사례):
  row 1~4: 메타
  row 5: 헤더 ['선거구명','투표구명','선거인수','투표수','후보자별 득표수','무효투표수','기권자수']
  row 6: 후보·정당 분할 헤더 ['t','민주당\\n전재수','국민의힘\\n서병수','개혁신당\\n배기석','계']
  row 7: 선거구 합계 ['북구갑','계', 선거인수, 투표수, dugsu_1, dugsu_2, ..., 계, 무효, 기권]
  row 8~: 특수투표(거소·관외사전·국외부재자·소계·관내사전) + 동별 투표구

투표구명 패턴:
  - '<동명>제<N>투': 동 단위 투표구 → 동 컨텍스트 갱신
  - '소계', '관내사전투표': 직전 동의 소계/관내사전 (또는 전체)
  - '거소·선상투표','관외사전투표','국외부재자투표': 선거구 전체

사용:
    python scripts/convert_nec_dongbyul_xlsx.py tmp/<파일>.xlsx
    python scripts/convert_nec_dongbyul_xlsx.py tmp/<파일>.xlsx -o exports/output.csv
"""

from __future__ import annotations

import argparse
import csv
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

NS = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}
NS_T = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}t"


def read_sheet_rows(path: Path) -> list[list]:
    """xlsx 1번 시트를 [[셀, ...], ...]. shared strings 풀어 문자열로."""
    with zipfile.ZipFile(path) as z:
        shared: list[str] = []
        try:
            for si in ET.fromstring(z.read("xl/sharedStrings.xml")).findall("s:si", NS):
                shared.append("".join((t.text or "") for t in si.iter(NS_T)))
        except KeyError:
            pass
        sheet_xml = None
        for entry in z.namelist():
            if "worksheets/sheet" in entry.lower() and entry.endswith(".xml"):
                sheet_xml = entry
                break
        if not sheet_xml:
            return []
        sheet = ET.fromstring(z.read(sheet_xml))
        rows: list[list] = []
        sd = sheet.find("s:sheetData", NS)
        if sd is None:
            return rows
        for row in sd.findall("s:row", NS):
            cells: list = []
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


def extract_candidate_columns(row6: list, row7: list) -> tuple[list[dict], int]:
    """row 6에서 정당·후보 라벨, row 7의 길이로 컬럼 매핑. 후보 정보 + 데이터 시작 인덱스 반환."""
    # row 7 길이가 10이면: 선거구명, 투표구명, 선거인수, 투표수, [후보 N명], 계, 무효, 기권
    # 즉 후보 컬럼 = 길이 - 7 (선거구명·투표구명·선거인수·투표수·계·무효·기권)
    # row 6의 후보 라벨 (사용된 정렬 기준: 첫 셀 't' 또는 None → 그 다음부터 후보 라벨)
    cand_count = len(row7) - 7  # 북구 22대: 10 - 7 = 3
    # row 6에서 후보 라벨 추출 — 마지막 '계' 제외하고 가져옴
    cand_labels = []
    raw_labels = [(c or "").strip() for c in row6 if c is not None and str(c).strip()]
    # 첫 셀이 't' 또는 빈 셀일 수 있어서 그것 제외 후 처음 cand_count개
    filtered = [l for l in raw_labels if l != "t"]
    # 마지막이 '계'면 제외
    if filtered and filtered[-1] == "계":
        filtered = filtered[:-1]
    cand_labels = filtered[:cand_count]
    cands = []
    for lbl in cand_labels:
        # '민주당\n전재수' 또는 '\n전재수' 형식. 줄바꿈으로 정당·이름 분리
        parts = [p.strip() for p in lbl.replace("\r\n", "\n").split("\n") if p.strip()]
        if len(parts) == 2:
            cands.append({"party": parts[0], "name": parts[1]})
        elif len(parts) == 1:
            cands.append({"party": "", "name": parts[0]})
        else:
            cands.append({"party": "", "name": lbl})
    return cands, cand_count


DONG_PAT = re.compile(r"^(.+?동)제(\d+)투\s*$")


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
    if name in ("거소·선상투표", "관외사전투표", "국외부재자투표"):
        return "special"
    return "other"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("xlsx", type=Path)
    ap.add_argument("-o", "--out", type=Path, default=None)
    args = ap.parse_args()

    rows = read_sheet_rows(args.xlsx)
    if len(rows) < 8:
        sys.exit("행 수 부족")

    meta_title = (rows[2][0] or "") if rows[2] else ""
    # row 6 후보, row 7 첫 데이터 행
    row6 = rows[5] if len(rows) > 5 else []
    row7 = rows[6] if len(rows) > 6 else []
    cands, cand_count = extract_candidate_columns(row6, row7)

    sgg_name = ""
    cur_dong = "전체"
    out_rows: list[dict] = []

    for r_idx in range(6, len(rows)):  # row 7부터 (0-indexed 6)
        r = rows[r_idx]
        if not r:
            continue
        first = (r[0] or "").strip() if r and r[0] else ""
        if not first:
            continue

        # 행 7만 길이 10: 첫 셀 선거구명, 두 번째 투표구명. 그 외는 첫 셀이 투표구명
        if first not in ("계", "소계", "관내사전투표", "거소·선상투표", "관외사전투표", "국외부재자투표") \
                and not DONG_PAT.match(first):
            # 선거구명 헤더 행
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
        elif kind == "special" or kind == "race_total":
            cur_dong = "전체"
        # subtotal·early·other는 cur_dong 그대로 유지

        # 데이터 추출
        eligible = to_int(r[offset]) if len(r) > offset else None
        voted = to_int(r[offset + 1]) if len(r) > offset + 1 else None
        cand_votes = []
        for i in range(cand_count):
            idx = offset + 2 + i
            cand_votes.append(to_int(r[idx]) if len(r) > idx else None)
        total_valid = to_int(r[offset + 2 + cand_count]) if len(r) > offset + 2 + cand_count else None
        invalid = to_int(r[offset + 3 + cand_count]) if len(r) > offset + 3 + cand_count else None
        abstain = to_int(r[offset + 4 + cand_count]) if len(r) > offset + 4 + cand_count else None

        row_dict = {
            "선거구명": sgg_name,
            "동": cur_dong,
            "투표구명": box_name,
            "분류": kind,
            "선거인수": eligible,
            "투표수": voted,
        }
        for c, v in zip(cands, cand_votes):
            col = f"{c['party']}_{c['name']}".strip("_")
            row_dict[col] = v
        row_dict["유효표_계"] = total_valid
        row_dict["무효투표수"] = invalid
        row_dict["기권자수"] = abstain
        out_rows.append(row_dict)

    if not out_rows:
        sys.exit("추출된 행 없음")

    # 컬럼 순서
    fieldnames = list(out_rows[0].keys())
    out_path = args.out or args.xlsx.with_suffix(".csv")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    with out_path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(out_rows)

    print(f"메타: {meta_title}")
    cand_summary = ", ".join(f"{c['party']} {c['name']}".strip() for c in cands)
    print(f"후보 ({len(cands)}명): {cand_summary}")
    print(f"저장: {out_path}  ({len(out_rows)}행)")


if __name__ == "__main__":
    main()
