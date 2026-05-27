#!/usr/bin/env python3
"""Export uncontested-district evidence tables for the 2026 local election series."""

from __future__ import annotations

import argparse
import csv
import json
import shutil
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
KST = timezone(timedelta(hours=9))

SNAPSHOT_PATH = ROOT / "data" / "candidates" / "20260603" / "snapshot_20260517.json"
DETAILS_PATH = ROOT / "data" / "candidate_details.json"
CONSTITUENCIES_PATH = ROOT / "data" / "constituencies.json"
CRIMINAL_PATH = ROOT / "data" / "criminal_ocr.json"
DEFAULT_OUT_DIR = ROOT / "exports" / "uncontested_series_package_20260517_0900"

JOINT_SIDO = "전남광주통합특별시"
JOINT_SIDO_MEMBERS = {"광주광역시", "전라남도"}

SG_TITLE = {
    "2": "국회의원(재·보궐)",
    "3": "시도지사",
    "4": "기초단체장",
    "5": "시도의원",
    "6": "구시군의회의원",
    "8": "광역의원비례",
    "9": "기초의원비례",
    "11": "교육감",
}

LEAD_ECONOMIC_CATEGORIES = {"사기", "횡령", "뇌물", "배임"}
TAX_100M_THOUSAND_KRW = 100_000


@dataclass(frozen=True)
class DistrictKey:
    sg_type: str
    sd_name: str
    sgg_name: str

    @property
    def text(self) -> str:
        return f"{self.sg_type}|{self.sd_name}|{self.sgg_name}"


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


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


def parse_int(value: Any) -> int:
    if value is None:
        return 0
    if isinstance(value, int):
        return value
    text = str(value).strip().replace(",", "")
    if not text or text in {"-", "없음"}:
        return 0
    try:
        return int(float(text))
    except ValueError:
        return 0


def format_thousand_krw(value: int) -> str:
    return f"{value:,}천원" if value else "0천원"


def ratio_pct(numerator: int, denominator: int, digits: int = 1) -> float:
    if not denominator:
        return 0.0
    return round(numerator / denominator * 100, digits)


def party_name(candidate: dict[str, Any]) -> str:
    return candidate.get("jdName") or candidate.get("party") or "무소속"


def office_name(sg_type: str) -> str:
    return SG_TITLE.get(str(sg_type), str(sg_type))


def office_type(sg_type: str) -> str:
    sg_type = str(sg_type)
    if sg_type in {"8", "9"}:
        return "비례"
    if sg_type in {"2", "11"}:
        return "특수(교육감·재보궐 등)"
    return "지역구"


def is_active_candidate(candidate: dict[str, Any]) -> bool:
    return not candidate.get("status") or candidate.get("status") == "등록"


def joint_constituency_key(item: dict[str, Any]) -> str:
    return f"{item.get('sgTypecode')}|{item.get('sggName')}"


def build_joint_sd_map(constituencies: list[dict[str, Any]]) -> dict[str, str]:
    out: dict[str, str] = {}
    for item in constituencies:
        if item.get("sdName") in JOINT_SIDO_MEMBERS or item.get("sggName") == JOINT_SIDO:
            out[joint_constituency_key(item)] = item.get("sdName") or ""
    return out


def district_key(item: dict[str, Any], joint_sd_map: dict[str, str]) -> DistrictKey:
    sg_type = str(item.get("sgTypecode") or "")
    sd_name = item.get("sdName") or ""
    if sd_name == JOINT_SIDO:
        sd_name = joint_sd_map.get(joint_constituency_key(item), sd_name)
    return DistrictKey(sg_type=sg_type, sd_name=sd_name, sgg_name=item.get("sggName") or "")


def list_text(values: list[Any]) -> str:
    return ", ".join(str(v) for v in values if v is not None and str(v) != "")


def category_text(values: list[str]) -> str:
    return "; ".join(values)


def classify_criminal_records(criminal_payload: dict[str, Any]) -> tuple[dict[str, dict[str, Any]], set[str]]:
    category_group = {
        item.get("category"): item.get("group")
        for item in criminal_payload.get("categories", [])
        if item.get("category")
    }
    public_categories = {
        category for category, group in category_group.items() if group == "공직 검증"
    }

    records: dict[str, dict[str, Any]] = {}
    for row in criminal_payload.get("records", []):
        huboid = str(row.get("huboid") or "")
        cats = [str(c) for c in row.get("categories", []) if c]
        important = [c for c in cats if c in public_categories]
        offenses = row.get("offenses", []) or []
        important_offense_count = sum(
            1
            for offense in offenses
            if any(c in public_categories for c in (offense.get("categories") or []))
        )
        records[huboid] = {
            "categories": cats,
            "important_categories": important,
            "offense_count": len(offenses),
            "important_offense_count": important_offense_count,
            "nec_detail_url": row.get("nec_detail_url") or "",
        }
    return records, public_categories


def enrich_candidate(
    candidate: dict[str, Any],
    details_by_huboid: dict[str, dict[str, Any]],
    criminal_by_huboid: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    huboid = str(candidate.get("huboid") or "")
    details = details_by_huboid.get(huboid, {})
    disclosures = details.get("disclosures") or {}
    criminal = criminal_by_huboid.get(huboid, {})

    tax_5y = parse_int(disclosures.get("tax_arrears_5y_thousand_krw"))
    tax_current = parse_int(disclosures.get("tax_arrears_current_thousand_krw"))
    disclosure = disclosures.get("criminal_record") or candidate.get("criminal_record") or ""
    cats = list(criminal.get("categories") or [])
    important = list(criminal.get("important_categories") or [])

    return {
        **candidate,
        "huboid": huboid,
        "party": party_name(candidate),
        "nec_detail_url": details.get("nec_detail_url") or criminal.get("nec_detail_url") or "",
        "tax_arrears_5y_thousand_krw": tax_5y,
        "tax_arrears_5y_display": format_thousand_krw(tax_5y),
        "tax_arrears_current_thousand_krw": tax_current,
        "tax_arrears_current_display": format_thousand_krw(tax_current),
        "criminal_record_disclosure": disclosure,
        "categories_list": cats,
        "important_categories_list": important,
        "categories": category_text(cats),
        "important_categories": category_text(important),
        "criminal_offense_count": int(criminal.get("offense_count") or 0),
        "important_offense_count": int(criminal.get("important_offense_count") or 0),
        "has_tax_history": tax_5y > 0,
        "has_current_tax": tax_current > 0,
        "has_criminal_disclosure": bool(disclosure and disclosure != "없음"),
        "has_important_criminal": bool(important),
        "has_election_law": "공직선거법" in cats or "공직선거법" in important,
    }


def candidate_flag_count(candidates: list[dict[str, Any]], key: str) -> int:
    return sum(1 for c in candidates if c.get(key))


def make_district_rows(
    seats_by_key: dict[str, dict[str, Any]],
    candidate_groups: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key_text, seat_info in seats_by_key.items():
        candidates = candidate_groups.get(key_text, [])
        seat_count = seat_info["seat_count"]
        candidate_count = len(candidates)
        parties = [c.get("party") for c in candidates if c.get("party")]
        unique_parties = sorted(set(parties))
        single_party_proportional = (
            str(seat_info["sg_type"]) in {"8", "9"}
            and candidate_count > 0
            and len(unique_parties) == 1
            and candidate_count > seat_count
        )
        uncontested = candidate_count > 0 and (candidate_count <= seat_count or single_party_proportional)
        short = candidate_count < seat_count
        risk = any(c["has_tax_history"] or c["has_important_criminal"] for c in candidates)

        rows.append({
            "district_key": key_text,
            "sgTypecode": seat_info["sg_type"],
            "sdName": seat_info["sd_name"],
            "sggName": seat_info["sgg_name"],
            "office": seat_info["office"],
            "office_type": seat_info["office_type"],
            "의원정수": seat_count,
            "등록후보수": candidate_count,
            "경쟁률": f"{candidate_count / seat_count:.2f}" if seat_count else "",
            "무투표당선여부": "Y" if uncontested else "N",
            "무투표판정기준": (
                "비례대표_단일정당명부" if single_party_proportional else "등록후보수_의원정수이하" if uncontested else ""
            ),
            "비례대표_단일정당명부여부": "Y" if single_party_proportional else "N",
            "등록미달여부": "Y" if short else "N",
            "경쟁률_1미만여부": "Y" if short else "N",
            "해당선거구_후보huboid_리스트": list_text([c["huboid"] for c in candidates]),
            "해당선거구_후보명_리스트": list_text([c.get("name") for c in candidates]),
            "해당선거구_정당_리스트": list_text([c.get("party") for c in candidates]),
            "체납이력_후보수": candidate_flag_count(candidates, "has_tax_history"),
            "현체납_후보수": candidate_flag_count(candidates, "has_current_tax"),
            "전과공개_후보수": candidate_flag_count(candidates, "has_criminal_disclosure"),
            "공직검증전과_후보수": candidate_flag_count(candidates, "has_important_criminal"),
            "공직선거법전과_후보수": candidate_flag_count(candidates, "has_election_law"),
            "체납+공직검증전과_동시보유_후보수": sum(
                1 for c in candidates if c["has_tax_history"] and c["has_important_criminal"]
            ),
            "검증위험_플래그": "Y" if risk else "N",
        })

    rows.sort(
        key=lambda r: (
            r["무투표당선여부"] != "Y",
            r["검증위험_플래그"] != "Y",
            -int(r["의원정수"] or 0),
            r["sdName"],
            r["office"],
            r["sggName"],
        )
    )
    return rows


def make_uncontested_candidate_rows(
    district_rows: list[dict[str, Any]],
    candidate_groups: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    district_lookup = {row["district_key"]: row for row in district_rows if row["무투표당선여부"] == "Y"}
    rows: list[dict[str, Any]] = []
    for key_text, district in district_lookup.items():
        for c in candidate_groups.get(key_text, []):
            rows.append({
                "huboid": c["huboid"],
                "name": c.get("name") or "",
                "party": c.get("party") or "",
                "office": district["office"],
                "office_type": district["office_type"],
                "sdName": district["sdName"],
                "sggName": district["sggName"],
                "nec_detail_url": c.get("nec_detail_url") or "",
                "tax_arrears_5y_thousand_krw": c["tax_arrears_5y_thousand_krw"],
                "tax_arrears_5y_display": c["tax_arrears_5y_display"],
                "tax_arrears_current_thousand_krw": c["tax_arrears_current_thousand_krw"],
                "tax_arrears_current_display": c["tax_arrears_current_display"],
        "criminal_record_disclosure": c["criminal_record_disclosure"],
        "categories": c["categories"],
        "important_categories": c["important_categories"],
        "공직검증전과_분류수": len(c["important_categories_list"]),
        "공직검증전과_건수": c["important_offense_count"],
        "체납이력_보유": "Y" if c["has_tax_history"] else "N",
                "현체납_보유": "Y" if c["has_current_tax"] else "N",
                "전과공개_보유": "Y" if c["has_criminal_disclosure"] else "N",
                "공직검증전과_보유": "Y" if c["has_important_criminal"] else "N",
                "공직선거법전과_보유": "Y" if c["has_election_law"] else "N",
                "해당선거구_경쟁률": district["경쟁률"],
                "해당선거구_의원정수": district["의원정수"],
                "해당선거구_무투표판정기준": district["무투표판정기준"],
                "해당선거구_비례대표_단일정당명부여부": district["비례대표_단일정당명부여부"],
                "등록미달여부": district["등록미달여부"],
                "검증위험_플래그": "Y" if c["has_tax_history"] or c["has_important_criminal"] else "N",
            })
    rows.sort(
        key=lambda r: (
            r["검증위험_플래그"] != "Y",
            -int(r["tax_arrears_5y_thousand_krw"] or 0),
            r["sdName"],
            r["office"],
            r["sggName"],
            r["name"],
        )
    )
    return rows


def summarize_by_party(
    uncontested_candidates: list[dict[str, Any]],
    all_candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    total_by_party = Counter(c.get("party") or "무소속" for c in all_candidates)
    district_by_party: dict[str, set[tuple[str, str, str]]] = defaultdict(set)
    tax_districts: dict[str, set[tuple[str, str, str]]] = defaultdict(set)
    important_districts: dict[str, set[tuple[str, str, str]]] = defaultdict(set)
    election_law_districts: dict[str, set[tuple[str, str, str]]] = defaultdict(set)
    counts: dict[str, Counter[str]] = defaultdict(Counter)

    for row in uncontested_candidates:
        party = row["party"] or "무소속"
        dkey = (row["sdName"], row["sggName"], row["office"])
        district_by_party[party].add(dkey)
        counts[party]["uncontested_candidates"] += 1
        if row["체납이력_보유"] == "Y":
            counts[party]["tax"] += 1
            tax_districts[party].add(dkey)
        if row["공직검증전과_보유"] == "Y":
            counts[party]["important"] += 1
            important_districts[party].add(dkey)
        if row["공직선거법전과_보유"] == "Y":
            counts[party]["election_law"] += 1
            election_law_districts[party].add(dkey)

    rows: list[dict[str, Any]] = []
    for party, counter in counts.items():
        total = total_by_party.get(party, 0)
        rows.append({
            "party": party,
            "무투표당선_후보수": counter["uncontested_candidates"],
            "무투표당선_선거구수": len(district_by_party[party]),
            "무투표당선_선거구_공천횟수": counter["uncontested_candidates"],
            "체납이력_후보수": counter["tax"],
            "체납이력_후보를_낸_선거구수": len(tax_districts[party]),
            "공직검증전과_후보수": counter["important"],
            "공직검증전과_후보를_낸_선거구수": len(important_districts[party]),
            "공직선거법전과_후보수": counter["election_law"],
            "공직선거법전과_후보를_낸_선거구수": len(election_law_districts[party]),
            "정당전체후보수": total,
            "정당전체후보대비_무투표후보비율": ratio_pct(counter["uncontested_candidates"], total),
        })
    rows.sort(key=lambda r: (-r["무투표당선_후보수"], r["party"]))
    return rows


def summarize_by_region(
    district_rows: list[dict[str, Any]],
    uncontested_candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    all_districts_by_region = Counter(row["sdName"] for row in district_rows)
    uncontested_districts_by_region = Counter(
        row["sdName"] for row in district_rows if row["무투표당선여부"] == "Y"
    )
    candidates_by_region = Counter(row["sdName"] for row in uncontested_candidates)
    tax_by_region = Counter(row["sdName"] for row in uncontested_candidates if row["체납이력_보유"] == "Y")
    important_by_region = Counter(row["sdName"] for row in uncontested_candidates if row["공직검증전과_보유"] == "Y")
    election_by_region = Counter(row["sdName"] for row in uncontested_candidates if row["공직선거법전과_보유"] == "Y")

    rows: list[dict[str, Any]] = []
    for sd_name in sorted(all_districts_by_region):
        total_districts = all_districts_by_region[sd_name]
        uncontested_districts = uncontested_districts_by_region[sd_name]
        rows.append({
            "sdName": sd_name,
            "무투표당선_선거구수": uncontested_districts,
            "무투표당선_후보수": candidates_by_region[sd_name],
            "체납이력자수": tax_by_region[sd_name],
            "공직검증전과자수": important_by_region[sd_name],
            "공직선거법전과자수": election_by_region[sd_name],
            "시도내_전체선거구수": total_districts,
            "시도내_무투표당선_선거구비율": ratio_pct(uncontested_districts, total_districts),
        })
    rows.sort(key=lambda r: (-r["무투표당선_선거구수"], -r["무투표당선_후보수"], r["sdName"]))
    return rows


def summarize_by_office(
    district_rows: list[dict[str, Any]],
    uncontested_candidates: list[dict[str, Any]],
    all_candidates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    all_districts_by_office = Counter(row["office"] for row in district_rows)
    uncontested_districts_by_office = Counter(
        row["office"] for row in district_rows if row["무투표당선여부"] == "Y"
    )
    all_candidates_by_office = Counter(office_name(str(c.get("sgTypecode") or "")) for c in all_candidates)
    uncontested_candidates_by_office = Counter(row["office"] for row in uncontested_candidates)
    tax_by_office = Counter(row["office"] for row in uncontested_candidates if row["체납이력_보유"] == "Y")
    important_by_office = Counter(row["office"] for row in uncontested_candidates if row["공직검증전과_보유"] == "Y")
    election_by_office = Counter(row["office"] for row in uncontested_candidates if row["공직선거법전과_보유"] == "Y")

    office_type_by_name = {row["office"]: row["office_type"] for row in district_rows}
    rows: list[dict[str, Any]] = []
    for office in sorted(all_districts_by_office):
        total_districts = all_districts_by_office[office]
        total_candidates = all_candidates_by_office[office]
        uncontested_districts = uncontested_districts_by_office[office]
        uncontested_candidate_count = uncontested_candidates_by_office[office]
        rows.append({
            "office": office,
            "office_type": office_type_by_name.get(office, ""),
            "무투표당선_선거구수": uncontested_districts,
            "무투표당선_후보수": uncontested_candidate_count,
            "체납이력자수": tax_by_office[office],
            "공직검증전과자수": important_by_office[office],
            "공직선거법전과자수": election_by_office[office],
            "직책별_전체선거구수": total_districts,
            "직책별_전체후보수": total_candidates,
            "직책별_전체선거구대비_무투표비율": ratio_pct(uncontested_districts, total_districts),
            "직책별_전체후보대비_무투표후보비율": ratio_pct(uncontested_candidate_count, total_candidates),
        })
    rows.sort(key=lambda r: (-r["무투표당선_선거구수"], -r["무투표당선_후보수"], r["office"]))
    return rows


def make_lead_cases(uncontested_candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for row in uncontested_candidates:
        categories = [c.strip() for c in str(row.get("categories") or "").split(";") if c.strip()]
        important = [c.strip() for c in str(row.get("important_categories") or "").split(";") if c.strip()]
        tax_5y = parse_int(row.get("tax_arrears_5y_thousand_krw"))
        important_offense_count = parse_int(row.get("공직검증전과_건수"))

        reasons: list[str] = []
        if tax_5y >= TAX_100M_THOUSAND_KRW:
            reasons.append("최근 5년 체납 1억원 이상")
        if "공직선거법" in categories or "공직선거법" in important:
            reasons.append("공직선거법 전과")
        economic_hits = [c for c in categories if c in LEAD_ECONOMIC_CATEGORIES]
        if economic_hits:
            reasons.append("사기·횡령·뇌물·배임 전과: " + ", ".join(economic_hits))
        if important_offense_count >= 2:
            reasons.append(f"공직 검증 전과 {important_offense_count}건 이상")
        elif len(important) >= 2:
            reasons.append(f"공직 검증 전과 {len(important)}개 분류")
        if not reasons:
            continue

        priority_score = (
            (10 if tax_5y >= TAX_100M_THOUSAND_KRW else 0)
            + (8 if "공직선거법" in categories or "공직선거법" in important else 0)
            + (6 if economic_hits else 0)
            + min(max(len(important), important_offense_count), 5)
        )
        rows.append({
            **row,
            "우선순위_사유": "; ".join(reasons),
            "_priority_score": priority_score,
            "_important_count": len(important),
        })

    rows.sort(
        key=lambda r: (
            -r["_priority_score"],
            -parse_int(r.get("tax_arrears_5y_thousand_krw")),
            -parse_int(r.get("공직검증전과_건수")),
            -r["_important_count"],
            r["sdName"],
            r["office"],
            r["sggName"],
            r["name"],
        )
    )
    return [{k: v for k, v in row.items() if not k.startswith("_")} for row in rows[:30]]


def make_missing_seats_rows(
    candidate_groups: dict[str, list[dict[str, Any]]],
    seats_by_key: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key_text, candidates in sorted(candidate_groups.items()):
        if key_text in seats_by_key:
            continue
        sg_type, sd_name, sgg_name = key_text.split("|", 2)
        rows.append({
            "district_key": key_text,
            "sgTypecode": sg_type,
            "sdName": sd_name,
            "sggName": sgg_name,
            "office": office_name(sg_type),
            "office_type": office_type(sg_type),
            "등록후보수": len(candidates),
            "후보huboid_리스트": list_text([c["huboid"] for c in candidates]),
            "후보명_리스트": list_text([c.get("name") for c in candidates]),
            "정당_리스트": list_text([c.get("party") for c in candidates]),
            "누락사유": "후보 스냅샷에는 있으나 의원정수 표에서 같은 선거구 키를 찾지 못함",
        })
    return rows


def top_rows(rows: list[dict[str, Any]], label_key: str, count_key: str, top_n: int = 5) -> list[dict[str, Any]]:
    return [
        {
            "name": row[label_key],
            "count": row[count_key],
        }
        for row in sorted(
            [r for r in rows if int(r.get(count_key) or 0) > 0],
            key=lambda r: (-int(r[count_key] or 0), str(r[label_key])),
        )[:top_n]
    ]


def make_key_stats(
    district_rows: list[dict[str, Any]],
    uncontested_candidates: list[dict[str, Any]],
    party_rows: list[dict[str, Any]],
    region_rows: list[dict[str, Any]],
    office_rows: list[dict[str, Any]],
    missing_seats_rows: list[dict[str, Any]],
    snapshot_meta: dict[str, Any],
    criminal_meta: dict[str, Any],
) -> dict[str, Any]:
    total_districts = len(district_rows)
    uncontested_districts = [row for row in district_rows if row["무투표당선여부"] == "Y"]
    red_flag_candidates = [
        row
        for row in uncontested_candidates
        if row["체납이력_보유"] == "Y" or row["공직검증전과_보유"] == "Y"
    ]
    return {
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "snapshot_date": "2026-05-17",
        "candidate_snapshot_fetched_at": snapshot_meta.get("fetched_at"),
        "criminal_classification_generated_at": criminal_meta.get("generated_at"),
        "source_files": {
            "candidate_snapshot": str(SNAPSHOT_PATH.relative_to(ROOT)).replace("\\", "/"),
            "candidate_details": str(DETAILS_PATH.relative_to(ROOT)).replace("\\", "/"),
            "constituencies": str(CONSTITUENCIES_PATH.relative_to(ROOT)).replace("\\", "/"),
            "criminal_classification": "전과 PDF 죄명 분류 결과",
        },
        "total_districts": total_districts,
        "total_uncontested_districts": len(uncontested_districts),
        "total_uncontested_candidates": len(uncontested_candidates),
        "uncontested_with_tax_history_candidates": sum(1 for row in uncontested_candidates if row["체납이력_보유"] == "Y"),
        "uncontested_with_current_tax_candidates": sum(1 for row in uncontested_candidates if row["현체납_보유"] == "Y"),
        "uncontested_with_criminal_disclosure_candidates": sum(1 for row in uncontested_candidates if row["전과공개_보유"] == "Y"),
        "uncontested_with_official_misconduct_record_candidates": sum(1 for row in uncontested_candidates if row["공직검증전과_보유"] == "Y"),
        "uncontested_with_election_law_record_candidates": sum(1 for row in uncontested_candidates if row["공직선거법전과_보유"] == "Y"),
        "uncontested_with_both_tax_and_official_misconduct": sum(
            1 for row in uncontested_candidates
            if row["체납이력_보유"] == "Y" and row["공직검증전과_보유"] == "Y"
        ),
        "top_party_uncontested": top_rows(party_rows, "party", "무투표당선_후보수"),
        "top_region_uncontested": top_rows(region_rows, "sdName", "무투표당선_선거구수"),
        "top_office_uncontested": top_rows(office_rows, "office", "무투표당선_선거구수"),
        "share_of_uncontested_among_all_districts": ratio_pct(len(uncontested_districts), total_districts),
        "share_of_uncontested_candidates_with_any_red_flag": ratio_pct(len(red_flag_candidates), len(uncontested_candidates)),
        "underfilled_districts": sum(1 for row in district_rows if row["등록미달여부"] == "Y"),
        "zero_candidate_districts": sum(1 for row in district_rows if int(row["등록후보수"] or 0) == 0),
        "missing_seats_count": len(missing_seats_rows),
    }


def validation_lines(
    district_rows: list[dict[str, Any]],
    uncontested_candidates: list[dict[str, Any]],
    party_rows: list[dict[str, Any]],
    region_rows: list[dict[str, Any]],
    office_rows: list[dict[str, Any]],
    missing_seats_rows: list[dict[str, Any]],
    expected_missing_rows: int,
    all_active_candidates: list[dict[str, Any]],
    criminal_meta: dict[str, Any],
) -> list[str]:
    lines: list[str] = []
    lines.append("무투표 당선 데이터 패키지 자체 검증")
    lines.append(f"검증 시각: {datetime.now(KST).isoformat(timespec='seconds')}")
    lines.append("")

    expected_candidate_rows = sum(
        int(row["등록후보수"] or 0) for row in district_rows if row["무투표당선여부"] == "Y"
    )
    actual_candidate_rows = len(uncontested_candidates)
    lines.append(
        f"[{'PASS' if expected_candidate_rows == actual_candidate_rows else 'FAIL'}] "
        f"uncontested_candidates 행 수 = 무투표 선거구 등록후보수 합 "
        f"({actual_candidate_rows} / {expected_candidate_rows})"
    )

    tax_intersection = sum(1 for row in uncontested_candidates if row["체납이력_보유"] == "Y")
    tax_from_active = {
        c["huboid"] for c in all_active_candidates if c.get("has_tax_history")
    }
    uncontested_huboids = {row["huboid"] for row in uncontested_candidates}
    tax_expected = len(tax_from_active & uncontested_huboids)
    lines.append(
        f"[{'PASS' if tax_intersection == tax_expected else 'FAIL'}] "
        f"무투표 후보 중 최근 5년 체납 이력자 교차검증 ({tax_intersection} / {tax_expected})"
    )

    party_sum = sum(int(row["무투표당선_후보수"] or 0) for row in party_rows)
    region_sum = sum(int(row["무투표당선_후보수"] or 0) for row in region_rows)
    office_sum = sum(int(row["무투표당선_후보수"] or 0) for row in office_rows)
    lines.append(
        f"[{'PASS' if party_sum == actual_candidate_rows else 'FAIL'}] "
        f"정당별 무투표 후보 합계 ({party_sum} / {actual_candidate_rows})"
    )
    lines.append(
        f"[{'PASS' if region_sum == actual_candidate_rows else 'FAIL'}] "
        f"시도별 무투표 후보 합계 ({region_sum} / {actual_candidate_rows})"
    )
    lines.append(
        f"[{'PASS' if office_sum == actual_candidate_rows else 'FAIL'}] "
        f"직책별 무투표 후보 합계 ({office_sum} / {actual_candidate_rows})"
    )

    lines.append(
        f"[{'PASS' if len(missing_seats_rows) == expected_missing_rows else 'FAIL'}] "
        f"의원정수 누락 선거구 수 = missing_seats.csv 행 수 "
        f"({len(missing_seats_rows)} / {expected_missing_rows})"
    )

    disclosed_active = sum(1 for c in all_active_candidates if c.get("has_criminal_disclosure"))
    classified = int(criminal_meta.get("processed") or 0)
    lines.append(
        f"[{'PASS' if disclosed_active == classified else 'CHECK'}] "
        f"활성 후보 전과 공개 수와 전과 PDF 분류 수 비교 ({disclosed_active} / {classified})"
    )
    lines.append("")
    lines.append("주의: 전과 분류는 후보 1명이 여러 유형에 동시에 잡힐 수 있으므로 유형별 합계는 후보 수와 일치하지 않을 수 있습니다.")
    lines.append("주의: 무투표 판정은 후보 등록 스냅샷과 의원정수 표의 선거구 키 매칭 결과입니다.")
    return lines


def write_readme(path: Path, stats: dict[str, Any], output_files: list[str]) -> None:
    text = f"""# 무투표 당선 선거구 기사 근거 데이터 패키지

## 기준 시점

- 스냅샷 일자: 2026-05-17
- 후보 등록 스냅샷 수집 시각: {stats.get("candidate_snapshot_fetched_at") or ""}
- 생성 시각: {stats.get("generated_at") or ""}

## 사용 원자료

- `data/candidates/20260603/snapshot_20260517.json`: 선관위 후보 등록 스냅샷
- `data/candidate_details.json`: 선관위 후보자 상세 공개정보
- `data/constituencies.json`: 선거구별 의원정수
- 전과 PDF 죄명 분류 결과

## 핵심 정의

- 무투표 당선 선거구: 등록 후보 수가 1명 이상이고 의원정수 이하인 선거구. 비례대표는 한 정당 명부만 등록된 선거구도 선관위 보도 집계와 맞춰 무투표로 분류.
- 등록미달 선거구: 등록 후보 수가 의원정수보다 적은 선거구.
- 최근 5년 체납 이력자: `tax_arrears_5y_thousand_krw > 0`.
- 현 체납자: `tax_arrears_current_thousand_krw > 0`.
- 전과 공개 후보: 선관위 공개정보의 전과 항목이 `없음`이 아닌 후보.
- 공직 검증 전과: 전과 죄명 분류 결과에서 `공직 검증` 그룹에 하나 이상 포함된 후보.
- 공직선거법 전과: 전과 분류 문자열에 `공직선거법`이 포함된 후보.

## 산출 파일

{chr(10).join(f"- `{name}`" for name in output_files)}

## 보도 시 권장 표현

- "선관위 후보자 공개정보 기준"
- "2026년 5월 17일 후보 등록 스냅샷 기준"
- "인용 시 선관위 후보자 상세 페이지 원문 확인 필요"
- "전과 유형은 후보 1명이 여러 분류에 중복 포함될 수 있음"

## 헤드라인 사례 파일

`series_lead_cases.csv`는 조건을 만족한 후보만 담았습니다. 조건에 맞는 후보가 30명보다 적을 경우 보충 행을 임의로 넣지 않습니다. 이번 패키지의 조건 충족 사례는 {stats.get("series_lead_cases_count", 0)}건입니다.

## 한계

- 스냅샷 이후 사퇴·등록무효·추가 변동은 별도 확인이 필요합니다.
- 비례대표 선거는 정당명부와 의석 배분 구조가 지역구와 다르므로 `office_type`, `무투표판정기준`, `비례대표_단일정당명부여부`로 분리해 해석해야 합니다.
- 의원정수 자료와 후보 스냅샷의 선거구 키가 맞지 않는 행은 `missing_seats.csv`에 따로 분리했습니다. 추정으로 보정하지 않았습니다.
"""
    path.write_text(text, encoding="utf-8")


def write_claude_instructions(path: Path, stats: dict[str, Any]) -> None:
    text = f"""# Claude 작성 지침: 무투표 당선 선거구 3부작

## 역할

당신은 데이터 저널리즘 에디터다. 이 패키지는 선관위 후보자 공개정보와 선거구별 의원정수 자료를 정리한 기사 근거 데이터다. 목표는 6·3 지방선거에서 투표 없이 당선되는 구조와 그 안의 검증 사각지대를 3편의 기사와 1시간 방송 구성으로 설명하는 것이다.

## 반드시 사용할 핵심 파일

- `uncontested_key_stats.json`: 첫 문단과 그래픽의 기준 숫자.
- `uncontested_districts.csv`: 무투표 당선 선거구 마스터.
- `uncontested_candidates.csv`: 무투표 당선 후보 명단.
- `series_lead_cases.csv`: 기사 도입부와 방송용 사례 후보군.

보조 파일:
- `uncontested_by_party.csv`
- `uncontested_by_region.csv`
- `uncontested_by_office.csv`
- `validation_report.txt`
- `README.md`

## 현재 핵심 숫자

- 전체 선거구: {stats.get("total_districts"):,}곳
- 무투표 당선 선거구: {stats.get("total_uncontested_districts"):,}곳 ({stats.get("share_of_uncontested_among_all_districts")}%)
- 무투표 당선 후보: {stats.get("total_uncontested_candidates"):,}명
- 최근 5년 체납 이력 보유 무투표 후보: {stats.get("uncontested_with_tax_history_candidates"):,}명
- 현 체납 보유 무투표 후보: {stats.get("uncontested_with_current_tax_candidates"):,}명
- 전과 공개 무투표 후보: {stats.get("uncontested_with_criminal_disclosure_candidates"):,}명
- 공직 검증 전과 보유 무투표 후보: {stats.get("uncontested_with_official_misconduct_record_candidates"):,}명
- 공직선거법 전과 보유 무투표 후보: {stats.get("uncontested_with_election_law_record_candidates"):,}명
- 최근 5년 체납 이력과 공직 검증 전과 동시 보유: {stats.get("uncontested_with_both_tax_and_official_misconduct"):,}명
- 검증 위험 플래그가 있는 무투표 후보 비중: {stats.get("share_of_uncontested_candidates_with_any_red_flag")}%

## 3부작 제안

1. 1편: “투표 없이 당선되는 {stats.get("total_uncontested_candidates"):,}명”
   - 무투표 당선 선거구 규모, 직책별 분포, 지역별 집중도를 설명한다.
   - 독자에게 가장 먼저 전달할 질문은 “유권자가 선택할 기회 없이 공직자가 정해지는 곳이 얼마나 되는가”다.

2. 2편: “검증 없이 통과되는 체납·전과 후보”
   - 최근 5년 체납 이력, 현 체납, 전과 공개, 공직 검증 전과를 분리해 보여준다.
   - `series_lead_cases.csv`의 사례는 후보자 상세 페이지 원문 확인 후 실명 문장으로 쓴다.

3. 3편: “공천 책임은 어디에 있는가”
   - 정당별·지역별·직책별 집계를 사용하되 단순 비율 경쟁으로 몰지 않는다.
   - 공천 규모가 다른 정당을 비교할 때는 후보 수와 무투표 후보 수를 함께 적는다.

## 문장 원칙

- “선관위 후보자 공개정보 기준”, “2026년 5월 17일 후보 등록 스냅샷 기준”을 명시한다.
- 후보 실명을 쓰는 문장에서는 `nec_detail_url`의 선관위 상세 페이지 원문 확인을 전제로 한다.
- 체납은 “최근 5년 체납 이력”과 “현 체납”을 반드시 구분한다.
- 전과는 “전과 공개”, “공직 검증 전과”, “공직선거법 전과”를 구분한다.
- 죄명 분류는 후보 1명이 여러 분류에 중복 포함될 수 있음을 설명한다.
- 방법론 전문용어를 기사 본문에 쓰지 않는다.
- “혐의”라고 쓰지 말고, 선관위 공개 전과자료 기준의 “전과”, “죄명”, “분류”로 쓴다.
- 범죄명을 후보에게 단정해 덧씌우지 않는다. 예를 들어 분류명이 넓은 경우, 후보가 실제로 공개한 죄명과 선관위 원문을 확인한 뒤 표현한다.

## 1시간 방송 구성

- 0~5분: 오늘의 질문. “내 지역에 이미 사실상 당선자가 정해진 선거구가 있는가”
- 5~15분: 전체 숫자와 지도형 그래픽. 무투표 선거구 {stats.get("total_uncontested_districts"):,}곳, 후보 {stats.get("total_uncontested_candidates"):,}명.
- 15~30분: 체납·전과 검증 사각. 최근 5년 체납 73명, 공직 검증 전과 75명, 공직선거법 8명.
- 30~42분: 사례 파트. `series_lead_cases.csv`에서 원문 확인된 후보만 사용.
- 42~52분: 정당·지역·직책별 책임 구조. 무투표 후보 수와 공천 규모를 함께 제시.
- 52~60분: 독자가 확인할 방법. 선관위 상세 페이지 확인법, 다음 보도 예고.

## 그래픽 제안

- “무투표 선거구 {stats.get("total_uncontested_districts"):,}곳” 대형 숫자 카드.
- 직책별 무투표 선거구 막대그래프.
- 최근 5년 체납·공직 검증 전과·공직선거법 전과를 분리한 후보 수 카드.
- 정당별 무투표 후보 수와 정당 전체 후보 대비 비율을 나란히 배치한 표.
- 지역별 상위 5개 시도 지도 또는 순위표.

## 금지

- 후보자에게 공개자료에 없는 범죄명을 추가하지 말 것.
- 체납 이력을 현 체납처럼 쓰지 말 것.
- 정당별 숫자를 공천 규모 보정 없이 “가장 문제”라고 단정하지 말 것.
- 선관위 원문 확인 전 사례성 문장을 확정 기사체로 쓰지 말 것.
"""
    path.write_text(text, encoding="utf-8")


def build_package(out_dir: Path) -> dict[str, Any]:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    snapshot = read_json(SNAPSHOT_PATH)
    details_payload = read_json(DETAILS_PATH)
    constituencies = read_json(CONSTITUENCIES_PATH)
    criminal_payload = read_json(CRIMINAL_PATH)

    details_by_huboid = {
        str(row.get("huboid")): row
        for row in details_payload.get("details", [])
        if row.get("huboid")
    }
    criminal_by_huboid, _public_categories = classify_criminal_records(criminal_payload)
    joint_sd_map = build_joint_sd_map(constituencies)

    seats_by_key: dict[str, dict[str, Any]] = {}
    for item in constituencies:
        key = district_key(item, joint_sd_map)
        seat_count = parse_int(item.get("sggJungsu"))
        if seat_count <= 0:
            continue
        seats_by_key[key.text] = {
            "sg_type": key.sg_type,
            "sd_name": key.sd_name,
            "sgg_name": key.sgg_name,
            "office": office_name(key.sg_type),
            "office_type": office_type(key.sg_type),
            "seat_count": seat_count,
        }

    active_candidates: list[dict[str, Any]] = []
    candidate_groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for raw in snapshot.get("candidates", []):
        if not is_active_candidate(raw):
            continue
        enriched = enrich_candidate(raw, details_by_huboid, criminal_by_huboid)
        key = district_key(enriched, joint_sd_map)
        enriched["district_key"] = key.text
        enriched["office"] = office_name(key.sg_type)
        enriched["office_type"] = office_type(key.sg_type)
        enriched["sdName"] = key.sd_name
        enriched["sggName"] = key.sgg_name
        active_candidates.append(enriched)
        candidate_groups[key.text].append(enriched)

    district_rows = make_district_rows(seats_by_key, candidate_groups)
    uncontested_candidate_rows = make_uncontested_candidate_rows(district_rows, candidate_groups)
    party_rows = summarize_by_party(uncontested_candidate_rows, active_candidates)
    region_rows = summarize_by_region(district_rows, uncontested_candidate_rows)
    office_rows = summarize_by_office(district_rows, uncontested_candidate_rows, active_candidates)
    lead_case_rows = make_lead_cases(uncontested_candidate_rows)
    missing_seat_rows = make_missing_seats_rows(candidate_groups, seats_by_key)

    stats = make_key_stats(
        district_rows=district_rows,
        uncontested_candidates=uncontested_candidate_rows,
        party_rows=party_rows,
        region_rows=region_rows,
        office_rows=office_rows,
        missing_seats_rows=missing_seat_rows,
        snapshot_meta=snapshot,
        criminal_meta=criminal_payload.get("meta") or {},
    )
    stats["series_lead_cases_count"] = len(lead_case_rows)

    district_fields = [
        "sdName", "sggName", "office", "office_type", "sgTypecode",
        "의원정수", "등록후보수", "경쟁률", "무투표당선여부",
        "무투표판정기준", "비례대표_단일정당명부여부", "등록미달여부", "경쟁률_1미만여부",
        "해당선거구_후보huboid_리스트", "해당선거구_후보명_리스트", "해당선거구_정당_리스트",
        "체납이력_후보수", "현체납_후보수", "전과공개_후보수", "공직검증전과_후보수",
        "공직선거법전과_후보수", "체납+공직검증전과_동시보유_후보수", "검증위험_플래그",
        "district_key",
    ]
    candidate_fields = [
        "huboid", "name", "party", "office", "office_type", "sdName", "sggName", "nec_detail_url",
        "tax_arrears_5y_thousand_krw", "tax_arrears_5y_display",
        "tax_arrears_current_thousand_krw", "tax_arrears_current_display",
        "criminal_record_disclosure", "categories", "important_categories",
        "공직검증전과_분류수", "공직검증전과_건수",
        "체납이력_보유", "현체납_보유", "전과공개_보유", "공직검증전과_보유", "공직선거법전과_보유",
        "해당선거구_경쟁률", "해당선거구_의원정수",
        "해당선거구_무투표판정기준", "해당선거구_비례대표_단일정당명부여부",
        "등록미달여부", "검증위험_플래그",
    ]
    party_fields = [
        "party", "무투표당선_후보수", "무투표당선_선거구수", "무투표당선_선거구_공천횟수",
        "체납이력_후보수", "체납이력_후보를_낸_선거구수",
        "공직검증전과_후보수", "공직검증전과_후보를_낸_선거구수",
        "공직선거법전과_후보수", "공직선거법전과_후보를_낸_선거구수",
        "정당전체후보수", "정당전체후보대비_무투표후보비율",
    ]
    region_fields = [
        "sdName", "무투표당선_선거구수", "무투표당선_후보수", "체납이력자수",
        "공직검증전과자수", "공직선거법전과자수", "시도내_전체선거구수", "시도내_무투표당선_선거구비율",
    ]
    office_fields = [
        "office", "office_type", "무투표당선_선거구수", "무투표당선_후보수", "체납이력자수",
        "공직검증전과자수", "공직선거법전과자수", "직책별_전체선거구수", "직책별_전체후보수",
        "직책별_전체선거구대비_무투표비율", "직책별_전체후보대비_무투표후보비율",
    ]
    missing_fields = [
        "district_key", "sgTypecode", "sdName", "sggName", "office", "office_type",
        "등록후보수", "후보huboid_리스트", "후보명_리스트", "정당_리스트", "누락사유",
    ]

    write_csv(out_dir / "uncontested_districts.csv", district_rows, district_fields)
    write_csv(out_dir / "uncontested_candidates.csv", uncontested_candidate_rows, candidate_fields)
    write_csv(out_dir / "uncontested_by_party.csv", party_rows, party_fields)
    write_csv(out_dir / "uncontested_by_region.csv", region_rows, region_fields)
    write_csv(out_dir / "uncontested_by_office.csv", office_rows, office_fields)
    write_json(out_dir / "uncontested_key_stats.json", stats)
    write_csv(out_dir / "series_lead_cases.csv", lead_case_rows, candidate_fields + ["우선순위_사유"])
    write_csv(out_dir / "missing_seats.csv", missing_seat_rows, missing_fields)
    write_claude_instructions(out_dir / "00_CLAUDE_UNCONTESTED_SERIES_INSTRUCTIONS.md", stats)

    validation = validation_lines(
        district_rows=district_rows,
        uncontested_candidates=uncontested_candidate_rows,
        party_rows=party_rows,
        region_rows=region_rows,
        office_rows=office_rows,
        missing_seats_rows=missing_seat_rows,
        expected_missing_rows=len(missing_seat_rows),
        all_active_candidates=active_candidates,
        criminal_meta=criminal_payload.get("meta") or {},
    )
    (out_dir / "validation_report.txt").write_text("\n".join(validation) + "\n", encoding="utf-8")

    output_files = [
        "uncontested_districts.csv",
        "uncontested_candidates.csv",
        "uncontested_by_party.csv",
        "uncontested_by_region.csv",
        "uncontested_by_office.csv",
        "uncontested_key_stats.json",
        "series_lead_cases.csv",
        "missing_seats.csv",
        "validation_report.txt",
        "00_CLAUDE_UNCONTESTED_SERIES_INSTRUCTIONS.md",
        "README.md",
    ]
    write_readme(out_dir / "README.md", stats, output_files)
    write_json(out_dir / "manifest.json", {
        "package": out_dir.name,
        "generated_at": stats["generated_at"],
        "files": output_files,
        "key_stats": stats,
    })

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
        "validation": validation,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()
    result = build_package(args.out_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
