from __future__ import annotations

import csv
import json
import zipfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "exports" / "claude_driving_crime_package_20260519"
SNAPSHOT_FILE = ROOT / "data" / "candidates" / "20260603" / "snapshot_20260519.json"
CRIMINAL_OCR_FILE = ROOT / "data" / "criminal_ocr.json"
CONSTITUENCIES_FILE = ROOT / "data" / "constituencies.json"

SG_TITLE = {
    "2": "국회의원 재보궐",
    "3": "시도지사",
    "4": "기초단체장",
    "5": "시도의원",
    "6": "구시군의회의원",
    "8": "광역의원 비례",
    "9": "기초의원 비례",
    "11": "교육감",
}

UNCONTESTED_SG_TYPES = {"4", "5", "6", "8", "9"}
PROPORTIONAL_SG_TYPES = {"8", "9"}
FIVE_PARTIES = ["더불어민주당", "국민의힘", "조국혁신당", "진보당", "개혁신당"]
MAJOR_PARTIES = ["더불어민주당", "국민의힘"]


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def is_registered(candidate: dict | None) -> bool:
    return bool(candidate) and (candidate.get("status") or "등록") == "등록"


def district_key(row: dict) -> str:
    return "|".join([
        str(row.get("sgTypecode") or ""),
        row.get("sdName") or "",
        row.get("sggName") or "",
    ])


def build_uncontested_set(candidates: list[dict], constituencies: list[dict]) -> set[str]:
    seats = {
        district_key(row): int(row.get("sggJungsu") or 0)
        for row in constituencies
        if str(row.get("sgTypecode") or "") in UNCONTESTED_SG_TYPES
    }
    candidates_by_key: dict[str, list[dict]] = defaultdict(list)
    for candidate in candidates:
        if not is_registered(candidate):
            continue
        key = district_key(candidate)
        if key in seats:
            candidates_by_key[key].append(candidate)

    out: set[str] = set()
    for key, seat_count in seats.items():
        rows = candidates_by_key.get(key, [])
        count = len(rows)
        if not count:
            continue
        sg_type = key.split("|", 1)[0]
        parties = {row.get("jdName") or "무소속" for row in rows}
        single_party_pr = sg_type in PROPORTIONAL_SG_TYPES and count > seat_count and len(parties) == 1
        if count <= seat_count or single_party_pr:
            out.update(str(row.get("huboid") or "") for row in rows if row.get("huboid"))
    return out


def pct(n: int, d: int) -> float:
    return round(n / d * 100, 2) if d else 0.0


def csv_safe_rows(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fieldnames})


def offense_rows_for(record: dict, category: str) -> list[dict]:
    rows = [
        offense for offense in record.get("offenses", [])
        if category in (offense.get("categories") or [])
    ]
    if rows:
        return rows
    return [{
        "date": "",
        "offense": "",
        "sentence": "",
        "raw": record.get("offense_text") or record.get("ocr_text") or "",
    }]


def compact_raw(text: str, limit: int = 260) -> str:
    text = " ".join(str(text or "").split())
    return text[:limit] + ("..." if len(text) > limit else "")


def candidate_row(record: dict, candidate: dict | None, category: str, uncontested_set: set[str]) -> dict:
    offenses = offense_rows_for(record, category)
    huboid = str(record.get("huboid") or "")
    candidate = candidate or {}
    return {
        "huboid": huboid,
        "name": candidate.get("name") or record.get("name") or "",
        "party": candidate.get("jdName") or record.get("party") or "무소속",
        "sdName": candidate.get("sdName") or record.get("sdName") or "",
        "sggName": candidate.get("sggName") or record.get("sggName") or "",
        "wiwName": candidate.get("wiwName") or record.get("wiwName") or "",
        "office": SG_TITLE.get(str(candidate.get("sgTypecode") or ""), str(candidate.get("sgTypecode") or "")),
        "status": candidate.get("status") or "",
        "uncontested": "Y" if huboid in uncontested_set else "N",
        "criminal_record": record.get("criminal_record") or "",
        "categories": "; ".join(record.get("categories") or []),
        "matched_terms": "; ".join(
            f"{key}: {', '.join(value)}" for key, value in (record.get("matched_terms") or {}).items()
        ),
        "offense_dates": "; ".join(offense.get("date") or "" for offense in offenses if offense.get("date")),
        "offense_sentences": "; ".join(offense.get("sentence") or "" for offense in offenses if offense.get("sentence")),
        "offense_names_raw": "; ".join(offense.get("offense") or "" for offense in offenses if offense.get("offense")),
        "offense_raw_excerpt": " / ".join(compact_raw(offense.get("raw") or "") for offense in offenses),
        "nec_detail_url": record.get("nec_detail_url") or "",
    }


def summarize_by_group(rows: list[dict], denominators: Counter, key: str) -> list[dict]:
    drunk = Counter(row[key] or "미상" for row in rows if row["has_drunk_driving"])
    dangerous = Counter(row[key] or "미상" for row in rows if row["has_dangerous_driving"])
    both = Counter(row[key] or "미상" for row in rows if row["has_drunk_driving"] and row["has_dangerous_driving"])
    labels = sorted(set(denominators) | set(drunk) | set(dangerous), key=lambda x: (-denominators.get(x, 0), x))
    out = []
    for label in labels:
        total = denominators.get(label, 0)
        if total == 0 and not drunk.get(label) and not dangerous.get(label):
            continue
        out.append({
            key: label,
            "registered_candidates": total,
            "drunk_driving_candidates": drunk.get(label, 0),
            "drunk_driving_rate_pct": pct(drunk.get(label, 0), total),
            "dangerous_driving_candidates": dangerous.get(label, 0),
            "dangerous_driving_rate_pct": pct(dangerous.get(label, 0), total),
            "both_categories_candidates": both.get(label, 0),
        })
    return out


def md_table(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    head = "| " + " | ".join(rows[0]) + " |"
    sep = "| " + " | ".join("---" for _ in rows[0]) + " |"
    body = ["| " + " | ".join(str(cell) for cell in row) + " |" for row in rows[1:]]
    return "\n".join([head, sep, *body])


def main() -> None:
    snapshot = load_json(SNAPSHOT_FILE)
    candidates = snapshot["candidates"]
    candidate_map = {str(row.get("huboid") or ""): row for row in candidates}
    criminal = load_json(CRIMINAL_OCR_FILE)
    constituencies = load_json(CONSTITUENCIES_FILE)
    uncontested_set = build_uncontested_set(candidates, constituencies)

    registered = [row for row in candidates if is_registered(row)]
    party_den = Counter(row.get("jdName") or "무소속" for row in registered)
    region_den = Counter(row.get("sdName") or "미상" for row in registered)
    office_den = Counter(SG_TITLE.get(str(row.get("sgTypecode") or ""), str(row.get("sgTypecode") or "")) for row in registered)

    analysis_rows = []
    for record in criminal["records"]:
        candidate = candidate_map.get(str(record.get("huboid") or ""))
        if not is_registered(candidate):
            continue
        categories = set(record.get("categories") or [])
        if not ({"위험운전", "음주운전"} & categories):
            continue
        base = candidate_row(record, candidate, "위험운전" if "위험운전" in categories else "음주운전", uncontested_set)
        base.update({
            "has_dangerous_driving": "위험운전" in categories,
            "has_drunk_driving": "음주운전" in categories,
        })
        analysis_rows.append(base)

    dangerous_rows = [row for row in analysis_rows if row["has_dangerous_driving"]]
    drunk_rows = [row for row in analysis_rows if row["has_drunk_driving"]]
    both_rows = [row for row in analysis_rows if row["has_dangerous_driving"] and row["has_drunk_driving"]]

    party_summary = summarize_by_group(analysis_rows, party_den, "party")
    region_summary = summarize_by_group(analysis_rows, region_den, "sdName")
    office_summary = summarize_by_group(analysis_rows, office_den, "office")

    fields = [
        "huboid", "name", "party", "sdName", "sggName", "wiwName", "office", "status", "uncontested",
        "criminal_record", "categories", "matched_terms", "offense_dates", "offense_sentences",
        "offense_names_raw", "offense_raw_excerpt", "nec_detail_url",
    ]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_safe_rows(OUT_DIR / "dangerous_driving_candidates.csv", dangerous_rows, fields)
    csv_safe_rows(OUT_DIR / "drunk_driving_candidates.csv", drunk_rows, fields)
    csv_safe_rows(
        OUT_DIR / "party_summary.csv",
        party_summary,
        ["party", "registered_candidates", "drunk_driving_candidates", "drunk_driving_rate_pct",
         "dangerous_driving_candidates", "dangerous_driving_rate_pct", "both_categories_candidates"],
    )
    csv_safe_rows(
        OUT_DIR / "region_summary.csv",
        region_summary,
        ["sdName", "registered_candidates", "drunk_driving_candidates", "drunk_driving_rate_pct",
         "dangerous_driving_candidates", "dangerous_driving_rate_pct", "both_categories_candidates"],
    )
    csv_safe_rows(
        OUT_DIR / "office_summary.csv",
        office_summary,
        ["office", "registered_candidates", "drunk_driving_candidates", "drunk_driving_rate_pct",
         "dangerous_driving_candidates", "dangerous_driving_rate_pct", "both_categories_candidates"],
    )

    major_rows = [row for row in party_summary if row["party"] in MAJOR_PARTIES]
    five_rows = [row for row in party_summary if row["party"] in FIVE_PARTIES]
    dangerous_party = Counter(row["party"] for row in dangerous_rows)

    key_stats = {
        "snapshot": "2026-05-19 후보 등록 스냅샷",
        "registered_candidates": len(registered),
        "criminal_pdf_records": criminal["meta"]["processed"],
        "criminal_classification_version": criminal["meta"]["classification_version"],
        "dangerous_driving_candidates": len(dangerous_rows),
        "drunk_driving_candidates": len(drunk_rows),
        "both_dangerous_and_drunk_candidates": len(both_rows),
        "dangerous_by_party": dict(dangerous_party),
        "major_party_summary": major_rows,
        "five_party_summary": five_rows,
    }
    (OUT_DIR / "key_stats.json").write_text(json.dumps(key_stats, ensure_ascii=False, indent=2), encoding="utf-8")

    dangerous_table = [[
        "이름", "정당", "지역", "직책", "무투표", "일자", "형량", "죄명 원문 일부",
    ]]
    for row in sorted(dangerous_rows, key=lambda r: (r["party"] != "국민의힘", r["party"], r["sdName"], r["name"])):
        dangerous_table.append([
            row["name"],
            row["party"],
            f"{row['sdName']} {row['sggName']}".strip(),
            row["office"],
            row["uncontested"],
            row["offense_dates"] or "확인 필요",
            row["offense_sentences"] or "확인 필요",
            row["offense_raw_excerpt"] or row["offense_names_raw"],
        ])

    major_table = [["정당", "등록 후보", "음주운전", "음주운전 비율", "위험운전", "위험운전 비율", "둘 다"]]
    for row in major_rows:
        major_table.append([
            row["party"],
            f"{row['registered_candidates']:,}명",
            f"{row['drunk_driving_candidates']:,}명",
            f"{row['drunk_driving_rate_pct']:.2f}%",
            f"{row['dangerous_driving_candidates']:,}명",
            f"{row['dangerous_driving_rate_pct']:.2f}%",
            f"{row['both_categories_candidates']:,}명",
        ])

    five_table = [["정당", "등록 후보", "음주운전", "음주운전 비율", "위험운전", "위험운전 비율"]]
    for row in five_rows:
        five_table.append([
            row["party"],
            f"{row['registered_candidates']:,}명",
            f"{row['drunk_driving_candidates']:,}명",
            f"{row['drunk_driving_rate_pct']:.2f}%",
            f"{row['dangerous_driving_candidates']:,}명",
            f"{row['dangerous_driving_rate_pct']:.2f}%",
        ])

    office_table = [["직책", "등록 후보", "음주운전", "음주운전 비율", "위험운전", "위험운전 비율"]]
    for row in [r for r in office_summary if r["drunk_driving_candidates"] or r["dangerous_driving_candidates"]]:
        office_table.append([
            row["office"],
            f"{row['registered_candidates']:,}명",
            f"{row['drunk_driving_candidates']:,}명",
            f"{row['drunk_driving_rate_pct']:.2f}%",
            f"{row['dangerous_driving_candidates']:,}명",
            f"{row['dangerous_driving_rate_pct']:.2f}%",
        ])

    md = f"""# 클로드용 데이터 브리프: 음주운전과 위험운전 분리

생성 시각: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## 사용 목적

6·3 지방선거 후보 전과 분석에서 기존에 `음주·위험운전`으로 묶였던 범주를 `음주운전`과 `위험운전`으로 분리했다.  
특히 `위험운전`은 죄명에 `위험운전` 표현이 들어간 후보만 따로 추출했다. 기사·방송에서는 음주운전 일반과 구분해 다루는 것이 맞다.

## 핵심 숫자

- 분석 기준: 선관위 후보자 공개정보 2026년 5월 19일 스냅샷
- 등록 후보: {len(registered):,}명
- 전과 PDF 공개 후보: {criminal['meta']['processed']:,}명
- 분류 데이터 버전: {criminal['meta']['classification_version']}
- `위험운전` 분류 후보: {len(dangerous_rows):,}명
- `음주운전` 분류 후보: {len(drunk_rows):,}명
- `위험운전`과 `음주운전` 동시 분류 후보: {len(both_rows):,}명
- `위험운전` 후보 중 무투표 당선 선거구 후보: {sum(1 for row in dangerous_rows if row['uncontested'] == 'Y'):,}명

## 분류 기준

- `위험운전`: 죄명 영역에서 `위험운전` 표현 확인. 대표적으로 `위험운전치사상`이 여기에 들어간다.
- `음주운전`: 죄명 영역에서 `음주운전` 또는 `음주측정거부` 표현 확인.
- 같은 후보가 두 범주에 동시에 들어갈 수 있다. 예: `특정범죄가중처벌등에관한법률위반(위험운전치사상), 도로교통법위반(음주운전)`.
- 아래 수치는 선관위 공개정보 PDF의 죄명 영역을 분류한 것이다. 인용·보도 시 후보자 상세 페이지 원문 확인 필요.

## 양당 비교

{md_table(major_table)}

읽는 법:

- 위험운전은 절대 수가 작다. 비율만 과장해 말하기보다 `국민의힘 6명, 민주당 2명`처럼 후보 수를 같이 말해야 한다.
- 음주운전은 후보 수가 많아 양당 비교가 가능하다. 등록 후보 대비로는 국민의힘 {next(r for r in major_rows if r['party']=='국민의힘')['drunk_driving_rate_pct']:.2f}%, 더불어민주당 {next(r for r in major_rows if r['party']=='더불어민주당')['drunk_driving_rate_pct']:.2f}%다.

## 5개 정당 참고

{md_table(five_table)}

주의:

- 조국혁신당·진보당·개혁신당은 분모가 작아 양당과 같은 방식의 막대그래프로 나란히 놓으면 왜곡될 수 있다.
- 본방 그래픽에서는 양당을 메인으로, 나머지 정당은 참고 박스가 적절하다.

## 위험운전 후보 11명 명단

{md_table(dangerous_table)}

## 직책별 분포

{md_table(office_table)}

## 클로드에게 요청할 작업

1. `위험운전`을 `음주운전` 안에 다시 합치지 말 것.
2. 제목·리드에서는 `위험운전 11명`을 별도 사실로 세우되, 표본 수가 작다는 점을 반영해 과잉 일반화하지 말 것.
3. 양당 비교는 `국민의힘 6명 vs 민주당 2명`, `등록 후보 대비 0.22% vs 0.06%`처럼 절대수와 비율을 같이 쓸 것.
4. 음주운전은 별도 축으로 `국민의힘 376명(13.71%) vs 민주당 353명(10.99%)`을 쓸 수 있다.
5. 위험운전 후보별 죄명·일자·형량은 반드시 선관위 후보자 상세 페이지 원문 확인을 전제로 표현할 것.

## 동봉 파일

- `dangerous_driving_candidates.csv`: 위험운전 후보 11명 전수
- `drunk_driving_candidates.csv`: 음주운전 후보 964명 전수
- `party_summary.csv`: 정당별 등록 후보·음주운전·위험운전 집계
- `region_summary.csv`: 시도별 집계
- `office_summary.csv`: 직책별 집계
- `key_stats.json`: 핵심 숫자
"""
    (OUT_DIR / "CLAUDE_DRIVING_CRIME_BRIEF_20260519.md").write_text(md, encoding="utf-8")

    zip_path = OUT_DIR.with_suffix(".zip")
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(OUT_DIR.iterdir()):
            zf.write(path, path.name)

    print(f"wrote {OUT_DIR}")
    print(f"wrote {zip_path}")
    print(f"dangerous={len(dangerous_rows)} drunk={len(drunk_rows)} both={len(both_rows)}")


if __name__ == "__main__":
    main()
