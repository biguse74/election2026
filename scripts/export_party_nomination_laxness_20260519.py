#!/usr/bin/env python3
"""Build a Claude-ready May 19 package on party nomination laxness."""

from __future__ import annotations

import csv
import importlib.util
import json
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "exports" / "party_nomination_laxness_20260519"
DATA_DIR = OUT_DIR / "data"
OUT_MD = OUT_DIR / "CLAUDE_PARTY_NOMINATION_LAXNESS_20260519.md"
ZIP = ROOT / "exports" / "party_nomination_laxness_20260519.zip"

VETTING_STATS = ROOT / "exports" / "two_pm_party_vetting_package_20260518" / "data" / "party_vetting_key_stats.json"
UNCONTESTED_STATS = ROOT / "exports" / "uncontested_513_verification_20260518" / "uncontested_513_key_stats.json"

PARTIES = ["더불어민주당", "국민의힘", "조국혁신당", "진보당", "개혁신당"]
MAJOR_PARTIES = ["더불어민주당", "국민의힘"]
SHORT = {
    "더불어민주당": "민주당",
    "국민의힘": "국힘",
    "조국혁신당": "조국",
    "진보당": "진보",
    "개혁신당": "개혁",
}

ECONOMIC = {"사기", "횡령", "배임", "뇌물"}
ELECTION = {"공직선거법", "정치자금법", "청탁금지법"}
DOCUMENT_OFFICE = {"직권남용", "허위공문서·문서위조·공용서류", "국가공무원법", "지방공무원법"}
HARD_VETTING = ECONOMIC | ELECTION | DOCUMENT_OFFICE | {"조세", "보조금"}

FOCUS_CATEGORIES: list[tuple[str, set[str], str]] = [
    ("사기", {"사기"}, "돈·신뢰"),
    ("횡령", {"횡령"}, "돈·신뢰"),
    ("배임", {"배임"}, "돈·신뢰"),
    ("뇌물", {"뇌물"}, "돈·신뢰"),
    ("사기·횡령·배임·뇌물", ECONOMIC, "돈·신뢰 묶음"),
    ("공직선거법", {"공직선거법"}, "선거"),
    ("정치자금법", {"정치자금법"}, "선거"),
    ("국가보안법·집시법", {"국가보안법", "집시법"}, "시국·집회"),
    ("음주·위험운전", {"음주·위험운전"}, "안전"),
    ("무면허운전", {"무면허운전"}, "안전"),
    ("교통사고", {"교통사고"}, "안전"),
    ("성범죄", {"성범죄"}, "소수 사례"),
    ("마약", {"마약"}, "소수 사례"),
    ("도박", {"도박"}, "기타"),
    ("조세", {"조세"}, "체납·세금"),
    ("보조금", {"보조금"}, "공적 재원"),
    ("허위공문서·문서위조·공용서류", {"허위공문서·문서위조·공용서류"}, "문서·공직 신뢰"),
]

TAX_BUCKETS = [
    ("1원~100만원 미만", 1, 999),
    ("100만~500만원 미만", 1000, 4999),
    ("500만~1천만원 미만", 5000, 9999),
    ("1천만~5천만원 미만", 10000, 49999),
    ("5천만~1억원 미만", 50000, 99999),
    ("1억원 이상", 100000, 10**15),
]


def load_nomination_module():
    path = ROOT / "scripts" / "export_nomination_standards_claude_file.py"
    spec = importlib.util.spec_from_file_location("nomination_standards", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def rate(n: int, d: int) -> float:
    return round((n / d * 100) if d else 0, 4)


def rate_text(value: float) -> str:
    if 0 < value < 1:
        return f"{value:.2f}%"
    return f"{value:.1f}%"


def count_rate(n: int, d: int) -> str:
    return f"{n:,}명 ({rate_text(rate(n, d))})"


def amount_text(thousand: int) -> str:
    won = thousand * 1000
    if won >= 100_000_000:
        eok = won // 100_000_000
        man = (won % 100_000_000) // 10_000
        return f"{eok:,}억{man:,}만원" if man else f"{eok:,}억원"
    if won >= 10_000:
        return f"{won // 10_000:,}만원"
    return f"{won:,}원"


def csv_write(path: Path, rows: list[dict[str, Any]], fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def party_total(rows: list[dict[str, Any]], party: str) -> int:
    return sum(1 for row in rows if row["party"] == party)


def count(rows: list[dict[str, Any]], party: str, fn: Callable[[dict[str, Any]], bool]) -> int:
    return sum(1 for row in rows if row["party"] == party and fn(row))


def party_summary(rows: list[dict[str, Any]], important: set[str]) -> dict[str, dict[str, Any]]:
    summary: dict[str, dict[str, Any]] = {}
    for party in PARTIES:
        total = party_total(rows, party)
        criminal = count(rows, party, lambda r: r["criminal_count"] > 0)
        official = count(rows, party, lambda r: bool(r["categories"] & important))
        hard = count(rows, party, lambda r: bool(r["categories"] & HARD_VETTING))
        economic = count(rows, party, lambda r: bool(r["categories"] & ECONOMIC))
        election = count(rows, party, lambda r: bool(r["categories"] & ELECTION))
        tax5 = count(rows, party, lambda r: r["tax5"] > 0)
        tax_current = count(rows, party, lambda r: r["tax_current"] > 0)
        money_trust = count(rows, party, lambda r: bool(r["categories"] & ECONOMIC) or r["tax5"] > 0 or r["tax_current"] > 0)
        any_flag = count(rows, party, lambda r: bool(r["categories"] & important) or r["tax5"] > 0 or r["tax_current"] > 0)
        summary[party] = {
            "party": party,
            "party_short": SHORT[party],
            "total_candidates": total,
            "criminal_record_candidates": criminal,
            "criminal_record_rate": rate(criminal, total),
            "official_vetting_record_candidates": official,
            "official_vetting_record_rate": rate(official, total),
            "hard_vetting_record_candidates": hard,
            "hard_vetting_record_rate": rate(hard, total),
            "economic_trust_record_candidates": economic,
            "economic_trust_record_rate": rate(economic, total),
            "election_integrity_record_candidates": election,
            "election_integrity_record_rate": rate(election, total),
            "tax_arrears_5y_candidates": tax5,
            "tax_arrears_5y_rate": rate(tax5, total),
            "tax_arrears_current_candidates": tax_current,
            "tax_arrears_current_rate": rate(tax_current, total),
            "tax_arrears_5y_sum_thousand_krw": sum(row["tax5"] for row in rows if row["party"] == party),
            "tax_arrears_current_sum_thousand_krw": sum(row["tax_current"] for row in rows if row["party"] == party),
            "money_trust_flag_candidates": money_trust,
            "money_trust_flag_rate": rate(money_trust, total),
            "any_vetting_flag_candidates": any_flag,
            "any_vetting_flag_rate": rate(any_flag, total),
        }
    return summary


def build_major_comparison(summary: dict[str, dict[str, Any]], uncontested: dict[str, Any]) -> list[dict[str, Any]]:
    dem = summary["더불어민주당"]
    ppp = summary["국민의힘"]
    by_party = {row["party"]: row for row in uncontested["by_party"]}

    rows = [
        ("전과 공개", "criminal_record_candidates", "criminal_record_rate", "선관위 전과 공개정보에 1건 이상"),
        ("공직 검증 전과", "official_vetting_record_candidates", "official_vetting_record_rate", "전과 죄명 분류상 공직 검증 범주"),
        ("핵심 검증 전과", "hard_vetting_record_candidates", "hard_vetting_record_rate", "돈·선거·공직권한·조세·보조금"),
        ("사기·횡령·배임·뇌물", "economic_trust_record_candidates", "economic_trust_record_rate", "돈과 신뢰 범죄 묶음"),
        ("최근 5년 체납", "tax_arrears_5y_candidates", "tax_arrears_5y_rate", "최근 5년 체납액 1원 이상"),
        ("현 체납", "tax_arrears_current_candidates", "tax_arrears_current_rate", "현재 남아 있는 체납액 1원 이상"),
        ("돈·신뢰 플래그", "money_trust_flag_candidates", "money_trust_flag_rate", "사기·횡령·배임·뇌물 또는 체납"),
        ("전과·체납 검증 플래그", "any_vetting_flag_candidates", "any_vetting_flag_rate", "공직 검증 전과 또는 체납"),
    ]
    result: list[dict[str, Any]] = []
    for metric, count_key, rate_key, note in rows:
        dem_rate = dem[rate_key]
        ppp_rate = ppp[rate_key]
        higher = "국민의힘" if ppp_rate > dem_rate else "더불어민주당" if dem_rate > ppp_rate else "동률"
        result.append({
            "axis": metric,
            "democratic_count": dem[count_key],
            "democratic_rate": round(dem_rate, 2),
            "ppp_count": ppp[count_key],
            "ppp_rate": round(ppp_rate, 2),
            "higher_rate_party": higher,
            "rate_gap_pct_point": round(abs(ppp_rate - dem_rate), 2),
            "broadcast_note": note,
        })

    dem_u = by_party["더불어민주당"]
    ppp_u = by_party["국민의힘"]
    result.extend([
        {
            "axis": "무투표 당선 규모",
            "democratic_count": dem_u["무투표당선_후보수"],
            "democratic_rate": dem_u["정당전체후보대비_무투표비율"],
            "ppp_count": ppp_u["무투표당선_후보수"],
            "ppp_rate": ppp_u["정당전체후보대비_무투표비율"],
            "higher_rate_party": "더불어민주당",
            "rate_gap_pct_point": round(dem_u["정당전체후보대비_무투표비율"] - ppp_u["정당전체후보대비_무투표비율"], 2),
            "broadcast_note": "공천이 곧 당선에 가까워지는 구조의 절대 규모",
        },
        {
            "axis": "무투표 후보 중 전과·체납",
            "democratic_count": dem_u["전과또는체납_합집합"],
            "democratic_rate": dem_u["무투표후보내_전과또는체납비율"],
            "ppp_count": ppp_u["전과또는체납_합집합"],
            "ppp_rate": ppp_u["무투표후보내_전과또는체납비율"],
            "higher_rate_party": "국민의힘",
            "rate_gap_pct_point": round(ppp_u["무투표후보내_전과또는체납비율"] - dem_u["무투표후보내_전과또는체납비율"], 2),
            "broadcast_note": "무투표 후보 안에서 전과·체납 후보가 차지하는 비중",
        },
    ])
    return result


def build_category_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for label, cats, group in FOCUS_CATEGORIES:
        for party in PARTIES:
            total = party_total(rows, party)
            n = count(rows, party, lambda r, cats=cats: bool(r["categories"] & cats))
            out.append({
                "category": label,
                "group": group,
                "party": party,
                "party_short": SHORT[party],
                "candidate_count": n,
                "party_total_candidates": total,
                "candidate_rate_pct": round(rate(n, total), 2),
            })
    return out


def build_tax_bucket_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for field, label in [("tax5", "최근 5년 체납"), ("tax_current", "현 체납")]:
        for party in PARTIES:
            total = party_total(rows, party)
            party_rows = [row for row in rows if row["party"] == party]
            for bucket, low, high in TAX_BUCKETS:
                n = sum(1 for row in party_rows if low <= row[field] <= high)
                out.append({
                    "tax_type": label,
                    "bucket": bucket,
                    "party": party,
                    "party_short": SHORT[party],
                    "candidate_count": n,
                    "party_total_candidates": total,
                    "candidate_rate_pct": round(rate(n, total), 2),
                    "amount_sum_thousand_krw": sum(row[field] for row in party_rows if low <= row[field] <= high),
                })
    return out


def build_military_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out = []
    for party in PARTIES:
        party_rows = [row for row in rows if row["party"] == party and row["military"] in {"served", "not_served"}]
        total = len(party_rows)
        not_served = sum(1 for row in party_rows if row["military"] == "not_served")
        out.append({
            "party": party,
            "party_short": SHORT[party],
            "military_target_candidates": total,
            "not_served_candidates": not_served,
            "not_served_rate_pct": round(rate(not_served, total), 2),
        })
    return out


def markdown_table(headers: list[str], rows: list[list[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    lines += ["| " + " | ".join(row) + " |" for row in rows]
    return "\n".join(lines)


def md_major_table(comparison: list[dict[str, Any]]) -> str:
    rows = []
    for row in comparison:
        rows.append([
            row["axis"],
            f'{row["democratic_count"]:,}명 ({rate_text(row["democratic_rate"])})',
            f'{row["ppp_count"]:,}명 ({rate_text(row["ppp_rate"])})',
            row["higher_rate_party"],
            f'{row["rate_gap_pct_point"]:.2f}%p',
            row["broadcast_note"],
        ])
    return markdown_table(["비교 축", "민주당", "국민의힘", "비율상 높은 쪽", "격차", "해석"], rows)


def md_five_party(summary: dict[str, dict[str, Any]], military: list[dict[str, Any]]) -> str:
    military_by_party = {row["party"]: row for row in military}
    rows = []
    for party in PARTIES:
        item = summary[party]
        mil = military_by_party[party]
        rows.append([
            SHORT[party],
            f'{item["total_candidates"]:,}명',
            f'{item["criminal_record_candidates"]:,}명 ({rate_text(item["criminal_record_rate"])})',
            f'{item["official_vetting_record_candidates"]:,}명 ({rate_text(item["official_vetting_record_rate"])})',
            f'{item["money_trust_flag_candidates"]:,}명 ({rate_text(item["money_trust_flag_rate"])})',
            f'{item["tax_arrears_5y_candidates"]:,}명 ({rate_text(item["tax_arrears_5y_rate"])})',
            f'{mil["not_served_candidates"]:,}/{mil["military_target_candidates"]:,}명 ({rate_text(mil["not_served_rate_pct"])})',
        ])
    return markdown_table(["정당", "후보 수", "전과 공개", "공직 검증 전과", "돈·신뢰 플래그", "최근 5년 체납", "병역 미필"], rows)


def md_category_table(category_rows: list[dict[str, Any]]) -> str:
    by_key = {(row["category"], row["party"]): row for row in category_rows}
    rows = []
    for label, _, group in FOCUS_CATEGORIES:
        dem = by_key[(label, "더불어민주당")]
        ppp = by_key[(label, "국민의힘")]
        higher = "국힘" if ppp["candidate_rate_pct"] > dem["candidate_rate_pct"] else "민주당" if dem["candidate_rate_pct"] > ppp["candidate_rate_pct"] else "거의 같음"
        rows.append([
            label,
            group,
            f'{dem["candidate_count"]:,}명 ({rate_text(dem["candidate_rate_pct"])})',
            f'{ppp["candidate_count"]:,}명 ({rate_text(ppp["candidate_rate_pct"])})',
            higher,
        ])
    return markdown_table(["유형", "묶음", "민주당", "국민의힘", "비율상 높은 쪽"], rows)


def md_tax_buckets(tax_rows: list[dict[str, Any]], tax_type: str) -> str:
    by_key = {(row["bucket"], row["party"], row["tax_type"]): row for row in tax_rows}
    rows = []
    for bucket, _, _ in TAX_BUCKETS:
        dem = by_key[(bucket, "더불어민주당", tax_type)]
        ppp = by_key[(bucket, "국민의힘", tax_type)]
        higher = "국힘" if ppp["candidate_rate_pct"] > dem["candidate_rate_pct"] else "민주당" if dem["candidate_rate_pct"] > ppp["candidate_rate_pct"] else "같음"
        rows.append([
            bucket,
            f'{dem["candidate_count"]:,}명 ({rate_text(dem["candidate_rate_pct"])}, 합계 {amount_text(dem["amount_sum_thousand_krw"])})',
            f'{ppp["candidate_count"]:,}명 ({rate_text(ppp["candidate_rate_pct"])}, 합계 {amount_text(ppp["amount_sum_thousand_krw"])})',
            higher,
        ])
    return markdown_table(["금액 구간", "민주당", "국민의힘", "비율상 높은 쪽"], rows)


def md_uncontested(uncontested: dict[str, Any]) -> str:
    by_party = {row["party"]: row for row in uncontested["by_party"]}
    rows = []
    for party in ["더불어민주당", "국민의힘", "진보당"]:
        row = by_party[party]
        note = "그래픽 비교 포함" if party in MAJOR_PARTIES else "1명 표본, 본문 각주 처리"
        rows.append([
            SHORT.get(party, party),
            f'{row["정당전체후보수"]:,}명',
            f'{row["무투표당선_후보수"]:,}명 ({rate_text(row["정당전체후보대비_무투표비율"])})',
            f'{row["전과신고_후보수"]:,}명',
            f'{row["최근5년체납_후보수"]:,}명',
            f'{row["전과또는체납_합집합"]:,}명 ({rate_text(row["무투표후보내_전과또는체납비율"])})',
            note,
        ])
    return markdown_table(["정당", "전체 후보", "무투표 후보", "전과", "최근 5년 체납", "전과 또는 체납", "처리"], rows)


def build_markdown(
    summary: dict[str, dict[str, Any]],
    comparison: list[dict[str, Any]],
    category_rows: list[dict[str, Any]],
    tax_rows: list[dict[str, Any]],
    military_rows: list[dict[str, Any]],
    uncontested: dict[str, Any],
) -> str:
    generated = datetime.now().strftime("%Y-%m-%d %H:%M")
    return f"""# Claude 입력 파일: 어느 정당의 공천이 더 헐거웠나

생성: {generated} KST  
방송 예정: 2026년 5월 19일 〈2시의 데이터〉 후속편  
테마: 전과, 체납, 병역, 무투표 당선 구조로 본 정당별 공천 잣대

---

## 먼저 쓸 결론

한 문장으로는 이렇게 잡는 것이 가장 안전합니다.

> 전체 후보 기준 전과·체납·돈 문제 비율은 국민의힘이 더 높고, 무투표 당선 규모와 병역 미필 비율은 민주당이 더 높다. 다만 무투표 후보 안에서 전과 또는 체납 신고자가 차지하는 비율은 국민의힘이 더 높다.

따라서 “어느 한쪽만 헐거웠다”가 아니라 “헐거웠던 지점이 달랐다”로 가는 것이 좋습니다. 방송 제목은 세게 가더라도 본문은 축별로 나눠야 반박을 견딥니다.

## 방송용 핵심 숫자

- 양당 후보 분모: 민주당 3,214명, 국민의힘 2,744명.
- 전과 공개율: 민주당 29.6%, 국민의힘 33.3%.
- 공직 검증 전과율: 민주당 14.9%, 국민의힘 18.2%.
- 사기·횡령·배임·뇌물 분류 전과: 민주당 48명(1.5%), 국민의힘 56명(2.0%).
- 최근 5년 체납 이력: 민주당 391명(12.2%), 국민의힘 451명(16.4%).
- 전과 또는 체납 검증 플래그: 민주당 799명(24.9%), 국민의힘 853명(31.1%).
- 병역 미필: 민주당 252명(병역 대상 12.3%), 국민의힘 197명(10.1%).
- 무투표 당선: 전체 513명. 민주당 314명, 국민의힘 198명.
- 무투표 후보 중 전과 또는 체납 신고: 민주당 106명(33.8%), 국민의힘 81명(40.9%).

## 양당 비교 본표

{md_major_table(comparison)}

## 5개 정당 참고표

이 표는 입체감을 주기 위한 참고값입니다. 조국혁신당·진보당·개혁신당은 분모가 작아 비율이 튈 수 있으므로 메인 그래픽에서는 양당 비교를 중심으로 두는 편이 좋습니다.

{md_five_party(summary, military_rows)}

## 전과 유형별 양당 비교

{md_category_table(category_rows)}

### 유형별 읽는 법

- 돈·신뢰 범죄 묶음은 국민의힘이 높습니다. 사기·횡령·배임·뇌물을 따로 봐도 국민의힘 쪽이 대부분 더 높게 나옵니다.
- 시국·집회 전과는 민주당이 국민의힘보다 훨씬 높습니다. 다만 이 범주는 사기·횡령·뇌물과 성격이 다르므로 같은 “검증 실패”로 뭉개면 안 됩니다.
- 공직선거법은 양당 모두 비슷합니다. 민주당은 70명, 국민의힘은 64명이고 비율은 국민의힘이 근소하게 높습니다.
- 성범죄와 마약은 국민의힘에서만 소수 확인됩니다. 숫자가 작으므로 “국민의힘에서만 확인된 소수 사례” 정도가 적절합니다.

## 체납액 규모별 비교

### 최근 5년 체납

{md_tax_buckets(tax_rows, "최근 5년 체납")}

### 현 체납

{md_tax_buckets(tax_rows, "현 체납")}

### 체납 해석

- 최근 5년 체납은 거의 모든 구간에서 국민의힘이 더 높습니다.
- 최근 5년 1억원 이상 고액 체납은 민주당 9명, 국민의힘 8명으로 인원은 민주당이 1명 많지만, 정당 후보 수 대비 비율은 거의 같습니다.
- 현 체납 총액은 민주당이 더 큽니다. 민주당 현 체납 합계 6억6,271만8천원, 국민의힘 4억9,543만7천원입니다.
- 현 1억원 이상 체납은 민주당 2명, 국민의힘 1명입니다. 이 지점은 민주당의 약점으로 따로 짚을 수 있습니다.

## 무투표 당선 구조

{md_uncontested(uncontested)}

### 무투표 해석

- 무투표 당선의 절대 규모와 정당 후보 대비 비율은 민주당이 높습니다.
- 하지만 무투표 후보 안에서 전과 또는 체납 신고자가 차지하는 비율은 국민의힘이 높습니다.
- 진보당은 무투표 후보가 1명이고 그 1명이 전과·체납에 모두 걸려 100%로 보입니다. 이 값은 그래프에서 빼고 각주로 처리해야 왜곡이 줄어듭니다.

## 방송 프레임 제안

### 1막: “전과·체납 비율은 국힘이 높다”

전과 공개, 공직 검증 전과, 사기·횡령·배임·뇌물, 최근 5년 체납, 전과·체납 검증 플래그가 모두 국민의힘 쪽에서 높게 나온다. 이 축에서는 국민의힘 공천이 더 느슨해 보인다고 말할 수 있다.

### 2막: “민주당의 약점은 무투표 규모와 병역”

무투표 당선은 민주당 314명, 국민의힘 198명이다. 공천이 당선으로 직행하는 구조의 절대 규모는 민주당이 더 크다. 병역 미필 비율도 민주당 12.3%, 국민의힘 10.1%로 민주당이 높다.

### 3막: “무투표 안의 질을 보면 다시 국힘이 높다”

무투표 당선 후보 중 전과 또는 체납을 신고한 후보는 민주당 106명, 국민의힘 81명이다. 절대 인원은 민주당이 많지만, 무투표 후보 내부 비율은 민주당 33.8%, 국민의힘 40.9%다.

### 4막: “제3정당은 보조 발견”

진보당은 전체 전과 공개율과 시국·집회 전과, 병역 미필률이 높다. 조국혁신당은 공직 검증 전과율과 음주·무면허가 눈에 띈다. 개혁신당은 후보 수가 적지만 돈·신뢰 범죄와 현 체납 비율이 튄다. 다만 분모가 작아 양당과 같은 막대그래프로 놓으면 왜곡될 수 있다.

## 제목 후보

1. 전과·체납은 국힘, 무투표는 민주
2. 공천 잣대, 어디가 더 느슨했나
3. 전과·체납·병역으로 본 양당 공천
4. 검증자료로 본 공천의 빈틈
5. 돈 문제엔 국힘, 무투표엔 민주

## 그래픽 제안

1. 후보 분모 카드: 민주당 3,214명 vs 국민의힘 2,744명.
2. 전과 공개율 막대: 29.6% vs 33.3%.
3. 공직 검증 전과율 막대: 14.9% vs 18.2%.
4. 돈·신뢰 플래그 막대: 13.4% vs 18.1%.
5. 최근 5년 체납 구간별 누적 막대: 색을 금액 구간별로 구분.
6. 무투표 당선 규모: 민주당 314명 vs 국민의힘 198명.
7. 무투표 후보 중 전과·체납 비율: 민주당 33.8% vs 국민의힘 40.9%.
8. 병역 미필률: 민주당 12.3% vs 국민의힘 10.1%.
9. 시국·집회 전과: 민주당이 높은 축으로 별도 표시.
10. 제3정당 참고: “분모 작음” 표시를 크게 넣고 보조 박스로 처리.

## 클로드에게 시킬 일

아래 요청을 그대로 붙여 쓰면 됩니다.

```
위 데이터만 근거로 5월 19일 〈2시의 데이터〉 후속편 방송 자료를 작성해줘.

주제는 “민주당과 국민의힘, 어느 쪽 공천이 더 헐거웠을까”다.

작성물:
1. 12분 오프닝 원고
2. 1시간 방송 큐시트
3. 그래픽 10장 구성안
4. 제목 후보 10개
5. 기사형 리드 3개
6. 과잉 일반화를 피하는 표현 10개
7. 민주당·국민의힘·제3정당별 한 줄 평가

작성 원칙:
- 전과·체납·돈 문제 비율은 국민의힘이 높다는 점을 분명히 쓴다.
- 무투표 당선 규모와 병역 미필은 민주당이 높다는 점도 같이 쓴다.
- “어느 정당이 범죄자를 공천했다”처럼 단정하지 말고, “선관위 공개정보 기준 전과·체납 신고 후보 비율”이라고 쓴다.
- 성범죄·마약은 숫자가 작으므로 소수 사례로만 언급한다.
- 시국·집회 전과는 돈·신뢰 범죄와 성격이 다르므로 별도 축으로 설명한다.
- 진보당 100% 같은 작은 분모 수치는 메인 그래프에 넣지 말고 각주로 처리한다.
```

## 사용한 원자료와 기준

- 선관위 후보자 공개정보 스냅샷: `data/candidates/20260603/snapshot_20260518.json`
- 후보자 상세 공개정보: `data/candidate_details.json`
- 전과 PDF 죄명 분류 결과: `data/criminal_ocr.json`
- 무투표 당선 513명 검증 패키지: `exports/uncontested_513_verification_20260518/uncontested_513_key_stats.json`
- 양당 공천 검증 패키지: `exports/two_pm_party_vetting_package_20260518/data/party_vetting_key_stats.json`

주의: 전과 유형은 죄명 영역을 넓은 범주로 묶은 것이다. 후보 한 명이 여러 범주에 동시에 들어갈 수 있다. 후보별 죄명·시점·형량을 구체적으로 인용할 때는 선관위 후보자 상세 페이지 원문 확인이 필요하다.
"""


def main() -> None:
    nomination = load_nomination_module()
    rows, important = nomination.make_rows()
    summary = party_summary(rows, important)
    uncontested = load_json(UNCONTESTED_STATS)
    prior_vetting = load_json(VETTING_STATS)
    comparison = build_major_comparison(summary, uncontested)
    category_rows = build_category_rows(rows)
    tax_rows = build_tax_bucket_rows(rows)
    military_rows = build_military_rows(rows)

    DATA_DIR.mkdir(parents=True, exist_ok=True)

    major_csv = [
        {
            **row,
            "democratic_rate": rate_text(row["democratic_rate"]),
            "ppp_rate": rate_text(row["ppp_rate"]),
        }
        for row in comparison
    ]
    csv_write(DATA_DIR / "major_party_laxness_summary.csv", major_csv, [
        "axis", "democratic_count", "democratic_rate", "ppp_count", "ppp_rate",
        "higher_rate_party", "rate_gap_pct_point", "broadcast_note",
    ])

    five_party_rows = []
    for party in PARTIES:
        item = summary[party]
        five_party_rows.append({
            "party": party,
            "party_short": SHORT[party],
            "total_candidates": item["total_candidates"],
            "criminal_record_candidates": item["criminal_record_candidates"],
            "criminal_record_rate_pct": round(item["criminal_record_rate"], 2),
            "official_vetting_record_candidates": item["official_vetting_record_candidates"],
            "official_vetting_record_rate_pct": round(item["official_vetting_record_rate"], 2),
            "economic_trust_record_candidates": item["economic_trust_record_candidates"],
            "economic_trust_record_rate_pct": round(item["economic_trust_record_rate"], 2),
            "tax_arrears_5y_candidates": item["tax_arrears_5y_candidates"],
            "tax_arrears_5y_rate_pct": round(item["tax_arrears_5y_rate"], 2),
            "tax_arrears_current_candidates": item["tax_arrears_current_candidates"],
            "tax_arrears_current_rate_pct": round(item["tax_arrears_current_rate"], 2),
            "money_trust_flag_candidates": item["money_trust_flag_candidates"],
            "money_trust_flag_rate_pct": round(item["money_trust_flag_rate"], 2),
            "any_vetting_flag_candidates": item["any_vetting_flag_candidates"],
            "any_vetting_flag_rate_pct": round(item["any_vetting_flag_rate"], 2),
        })
    csv_write(DATA_DIR / "five_party_reference_summary.csv", five_party_rows, [
        "party", "party_short", "total_candidates",
        "criminal_record_candidates", "criminal_record_rate_pct",
        "official_vetting_record_candidates", "official_vetting_record_rate_pct",
        "economic_trust_record_candidates", "economic_trust_record_rate_pct",
        "tax_arrears_5y_candidates", "tax_arrears_5y_rate_pct",
        "tax_arrears_current_candidates", "tax_arrears_current_rate_pct",
        "money_trust_flag_candidates", "money_trust_flag_rate_pct",
        "any_vetting_flag_candidates", "any_vetting_flag_rate_pct",
    ])

    csv_write(DATA_DIR / "category_by_party_focus.csv", category_rows, [
        "category", "group", "party", "party_short", "candidate_count",
        "party_total_candidates", "candidate_rate_pct",
    ])
    csv_write(DATA_DIR / "tax_amount_buckets_by_party.csv", tax_rows, [
        "tax_type", "bucket", "party", "party_short", "candidate_count",
        "party_total_candidates", "candidate_rate_pct", "amount_sum_thousand_krw",
    ])
    csv_write(DATA_DIR / "military_by_party.csv", military_rows, [
        "party", "party_short", "military_target_candidates",
        "not_served_candidates", "not_served_rate_pct",
    ])

    uncontested_rows = uncontested["by_party"]
    csv_write(DATA_DIR / "uncontested_party_laxness.csv", uncontested_rows, [
        "party", "정당전체후보수", "무투표당선_후보수", "정당전체후보대비_무투표비율",
        "전과신고_후보수", "최근5년체납_후보수", "현체납_후보수",
        "전과또는체납_합집합", "무투표후보내_전과또는체납비율",
    ])

    key_stats = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "theme": "민주당과 국민의힘 어느 쪽 공천이 더 헐거웠을까",
        "major_party_conclusion": "전과·체납·돈 문제 비율은 국민의힘이 높고, 무투표 당선 규모와 병역 미필 비율은 민주당이 높다.",
        "major_party_comparison": comparison,
        "five_party_summary": five_party_rows,
        "military_summary": military_rows,
        "uncontested_key_stats": {
            "total_uncontested_candidates": uncontested["total_uncontested_candidates"],
            "criminal_or_tax_union_candidates": uncontested["criminal_or_tax_union_candidates"],
            "by_party": uncontested["by_party"],
        },
        "prior_package_crosscheck": {
            "file": str(VETTING_STATS.relative_to(ROOT)),
            "generated_at": prior_vetting.get("generated_at"),
            "note": "무투표 당선 수는 513명 재검증 패키지의 최신값으로 보정했다.",
        },
    }
    (DATA_DIR / "key_stats.json").write_text(json.dumps(key_stats, ensure_ascii=False, indent=2), encoding="utf-8")

    OUT_MD.write_text(
        build_markdown(summary, comparison, category_rows, tax_rows, military_rows, uncontested),
        encoding="utf-8",
    )

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
