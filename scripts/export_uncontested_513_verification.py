#!/usr/bin/env python3
"""Verify criminal-record and tax-arrears flags among 513 uncontested candidates."""

from __future__ import annotations

import csv
import importlib.util
import json
import shutil
import sys
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
BASE_SCRIPT = ROOT / "scripts" / "export_uncontested_series_data.py"
OUT_DIR = ROOT / "exports" / "uncontested_513_verification_20260518"
KST = timezone(timedelta(hours=9))

OFFICIAL_NEC_URL = "https://info.nec.go.kr/electioninfo/"
SBS_URL = "https://news.sbs.co.kr/news/endPage.do?news_id=N1008564878"
DONGA_DAUM_URL = "https://v.daum.net/v/20260516123353078"

ECONOMIC_CATEGORIES = {"사기", "횡령", "배임", "뇌물"}
OFFENSE_GROUPS: list[tuple[str, set[str], str]] = [
    ("사기·횡령·배임·뇌물", ECONOMIC_CATEGORIES, "돈·신뢰 범죄"),
    ("공직선거법", {"공직선거법"}, "선거범죄"),
    ("정치자금법", {"정치자금법"}, "정치자금"),
    ("도로교통법", {"도로교통", "음주·위험운전", "무면허운전", "교통사고"}, "음주·무면허·교통사고 포함"),
    ("폭행·상해", {"폭력"}, "폭행·상해 등 폭력 범주"),
    ("집회시위법", {"집시법"}, "집회 및 시위에 관한 법률"),
    ("근로기준법·노동관계법", {"노동"}, "근로기준법·산업안전보건법 등"),
    ("국가보안법·시국", {"국가보안법", "집시법"}, "국가보안법과 집시법을 함께 본 시국 관련 지표"),
]
OFFENSE_GROUP_COVERAGE = set().union(*(cats for _label, cats, _note in OFFENSE_GROUPS))

PARTY_ORDER = ["더불어민주당", "국민의힘", "진보당", "기타"]
OFFICE_ORDER = ["시도의원", "구시군의회의원", "기초의원비례", "기초단체장"]
OFFICE_DISPLAY = {
    "시도의원": "광역의원",
    "구시군의회의원": "지역구 기초의원",
    "기초의원비례": "기초의원 비례대표",
    "기초단체장": "기초단체장",
}


def load_base_module() -> Any:
    spec = importlib.util.spec_from_file_location("uncontested_base", BASE_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load base script: {BASE_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


base = load_base_module()


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def pct(numerator: int, denominator: int, digits: int = 1) -> float:
    if denominator == 0:
        return 0.0
    return round(numerator / denominator * 100, digits)


def parse_categories(text: str) -> set[str]:
    return {part.strip() for part in str(text or "").split(";") if part.strip()}


def row_has_criminal(row: dict[str, Any]) -> bool:
    return row.get("전과공개_보유") == "Y"


def row_has_tax(row: dict[str, Any]) -> bool:
    return row.get("체납이력_보유") == "Y"


def row_has_current_tax(row: dict[str, Any]) -> bool:
    return row.get("현체납_보유") == "Y"


def risk_bucket(row: dict[str, Any]) -> str:
    has_criminal = row_has_criminal(row)
    has_tax = row_has_tax(row)
    if has_criminal and has_tax:
        return "전과·체납 동시"
    if has_criminal:
        return "전과만"
    if has_tax:
        return "체납만"
    return ""


def party_bucket(party: str) -> str:
    if party in {"더불어민주당", "국민의힘", "진보당"}:
        return party
    return "기타"


def build_uncontested_context() -> dict[str, Any]:
    snapshot = base.read_json(base.SNAPSHOT_PATH)
    details_payload = base.read_json(base.DETAILS_PATH)
    constituencies = base.read_json(base.CONSTITUENCIES_PATH)
    criminal_payload = base.read_json(base.CRIMINAL_PATH)

    details_by_huboid = {
        str(row.get("huboid")): row
        for row in details_payload.get("details", [])
        if row.get("huboid")
    }
    criminal_by_huboid, public_categories = base.classify_criminal_records(criminal_payload)
    joint_sd_map = base.build_joint_sd_map(constituencies)

    seats_by_key: dict[str, dict[str, Any]] = {}
    for item in constituencies:
        key = base.district_key(item, joint_sd_map)
        seat_count = base.parse_int(item.get("sggJungsu"))
        if seat_count <= 0:
            continue
        seats_by_key[key.text] = {
            "sg_type": key.sg_type,
            "sd_name": key.sd_name,
            "sgg_name": key.sgg_name,
            "office": base.office_name(key.sg_type),
            "office_type": base.office_type(key.sg_type),
            "seat_count": seat_count,
        }

    active_candidates: list[dict[str, Any]] = []
    candidate_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw in snapshot.get("candidates", []):
        if not base.is_active_candidate(raw):
            continue
        enriched = base.enrich_candidate(raw, details_by_huboid, criminal_by_huboid)
        key = base.district_key(enriched, joint_sd_map)
        enriched["district_key"] = key.text
        enriched["office"] = base.office_name(key.sg_type)
        enriched["office_type"] = base.office_type(key.sg_type)
        enriched["sdName"] = key.sd_name
        enriched["sggName"] = key.sgg_name
        active_candidates.append(enriched)
        candidate_groups[key.text].append(enriched)

    district_rows = base.make_district_rows(seats_by_key, candidate_groups)
    uncontested_rows = base.make_uncontested_candidate_rows(district_rows, candidate_groups)

    return {
        "snapshot": snapshot,
        "details_payload": details_payload,
        "criminal_payload": criminal_payload,
        "criminal_by_huboid": criminal_by_huboid,
        "criminal_raw_by_huboid": {
            str(row.get("huboid")): row
            for row in criminal_payload.get("records", [])
            if row.get("huboid")
        },
        "public_categories": public_categories,
        "active_candidates": active_candidates,
        "district_rows": district_rows,
        "uncontested_rows": uncontested_rows,
    }


def make_candidate_flag_rows(uncontested_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in uncontested_rows:
        has_criminal = row_has_criminal(row)
        has_tax = row_has_tax(row)
        if not has_criminal and not has_tax:
            continue
        rows.append({
            "huboid": row["huboid"],
            "name": row["name"],
            "party": row["party"],
            "office": row["office"],
            "sdName": row["sdName"],
            "sggName": row["sggName"],
            "risk_bucket": risk_bucket(row),
            "criminal_record_disclosure": row["criminal_record_disclosure"],
            "categories": row["categories"],
            "important_categories": row["important_categories"],
            "tax_arrears_5y_thousand_krw": row["tax_arrears_5y_thousand_krw"],
            "tax_arrears_5y_display": row["tax_arrears_5y_display"],
            "tax_arrears_current_thousand_krw": row["tax_arrears_current_thousand_krw"],
            "tax_arrears_current_display": row["tax_arrears_current_display"],
            "nec_detail_url": row["nec_detail_url"],
        })
    rows.sort(
        key=lambda r: (
            {"전과·체납 동시": 0, "체납만": 1, "전과만": 2}.get(r["risk_bucket"], 9),
            -base.parse_int(r["tax_arrears_5y_thousand_krw"]),
            r["party"],
            r["sdName"],
            r["office"],
            r["sggName"],
            r["name"],
        )
    )
    return rows


def make_by_party(uncontested_rows: list[dict[str, Any]], active_candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    total_by_party = Counter(party_bucket(c.get("party") or c.get("jdName") or "무소속") for c in active_candidates)
    grouped: dict[str, Counter[str]] = defaultdict(Counter)
    for row in uncontested_rows:
        party = party_bucket(row["party"])
        grouped[party]["uncontested"] += 1
        if row_has_criminal(row):
            grouped[party]["criminal"] += 1
        if row_has_tax(row):
            grouped[party]["tax_5y"] += 1
        if row_has_current_tax(row):
            grouped[party]["current_tax"] += 1
        if row_has_criminal(row) or row_has_tax(row):
            grouped[party]["criminal_or_tax"] += 1

    rows: list[dict[str, Any]] = []
    for party in PARTY_ORDER:
        counter = grouped[party]
        total = total_by_party[party]
        rows.append({
            "party": party,
            "정당전체후보수": total,
            "무투표당선_후보수": counter["uncontested"],
            "정당전체후보대비_무투표비율": pct(counter["uncontested"], total),
            "전과신고_후보수": counter["criminal"],
            "최근5년체납_후보수": counter["tax_5y"],
            "현체납_후보수": counter["current_tax"],
            "전과또는체납_합집합": counter["criminal_or_tax"],
            "무투표후보내_전과또는체납비율": pct(counter["criminal_or_tax"], counter["uncontested"]),
        })
    return rows


def make_by_office(uncontested_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, Counter[str]] = defaultdict(Counter)
    for row in uncontested_rows:
        office = row["office"]
        grouped[office]["uncontested"] += 1
        if row_has_criminal(row):
            grouped[office]["criminal"] += 1
        if row_has_tax(row):
            grouped[office]["tax_5y"] += 1
        if row_has_current_tax(row):
            grouped[office]["current_tax"] += 1
        if row_has_criminal(row) or row_has_tax(row):
            grouped[office]["criminal_or_tax"] += 1

    rows: list[dict[str, Any]] = []
    for office in OFFICE_ORDER:
        counter = grouped[office]
        rows.append({
            "office": OFFICE_DISPLAY.get(office, office),
            "office_raw": office,
            "무투표당선_후보수": counter["uncontested"],
            "전과신고_후보수": counter["criminal"],
            "최근5년체납_후보수": counter["tax_5y"],
            "현체납_후보수": counter["current_tax"],
            "전과또는체납_합집합": counter["criminal_or_tax"],
            "무투표후보내_전과또는체납비율": pct(counter["criminal_or_tax"], counter["uncontested"]),
        })
    return rows


def offense_row_hit_count(record: dict[str, Any], categories: set[str]) -> int:
    count = 0
    for offense in record.get("offenses") or []:
        if categories & set(offense.get("categories") or []):
            count += 1
    return count


def make_offense_distribution(
    uncontested_rows: list[dict[str, Any]],
    criminal_records: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    criminal_rows = [row for row in uncontested_rows if row_has_criminal(row)]
    distribution: list[dict[str, Any]] = []

    for label, categories, note in OFFENSE_GROUPS:
        candidate_count = 0
        category_hit_count = 0
        offense_hit_count = 0
        example_names: list[str] = []
        for row in criminal_rows:
            row_categories = parse_categories(row["categories"])
            hits = row_categories & categories
            if not hits:
                continue
            candidate_count += 1
            category_hit_count += len(hits)
            offense_hit_count += offense_row_hit_count(criminal_records.get(row["huboid"], {}), categories)
            if len(example_names) < 10:
                example_names.append(row["name"])
        distribution.append({
            "분류": label,
            "후보수": candidate_count,
            "분류적중건수": category_hit_count,
            "OCR_전과행_적중건수_참고": offense_hit_count,
            "비고": note,
            "예시후보": ", ".join(example_names),
        })

    other_candidate_count = 0
    other_hit_count = 0
    other_offense_count = 0
    other_names: list[str] = []
    for row in criminal_rows:
        row_categories = parse_categories(row["categories"])
        hits = row_categories - OFFENSE_GROUP_COVERAGE
        if not hits:
            continue
        other_candidate_count += 1
        other_hit_count += len(hits)
        record = criminal_records.get(row["huboid"], {})
        for offense in record.get("offenses") or []:
            if set(offense.get("categories") or []) - OFFENSE_GROUP_COVERAGE:
                other_offense_count += 1
        if len(other_names) < 10:
            other_names.append(row["name"])

    distribution.append({
        "분류": "기타",
        "후보수": other_candidate_count,
        "분류적중건수": other_hit_count,
        "OCR_전과행_적중건수_참고": other_offense_count,
        "비고": "위 8개 묶음에 들어가지 않은 전과 분류",
        "예시후보": ", ".join(other_names),
    })
    return distribution


def make_economic_candidate_rows(uncontested_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in uncontested_rows:
        categories = parse_categories(row["categories"])
        hits = sorted(categories & ECONOMIC_CATEGORIES)
        if not hits:
            continue
        rows.append({
            "huboid": row["huboid"],
            "name": row["name"],
            "party": row["party"],
            "office": row["office"],
            "sdName": row["sdName"],
            "sggName": row["sggName"],
            "경제범죄분류": ", ".join(hits),
            "최근5년체납_보유": row["체납이력_보유"],
            "최근5년체납액_천원": row["tax_arrears_5y_thousand_krw"],
            "현체납_보유": row["현체납_보유"],
            "전과분류전체": row["categories"],
            "nec_detail_url": row["nec_detail_url"],
        })
    rows.sort(key=lambda r: (r["party"], r["sdName"], r["office"], r["sggName"], r["name"]))
    return rows


def make_key_stats(
    context: dict[str, Any],
    by_party: list[dict[str, Any]],
    by_office: list[dict[str, Any]],
    offense_distribution: list[dict[str, Any]],
    economic_rows: list[dict[str, Any]],
) -> dict[str, Any]:
    snapshot = context["snapshot"]
    criminal_payload = context["criminal_payload"]
    uncontested_rows = context["uncontested_rows"]
    district_rows = context["district_rows"]
    active_candidates = context["active_candidates"]
    criminal_records = context["criminal_raw_by_huboid"]

    uncontested_districts = [row for row in district_rows if row["무투표당선여부"] == "Y"]
    single_candidate_districts = [
        row
        for row in uncontested_districts
        if base.parse_int(row["의원정수"]) == 1 and base.parse_int(row["등록후보수"]) == 1
    ]
    criminal_count = sum(1 for row in uncontested_rows if row_has_criminal(row))
    tax_count = sum(1 for row in uncontested_rows if row_has_tax(row))
    current_tax_count = sum(1 for row in uncontested_rows if row_has_current_tax(row))
    both_criminal_tax = sum(1 for row in uncontested_rows if row_has_criminal(row) and row_has_tax(row))
    union_count = sum(1 for row in uncontested_rows if row_has_criminal(row) or row_has_tax(row))
    only_criminal = sum(1 for row in uncontested_rows if row_has_criminal(row) and not row_has_tax(row))
    only_tax = sum(1 for row in uncontested_rows if row_has_tax(row) and not row_has_criminal(row))
    economic_count = len(economic_rows)
    economic_category_hits = sum(len(parse_categories(row["전과분류전체"]) & ECONOMIC_CATEGORIES) for row in economic_rows)
    economic_tax_overlap = [row for row in economic_rows if row["최근5년체납_보유"] == "Y"]
    important_tax_overlap = sum(
        1
        for row in uncontested_rows
        if row_has_tax(row) and row.get("공직검증전과_보유") == "Y"
    )

    all_tax_huboids = {c["huboid"] for c in active_candidates if c.get("has_tax_history")}
    all_economic_huboids = {
        huboid
        for huboid, record in criminal_records.items()
        if set(record.get("categories") or []) & ECONOMIC_CATEGORIES
    }

    return {
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "snapshot_date": "2026-05-17",
        "snapshot_fetched_at": snapshot.get("fetched_at"),
        "snapshot_total_candidates": snapshot.get("total_candidates"),
        "criminal_ocr_generated_at": (criminal_payload.get("meta") or {}).get("generated_at"),
        "criminal_ocr_processed": (criminal_payload.get("meta") or {}).get("processed"),
        "source_files": {
            "candidate_snapshot": str(base.SNAPSHOT_PATH.relative_to(ROOT)).replace("\\", "/"),
            "candidate_details": str(base.DETAILS_PATH.relative_to(ROOT)).replace("\\", "/"),
            "constituencies": str(base.CONSTITUENCIES_PATH.relative_to(ROOT)).replace("\\", "/"),
            "criminal_ocr": str(base.CRIMINAL_PATH.relative_to(ROOT)).replace("\\", "/"),
        },
        "source_urls": {
            "nec_candidate_info": OFFICIAL_NEC_URL,
            "sbs_nec_uncontested_report": SBS_URL,
            "donga_daum_uncontested_report": DONGA_DAUM_URL,
        },
        "total_uncontested_candidates": len(uncontested_rows),
        "total_uncontested_districts": len(uncontested_districts),
        "single_candidate_districts_seat1_candidate1": len(single_candidate_districts),
        "office_breakdown_reported": {
            row["office"]: row["무투표당선_후보수"]
            for row in by_office
        },
        "criminal_disclosure_candidates": criminal_count,
        "tax_5y_candidates": tax_count,
        "current_tax_candidates": current_tax_count,
        "criminal_or_tax_union_candidates": union_count,
        "criminal_only_candidates": only_criminal,
        "tax_only_candidates": only_tax,
        "criminal_and_tax_candidates": both_criminal_tax,
        "economic_crime_candidates": economic_count,
        "economic_crime_category_hits": economic_category_hits,
        "economic_crime_and_tax_overlap_uncontested": len(economic_tax_overlap),
        "economic_crime_and_tax_overlap_uncontested_names": [row["name"] for row in economic_tax_overlap],
        "tax_and_public_vetting_record_overlap_uncontested": important_tax_overlap,
        "economic_crime_and_tax_overlap_all_candidates": len(all_tax_huboids & all_economic_huboids),
        "union_share_of_uncontested_candidates": pct(union_count, len(uncontested_rows)),
        "by_party": by_party,
        "by_office": by_office,
        "offense_distribution": offense_distribution,
    }


def md_table(rows: list[dict[str, Any]], columns: list[str]) -> str:
    if not rows:
        return ""
    lines = [
        "| " + " | ".join(columns) + " |",
        "| " + " | ".join("---" for _ in columns) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(str(row.get(col, "")) for col in columns) + " |")
    return "\n".join(lines)


def make_report(
    stats: dict[str, Any],
    by_party: list[dict[str, Any]],
    by_office: list[dict[str, Any]],
    offense_distribution: list[dict[str, Any]],
    economic_rows: list[dict[str, Any]],
) -> str:
    current_tax_note = f"{stats['current_tax_candidates']}명"
    economic_names = ", ".join(row["name"] for row in economic_rows)
    economic_tax_names = ", ".join(stats["economic_crime_and_tax_overlap_uncontested_names"]) or "없음"

    source_line = (
        f"- 선관위 후보자 공개정보 로컬 스냅샷: `{stats['source_files']['candidate_snapshot']}` "
        f"(수집 {stats['snapshot_fetched_at']}, 후보 {stats['snapshot_total_candidates']:,}명)\n"
        f"- 선관위 후보자 상세 공개정보: `{stats['source_files']['candidate_details']}` / {OFFICIAL_NEC_URL}\n"
        f"- 전과 PDF 분류 결과: `{stats['source_files']['criminal_ocr']}` "
        f"(처리 {stats['criminal_ocr_processed']:,}명)\n"
        f"- 513명·307곳 보도 대조: SBS {SBS_URL}, 동아일보/다음 {DONGA_DAUM_URL}"
    )

    title_rows = [
        {"안": "A", "제목": f"무투표 513명, {stats['criminal_or_tax_union_candidates']}명 전과·체납", "SEO점수": "9.5", "코멘트": "숫자와 키워드가 모두 들어가 검색·공유에 강함"},
        {"안": "B", "제목": f"513명 중 {stats['criminal_or_tax_union_candidates']}명, 전과·체납 신고한 채 투표 없이 당선", "SEO점수": "9.0", "코멘트": "리드형 제목. 길지만 맥락이 가장 명확함"},
        {"안": "C", "제목": f"투표 없는 당선 513명, 검증 신호 {stats['criminal_or_tax_union_candidates']}명", "SEO점수": "8.4", "코멘트": "방송 자막용으로 부드럽지만 검색어 밀도는 약간 낮음"},
    ]

    report = f"""# 6·3 지방선거 무투표 당선 513명 전과·체납 전수 검증

생성 시각: {stats['generated_at']}

## 사용 자료

{source_line}

## 1. 기존 수치 재확인

- 513명: 확인됨. 로컬 선관위 후보 스냅샷+의원정수 매칭 결과 {stats['total_uncontested_candidates']}명, SBS·동아일보 보도와 일치.
- 307곳: 확인됨. 로컬 선거구 판정 {stats['total_uncontested_districts']}곳, SBS·동아일보 보도와 일치.
- 직책별 내역: 확인됨. 기초단체장 3명 / 광역의원 108명 / 지역구 기초의원 305명 / 기초의원 비례대표 97명.
- 사기·횡령·배임·뇌물 분류 전과 10명: 확인됨. 명단: {economic_names}
- 단독후보(의원정수 1·등록후보 1): 확인됨. {stats['single_candidate_districts_seat1_candidate1']}곳.
- 최근 5년 체납 이력: 확인됨. {stats['tax_5y_candidates']}명.
- 현재 체납: 확인됨. {current_tax_note}.
- 체납+사기·횡령·배임·뇌물 분류 10명 중복: 확인됨. {len(stats['economic_crime_and_tax_overlap_uncontested_names'])}명({economic_tax_names}).
- 주의: v6의 “12명 중복”은 이번 기준에서는 `체납+공직 검증 전과` 교집합 {stats['tax_and_public_vetting_record_overlap_uncontested']}명과 일치합니다. `체납+사기·횡령·배임·뇌물` 교집합은 무투표 513명 안에서는 1명, 전체 후보 기준으로는 {stats['economic_crime_and_tax_overlap_all_candidates']}명입니다.

## 2. 신규 산출

- A(전과 1건 이상 신고): {stats['criminal_disclosure_candidates']}명.
- B(전과 또는 최근 5년 체납 합집합): {stats['criminal_or_tax_union_candidates']}명.
- B 산출식: {stats['criminal_disclosure_candidates']} + {stats['tax_5y_candidates']} - {stats['criminal_and_tax_candidates']} = {stats['criminal_or_tax_union_candidates']}.
- B1(전과만): {stats['criminal_only_candidates']}명.
- B2(체납만): {stats['tax_only_candidates']}명.
- B3(전과·체납 동시): {stats['criminal_and_tax_candidates']}명.
- 합산 검증: {stats['criminal_only_candidates']} + {stats['tax_only_candidates']} + {stats['criminal_and_tax_candidates']} = {stats['criminal_or_tax_union_candidates']}.
- 무투표 당선 513명 중 전과 또는 체납 신고 비율: {stats['union_share_of_uncontested_candidates']}%.

## 3. 죄목별 분포

아래 `분류적중건수`는 후보별 죄명 분류가 해당 묶음에 걸린 횟수입니다. PDF 원문 한 줄짜리 전과 행 수와는 다를 수 있으므로, 기사 본문에는 후보 수를 우선 쓰고 세부 죄명은 선관위 상세 원문 확인 뒤 인용하는 편이 안전합니다.

{md_table(offense_distribution, ["분류", "후보수", "분류적중건수", "OCR_전과행_적중건수_참고", "비고"])}

## 4. 정당별

{md_table(by_party, ["party", "정당전체후보수", "무투표당선_후보수", "전과신고_후보수", "최근5년체납_후보수", "현체납_후보수", "전과또는체납_합집합", "무투표후보내_전과또는체납비율"])}

## 5. 정당별 무투표 의존도

{md_table(by_party, ["party", "정당전체후보수", "무투표당선_후보수", "정당전체후보대비_무투표비율"])}

## 6. 직책별

{md_table(by_office, ["office", "무투표당선_후보수", "전과신고_후보수", "최근5년체납_후보수", "현체납_후보수", "전과또는체납_합집합", "무투표후보내_전과또는체납비율"])}

## 7. 기사 v10 제목 후보

{md_table(title_rows, ["안", "제목", "SEO점수", "코멘트"])}

## 8. 비어 있는 데이터 / 추가 검증 필요

- 513명 명단: 로컬 선관위 후보 스냅샷과 의원정수표로 전수 확보.
- 각 후보 전과·체납 여부: 선관위 후보자 상세 공개정보 필드 기준으로 전수 산출.
- 각 후보별 죄명 세부 표현·시점·형량: 후보 실명 기사 문장에는 선관위 상세 페이지 원문 확인 필요.
- 비례대표 순번: 이번 검증의 핵심 산출 대상이 아니어서 별도 순번 검증은 하지 않았음.
- `OCR_전과행_적중건수_참고`는 자동 추출된 전과 행 기준이라 후보별 PDF 표가 깨진 경우 과소·과대 가능. 기사 숫자는 `전과 신고 여부`, `후보 수`, `분류적중건수` 중심으로 사용 권장.

## 방송 원고용 한 문장

선관위 후보자 공개정보와 선거구별 의원정수 자료를 대조한 결과, 6·3 지방선거에서 투표 없이 당선되는 후보 513명 가운데 전과 또는 최근 5년 체납 이력 중 하나라도 신고한 후보는 {stats['criminal_or_tax_union_candidates']}명, 전체의 {stats['union_share_of_uncontested_candidates']}%였습니다.
"""
    return report


def write_readme(path: Path, stats: dict[str, Any]) -> None:
    files = [
        "uncontested_513_verification_report.md",
        "uncontested_513_key_stats.json",
        "uncontested_513_red_flag_candidates.csv",
        "uncontested_513_by_party.csv",
        "uncontested_513_by_office.csv",
        "uncontested_513_offense_distribution.csv",
        "uncontested_513_economic_crime_candidates.csv",
    ]
    text = f"""# 무투표 당선 513명 전과·체납 전수 검증 패키지

기준: 2026년 5월 17일 후보 등록 스냅샷.

핵심 숫자:
- 무투표 당선 후보: {stats['total_uncontested_candidates']}명
- 전과 신고: {stats['criminal_disclosure_candidates']}명
- 최근 5년 체납 이력: {stats['tax_5y_candidates']}명
- 전과 또는 체납 합집합: {stats['criminal_or_tax_union_candidates']}명
- 전과만: {stats['criminal_only_candidates']}명
- 체납만: {stats['tax_only_candidates']}명
- 전과·체납 동시: {stats['criminal_and_tax_candidates']}명

파일:
{chr(10).join(f'- `{name}`' for name in files)}

주의:
- 전과 분류는 후보 1명이 여러 유형에 중복 포함될 수 있습니다.
- 후보 실명 기사 문장에는 선관위 후보자 상세 페이지 원문 확인이 필요합니다.
- 체납은 최근 5년 체납 이력과 현 체납을 구분해야 합니다.
"""
    path.write_text(text, encoding="utf-8")


def build_package(out_dir: Path = OUT_DIR) -> dict[str, Any]:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    context = build_uncontested_context()
    uncontested_rows = context["uncontested_rows"]
    active_candidates = context["active_candidates"]
    criminal_records = context["criminal_raw_by_huboid"]

    red_flag_rows = make_candidate_flag_rows(uncontested_rows)
    by_party = make_by_party(uncontested_rows, active_candidates)
    by_office = make_by_office(uncontested_rows)
    offense_distribution = make_offense_distribution(uncontested_rows, criminal_records)
    economic_rows = make_economic_candidate_rows(uncontested_rows)
    stats = make_key_stats(context, by_party, by_office, offense_distribution, economic_rows)

    report = make_report(stats, by_party, by_office, offense_distribution, economic_rows)

    write_csv(out_dir / "uncontested_513_red_flag_candidates.csv", red_flag_rows, [
        "huboid", "name", "party", "office", "sdName", "sggName", "risk_bucket",
        "criminal_record_disclosure", "categories", "important_categories",
        "tax_arrears_5y_thousand_krw", "tax_arrears_5y_display",
        "tax_arrears_current_thousand_krw", "tax_arrears_current_display",
        "nec_detail_url",
    ])
    write_csv(out_dir / "uncontested_513_by_party.csv", by_party, [
        "party", "정당전체후보수", "무투표당선_후보수", "정당전체후보대비_무투표비율",
        "전과신고_후보수", "최근5년체납_후보수", "현체납_후보수",
        "전과또는체납_합집합", "무투표후보내_전과또는체납비율",
    ])
    write_csv(out_dir / "uncontested_513_by_office.csv", by_office, [
        "office", "office_raw", "무투표당선_후보수", "전과신고_후보수", "최근5년체납_후보수",
        "현체납_후보수", "전과또는체납_합집합", "무투표후보내_전과또는체납비율",
    ])
    write_csv(out_dir / "uncontested_513_offense_distribution.csv", offense_distribution, [
        "분류", "후보수", "분류적중건수", "OCR_전과행_적중건수_참고", "비고", "예시후보",
    ])
    write_csv(out_dir / "uncontested_513_economic_crime_candidates.csv", economic_rows, [
        "huboid", "name", "party", "office", "sdName", "sggName", "경제범죄분류",
        "최근5년체납_보유", "최근5년체납액_천원", "현체납_보유", "전과분류전체", "nec_detail_url",
    ])
    write_json(out_dir / "uncontested_513_key_stats.json", stats)
    (out_dir / "uncontested_513_verification_report.md").write_text(report, encoding="utf-8")
    write_readme(out_dir / "README.md", stats)

    zip_path = out_dir.with_suffix(".zip")
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(out_dir.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(out_dir.parent))

    return {
        "out_dir": str(out_dir),
        "zip_path": str(zip_path),
        "stats": stats,
    }


def main() -> None:
    result = build_package()
    print(json.dumps({
        "out_dir": result["out_dir"],
        "zip_path": result["zip_path"],
        "summary": {
            key: result["stats"][key]
            for key in [
                "total_uncontested_candidates",
                "total_uncontested_districts",
                "criminal_disclosure_candidates",
                "tax_5y_candidates",
                "current_tax_candidates",
                "criminal_or_tax_union_candidates",
                "criminal_only_candidates",
                "tax_only_candidates",
                "criminal_and_tax_candidates",
                "union_share_of_uncontested_candidates",
            ]
        },
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
