#!/usr/bin/env python3
"""Build an emergency 2022-vs-2026 timeseries package for Claude.

The 2022 public OpenAPI exposes candidate registration and constituency
metadata. Candidate detail disclosures used in the 2026 package (tax,
military, criminal detail/PDF) are not exposed by that basic API, and the
current 2026 candidate detail page pattern returns 404 for 2022 huboids.
This script therefore publishes confirmed denominators and uncontested
metrics, while marking disclosure-dependent axes as unavailable.
"""

from __future__ import annotations

import csv
import importlib.util
import json
import os
import sys
import time
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import requests


ROOT = Path(__file__).resolve().parent.parent
SG_ID_2022 = "20220601"
SG_ID_2026 = "20260603"
KST = timezone(timedelta(hours=9))

COMMON_CODE_URL = "http://apis.data.go.kr/9760000/CommonCodeService"
CANDIDATE_URL = "http://apis.data.go.kr/9760000/PofelcddInfoInqireService"
UNCONTESTED_URL = "http://apis.data.go.kr/9760000/WtvtelpcInfoInqireService"
DETAIL_TEST_URL = "https://info.nec.go.kr/electioninfo/candidate_detail_info.xhtml"

OUT_DIR = ROOT / "exports" / "timeseries_2022_vs_2026_20260519"
DATA_DIR = OUT_DIR / "data"
ZIP_PATH = ROOT / "exports" / "timeseries_2022_vs_2026_20260519.zip"

CODE_DIR_2022 = ROOT / "data" / "codes" / SG_ID_2022
CANDIDATE_DIR_2022 = ROOT / "data" / "candidates" / SG_ID_2022
CANDIDATE_SNAPSHOT_2022 = CANDIDATE_DIR_2022 / "snapshot_20220513_api.json"
CONSTITUENCIES_2022 = CODE_DIR_2022 / "constituencies" / "combined.json"
GUSIGUN_2022 = CODE_DIR_2022 / "gusigun.json"

KEY_STATS_2026 = ROOT / "exports" / "party_nomination_laxness_20260519_v2" / "data" / "key_stats.json"

LOCAL_ELECTION_TYPES: dict[int, str] = {
    2: "국회의원선거(재·보궐)",
    3: "시도지사선거",
    4: "구시군장선거",
    5: "시도의원선거",
    6: "구시군의회의원선거",
    8: "광역의원비례대표",
    9: "기초의원비례대표",
    10: "교육의원선거",
    11: "교육감선거",
}

MAJOR_PARTIES = ["더불어민주당", "국민의힘"]

AXIS_ORDER = [
    "전과 공개",
    "공직 검증 전과",
    "핵심 검증 전과",
    "사기·횡령·배임·뇌물",
    "최근 5년 체납",
    "현 체납",
    "돈·신뢰 플래그",
    "전과·체납 검증 플래그",
    "무투표 당선 규모",
    "무투표 후보 중 전과·체납",
]

AXIS_TO_2026_KEYS = {
    "전과 공개": ("criminal_record_candidates", "criminal_record_rate_pct"),
    "공직 검증 전과": ("official_vetting_record_candidates", "official_vetting_record_rate_pct"),
    "핵심 검증 전과": ("hard_vetting_record_candidates", "hard_vetting_record_rate_pct"),
    "사기·횡령·배임·뇌물": ("economic_trust_record_candidates", "economic_trust_record_rate_pct"),
    "최근 5년 체납": ("tax_arrears_5y_candidates", "tax_arrears_5y_rate_pct"),
    "현 체납": ("tax_arrears_current_candidates", "tax_arrears_current_rate_pct"),
    "돈·신뢰 플래그": ("money_trust_flag_candidates", "money_trust_flag_rate_pct"),
    "전과·체납 검증 플래그": ("any_vetting_flag_candidates", "any_vetting_flag_rate_pct"),
}


def now_kst() -> datetime:
    return datetime.now(KST)


def load_base_module() -> Any:
    path = ROOT / "scripts" / "export_uncontested_series_data.py"
    spec = importlib.util.spec_from_file_location("uncontested_base", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


BASE = load_base_module()


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


def pct(n: int, d: int, digits: int = 1) -> float:
    return round(n / d * 100, digits) if d else 0.0


def fetch_pages(base_url: str, operation: str, params: dict[str, Any], api_key: str, max_pages: int = 100) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    page = 1
    while page <= max_pages:
        query = {
            **params,
            "serviceKey": api_key,
            "pageNo": page,
            "numOfRows": 100,
            "resultType": "json",
        }
        res = requests.get(f"{base_url}/{operation}", params=query, timeout=30)
        res.raise_for_status()
        if "<OpenAPI_ServiceResponse>" in res.text:
            raise RuntimeError(f"OpenAPI service error: {res.text[:500]}")
        data = res.json()
        resp = data.get("response", {})
        header = resp.get("header", {})
        code = header.get("resultCode", "")
        if code in {"ERROR-03", "INFO-03"}:
            return items
        if code not in {"INFO-00", "00"}:
            raise RuntimeError(f"OpenAPI result error: {header}")
        body = resp.get("body", {})
        wrapper = body.get("items", {})
        chunk = wrapper.get("item", []) if isinstance(wrapper, dict) else wrapper or []
        if isinstance(chunk, dict):
            chunk = [chunk]
        items.extend(chunk)
        total = int(body.get("totalCount", 0) or 0)
        if total == 0 or len(items) >= total:
            break
        page += 1
        time.sleep(0.15)
    return items


def ensure_2022_codes(api_key: str) -> list[dict[str, Any]]:
    if GUSIGUN_2022.exists() and CONSTITUENCIES_2022.exists():
        return load_json(CONSTITUENCIES_2022)

    GUSIGUN_2022.parent.mkdir(parents=True, exist_ok=True)
    write_json(
        GUSIGUN_2022,
        fetch_pages(COMMON_CODE_URL, "getCommonGusigunCodeList", {"sgId": SG_ID_2022}, api_key),
    )

    cstc_dir = CODE_DIR_2022 / "constituencies"
    cstc_dir.mkdir(parents=True, exist_ok=True)
    combined: list[dict[str, Any]] = []
    for sg_type in LOCAL_ELECTION_TYPES:
        rows = fetch_pages(
            COMMON_CODE_URL,
            "getCommonSggCodeList",
            {"sgId": SG_ID_2022, "sgTypecode": sg_type},
            api_key,
        )
        write_json(cstc_dir / f"sgType_{sg_type}.json", rows)
        combined.extend(rows)
        time.sleep(0.15)
    write_json(CONSTITUENCIES_2022, combined)
    return combined


def sido_list() -> list[str]:
    rows = load_json(GUSIGUN_2022)
    sidos = sorted({row.get("wiwName") for row in rows if row.get("wiwName") and not row.get("sdName")})
    if not sidos:
        sidos = sorted({row.get("sdName") for row in rows if row.get("sdName")})
    return [s for s in sidos if s]


def dedupe_by_huboid(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    seen: set[str] = set()
    out: list[dict[str, Any]] = []
    for row in rows:
        huboid = str(row.get("huboid") or "")
        if huboid and huboid in seen:
            continue
        if huboid:
            seen.add(huboid)
        out.append(row)
    return out


def ensure_2022_candidates(api_key: str) -> dict[str, Any]:
    if CANDIDATE_SNAPSHOT_2022.exists():
        return load_json(CANDIDATE_SNAPSHOT_2022)

    sidos = sido_list()
    started = now_kst()
    all_rows: list[dict[str, Any]] = []
    call_count = 0
    for sg_type in LOCAL_ELECTION_TYPES:
        for sido in sidos:
            call_count += 1
            all_rows.extend(
                fetch_pages(
                    CANDIDATE_URL,
                    "getPofelcddRegistSttusInfoInqire",
                    {"sgId": SG_ID_2022, "sgTypecode": sg_type, "sdName": sido},
                    api_key,
                )
            )
            time.sleep(0.08)
    before = len(all_rows)
    all_rows = dedupe_by_huboid(all_rows)
    snapshot = {
        "sgId": SG_ID_2022,
        "snapshot_basis": "선관위 후보자정보 OpenAPI의 2022-06-01 선거ID 현재 응답. API가 후보 등록 마감 시점별 스냅샷을 따로 제공하지 않아 status=등록 후보를 활성 후보로 계산함",
        "fetched_at": started.isoformat(timespec="seconds"),
        "total_api_calls": call_count,
        "raw_candidate_rows_before_dedupe": before,
        "deduped_candidates": len(all_rows),
        "candidates": all_rows,
    }
    write_json(CANDIDATE_SNAPSHOT_2022, snapshot)
    return snapshot


def is_active(candidate: dict[str, Any]) -> bool:
    return not candidate.get("status") or candidate.get("status") == "등록"


def build_uncontested_metrics(candidates: list[dict[str, Any]], constituencies: list[dict[str, Any]]) -> dict[str, Any]:
    joint_sd_map = BASE.build_joint_sd_map(constituencies)
    seats_by_key: dict[str, dict[str, Any]] = {}
    for item in constituencies:
        key = BASE.district_key(item, joint_sd_map)
        seat_count = BASE.parse_int(item.get("sggJungsu"))
        if seat_count <= 0:
            continue
        seats_by_key[key.text] = {
            "sg_type": key.sg_type,
            "sd_name": key.sd_name,
            "sgg_name": key.sgg_name,
            "office": BASE.office_name(key.sg_type),
            "office_type": BASE.office_type(key.sg_type),
            "seat_count": seat_count,
        }

    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    active: list[dict[str, Any]] = []
    for raw in candidates:
        if not is_active(raw):
            continue
        key = BASE.district_key(raw, joint_sd_map)
        row = {
            **raw,
            "huboid": str(raw.get("huboid") or ""),
            "party": raw.get("jdName") or "무소속",
            "district_key": key.text,
            "has_tax_history": False,
            "has_current_tax": False,
            "has_criminal_disclosure": False,
            "has_important_criminal": False,
            "has_election_law": False,
        }
        groups[key.text].append(row)
        active.append(row)

    district_rows: list[dict[str, Any]] = []
    uncontested_candidates: list[dict[str, Any]] = []
    for key_text, seat_info in seats_by_key.items():
        rows = groups.get(key_text, [])
        seat_count = int(seat_info["seat_count"])
        candidate_count = len(rows)
        unique_parties = sorted({row.get("party") for row in rows if row.get("party")})
        single_party_pr = (
            str(seat_info["sg_type"]) in {"8", "9"}
            and candidate_count > 0
            and len(unique_parties) == 1
            and candidate_count > seat_count
        )
        uncontested = candidate_count > 0 and (candidate_count <= seat_count or single_party_pr)
        row = {
            "district_key": key_text,
            "sgTypecode": seat_info["sg_type"],
            "sdName": seat_info["sd_name"],
            "sggName": seat_info["sgg_name"],
            "office": seat_info["office"],
            "office_type": seat_info["office_type"],
            "seat_count": seat_count,
            "candidate_count": candidate_count,
            "competition_rate": round(candidate_count / seat_count, 2) if seat_count else "",
            "uncontested": "Y" if uncontested else "N",
            "basis": "비례대표_단일정당명부" if single_party_pr else "등록후보수_의원정수이하" if uncontested else "",
        }
        district_rows.append(row)
        if uncontested:
            for candidate in rows:
                uncontested_candidates.append({
                    "huboid": candidate["huboid"],
                    "name": candidate.get("name") or "",
                    "party": candidate.get("party") or "",
                    "sgTypecode": seat_info["sg_type"],
                    "office": seat_info["office"],
                    "sdName": seat_info["sd_name"],
                    "sggName": seat_info["sgg_name"],
                    "district_key": key_text,
                    "seat_count": seat_count,
                    "candidate_count": candidate_count,
                    "uncontested_basis": row["basis"],
                })

    by_party: list[dict[str, Any]] = []
    for party in MAJOR_PARTIES:
        total = sum(1 for row in active if row.get("party") == party)
        uncontested = sum(1 for row in uncontested_candidates if row.get("party") == party)
        by_party.append({
            "party": party,
            "total_candidates": total,
            "uncontested_candidates": uncontested,
            "uncontested_rate_pct": pct(uncontested, total),
        })

    district_rows.sort(key=lambda r: (r["uncontested"] != "Y", r["sdName"], r["sgTypecode"], r["sggName"]))
    uncontested_candidates.sort(key=lambda r: (r["party"], r["sdName"], r["sgTypecode"], r["sggName"], r["name"]))
    return {
        "active_candidates": active,
        "district_rows": district_rows,
        "uncontested_candidates": uncontested_candidates,
        "by_party": by_party,
        "total_uncontested_candidates": len(uncontested_candidates),
        "total_uncontested_districts": sum(1 for row in district_rows if row["uncontested"] == "Y"),
    }


def detail_endpoint_probe(candidates: list[dict[str, Any]]) -> dict[str, Any]:
    sample = next((row for row in candidates if str(row.get("huboid") or "")), {})
    huboid = str(sample.get("huboid") or "")
    if not huboid:
        return {"status": "not_tested", "reason": "no huboid sample"}
    url = f"{DETAIL_TEST_URL}?electionId=00{SG_ID_2022}&huboId={huboid}"
    try:
        res = requests.get(url, timeout=20)
        return {
            "status_code": res.status_code,
            "tested_url": url,
            "sample_huboid": huboid,
            "sample_name": sample.get("name") or "",
            "usable": res.status_code == 200,
            "note": "2026 상세 페이지 패턴을 2022 huboid에 적용한 점검",
        }
    except requests.RequestException as exc:
        return {
            "status": "request_failed",
            "tested_url": url,
            "sample_huboid": huboid,
            "error": str(exc),
        }


def uncontested_api_probe(api_key: str) -> dict[str, Any]:
    url = f"{UNCONTESTED_URL}/getWtvtelpccndaInfoInqire"
    try:
        res = requests.get(
            url,
            params={
                "serviceKey": api_key,
                "sgId": SG_ID_2022,
                "sgTypecode": "5",
                "pageNo": 1,
                "numOfRows": 3,
                "resultType": "json",
            },
            timeout=20,
        )
        return {
            "status_code": res.status_code,
            "tested_url": url,
            "usable": res.status_code == 200,
            "note": "선관위 무투표선거구 정보 전용 OpenAPI 샘플 호출. 현재 키로는 HTTP 403이면 접근권한 미승인으로 판단",
        }
    except requests.RequestException as exc:
        return {
            "status": "request_failed",
            "tested_url": url,
            "error": str(exc),
        }


def load_2026_major_stats() -> dict[str, dict[str, dict[str, Any]]]:
    payload = load_json(KEY_STATS_2026)
    by_party: dict[str, dict[str, dict[str, Any]]] = {party: {} for party in MAJOR_PARTIES}
    for row in payload["major_party_comparison"]:
        by_party["더불어민주당"][row["axis"]] = {
            "count": row["democratic_count"],
            "rate": row["democratic_rate"],
        }
        by_party["국민의힘"][row["axis"]] = {
            "count": row["ppp_count"],
            "rate": row["ppp_rate"],
        }
    return by_party


def load_2026_uncontested_stats() -> dict[str, dict[str, Any]]:
    payload = load_json(KEY_STATS_2026)
    rows = payload["uncontested_key_stats"]["by_party"]
    return {row["party"]: row for row in rows}


def comparison_rows(uncontested_2022: dict[str, Any]) -> list[dict[str, Any]]:
    stats_2026 = load_2026_major_stats()
    uncontested_2026 = load_2026_uncontested_stats()
    by_party_2022 = {row["party"]: row for row in uncontested_2022["by_party"]}
    rows: list[dict[str, Any]] = []
    unavailable_note = "2022 후보자 상세/PDF 공개정보 미확보: 후보자정보 OpenAPI 기본 응답에는 전과·체납·병역 필드가 없음"
    for party in MAJOR_PARTIES:
        for axis in AXIS_ORDER:
            if axis == "무투표 당선 규모":
                item_2022 = by_party_2022[party]
                item_2026 = uncontested_2026[party]
                c2022 = item_2022["uncontested_candidates"]
                r2022 = item_2022["uncontested_rate_pct"]
                c2026 = item_2026["무투표당선_후보수"]
                r2026 = item_2026["정당전체후보대비_무투표비율"]
                rows.append({
                    "party": party,
                    "axis": axis,
                    "count_2022": c2022,
                    "rate_2022_pct": r2022,
                    "count_2026": c2026,
                    "rate_2026_pct": r2026,
                    "change_pct_point": round(r2026 - r2022, 1),
                    "judgement": "헐거워졌다" if r2026 > r2022 else "타이트해졌다" if r2026 < r2022 else "변화없음",
                    "source_status": "2022·2026 모두 산출",
                    "note": "분모는 해당 정당 활성 후보 전체, 분자는 등록후보수 <= 의원정수 또는 비례 단일정당명부",
                })
                continue
            if axis == "무투표 후보 중 전과·체납":
                item_2026 = uncontested_2026[party]
                rows.append({
                    "party": party,
                    "axis": axis,
                    "count_2022": "확인 불가",
                    "rate_2022_pct": "확인 불가",
                    "count_2026": item_2026["전과또는체납_합집합"],
                    "rate_2026_pct": item_2026["무투표후보내_전과또는체납비율"],
                    "change_pct_point": "확인 불가",
                    "judgement": "확인 불가",
                    "source_status": "2022 상세정보 미확보",
                    "note": unavailable_note,
                })
                continue
            rows.append({
                "party": party,
                "axis": axis,
                "count_2022": "확인 불가",
                "rate_2022_pct": "확인 불가",
                "count_2026": stats_2026[party][axis]["count"],
                "rate_2026_pct": stats_2026[party][axis]["rate"],
                "change_pct_point": "확인 불가",
                "judgement": "확인 불가",
                "source_status": "2022 상세정보 미확보",
                "note": unavailable_note,
            })
    return rows


def by_party_denominator_rows(active: list[dict[str, Any]]) -> list[dict[str, Any]]:
    counts = Counter(row.get("party") for row in active)
    return [
        {
            "party": party,
            "active_candidates": counts.get(party, 0),
            "share_of_all_active_pct": pct(counts.get(party, 0), len(active)),
        }
        for party in MAJOR_PARTIES
    ]


def build_markdown(
    comparison: list[dict[str, Any]],
    denom_rows: list[dict[str, Any]],
    uncontested: dict[str, Any],
    probe: dict[str, Any],
    uncontested_probe: dict[str, Any],
) -> str:
    by_party = {row["party"]: row for row in denom_rows}
    uc_by_party = {row["party"]: row for row in uncontested["by_party"]}

    def table_for_party(party: str) -> str:
        lines = ["| 축 | 2022 (8회) | 2026 (9회) | 변화(%p) | 판정 |", "|---|---:|---:|---:|---|"]
        for row in comparison:
            if row["party"] != party:
                continue
            v2022 = (
                f"{int(row['count_2022']):,}명 ({float(row['rate_2022_pct']):.1f}%)"
                if isinstance(row["count_2022"], int)
                else "확인 불가"
            )
            v2026 = f"{int(row['count_2026']):,}명 ({float(row['rate_2026_pct']):.1f}%)"
            lines.append(
                f"| {row['axis']} | {v2022} | {v2026} | {row['change_pct_point']} | {row['judgement']} |"
            )
        return "\n".join(lines)

    probe_line = (
        f"`{probe.get('tested_url')}` → HTTP {probe.get('status_code')}"
        if probe.get("tested_url")
        else json.dumps(probe, ensure_ascii=False)
    )
    uncontested_probe_line = (
        f"`{uncontested_probe.get('tested_url')}` → HTTP {uncontested_probe.get('status_code')}"
        if uncontested_probe.get("tested_url")
        else json.dumps(uncontested_probe, ensure_ascii=False)
    )

    return f"""# 8회 지선(2022) vs 9회 지선(2026) 양당 시계열 긴급 패키지

생성 시각: {now_kst().strftime('%Y-%m-%d %H:%M:%S KST')}

## 결론부터

- 2022년 후보자 기본 OpenAPI는 정상 응답했고, 양당 분모와 무투표 당선 규모는 산출했다.
- 전과·체납·병역 축은 2022 후보자 상세 공개정보/PDF endpoint를 아직 확보하지 못해 `확인 불가`로 둔다.
- 2026년에 쓰던 상세 페이지 경로를 2022 huboid에 적용하면 다음처럼 404가 난다: {probe_line}
- 선관위 무투표선거구 전용 OpenAPI도 확인했지만 현재 보유 키로는 다음처럼 403이 난다: {uncontested_probe_line}

## 분모

| 정당 | 2022 활성 후보 | 전체 활성 후보 내 비중 |
|---|---:|---:|
| 더불어민주당 | {by_party['더불어민주당']['active_candidates']:,}명 | {by_party['더불어민주당']['share_of_all_active_pct']:.1f}% |
| 국민의힘 | {by_party['국민의힘']['active_candidates']:,}명 | {by_party['국민의힘']['share_of_all_active_pct']:.1f}% |

## 무투표 당선 축

| 정당 | 2022 무투표 후보 | 정당 후보 대비 |
|---|---:|---:|
| 더불어민주당 | {uc_by_party['더불어민주당']['uncontested_candidates']:,}명 | {uc_by_party['더불어민주당']['uncontested_rate_pct']:.1f}% |
| 국민의힘 | {uc_by_party['국민의힘']['uncontested_candidates']:,}명 | {uc_by_party['국민의힘']['uncontested_rate_pct']:.1f}% |

전체 2022 무투표 후보 산출값: {uncontested['total_uncontested_candidates']:,}명 / 선거구 {uncontested['total_uncontested_districts']:,}곳.

주의: 이 508명은 현재 선관위 후보자정보 OpenAPI와 의원정수 코드로 재계산한 값이다. 2022년 보도·자료에는 508명 또는 509명으로 병기된 사례가 있어, 원문에서는 “선관위 OpenAPI 재계산 기준 508명”으로 쓰는 편이 안전하다.

## 더불어민주당

{table_for_party('더불어민주당')}

## 국민의힘

{table_for_party('국민의힘')}

## 방송용 문장

2022년 제8회 지방선거의 후보자 기본 OpenAPI 기준으로는 양당 분모와 무투표 당선 규모까지 확인됐지만, 전과·체납·병역 상세정보는 현재 2026년과 같은 공개정보 endpoint로는 2022 자료가 열리지 않아 원문 수치 비교는 보류해야 합니다.

## 원자료와 한계

- 선관위 후보자정보 OpenAPI: `PofelcddInfoInqireService/getPofelcddRegistSttusInfoInqire`
- 선관위 코드정보 OpenAPI: `CommonCodeService/getCommonSggCodeList`, `getCommonGusigunCodeList`
- 선관위 무투표선거구 정보 전용 OpenAPI: `WtvtelpcInfoInqireService/getWtvtelpccndaInfoInqire`는 존재하지만 현재 키로는 HTTP 403.
- 2022 후보 등록 마감 시점별 원자료가 아니라, 현재 조회 가능한 역사 선거 OpenAPI 응답이다. `status=등록` 후보만 활성 후보로 계산했다.
- 후보자 기본 API에는 전과·체납·병역 필드가 없고, 2022 상세 공개정보/PDF 경로가 확인되지 않아 세부 검증축은 추정하지 않았다.
"""


def main() -> None:
    api_key = os.environ.get("NEC_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("환경변수 NEC_API_KEY가 필요합니다.")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    constituencies = ensure_2022_codes(api_key)
    snapshot = ensure_2022_candidates(api_key)
    candidates = snapshot["candidates"]
    active = [
        {**row, "party": row.get("jdName") or "무소속"}
        for row in candidates
        if is_active(row)
    ]
    uncontested = build_uncontested_metrics(candidates, constituencies)
    denom_rows = by_party_denominator_rows(uncontested["active_candidates"])
    probe = detail_endpoint_probe(active)
    uncontested_probe = uncontested_api_probe(api_key)
    comparison = comparison_rows(uncontested)

    write_csv(
        DATA_DIR / "party_denominators_2022.csv",
        denom_rows,
        ["party", "active_candidates", "share_of_all_active_pct"],
    )
    write_csv(
        DATA_DIR / "uncontested_by_party_2022.csv",
        uncontested["by_party"],
        ["party", "total_candidates", "uncontested_candidates", "uncontested_rate_pct"],
    )
    write_csv(
        DATA_DIR / "uncontested_candidates_2022.csv",
        uncontested["uncontested_candidates"],
        [
            "huboid",
            "name",
            "party",
            "sgTypecode",
            "office",
            "sdName",
            "sggName",
            "district_key",
            "seat_count",
            "candidate_count",
            "uncontested_basis",
        ],
    )
    write_csv(
        DATA_DIR / "timeseries_10_axis_comparison.csv",
        comparison,
        [
            "party",
            "axis",
            "count_2022",
            "rate_2022_pct",
            "count_2026",
            "rate_2026_pct",
            "change_pct_point",
            "judgement",
            "source_status",
            "note",
        ],
    )
    write_json(
        DATA_DIR / "key_stats.json",
        {
            "generated_at": now_kst().isoformat(timespec="seconds"),
            "sgId_2022": SG_ID_2022,
            "sgId_2026": SG_ID_2026,
            "party_denominators_2022": denom_rows,
            "uncontested_2022": {
                "total_uncontested_candidates": uncontested["total_uncontested_candidates"],
                "total_uncontested_districts": uncontested["total_uncontested_districts"],
                "by_party": uncontested["by_party"],
            },
            "detail_endpoint_probe": probe,
            "uncontested_api_probe": uncontested_probe,
            "unavailable_axes": [
                axis for axis in AXIS_ORDER if axis != "무투표 당선 규모"
            ],
        },
    )
    md = build_markdown(comparison, denom_rows, uncontested, probe, uncontested_probe)
    (OUT_DIR / "CLAUDE_2022_2026_TIMESERIES_STATUS_20260519.md").write_text(md, encoding="utf-8")

    with zipfile.ZipFile(ZIP_PATH, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in OUT_DIR.rglob("*"):
            if path.is_file():
                zf.write(path, path.relative_to(OUT_DIR.parent))

    print(f"written: {OUT_DIR.relative_to(ROOT)}")
    print(f"zip: {ZIP_PATH.relative_to(ROOT)}")
    print(f"2022 active 민주당={next(r for r in denom_rows if r['party']=='더불어민주당')['active_candidates']:,}, "
          f"국민의힘={next(r for r in denom_rows if r['party']=='국민의힘')['active_candidates']:,}")
    print(f"2022 uncontested candidates={uncontested['total_uncontested_candidates']:,}, "
          f"districts={uncontested['total_uncontested_districts']:,}")
    print(f"detail probe: {probe}")


if __name__ == "__main__":
    main()
