#!/usr/bin/env python3
"""
선관위 전과 PDF를 OCR해서 범죄 유형 색인을 만든다.

기본 산출물:
    data/criminal_ocr.json

윈도우에서는 Windows OCR(한국어 언어팩)을 우선 사용하고,
그 외 환경에서는 tesseract 명령이 있으면 kor+eng 모델로 처리한다.
PDF와 추출 이미지는 cache 디렉터리에 저장하고 커밋하지 않는다.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DETAILS_FILE = ROOT / "data" / "candidate_details.json"
CANDIDATE_DIR = ROOT / "data" / "candidates" / "20260603"
OUT_FILE = ROOT / "data" / "criminal_ocr.json"
CACHE_DIR = ROOT / "data" / ".criminal_ocr_cache"

CRIME_KEYWORDS = {
    "사기": ["사기"],
    "음주운전": ["음주운전"],
    "무면허운전": ["무면허운전"],
    "도로교통": ["도로교통법"],
    "폭력": ["폭력행위", "공동폭행", "폭행", "상해"],
    "공무집행방해": ["공무집행방해"],
    "집시법": ["집회및시위", "집회 및 시위"],
    "공직선거법": ["공직선거법"],
    "정치자금법": ["정치자금법"],
    "뇌물": ["뇌물"],
    "횡령·배임": ["횡령", "배임"],
    "절도": ["절도"],
    "성범죄": ["성폭력", "강제추행", "성매매", "아동청소년"],
    "마약": ["마약", "향정"],
    "명예훼손·모욕": ["명예훼손", "모욕"],
    "업무방해": ["업무방해"],
    "재물손괴": ["재물손괴"],
    "주거침입": ["주거침입"],
    "국가공무원법": ["국가공무원법"],
}

WIN_OCR_SCRIPT = r"""
Add-Type -AssemblyName System.Runtime.WindowsRuntime
[Windows.Storage.StorageFile, Windows.Storage, ContentType=WindowsRuntime] | Out-Null
[Windows.Storage.FileAccessMode, Windows.Storage, ContentType=WindowsRuntime] | Out-Null
[Windows.Storage.Streams.IRandomAccessStream, Windows.Storage.Streams, ContentType=WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType=WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics.Imaging, ContentType=WindowsRuntime] | Out-Null
[Windows.Globalization.Language, Windows.Globalization, ContentType=WindowsRuntime] | Out-Null
[Windows.Media.Ocr.OcrEngine, Windows.Media.Ocr, ContentType=WindowsRuntime] | Out-Null
[Windows.Media.Ocr.OcrResult, Windows.Media.Ocr, ContentType=WindowsRuntime] | Out-Null
$asTaskGeneric = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, [Type]$type) {
  $asTask = $asTaskGeneric.MakeGenericMethod($type)
  $task = $asTask.Invoke($null, @($op))
  $task.Wait() | Out-Null
  $task.Result
}
$path = (Resolve-Path $args[0]).Path
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($path)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$decoder = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bitmap = Await ($decoder.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$lang = [Windows.Globalization.Language]::new('ko')
$engine = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage($lang)
if (-not $engine) {
  Write-Error 'NO_KOREAN_OCR_ENGINE'
  exit 2
}
$result = Await ($engine.RecognizeAsync($bitmap)) ([Windows.Media.Ocr.OcrResult])
$result.Text
"""


def url_key(url: str) -> str:
    return hashlib.sha1(url.encode("utf-8")).hexdigest()[:16]


def download(url: str, cache_dir: Path) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    dest = cache_dir / f"{url_key(url)}.PDF"
    if dest.exists() and dest.stat().st_size:
        return dest
    with urllib.request.urlopen(url, timeout=30) as response:
        dest.write_bytes(response.read())
    return dest


def extract_jpegs(pdf_path: Path, cache_dir: Path) -> list[Path]:
    data = pdf_path.read_bytes()
    out = []
    for idx, match in enumerate(re.finditer(rb"stream\r?\n(.*?)\r?\nendstream", data, re.S), start=1):
        stream = match.group(1)
        if not stream.startswith(b"\xff\xd8"):
            continue
        img_path = cache_dir / f"{pdf_path.stem}_{idx}.jpg"
        if not img_path.exists():
            img_path.write_bytes(stream)
        out.append(img_path)
    return out


def windows_ocr(image_path: Path, helper_script: Path) -> str:
    result = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(helper_script),
            str(image_path),
        ],
        check=True,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout.strip()


def tesseract_ocr(image_path: Path) -> str:
    result = subprocess.run(
        ["tesseract", str(image_path), "stdout", "-l", "kor+eng", "--psm", "6"],
        check=True,
        text=True,
        capture_output=True,
        encoding="utf-8",
        errors="replace",
    )
    return result.stdout.strip()


def available_engine() -> str:
    if os.name == "nt":
        return "windows"
    if shutil.which("tesseract"):
        return "tesseract"
    return ""


def compact_text(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def offense_section(text: str) -> str:
    compact = compact_text(text)
    start = compact.find("죄명")
    if start >= 0:
        compact = compact[start + len("죄명"):]
    for marker in ("첨부서류", "침부서류", "범죄경력조회", "선거구명후보자성명", "2026년"):
        idx = compact.find(marker)
        if idx > 0:
            compact = compact[:idx]
            break
    return compact or compact_text(text)


def classify(text: str) -> tuple[list[str], dict[str, list[str]]]:
    compact = offense_section(text)
    categories = []
    matched = {}
    for category, terms in CRIME_KEYWORDS.items():
        hits = [term for term in terms if compact_text(term) in compact]
        if hits:
            categories.append(category)
            matched[category] = hits
    return categories, matched


def load_details() -> list[dict]:
    payload = json.loads(DETAILS_FILE.read_text(encoding="utf-8"))
    return payload.get("details", [])


def load_candidate_map() -> dict[str, dict]:
    files = sorted(CANDIDATE_DIR.glob("snapshot_*.json"))
    if not files:
        return {}
    payload = json.loads(files[-1].read_text(encoding="utf-8"))
    return {str(c.get("huboid")): c for c in payload.get("candidates", []) if c.get("huboid")}


def candidate_row(detail: dict, candidate_map: dict[str, dict], text: str, categories: list[str], matched: dict, pdf_urls: list[str]) -> dict:
    huboid = str(detail.get("huboid") or "")
    cand = candidate_map.get(huboid) or detail.get("candidate") or {}
    disclosures = detail.get("disclosures") or {}
    return {
        "huboid": huboid or cand.get("huboid"),
        "name": cand.get("name") or detail.get("name") or "",
        "party": cand.get("jdName") or "",
        "sdName": cand.get("sdName") or "",
        "sggName": cand.get("sggName") or "",
        "wiwName": cand.get("wiwName") or "",
        "criminal_record": disclosures.get("criminal_record") or "",
        "categories": categories,
        "matched_terms": matched,
        "offense_text": offense_section(text),
        "ocr_text": text,
        "pdf_urls": pdf_urls,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="처리할 후보 수 제한")
    parser.add_argument("--huboid", help="특정 후보만 처리")
    parser.add_argument("--cache-dir", type=Path, default=CACHE_DIR)
    parser.add_argument("--out", type=Path, default=OUT_FILE)
    args = parser.parse_args()

    engine = available_engine()
    if not engine:
        sys.exit("OCR 엔진을 찾지 못했습니다. Windows OCR 또는 tesseract가 필요합니다.")

    args.cache_dir.mkdir(parents=True, exist_ok=True)
    helper_script = args.cache_dir / "win_ocr_image.ps1"
    if engine == "windows":
        helper_script.write_text(WIN_OCR_SCRIPT, encoding="utf-8")

    details = [
        d for d in load_details()
        if d.get("scan_files", {}).get("criminal")
        and (not args.huboid or str(d.get("huboid")) == str(args.huboid))
    ]
    if args.limit:
        details = details[:args.limit]

    candidate_map = load_candidate_map()
    records = []
    failures = []
    for idx, detail in enumerate(details, start=1):
        huboid = str(detail.get("huboid") or "")
        pdf_urls = [f.get("pdf_url", "") for f in detail.get("scan_files", {}).get("criminal", []) if f.get("pdf_url")]
        texts = []
        try:
            for url in pdf_urls:
                pdf_path = download(url, args.cache_dir)
                images = extract_jpegs(pdf_path, args.cache_dir)
                if not images:
                    raise RuntimeError("PDF 이미지 스트림을 찾지 못했습니다.")
                for image in images:
                    texts.append(windows_ocr(image, helper_script) if engine == "windows" else tesseract_ocr(image))
            text = "\n".join(t for t in texts if t)
            categories, matched = classify(text)
            records.append(candidate_row(detail, candidate_map, text, categories, matched, pdf_urls))
            print(f"[{idx}/{len(details)}] {huboid} {categories or ['미분류']}")
        except Exception as exc:  # noqa: BLE001
            failures.append({"huboid": huboid, "error": str(exc)})
            print(f"[{idx}/{len(details)}] {huboid} 실패: {exc}", file=sys.stderr)

    category_counts = Counter(cat for r in records for cat in r["categories"])
    output = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "engine": engine,
            "processed": len(records),
            "failures": len(failures),
            "total_candidates_with_criminal_pdf": len(details),
            "partial": bool(args.limit or args.huboid),
        },
        "categories": [
            {"category": category, "count": count}
            for category, count in sorted(category_counts.items(), key=lambda x: (-x[1], x[0]))
        ],
        "records": records,
        "failures": failures,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        out_label = args.out.resolve().relative_to(ROOT)
    except ValueError:
        out_label = args.out
    print(f"전과 OCR 색인: {len(records)}명 -> {out_label}")


if __name__ == "__main__":
    main()
