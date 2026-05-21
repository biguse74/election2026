#!/usr/bin/env python3
"""
중앙선거관리위원회 선거통계시스템에서 수동으로 다운로드한 회차별 시간대별
투표율 xlsx를 모아서 라이브 화면용 JSON을 만든다.

입력 (수동 배치):
    tmp/투표현황[제8회][지방선거].xlsx
    tmp/투표현황[제7회][지방선거].xlsx
    (기타 회차 xlsx — INPUT_FILES에 추가)

출력:
    data/history_turnout_hourly.json

xlsx 포맷(공통):
  row 1~4: 메타(생성자, 제목, 회차, 일시)
  row 5  : ['시도명','구분','선거인수','시간대별 투표현황',None,...,'총투표자수']
  row 6  : [None,None,None,'7시','8시',...,'18시',(8회는 '19시 30분'),None]
  row 7+ : 시도별 3행 묶음
           - 7번째(첫 행): [시도명, '계',   선거인수,    7시누계, 8시누계, ..., 마지막]
           - 8번째      : ['사전+거소', 사전수, '-', '-', ..., 13시부터 누적]
           - 9번째      : ['투표율(%)', '-', 7시%, 8시%, ..., 마지막%]
  → 우리가 쓰는 건 매 3행 중 **세 번째 (투표율%)**.

8회만 18시 이후 '19시 30분' 칸이 추가됨(사전투표·잔여투표 합산 완료 시점).
실제로는 같은 값이 반복되는 경우가 많아 18시값과 동일.

xlsx가 일부 drawing 참조가 깨져 있어 openpyxl이 끝까지 못 읽는다.
zipfile + ElementTree로 직접 sheetData를 파싱한다.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
import zipfile
from datetime import datetime, timezone, timedelta
from pathlib import Path

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
TMP_DIR = ROOT / "tmp"
OUT_PATH = ROOT / "data" / "history_turnout_hourly.json"

NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
NS = {"s": NS_MAIN}

# 수동 다운로드 파일 → 메타. 파일이 없으면 자동 스킵.
INPUT_FILES: list[dict] = [
    {
        "filename": "투표현황[제8회][지방선거].xlsx",
        "round": 8,
        "year": 2022,
        "election_type": "지방선거",
        "sgId": "20220601",
    },
    {
        "filename": "투표현황[제7회][지방선거].xlsx",
        "round": 7,
        "year": 2018,
        "election_type": "지방선거",
        "sgId": "20180613",
    },
]


# 17개 시도 신표준명 — 옛 이름이 들어와도 모두 신이름으로 정규화한다.
# 차트 매칭 시 SIDO_HISTORY_ALIAS(live.js)와 분리해 두 가지 룩업 둘 다 안전.
SIDO_OLD_TO_NEW = {
    "강원도": "강원특별자치도",
    "전라북도": "전북특별자치도",
}
KNOWN_SIDOS = {
    "서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시",
    "대전광역시", "울산광역시", "세종특별자치시", "경기도",
    "강원특별자치도", "충청북도", "충청남도", "전북특별자치도",
    "전라남도", "경상북도", "경상남도", "제주특별자치도",
}


def read_sheet_rows(path: Path) -> list[list]:
    """xlsx 1번 시트를 [[셀,...], ...] 형태로. shared strings 풀어 문자열로 변환."""
    with zipfile.ZipFile(path) as z:
        shared: list[str] = []
        try:
            ss_root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in ss_root.findall("s:si", NS):
                texts = [
                    (t.text or "")
                    for t in si.iter("{%s}t" % NS_MAIN)
                ]
                shared.append("".join(texts))
        except KeyError:
            pass

        sheet = ET.fromstring(z.read("xl/worksheets/Sheet1.xml"))
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


def parse_pct(v) -> float | None:
    if v is None:
        return None
    s = str(v).strip()
    if not s or s == "-":
        return None
    s = s.replace("%", "").replace(",", "").strip()
    try:
        return round(float(s), 2)
    except ValueError:
        return None


def parse_hour_header(label) -> str | None:
    """'7시' → '07:00', '19시 30분' → '19:30'. 다른 값은 None."""
    if not label:
        return None
    s = str(label).strip()
    m = re.match(r"(\d{1,2})\s*시(?:\s*(\d{1,2})\s*분)?$", s)
    if not m:
        return None
    hh = int(m.group(1))
    mm = int(m.group(2)) if m.group(2) else 0
    return f"{hh:02d}:{mm:02d}"


def normalize_sido(name: str) -> str:
    name = (name or "").strip()
    return SIDO_OLD_TO_NEW.get(name, name)


def extract_round(meta: dict, rows: list[list]) -> dict:
    """한 회차 xlsx에서 national + by_sido 시간대별 투표율 추출."""
    # 시간대 헤더는 row 6(인덱스 5). 첫 3칸은 시도/구분/선거인수, 그 다음이 시각.
    if len(rows) < 6:
        raise ValueError(f"{meta['filename']}: 헤더 행 부족")
    header = rows[5]
    times: list[tuple[int, str]] = []
    for col_idx, label in enumerate(header):
        hhmm = parse_hour_header(label)
        if hhmm:
            times.append((col_idx, hhmm))
    if not times:
        raise ValueError(f"{meta['filename']}: 시간대 헤더를 찾지 못했다")

    # row 7 이후 매 3행 묶음. 첫 행 셀[0]에 시도명(또는 '합계').
    national: list[dict] = []
    by_sido: dict[str, list[dict]] = {}

    i = 6  # 0-based: row 7
    while i + 2 < len(rows):
        first = rows[i]
        third = rows[i + 2]  # 투표율(%) 행
        sido_raw = (first[0] if first else "") or ""
        sido_raw = str(sido_raw).strip()
        if not sido_raw:
            i += 1
            continue

        # 투표율 행은 시도명 자리에 '투표율(%)'이 들어가서 컬럼이 한 칸 당겨진다.
        # 헤더 '7시'가 col=3에 있으면, 투표율 행에서 7시 값은 col=2에 있다.
        series: list[dict] = []
        for col_idx, hhmm in times:
            src_idx = col_idx - 1
            pct = parse_pct(third[src_idx] if 0 <= src_idx < len(third) else None)
            if pct is None:
                continue
            # 동일 시각 중복은 마지막값 채택
            if series and series[-1]["time"] == hhmm:
                series[-1] = {"time": hhmm, "turnout_pct": pct}
            else:
                series.append({"time": hhmm, "turnout_pct": pct})

        if sido_raw == "합계":
            national = series
        else:
            sido_norm = normalize_sido(sido_raw)
            if sido_norm in KNOWN_SIDOS:
                by_sido[sido_norm] = series
            # 알 수 없는 라벨은 조용히 무시 (소계행 등)
        i += 3

    return {
        "round": meta["round"],
        "year": meta["year"],
        "election_type": meta["election_type"],
        "sgId": meta["sgId"],
        "source_file": meta["filename"],
        "national": national,
        "by_sido": by_sido,
    }


def main() -> None:
    rounds_out: list[dict] = []
    skipped: list[str] = []

    for meta in INPUT_FILES:
        path = TMP_DIR / meta["filename"]
        if not path.exists():
            skipped.append(meta["filename"])
            continue
        rows = read_sheet_rows(path)
        rounds_out.append(extract_round(meta, rows))

    if not rounds_out:
        raise SystemExit(
            f"입력 파일을 하나도 찾지 못했습니다. tmp/ 폴더에 다음 중 하나 이상이 필요합니다:\n"
            + "\n".join(f"  - {m['filename']}" for m in INPUT_FILES)
        )

    payload = {
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "source": "중앙선거관리위원회 선거통계시스템 (수동 다운로드 xlsx)",
        "note": (
            "회차별 시간대별 누계 투표율(%). 시도명은 신표준명으로 정규화 "
            "(강원특별자치도·전북특별자치도). 13시 점프는 사전투표 합산 시점."
        ),
        "rounds": rounds_out,
    }
    OUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUT_PATH.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(f"저장: {OUT_PATH.relative_to(ROOT)}")
    for r in rounds_out:
        print(
            f"  · {r['round']}회 ({r['year']}) {r['election_type']} — "
            f"전국 {len(r['national'])}포인트 · 시도 {len(r['by_sido'])}개"
        )
    if skipped:
        print("스킵된 파일:")
        for s in skipped:
            print(f"  - tmp/{s}")


if __name__ == "__main__":
    main()
