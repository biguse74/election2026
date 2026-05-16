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
CLASSIFICATION_VERSION = 12
PDF_HEADERS = {
    "User-Agent": "newtamsa-election2026/1.0 (+https://github.com/biguse74/election2026)",
    "Referer": "https://info.nec.go.kr/",
}

CRIME_KEYWORDS = {
    "사기": ["사기"],
    "횡령": ["횡령"],
    "배임": ["배임"],
    "뇌물": ["뇌물", "수뢰", "알선수재"],
    "정치자금법": ["정치자금법"],
    "공직선거법": ["공직선거법"],
    "청탁금지법": ["부정청탁", "청탁금지법", "금품등수수"],
    "직권남용": ["직권남용"],
    "허위공문서·문서위조·공용서류": [
        "허위공문서작성",
        "허위작성공문서행사",
        "공용서류손상",
        "공용서류은닉",
        "공기호부정사용",
        "부정사용공기호",
        "공무상표시무효",
        "사문서",
        "위조",
        "변조",
    ],
    "성범죄": ["성폭력", "강제추행", "성매매", "아동청소년"],
    "마약": ["마약", "향정"],
    "특가법": ["특정범죄가중처벌"],
    "음주·위험운전": ["음주운전", "위험운전치사상"],
    "무면허운전": ["무면허운전"],
    "교통사고": ["교통사고처리특례법", "교통사고처리특례", "교통사고처리복례", "교동사고"],
    "절도": ["절도"],
    "조세": ["조세범", "지방세", "관세법"],
    "보조금": ["보조금관리에관한법률", "보조금", "지방보조금"],
    "보험·금융": ["보험업법", "이자제한법", "부정수표단속법", "대부업", "자동차손해배상보장법", "전자금융거래법"],
    "폭력": ["폭력행위", "공동폭행", "폭행", "상해"],
    "공무집행방해": ["공무집행방해"],
    "업무방해": ["업무방해"],
    "재물손괴": ["재물손괴"],
    "주거침입": ["주거침입"],
    "범인도피": ["범인도피", "법인도피", "범인은닉"],
    "사법방해": ["증거은닉", "증거인멸", "위증", "무고"],
    "입찰방해": ["입찰방해"],
    "도로교통": ["도로교통법", "도로법", "일반교통방해"],
    "자동차관리": ["자동차관리법"],
    "환경": ["폐기물관리법", "대기환경보전법", "수질", "환경범죄"],
    "식품·보건": ["식품위생법", "의료법", "약사법", "감염병", "학교보건법", "공중위생관리법"],
    "교육·청소년": ["영유아보육법", "청소년보호법", "학원의설립", "과외교습"],
    "노동": ["근로기준법", "고용보험법"],
    "농수산": ["농수산물의원산지표시", "원산지표시"],
    "건축·건설·부동산": [
        "건축법",
        "건축위반법",
        "부동산",
        "농지법",
        "산지관리",
        "국토의계획",
        "개발제한구역",
        "건설업법",
        "건설산업기본법",
        "건설기계관리법",
        "주택건설촉진법",
        "소방시설공사업법",
    ],
    "총포·화약": ["총포", "도검", "화약류"],
    "야생생물": ["야생생물보호"],
    "저작권법": ["저작권법"],
    "도박": ["도박"],
    "국가보안법": ["국가보안법", "국보법"],
    "집시법": ["집회및시위", "집회 및 시위"],
    "국가공무원법": ["국가공무원법"],
    "지방공무원법": ["지방공무원법", "지방-공무원법"],
    "명예훼손": ["명예훼손"],
    "모욕": ["모욕"],
}

CATEGORY_META = {
    "사기": {"group": "공직 검증", "tone": "priority", "order": 10},
    "횡령": {"group": "공직 검증", "tone": "priority", "order": 11},
    "배임": {"group": "공직 검증", "tone": "priority", "order": 12},
    "뇌물": {"group": "공직 검증", "tone": "priority", "order": 13},
    "정치자금법": {"group": "공직 검증", "tone": "priority", "order": 14},
    "공직선거법": {"group": "공직 검증", "tone": "priority", "order": 15},
    "청탁금지법": {"group": "공직 검증", "tone": "priority", "order": 16},
    "직권남용": {"group": "공직 검증", "tone": "priority", "order": 17},
    "허위공문서·문서위조·공용서류": {"group": "공직 검증", "tone": "priority", "order": 18},
    "성범죄": {"group": "공직 검증", "tone": "priority", "order": 22},
    "특가법": {"group": "공직 검증", "tone": "priority", "order": 24},
    "음주·위험운전": {"group": "공직 검증", "tone": "priority", "order": 25},
    "무면허운전": {"group": "공직 검증", "tone": "priority", "order": 26},
    "절도": {"group": "공직 검증", "tone": "priority", "order": 28},
    "조세": {"group": "공직 검증", "tone": "priority", "order": 29},
    "보조금": {"group": "공직 검증", "tone": "priority", "order": 30},
    "폭력": {"group": "폭력·질서", "tone": "standard", "order": 40},
    "공무집행방해": {"group": "폭력·질서", "tone": "standard", "order": 41},
    "업무방해": {"group": "폭력·질서", "tone": "standard", "order": 42},
    "재물손괴": {"group": "폭력·질서", "tone": "standard", "order": 43},
    "주거침입": {"group": "폭력·질서", "tone": "standard", "order": 44},
    "범인도피": {"group": "폭력·질서", "tone": "standard", "order": 45},
    "사법방해": {"group": "폭력·질서", "tone": "standard", "order": 46},
    "입찰방해": {"group": "폭력·질서", "tone": "standard", "order": 47},
    "교통사고": {"group": "교통·안전 법규", "tone": "standard", "order": 50},
    "도로교통": {"group": "교통·안전 법규", "tone": "standard", "order": 51},
    "자동차관리": {"group": "교통·안전 법규", "tone": "standard", "order": 52},
    "보험·금융": {"group": "경제·금융 법규", "tone": "standard", "order": 60},
    "환경": {"group": "생활·안전 법규", "tone": "standard", "order": 70},
    "식품·보건": {"group": "생활·안전 법규", "tone": "standard", "order": 71},
    "교육·청소년": {"group": "생활·안전 법규", "tone": "standard", "order": 72},
    "노동": {"group": "생활·안전 법규", "tone": "standard", "order": 73},
    "농수산": {"group": "생활·안전 법규", "tone": "standard", "order": 74},
    "건축·건설·부동산": {"group": "생활·안전 법규", "tone": "standard", "order": 75},
    "총포·화약": {"group": "생활·안전 법규", "tone": "standard", "order": 76},
    "야생생물": {"group": "생활·안전 법규", "tone": "standard", "order": 77},
    "국가공무원법": {"group": "공직·행정 법규", "tone": "standard", "order": 80},
    "지방공무원법": {"group": "공직·행정 법규", "tone": "standard", "order": 81},
    "국가보안법": {"group": "시국·안보 관련", "tone": "context", "order": 90},
    "집시법": {"group": "집회·시위 관련", "tone": "context", "order": 91},
    "명예훼손": {"group": "기타", "tone": "standard", "order": 100},
    "모욕": {"group": "기타", "tone": "standard", "order": 101},
    "저작권법": {"group": "기타", "tone": "standard", "order": 102},
    "마약": {"group": "기타", "tone": "standard", "order": 103},
    "도박": {"group": "기타", "tone": "standard", "order": 104},
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


def is_pdf_bytes(data: bytes) -> bool:
    return data.startswith(b"%PDF")


def download(url: str, cache_dir: Path) -> Path:
    cache_dir.mkdir(parents=True, exist_ok=True)
    dest = cache_dir / f"{url_key(url)}.PDF"
    if dest.exists() and dest.stat().st_size:
        if is_pdf_bytes(dest.read_bytes()[:8]):
            return dest
        dest.unlink(missing_ok=True)
    request = urllib.request.Request(url, headers=PDF_HEADERS)
    with urllib.request.urlopen(request, timeout=30) as response:
        data = response.read()
    if not is_pdf_bytes(data[:8]):
        preview = data[:80].decode("utf-8", errors="replace").replace("\n", " ")
        raise RuntimeError(f"non-PDF response from NEC ({len(data):,} bytes): {preview}")
    dest.write_bytes(data)
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


def is_fatal_network_error(exc: Exception) -> bool:
    return "WinError 10013" in str(exc)


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


def normalize_date(raw: str) -> str:
    digits = re.sub(r"\D", "", raw)
    if len(digits) >= 8:
        return f"{int(digits[:4]):04d}-{int(digits[4:6]):02d}-{int(digits[6:8]):02d}"
    parts = [int(p) for p in re.findall(r"\d+", raw)[:3]]
    if len(parts) != 3:
        return raw
    year, month, day = parts
    return f"{year:04d}-{month:02d}-{day:02d}"


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


def extract_offenses(text: str) -> list[dict]:
    section = offense_section(text)
    date_re = re.compile(r"(?:19|20)\d{2}[.\-/년]\s*\d{1,2}(?:[.\-/월]\s*)?\d{1,2}")
    sentence_re = re.compile(
        r"(벌금\s*[0-9,]+\s*(?:만)?원|징역\s*[0-9]+\s*(?:년|월)(?:\s*[0-9]+\s*월)?"
        r"(?:\s*집행유예\s*[0-9]+\s*년)?|금고\s*[0-9]+\s*(?:년|월)|선고유예|기소유예|무죄)"
    )
    matches = list(date_re.finditer(section))
    offenses = []
    for idx, match in enumerate(matches):
        start = match.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(section)
        chunk = section[start:end].strip("·.,;:()[]{} ")
        chunk = re.sub(r"^(처분일자|저분일자|처분결과|형량|치분결과)+", "", chunk)
        if not chunk:
            continue

        sentence = ""
        offense = chunk
        sentence_match = sentence_re.search(chunk)
        if sentence_match:
            sentence = sentence_match.group(1).strip()
            offense = chunk[:sentence_match.start()].strip("·.,;:()[]{} ")

        categories, matched = classify(chunk)
        offenses.append({
            "date": normalize_date(match.group(0)),
            "offense": offense or chunk,
            "sentence": sentence,
            "categories": categories,
            "matched_terms": matched,
            "raw": chunk,
        })
    if offenses:
        return offenses

    categories, matched = classify(section)
    if not categories:
        return []

    sentence = ""
    offense = section
    sentence_match = sentence_re.search(section)
    if sentence_match:
        sentence = sentence_match.group(1).strip()
        offense = section[:sentence_match.start()].strip("·.,;:()[]{} ")
    offense = re.sub(r"(선거구명|후보자성명|전과기록|형량|처분결과).*$", "", offense)
    dates = list(date_re.finditer(section))
    return [{
        "date": normalize_date(dates[0].group(0)) if dates else "",
        "offense": offense[:120] or section[:120],
        "sentence": sentence,
        "categories": categories,
        "matched_terms": matched,
        "raw": section[:300],
    }]


def category_sort_key(item: tuple[str, int]) -> tuple[int, int, str]:
    category, count = item
    return (CATEGORY_META.get(category, {}).get("order", 999), -count, category)


def load_details() -> list[dict]:
    payload = json.loads(DETAILS_FILE.read_text(encoding="utf-8"))
    return payload.get("details", [])


def load_candidate_map() -> dict[str, dict]:
    files = sorted(CANDIDATE_DIR.glob("snapshot_*.json"))
    if not files:
        return {}
    payload = json.loads(files[-1].read_text(encoding="utf-8"))
    return {str(c.get("huboid")): c for c in payload.get("candidates", []) if c.get("huboid")}


def criminal_pdf_urls(detail: dict) -> list[str]:
    return [
        f.get("pdf_url", "")
        for f in detail.get("scan_files", {}).get("criminal", [])
        if f.get("pdf_url")
    ]


def load_resume_records(out_file: Path) -> dict[str, dict]:
    if not out_file.exists():
        return {}
    try:
        payload = json.loads(out_file.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    meta = payload.get("meta") or {}
    if meta.get("classification_version") != CLASSIFICATION_VERSION:
        return {}
    records = payload.get("records") or []
    if not isinstance(records, list):
        return {}
    return {
        str(record.get("huboid")): record
        for record in records
        if record.get("huboid") and isinstance(record.get("pdf_urls"), list)
    }


def ordered_records(record_map: dict[str, dict], details: list[dict]) -> list[dict]:
    order = {str(detail.get("huboid") or ""): idx for idx, detail in enumerate(details)}
    return sorted(
        record_map.values(),
        key=lambda record: order.get(str(record.get("huboid") or ""), len(order)),
    )


def write_output(
    out_file: Path,
    records: list[dict],
    failures: list[dict],
    engine: str,
    total_candidates_with_criminal_pdf: int,
    selected_candidates: int,
    partial: bool,
) -> None:
    category_counts = Counter(cat for record in records for cat in record["categories"])
    offense_category_counts = Counter(
        cat
        for record in records
        for offense in record.get("offenses", [])
        for cat in offense.get("categories", [])
    )
    output = {
        "meta": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "engine": engine,
            "classification_version": CLASSIFICATION_VERSION,
            "processed": len(records),
            "failures": len(failures),
            "selected_candidates": selected_candidates,
            "total_candidates_with_criminal_pdf": total_candidates_with_criminal_pdf,
            "partial": partial,
        },
        "categories": [
            {"category": category, "count": count, **CATEGORY_META.get(category, {})}
            for category, count in sorted(category_counts.items(), key=category_sort_key)
        ],
        "offense_categories": [
            {"category": category, "count": count, **CATEGORY_META.get(category, {})}
            for category, count in sorted(offense_category_counts.items(), key=category_sort_key)
        ],
        "records": records,
        "failures": failures,
    }
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")


def reclassify_existing(out_file: Path) -> None:
    payload = json.loads(out_file.read_text(encoding="utf-8"))
    records = payload.get("records") or []
    failures = payload.get("failures") or []
    for record in records:
        text = record.get("ocr_text") or record.get("offense_text") or ""
        categories, matched = classify(text)
        record["categories"] = categories
        record["matched_terms"] = matched
        record["offenses"] = extract_offenses(text)

    meta = payload.get("meta") or {}
    write_output(
        out_file,
        records,
        failures,
        meta.get("engine") or "reclassify",
        int(meta.get("total_candidates_with_criminal_pdf") or len(records) + len(failures)),
        int(meta.get("selected_candidates") or len(records) + len(failures)),
        partial=bool(failures or meta.get("partial")),
    )


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
        "offenses": extract_offenses(text),
        "offense_text": offense_section(text),
        "ocr_text": text,
        "nec_detail_url": detail.get("nec_detail_url") or "",
        "pdf_count": len(pdf_urls),
        "pdf_urls": pdf_urls,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int, default=0, help="처리할 후보 수 제한")
    parser.add_argument("--huboid", help="특정 후보만 처리")
    parser.add_argument("--cache-dir", type=Path, default=CACHE_DIR)
    parser.add_argument("--out", type=Path, default=OUT_FILE)
    parser.add_argument("--checkpoint-every", type=int, default=25, help="N명 처리마다 산출물 중간 저장")
    parser.add_argument("--progress-every", type=int, default=1, help="N명마다 진행 로그 출력")
    parser.add_argument("--no-resume", action="store_true", help="기존 산출물을 이어받지 않고 다시 처리")
    parser.add_argument("--reclassify-existing", action="store_true", help="기존 OCR 텍스트를 현재 분류 사전으로 다시 분류")
    args = parser.parse_args()

    if args.reclassify_existing:
        reclassify_existing(args.out)
        try:
            out_label = args.out.resolve().relative_to(ROOT)
        except ValueError:
            out_label = args.out
        print(f"전과 OCR 재분류: {out_label}")
        return

    engine = available_engine()
    if not engine:
        sys.exit("OCR 엔진을 찾지 못했습니다. Windows OCR 또는 tesseract가 필요합니다.")

    args.cache_dir.mkdir(parents=True, exist_ok=True)
    helper_script = args.cache_dir / "win_ocr_image.ps1"
    if engine == "windows":
        helper_script.write_text(WIN_OCR_SCRIPT, encoding="utf-8")

    all_details = [
        d for d in load_details()
        if d.get("scan_files", {}).get("criminal")
        and (not args.huboid or str(d.get("huboid")) == str(args.huboid))
    ]
    details = all_details
    if args.limit:
        details = details[:args.limit]

    candidate_map = load_candidate_map()
    resume_records = {} if args.no_resume else load_resume_records(args.out)
    record_map = {}
    failures = []
    for idx, detail in enumerate(details, start=1):
        report_progress = args.progress_every <= 1 or idx % args.progress_every == 0 or idx == len(details)
        huboid = str(detail.get("huboid") or "")
        pdf_urls = criminal_pdf_urls(detail)
        resume_record = resume_records.get(huboid)
        if resume_record and resume_record.get("pdf_urls") == pdf_urls:
            record_map[huboid] = resume_record
            if report_progress:
                print(f"[{idx}/{len(details)}] {huboid} 기존 OCR 재사용", flush=True)
            continue

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
            record_map[huboid] = candidate_row(detail, candidate_map, text, categories, matched, pdf_urls)
            if report_progress:
                print(f"[{idx}/{len(details)}] {huboid} {categories or ['미분류']}", flush=True)
        except Exception as exc:  # noqa: BLE001
            if is_fatal_network_error(exc):
                raise RuntimeError("네트워크 권한 오류로 PDF를 받을 수 없습니다. 권한을 승인한 뒤 다시 실행하세요.") from exc
            failures.append({"huboid": huboid, "error": str(exc)})
            print(f"[{idx}/{len(details)}] {huboid} 실패: {exc}", file=sys.stderr, flush=True)

        if args.checkpoint_every > 0 and idx % args.checkpoint_every == 0:
            records = ordered_records(record_map, details)
            write_output(
                args.out,
                records,
                failures,
                engine,
                len(all_details),
                len(details),
                partial=True,
            )

    records = ordered_records(record_map, details)
    write_output(
        args.out,
        records,
        failures,
        engine,
        len(all_details),
        len(details),
        partial=bool(args.limit or args.huboid or len(records) < len(details)),
    )
    try:
        out_label = args.out.resolve().relative_to(ROOT)
    except ValueError:
        out_label = args.out
    print(f"전과 OCR 색인: {len(records)}명 -> {out_label}")


if __name__ == "__main__":
    main()
