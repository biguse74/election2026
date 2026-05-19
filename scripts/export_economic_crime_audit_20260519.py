from __future__ import annotations

import csv
import json
import re
import zipfile
from collections import defaultdict
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
CRIMINAL = ROOT / "data" / "criminal_ocr.json"
CANDIDATES = ROOT / "data" / "candidates" / "20260603" / "snapshot_20260519.json"
DETAILS = ROOT / "data" / "candidate_details.json"
CONSTITUENCIES = ROOT / "data" / "constituencies.json"
OCR_SCRIPT = ROOT / "scripts" / "ocr_criminal_records.py"
OUT = ROOT / "exports" / "economic_crime_classification_audit_20260519"

MAJOR_PARTIES = ["더불어민주당", "국민의힘"]
FIVE_PARTIES = ["더불어민주당", "국민의힘", "조국혁신당", "진보당", "개혁신당"]
TARGET_CATEGORIES = ["사기", "횡령", "배임", "뇌물"]
PROPORTIONAL_TYPES = {"8", "9"}

OFFICE = {
    "2": "국회의원(재·보궐)",
    "3": "시도지사",
    "4": "기초단체장",
    "5": "광역의원",
    "6": "지역구 기초의원",
    "8": "광역의원 비례",
    "9": "기초의원 비례",
    "11": "교육감",
}

REQUESTED_KEYWORDS = {
    "사기": [
        "사기",
        "사기죄",
        "사기미수",
        "사기방조",
        "컴퓨터등사용사기",
        "컴퓨터사용사기",
        "부정수표단속법위반",
        "보험사기방지특별법",
        "보조금관리에관한법률위반",
        "특정경제범죄가중처벌등에관한법률위반(사기)",
        "특경법위반(사기)",
        "유사수신행위",
    ],
    "횡령": [
        "횡령",
        "횡령죄",
        "횡령미수",
        "업무상횡령",
        "점유이탈물횡령",
        "특정경제범죄가중처벌등에관한법률위반(횡령)",
        "특경법위반(횡령)",
    ],
    "배임": [
        "배임",
        "배임죄",
        "배임미수",
        "업무상배임",
        "배임수재",
        "배임증재",
        "특정경제범죄가중처벌등에관한법률위반(배임)",
        "특경법위반(배임)",
        "신용훼손",
    ],
    "뇌물": [
        "뇌물",
        "뇌물공여",
        "뇌물수수",
        "뇌물공여약속",
        "수뢰",
        "증뢰",
        "알선수재",
        "알선뇌물",
        "변호사법위반(알선)",
        "청탁금지법",
        "부정청탁및금품등수수의금지에관한법률",
        "특정범죄가중처벌등에관한법률위반(뇌물)",
        "특가법위반(뇌물)",
    ],
}

# 본방 핵심 수치에 포함하면 해석이 넓어지는 키워드. 메인 v2에는 포함하되,
# 별도 컬럼과 주석으로 확인 가능하게 남긴다.
BROAD_TERMS = {
    "사기": {"부정수표단속법위반", "보조금관리에관한법률위반", "유사수신행위"},
    "배임": {"신용훼손"},
    "뇌물": {"변호사법위반(알선)", "청탁금지법", "부정청탁및금품등수수의금지에관한법률"},
}


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def compact(value: str) -> str:
    return re.sub(r"[^0-9A-Za-z가-힣]", "", value or "")


def parse_keyword_list(category: str) -> list[str]:
    text = OCR_SCRIPT.read_text(encoding="utf-8")
    m = re.search(rf'"{re.escape(category)}"\s*:\s*\[([^\]]+)\]', text)
    if not m:
        return []
    return re.findall(r'"([^"]+)"', m.group(1))


def covered_by_existing(keyword: str, existing: list[str]) -> bool:
    ck = compact(keyword)
    for term in existing:
        ct = compact(term)
        if ct and (ct in ck or ck in ct):
            return True
    return False


def parse_int(value: str | int | None) -> int:
    if value is None:
        return 0
    nums = re.findall(r"\d+", str(value).replace(",", ""))
    return int("".join(nums)) if nums else 0


def seat_key(item: dict) -> str:
    return "|".join([str(item.get("sgTypecode") or ""), str(item.get("sdName") or ""), str(item.get("sggName") or "")])


def rank_of(candidate: dict) -> int:
    return parse_int(candidate.get("giho") or candidate.get("gihoSangse"))


def region(candidate: dict, record: dict | None = None) -> str:
    source = candidate or record or {}
    sd = source.get("sdName") or ""
    sgg = source.get("sggName") or source.get("wiwName") or ""
    if sgg and sgg != sd:
        return f"{sd} {sgg}".strip()
    return sd


def make_context():
    criminal = load_json(CRIMINAL)
    candidate_payload = load_json(CANDIDATES)
    detail_payload = load_json(DETAILS)
    constituencies = load_json(CONSTITUENCIES)

    candidates = {
        str(row.get("huboid")): row
        for row in candidate_payload.get("candidates", [])
        if row.get("huboid")
    }
    details = {
        str(row.get("huboid")): row
        for row in detail_payload.get("details", [])
        if row.get("huboid")
    }
    denominators = {
        party: sum(1 for row in candidate_payload.get("candidates", []) if row.get("jdName") == party)
        for party in FIVE_PARTIES
    }
    seats = {
        seat_key(row): parse_int(row.get("sggJungsu")) or 1
        for row in constituencies
    }
    active_by_key: dict[str, list[dict]] = defaultdict(list)
    for row in candidates.values():
        if row.get("status") and row.get("status") != "등록":
            continue
        active_by_key[seat_key(row)].append(row)
    return criminal, candidates, details, denominators, seats, active_by_key


def is_uncontested(candidate: dict, seats: dict[str, int], active_by_key: dict[str, list[dict]]) -> bool:
    key = seat_key(candidate)
    seat = seats.get(key, 0)
    active = active_by_key.get(key, [])
    if not seat or not active:
        return False
    if len(active) <= seat:
        return True
    if str(candidate.get("sgTypecode")) in PROPORTIONAL_TYPES:
        parties = {row.get("jdName") or "무소속" for row in active}
        return len(parties) == 1
    return False


def is_electable_order(candidate: dict, seats: dict[str, int]) -> bool:
    if str(candidate.get("sgTypecode")) not in PROPORTIONAL_TYPES:
        return False
    rank = rank_of(candidate)
    seat = seats.get(seat_key(candidate), 0)
    return bool(rank and seat and rank <= seat)


def full_record_text(record: dict) -> str:
    pieces = [
        record.get("offense_text") or "",
        record.get("ocr_text") or "",
    ]
    for offense in record.get("offenses") or []:
        pieces.extend([offense.get("offense") or "", offense.get("raw") or ""])
    return compact(" ".join(pieces))


def match_keyword(text: str, keyword: str) -> bool:
    key = compact(keyword)
    if not key:
        return False
    if keyword == "변호사법위반(알선)":
        return "변호사법위반" in text and "알선" in text
    return key in text


def category_hits(record: dict) -> dict[str, list[str]]:
    text = full_record_text(record)
    hits: dict[str, list[str]] = {}
    for category, keywords in REQUESTED_KEYWORDS.items():
        matched = [kw for kw in keywords if match_keyword(text, kw)]
        if matched:
            hits[category] = matched
    return hits


def offense_matches(record: dict) -> list[dict]:
    rows = []
    covered = {category: set() for category in TARGET_CATEGORIES}
    for offense in record.get("offenses") or []:
        text = compact(" ".join([offense.get("offense") or "", offense.get("raw") or ""]))
        matched_categories = {}
        for category, keywords in REQUESTED_KEYWORDS.items():
            hits = [kw for kw in keywords if match_keyword(text, kw)]
            if hits:
                matched_categories[category] = hits
                covered[category].update(hits)
        if not matched_categories:
            continue
        rows.append({
            "source": "offense_row",
            "offense_name": offense.get("offense") or "",
            "date": offense.get("date") or "",
            "sentence": offense.get("sentence") or "",
            "raw": offense.get("raw") or "",
            "categories": sorted(matched_categories),
            "keywords": sorted({kw for items in matched_categories.values() for kw in items}),
            "broad_keywords": sorted({
                kw
                for cat, items in matched_categories.items()
                for kw in items
                if kw in BROAD_TERMS.get(cat, set())
            }),
        })

    whole_hits = category_hits(record)
    missing = {
        cat: [kw for kw in kws if kw not in covered.get(cat, set())]
        for cat, kws in whole_hits.items()
    }
    missing = {cat: kws for cat, kws in missing.items() if kws}
    if missing:
        rows.append({
            "source": "record_text",
            "offense_name": " / ".join(sorted({kw for kws in missing.values() for kw in kws})),
            "date": "",
            "sentence": "",
            "raw": (record.get("ocr_text") or record.get("offense_text") or "")[:500],
            "categories": sorted(missing),
            "keywords": sorted({kw for kws in missing.values() for kw in kws}),
            "broad_keywords": sorted({
                kw
                for cat, kws in missing.items()
                for kw in kws
                if kw in BROAD_TERMS.get(cat, set())
            }),
        })
    return rows


def build_rows():
    criminal, candidates, details, denominators, seats, active_by_key = make_context()
    people = {}
    detail_rows = []
    for record in criminal.get("records", []):
        huboid = str(record.get("huboid") or "")
        candidate = candidates.get(huboid, {})
        detail = details.get(huboid, {})
        party = candidate.get("jdName") or record.get("party") or detail.get("jdName") or ""
        v1_categories = sorted(set(record.get("categories") or []) & set(TARGET_CATEGORIES))
        v2_hits = category_hits(record)
        if not v1_categories and not v2_hits:
            continue
        matches = offense_matches(record)
        if not matches and v2_hits:
            matches = [{
                "source": "record_text",
                "offense_name": " / ".join(sorted({kw for kws in v2_hits.values() for kw in kws})),
                "date": "",
                "sentence": "",
                "raw": (record.get("ocr_text") or record.get("offense_text") or "")[:500],
                "categories": sorted(v2_hits),
                "keywords": sorted({kw for kws in v2_hits.values() for kw in kws}),
                "broad_keywords": sorted({
                    kw
                    for cat, kws in v2_hits.items()
                    for kw in kws
                    if kw in BROAD_TERMS.get(cat, set())
                }),
            }]
        rank = rank_of(candidate)
        seat = seats.get(seat_key(candidate), 0)
        sg_type = str(candidate.get("sgTypecode") or record.get("sgTypecode") or "")
        base = {
            "huboid": huboid,
            "name": candidate.get("name") or record.get("name") or detail.get("name") or "",
            "party": party,
            "region": region(candidate, record),
            "office": OFFICE.get(sg_type, ""),
            "sgTypecode": sg_type,
            "proportional_rank": rank if sg_type in PROPORTIONAL_TYPES and rank else "",
            "seat_count": seat if sg_type in PROPORTIONAL_TYPES and seat else "",
            "electable_order": "Y" if is_electable_order(candidate, seats) else "N",
            "uncontested": "Y" if is_uncontested(candidate, seats, active_by_key) else "N",
            "status": candidate.get("status") or "",
            "v1_categories": "; ".join(v1_categories),
            "v2_categories": "; ".join(sorted(v2_hits)),
            "v2_keywords": "; ".join(sorted({kw for kws in v2_hits.values() for kw in kws})),
            "v2_broad_keywords": "; ".join(sorted({
                kw
                for cat, kws in v2_hits.items()
                for kw in kws
                if kw in BROAD_TERMS.get(cat, set())
            })),
            "nec_detail_url": detail.get("nec_detail_url") or record.get("nec_detail_url") or "",
            "pdf_urls": "; ".join(record.get("pdf_urls") or []),
        }
        summaries = []
        for match in matches:
            date_text = match["date"] or ("일자 행 매핑 실패" if match["source"] == "record_text" else "일자 확인 불가")
            sentence_text = match["sentence"] or ("형량 행 매핑 실패" if match["source"] == "record_text" else "형량 확인 불가")
            summaries.append(f"{match['offense_name']} ({date_text}, {sentence_text})")
            detail_rows.append({
                **base,
                "match_source": match["source"],
                "matched_categories": "; ".join(match["categories"]),
                "matched_keywords": "; ".join(match["keywords"]),
                "broad_keywords": "; ".join(match["broad_keywords"]),
                "offense_name": match["offense_name"],
                "disposition_date": match["date"],
                "sentence": match["sentence"],
                "raw": match["raw"],
            })
        base["offense_summaries"] = "; ".join(dict.fromkeys(summaries))
        base["change_status"] = (
            "v1+v2" if v1_categories and v2_hits
            else "v2_added" if v2_hits
            else "v1_only"
        )
        people[huboid] = base
    return criminal, denominators, list(people.values()), detail_rows


def has_category(row: dict, version: str, category: str) -> bool:
    field = "v1_categories" if version == "v1" else "v2_categories"
    return category in {x.strip() for x in str(row.get(field) or "").split(";") if x.strip()}


def count_category(rows: list[dict], party: str, version: str, category: str) -> int:
    return sum(1 for row in rows if row["party"] == party and has_category(row, version, category))


def count_union(rows: list[dict], party: str, version: str) -> int:
    field = "v1_categories" if version == "v1" else "v2_categories"
    return sum(1 for row in rows if row["party"] == party and str(row.get(field) or "").strip())


def pct(n: int, denom: int) -> str:
    return f"{(n / denom * 100 if denom else 0):.2f}%"


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def table_md(headers: list[str], rows: list[list[object]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    out.extend("| " + " | ".join(str(v) for v in row) + " |" for row in rows)
    return "\n".join(out)


def summary_rows(rows: list[dict], parties: list[str]) -> list[dict]:
    out = []
    for category in TARGET_CATEGORIES:
        row = {"죄목": category}
        for party in parties:
            v1 = count_category(rows, party, "v1", category)
            v2 = count_category(rows, party, "v2", category)
            row[f"v1_{party}"] = v1
            row[f"v2_{party}"] = v2
            row[f"변동_{party}"] = v2 - v1
        out.append(row)
    row = {"죄목": "사기·횡령·배임·뇌물 합계(중복 제거)"}
    for party in parties:
        v1 = count_union(rows, party, "v1")
        v2 = count_union(rows, party, "v2")
        row[f"v1_{party}"] = v1
        row[f"v2_{party}"] = v2
        row[f"변동_{party}"] = v2 - v1
    out.append(row)
    return out


def summary_md_for_parties(summary: list[dict], parties: list[str]) -> str:
    if parties == MAJOR_PARTIES:
        return table_md(
            ["죄목", "v1 민주당", "v2 민주당", "변동", "v1 국힘", "v2 국힘", "변동"],
            [
                [
                    row["죄목"],
                    row["v1_더불어민주당"],
                    row["v2_더불어민주당"],
                    f"{row['변동_더불어민주당']:+d}",
                    row["v1_국민의힘"],
                    row["v2_국민의힘"],
                    f"{row['변동_국민의힘']:+d}",
                ]
                for row in summary
            ],
        )
    headers = ["죄목"]
    for party in parties:
        headers.extend([f"v1 {party}", f"v2 {party}", "변동"])
    md_rows = []
    for row in summary:
        out = [row["죄목"]]
        for party in parties:
            out.extend([row[f"v1_{party}"], row[f"v2_{party}"], f"{row[f'변동_{party}']:+d}"])
        md_rows.append(out)
    return table_md(headers, md_rows)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    criminal, denominators, rows, detail_rows = build_rows()

    v1_keywords = {cat: parse_keyword_list(cat) for cat in TARGET_CATEGORIES}
    missing = {
        cat: [kw for kw in REQUESTED_KEYWORDS[cat] if not covered_by_existing(kw, v1_keywords[cat])]
        for cat in TARGET_CATEGORIES
    }

    major_summary = summary_rows(rows, MAJOR_PARTIES)
    five_summary = summary_rows(rows, FIVE_PARTIES)

    fields = [
        "huboid", "name", "party", "region", "office", "proportional_rank", "seat_count",
        "electable_order", "uncontested", "status", "v1_categories", "v2_categories",
        "v2_keywords", "v2_broad_keywords", "offense_summaries", "change_status",
        "nec_detail_url", "pdf_urls",
    ]
    detail_fields = [
        "huboid", "name", "party", "region", "office", "proportional_rank", "seat_count",
        "electable_order", "uncontested", "status", "v1_categories", "v2_categories",
        "match_source", "matched_categories", "matched_keywords", "broad_keywords",
        "offense_name", "disposition_date", "sentence", "raw", "nec_detail_url", "pdf_urls",
    ]
    write_csv(OUT / "economic_trust_candidates_v1_v2.csv", rows, fields)
    write_csv(OUT / "economic_trust_offense_matches_v2.csv", detail_rows, detail_fields)
    write_csv(OUT / "economic_trust_summary_major_parties.csv", major_summary, ["죄목", *[k for p in MAJOR_PARTIES for k in (f"v1_{p}", f"v2_{p}", f"변동_{p}")]])
    write_csv(OUT / "economic_trust_summary_five_parties.csv", five_summary, ["죄목", *[k for p in FIVE_PARTIES for k in (f"v1_{p}", f"v2_{p}", f"변동_{p}")]])

    additions = [row for row in rows if row["change_status"] == "v2_added" and row["party"] in FIVE_PARTIES]
    removals = [row for row in rows if row["change_status"] == "v1_only" and row["party"] in FIVE_PARTIES]
    proportional = [
        row for row in rows
        if row["sgTypecode"] in PROPORTIONAL_TYPES and row["electable_order"] == "Y" and row["party"] in MAJOR_PARTIES
    ]
    proportional_summary = []
    for party in MAJOR_PARTIES:
        party_rows = [row for row in proportional if row["party"] == party]
        proportional_summary.append({
            "party": party,
            "v1": sum(1 for row in party_rows if row["v1_categories"]),
            "v2": sum(1 for row in party_rows if row["v2_categories"]),
            "delta": sum(1 for row in party_rows if row["v2_categories"]) - sum(1 for row in party_rows if row["v1_categories"]),
        })
    write_csv(OUT / "proportional_electable_order_economic_trust_v1_v2.csv", proportional, fields)

    keyword_report = {
        "source_rule_file": "scripts/ocr_criminal_records.py",
        "source_data": "data/criminal_ocr.json",
        "classification_version": criminal.get("meta", {}).get("classification_version"),
        "matching_method_v1": "공백 제거 후 offense_section(죄명~첨부서류/2026년 전)에서 키워드 부분 포함 여부를 검사. 정규표현식이 아니라 부분 문자열 매칭.",
        "v1_keywords": v1_keywords,
        "requested_keywords": REQUESTED_KEYWORDS,
        "missing_from_explicit_v1": missing,
        "broad_terms_to_read_carefully": {key: sorted(value) for key, value in BROAD_TERMS.items()},
    }
    (OUT / "economic_trust_keyword_audit.json").write_text(json.dumps(keyword_report, ensure_ascii=False, indent=2), encoding="utf-8")

    def line_for(row: dict) -> str:
        rank = f" · 비례 {row['proportional_rank']}순위/{row['seat_count']}명" if row["proportional_rank"] else ""
        electable = " · 선출인원 안 순번" if row["electable_order"] == "Y" else ""
        uncontested = " · 무투표" if row["uncontested"] == "Y" else ""
        return (
            f"- {row['name']} | {row['party']} | {row['region']} {row['office']}{rank}{electable}{uncontested} | "
            f"v2 {row['v2_categories']} | {row['v2_keywords']} | {row['offense_summaries'] or '행 매핑 실패'}"
        )

    dem_v1 = count_union(rows, "더불어민주당", "v1")
    dem_v2 = count_union(rows, "더불어민주당", "v2")
    ppp_v1 = count_union(rows, "국민의힘", "v1")
    ppp_v2 = count_union(rows, "국민의힘", "v2")
    dem_den = denominators["더불어민주당"]
    ppp_den = denominators["국민의힘"]
    diff_v1 = dem_v1 / dem_den * 100 - ppp_v1 / ppp_den * 100
    diff_v2 = dem_v2 / dem_den * 100 - ppp_v2 / ppp_den * 100

    prop_lines = []
    for row in proportional_summary:
        prop_lines.append(f"- {row['party']}: v1 {row['v1']}명 → v2 {row['v2']}명 ({row['delta']:+d})")
    prop_changes = [
        row for row in proportional
        if (bool(row["v1_categories"]) != bool(row["v2_categories"]))
    ]

    md = f"""# 사기·횡령·배임·뇌물 분류 검증 결과

생성 시각: 2026-05-19

## 1순위. 키워드 공개

- v1 `사기` 키워드: {', '.join(v1_keywords['사기'])}
- v1 `횡령` 키워드: {', '.join(v1_keywords['횡령'])}
- v1 `배임` 키워드: {', '.join(v1_keywords['배임'])}
- v1 `뇌물` 키워드: {', '.join(v1_keywords['뇌물'])}
- 매칭 방식: 공백 제거 후 `죄명` 영역 안에서 키워드가 부분 문자열로 포함되는지 검사. 정규표현식·정확 일치가 아니라 부분 일치 방식.

## 2순위. 누락 여부 판정

- 사기 누락 키워드: {', '.join(missing['사기']) or '없음'}
- 횡령 누락 키워드: {', '.join(missing['횡령']) or '없음'}
- 배임 누락 키워드: {', '.join(missing['배임']) or '없음'}
- 뇌물 누락 키워드: {', '.join(missing['뇌물']) or '없음'}

주의: `부정수표단속법위반`, `보조금관리에관한법률위반`, `유사수신행위`, `신용훼손`, `청탁금지법`, `변호사법위반(알선)`은 요청 키워드에 따라 포함했지만, 죄명 자체가 사기·배임·뇌물의 직접 죄명과 완전히 같지는 않아 보도 문장에서는 별도 설명이 필요합니다.

## 재추출 결과 (양당)

{summary_md_for_parties(major_summary, MAJOR_PARTIES)}

## 재추출 결과 (5개 정당)

{summary_md_for_parties(five_summary, FIVE_PARTIES)}

## 인물 명단 변동

### v1에 없었지만 v2에 추가된 5개 정당 후보: {len(additions)}명
{chr(10).join(line_for(row) for row in additions) if additions else '- 해당 없음'}

### v1에 있었지만 v2에서 빠진 5개 정당 후보: {len(removals)}명
{chr(10).join(line_for(row) for row in removals) if removals else '- 해당 없음'}

## 본방 핵심 수치 갱신

- 민주당 사기·횡령·배임·뇌물 신고: v1 {dem_v1}명({pct(dem_v1, dem_den)}) → v2 {dem_v2}명({pct(dem_v2, dem_den)}) ({dem_v2 - dem_v1:+d})
- 국민의힘 사기·횡령·배임·뇌물 신고: v1 {ppp_v1}명({pct(ppp_v1, ppp_den)}) → v2 {ppp_v2}명({pct(ppp_v2, ppp_den)}) ({ppp_v2 - ppp_v1:+d})
- 양당 차이: v1 국민의힘이 민주당보다 {abs(diff_v1):.2f}%p 높음 → v2 국민의힘이 민주당보다 {abs(diff_v2):.2f}%p 높음
- 분모: 민주당 {dem_den:,}명, 국민의힘 {ppp_den:,}명. 2026-05-19 후보자 스냅샷의 정당별 전체 행 수 기준.

## 비례 명부 선출인원 안 순번

{chr(10).join(prop_lines)}

### 비례 명부 안 변동 인물
{chr(10).join(line_for(row) for row in prop_changes) if prop_changes else '- 변동 없음'}

## 보도 주의 문구

이 표는 `criminal_ocr.json`의 죄명 영역을 키워드로 재분류한 결과입니다. 후보별 죄명·시점·형량은 선관위 후보자 공개정보 기준이며, 인용 시 선관위 후보자 상세 페이지 원문 확인이 필요합니다.
"""

    (OUT / "ECONOMIC_TRUST_CLASSIFICATION_AUDIT_20260519.md").write_text(md, encoding="utf-8")
    zip_path = OUT.with_suffix(".zip")
    if zip_path.exists():
        zip_path.unlink()
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in OUT.rglob("*"):
            zf.write(path, path.relative_to(OUT.parent))

    print(md)
    print(f"\nWrote {OUT}")
    print(f"Wrote {zip_path}")


if __name__ == "__main__":
    main()
