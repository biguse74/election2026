#!/usr/bin/env python3
"""Export hand-checked offense rows for the 10 uncontested candidates flagged for fraud/embezzlement/breach/bribery."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
import shutil
import zipfile
from collections import defaultdict
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
KST = timezone(timedelta(hours=9))
REFERENCE_DATE = date(2026, 6, 3)

SOURCE_PACKAGE = ROOT / "exports" / "uncontested_series_package_20260517_0900"
UNCONTESTED_CANDIDATES = SOURCE_PACKAGE / "uncontested_candidates.csv"
CRIMINAL_JSON = ROOT / "data" / "criminal_ocr.json"
PDF_CACHE_DIR = ROOT / "data" / ".criminal_ocr_cache"
DEFAULT_OUT_DIR = ROOT / "exports" / "top10_offense_details_20260517_1230"

TARGET_CATEGORIES = {"사기", "횡령", "배임", "뇌물"}


MANUAL_OFFENSES: dict[str, list[dict[str, str]]] = {
    "100154075": [
        {"offense": "사기", "result": "벌금1.500.000원", "date": "2004.07.14"},
    ],
    "100156458": [
        {
            "offense": "허위공문서작성\n허위작성공문서행사\n업무상배임\n특정경제범죄가중처벌등에관한\n법률위반(배임)",
            "result": "징역2년, 집행유예3년",
            "date": "2006/08/17",
        },
    ],
    "100160386": [
        {"offense": "도로교통법위반\n(음주운전)", "result": "벌금1,500,000원", "date": "2012.06.07."},
        {"offense": "업무상 횡령", "result": "징역 6월, 집행유예 1년", "date": "2019.02.08."},
    ],
    "100160943": [
        {
            "offense": "농지의보전및이용에관한법률위반\n수산업법위반\n건축법위반",
            "result": "벌금 1,000,000원",
            "date": "1992.12.11",
        },
        {"offense": "수산업법위반", "result": "벌금 1,000,000원", "date": "1995.02.23"},
        {"offense": "대기환경보전법위반", "result": "벌금 1,000,000원", "date": "1997.05.06"},
        {"offense": "배임\n특수공무집행방해", "result": "징역1년6월\n집행유예 2년", "date": "2001.11.23"},
        {"offense": "배임", "result": "징역 6월\n집행유예 1년", "date": "2007.08.23"},
        {"offense": "국토의계획및이용에관한법률위반", "result": "벌금 5,000,000원", "date": "2022.09.15"},
        {"offense": "국토의계획및이용에관한법률위반", "result": "벌금 3,000,000원", "date": "2023.07.07"},
    ],
    "100161391": [
        {"offense": "뇌물공여 변호사법위반", "result": "벌금 2,000,000원", "date": "1990.4.24."},
        {"offense": "폭력행위등처벌에관한법률위반", "result": "벌금 1,000,000원", "date": "1999.11.10."},
        {
            "offense": "공정증서원본불실기재 불실기재\n공정증서원본행사 상법위반",
            "result": "벌금 5,000,000원",
            "date": "2003.10.6.",
        },
    ],
    "100161815": [
        {"offense": "사문서위조, 위조사문서행사,\n사기", "result": "벌금 2,000,000원", "date": "2002.12.28."},
        {"offense": "뇌물공여", "result": "벌금 3,000,000원", "date": "2011.8.24."},
        {"offense": "사기", "result": "벌금 1,500,000원", "date": "2016.11.25."},
    ],
    "100162708": [
        {"offense": "업무방해", "result": "징역6월, 집행유예2년", "date": "1989.11.23"},
        {
            "offense": "교통사고처리특례법위반\n도로교통법위반(음주운전)",
            "result": "벌금 2,500,000원",
            "date": "2001.03.12",
        },
        {
            "offense": "공정증서원본불실기재\n불실기재공정증서원본행사\n업무상횡령\n배임증재\n상법위반\n건설산업기본법위반\n골재채취법위반",
            "result": "징역1년, 집행유예2년",
            "date": "2007.6.21",
        },
        {"offense": "도로교통법위반(음주운전)", "result": "벌금 2,000,000원", "date": "2017.03.14"},
    ],
    "100163388": [
        {"offense": "도로교통법위반(음주운전)", "result": "벌금 4,000,000원", "date": "2015/04/22"},
        {"offense": "사기", "result": "벌금 1,000,000원", "date": "2016/12/21"},
    ],
    "100163407": [
        {"offense": "폭력행위등처벌에 관한법률위반\n도로교통법위반", "result": "벌금 1,500,000원", "date": "1994.7.14"},
        {"offense": "업무상횡령", "result": "벌금 1,000,000원", "date": "2002.5.13"},
    ],
    "100164219": [
        {"offense": "도로교통법위반", "result": "벌금 1,000,000", "date": "2003.3.28."},
        {"offense": "도로교통법위반(음주운전)", "result": "벌금 3,000,000", "date": "2013.12.16."},
        {"offense": "사기", "result": "벌금 3,000,000", "date": "2023.4.19."},
    ],
}


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def url_key(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


def safe_filename(text: str) -> str:
    return re.sub(r'[\\/:*?"<>|\\s]+', "_", text).strip("_")


def normalize_offense_name(text: str) -> str:
    normalized = re.sub(r"\s+", " ", text.replace("\r", "\n")).strip()
    normalized = normalized.replace(" 관한법률", " 관한 법률")
    normalized = normalized.replace("법률위반", "법률위반")
    return normalized


def parse_date(raw: str) -> str:
    nums = re.findall(r"\d+", raw or "")
    if len(nums) < 3:
        return ""
    year, month, day = int(nums[0]), int(nums[1]), int(nums[2])
    if year < 100:
        return ""
    try:
        return date(year, month, day).isoformat()
    except ValueError:
        return ""


def years_since(iso_date: str) -> str:
    if not iso_date:
        return ""
    d = date.fromisoformat(iso_date)
    return f"{(REFERENCE_DATE - d).days / 365.2425:.2f}"


def parse_months(text: str, prefix: str | None = None) -> int | None:
    source = text.replace(" ", "")
    if prefix:
        match = re.search(prefix + r"(?:(\d+)년)?(?:(\d+)월)?", source)
    else:
        match = re.search(r"(?:(\d+)년)?(?:(\d+)월)", source)
    if not match:
        return None
    years = int(match.group(1) or 0)
    months = int(match.group(2) or 0)
    total = years * 12 + months
    return total or None


def disposition_result_type(raw: str) -> str:
    if "집행유예" in raw:
        return "집행유예"
    if "징역" in raw:
        return "징역"
    if "금고" in raw:
        return "금고"
    if "선고유예" in raw:
        return "선고유예"
    if "기소유예" in raw:
        return "기소유예"
    if "벌금" in raw:
        return "벌금"
    return "기타"


def fine_krw(raw: str) -> int | None:
    if "벌금" not in raw:
        return None
    numbers = re.findall(r"\d[\d,.]*", raw)
    if not numbers:
        return None
    return int(re.sub(r"\D", "", numbers[0]))


def amount_or_term(raw: str, result_type: str) -> str:
    if result_type == "벌금":
        value = fine_krw(raw)
        return str(value) if value is not None else ""
    if result_type == "집행유예":
        suspended = parse_months(raw, "집행유예")
        return str(suspended) if suspended is not None else ""
    if result_type in {"징역", "금고"}:
        months = parse_months(raw, result_type)
        return str(months) if months is not None else ""
    return ""


def match_categories(offense: str) -> list[str]:
    flat = re.sub(r"\s+", "", offense)
    matches: list[str] = []
    checks = [
        ("사기", ["사기"]),
        ("횡령", ["횡령"]),
        ("배임", ["배임"]),
        ("뇌물", ["뇌물", "수뢰", "알선수재"]),
        ("공직선거법", ["공직선거법"]),
        ("음주·위험운전", ["음주운전", "위험운전치사상"]),
        ("무면허운전", ["무면허운전"]),
        ("교통사고", ["교통사고처리특례법", "교통사고처리특례"]),
        ("도로교통", ["도로교통법"]),
        ("허위공문서·문서위조·공용서류", ["허위공문서", "허위작성공문서", "공정증서원본불실기재", "사문서위조", "위조사문서"]),
        ("건축·건설·부동산", ["건축법", "건설산업기본법", "골재채취법", "국토의계획및이용에관한법률"]),
        ("공무집행방해", ["공무집행방해"]),
        ("업무방해", ["업무방해"]),
        ("폭력", ["폭력행위", "폭행", "상해"]),
        ("농수산", ["농지", "수산업법"]),
        ("환경", ["대기환경보전법", "환경"]),
    ]
    for category, terms in checks:
        if category == "도로교통" and "음주운전" in flat:
            continue
        if any(term in flat for term in terms):
            matches.append(category)
    return matches


def candidate_targets() -> list[dict[str, str]]:
    rows = read_csv(UNCONTESTED_CANDIDATES)
    targets = [
        r for r in rows
        if any(category in (r.get("important_categories") or "") for category in TARGET_CATEGORIES)
    ]
    if len(targets) != 10:
        raise RuntimeError(f"target count mismatch: expected 10, got {len(targets)}")
    manual_missing = sorted({r["huboid"] for r in targets} - set(MANUAL_OFFENSES))
    manual_extra = sorted(set(MANUAL_OFFENSES) - {r["huboid"] for r in targets})
    if manual_missing or manual_extra:
        raise RuntimeError(f"manual table mismatch: missing={manual_missing}, extra={manual_extra}")
    name_order = ["도희재", "서재원", "이우청", "임승식", "이정운"]
    return sorted(targets, key=lambda r: (name_order.index(r["name"]) if r["name"] in name_order else 99, r["sdName"], r["name"]))


def build_criminal_lookup() -> dict[str, dict[str, Any]]:
    data = read_json(CRIMINAL_JSON)
    return {str(r.get("huboid")): r for r in data.get("records", []) if r.get("huboid")}


def build_detail_rows(targets: list[dict[str, str]], criminal_lookup: dict[str, dict[str, Any]]) -> tuple[list[dict[str, Any]], list[str]]:
    rows: list[dict[str, Any]] = []
    logs: list[str] = []
    for target in targets:
        huboid = target["huboid"]
        record = criminal_lookup.get(huboid, {})
        pdf_urls = record.get("pdf_urls") or []
        pdf_status = "성공" if pdf_urls else "실패"
        cache_note = ""
        if pdf_urls:
            h = url_key(pdf_urls[0])
            pdf_path = PDF_CACHE_DIR / f"{h}.PDF"
            image_path = PDF_CACHE_DIR / f"{h}_1.jpg"
            cache_note = f"PDF cache={'Y' if pdf_path.exists() else 'N'}, image cache={'Y' if image_path.exists() else 'N'}"
            if not pdf_path.exists() or not image_path.exists():
                pdf_status = "실패"

        empty_category_offenses: list[str] = []
        uncertain: list[str] = ["PDF 표에 처분기관·확정 여부 별도 칼럼 없음", "PDF 표에 연번 칼럼 없음: 표 순서를 offense_seq로 기록"]

        for idx, manual in enumerate(MANUAL_OFFENSES[huboid], start=1):
            date_iso = parse_date(manual["date"])
            result_type = disposition_result_type(manual["result"])
            matched = match_categories(manual["offense"])
            if not matched:
                empty_category_offenses.append(manual["offense"])
            details = {
                "huboid": huboid,
                "name": target["name"],
                "party": target["party"],
                "office": target["office"],
                "sdName": target["sdName"],
                "sggName": target["sggName"],
                "nec_detail_url": target["nec_detail_url"],
                "pdf_url": pdf_urls[0] if pdf_urls else "",
                "offense_seq": idx,
                "offense_name_raw": manual["offense"],
                "offense_name_normalized": normalize_offense_name(manual["offense"]),
                "disposition_date_raw": manual["date"],
                "disposition_date_iso": date_iso,
                "disposition_result_raw": manual["result"],
                "disposition_result_type": result_type,
                "disposition_amount_or_term": amount_or_term(manual["result"], result_type),
                "fine_krw": fine_krw(manual["result"]) or "",
                "imprisonment_term_months": parse_months(manual["result"], "징역") or parse_months(manual["result"], "금고") or "",
                "suspension_term_months": parse_months(manual["result"], "집행유예") or "",
                "disposition_agency": "",
                "finality_raw": "",
                "finality_normalized": "",
                "years_since_disposition": years_since(date_iso),
                "our_category_match": ", ".join(matched),
                "needs_human_review": "N" if pdf_status == "성공" and date_iso and result_type != "기타" else "Y",
            }
            rows.append(details)

        logs.extend([
            f"[{target['huboid']} {target['name']}] PDF 접근: {pdf_status} ({cache_note})",
            f"  텍스트 추출 방식: 캐시된 PDF 이미지 원문 대조 + 표 수동 전사",
            f"  추출된 전과 행 수: {len(MANUAL_OFFENSES[huboid])}",
            f"  정규화 불확실 항목: {', '.join(uncertain)}",
            f"  our_category_match 공란 죄명: {', '.join(empty_category_offenses) if empty_category_offenses else '없음'}",
        ])
    return rows, logs


def build_summary_rows(detail_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for row in detail_rows:
        grouped[row["huboid"]].append(row)

    summary: list[dict[str, Any]] = []
    for huboid, rows in grouped.items():
        first = rows[0]
        dates = sorted([r["disposition_date_iso"] for r in rows if r["disposition_date_iso"]])
        fines = [int(r["fine_krw"]) for r in rows if str(r.get("fine_krw") or "").isdigit()]
        categories = sorted({
            c.strip()
            for r in rows
            for c in str(r.get("our_category_match") or "").split(",")
            if c.strip()
        })
        latest = dates[-1] if dates else ""
        summary.append({
            "huboid": huboid,
            "name": first["name"],
            "party": first["party"],
            "office": first["office"],
            "sdName": first["sdName"],
            "sggName": first["sggName"],
            "nec_detail_url": first["nec_detail_url"],
            "total_offense_count": len(rows),
            "offense_names_concat": "; ".join(r["offense_name_normalized"] for r in rows),
            "earliest_disposition_date_iso": dates[0] if dates else "",
            "latest_disposition_date_iso": latest,
            "years_since_latest": years_since(latest),
            "has_imprisonment": "Y" if any(r["disposition_result_type"] in {"징역", "금고", "집행유예"} for r in rows) else "N",
            "has_suspended_sentence": "Y" if any(r["disposition_result_type"] == "집행유예" for r in rows) else "N",
            "max_fine_krw": max(fines) if fines else "",
            "categories_matched_in_record": ", ".join(categories),
            "needs_human_review": "Y" if any(r["needs_human_review"] == "Y" for r in rows) else "N",
        })
    priority = ["도희재", "서재원", "이우청", "임승식", "이정운"]
    summary.sort(key=lambda r: (priority.index(r["name"]) if r["name"] in priority else 99, r["sdName"], r["name"]))
    return summary


def write_raw_files(out_dir: Path, targets: list[dict[str, str]], criminal_lookup: dict[str, dict[str, Any]]) -> None:
    raw_dir = out_dir / "top10_pdf_raw"
    raw_dir.mkdir(parents=True, exist_ok=True)
    for target in targets:
        huboid = target["huboid"]
        record = criminal_lookup.get(huboid, {})
        rows = MANUAL_OFFENSES[huboid]
        pdf_urls = record.get("pdf_urls") or []
        lines = [
            f"huboid: {huboid}",
            f"name: {target['name']}",
            f"party: {target['party']}",
            f"office: {target['office']}",
            f"district: {target['sdName']} {target['sggName']}",
            f"nec_detail_url: {target['nec_detail_url']}",
            f"pdf_url: {pdf_urls[0] if pdf_urls else ''}",
            "",
            "원문 표 전사",
        ]
        for idx, row in enumerate(rows, start=1):
            lines.append(f"{idx}. 죄명: {row['offense']} | 형량(처분결과): {row['result']} | 처분일자: {row['date']}")
        lines.extend([
            "",
            "기존 추출 텍스트",
            record.get("ocr_text") or record.get("offense_text") or "",
        ])
        path = raw_dir / f"{huboid}_{safe_filename(target['name'])}.txt"
        path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def validation_lines(detail_rows: list[dict[str, Any]], summary_rows: list[dict[str, Any]]) -> list[str]:
    detail_huboids = {r["huboid"] for r in detail_rows}
    summary_total = sum(int(r["total_offense_count"]) for r in summary_rows)
    target_hit_count = sum(
        1 for r in summary_rows
        if any(category in r["categories_matched_in_record"] for category in TARGET_CATEGORIES)
    )
    dated_rows = sum(1 for r in detail_rows if r["disposition_date_iso"])
    review_rows = sum(1 for r in detail_rows if r["needs_human_review"] == "Y")
    lines = [
        "top10 전과 원문 세부 추출 검증",
        f"검증 시각: {datetime.now(KST).isoformat(timespec='seconds')}",
        "",
        f"[{'PASS' if len(detail_huboids) == 10 else 'FAIL'}] top10_offense_details 고유 huboid 수 = 10 ({len(detail_huboids)}/10)",
        f"[{'PASS' if summary_total == len(detail_rows) else 'FAIL'}] summary total_offense_count 합 = details 행 수 ({summary_total}/{len(detail_rows)})",
        f"[{'PASS' if target_hit_count == 10 else 'FAIL'}] 사기·횡령·배임·뇌물 중 최소 하나가 매칭된 후보 수 ({target_hit_count}/10)",
        f"disposition_date_iso 입력률: {dated_rows}/{len(detail_rows)} ({dated_rows / len(detail_rows) * 100:.1f}%)",
        f"needs_human_review=Y 행 수: {review_rows}",
        "",
        "비고: PDF 표에는 처분기관과 확정 여부 칼럼이 없어 해당 컬럼은 추정하지 않고 비워 두었습니다.",
        "비고: PDF 표에는 연번 칼럼이 없어 표의 위에서 아래 순서를 offense_seq로 기록했습니다.",
    ]
    return lines


def write_readme(out_dir: Path, stats: dict[str, Any]) -> None:
    text = f"""# Top 10 전과 원문 세부 추출 패키지

## 기준

- 기준 후보: `uncontested_candidates.csv`에서 `important_categories`에 사기·횡령·배임·뇌물 중 하나 이상이 포함된 무투표 당선 후보 10명
- 기준일: 2026-06-03
- 생성 시각: {stats["generated_at"]}

## 파일

- `top10_offense_details.csv`: 한 행이 전과 기록 1건입니다.
- `top10_offense_summary.csv`: 후보 단위 요약입니다.
- `top10_pdf_raw/`: 후보별 PDF 표 전사와 기존 추출 텍스트입니다.
- `top10_extraction_log.txt`: 후보별 접근·추출 로그입니다.
- `top10_validation.txt`: 자체 검증 결과입니다.

## 처리 원칙

- 죄명·형량·처분일자는 원문 표기를 `_raw` 컬럼에 보존했습니다.
- 처분기관과 확정 여부는 PDF 표에 별도 칼럼이 없어 비워 두었습니다.
- PDF 표에 연번 칼럼이 없어 표 순서를 `offense_seq`로 기록했습니다.
- 인용 시 선관위 후보자 상세 페이지 원문 확인 필요.
"""
    (out_dir / "README.md").write_text(text, encoding="utf-8")


def build_package(out_dir: Path) -> dict[str, Any]:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    targets = candidate_targets()
    criminal_lookup = build_criminal_lookup()
    detail_rows, log_lines = build_detail_rows(targets, criminal_lookup)
    summary_rows = build_summary_rows(detail_rows)
    write_raw_files(out_dir, targets, criminal_lookup)

    detail_fields = [
        "huboid", "name", "party", "office", "sdName", "sggName", "nec_detail_url", "pdf_url",
        "offense_seq", "offense_name_raw", "offense_name_normalized",
        "disposition_date_raw", "disposition_date_iso",
        "disposition_result_raw", "disposition_result_type", "disposition_amount_or_term",
        "fine_krw", "imprisonment_term_months", "suspension_term_months",
        "disposition_agency", "finality_raw", "finality_normalized",
        "years_since_disposition", "our_category_match", "needs_human_review",
    ]
    summary_fields = [
        "huboid", "name", "party", "office", "sdName", "sggName", "nec_detail_url",
        "total_offense_count", "offense_names_concat",
        "earliest_disposition_date_iso", "latest_disposition_date_iso", "years_since_latest",
        "has_imprisonment", "has_suspended_sentence", "max_fine_krw",
        "categories_matched_in_record", "needs_human_review",
    ]

    write_csv(out_dir / "top10_offense_details.csv", detail_rows, detail_fields)
    write_csv(out_dir / "top10_offense_summary.csv", summary_rows, summary_fields)

    validation = validation_lines(detail_rows, summary_rows)
    (out_dir / "top10_extraction_log.txt").write_text("\n".join(log_lines) + "\n", encoding="utf-8")
    (out_dir / "top10_validation.txt").write_text("\n".join(validation) + "\n", encoding="utf-8")

    stats = {
        "generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "target_candidate_count": len(targets),
        "detail_row_count": len(detail_rows),
        "summary_row_count": len(summary_rows),
        "needs_human_review_rows": sum(1 for r in detail_rows if r["needs_human_review"] == "Y"),
    }
    write_readme(out_dir, stats)
    (out_dir / "manifest.json").write_text(json.dumps(stats, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

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
