#!/usr/bin/env python3
"""Build a Claude-ready package for comparing Democratic Party vs People Power Party vetting."""

from __future__ import annotations

import csv
import json
import shutil
import zipfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "exports" / "two_pm_party_vetting_package_20260518"

SNAPSHOT = ROOT / "data" / "candidates" / "20260603" / "snapshot_20260518.json"
DETAILS = ROOT / "data" / "candidate_details.json"
CRIMINAL_OCR = ROOT / "data" / "criminal_ocr.json"
CONSTITUENCIES = ROOT / "data" / "constituencies.json"

PARTIES = ("더불어민주당", "국민의힘")
PARTY_SHORT = {"더불어민주당": "민주당", "국민의힘": "국힘"}
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
UNCONTESTED_TYPES = {"4", "5", "6", "8", "9"}
ECONOMIC_TRUST = ("사기", "횡령", "배임", "뇌물")
ELECTION_INTEGRITY = ("공직선거법", "정치자금법", "청탁금지법")
PUBLIC_ADMIN = ("직권남용", "허위공문서·문서위조·공용서류", "국가공무원법", "지방공무원법")
TAX_PUBLIC_MONEY = ("조세", "보조금")
TRAFFIC_SAFETY = ("위험운전", "음주운전", "무면허운전")


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def write_json(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def parse_int(value: Any) -> int:
    text = str(value or "").replace(",", "").strip()
    if not text:
        return 0
    try:
        return int(float(text))
    except ValueError:
        return 0


def parse_criminal_count(value: Any) -> int:
    text = str(value or "").strip()
    if text in ("", "없음", "0", "0건"):
        return 0
    digits = "".join(ch for ch in text if ch.isdigit())
    return int(digits or 0)


def pct(n: int, d: int) -> str:
    return f"{(n / d * 100) if d else 0:.1f}%"


def rate_value(n: int, d: int) -> float:
    return round((n / d * 100) if d else 0, 4)


def money_text(thousand_krw: int) -> str:
    if not thousand_krw:
        return "0원"
    won = thousand_krw * 1000
    if won >= 100_000_000:
        eok = won // 100_000_000
        man = (won % 100_000_000) // 10_000
        return f"{eok:,}억{man:,}만원" if man else f"{eok:,}억원"
    if won >= 10_000:
        return f"{won // 10_000:,}만원"
    return f"{won:,}원"


def is_active(c: dict[str, Any]) -> bool:
    return not c.get("status") or c.get("status") == "등록"


def seat_key(row: dict[str, Any]) -> str:
    return f'{row.get("sgTypecode")}|{row.get("sdName")}|{row.get("sggName")}'


def office(c: dict[str, Any]) -> str:
    return SG_TITLE.get(str(c.get("sgTypecode")), str(c.get("sgTypecode") or ""))


def region(c: dict[str, Any]) -> str:
    sd = c.get("sdName") or ""
    sgg = c.get("sggName") or ""
    return f"{sd} {sgg}".strip() if sgg and sgg != sd else sd


def category_string(categories: set[str]) -> str:
    return ", ".join(sorted(categories))


def build_uncontested_set(candidates: list[dict[str, Any]], constituencies: list[dict[str, Any]]) -> set[str]:
    seats: dict[str, int] = {}
    counts: Counter[str] = Counter()
    by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for s in constituencies:
        if str(s.get("sgTypecode")) not in UNCONTESTED_TYPES:
            continue
        seats[seat_key(s)] = parse_int(s.get("sggJungsu")) or 1
    for c in candidates:
        if not is_active(c) or str(c.get("sgTypecode")) not in UNCONTESTED_TYPES:
            continue
        key = seat_key(c)
        counts[key] += 1
        by_key[key].append(c)
    out: set[str] = set()
    for key, seat in seats.items():
        rows = by_key.get(key, [])
        count = counts[key]
        if not count:
            continue
        sg_type = key.split("|", 1)[0]
        parties = {r.get("jdName") or "무소속" for r in rows}
        single_party_pr = sg_type in {"8", "9"} and count > seat and len(parties) == 1
        if count <= seat or single_party_pr:
            for row in rows:
                if row.get("huboid"):
                    out.add(str(row["huboid"]))
    return out


def annotate_candidates() -> tuple[list[dict[str, Any]], dict[str, Any]]:
    snapshot = read_json(SNAPSHOT)
    details_payload = read_json(DETAILS)
    ocr_payload = read_json(CRIMINAL_OCR)
    constituencies = read_json(CONSTITUENCIES)

    active = [c for c in snapshot["candidates"] if is_active(c)]
    details = {str(d.get("huboid")): d for d in details_payload.get("details", [])}
    ocr = {str(r.get("huboid")): r for r in ocr_payload.get("records", [])}
    important_categories = {
        row["category"]
        for row in ocr_payload.get("categories", [])
        if row.get("group") == "공직 검증"
    }
    uncontested = build_uncontested_set(active, constituencies)

    rows = []
    for c in active:
        if c.get("jdName") not in PARTIES:
            continue
        huboid = str(c.get("huboid") or "")
        detail = details.get(huboid, {})
        disclosures = detail.get("disclosures", {})
        criminal_record_count = parse_criminal_count(disclosures.get("criminal_record"))
        tax_5y = parse_int(disclosures.get("tax_arrears_5y_thousand_krw"))
        tax_current = parse_int(disclosures.get("tax_arrears_current_thousand_krw"))
        ocr_record = ocr.get(huboid, {})
        categories = set(ocr_record.get("categories") or [])
        important_hits = categories & important_categories
        economic_hits = categories & set(ECONOMIC_TRUST)
        election_hits = categories & set(ELECTION_INTEGRITY)
        admin_hits = categories & set(PUBLIC_ADMIN)
        tax_public_hits = categories & set(TAX_PUBLIC_MONEY)
        traffic_hits = categories & set(TRAFFIC_SAFETY)
        hard_vetting_hits = economic_hits | election_hits | admin_hits | tax_public_hits
        any_money_trust = bool(economic_hits) or tax_5y > 0 or tax_current > 0
        any_vetting_flag = bool(important_hits) or tax_5y > 0 or tax_current > 0
        row = {
            "huboid": huboid,
            "name": c.get("name", ""),
            "party": c.get("jdName", ""),
            "party_short": PARTY_SHORT.get(c.get("jdName"), c.get("jdName", "")),
            "office": office(c),
            "sgTypecode": str(c.get("sgTypecode") or ""),
            "sdName": c.get("sdName", ""),
            "sggName": c.get("sggName", ""),
            "wiwName": c.get("wiwName", ""),
            "region": region(c),
            "job": c.get("job", ""),
            "status": c.get("status", "등록"),
            "nec_detail_url": detail.get("nec_detail_url", ""),
            "criminal_record_count": criminal_record_count,
            "has_criminal_record": criminal_record_count > 0,
            "ocr_categories": category_string(categories),
            "official_vetting_categories": category_string(important_hits),
            "economic_trust_categories": category_string(economic_hits),
            "election_integrity_categories": category_string(election_hits),
            "public_admin_categories": category_string(admin_hits),
            "tax_public_money_categories": category_string(tax_public_hits),
            "traffic_safety_categories": category_string(traffic_hits),
            "has_official_vetting_record": bool(important_hits),
            "has_hard_vetting_record": bool(hard_vetting_hits),
            "has_economic_trust_record": bool(economic_hits),
            "has_election_integrity_record": bool(election_hits),
            "has_public_admin_record": bool(admin_hits),
            "has_tax_public_money_record": bool(tax_public_hits),
            "has_traffic_safety_record": bool(traffic_hits),
            "tax_arrears_5y_thousand_krw": tax_5y,
            "tax_arrears_5y_display": money_text(tax_5y),
            "tax_arrears_current_thousand_krw": tax_current,
            "tax_arrears_current_display": money_text(tax_current),
            "has_tax_arrears_5y": tax_5y > 0,
            "has_tax_arrears_current": tax_current > 0,
            "has_money_trust_flag": any_money_trust,
            "has_any_vetting_flag": any_vetting_flag,
            "is_uncontested_candidate": huboid in uncontested,
            "career1": c.get("career1", ""),
            "career2": c.get("career2", ""),
        }
        rows.append(row)
    meta = {
        "snapshot_file": str(SNAPSHOT.relative_to(ROOT)),
        "snapshot_fetched_at": snapshot.get("fetched_at"),
        "candidate_details_file": str(DETAILS.relative_to(ROOT)),
        "criminal_ocr_file": str(CRIMINAL_OCR.relative_to(ROOT)),
        "constituencies_file": str(CONSTITUENCIES.relative_to(ROOT)),
        "total_active_candidates": len(active),
        "target_party_candidates": len(rows),
        "important_categories": sorted(important_categories),
    }
    return rows, meta


def aggregate(rows: list[dict[str, Any]], keys: tuple[str, ...]) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = defaultdict(list)
    for row in rows:
        grouped[tuple(row[k] for k in keys)].append(row)
    out = []
    for key, items in grouped.items():
        total = len(items)
        def count(field: str) -> int:
            return sum(1 for item in items if item[field])
        tax5_sum = sum(int(item["tax_arrears_5y_thousand_krw"]) for item in items)
        current_sum = sum(int(item["tax_arrears_current_thousand_krw"]) for item in items)
        record = {k: v for k, v in zip(keys, key)}
        record.update({
            "total_candidates": total,
            "criminal_record_candidates": count("has_criminal_record"),
            "criminal_record_rate": pct(count("has_criminal_record"), total),
            "official_vetting_record_candidates": count("has_official_vetting_record"),
            "official_vetting_record_rate": pct(count("has_official_vetting_record"), total),
            "hard_vetting_record_candidates": count("has_hard_vetting_record"),
            "hard_vetting_record_rate": pct(count("has_hard_vetting_record"), total),
            "economic_trust_record_candidates": count("has_economic_trust_record"),
            "economic_trust_record_rate": pct(count("has_economic_trust_record"), total),
            "election_integrity_record_candidates": count("has_election_integrity_record"),
            "election_integrity_record_rate": pct(count("has_election_integrity_record"), total),
            "tax_arrears_5y_candidates": count("has_tax_arrears_5y"),
            "tax_arrears_5y_rate": pct(count("has_tax_arrears_5y"), total),
            "tax_arrears_5y_sum_thousand_krw": tax5_sum,
            "tax_arrears_current_candidates": count("has_tax_arrears_current"),
            "tax_arrears_current_rate": pct(count("has_tax_arrears_current"), total),
            "tax_arrears_current_sum_thousand_krw": current_sum,
            "money_trust_flag_candidates": count("has_money_trust_flag"),
            "money_trust_flag_rate": pct(count("has_money_trust_flag"), total),
            "any_vetting_flag_candidates": count("has_any_vetting_flag"),
            "any_vetting_flag_rate": pct(count("has_any_vetting_flag"), total),
            "uncontested_candidates": count("is_uncontested_candidate"),
            "uncontested_rate": pct(count("is_uncontested_candidate"), total),
            "uncontested_with_any_vetting_flag": sum(1 for item in items if item["is_uncontested_candidate"] and item["has_any_vetting_flag"]),
        })
        out.append(record)
    return sorted(out, key=lambda r: tuple(str(r[k]) for k in keys))


def category_counts(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for party in PARTIES:
        party_rows = [r for r in rows if r["party"] == party]
        denom = len(party_rows)
        categories = Counter()
        for row in party_rows:
            for category in filter(None, row["ocr_categories"].split(", ")):
                categories[category] += 1
        for category, count in sorted(categories.items(), key=lambda x: (-x[1], x[0])):
            out.append({
                "party": party,
                "party_short": PARTY_SHORT[party],
                "category": category,
                "candidate_count": count,
                "party_total_candidates": denom,
                "candidate_rate": pct(count, denom),
            })
    return out


def strongest_cases(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    def score(row: dict[str, Any]) -> tuple[int, int, int]:
        s = 0
        if row["is_uncontested_candidate"]:
            s += 30
        if row["has_economic_trust_record"]:
            s += 25
        if row["has_election_integrity_record"]:
            s += 20
        if row["has_public_admin_record"]:
            s += 15
        if row["has_tax_arrears_5y"]:
            s += 10
        if row["has_tax_arrears_current"]:
            s += 15
        if row["tax_arrears_5y_thousand_krw"] >= 100_000:
            s += 20
        return (s, int(row["tax_arrears_5y_thousand_krw"]), int(row["criminal_record_count"]))

    cases = []
    for row in rows:
        if not row["has_any_vetting_flag"]:
            continue
        reasons = []
        if row["is_uncontested_candidate"]:
            reasons.append("무투표 당선")
        if row["economic_trust_categories"]:
            reasons.append(f"경제·신뢰 전과({row['economic_trust_categories']})")
        if row["election_integrity_categories"]:
            reasons.append(f"선거·정치자금 전과({row['election_integrity_categories']})")
        if row["public_admin_categories"]:
            reasons.append(f"공직·문서 전과({row['public_admin_categories']})")
        if row["tax_arrears_5y_thousand_krw"]:
            reasons.append(f"최근 5년 체납 {row['tax_arrears_5y_display']}")
        if row["tax_arrears_current_thousand_krw"]:
            reasons.append(f"현 체납 {row['tax_arrears_current_display']}")
        case = dict(row)
        case["priority_reason"] = "; ".join(reasons)
        case["_score"] = score(row)
        cases.append(case)
    cases.sort(key=lambda r: (r["_score"], r["party"] == "더불어민주당"), reverse=True)
    for i, row in enumerate(cases, 1):
        row["rank"] = i
        row.pop("_score", None)
    return cases[:120]


def key_stats(rows: list[dict[str, Any]], meta: dict[str, Any]) -> dict[str, Any]:
    by_party = {r["party"]: r for r in aggregate(rows, ("party",))}
    metrics = [
        ("criminal_record_rate", "criminal_record_candidates", "전과 공개"),
        ("official_vetting_record_rate", "official_vetting_record_candidates", "공직 검증 전과"),
        ("hard_vetting_record_rate", "hard_vetting_record_candidates", "핵심 검증 전과"),
        ("economic_trust_record_rate", "economic_trust_record_candidates", "사기·횡령·배임·뇌물"),
        ("tax_arrears_5y_rate", "tax_arrears_5y_candidates", "최근 5년 체납"),
        ("money_trust_flag_rate", "money_trust_flag_candidates", "돈·신뢰 검증 플래그"),
        ("any_vetting_flag_rate", "any_vetting_flag_candidates", "전과·체납 검증 플래그"),
        ("uncontested_rate", "uncontested_candidates", "무투표 당선"),
    ]
    comparison = []
    for rate_key, count_key, label in metrics:
        dem = by_party["더불어민주당"]
        ppp = by_party["국민의힘"]
        dem_rate = rate_value(int(dem[count_key]), int(dem["total_candidates"]))
        ppp_rate = rate_value(int(ppp[count_key]), int(ppp["total_candidates"]))
        comparison.append({
            "metric": label,
            "democratic_count": dem[count_key],
            "democratic_rate": f"{dem_rate:.1f}%",
            "ppp_count": ppp[count_key],
            "ppp_rate": f"{ppp_rate:.1f}%",
            "higher_rate_party": "더불어민주당" if dem_rate > ppp_rate else "국민의힘" if ppp_rate > dem_rate else "동률",
            "rate_gap_pct_point": round(abs(dem_rate - ppp_rate), 2),
        })
    return {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "theme": "민주당과 국민의힘 어느 쪽이 더 헐겁게 공천했을까",
        "source_meta": meta,
        "party_summary": by_party,
        "comparison": comparison,
        "definitions": {
            "official_vetting_record": "전과 PDF 죄명 분류 결과 중 group='공직 검증'에 속한 유형이 1개 이상인 후보",
            "hard_vetting_record": "사기·횡령·배임·뇌물, 공직선거법·정치자금법·청탁금지법, 직권남용·허위공문서·문서위조·공용서류·공무원법, 조세·보조금 중 1개 이상",
            "money_trust_flag": "사기·횡령·배임·뇌물 전과 또는 최근 5년/현 체납 중 1개 이상",
            "any_vetting_flag": "공직 검증 전과 또는 최근 5년/현 체납 중 1개 이상",
        },
    }


def write_docs(out: Path, stats: dict[str, Any]) -> None:
    docs = out / "docs"
    docs.mkdir(parents=True, exist_ok=True)
    comp_lines = "\n".join(
        f"- {row['metric']}: 민주당 {row['democratic_count']}명({row['democratic_rate']}), "
        f"국힘 {row['ppp_count']}명({row['ppp_rate']}) — 비율 높은 쪽 {row['higher_rate_party']} "
        f"({row['rate_gap_pct_point']}%p 차)"
        for row in stats["comparison"]
    )
    (docs / "00_BROADCAST_BRIEF.md").write_text(f"""# 2시에 데이터 후속편 브리프

## 주제

민주당과 국민의힘 어느 쪽이 더 헐겁게 공천했을까.

## 기본 원칙

절대 인원만 보면 후보를 더 많이 낸 정당이 불리하다. 방송에서는 `절대 인원`과 `당내 후보 대비 비율`을 같이 말한다. 특히 지역 독점 구도 때문에 공천이 곧 당선에 가까운 `무투표 당선 후보`는 별도 지표로 분리한다.

## 핵심 비교표

{comp_lines}

## 방송에서 안전한 표현

- “선관위 후보자 공개정보와 전과 PDF 죄명 분류 결과 기준”
- “후보별 죄명·시점·형량을 인용할 때는 선관위 후보자 상세 페이지 원문 확인 필요”
- “출마 자격이 아니라 정당 공천 검증의 엄격성을 비교하는 분석”

## 해석 팁

정답을 하나로 단정하기보다 지표를 나눠 보여주는 편이 좋다. 예를 들어 `전체 전과 공개율`, `공직 검증 전과율`, `돈·신뢰 플래그`, `체납`, `무투표 당선 후보 중 검증 플래그`가 서로 다른 방향을 보일 수 있다. 그 차이 자체가 방송의 핵심이다.
""", encoding="utf-8")

    (docs / "01_CLAUDE_PROMPT.md").write_text("""# Claude 작업 지침

아래 데이터 패키지는 선관위 후보자 공개정보와 전과 PDF 죄명 분류 결과를 바탕으로, 더불어민주당과 국민의힘 공천 후보의 검증 지표를 비교하기 위한 것이다.

## 목표

〈2시에 데이터〉 후속편 주제 “민주당과 국힘 어느 쪽이 더 헐겁게 공천했을까” 방송 원고와 그래픽 구성을 만든다.

## 반드시 사용할 파일

- `data/party_vetting_key_stats.json`: 핵심 숫자와 정의
- `data/party_vetting_summary.csv`: 정당별 전체 비교
- `data/party_vetting_by_office.csv`: 직책별 보정 비교
- `data/party_vetting_by_region.csv`: 지역별 보정 비교
- `data/party_vetting_candidates.csv`: 후보별 근거 행
- `data/party_vetting_strong_cases.csv`: 방송 사례 후보

## 원고 원칙

1. 절대 인원과 비율을 함께 쓴다.
2. “전과자 정당”처럼 과도한 낙인을 찍지 않는다.
3. 비교의 핵심은 출마 자격이 아니라 공천 검증의 엄격성이다.
4. 전과 유형은 죄명 영역을 넓은 범주로 묶은 것이므로, 후보별 죄명·시점·형량을 구체적으로 말할 때는 선관위 후보자 상세 페이지 원문 확인 필요 문장을 붙인다.
5. 무투표 당선 후보는 별도 챕터로 다룬다. 공천이 곧 당선이 되는 지역에서는 정당 내부 검증의 책임이 더 커진다는 구조를 설명한다.

## 추천 구성

1. 오늘의 질문: 어느 정당이 더 헐겁게 공천했나
2. 비교 기준 설명: 절대 인원 vs 당내 비율
3. 전체 전과 공개율
4. 공직 검증 전과율
5. 돈·신뢰 지표: 사기·횡령·배임·뇌물 + 체납
6. 무투표 당선 후보 중 검증 플래그
7. 직책별/지역별로 보면 달라지는가
8. 결론: 한 줄 승패보다 정당 내부 검증 장치의 부재

## 산출물

- 방송용 12분 오프닝 원고
- 1시간 진행 큐시트
- 그래픽 8장 제목과 숫자
- 앵커가 말할 수 있는 조심스러운 결론 3개
""", encoding="utf-8")

    (docs / "02_GRAPHIC_IDEAS.md").write_text("""# 그래픽 제안

1. 정당별 후보 수: 민주당 vs 국민의힘
2. 전체 전과 공개율: 절대 인원과 당내 비율 병기
3. 공직 검증 전과율
4. 사기·횡령·배임·뇌물 후보 수와 비율
5. 최근 5년 체납 후보 수와 비율
6. 돈·신뢰 플래그: 경제범죄 또는 체납
7. 무투표 당선 후보 중 검증 플래그
8. 직책별 비교: 기초단체장/시도의원/구시군의원
9. 지역별 비교: 각 정당 우세 지역에서 공천 검증이 어떻게 보이는가
10. 결론 카드: “공천이 곧 당선인 곳에서 검증은 정당 안으로 들어간다”
""", encoding="utf-8")


def write_validation(out: Path, rows: list[dict[str, Any]], stats: dict[str, Any]) -> None:
    summary = stats["party_summary"]
    summary_total = sum(int(row["total_candidates"]) for row in summary.values())
    candidate_total = len(rows)
    flag_total = sum(1 for row in rows if row["has_any_vetting_flag"])
    summary_flag_total = sum(int(row["any_vetting_flag_candidates"]) for row in summary.values())
    lines = [
        "# 검증 보고",
        "",
        f"- 후보별 행 수: {candidate_total:,}",
        f"- 정당별 summary 후보 합계: {summary_total:,}",
        f"- 후보별 검증 플래그 합계: {flag_total:,}",
        f"- 정당별 summary 검증 플래그 합계: {summary_flag_total:,}",
        f"- 후보 행 수 일치: {'Y' if candidate_total == summary_total else 'N'}",
        f"- 검증 플래그 합계 일치: {'Y' if flag_total == summary_flag_total else 'N'}",
        "",
        "## 정당별 핵심 지표",
    ]
    for party in PARTIES:
        row = summary[party]
        lines.append(
            f"- {party}: 후보 {int(row['total_candidates']):,}명, "
            f"전과 공개 {row['criminal_record_candidates']}명({row['criminal_record_rate']}), "
            f"공직 검증 전과 {row['official_vetting_record_candidates']}명({row['official_vetting_record_rate']}), "
            f"최근 5년 체납 {row['tax_arrears_5y_candidates']}명({row['tax_arrears_5y_rate']}), "
            f"전과·체납 검증 플래그 {row['any_vetting_flag_candidates']}명({row['any_vetting_flag_rate']}), "
            f"무투표 {row['uncontested_candidates']}명({row['uncontested_rate']})"
        )
    (out / "validation_report.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> None:
    rows, meta = annotate_candidates()
    if OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)
    (OUT_DIR / "data").mkdir(parents=True, exist_ok=True)

    fields = [
        "huboid", "name", "party", "party_short", "office", "sdName", "sggName", "region",
        "criminal_record_count", "has_criminal_record", "ocr_categories",
        "official_vetting_categories", "economic_trust_categories", "election_integrity_categories",
        "public_admin_categories", "tax_public_money_categories", "traffic_safety_categories",
        "has_official_vetting_record", "has_hard_vetting_record", "has_economic_trust_record",
        "has_election_integrity_record", "has_public_admin_record", "has_tax_public_money_record",
        "tax_arrears_5y_thousand_krw", "tax_arrears_5y_display",
        "tax_arrears_current_thousand_krw", "tax_arrears_current_display",
        "has_tax_arrears_5y", "has_tax_arrears_current", "has_money_trust_flag",
        "has_any_vetting_flag", "is_uncontested_candidate", "job", "career1", "career2", "nec_detail_url",
    ]
    write_csv(OUT_DIR / "data" / "party_vetting_candidates.csv", rows, fields)
    write_csv(OUT_DIR / "data" / "party_vetting_summary.csv", aggregate(rows, ("party",)), list(aggregate(rows, ("party",))[0].keys()))
    write_csv(OUT_DIR / "data" / "party_vetting_by_office.csv", aggregate(rows, ("office", "party")), list(aggregate(rows, ("office", "party"))[0].keys()))
    write_csv(OUT_DIR / "data" / "party_vetting_by_region.csv", aggregate(rows, ("sdName", "party")), list(aggregate(rows, ("sdName", "party"))[0].keys()))
    write_csv(OUT_DIR / "data" / "party_vetting_category_counts.csv", category_counts(rows), [
        "party", "party_short", "category", "candidate_count", "party_total_candidates", "candidate_rate",
    ])
    strong = strongest_cases(rows)
    write_csv(OUT_DIR / "data" / "party_vetting_strong_cases.csv", strong, ["rank", *fields, "priority_reason"])

    stats = key_stats(rows, meta)
    write_json(OUT_DIR / "data" / "party_vetting_key_stats.json", stats)
    write_docs(OUT_DIR, stats)
    write_validation(OUT_DIR, rows, stats)
    (OUT_DIR / "README.md").write_text(f"""# 민주당 vs 국민의힘 공천 검증 비교 데이터 패키지

생성 시각: {datetime.now().isoformat(timespec="seconds")}

## 주제

민주당과 국힘 어느 쪽이 더 헐겁게 공천했을까.

## 기준

- 후보 스냅샷: `{meta["snapshot_file"]}`
- 후보자 공개정보: `{meta["candidate_details_file"]}`
- 전과 PDF 죄명 분류: `{meta["criminal_ocr_file"]}`
- 대상 정당: 더불어민주당, 국민의힘
- 대상 후보: 등록 상태 후보만 포함

## 핵심 파일

- `docs/00_BROADCAST_BRIEF.md`
- `docs/01_CLAUDE_PROMPT.md`
- `data/party_vetting_key_stats.json`
- `data/party_vetting_summary.csv`
- `data/party_vetting_by_office.csv`
- `data/party_vetting_by_region.csv`
- `data/party_vetting_candidates.csv`
- `data/party_vetting_strong_cases.csv`

## 주의

후보별 죄명·시점·형량을 인용할 때는 선관위 후보자 상세 페이지 원문 확인이 필요합니다.
""", encoding="utf-8")

    zip_path = OUT_DIR.with_suffix(".zip")
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in OUT_DIR.rglob("*"):
            zf.write(path, path.relative_to(OUT_DIR.parent))
    print(OUT_DIR)
    print(zip_path)


if __name__ == "__main__":
    main()
