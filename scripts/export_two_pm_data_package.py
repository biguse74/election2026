#!/usr/bin/env python3
"""Build a broadcast-oriented package for the 2시에 데이터 uncontested-election segment."""

from __future__ import annotations

import argparse
import csv
import json
import re
import shutil
import zipfile
from collections import Counter
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
KST = timezone(timedelta(hours=9))

SOURCE_PACKAGE = ROOT / "exports" / "uncontested_series_package_20260517_1545"
TOP10_PACKAGE = ROOT / "exports" / "top10_offense_details_20260517_1230"
DEFAULT_OUT_DIR = ROOT / "exports" / "two_pm_data_uncontested_package_20260517_1400"

TARGET_CATEGORIES = ("사기", "횡령", "배임", "뇌물")


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def write_csv(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def money_thousand_to_won_text(value: str) -> str:
    try:
        thousand = int(str(value or "0").replace(",", ""))
    except ValueError:
        thousand = 0
    if not thousand:
        return "0원"
    won = thousand * 1000
    if won >= 10_000:
        man = won // 10_000
        rest = won % 10_000
        return f"{man:,}만{rest:,}원" if rest else f"{man:,}만원"
    return f"{won:,}원"


def compact_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def category_hits(text: str) -> list[str]:
    return [category for category in TARGET_CATEGORIES if category in (text or "")]


def district_key(row: dict[str, str]) -> str:
    return f"{row.get('office')}|{row.get('sdName')}|{row.get('sggName')}"


def load_snapshot_candidate_map() -> dict[str, dict[str, Any]]:
    snapshot = read_json(ROOT / "data" / "candidates" / "20260603" / "snapshot_20260517.json")
    return {str(row.get("huboid")): row for row in snapshot.get("candidates", [])}


def make_target_offense_rows(details: list[dict[str, str]]) -> list[dict[str, str]]:
    rows = []
    for row in details:
        hits = category_hits(row.get("our_category_match", ""))
        if not hits:
            continue
        out = dict(row)
        out["target_category_match"] = ", ".join(hits)
        rows.append(out)
    rows.sort(key=lambda r: (r["huboid"], r.get("disposition_date_iso", "")))
    return rows


def make_candidate_cards(
    targets: list[dict[str, str]],
    districts: list[dict[str, str]],
    summaries: list[dict[str, str]],
    target_offenses: list[dict[str, str]],
    snapshot_by_huboid: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    district_by_key = {district_key(row): row for row in districts}
    summary_by_huboid = {row["huboid"]: row for row in summaries}
    offenses_by_huboid: dict[str, list[dict[str, str]]] = {}
    for row in target_offenses:
        offenses_by_huboid.setdefault(row["huboid"], []).append(row)

    cards: list[dict[str, Any]] = []
    for row in sorted(targets, key=lambda r: (r["office"] != "시도의원", r["sdName"], r["sggName"], r["name"])):
        huboid = row["huboid"]
        district = district_by_key.get(district_key(row), {})
        summary = summary_by_huboid.get(huboid, {})
        snapshot = snapshot_by_huboid.get(huboid, {})
        target_rows = offenses_by_huboid.get(huboid, [])
        latest_target = max(target_rows, key=lambda r: r.get("disposition_date_iso", "")) if target_rows else {}
        seat_count = int(district.get("의원정수") or row.get("해당선거구_의원정수") or 0)
        candidate_count = int(district.get("등록후보수") or 0)
        if seat_count == 1 and candidate_count == 1:
            uncontested_shape = "단독 출마"
        elif candidate_count == seat_count:
            uncontested_shape = "정수와 후보 수 동일"
        elif district.get("비례대표_단일정당명부여부") == "Y":
            uncontested_shape = "비례대표 단일 정당 명부"
        else:
            uncontested_shape = "무투표"
        tax_text = money_thousand_to_won_text(row.get("tax_arrears_5y_thousand_krw", "0"))
        category_text = ", ".join(category_hits(row.get("important_categories", "")))
        career_text = " / ".join(
            compact_text(snapshot.get(key, "")) for key in ("career1", "career2") if compact_text(snapshot.get(key, ""))
        )
        offense_line = "; ".join(
            f"{r.get('disposition_date_iso')} {compact_text(r.get('offense_name_normalized'))} {compact_text(r.get('disposition_result_raw'))}"
            for r in target_rows
        )
        if tax_text != "0원":
            tax_line = f", 최근 5년 체납 {tax_text}"
        else:
            tax_line = ""
        cards.append({
            "huboid": huboid,
            "name": row["name"],
            "party": row["party"],
            "office": row["office"],
            "sdName": row["sdName"],
            "sggName": row["sggName"],
            "district_label": f'{row["sdName"]} {row["sggName"]}',
            "seat_count": seat_count,
            "registered_candidates": candidate_count,
            "uncontested_shape": uncontested_shape,
            "target_categories": category_text,
            "tax_arrears_5y_thousand_krw": row.get("tax_arrears_5y_thousand_krw", "0"),
            "tax_arrears_5y_won_text": tax_text,
            "criminal_record_disclosure": row.get("criminal_record_disclosure", ""),
            "total_offense_count": summary.get("total_offense_count", ""),
            "target_offense_count": len(target_rows),
            "target_offense_line": offense_line,
            "latest_target_offense_date": latest_target.get("disposition_date_iso", ""),
            "latest_target_offense_name": compact_text(latest_target.get("offense_name_normalized", "")),
            "latest_target_disposition": compact_text(latest_target.get("disposition_result_raw", "")),
            "has_imprisonment": summary.get("has_imprisonment", ""),
            "has_suspended_sentence": summary.get("has_suspended_sentence", ""),
            "max_fine_krw": summary.get("max_fine_krw", ""),
            "job": compact_text(snapshot.get("job", "")),
            "career_summary": career_text,
            "nec_detail_url": row.get("nec_detail_url", ""),
            "on_air_line": (
                f'{row["name"]} {row["party"]} 후보는 {row["sdName"]} {row["sggName"]} '
                f'{row["office"]} 선거에서 {uncontested_shape}로 본투표 없이 당선되는 구조입니다. '
                f'선관위 공개 전과 분류상 {category_text} 항목이 확인됩니다{tax_line}.'
            ),
        })
    return cards


def write_readme(path: Path, stats: dict[str, Any]) -> None:
    path.write_text(f"""# 2시에 데이터 방송용 패키지

## 주제

사기·횡령·배임·뇌물 전과와 체납 이력이 있어도 본투표 없이 당선되는 구조.

## 기준 숫자

- 선관위 보도 집계와 맞춘 무투표 당선 후보: {stats["total_uncontested_candidates"]:,}명
- 무투표 선거구: {stats["total_uncontested_districts"]:,}곳
- 사기·횡령·배임·뇌물 분류 무투표 후보: {stats["target_economic_trust_candidates"]:,}명
- 그중 단독 출마: {stats["solo_single_seat_target_candidates"]:,}명
- 무투표 후보 중 최근 5년 체납 이력: {stats["uncontested_with_tax_history_candidates"]:,}명

## 폴더 구조

- `docs/`: 방송 원고·그래픽·팩트체크용 문서
- `data/`: CSV/JSON 근거 데이터
- `source_notes/`: 기존 검증 로그와 추출 로그

## 주의

후보별 죄명·시점·형량을 인용할 때는 선관위 후보자 상세 페이지 원문 확인이 필요합니다. 전과 유형은 죄명 영역을 넓은 보도용 범주로 묶은 것이며, 후보 한 명이 여러 분류에 동시에 포함될 수 있습니다.
""", encoding="utf-8")


def write_broadcast_docs(out_dir: Path, stats: dict[str, Any], cards: list[dict[str, Any]]) -> None:
    docs = out_dir / "docs"
    docs.mkdir(parents=True, exist_ok=True)

    category_counts = stats["target_category_candidate_counts"]
    write = lambda name, text: (docs / name).write_text(text, encoding="utf-8")

    write("00_BROADCAST_BRIEF.md", f"""# 방송 브리프

## 한 문장

6·3 지방선거에서 본투표 없이 당선되는 후보는 선관위 보도 집계 기준 {stats["total_uncontested_candidates"]:,}명이고, 이 가운데 사기·횡령·배임·뇌물로 분류되는 전과를 신고한 후보가 {stats["target_economic_trust_candidates"]}명 확인됐다.

## 숫자 골격

- 무투표 당선 후보: {stats["total_uncontested_candidates"]:,}명
- 무투표 선거구: {stats["total_uncontested_districts"]:,}곳
- 직책별: 기초단체장 3명, 광역의원 108명, 지역구 기초의원 305명, 기초의원비례 97명
- 사기·횡령·배임·뇌물 분류 후보: {stats["target_economic_trust_candidates"]}명
- 분류별 후보 수: 사기 {category_counts["사기"]}명, 횡령 {category_counts["횡령"]}명, 배임 {category_counts["배임"]}명, 뇌물 {category_counts["뇌물"]}명
- 위 10명 중 단독 출마: {stats["solo_single_seat_target_candidates"]}명
- 무투표 후보 중 최근 5년 체납 이력: {stats["uncontested_with_tax_history_candidates"]}명

## 핵심 프레임

출마 자격을 문제 삼는 방송이 아니다. 유권자가 후보의 전과와 체납, 의정 이력을 보고 판단할 본투표가 사라지는 구조를 파헤치는 방송이다. 공천이 곧 당선이 되는 지역에서 검증의 마지막 관문이 정당 안으로 들어간다는 점을 전면에 둔다.

## 494명과 513명 차이

우리의 첫 산출물은 비례대표도 지역구처럼 `등록후보수 <= 의원정수`만 적용해 {stats["previous_uncontested_candidates"]}명으로 잡혔다. 선관위 보도 집계와 대조하니 기초의원비례에서 한 정당 명부만 등록된 9개 선거구, 19명이 빠져 있었다. 이를 반영하면 {stats["total_uncontested_candidates"]}명, {stats["total_uncontested_districts"]}곳으로 보도 숫자와 일치한다.
""")

    write("01_RUNDOWN_2PM_DATA.md", f"""# 1시간 구성안

## 0-5분: 오늘의 질문

“범죄 전력이나 체납 이력이 있어도, 본투표 없이 당선되는 구조가 있다면 유권자는 어디서 검증해야 하는가.”

## 5-13분: 전체 판

무투표 후보 {stats["total_uncontested_candidates"]}명, 선거구 {stats["total_uncontested_districts"]}곳. 먼저 동아일보·SBS 보도에 나온 선관위 발표 숫자와 우리가 정리한 후보별 데이터가 일치하도록 보정한 경위를 짧게 설명한다.

## 13-25분: 10명

사기·횡령·배임·뇌물 분류 후보 10명. 단독 출마 5명과 정수 동수 5명으로 나눠 보여준다.

## 25-35분: 사례

임승식 후보를 도입 사례로 쓰되 체납액은 “894만7천원” 또는 “약 895만원”으로 읽는다. 가장 최근 사례는 “전체 전과”가 아니라 “사기·횡령·배임·뇌물 범주 중 가장 최근”이라는 식으로 이종석 후보 2023년 4월 사기를 설명한다.

## 35-45분: 체납

무투표 후보 중 최근 5년 체납 이력 {stats["uncontested_with_tax_history_candidates"]}명. 현 체납 {stats["uncontested_with_current_tax_candidates"]}명과 구분한다.

## 45-55분: 정당과 지역 구조

영남 단독 도의원 후보 3명은 국민의힘, 호남 단독 도의원 후보 2명은 민주당이다. 정당 이름은 다르지만 경쟁이 사라진 지역에서 공천이 곧 당선으로 이어지는 구조는 같다.

## 55-60분: 결론

법이 허용한 출마를 문제 삼는 것이 아니라, 본투표라는 공개 검증 절차가 사라진 자리에 무엇이 들어와야 하는지를 묻는다.
""")

    write("02_ON_AIR_NUMBERS.md", f"""# 온에어 숫자

- 무투표 당선 후보: {stats["total_uncontested_candidates"]:,}명
- 무투표 선거구: {stats["total_uncontested_districts"]:,}곳
- 기초단체장: 3명
- 광역의원: 108명
- 지역구 기초의원: 305명
- 기초의원비례: 97명
- 사기·횡령·배임·뇌물 분류: 10명
- 단독 출마: 5명
- 최근 5년 체납 이력 무투표 후보: {stats["uncontested_with_tax_history_candidates"]}명
- 현 체납 무투표 후보: {stats["uncontested_with_current_tax_candidates"]}명
- 전과 공개 무투표 후보: {stats["uncontested_with_criminal_disclosure_candidates"]}명
- 공직 검증 전과 무투표 후보: {stats["uncontested_with_official_misconduct_record_candidates"]}명

## 읽을 때 조심할 문장

- “무투표 당선 494명”은 쓰지 않는다. 선관위 보도 집계 기준은 513명이다.
- “최근 체납 73명”은 쓰지 않는다. 보정 후 기준은 74명이다.
- “가장 최근 전과는 이종석 후보 사기”라고 넓게 말하지 않는다. “사기·횡령·배임·뇌물 범주 중 가장 최근”이라고 말한다.
- “임승식 후보 체납 894만원”보다 “894만7천원” 또는 “약 895만원”이 정확하다.
""")

    card_lines = ["# 후보 카드\n"]
    for card in cards:
        card_lines.append(f"""## {card["name"]} / {card["party"]}

- 선거: {card["district_label"]} {card["office"]}
- 구조: {card["uncontested_shape"]} / 정수 {card["seat_count"]}명, 등록 {card["registered_candidates"]}명
- 분류: {card["target_categories"]}
- 최근 5년 체납: {card["tax_arrears_5y_won_text"]}
- 전과 상세: {card["target_offense_line"]}
- 경력: {card["career_summary"]}
- 온에어 문장: {card["on_air_line"]}
""")
    write("03_TOP10_CANDIDATE_CARDS.md", "\n".join(card_lines))

    write("04_GRAPHICS_AND_LOWER_THIRDS.md", f"""# 그래픽·자막 제안

## 대형 숫자

- “무투표 당선 {stats["total_uncontested_candidates"]}명”
- “사기·횡령·배임·뇌물 분류 10명”
- “10명 중 5명은 단독 출마”
- “최근 5년 체납 이력 무투표 후보 {stats["uncontested_with_tax_history_candidates"]}명”

## 비교 그래픽

1. 직책별 무투표 후보 막대: 기초단체장 3, 광역의원 108, 지역구 기초의원 305, 기초의원비례 97.
2. 10명 분류 도넛: 사기 4, 횡령 3, 배임 3, 뇌물 2. 후보 중복 포함 주석 필수.
3. 단독 5명 지도: 경북 3, 전북 1, 전남 1.
4. 체납 카드: 최근 5년 체납 74명, 현 체납 3명.

## 하단 자막

- “선관위 후보자 공개정보 기준”
- “후보별 죄명·시점·형량은 선관위 상세 페이지 원문 확인 필요”
- “전과 유형은 죄명 영역을 넓은 범주로 묶은 것으로 중복 분류 가능”
""")

    write("05_FACTCHECK_NOTES.md", f"""# 팩트체크 노트

## 기사 참고 후 수정한 핵심

동아일보·SBS 보도는 선관위 발표로 무투표 당선 후보 {stats["total_uncontested_candidates"]}명, 선거구 {stats["total_uncontested_districts"]}곳을 제시했다. 우리의 기존 494명과 다른 이유는 기초의원비례 단일 정당 명부 선거구 9곳 19명이 누락됐기 때문이다.

## 추가된 19명

`data/uncontested_single_party_pr_added_19.csv`에 따로 분리했다. 정당별로 더불어민주당 17명, 국민의힘 2명이다. 이를 더하면 기초의원비례가 민주당 56명, 국민의힘 41명으로 기사 수치와 일치한다.

## 초안 문장 교정

- “무투표 당선 494명” -> “무투표 당선 513명”
- “무투표 선거구 298곳” -> “무투표 선거구 307곳”
- “최근 5년 체납 이력 73명” -> “최근 5년 체납 이력 74명”
- “임승식 체납 894만원” -> “임승식 최근 5년 체납 894만7천원” 또는 “약 895만원”
- “가장 최근 전과는 이종석 후보 사기” -> “사기·횡령·배임·뇌물 범주 중 가장 최근 항목은 이종석 후보의 2023년 4월 사기”

## 변하지 않는 핵심

사기·횡령·배임·뇌물 분류 무투표 후보는 10명 그대로다. 이들은 모두 지역구 후보라 기초의원비례 보정의 영향을 받지 않는다.
""")

    write("06_CLAUDE_BROADCAST_PROMPT.md", f"""# Claude 투입 프롬프트

너는 데이터 방송 작가다. 아래 패키지는 선관위 후보자 공개정보와 후보별 전과 상세 추출표를 바탕으로 만든 방송용 근거 자료다.

## 방송 주제

사기·횡령·배임·뇌물 전과와 체납 이력이 있어도 본투표 없이 당선되는 구조를 파헤친다.

## 반드시 지킬 숫자

- 무투표 당선 후보는 513명이다. 494명은 이전 산식의 누락값이므로 쓰지 않는다.
- 무투표 선거구는 307곳이다.
- 사기·횡령·배임·뇌물 분류 후보는 10명이다.
- 10명 중 단독 출마는 5명이다.
- 무투표 후보 중 최근 5년 체납 이력은 74명이다.

## 사용할 파일

- `data/core_stats.json`
- `data/top10_broadcast_cards.csv`
- `data/top10_target_offense_rows.csv`
- `data/uncontested_tax_candidates.csv`
- `docs/05_FACTCHECK_NOTES.md`

## 톤

출마 자격을 단정적으로 문제 삼지 말고, 본투표가 사라지며 유권자 검증 기회가 사라지는 구조를 설명하라. 후보별 범죄명은 선관위 상세 페이지 원문 확인이 필요하다는 문장을 붙여라. 방법론 전문용어는 방송 원고에 쓰지 말라.
""")


def build_package(out_dir: Path) -> dict[str, Any]:
    if out_dir.exists():
        shutil.rmtree(out_dir)
    (out_dir / "data").mkdir(parents=True)
    (out_dir / "source_notes").mkdir(parents=True)

    key_stats = read_json(SOURCE_PACKAGE / "uncontested_key_stats.json")
    candidates = read_csv(SOURCE_PACKAGE / "uncontested_candidates.csv")
    districts = read_csv(SOURCE_PACKAGE / "uncontested_districts.csv")
    summaries = read_csv(TOP10_PACKAGE / "top10_offense_summary.csv")
    details = read_csv(TOP10_PACKAGE / "top10_offense_details.csv")
    snapshot_by_huboid = load_snapshot_candidate_map()

    targets = [row for row in candidates if category_hits(row.get("important_categories", ""))]
    target_offenses = make_target_offense_rows(details)
    cards = make_candidate_cards(targets, districts, summaries, target_offenses, snapshot_by_huboid)

    category_counts = Counter()
    for row in targets:
        for category in category_hits(row.get("important_categories", "")):
            category_counts[category] += 1

    single_party_pr_candidates = [
        row for row in candidates if row.get("해당선거구_비례대표_단일정당명부여부") == "Y"
    ]
    tax_candidates = [row for row in candidates if row.get("체납이력_보유") == "Y"]
    red_flag_candidates = [
        row for row in candidates if row.get("체납이력_보유") == "Y" or row.get("공직검증전과_보유") == "Y"
    ]

    stats = {
        **key_stats,
        "package_generated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "previous_uncontested_candidates": 494,
        "previous_uncontested_districts": 298,
        "reconciliation_added_candidates": len(single_party_pr_candidates),
        "reconciliation_added_districts": len({district_key(row) for row in single_party_pr_candidates}),
        "target_economic_trust_candidates": len(targets),
        "target_category_candidate_counts": {category: category_counts[category] for category in TARGET_CATEGORIES},
        "solo_single_seat_target_candidates": sum(
            1 for card in cards if card["seat_count"] == 1 and card["registered_candidates"] == 1
        ),
        "target_with_tax_history_candidates": sum(1 for row in targets if row.get("체납이력_보유") == "Y"),
        "single_party_pr_added_party_counts": dict(Counter(row["party"] for row in single_party_pr_candidates)),
    }

    data_dir = out_dir / "data"
    write_json(data_dir / "core_stats.json", stats)
    write_csv(data_dir / "top10_broadcast_cards.csv", cards, list(cards[0].keys()))
    write_csv(data_dir / "top10_target_offense_rows.csv", target_offenses, list(target_offenses[0].keys()))
    shutil.copy2(TOP10_PACKAGE / "top10_offense_summary.csv", data_dir / "top10_offense_summary.csv")
    shutil.copy2(TOP10_PACKAGE / "top10_offense_details.csv", data_dir / "top10_offense_details.csv")
    shutil.copy2(SOURCE_PACKAGE / "uncontested_key_stats.json", data_dir / "uncontested_key_stats.json")
    shutil.copy2(SOURCE_PACKAGE / "uncontested_by_office.csv", data_dir / "uncontested_by_office.csv")
    shutil.copy2(SOURCE_PACKAGE / "uncontested_by_party.csv", data_dir / "uncontested_by_party.csv")
    shutil.copy2(SOURCE_PACKAGE / "uncontested_by_region.csv", data_dir / "uncontested_by_region.csv")
    write_csv(data_dir / "uncontested_tax_candidates.csv", tax_candidates, list(candidates[0].keys()))
    write_csv(data_dir / "uncontested_red_flag_candidates.csv", red_flag_candidates, list(candidates[0].keys()))
    write_csv(data_dir / "uncontested_single_party_pr_added_19.csv", single_party_pr_candidates, list(candidates[0].keys()))

    checklist = [
        {"claim": "무투표 당선 494명", "status": "수정", "use": "선관위 보도 집계와 맞춘 513명"},
        {"claim": "무투표 선거구 298곳", "status": "수정", "use": "307곳"},
        {"claim": "최근 5년 체납 73명", "status": "수정", "use": "74명"},
        {"claim": "사기·횡령·배임·뇌물 분류 10명", "status": "유지", "use": "10명"},
        {"claim": "그중 단독 출마 5명", "status": "유지", "use": "5명"},
        {"claim": "임승식 체납 894만원", "status": "정확화", "use": "894만7천원 또는 약 895만원"},
        {
            "claim": "가장 최근 전과는 이종석 후보 사기",
            "status": "표현 제한",
            "use": "사기·횡령·배임·뇌물 범주 중 가장 최근 항목은 이종석 후보의 2023년 4월 사기",
        },
    ]
    write_csv(data_dir / "draft_claim_checklist.csv", checklist, ["claim", "status", "use"])

    write_readme(out_dir / "README.md", stats)
    write_broadcast_docs(out_dir, stats, cards)

    for filename in ("validation_report.txt",):
        shutil.copy2(SOURCE_PACKAGE / filename, out_dir / "source_notes" / filename)
    for filename in ("top10_validation.txt", "top10_extraction_log.txt", "README.md"):
        shutil.copy2(TOP10_PACKAGE / filename, out_dir / "source_notes" / f"top10_{filename}")

    manifest = {
        "generated_at": stats["package_generated_at"],
        "source_package": str(SOURCE_PACKAGE.relative_to(ROOT)).replace("\\", "/"),
        "top10_package": str(TOP10_PACKAGE.relative_to(ROOT)).replace("\\", "/"),
        "files": sorted(str(p.relative_to(out_dir)).replace("\\", "/") for p in out_dir.rglob("*") if p.is_file()),
    }
    write_json(out_dir / "manifest.json", manifest)

    zip_path = out_dir.with_suffix(".zip")
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in out_dir.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(out_dir.parent))
    return {"out_dir": str(out_dir.relative_to(ROOT)), "zip_path": str(zip_path.relative_to(ROOT)), "stats": stats}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out-dir", type=Path, default=DEFAULT_OUT_DIR)
    args = parser.parse_args()
    out_dir = args.out_dir if args.out_dir.is_absolute() else ROOT / args.out_dir
    result = build_package(out_dir)
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
