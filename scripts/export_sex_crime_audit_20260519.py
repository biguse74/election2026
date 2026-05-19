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
OUT = ROOT / "exports" / "sex_crime_classification_audit_20260519"

MAJOR_PARTIES = ["더불어민주당", "국민의힘"]
FIVE_PARTIES = ["더불어민주당", "국민의힘", "조국혁신당", "진보당", "개혁신당"]
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

REQUESTED_KEYWORDS = [
    "강제추행",
    "강간",
    "준강간",
    "준강제추행",
    "유사강간",
    "성폭력",
    "성폭행",
    "아동·청소년의성보호",
    "청소년성보호",
    "아청법",
    "성폭력처벌",
    "성폭력특례",
    "성폭력범죄의처벌",
    "성매매",
    "성매매처벌",
    "성매매알선",
    "윤락행위",
    "윤락",
    "카메라등이용촬영",
    "통신매체이용음란",
    "공중밀집장소추행",
]

BUCKET_TERMS = {
    "강제추행": ["강제추행"],
    "강간": ["강간", "강간미수", "유사강간"],
    "준강간·준강제추행": ["준강간", "준강제추행"],
    "아동·청소년 성보호법": ["아동청소년의성보호", "청소년성보호", "아청법", "아동청소년"],
    "성폭력처벌법": ["성폭력처벌", "성폭력특례", "성폭력범죄의처벌", "성폭력", "성폭행"],
    "성매매처벌법": ["성매매처벌", "성매매알선", "성매매"],
    "윤락행위방지법": ["윤락행위", "윤락"],
    "카메라등이용촬영·통신매체음란·공중밀집장소추행": [
        "카메라등이용촬영",
        "통신매체이용음란",
        "공중밀집장소추행",
    ],
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


def bucket_hits(text: str) -> dict[str, list[str]]:
    c = compact(text)
    hits: dict[str, list[str]] = {}
    for bucket, terms in BUCKET_TERMS.items():
        matched = []
        for term in terms:
            t = compact(term)
            if not t or t not in c:
                continue
            if term == "강간" and ("준강간" in c or "강제집행면탈" in c):
                continue
            if term == "강제추행" and "준강제추행" in c and "강제추행" not in c.replace("준강제추행", ""):
                continue
            matched.append(term)
        if matched:
            hits[bucket] = matched
    return hits


def parse_int(value: str | int | None) -> int:
    if value is None:
        return 0
    m = re.findall(r"\d+", str(value).replace(",", ""))
    return int("".join(m)) if m else 0


def seat_key(item: dict) -> str:
    return "|".join([str(item.get("sgTypecode") or ""), str(item.get("sdName") or ""), str(item.get("sggName") or "")])


def rank_of(candidate: dict) -> int:
    return parse_int(candidate.get("giho") or candidate.get("gihoSangse"))


def region(candidate: dict) -> str:
    sd = candidate.get("sdName") or ""
    sgg = candidate.get("sggName") or candidate.get("wiwName") or ""
    if sgg and sgg != sd:
        return f"{sd} {sgg}".strip()
    return sd


def make_context():
    criminal = load_json(CRIMINAL)
    candidates_payload = load_json(CANDIDATES)
    details_payload = load_json(DETAILS)
    constituencies = load_json(CONSTITUENCIES)

    candidates = {
        str(row.get("huboid")): row
        for row in candidates_payload.get("candidates", [])
        if row.get("huboid")
    }
    details = {
        str(row.get("huboid")): row
        for row in details_payload.get("details", [])
        if row.get("huboid")
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
    return criminal, candidates, details, seats, active_by_key


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


def offense_matches(record: dict) -> list[dict]:
    rows = []
    covered_buckets = set()
    for offense in record.get("offenses") or []:
        text = " ".join(str(offense.get(k) or "") for k in ("offense", "raw"))
        hits = bucket_hits(text)
        if not hits:
            continue
        covered_buckets.update(hits)
        rows.append({
            "source": "offense_row",
            "offense_name": offense.get("offense") or "",
            "date": offense.get("date") or "",
            "sentence": offense.get("sentence") or "",
            "raw": offense.get("raw") or "",
            "buckets": sorted(hits),
            "keywords": sorted({kw for kws in hits.values() for kw in kws}),
        })

    whole_hits = bucket_hits(" ".join([
        str(record.get("offense_text") or ""),
        str(record.get("ocr_text") or ""),
        " ".join(str(o.get("raw") or "") for o in record.get("offenses") or []),
    ]))
    missing = {bucket: kws for bucket, kws in whole_hits.items() if bucket not in covered_buckets}
    if missing:
        rows.append({
            "source": "record_text",
            "offense_name": " / ".join(sorted({kw for kws in missing.values() for kw in kws})),
            "date": "",
            "sentence": "",
            "raw": (record.get("ocr_text") or record.get("offense_text") or "")[:500],
            "buckets": sorted(missing),
            "keywords": sorted({kw for kws in missing.values() for kw in kws}),
        })
    return rows


def build_rows():
    criminal, candidates, details, seats, active_by_key = make_context()
    rows = []
    person_map = {}
    for record in criminal.get("records", []):
        huboid = str(record.get("huboid") or "")
        candidate = candidates.get(huboid, {})
        detail = details.get(huboid, {})
        matches = offense_matches(record)
        if not matches:
            continue
        party = candidate.get("jdName") or record.get("party") or detail.get("jdName") or ""
        rank = rank_of(candidate)
        seat = seats.get(seat_key(candidate), 0)
        base = {
            "huboid": huboid,
            "name": candidate.get("name") or record.get("name") or detail.get("name") or "",
            "party": party,
            "sdName": candidate.get("sdName") or record.get("sdName") or "",
            "sggName": candidate.get("sggName") or record.get("sggName") or "",
            "region": region(candidate) if candidate else f"{record.get('sdName','')} {record.get('sggName','')}".strip(),
            "sgTypecode": str(candidate.get("sgTypecode") or record.get("sgTypecode") or ""),
            "office": OFFICE.get(str(candidate.get("sgTypecode") or record.get("sgTypecode") or ""), ""),
            "proportional_rank": rank if str(candidate.get("sgTypecode")) in PROPORTIONAL_TYPES and rank else "",
            "seat_count": seat if str(candidate.get("sgTypecode")) in PROPORTIONAL_TYPES and seat else "",
            "electable_order": "Y" if is_electable_order(candidate, seats) else "N",
            "uncontested": "Y" if is_uncontested(candidate, seats, active_by_key) else "N",
            "status": candidate.get("status") or "",
            "nec_detail_url": detail.get("nec_detail_url") or record.get("nec_detail_url") or "",
            "pdf_urls": "; ".join(record.get("pdf_urls") or []),
        }
        person_buckets = set()
        person_keywords = set()
        person_offenses = []
        person_summaries = []
        for match in matches:
            person_buckets.update(match["buckets"])
            person_keywords.update(match["keywords"])
            person_offenses.append(match["offense_name"])
            date_text = match["date"] or ("일자 행 매핑 실패" if match["source"] == "record_text" else "일자 확인 불가")
            sentence_text = match["sentence"] or ("형량 행 매핑 실패" if match["source"] == "record_text" else "형량 확인 불가")
            person_summaries.append(f"{match['offense_name'] or '/'.join(match['keywords'])} ({date_text}, {sentence_text})")
            row = {
                **base,
                "match_source": match["source"],
                "matched_buckets": "; ".join(match["buckets"]),
                "matched_keywords": "; ".join(match["keywords"]),
                "offense_name": match["offense_name"],
                "disposition_date": match["date"],
                "sentence": match["sentence"],
                "raw": match["raw"],
            }
            rows.append(row)
        person_map[huboid] = {
            **base,
            "matched_buckets": "; ".join(sorted(person_buckets)),
            "matched_keywords": "; ".join(sorted(person_keywords)),
            "offense_names": "; ".join(dict.fromkeys(person_offenses)),
            "offense_summaries": "; ".join(dict.fromkeys(person_summaries)),
            "offense_rows": len(matches),
        }
    return criminal, rows, list(person_map.values())


def count_bucket(rows: list[dict], bucket: str, party_filter: list[str] | None = None) -> int:
    ids = set()
    for row in rows:
        if party_filter and row["party"] not in party_filter:
            continue
        buckets = {x.strip() for x in row["matched_buckets"].split(";") if x.strip()}
        if bucket in buckets:
            ids.add(row["huboid"])
    return len(ids)


def count_union(rows: list[dict], party_filter: list[str] | None = None) -> int:
    return len({
        row["huboid"]
        for row in rows
        if not party_filter or row["party"] in party_filter
    })


def write_csv(path: Path, rows: list[dict], fields: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def table_md(headers: list[str], rows: list[list[str | int]]) -> str:
    out = ["| " + " | ".join(headers) + " |", "| " + " | ".join(["---"] * len(headers)) + " |"]
    out.extend("| " + " | ".join(str(v) for v in row) + " |" for row in rows)
    return "\n".join(out)


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    criminal, detail_rows, people = build_rows()

    existing_sex = parse_keyword_list("성범죄")
    existing_drug = parse_keyword_list("마약")
    missing = [kw for kw in REQUESTED_KEYWORDS if not covered_by_existing(kw, existing_sex)]

    original_sex_records = [r for r in criminal.get("records", []) if "성범죄" in (r.get("categories") or [])]
    original_five = [r for r in original_sex_records if (r.get("party") or "") in FIVE_PARTIES]
    original_major = [r for r in original_sex_records if (r.get("party") or "") in MAJOR_PARTIES]

    bucket_rows_major = []
    bucket_rows_five = []
    for bucket in BUCKET_TERMS:
        bucket_rows_major.append({
            "죄명": bucket,
            "더불어민주당": count_bucket(detail_rows, bucket, ["더불어민주당"]),
            "국민의힘": count_bucket(detail_rows, bucket, ["국민의힘"]),
        })
        row = {"죄명": bucket}
        for party in FIVE_PARTIES:
            row[party] = count_bucket(detail_rows, bucket, [party])
        row["5개정당합계"] = count_bucket(detail_rows, bucket, FIVE_PARTIES)
        row["전체"] = count_bucket(detail_rows, bucket, None)
        bucket_rows_five.append(row)
    bucket_rows_major.append({
        "죄명": "합계(중복제거)",
        "더불어민주당": count_union(detail_rows, ["더불어민주당"]),
        "국민의힘": count_union(detail_rows, ["국민의힘"]),
    })
    total_row = {"죄명": "합계(중복제거)"}
    for party in FIVE_PARTIES:
        total_row[party] = count_union(detail_rows, [party])
    total_row["5개정당합계"] = count_union(detail_rows, FIVE_PARTIES)
    total_row["전체"] = count_union(detail_rows, None)
    bucket_rows_five.append(total_row)

    proportional = [
        row for row in people
        if row["sgTypecode"] in PROPORTIONAL_TYPES and row["electable_order"] == "Y"
    ]
    proportional_major = [row for row in proportional if row["party"] in MAJOR_PARTIES]
    proportional_five = [row for row in proportional if row["party"] in FIVE_PARTIES]

    unclassified = []
    for record in criminal.get("records", []):
        for offense in record.get("offenses") or []:
            if offense.get("categories"):
                continue
            label = offense.get("offense") or offense.get("raw") or ""
            label = re.sub(r"\s+", "", label)
            if len(label) < 4 or not re.search(r"[가-힣]", label):
                continue
            if re.fullmatch(r"[0-9.\-/년월일]+", label):
                continue
            if label not in unclassified:
                unclassified.append(label[:80])
            if len(unclassified) >= 10:
                break
        if len(unclassified) >= 10:
            break

    fields = [
        "huboid", "name", "party", "region", "office", "proportional_rank", "seat_count",
        "electable_order", "uncontested", "status", "matched_buckets", "matched_keywords",
        "offense_names", "offense_summaries", "offense_rows", "nec_detail_url", "pdf_urls",
    ]
    detail_fields = [
        "huboid", "name", "party", "region", "office", "proportional_rank", "seat_count",
        "electable_order", "uncontested", "matched_buckets", "matched_keywords",
        "offense_name", "disposition_date", "sentence", "match_source", "raw",
        "nec_detail_url", "pdf_urls",
    ]
    write_csv(OUT / "sex_crime_candidates_full.csv", people, fields)
    write_csv(OUT / "sex_crime_offense_matches.csv", detail_rows, detail_fields)
    write_csv(OUT / "sex_crime_bucket_counts_major_parties.csv", bucket_rows_major, ["죄명", "더불어민주당", "국민의힘"])
    write_csv(OUT / "sex_crime_bucket_counts_five_parties.csv", bucket_rows_five, ["죄명", *FIVE_PARTIES, "5개정당합계", "전체"])
    write_csv(OUT / "proportional_electable_order_sex_crime.csv", proportional, fields)

    keyword_report = {
        "source_rule_file": "scripts/ocr_criminal_records.py",
        "source_data": "data/criminal_ocr.json",
        "classification_version": criminal.get("meta", {}).get("classification_version"),
        "matching_method_v1": "공백 제거 후 offense_section(죄명~첨부서류/2026년 전)에서 키워드 부분 포함 여부를 검사. 정규표현식이 아니라 부분 문자열 매칭.",
        "v1_sex_crime_keywords": existing_sex,
        "v1_drug_keywords": existing_drug,
        "requested_keywords": REQUESTED_KEYWORDS,
        "explicit_keywords_not_in_v1": missing,
        "unclassified_bucket_sample": unclassified,
    }
    (OUT / "classification_keyword_audit.json").write_text(json.dumps(keyword_report, ensure_ascii=False, indent=2), encoding="utf-8")

    major_md_rows = [[row["죄명"], row["더불어민주당"], row["국민의힘"]] for row in bucket_rows_major]
    five_md_rows = [[row["죄명"], row["더불어민주당"], row["국민의힘"], row["조국혁신당"], row["진보당"], row["개혁신당"], row["5개정당합계"], row["전체"]] for row in bucket_rows_five]

    people_lines = []
    for idx, row in enumerate(sorted(people, key=lambda r: (r["party"] not in FIVE_PARTIES, r["party"], r["region"], r["name"])), 1):
        seat_text = f"/{row['seat_count']}명" if row["seat_count"] else ""
        rank = f" · 비례 {row['proportional_rank']}순위{seat_text}" if row["proportional_rank"] else ""
        electable = " · 선출인원 안 순번" if row["electable_order"] == "Y" else ""
        uncontested = " · 무투표" if row["uncontested"] == "Y" else ""
        people_lines.append(
            f"{idx}. {row['name']} | {row['party']} | {row['region']} {row['office']}{rank}{electable}{uncontested} | "
            f"{row['matched_buckets']} | {row['matched_keywords']} | {row['offense_summaries'] or row['offense_names'] or '행 분리 실패'}"
        )

    proportional_lines = []
    for label, rows in [
        ("민주당", [r for r in proportional_major if r["party"] == "더불어민주당"]),
        ("국민의힘", [r for r in proportional_major if r["party"] == "국민의힘"]),
        ("5개 정당 합계", proportional_five),
    ]:
        if rows:
            entries = "\n".join(
                f"- {r['name']} | {r['party']} | {r['region']} {r['office']} {r['proportional_rank']}순위/{r['seat_count']}명 | {r['matched_buckets']} | {r['offense_summaries'] or r['offense_names']}"
                for r in rows
            )
        else:
            entries = "- 해당 없음"
        proportional_lines.append(f"### {label}: {len(rows)}명\n{entries}")

    md = f"""# 성범죄 분류 검증 결과

생성 시각: 2026-05-19

## 1-1. 키워드 공개

- v1 `성범죄` 카테고리 키워드: {', '.join(existing_sex) or '확인 불가'}
- v1 `마약` 카테고리 키워드: {', '.join(existing_drug) or '확인 불가'}
- 매칭 방식: 공백 제거 후 `죄명` 영역 안에서 키워드가 부분 문자열로 포함되는지 검사. 정규표현식·정확 일치가 아니라 부분 일치 방식.
- 요청 키워드 중 v1에 명시되지 않은 표현: {', '.join(missing) or '없음'}
- 미분류 bucket 샘플 10개: {', '.join(unclassified) or '없음'}

## 기존 v1 성범죄 분류와 재추출 차이

- v1 `criminal_ocr.json` 성범죄 카테고리: 전체 {len(original_sex_records)}명
- v1 성범죄 중 양당: {len(original_major)}명
- v1 성범죄 중 5개 정당: {len(original_five)}명
- 넓은 키워드 재추출: 전체 {count_union(detail_rows)}명
- 넓은 키워드 재추출 중 양당: 민주당 {count_union(detail_rows, ['더불어민주당'])}명 / 국민의힘 {count_union(detail_rows, ['국민의힘'])}명
- 넓은 키워드 재추출 중 5개 정당 합계: {count_union(detail_rows, FIVE_PARTIES)}명

추가로 잡힌 1명은 무소속 오태완 후보입니다. v1 키워드에는 `강제추행`이 있었지만, 기존 분류가 `죄명` 영역 일부만 잘라 매칭하면서 OCR 앞쪽에 있던 `강제추행` 표현을 놓친 것으로 보입니다. 양당·5개 정당 합계에는 변동이 없습니다.

## 1-2. 재추출 결과 (양당)

{table_md(['죄명', '민주당', '국민의힘'], major_md_rows)}

## 1-2. 재추출 결과 (5개 정당 합계)

{table_md(['죄명', '민주당', '국민의힘', '조국혁신당', '진보당', '개혁신당', '5개정당합계', '전체'], five_md_rows)}

## 1-3. 인물 명단 (전수)

{chr(10).join(people_lines)}

## 2. 비례 명부 선출인원 안 순번의 성범죄 신고 후보

{chr(10).join(proportional_lines)}

## 보도 주의 문구

후보별 죄명·시점·형량은 선관위 후보자 공개정보 기준이며, 인용 시 선관위 후보자 상세 페이지 원문 확인이 필요합니다. 이 표는 `criminal_ocr.json`의 죄명 영역을 키워드로 재분류한 결과입니다.
"""
    (OUT / "SEX_CRIME_CLASSIFICATION_AUDIT_20260519.md").write_text(md, encoding="utf-8")

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
