#!/usr/bin/env python3
"""Create a single Claude-ready brief on how party nomination standards differed."""

from __future__ import annotations

import json
import zipfile
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Callable


ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "exports" / "party_nomination_standards_claude_20260518.md"
ZIP = ROOT / "exports" / "party_nomination_standards_claude_20260518.zip"

SNAPSHOT = ROOT / "data" / "candidates" / "20260603" / "snapshot_20260518.json"
DETAILS = ROOT / "data" / "candidate_details.json"
CRIMINAL = ROOT / "data" / "criminal_ocr.json"
CONSTITUENCIES = ROOT / "data" / "constituencies.json"

PARTIES = ["더불어민주당", "국민의힘", "조국혁신당", "진보당", "개혁신당"]
SHORT = {
    "더불어민주당": "민주당",
    "국민의힘": "국힘",
    "조국혁신당": "조국",
    "진보당": "진보",
    "개혁신당": "개혁",
}
UNCONTESTED_TYPES = {"4", "5", "6", "8", "9"}

GROUPS: dict[str, list[str]] = {
    "돈·신뢰 범죄": ["사기", "횡령", "배임", "뇌물"],
    "선거·정치자금": ["공직선거법", "정치자금법", "청탁금지법"],
    "시국·집회": ["국가보안법", "집시법"],
    "문서·공직권한": ["직권남용", "허위공문서·문서위조·공용서류", "국가공무원법", "지방공무원법"],
    "음주·무면허": ["음주·위험운전", "무면허운전"],
    "성범죄": ["성범죄"],
    "마약·도박": ["마약", "도박"],
}
CATEGORIES = [
    "사기", "횡령", "배임", "뇌물",
    "공직선거법", "정치자금법", "청탁금지법",
    "직권남용", "허위공문서·문서위조·공용서류", "조세", "보조금",
    "음주·위험운전", "무면허운전", "교통사고",
    "폭력", "공무집행방해", "업무방해",
    "성범죄", "국가보안법", "집시법", "마약", "도박", "명예훼손", "모욕",
]
TAX_BUCKETS = [
    ("1원~100만원 미만", 1, 999),
    ("100만~500만원 미만", 1000, 4999),
    ("500만~1천만원 미만", 5000, 9999),
    ("1천만~5천만원 미만", 10000, 49999),
    ("5천만~1억원 미만", 50000, 99999),
    ("1억원 이상", 100000, 10**15),
]


def load_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def parse_int(value: Any) -> int:
    text = str(value or "").replace(",", "").strip()
    digits = "".join(ch for ch in text if ch.isdigit() or ch == "-")
    return int(digits or 0)


def parse_criminal(value: Any) -> int:
    text = str(value or "").strip()
    if text in {"", "없음", "0", "0건"}:
        return 0
    digits = "".join(ch for ch in text if ch.isdigit())
    return int(digits or 0)


def pct(n: int, d: int) -> str:
    return f"{(n / d * 100) if d else 0:.1f}%"


def pct_value(n: int, d: int) -> float:
    return round((n / d * 100) if d else 0, 4)


def rate_text(value: float) -> str:
    if 0 < value < 1:
        return f"{value:.2f}%"
    return f"{value:.1f}%"


def amount_text(thousand: int) -> str:
    if not thousand:
        return "0원"
    won = thousand * 1000
    if won >= 100_000_000:
        eok = won // 100_000_000
        man = (won % 100_000_000) // 10_000
        return f"{eok:,}억{man:,}만원" if man else f"{eok:,}억원"
    if won >= 10_000:
        return f"{won // 10_000:,}만원"
    return f"{won:,}원"


def is_active(candidate: dict[str, Any]) -> bool:
    return not candidate.get("status") or candidate.get("status") == "등록"


def seat_key(row: dict[str, Any]) -> str:
    return f'{row.get("sgTypecode")}|{row.get("sdName")}|{row.get("sggName")}'


def build_uncontested_set(candidates: list[dict[str, Any]], constituencies: list[dict[str, Any]]) -> set[str]:
    seats: dict[str, int] = {}
    counts: Counter[str] = Counter()
    by_key: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for seat in constituencies:
        if str(seat.get("sgTypecode")) in UNCONTESTED_TYPES:
            seats[seat_key(seat)] = parse_int(seat.get("sggJungsu")) or 1
    for candidate in candidates:
        if not is_active(candidate) or str(candidate.get("sgTypecode")) not in UNCONTESTED_TYPES:
            continue
        key = seat_key(candidate)
        counts[key] += 1
        by_key[key].append(candidate)
    result: set[str] = set()
    for key, seat_count in seats.items():
        rows = by_key.get(key, [])
        count = counts[key]
        if not count:
            continue
        sg_type = key.split("|", 1)[0]
        parties = {row.get("jdName") or "무소속" for row in rows}
        single_party_pr = sg_type in {"8", "9"} and count > seat_count and len(parties) == 1
        if count <= seat_count or single_party_pr:
            for row in rows:
                if row.get("huboid"):
                    result.add(str(row["huboid"]))
    return result


def military_bucket(text: Any) -> str:
    value = str(text or "")
    if "군복무를 마치지 아니한" in value or "미필" in value:
        return "not_served"
    if "군복무를 마친" in value or "군필" in value:
        return "served"
    if "비대상" in value or "해당없음" in value:
        return "non_target"
    return "unknown"


def make_rows() -> tuple[list[dict[str, Any]], set[str]]:
    snapshot = load_json(SNAPSHOT)
    details = {str(row.get("huboid")): row for row in load_json(DETAILS).get("details", [])}
    criminal = load_json(CRIMINAL)
    criminal_records = {str(row.get("huboid")): row for row in criminal.get("records", [])}
    important = {
        row["category"]
        for row in criminal.get("categories", [])
        if row.get("group") == "공직 검증"
    }
    active = [row for row in snapshot["candidates"] if is_active(row)]
    uncontested = build_uncontested_set(active, load_json(CONSTITUENCIES))
    rows = []
    for candidate in active:
        if candidate.get("jdName") not in PARTIES:
            continue
        huboid = str(candidate.get("huboid") or "")
        detail = details.get(huboid, {})
        disclosures = detail.get("disclosures", {})
        record = criminal_records.get(huboid, {})
        cats = set(record.get("categories") or [])
        rows.append({
            "huboid": huboid,
            "name": candidate.get("name", ""),
            "party": candidate.get("jdName", ""),
            "short": SHORT[candidate.get("jdName", "")],
            "gender": candidate.get("gender", ""),
            "criminal_count": parse_criminal(disclosures.get("criminal_record")),
            "categories": cats,
            "tax5": parse_int(disclosures.get("tax_arrears_5y_thousand_krw")),
            "tax_current": parse_int(disclosures.get("tax_arrears_current_thousand_krw")),
            "military": military_bucket(disclosures.get("military")),
            "is_uncontested": huboid in uncontested,
            "official_vetting": bool(cats & important),
        })
    return rows, important


def count_by_party(rows: list[dict[str, Any]], fn: Callable[[dict[str, Any]], bool]) -> dict[str, int]:
    return {party: sum(1 for row in rows if row["party"] == party and fn(row)) for party in PARTIES}


def party_total(rows: list[dict[str, Any]], party: str) -> int:
    return sum(1 for row in rows if row["party"] == party)


def metric_table(rows: list[dict[str, Any]], metrics: list[tuple[str, Callable[[dict[str, Any]], bool]]]) -> str:
    header = "| 지표 | " + " | ".join(SHORT[p] for p in PARTIES) + " | 가장 높은 비율 |\n"
    sep = "|" + "---|" * (len(PARTIES) + 2) + "\n"
    body = []
    for label, fn in metrics:
        counts = count_by_party(rows, fn)
        cells = []
        ranked = []
        for party in PARTIES:
            total = party_total(rows, party)
            n = counts[party]
            rate = pct_value(n, total)
            ranked.append((rate, n, SHORT[party]))
            cells.append(f"{n:,}명 ({rate_text(rate)})")
        top = sorted(ranked, reverse=True)[0]
        body.append("| " + " | ".join([label, *cells, f"{top[2]} {rate_text(top[0])}"]) + " |")
    return header + sep + "\n".join(body)


def tax_bucket_table(rows: list[dict[str, Any]], field: str) -> str:
    title = "최근 5년 체납" if field == "tax5" else "현 체납"
    lines = [f"### {title} 금액 구간", ""]
    lines.append("| 구간 | " + " | ".join(SHORT[p] for p in PARTIES) + " | 비율상 높은 정당 |")
    lines.append("|" + "---|" * (len(PARTIES) + 2))
    for label, low, high in TAX_BUCKETS:
        cells = []
        ranked = []
        for party in PARTIES:
            total = party_total(rows, party)
            party_rows = [row for row in rows if row["party"] == party]
            items = [row for row in party_rows if low <= row[field] <= high]
            rate = pct_value(len(items), total)
            total_amount = sum(row[field] for row in items)
            ranked.append((rate, len(items), SHORT[party]))
            cells.append(f"{len(items):,}명 ({rate:.2f}%, 합계 {amount_text(total_amount)})")
        top = sorted(ranked, reverse=True)[0]
        lines.append("| " + " | ".join([label, *cells, f"{top[2]} {top[0]:.2f}%"]) + " |")
    return "\n".join(lines)


def category_table(rows: list[dict[str, Any]]) -> str:
    lines = [
        "| 전과 유형 | 민주당 | 국힘 | 조국 | 진보 | 개혁 | 비율상 높은 정당 |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for category in CATEGORIES:
        cells = []
        ranked = []
        for party in PARTIES:
            total = party_total(rows, party)
            n = sum(1 for row in rows if row["party"] == party and category in row["categories"])
            rate = pct_value(n, total)
            ranked.append((rate, n, SHORT[party]))
            cells.append(f"{n:,}명 ({rate:.2f}%)")
        top = sorted(ranked, reverse=True)[0]
        lines.append("| " + " | ".join([category, *cells, f"{top[2]} {top[0]:.2f}%"]) + " |")
    return "\n".join(lines)


def top_cases(rows: list[dict[str, Any]], field: str, limit: int = 10) -> str:
    title = "최근 5년 체납" if field == "tax5" else "현 체납"
    lines = [f"### {title} 상위 {limit}명", ""]
    lines.append("| 순위 | 정당 | 후보 | 금액 |")
    lines.append("|---:|---|---|---:|")
    ranked = sorted([row for row in rows if row[field] > 0], key=lambda row: row[field], reverse=True)[:limit]
    for idx, row in enumerate(ranked, 1):
        lines.append(f"| {idx} | {row['short']} | {row['name']} | {amount_text(row[field])} |")
    return "\n".join(lines)


def build_markdown() -> str:
    rows, _important = make_rows()
    totals = {party: party_total(rows, party) for party in PARTIES}
    generated = datetime.now().isoformat(timespec="seconds")
    metrics = [
        ("전과 공개", lambda r: r["criminal_count"] > 0),
        ("공직 검증 전과", lambda r: r["official_vetting"]),
        ("돈·신뢰 범죄", lambda r: any(cat in r["categories"] for cat in GROUPS["돈·신뢰 범죄"])),
        ("선거·정치자금", lambda r: any(cat in r["categories"] for cat in GROUPS["선거·정치자금"])),
        ("시국·집회", lambda r: any(cat in r["categories"] for cat in GROUPS["시국·집회"])),
        ("문서·공직권한", lambda r: any(cat in r["categories"] for cat in GROUPS["문서·공직권한"])),
        ("음주·무면허", lambda r: any(cat in r["categories"] for cat in GROUPS["음주·무면허"])),
        ("성범죄", lambda r: "성범죄" in r["categories"]),
        ("마약·도박", lambda r: any(cat in r["categories"] for cat in GROUPS["마약·도박"])),
        ("최근 5년 체납", lambda r: r["tax5"] > 0),
        ("현 체납", lambda r: r["tax_current"] > 0),
        ("최근 5년 1천만원 이상 체납", lambda r: r["tax5"] >= 10_000),
        ("최근 5년 1억원 이상 체납", lambda r: r["tax5"] >= 100_000),
        ("현 1천만원 이상 체납", lambda r: r["tax_current"] >= 10_000),
        ("현 1억원 이상 체납", lambda r: r["tax_current"] >= 100_000),
        ("무투표 당선", lambda r: r["is_uncontested"]),
    ]
    military_lines = [
        "| 정당 | 병역 대상 남성 | 미필 | 미필률 |",
        "|---|---:|---:|---:|",
    ]
    for party in PARTIES:
        party_rows = [row for row in rows if row["party"] == party and row["gender"] == "남"]
        eligible = [row for row in party_rows if row["military"] in {"served", "not_served"}]
        not_served = [row for row in eligible if row["military"] == "not_served"]
        military_lines.append(
            f"| {SHORT[party]} | {len(eligible):,}명 | {len(not_served):,}명 | {pct(len(not_served), len(eligible))} |"
        )
    totals_line = ", ".join(f"{SHORT[p]} {totals[p]:,}명" for p in PARTIES)
    return f"""# Claude 입력 파일: 정당별 공천 잣대 비교

생성 시각: {generated}

## 방송 주제

정당 공천 잣대는 어떻게 달랐나. 전과·체납·병역·무투표 당선 데이터를 종합해, 각 정당이 어떤 유형의 리스크에 더 관대했는지 비교한다.

## 사용 원자료

- 선관위 후보 등록 스냅샷: `data/candidates/20260603/snapshot_20260518.json`
- 선관위 후보자 공개정보: `data/candidate_details.json`
- 전과 PDF 죄명 분류 결과: `data/criminal_ocr.json`
- 선거구별 정원 자료: `data/constituencies.json`

후보별 죄명·시점·형량을 인용할 때는 선관위 후보자 상세 페이지 원문 확인이 필요하다.

## 분석 대상 정당과 분모

{totals_line}

제3정당은 분모가 작아 비율이 크게 출렁일 수 있다. 원고에서는 절대 인원과 비율을 반드시 함께 쓴다.

## 핵심 판단

1. 국민의힘은 체납 전반, 돈·신뢰 범죄, 음주·무면허, 조세, 성범죄·마약 소수 사례에서 더 관대한 공천으로 보인다.
2. 민주당은 무투표 당선 규모, 공무집행방해·업무방해, 보조금, 현 초고액 체납 일부, 병역 미필에서 약점이 보인다.
3. 조국혁신당은 후보 수는 적지만 공직 검증 전과율과 음주·무면허 비율이 높게 나온다.
4. 진보당은 전체 전과 공개율, 시국·집회 전과, 공무집행방해·업무방해, 병역 미필률이 압도적으로 높다. 다만 시국·집회 전과는 사기·횡령·뇌물과 성격이 다르므로 분리 설명해야 한다.
5. 개혁신당은 전체 전과율은 낮지만 돈·신뢰 범죄와 현 체납 비율이 분모 대비 튄다.

## 정당별 핵심 지표

{metric_table(rows, metrics)}

## 병역 미필

{chr(10).join(military_lines)}

## 체납 금액 구간

{tax_bucket_table(rows, "tax5")}

{tax_bucket_table(rows, "tax_current")}

{top_cases(rows, "tax5")}

{top_cases(rows, "tax_current")}

## 전과 유형별 비교

{category_table(rows)}

## 원고 작성 지침

### 프레임

“어느 정당이 더 나쁘다”보다 “정당마다 공천에서 관대하게 넘긴 리스크의 종류가 달랐다”로 쓴다. 양당 비교에서는 국민의힘이 전과·체납 쪽에서 더 느슨해 보이지만, 제3정당까지 넣으면 진보당의 시국·집회 전과와 조국혁신당의 공직 검증 전과율이 새롭게 보인다.

### 권장 제목

- 체납·경제범죄는 국힘, 시국전과는 진보·민주…정당마다 달랐던 공천 잣대
- 돈 문제엔 국힘, 시국 전과엔 진보·민주, 음주엔 국힘·조국…공천 검증의 다른 기준
- “공천 잣대는 같았나” 전과·체납·병역으로 본 5개 정당 후보 검증

### 그래픽 제안

1. 5개 정당 후보 수와 분모 경고
2. 공직 검증 전과율: 조국, 국힘, 민주, 진보, 개혁
3. 돈·신뢰 범죄: 개혁·국힘·조국 순, 단 개혁/조국은 분모 작음 표시
4. 체납 전반: 국힘 우위
5. 고액 체납: 최근 5년 1억원 이상은 민주·국힘이 사실상 비슷, 현 1억원 이상은 민주 2명·국힘 1명
6. 시국·집회 전과: 진보 압도, 민주·조국이 뒤따름
7. 음주·무면허: 국힘과 조국이 높은 축
8. 성범죄·마약: 국힘에서만 확인된 소수 사례

### 주의 문구

전과 유형은 죄명 영역을 넓은 범주로 묶은 것이다. 후보 한 명이 여러 범주에 동시에 들어갈 수 있다. 후보별 죄명·시점·형량을 구체적으로 말할 때는 선관위 후보자 상세 페이지 원문 확인이 필요하다.

## Claude에게 요청할 산출물

1. 12분 오프닝 원고
2. 1시간 방송 큐시트
3. 그래픽 10장 제목과 각 장에 들어갈 숫자
4. “의외의 발견” 5개
5. 과잉 일반화를 피하는 표현 10개
6. 각 정당별 공천 잣대 한 줄 평가
"""


def main() -> None:
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(build_markdown(), encoding="utf-8")
    if ZIP.exists():
        ZIP.unlink()
    with zipfile.ZipFile(ZIP, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.write(OUT, OUT.name)
    print(OUT)
    print(ZIP)


if __name__ == "__main__":
    main()
