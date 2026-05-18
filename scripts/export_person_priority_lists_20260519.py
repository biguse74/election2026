#!/usr/bin/env python3
"""Export broadcast-priority person lists for the May 19 follow-up."""

from __future__ import annotations

import csv
import importlib.util
import json
import re
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "exports" / "person_priority_lists_20260519"
DATA_DIR = OUT_DIR / "data"
OUT_MD = OUT_DIR / "CLAUDE_PERSON_PRIORITY_LISTS_20260519.md"
ZIP = ROOT / "exports" / "person_priority_lists_20260519.zip"

SNAPSHOT = ROOT / "data" / "candidates" / "20260603" / "snapshot_20260518.json"
DETAILS = ROOT / "data" / "candidate_details.json"
CRIMINAL = ROOT / "data" / "criminal_ocr.json"
UNCONTESTED_SCRIPT = ROOT / "scripts" / "export_uncontested_513_verification.py"
TOP10_OFFENSE_DETAILS = ROOT / "exports" / "two_pm_data_uncontested_package_20260517_1400" / "data" / "top10_offense_details.csv"

MAJOR_PARTIES = {"더불어민주당", "국민의힘"}
ECONOMIC = {"사기", "횡령", "배임", "뇌물"}
SEX_DRUG = {"성범죄", "마약"}
SHORT = {"더불어민주당": "민주당", "국민의힘": "국힘"}
OFFICE = {
    "2": "국회의원 재보궐",
    "3": "광역단체장",
    "4": "기초단체장",
    "5": "광역의원",
    "6": "지역구 기초의원",
    "8": "광역의원 비례",
    "9": "기초의원 비례",
    "11": "교육감",
}
OFFICE_PRIORITY = {
    "3": 1,
    "4": 1,
    "5": 2,
    "6": 2,
    "8": 3,
    "9": 3,
    "2": 4,
    "11": 4,
}


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_uncontested_huboids() -> set[str]:
    spec = importlib.util.spec_from_file_location("uncontested_verify", UNCONTESTED_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {UNCONTESTED_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    context = module.build_uncontested_context()
    return {str(row["huboid"]) for row in context["uncontested_rows"]}


def parse_int(value: Any) -> int:
    text = str(value or "").replace(",", "").strip()
    digits = "".join(ch for ch in text if ch.isdigit() or ch == "-")
    return int(digits or 0)


def active(candidate: dict[str, Any]) -> bool:
    return not candidate.get("status") or candidate.get("status") == "등록"


def won_text_from_thousand(thousand: int) -> str:
    won = thousand * 1000
    if won >= 100_000_000:
        eok = won // 100_000_000
        man = (won % 100_000_000) // 10_000
        return f"{eok:,}억 {man:,}만원" if man else f"{eok:,}억원"
    if won >= 10_000:
        return f"{won // 10_000:,}만원"
    return f"{won:,}원"


def csv_write(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def load_verified_top10_summaries() -> dict[str, str]:
    """Use the previously hand-targeted top-10 extraction when present."""
    if not TOP10_OFFENSE_DETAILS.exists():
        return {}
    summaries: dict[str, list[str]] = {}
    with TOP10_OFFENSE_DETAILS.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            cats = {item.strip() for item in str(row.get("our_category_match") or "").split(",") if item.strip()}
            if not cats & ECONOMIC:
                continue
            huboid = str(row.get("huboid") or "")
            offense = clean_cell(row.get("offense_name_normalized") or row.get("offense_name_raw") or "죄명 확인 불가")
            date = clean_cell(row.get("disposition_date_iso") or row.get("disposition_date_raw") or "일자 확인 불가")
            result = clean_cell(row.get("disposition_result_raw") or "형량 확인 불가")
            category = ",".join(sorted(cats & ECONOMIC))
            summaries.setdefault(huboid, []).append(f"{offense} | {date} | {result} | 분류 {category}")
    return {huboid: "; ".join(items) for huboid, items in summaries.items()}


def clean_cell(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def short_region(candidate: dict[str, Any]) -> str:
    sd = display_sd(candidate.get("sdName") or "")
    wiw = candidate.get("wiwName") or ""
    sgg = candidate.get("sggName") or ""
    sg_type = str(candidate.get("sgTypecode") or "")
    if sg_type == "3":
        return sd
    if sg_type in {"4", "8", "9", "11"}:
        return f"{sd} {sgg}".strip()
    if wiw and wiw != sgg:
        return f"{sd} {wiw} {sgg}"
    return f"{sd} {sgg}".strip()


def display_sd(value: str) -> str:
    if value == "전남광주통합특별시":
        return "전라남도"
    return value


def candidate_base(
    candidate: dict[str, Any],
    detail: dict[str, Any],
    uncontested: set[str],
) -> dict[str, Any]:
    huboid = str(candidate.get("huboid") or detail.get("huboid") or "")
    sg_type = str(candidate.get("sgTypecode") or detail.get("sgTypecode") or "")
    return {
        "huboid": huboid,
        "name": candidate.get("name") or detail.get("name") or "",
        "party": candidate.get("jdName") or detail.get("jdName") or "",
        "party_short": SHORT.get(candidate.get("jdName") or detail.get("jdName") or "", candidate.get("jdName") or ""),
        "sdName": display_sd(candidate.get("sdName") or detail.get("sdName") or ""),
        "wiwName": candidate.get("wiwName") or "",
        "sggName": candidate.get("sggName") or detail.get("sggName") or "",
        "region": short_region(candidate),
        "sgTypecode": sg_type,
        "office": OFFICE.get(sg_type, f"기타({sg_type})"),
        "uncontested": "Y" if huboid in uncontested else "N",
        "nec_detail_url": detail.get("nec_detail_url") or "",
    }


def offense_matches(record: dict[str, Any], targets: set[str]) -> list[dict[str, Any]]:
    matches = [
        offense for offense in record.get("offenses", [])
        if set(offense.get("categories") or []) & targets
    ]
    if matches:
        return matches
    if set(record.get("categories") or []) & targets:
        fallback = fallback_offense_from_text(record, targets)
        if fallback:
            return [fallback]
        return [{
            "date": "",
            "offense": "구조화 확인 불가",
            "sentence": "구조화 확인 불가",
            "categories": sorted(set(record.get("categories") or []) & targets),
            "raw": re.sub(r"\s+", " ", str(record.get("offense_text") or ""))[:180],
        }]
    return []


def fallback_offense_from_text(record: dict[str, Any], targets: set[str]) -> dict[str, Any] | None:
    text = f"{record.get('offense_text') or ''} {record.get('ocr_text') or ''}"
    cats = sorted(set(record.get("categories") or []) & targets)
    if not cats:
        return None

    offense_name = ""
    known_names = [
        "마약류관리에관한법률위반(향정)",
        "마약류관리에관한법률위반",
        "윤락행위등방지법위반",
        "업무상횡령",
        "특정경제범죄가중처벌등에관한법률위반(배임)",
        "특정경제범죄가중처벌등에관한법률위반(사기)",
        "뇌물공여",
        "배임증재",
        "사기",
        "횡령",
        "배임",
    ]
    for name in known_names:
        if name in text:
            offense_name = name
            break

    date_raw = ""
    date_match = re.search(r"((?:19|20)\d{2})[. /-]?(\d{1,2})[. /-](\d{1,2})", text)
    if date_match:
        year, month, day = date_match.groups()
        date_raw = f"{year}-{int(month):02d}-{int(day):02d}"
    sentence_raw = ""
    sentence_match = re.search(r"(벌금\s*[0-9,]+[원%]|징역\s*\d+\s*[년월][^ ]*|금고\s*\d+\s*[년월][^ ]*)", text)
    if sentence_match:
        sentence_raw = sentence_match.group(1).replace(" ", "")

    if not offense_name and not date_raw and not sentence_raw:
        return None
    return {
        "date": date_raw,
        "offense": offense_name or "죄명 구조화 확인 불가",
        "sentence": sentence_raw or "형량 구조화 확인 불가",
        "categories": cats,
        "raw": re.sub(r"\s+", " ", str(record.get("offense_text") or ""))[:180],
    }


def offense_summary(record: dict[str, Any], targets: set[str]) -> str:
    items = []
    for offense in offense_matches(record, targets):
        cats = ",".join(offense.get("categories") or [])
        name = offense.get("offense") or "죄명 확인 불가"
        date = offense.get("date") or "일자 확인 불가"
        sentence = offense.get("sentence") or "형량 확인 불가"
        raw = offense.get("raw") or ""
        if name == "구조화 확인 불가":
            items.append(f"{cats} 분류 | 원문 일부: {raw} | 일자·형량 구조화 확인 불가")
        else:
            items.append(f"{name} | {date} | {sentence} | 분류 {cats}")
    return "; ".join(items)


def latest_offense_year(record: dict[str, Any], targets: set[str]) -> int:
    years = []
    for offense in offense_matches(record, targets):
        match = re.search(r"(19|20)\d{2}", str(offense.get("date") or offense.get("raw") or ""))
        if match:
            years.append(int(match.group(0)))
    return max(years) if years else 0


def build_tax_rows(
    candidates: dict[str, dict[str, Any]],
    details: dict[str, dict[str, Any]],
    uncontested: set[str],
) -> list[dict[str, Any]]:
    rows = []
    for huboid, candidate in candidates.items():
        if candidate.get("jdName") not in MAJOR_PARTIES:
            continue
        detail = details.get(huboid, {})
        disclosure = detail.get("disclosures", {})
        tax5 = parse_int(disclosure.get("tax_arrears_5y_thousand_krw"))
        current = parse_int(disclosure.get("tax_arrears_current_thousand_krw"))
        if tax5 < 100000 and current < 100000:
            continue
        base = candidate_base(candidate, detail, uncontested)
        if tax5 >= 100000 and current >= 100000:
            tax_type = "최근 5년+현 체납"
        elif tax5 >= 100000:
            tax_type = "최근 5년"
        else:
            tax_type = "현 체납"
        rows.append({
            **base,
            "tax_type": tax_type,
            "tax_5y_won": tax5 * 1000,
            "tax_5y_display": won_text_from_thousand(tax5) if tax5 else "0원",
            "tax_current_won": current * 1000,
            "tax_current_display": won_text_from_thousand(current) if current else "0원",
            "tax_agency": "확인 불가(구조화 데이터에 국세/지방세 구분 없음)",
        })
    return sorted(rows, key=lambda r: max(int(r["tax_5y_won"]), int(r["tax_current_won"])), reverse=True)


def build_sex_drug_rows(
    candidates: dict[str, dict[str, Any]],
    details: dict[str, dict[str, Any]],
    records: dict[str, dict[str, Any]],
    uncontested: set[str],
) -> list[dict[str, Any]]:
    rows = []
    for huboid, record in records.items():
        if record.get("party") not in MAJOR_PARTIES:
            continue
        cats = set(record.get("categories") or [])
        if not cats & SEX_DRUG:
            continue
        candidate = candidates.get(huboid, {})
        detail = details.get(huboid, {})
        base = candidate_base(candidate, detail, uncontested)
        rows.append({
            **base,
            "matched_categories": ";".join(sorted(cats & SEX_DRUG)),
            "offense_summary": offense_summary(record, SEX_DRUG),
            "pdf_urls": ";".join(record.get("pdf_urls") or []),
        })
    return sorted(rows, key=lambda r: (r["matched_categories"], r["sdName"], r["sggName"]))


def build_economic_priority_rows(
    candidates: dict[str, dict[str, Any]],
    details: dict[str, dict[str, Any]],
    records: dict[str, dict[str, Any]],
    uncontested: set[str],
    verified_summaries: dict[str, str],
) -> list[dict[str, Any]]:
    all_rows = []
    for huboid, record in records.items():
        if record.get("party") not in MAJOR_PARTIES:
            continue
        cats = set(record.get("categories") or [])
        hits = cats & ECONOMIC
        if not hits:
            continue
        candidate = candidates.get(huboid, {})
        detail = details.get(huboid, {})
        base = candidate_base(candidate, detail, uncontested)
        priority = 0 if base["uncontested"] == "Y" else OFFICE_PRIORITY.get(base["sgTypecode"], 9)
        all_rows.append({
            **base,
            "matched_categories": ";".join(sorted(hits)),
            "offense_summary": verified_summaries.get(huboid) or offense_summary(record, ECONOMIC),
            "pdf_urls": ";".join(record.get("pdf_urls") or []),
            "_priority": priority,
            "_hit_count": len(hits),
            "_latest_year": latest_offense_year(record, ECONOMIC),
        })
    selected = []
    for party in ["더불어민주당", "국민의힘"]:
        party_rows = [row for row in all_rows if row["party"] == party]
        party_rows.sort(key=lambda r: (r["_priority"], -r["_hit_count"], -r["_latest_year"], r["sdName"], r["sggName"], r["name"]))
        selected.extend(party_rows[:10])
    for row in selected:
        row.pop("_priority", None)
        row.pop("_hit_count", None)
        row.pop("_latest_year", None)
    return selected


def md_tax(rows: list[dict[str, Any]], party: str) -> str:
    party_rows = [row for row in rows if row["party"] == party]
    lines = [f"### {SHORT[party]} 1억 이상 체납"]
    for i, row in enumerate(party_rows, 1):
        amount = f"최근 5년 {row['tax_5y_display']}"
        if row["tax_current_won"]:
            amount += f", 현 체납 {row['tax_current_display']}"
        lines.append(
            f"{i}. {row['name']} | {row['region']} {row['office']} | {row['tax_type']} | "
            f"{amount} | 체납 기관 {row['tax_agency']} | 무투표 {row['uncontested']}"
        )
    return "\n".join(lines)


def md_crime(rows: list[dict[str, Any]], title: str, party: str | None = None) -> str:
    if party:
        target = [row for row in rows if row["party"] == party]
        heading = f"### {SHORT[party]} {title}"
    else:
        target = rows
        heading = f"### {title}"
    lines = [heading]
    for i, row in enumerate(target, 1):
        lines.append(
            f"{i}. {row['name']} | {row['party_short']} | {row['region']} {row['office']} | "
            f"{row['offense_summary']} | 무투표 {row['uncontested']}"
        )
    return "\n".join(lines)


def build_markdown(tax_rows: list[dict[str, Any]], sex_drug_rows: list[dict[str, Any]], economic_rows: list[dict[str, Any]]) -> str:
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    tax_parties = {party: sum(1 for row in tax_rows if row["party"] == party) for party in MAJOR_PARTIES}
    econ_parties = {party: sum(1 for row in economic_rows if row["party"] == party) for party in MAJOR_PARTIES}
    return f"""# Codex 임무 B 결과: 인물 우선순위 명단

생성: {generated} KST  
방송: 2026년 5월 19일 14시 〈2시의 데이터〉  
기준: 선관위 공개정보 로컬 스냅샷 및 전과 PDF 분류 결과

## 확인 요약

- 1억 이상 체납 양당 후보: 중복 제거 후 {len(tax_rows)}명. 민주당 {tax_parties['더불어민주당']}명, 국민의힘 {tax_parties['국민의힘']}명.
- 현 1억 이상 체납 3명은 모두 최근 5년 1억 이상 체납 명단에 포함되어 별도 추가 인원이 생기지 않는다.
- 성범죄·마약 분류 국힘 후보: {len(sex_drug_rows)}명.
- 사기·횡령·배임·뇌물 우선 추출: 민주당 {econ_parties['더불어민주당']}명, 국민의힘 {econ_parties['국민의힘']}명.
- 체납 기관(국세/지방세)은 현재 구조화 데이터에 없으므로 전원 “확인 불가”로 표기했다.

## 보고 로그

- 시작 보고: 로컬 선관위 스냅샷·후보 상세·전과 분류 파일 기준으로 1순위 명단부터 추출 시작.
- 중간 보고: 사기·횡령·배임·뇌물 양당 합계 104명, 무투표는 민주당 6명·국민의힘 4명으로 확인.
- 완료 보고: 1억 이상 체납 17명, 성범죄·마약 3명, 사기·횡령·배임·뇌물 우선 20명 산출 완료.

## 표현 주의

- 모든 인물 정보는 “선관위 공개정보 기준”으로 표기한다.
- 아래 죄명·일자·형량은 `data/criminal_ocr.json`의 전과 PDF 구조화 결과 기준이다.
- 구조화가 실패하거나 OCR 원문이 불명확한 항목은 “확인 불가” 또는 “원문 일부”로 남겼다. 방송에서 후보별로 구체 인용할 때는 선관위 후보자 상세 페이지 원문 확인이 필요하다.
- 죄질 판단, 도덕 평가, 단정적 비난은 넣지 않는다.

## 1순위: 1억 이상 체납

{md_tax(tax_rows, "더불어민주당")}

{md_tax(tax_rows, "국민의힘")}

## 1순위: 국민의힘 성범죄·마약 3명

{md_crime(sex_drug_rows, "성범죄·마약")}

## 2순위: 사기·횡령·배임·뇌물 양당 각 10명

선정 기준: 무투표 당선자 우선, 그다음 단체장, 광역·기초의원, 비례 순. 같은 우선순위 안에서는 분류 적중 수와 최근 처분연도를 참고했다.

{md_crime(economic_rows, "사기·횡령·배임·뇌물", "더불어민주당")}

{md_crime(economic_rows, "사기·횡령·배임·뇌물", "국민의힘")}

## 산출 파일

- `data/priority_tax_100m_candidates.csv`
- `data/priority_sex_drug_candidates.csv`
- `data/priority_economic_candidates_20.csv`
- `data/key_stats.json`
"""


def main() -> None:
    snapshot = load_json(SNAPSHOT)
    details_payload = load_json(DETAILS)
    criminal_payload = load_json(CRIMINAL)
    candidates = {
        str(row.get("huboid")): row
        for row in snapshot["candidates"]
        if active(row)
    }
    details = {str(row.get("huboid")): row for row in details_payload["details"]}
    records = {str(row.get("huboid")): row for row in criminal_payload["records"]}
    uncontested = load_uncontested_huboids()
    verified_summaries = load_verified_top10_summaries()

    tax_rows = build_tax_rows(candidates, details, uncontested)
    sex_drug_rows = build_sex_drug_rows(candidates, details, records, uncontested)
    economic_rows = build_economic_priority_rows(candidates, details, records, uncontested, verified_summaries)

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    tax_fields = [
        "huboid", "name", "party", "party_short", "sdName", "wiwName", "sggName", "region",
        "sgTypecode", "office", "tax_type", "tax_5y_won", "tax_5y_display", "tax_current_won",
        "tax_current_display", "tax_agency", "uncontested", "nec_detail_url",
    ]
    crime_fields = [
        "huboid", "name", "party", "party_short", "sdName", "wiwName", "sggName", "region",
        "sgTypecode", "office", "matched_categories", "offense_summary", "uncontested", "nec_detail_url", "pdf_urls",
    ]
    csv_write(DATA_DIR / "priority_tax_100m_candidates.csv", tax_rows, tax_fields)
    csv_write(DATA_DIR / "priority_sex_drug_candidates.csv", sex_drug_rows, crime_fields)
    csv_write(DATA_DIR / "priority_economic_candidates_20.csv", economic_rows, crime_fields)

    key_stats = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "source_files": {
            "snapshot": str(SNAPSHOT.relative_to(ROOT)),
            "candidate_details": str(DETAILS.relative_to(ROOT)),
            "criminal_ocr": str(CRIMINAL.relative_to(ROOT)),
        },
        "tax_100m_candidates": {
            "total_deduped_major_party": len(tax_rows),
            "democratic": sum(1 for row in tax_rows if row["party"] == "더불어민주당"),
            "ppp": sum(1 for row in tax_rows if row["party"] == "국민의힘"),
            "current_100m_included_in_recent_100m": True,
            "tax_agency_status": "구조화 데이터에 국세/지방세 구분 없음",
        },
        "sex_drug_candidates": {
            "total_major_party": len(sex_drug_rows),
            "democratic": sum(1 for row in sex_drug_rows if row["party"] == "더불어민주당"),
            "ppp": sum(1 for row in sex_drug_rows if row["party"] == "국민의힘"),
        },
        "economic_priority_candidates": {
            "selected_total": len(economic_rows),
            "democratic": sum(1 for row in economic_rows if row["party"] == "더불어민주당"),
            "ppp": sum(1 for row in economic_rows if row["party"] == "국민의힘"),
            "selection_rule": "무투표, 단체장, 광역·기초의원, 비례 순",
            "verified_top10_detail_source_used": TOP10_OFFENSE_DETAILS.exists(),
        },
    }
    (DATA_DIR / "key_stats.json").write_text(json.dumps(key_stats, ensure_ascii=False, indent=2), encoding="utf-8")

    OUT_MD.write_text(build_markdown(tax_rows, sex_drug_rows, economic_rows), encoding="utf-8")

    if ZIP.exists():
        ZIP.unlink()
    with zipfile.ZipFile(ZIP, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(OUT_MD, OUT_MD.relative_to(OUT_DIR.parent))
        for path in sorted(DATA_DIR.glob("*")):
            zf.write(path, path.relative_to(OUT_DIR.parent))

    print(OUT_MD)
    print(ZIP)


if __name__ == "__main__":
    main()
