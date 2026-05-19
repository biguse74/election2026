#!/usr/bin/env python3
"""Emergency proportional-list vetting package for May 19 broadcast."""

from __future__ import annotations

import csv
import json
import zipfile
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
SNAPSHOT = ROOT / "data" / "candidates" / "20260603" / "snapshot_20260519.json"
DETAILS = ROOT / "data" / "candidate_details" / "20260603" / "snapshot_20260519.json"
CRIMINAL = ROOT / "data" / "criminal_ocr.json"
CONSTITUENCY_DIR = ROOT / "data" / "codes" / "20260603" / "constituencies"
PERSON_PRIORITY_DIR = ROOT / "exports" / "person_priority_lists_20260519" / "data"

OUT_DIR = ROOT / "exports" / "proportional_nomination_check_20260519"
DATA_DIR = OUT_DIR / "data"
ZIP_PATH = ROOT / "exports" / "proportional_nomination_check_20260519.zip"

KST = timezone(timedelta(hours=9))
MAJOR_PARTIES = ["더불어민주당", "국민의힘"]
ECONOMIC = {"사기", "횡령", "배임", "뇌물"}

KIM_HUBOID = "100165618"
KIM_PDF_URL = "https://info.nec.go.kr/unielec_pdf_file/20260603/open/Gsg4710/Hb100165618/junkwa/20260515134104431_9.PDF"
KIM_DETAIL_URL = "https://info.nec.go.kr/electioninfo/candidate_detail_info.xhtml?electionId=0020260603&huboId=100165618"
KIM_CONFIRMED_OFFENSES = [
    {
        "disposition_date": "1999-10-13",
        "offense_name": "윤락행위등방지법위반",
        "offense_article": "PDF 죄명란에 조항 별도 표기 없음",
        "sentence": "벌금 2,000,000원",
        "before_2004_repeal": "Y",
    },
    {
        "disposition_date": "2000-02-22",
        "offense_name": "윤락행위등방지법위반",
        "offense_article": "PDF 죄명란에 조항 별도 표기 없음",
        "sentence": "벌금 1,000,000원",
        "before_2004_repeal": "Y",
    },
]


def now_kst() -> datetime:
    return datetime.now(KST)


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def parse_int(value: Any) -> int:
    text = str(value or "").replace(",", "").strip()
    digits = "".join(ch for ch in text if ch.isdigit() or ch == "-")
    return int(digits or 0)


def active(candidate: dict[str, Any]) -> bool:
    return not candidate.get("status") or candidate.get("status") == "등록"


def party(candidate: dict[str, Any]) -> str:
    return candidate.get("jdName") or "무소속"


def office_name(sg_type: str) -> str:
    return {"8": "광역의원 비례", "9": "기초의원 비례"}.get(str(sg_type), str(sg_type))


def district_key(row: dict[str, Any]) -> tuple[str, str, str]:
    return str(row.get("sgTypecode") or ""), row.get("sdName") or "", row.get("sggName") or ""


def load_constituency_seats() -> dict[tuple[str, str, str], int]:
    seats: dict[tuple[str, str, str], int] = {}
    for sg_type in ["8", "9"]:
        for row in load_json(CONSTITUENCY_DIR / f"sgType_{sg_type}.json"):
            seats[district_key(row)] = parse_int(row.get("sggJungsu"))
    return seats


def criminal_record_map() -> dict[str, dict[str, Any]]:
    return {
        str(row.get("huboid")): row
        for row in load_json(CRIMINAL).get("records", [])
        if row.get("huboid")
    }


def detail_map() -> dict[str, dict[str, Any]]:
    return {
        str(row.get("huboid")): row
        for row in load_json(DETAILS).get("details", [])
        if row.get("huboid")
    }


def disclosure_criminal_count(text: str) -> int:
    text = str(text or "").strip()
    if not text or text == "없음":
        return 0
    return parse_int(text)


def amount_text(thousand: int) -> str:
    won = thousand * 1000
    if won >= 100_000_000:
        eok = won // 100_000_000
        man = (won % 100_000_000) // 10_000
        return f"{eok:,}억 {man:,}만원" if man else f"{eok:,}억원"
    if won >= 10_000:
        return f"{won // 10_000:,}만원"
    return f"{won:,}원"


def offense_summary(criminal: dict[str, Any]) -> str:
    offenses = criminal.get("offenses") or []
    parts = []
    for offense in offenses[:4]:
        name = offense.get("offense") or ""
        date = offense.get("date") or ""
        sentence = offense.get("sentence") or ""
        bits = [x for x in [name, date, sentence] if x]
        if bits:
            parts.append(" / ".join(bits))
    return "; ".join(parts)


def build_proportional_rows() -> list[dict[str, Any]]:
    snapshot = load_json(SNAPSHOT)
    details = detail_map()
    crimes = criminal_record_map()
    seats = load_constituency_seats()
    rows: list[dict[str, Any]] = []

    for candidate in snapshot["candidates"]:
        if str(candidate.get("sgTypecode")) not in {"8", "9"}:
            continue
        if party(candidate) not in MAJOR_PARTIES:
            continue
        if not active(candidate):
            continue
        huboid = str(candidate.get("huboid") or "")
        detail = details.get(huboid, {})
        disclosure = detail.get("disclosures") or {}
        criminal = crimes.get(huboid, {})
        cats = [str(c) for c in criminal.get("categories", []) if c]
        seq = parse_int(candidate.get("giho"))
        seat_count = seats.get(district_key(candidate), 0)
        tax5 = parse_int(disclosure.get("tax_arrears_5y_thousand_krw"))
        current = parse_int(disclosure.get("tax_arrears_current_thousand_krw"))
        criminal_text = disclosure.get("criminal_record") or criminal.get("criminal_record") or ""
        has_criminal = disclosure_criminal_count(criminal_text) > 0
        has_tax = tax5 > 0 or current > 0
        rows.append({
            "huboid": huboid,
            "name": candidate.get("name") or "",
            "party": party(candidate),
            "sdName": candidate.get("sdName") or "",
            "sggName": candidate.get("sggName") or "",
            "office": office_name(str(candidate.get("sgTypecode"))),
            "sgTypecode": str(candidate.get("sgTypecode") or ""),
            "list_rank": seq,
            "seat_count": seat_count,
            "estimated_electable": "Y" if seq and seat_count and seq <= seat_count else "N",
            "status": candidate.get("status") or "",
            "age": candidate.get("age") or "",
            "birthday": candidate.get("birthday") or "",
            "criminal_record": criminal_text or "없음",
            "has_criminal": "Y" if has_criminal else "N",
            "criminal_categories": "; ".join(cats),
            "offense_summary": offense_summary(criminal),
            "tax_arrears_5y_thousand_krw": tax5,
            "tax_arrears_5y_display": amount_text(tax5) if tax5 else "0원",
            "tax_arrears_current_thousand_krw": current,
            "tax_arrears_current_display": amount_text(current) if current else "0원",
            "has_tax": "Y" if has_tax else "N",
            "economic_trust_record": "Y" if bool(set(cats) & ECONOMIC) else "N",
            "tax_100m_or_more": "Y" if tax5 >= 100_000 or current >= 100_000 else "N",
            "nec_detail_url": detail.get("nec_detail_url") or f"https://info.nec.go.kr/electioninfo/candidate_detail_info.xhtml?electionId=0020260603&huboId={huboid}",
            "criminal_pdf_url": "; ".join(
                f.get("pdf_url") or ""
                for f in (detail.get("scan_files") or {}).get("criminal", [])
                if f.get("pdf_url")
            ),
        })

    rows.sort(key=lambda r: (r["party"], r["sgTypecode"], r["sdName"], r["sggName"], r["list_rank"], r["name"]))
    return rows


def build_kim_confirmation(prop_rows: list[dict[str, Any]]) -> dict[str, Any]:
    kim = next(row for row in prop_rows if row["huboid"] == KIM_HUBOID)
    return {
        "checked_at": now_kst().isoformat(timespec="seconds"),
        "same_person_status": "동일인",
        "same_person_basis": "후보자 기본정보 huboid 100165618, 이름 김장환, 국민의힘, 경상북도 상주시, sgTypecode 9, 나이 69세와 전과 PDF의 비례대표상주시의회의원선거·국민의힘·후보자성명 김장환 표기가 일치",
        "candidate_registration": {
            **{k: kim[k] for k in ["huboid", "name", "party", "sdName", "sggName", "office", "list_rank", "seat_count", "estimated_electable", "age", "birthday", "status"]},
        },
        "offenses_from_pdf": KIM_CONFIRMED_OFFENSES,
        "detail_url": KIM_DETAIL_URL,
        "criminal_pdf_url": KIM_PDF_URL,
        "pdf_cache_image": "data/.criminal_ocr_cache/e5e0e2daebdaef4f_1.jpg",
    }


def build_summary(prop_rows: list[dict[str, Any]]) -> dict[str, Any]:
    total_by_party_type: dict[str, dict[str, int]] = {}
    electable_flags: dict[str, list[dict[str, Any]]] = {p: [] for p in MAJOR_PARTIES}
    electable_criminal: dict[str, list[dict[str, Any]]] = {p: [] for p in MAJOR_PARTIES}
    for party_name in MAJOR_PARTIES:
        party_rows = [r for r in prop_rows if r["party"] == party_name]
        total_by_party_type[party_name] = {
            "광역의원 비례": sum(1 for r in party_rows if r["sgTypecode"] == "8"),
            "기초의원 비례": sum(1 for r in party_rows if r["sgTypecode"] == "9"),
            "total": len(party_rows),
        }
        for row in party_rows:
            if row["estimated_electable"] != "Y":
                continue
            if row["has_criminal"] == "Y" or row["has_tax"] == "Y":
                electable_flags[party_name].append(row)
            if row["has_criminal"] == "Y":
                electable_criminal[party_name].append(row)
    return {
        "total_by_party_type": total_by_party_type,
        "electable_criminal_or_tax_counts": {p: len(v) for p, v in electable_flags.items()},
        "electable_criminal_counts": {p: len(v) for p, v in electable_criminal.items()},
        "electable_flags": electable_flags,
        "electable_criminal": electable_criminal,
    }


def read_priority_rows() -> list[dict[str, Any]]:
    files = [
        ("1억 이상 체납", "priority_tax_100m_candidates.csv"),
        ("성범죄·마약", "priority_sex_drug_candidates.csv"),
        ("사기·횡령·배임·뇌물", "priority_economic_candidates_20.csv"),
    ]
    out: list[dict[str, Any]] = []
    seen_key: set[tuple[str, str]] = set()
    for group, filename in files:
        path = PERSON_PRIORITY_DIR / filename
        with path.open("r", encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                key = (group, str(row.get("huboid") or ""))
                if key in seen_key:
                    continue
                seen_key.add(key)
                row["priority_group"] = group
                out.append(row)
    return out


def build_priority_status(prop_lookup: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    snapshot = {str(r.get("huboid")): r for r in load_json(SNAPSHOT)["candidates"] if r.get("huboid")}
    seats = load_constituency_seats()
    rows: list[dict[str, Any]] = []
    for row in read_priority_rows():
        huboid = str(row.get("huboid") or "")
        candidate = snapshot.get(huboid, {})
        sg_type = str(candidate.get("sgTypecode") or row.get("sgTypecode") or "")
        is_pr = sg_type in {"8", "9"}
        prop = prop_lookup.get(huboid, {})
        seq = parse_int(candidate.get("giho")) if is_pr else 0
        seat_count = seats.get(district_key(candidate), 0) if is_pr and candidate else 0
        rows.append({
            "priority_group": row["priority_group"],
            "huboid": huboid,
            "name": row.get("name") or candidate.get("name") or "",
            "party": candidate.get("jdName") or row.get("party") or "",
            "status": candidate.get("status") or "확인 불가",
            "sdName": candidate.get("sdName") or row.get("sdName") or "",
            "sggName": candidate.get("sggName") or row.get("sggName") or "",
            "sgTypecode": sg_type,
            "office_type_rechecked": "비례" if is_pr else "지역구/단체장/기타",
            "proportional_rank": seq if is_pr else "",
            "seat_count": seat_count if is_pr else "",
            "estimated_electable": prop.get("estimated_electable") or ("Y" if is_pr and seq and seat_count and seq <= seat_count else "N" if is_pr else ""),
            "original_office": row.get("office") or "",
            "criminal_or_tax_summary": row.get("offense_summary") or row.get("tax_5y_display") or row.get("tax_type") or "",
        })
    rows.sort(key=lambda r: (r["priority_group"], r["party"], r["sdName"], r["sggName"], r["name"]))
    return rows


def build_denominator_status() -> list[dict[str, Any]]:
    rows = load_json(SNAPSHOT)["candidates"]
    out: list[dict[str, Any]] = []
    for party_name in MAJOR_PARTIES:
        party_rows = [r for r in rows if party(r) == party_name]
        status_counts = Counter(r.get("status") or "" for r in party_rows)
        active_count = sum(1 for r in party_rows if active(r))
        out.append({
            "party": party_name,
            "candidate_rows_in_latest_snapshot": len(party_rows),
            "active_registered_candidates": active_count,
            "withdrawn_candidates": status_counts.get("사퇴", 0),
            "invalidated_candidates": status_counts.get("등록무효", 0),
            "status_breakdown": "; ".join(f"{k or '빈값'} {v}" for k, v in sorted(status_counts.items())),
            "note": "2026-05-19 스냅샷 기준. 기존 3,214/2,744는 사퇴·등록무효 반영 전 후보 행 수와 일치",
        })
    return out


def md_list(rows: list[dict[str, Any]], limit: int = 30) -> str:
    if not rows:
        return "- 없음"
    lines = []
    for i, row in enumerate(rows[:limit], start=1):
        flag = []
        if row["has_criminal"] == "Y":
            flag.append(f"전과 {row['criminal_record']} {row['criminal_categories'] or row['offense_summary']}".strip())
        if row["has_tax"] == "Y":
            flag.append(f"체납 최근5년 {row['tax_arrears_5y_display']}, 현 {row['tax_arrears_current_display']}")
        lines.append(
            f"{i}. {row['name']} | {row['party']} | {row['sdName']} {row['sggName']} {row['office']} "
            f"{row['list_rank']}순위/{row['seat_count']}명 | {'; '.join(flag)} | {row['nec_detail_url']}"
        )
    if len(rows) > limit:
        lines.append(f"- 외 {len(rows) - limit}명은 CSV 참조")
    return "\n".join(lines)


def build_markdown(kim: dict[str, Any], summary: dict[str, Any], denom: list[dict[str, Any]]) -> str:
    t = summary["total_by_party_type"]
    flags = summary["electable_flags"]
    criminal = summary["electable_criminal"]
    kim_reg = kim["candidate_registration"]
    offenses = "\n".join(
        f"- {o['disposition_date']} | {o['offense_name']} | {o['sentence']} | 조항: {o['offense_article']}"
        for o in kim["offenses_from_pdf"]
    )
    denom_lines = "\n".join(
        f"- {row['party']}: 후보 행 {row['candidate_rows_in_latest_snapshot']:,}명, 등록 유지 {row['active_registered_candidates']:,}명, "
        f"사퇴 {row['withdrawn_candidates']}명, 등록무효 {row['invalidated_candidates']}명"
        for row in denom
    )
    return f"""# 김장환 1차 확인 + 비례 명부 전수

확인 시각: {now_kst().strftime('%Y-%m-%d %H:%M:%S KST')}
기준: 선관위 후보자 공개정보 2026-05-19 스냅샷 및 후보자 상세 전과 PDF 원문.

## 김장환 1차 확정

- 동명이인 여부: 동일인
- 후보 등록: 경북 상주시 기초의원 비례 {kim_reg['list_rank']}순위, 국민의힘, 나이 {kim_reg['age']}세, 상태 {kim_reg['status']}
- 선출 인원: {kim_reg['seat_count']}명
- 순번 ≤ 선출 인원 기준 당선 추정권: {kim_reg['estimated_electable']}
- 선관위 후보자 상세 페이지: {kim['detail_url']}
- 전과 PDF: {kim['criminal_pdf_url']}

### PDF 원문 확인 전과

{offenses}

처분일자는 모두 윤락행위방지법 폐지(2004년) 이전이다. 사건 발생일은 PDF에 별도 표기되지 않아 처분일자 기준으로만 확인했다.

## 비례 명부 전수 분석

### 양당 비례 후보 총 인원

- 민주 비례: 광역 {t['더불어민주당']['광역의원 비례']}명 + 기초 {t['더불어민주당']['기초의원 비례']}명 = {t['더불어민주당']['total']}명
- 국힘 비례: 광역 {t['국민의힘']['광역의원 비례']}명 + 기초 {t['국민의힘']['기초의원 비례']}명 = {t['국민의힘']['total']}명

### 당선 추정권 안 전과·체납 신고 후보

- 민주: {len(flags['더불어민주당'])}명
- 국힘: {len(flags['국민의힘'])}명

#### 민주
{md_list(flags['더불어민주당'])}

#### 국힘
{md_list(flags['국민의힘'])}

## 김장환과 같은 사례: 전과 신고 후보가 당선 추정권 비례 순번

- 민주: {len(criminal['더불어민주당'])}명
- 국힘: {len(criminal['국민의힘'])}명

#### 민주 전과 사례
{md_list(criminal['더불어민주당'])}

#### 국힘 전과 사례
{md_list(criminal['국민의힘'])}

## 분모 재계산

{denom_lines}

기존 패키지의 민주 3,214명·국힘 2,744명은 후보 행 기준이다. 2026-05-19 최신 스냅샷에서 등록 유지 후보만 분모로 잡으면 민주 3,213명, 국힘 2,742명이다.

## 산출 파일

- `data/kim_janghwan_confirmation.json`
- `data/proportional_candidates_major_parties.csv`
- `data/proportional_electable_criminal_or_tax.csv`
- `data/proportional_electable_criminal.csv`
- `data/priority_40_status_recheck.csv`
- `data/denominator_recheck_20260519.csv`
"""


def main() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    prop_rows = build_proportional_rows()
    prop_lookup = {row["huboid"]: row for row in prop_rows}
    kim = build_kim_confirmation(prop_rows)
    summary = build_summary(prop_rows)
    electable_flags = summary["electable_flags"]["더불어민주당"] + summary["electable_flags"]["국민의힘"]
    electable_criminal = summary["electable_criminal"]["더불어민주당"] + summary["electable_criminal"]["국민의힘"]
    priority_status = build_priority_status(prop_lookup)
    denom = build_denominator_status()

    prop_fields = [
        "huboid", "name", "party", "sdName", "sggName", "office", "sgTypecode",
        "list_rank", "seat_count", "estimated_electable", "status", "age", "birthday",
        "criminal_record", "has_criminal", "criminal_categories", "offense_summary",
        "tax_arrears_5y_thousand_krw", "tax_arrears_5y_display",
        "tax_arrears_current_thousand_krw", "tax_arrears_current_display", "has_tax",
        "economic_trust_record", "tax_100m_or_more", "nec_detail_url", "criminal_pdf_url",
    ]
    write_csv(DATA_DIR / "proportional_candidates_major_parties.csv", prop_rows, prop_fields)
    write_csv(DATA_DIR / "proportional_electable_criminal_or_tax.csv", electable_flags, prop_fields)
    write_csv(DATA_DIR / "proportional_electable_criminal.csv", electable_criminal, prop_fields)
    write_csv(
        DATA_DIR / "priority_40_status_recheck.csv",
        priority_status,
        [
            "priority_group", "huboid", "name", "party", "status", "sdName", "sggName",
            "sgTypecode", "office_type_rechecked", "proportional_rank", "seat_count",
            "estimated_electable", "original_office", "criminal_or_tax_summary",
        ],
    )
    write_csv(
        DATA_DIR / "denominator_recheck_20260519.csv",
        denom,
        [
            "party", "candidate_rows_in_latest_snapshot", "active_registered_candidates",
            "withdrawn_candidates", "invalidated_candidates", "status_breakdown", "note",
        ],
    )
    write_json(DATA_DIR / "kim_janghwan_confirmation.json", kim)
    write_json(
        DATA_DIR / "key_stats.json",
        {
            "checked_at": now_kst().isoformat(timespec="seconds"),
            "kim_janghwan": kim,
            "proportional_summary": {
                "total_by_party_type": summary["total_by_party_type"],
                "electable_criminal_or_tax_counts": summary["electable_criminal_or_tax_counts"],
                "electable_criminal_counts": summary["electable_criminal_counts"],
            },
            "denominator_recheck": denom,
        },
    )
    (OUT_DIR / "CLAUDE_PROPORTIONAL_NOMINATION_CHECK_20260519.md").write_text(
        build_markdown(kim, summary, denom),
        encoding="utf-8",
    )

    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in OUT_DIR.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(OUT_DIR.parent))

    print(f"written: {OUT_DIR.relative_to(ROOT)}")
    print(f"zip: {ZIP_PATH.relative_to(ROOT)}")
    print(f"kim: rank {kim['candidate_registration']['list_rank']} / seats {kim['candidate_registration']['seat_count']}")
    print(f"electable criminal/tax: 민주 {summary['electable_criminal_or_tax_counts']['더불어민주당']}, 국힘 {summary['electable_criminal_or_tax_counts']['국민의힘']}")
    print(f"electable criminal: 민주 {summary['electable_criminal_counts']['더불어민주당']}, 국힘 {summary['electable_criminal_counts']['국민의힘']}")


if __name__ == "__main__":
    main()
