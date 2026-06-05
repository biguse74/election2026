#!/usr/bin/env python3
"""
선관위 선거통계시스템 후보자 상세 페이지에서 공개정보를 보강 수집한다.

OpenAPI 후보자 정보에는 사진·재산·병역·납세·전과 요약이 빠져 있으므로,
후보 스냅샷의 huboid를 기준으로 info.nec.go.kr 상세 팝업을 조회한다.

사용:
    python scripts/fetch_candidate_details.py
    python scripts/fetch_candidate_details.py --limit 20
    python scripts/fetch_candidate_details.py --huboid 100163255 --scan-types 5

산출물:
    data/candidate_details.json
    data/candidate_details/20260603/snapshot_YYYYMMDD.json
"""

from __future__ import annotations

import argparse
import html
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urljoin

import requests

TARGET_SG_ID = "20260603"
ELECTION_ID = f"00{TARGET_SG_ID}"
BASE_URL = "https://info.nec.go.kr"
DETAIL_URL = f"{BASE_URL}/electioninfo/candidate_detail_info.xhtml"
SCAN_URL = f"{BASE_URL}/electioninfo/candidate_detail_scanSearchJson.json"
ROOT_DIR = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT_DIR / "data" / "candidate_details" / TARGET_SG_ID
LATEST_OUT = ROOT_DIR / "data" / "candidate_details.json"
KST = timezone(timedelta(hours=9))

DISCLOSURE_LABELS = {
    "재산신고액(천원)": "assets_thousand_krw",
    "병역신고사항(본인)": "military",
    "납부액(천원)": "tax_paid_thousand_krw",
    "최근 5년간 체납액(천원)": "tax_arrears_5y_thousand_krw",
    "현체납액(천원)": "tax_arrears_current_thousand_krw",
    "전과기록유무(건수)": "criminal_record",
    "입후보 횟수": "candidacy_count",
}

SCAN_TYPES = {
    "1": "education",
    "2": "assets",
    "3": "tax",
    "4": "military",
    "5": "criminal",
    "6": "education_career",
    "8": "election_career",
}

ROW_RE = re.compile(r"<tr>\s*<th[^>]*>(.*?)</th>\s*<td[^>]*>(.*?)</td>\s*</tr>", re.S)
PHOTO_LINK_RE = re.compile(r"fn_ClickPhoto\('([^']+)'\)", re.S)
PHOTO_THUMB_RE = re.compile(r"<img[^>]+src=\"([^\"]+)\"[^>]+alt=\"후보자 사진\"", re.S)
THREAD_LOCAL = threading.local()
REQUEST_HEADERS = {
    "User-Agent": "newtamsa-election2026/1.0 (+https://github.com/biguse74/election2026)",
    "Referer": f"{BASE_URL}/main/showDocument.xhtml?electionId={ELECTION_ID}&secondMenuId=CPRI03&topMenuId=CP",
}


def now_kst() -> datetime:
    return datetime.now(KST)


def clean_html(value: str) -> str:
    value = re.sub(r"<br\s*/?>", "\n", value, flags=re.I)
    value = re.sub(r"<[^>]+>", "", value)
    value = html.unescape(value)
    lines = [" ".join(line.split()) for line in value.splitlines()]
    return "\n".join(line for line in lines if line).strip()


def latest_snapshot_path() -> Path:
    folder = ROOT_DIR / "data" / "candidates" / TARGET_SG_ID
    files = sorted(folder.glob("snapshot_*.json"))
    if not files:
        sys.exit(f"후보자 스냅샷이 없습니다: {folder}")
    return files[-1]


def normalize_url(path: str) -> str:
    return urljoin(BASE_URL, path)


def parse_detail_html(text: str) -> dict:
    rows = {clean_html(k): clean_html(v) for k, v in ROW_RE.findall(text)}
    disclosures = {
        out_key: rows[label]
        for label, out_key in DISCLOSURE_LABELS.items()
        if rows.get(label)
    }

    photo_path = PHOTO_LINK_RE.search(text)
    thumb_path = PHOTO_THUMB_RE.search(text)
    photo = {}
    if photo_path:
        photo["url"] = normalize_url(photo_path.group(1))
    if thumb_path:
        photo["thumbnail_url"] = normalize_url(thumb_path.group(1))

    return {
        "photo": photo,
        "disclosures": disclosures,
    }


def scan_pdf_url(file_path: str) -> str:
    stem = file_path.rsplit(".", 1)[0] if "." in file_path else file_path
    return normalize_url(f"/unielec_pdf_file/{stem}.PDF")


def should_fetch_scan(scan_type: str, disclosures: dict, scan_all: bool) -> bool:
    if scan_all:
        return True
    if scan_type != "5":
        return True
    criminal = (disclosures.get("criminal_record") or "").strip()
    return bool(criminal and criminal != "없음")


def get_session() -> requests.Session:
    session = getattr(THREAD_LOCAL, "session", None)
    if session is None:
        session = requests.Session()
        session.headers.update(REQUEST_HEADERS)
        THREAD_LOCAL.session = session
    return session


def fetch_scan_files(
    hubo_id: str,
    scan_types: list[str],
    disclosures: dict,
    scan_all: bool,
) -> dict:
    out: dict[str, list[dict]] = {}
    for scan_type in scan_types:
        if scan_type not in SCAN_TYPES:
            continue
        if not should_fetch_scan(scan_type, disclosures, scan_all):
            continue
        session = get_session()
        params = {
            "gubun": scan_type,
            "electionId": ELECTION_ID,
            "huboId": hubo_id,
            "statementId": "CPRI03_candidate_scanSearch",
        }
        res = session.get(SCAN_URL, params=params, timeout=30)
        res.raise_for_status()
        payload = res.json()
        rows = payload.get("jsonResult", {}).get("body") or []
        if isinstance(rows, dict):
            rows = [rows]

        files = []
        for row in rows:
            file_path = row.get("FILEPATH")
            if not file_path:
                continue
            files.append({
                "source_path": file_path,
                "pdf_url": scan_pdf_url(file_path),
                "display_seq": row.get("DISP_SEQ"),
            })
        if files:
            out[SCAN_TYPES[scan_type]] = files
    return out


def fetch_one(
    candidate: dict,
    scan_types: list[str],
    scan_all: bool,
) -> dict:
    hubo_id = str(candidate["huboid"])
    session = get_session()
    res = session.get(
        DETAIL_URL,
        params={"electionId": ELECTION_ID, "huboId": hubo_id},
        timeout=30,
    )
    res.raise_for_status()
    parsed = parse_detail_html(res.text)
    scan_files = fetch_scan_files(
        hubo_id,
        scan_types,
        parsed["disclosures"],
        scan_all,
    )

    row = {
        "huboid": hubo_id,
        "name": candidate.get("name", ""),
        "sgTypecode": str(candidate.get("sgTypecode", "")),
        "sdName": candidate.get("sdName", ""),
        "sggName": candidate.get("sggName", ""),
        "jdName": candidate.get("jdName", ""),
        "nec_detail_url": f"{DETAIL_URL}?electionId={ELECTION_ID}&huboId={hubo_id}",
        **parsed,
    }
    if scan_files:
        row["scan_files"] = scan_files
    return row


def parse_scan_types(value: str) -> list[str]:
    if not value:
        return []
    if value == "all":
        return list(SCAN_TYPES)
    return [x.strip() for x in value.split(",") if x.strip()]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--snapshot", type=Path, default=None, help="읽을 후보자 스냅샷 JSON")
    parser.add_argument("--huboid", action="append", default=[], help="특정 huboid만 수집")
    parser.add_argument("--limit", type=int, default=0, help="앞에서 N명만 수집")
    parser.add_argument("--delay", type=float, default=0.02, help="작업 제출 사이 대기 초")
    parser.add_argument("--workers", type=int, default=8, help="동시 수집 worker 수")
    parser.add_argument("--scan-types", default="5", help="수집할 스캔파일 유형. 예: 5, 2,3,4,5, all, 빈 문자열")
    parser.add_argument("--scan-all-candidates", action="store_true", help="전과 없음 후보도 전과 PDF endpoint 조회")
    args = parser.parse_args()

    snapshot_path = args.snapshot or latest_snapshot_path()
    snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
    candidates = [c for c in snapshot.get("candidates", []) if c.get("huboid")]
    if args.huboid:
        wanted = {str(x) for x in args.huboid}
        candidates = [c for c in candidates if str(c.get("huboid")) in wanted]
    if args.limit:
        candidates = candidates[:args.limit]

    scan_types = parse_scan_types(args.scan_types)
    print(f"후보 상세 수집: {len(candidates):,}명")
    print(f"후보 스냅샷: {snapshot_path.relative_to(ROOT_DIR)}")
    print(f"스캔파일 유형: {scan_types or '없음'}")
    print(f"동시 작업: {max(args.workers, 1)}")

    started_at = now_kst()
    details: list[dict] = []
    errors: list[dict] = []

    with ThreadPoolExecutor(max_workers=max(args.workers, 1)) as executor:
        futures = {}
        for candidate in candidates:
            future = executor.submit(fetch_one, candidate, scan_types, args.scan_all_candidates)
            futures[future] = candidate
            if args.delay > 0:
                time.sleep(args.delay)

        for idx, future in enumerate(as_completed(futures), 1):
            candidate = futures[future]
            hubo_id = str(candidate.get("huboid"))
            try:
                details.append(future.result())
            except Exception as exc:  # noqa: BLE001 - 수집 작업은 개별 실패를 기록하고 계속 진행
                errors.append({
                    "huboid": hubo_id,
                    "name": candidate.get("name", ""),
                    "error": str(exc),
                })
                print(f"  실패 {hubo_id} {candidate.get('name', '')}: {exc}", file=sys.stderr)

            if idx % 100 == 0 or idx == len(candidates):
                print(f"  진행 {idx:,}/{len(candidates):,}명 · 실패 {len(errors):,}")

    details.sort(key=lambda d: int(d["huboid"]) if str(d.get("huboid", "")).isdigit() else str(d.get("huboid", "")))

    today = now_kst().strftime("%Y%m%d")
    payload = {
        "sgId": TARGET_SG_ID,
        "electionId": ELECTION_ID,
        "generated_at": started_at.isoformat(timespec="seconds"),
        "source": "https://info.nec.go.kr",
        "candidate_snapshot": str(snapshot_path.relative_to(ROOT_DIR)).replace("\\", "/"),
        "count": len(details),
        "error_count": len(errors),
        "details": details,
        "errors": errors,
    }

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_file = OUT_DIR / f"snapshot_{today}.json"
    text = json.dumps(payload, ensure_ascii=False, indent=2)
    # 날짜 스냅샷은 항상 기록(실패도 추적용).
    out_file.write_text(text, encoding="utf-8")
    # ── 축소 방지 가드 ──────────────────────────────────────────────
    # 선거 종료 후 NEC 상세 페이지가 내려가(404) 전부 실패하면 후보 상세가 0건이 된다.
    # 후보 상세는 사후 불변 아카이브이므로, 새 수집이 0건이거나 기존의 80% 미만이면
    # 기존 정상본(candidate_details.json)을 덮어쓰지 않고 보존한다.
    prev_count = 0
    if LATEST_OUT.exists():
        try:
            prev_count = int(json.loads(LATEST_OUT.read_text(encoding="utf-8")).get("count", 0) or 0)
        except Exception:
            prev_count = 0
    if prev_count > 0 and len(details) < max(1, int(prev_count * 0.8)):
        print(f"[보존] 새 수집 {len(details):,}건 < 기존 {prev_count:,}건의 80% "
              f"(실패 {len(errors):,}건, 선거 후 404 추정) — candidate_details.json 덮어쓰기 생략")
    else:
        LATEST_OUT.write_text(text, encoding="utf-8")

    elapsed = (now_kst() - started_at).total_seconds()
    print("=" * 60)
    print(f"수집 완료: 상세 {len(details):,}명, 실패 {len(errors):,}, {elapsed:.1f}초")
    print(f"저장: {out_file.relative_to(ROOT_DIR)}")
    print(f"최신본: {LATEST_OUT.relative_to(ROOT_DIR)}")


if __name__ == "__main__":
    main()
