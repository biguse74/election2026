#!/usr/bin/env python3
"""
선관위 후보자 사진 썸네일을 GitHub Pages에서 바로 제공할 수 있게 로컬 캐시로 저장한다.

후보자 상세 수집 결과의 photo.thumbnail_url은 info.nec.go.kr을 직접 바라보는데,
후보 카드가 열릴 때마다 선관위 서버 응답을 기다리면 체감 속도가 크게 떨어진다.
이 스크립트는 썸네일을 data/photos/{sgId}/ 아래에 저장하고
data/candidate_details.json의 photo.cached_thumbnail_url을 갱신한다.
"""

from __future__ import annotations

import argparse
import json
import mimetypes
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.error import URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen

TARGET_SG_ID = "20260603"
ROOT_DIR = Path(__file__).resolve().parent.parent
DETAILS_FILE = ROOT_DIR / "data" / "candidate_details.json"
PHOTO_DIR = ROOT_DIR / "data" / "photos" / TARGET_SG_ID
MANIFEST_FILE = PHOTO_DIR / "manifest.json"
ALLOWED_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
REQUEST_HEADERS = {
    "User-Agent": "newtamsa-election2026/1.0 (+https://github.com/biguse74/election2026)",
    "Referer": "https://info.nec.go.kr/",
}


def relative_path(path: Path) -> str:
    return path.resolve().relative_to(ROOT_DIR).as_posix()


def normalize_ext(ext: str) -> str:
    ext = ext.lower()
    return ".jpg" if ext == ".jpeg" else ext


def extension_from_response(url: str, content_type: str) -> str:
    ext = Path(urlparse(url).path).suffix.lower()
    if ext in ALLOWED_EXTS:
        return normalize_ext(ext)

    mime = content_type.split(";", 1)[0].strip().lower()
    guessed = mimetypes.guess_extension(mime) if mime else ""
    if guessed in ALLOWED_EXTS:
        return normalize_ext(guessed)
    return ".jpg"


def load_manifest(path: Path) -> dict:
    if not path.exists():
        return {"version": 1, "photos": {}}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"version": 1, "photos": {}}
    if not isinstance(data, dict):
        return {"version": 1, "photos": {}}
    data.setdefault("version", 1)
    data.setdefault("photos", {})
    return data


def cached_file_from_manifest(manifest: dict, hubo_id: str, source_url: str) -> Path | None:
    photo = manifest.get("photos", {}).get(hubo_id) or {}
    cached_path = photo.get("path") or ""
    if photo.get("source") != source_url or not cached_path:
        return None

    path = ROOT_DIR / cached_path
    if path.exists() and path.stat().st_size > 0:
        return path
    return None


def remove_old_cached_files(photo_dir: Path, hubo_id: str) -> None:
    for path in photo_dir.glob(f"{hubo_id}.*"):
        if path.name == "manifest.json":
            continue
        path.unlink(missing_ok=True)


def download_photo(source_url: str, dest_base: Path, refresh: bool) -> Path:
    if refresh:
        remove_old_cached_files(dest_base.parent, dest_base.name)
    else:
        for existing in dest_base.parent.glob(f"{dest_base.name}.*"):
            if existing.name == "manifest.json":
                continue
            if existing.stat().st_size > 0:
                return existing

    request = Request(source_url, headers=REQUEST_HEADERS)
    with urlopen(request, timeout=30) as response:
        content_type = response.headers.get("content-type", "")
        content = response.read()

    if not content:
        raise RuntimeError("empty image response")

    ext = extension_from_response(source_url, content_type)
    dest = dest_base.with_suffix(ext)
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(content)
    return dest


def cache_photos(
    details_file: Path,
    output_file: Path,
    photo_dir: Path,
    limit: int,
    huboids: set[str],
    refresh: bool,
    delay: float,
    workers: int,
) -> tuple[int, int, int]:
    payload = json.loads(details_file.read_text(encoding="utf-8"))
    details = payload.get("details") or []
    if not isinstance(details, list):
        raise RuntimeError(f"details 배열을 찾을 수 없습니다: {details_file}")

    photo_dir.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest(MANIFEST_FILE if photo_dir == PHOTO_DIR else photo_dir / "manifest.json")
    manifest_photos = manifest.setdefault("photos", {})

    targets = []
    for row in details:
        hubo_id = str(row.get("huboid") or "")
        photo = row.get("photo") or {}
        source_url = photo.get("thumbnail_url") or ""
        if not hubo_id or not source_url:
            continue
        if huboids and hubo_id not in huboids:
            continue
        targets.append(row)

    if limit > 0:
        targets = targets[:limit]

    cached = 0
    skipped = 0
    failed = 0
    total = len(targets)

    def record_success(row: dict, source_url: str, cached_path: Path) -> None:
        photo = row.setdefault("photo", {})
        rel_path = relative_path(cached_path)
        photo["cached_thumbnail_url"] = rel_path
        manifest_photos[str(row.get("huboid") or "")] = {
            "source": source_url,
            "path": rel_path,
            "bytes": cached_path.stat().st_size,
        }

    def report(processed: int) -> None:
        if processed % 100 == 0 or processed == total:
            print(f"사진 캐시 {processed:,}/{total:,}명 · 신규 {cached:,} · 기존 {skipped:,} · 실패 {failed:,}")

    processed = 0
    futures = {}
    max_workers = max(workers, 1)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        for idx, row in enumerate(targets, 1):
            hubo_id = str(row.get("huboid") or "")
            photo = row.setdefault("photo", {})
            source_url = photo.get("thumbnail_url") or ""
            dest_base = photo_dir / hubo_id

            manifest_entry = manifest_photos.get(hubo_id) or {}
            source_changed = bool(manifest_entry.get("source") and manifest_entry.get("source") != source_url)
            cached_path = None if refresh else cached_file_from_manifest(manifest, hubo_id, source_url)
            if cached_path is not None:
                record_success(row, source_url, cached_path)
                skipped += 1
                processed += 1
                report(processed)
                continue

            future = executor.submit(download_photo, source_url, dest_base, refresh or source_changed)
            futures[future] = (idx, row, hubo_id, source_url)

            if delay > 0:
                time.sleep(delay)

        for future in as_completed(futures):
            _idx, row, hubo_id, source_url = futures[future]
            try:
                cached_path = future.result()
                record_success(row, source_url, cached_path)
                cached += 1
            except (OSError, TimeoutError, URLError, RuntimeError) as exc:
                failed += 1
                print(f"실패 {hubo_id}: {exc}", file=sys.stderr)

            processed += 1
            report(processed)

    manifest_path = photo_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    output_file.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return cached, skipped, failed


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--details-file", type=Path, default=DETAILS_FILE, help="후보 상세 JSON 경로")
    parser.add_argument("--out", type=Path, default=DETAILS_FILE, help="갱신한 JSON 저장 경로")
    parser.add_argument("--photo-dir", type=Path, default=PHOTO_DIR, help="사진 캐시 디렉터리")
    parser.add_argument("--huboid", action="append", default=[], help="특정 huboid만 처리")
    parser.add_argument("--limit", type=int, default=0, help="앞에서 N명만 처리. 0이면 전체")
    parser.add_argument("--refresh", action="store_true", help="기존 캐시를 지우고 다시 받기")
    parser.add_argument("--delay", type=float, default=0.0, help="후보별 대기 초")
    parser.add_argument("--workers", type=int, default=16, help="동시 다운로드 worker 수")
    parser.add_argument("--allow-failures", action="store_true", help="일부 사진 다운로드 실패가 있어도 성공 종료")
    args = parser.parse_args()

    cached, skipped, failed = cache_photos(
        details_file=args.details_file.resolve(),
        output_file=args.out.resolve(),
        photo_dir=args.photo_dir.resolve(),
        limit=args.limit,
        huboids={str(x) for x in args.huboid},
        refresh=args.refresh,
        delay=args.delay,
        workers=args.workers,
    )
    print(f"완료: 신규 {cached:,}명, 기존 {skipped:,}명, 실패 {failed:,}명")
    if failed and not args.allow_failures:
        sys.exit(1)


if __name__ == "__main__":
    main()
