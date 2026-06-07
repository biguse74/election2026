# -*- coding: utf-8 -*-
"""재산신고서에서 인물별 '주식 평가액(천원)'을 좌표 OCR로 자동 추출.

재산신고서 표는 [구분 | 관계 | 권리명세 | 가액(천원) | 비고]. 가액 칸은 우측에 정렬.
유가증권/주식 행(권리명세에 '주식·증권·상장·비상장')의 가액을 합산해 인물 주식 평가액으로.
종목별 수량 OCR 오류와 무관(가액은 별도 칸) → 부(富) 순위는 이 값으로.

PoC: python scripts/extract_asset_value.py --names 이경철,정창수 --limit 10
"""
import argparse
import glob
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import fitz  # PyMuPDF

ROOT = Path(__file__).resolve().parent.parent
SLIM = ROOT / "stocks" / "stock_holdings.json"
CACHE = ROOT / "data" / ".asset_value_cache"
CACHE.mkdir(parents=True, exist_ok=True)

WIN_OCR_COORD = r"""
Add-Type -AssemblyName System.Runtime.WindowsRuntime
[Windows.Storage.StorageFile, Windows.Storage, ContentType=WindowsRuntime] | Out-Null
[Windows.Storage.FileAccessMode, Windows.Storage, ContentType=WindowsRuntime] | Out-Null
[Windows.Storage.Streams.IRandomAccessStream, Windows.Storage.Streams, ContentType=WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics.Imaging, ContentType=WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics.Imaging, ContentType=WindowsRuntime] | Out-Null
[Windows.Globalization.Language, Windows.Globalization, ContentType=WindowsRuntime] | Out-Null
[Windows.Media.Ocr.OcrEngine, Windows.Media.Ocr, ContentType=WindowsRuntime] | Out-Null
$g=([System.WindowsRuntimeSystemExtensions].GetMethods()|?{$_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1'})[0]
function Await($op,[Type]$t){$at=$g.MakeGenericMethod($t);$k=$at.Invoke($null,@($op));$k.Wait()|Out-Null;$k.Result}
$eng=[Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new('ko'))
foreach($p in $args){
  try{
    $path=(Resolve-Path $p).Path
    $file=Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($path)) ([Windows.Storage.StorageFile])
    $stream=Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
    $dec=Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
    $bmp=Await ($dec.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
    $res=Await ($eng.RecognizeAsync($bmp)) ([Windows.Media.Ocr.OcrResult])
    "##FILE##$p"
    foreach($l in $res.Lines){foreach($w in $l.Words){$r=$w.BoundingRect; "$($w.Text)`t$([int]$r.X)`t$([int]$r.Y)`t$([int]$r.Width)"}}
  }catch{ "##FILE##$p" }
}
"""
_HELPER = CACHE / "coord_ocr.ps1"
if not _HELPER.exists():
    _HELPER.write_text(WIN_OCR_COORD, encoding="utf-8")

# '증권'(증권사명·예금행 오매칭) 제외. 권리유형만: 주식·출자·펀드·채권 등.
STOCK_KW = re.compile(r"주식|상장|비상장|출자지분|출자좌|수익증권|펀드|회사채|국공채|코스닥|코스피")
NUM = re.compile(r"^\d{1,3}(?:,\d{3})+$|^\d{4,}$")  # 콤마형 또는 4자리+ (천원 가액)

DPI = 200  # 렌더 해상도(2차 검수에서 다른 값으로 재추출해 1차와 대조)


def ocr_coords_multi(png_paths):
    """여러 PNG를 한 PowerShell 호출로 OCR(프로세스 오버헤드 절감). {png: [words]}."""
    if not png_paths:
        return {}
    out = subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
                          "-File", str(_HELPER)] + [str(p) for p in png_paths],
                         capture_output=True, text=True, encoding="utf-8")
    res, cur = {}, None
    for line in (out.stdout or "").splitlines():
        if line.startswith("##FILE##"):
            cur = line[len("##FILE##"):]
            res[cur] = []
            continue
        parts = line.split("\t")
        if cur is not None and len(parts) == 4:
            try:
                res[cur].append((parts[0], int(parts[1]), int(parts[2]), int(parts[3])))
            except ValueError:
                pass
    return res


def words_asset_value(words):
    """한 페이지 단어좌표 → 주식 행 가액 합 + hit."""
    if not words:
        return 0, []
    W = max((x + w for _, x, _, w in words), default=1)
    val_thresh = W * 0.72
    stock_ys = [y for t, x, y, w in words if x < W * 0.6 and STOCK_KW.search(t)]
    if not stock_ys:
        return 0, []
    total, hits = 0, []
    for t, x, y, w in words:
        if x < val_thresh:
            continue
        num = t.replace(",", "")
        if not (NUM.match(t) and num.isdigit()):
            continue
        v = int(num)
        if v < 100:
            continue
        if min(abs(y - sy) for sy in stock_ys) <= 22:
            total += v
            hits.append((t, x, y))
    return total, hits


def person_value(huboid, name):
    folder = next(iter(glob.glob(str(ROOT / f"data/disclosure_archive/{huboid}_*/재산"))), None)
    if not folder:
        return None, []
    # 인물 전체 PDF → 페이지별 PNG → 한 번에 OCR
    pngs, tmpdir = [], tempfile.mkdtemp(dir=str(CACHE))
    for pi, pdf in enumerate(sorted(glob.glob(os.path.join(folder, "*.PDF")))):
        doc = fitz.open(pdf)
        for pno in range(len(doc)):
            png = os.path.join(tmpdir, f"{pi}_{pno}.png")
            doc[pno].get_pixmap(dpi=DPI).save(png)
            pngs.append(png)
    coords = ocr_coords_multi(pngs)
    total, hits = 0, []
    for png in pngs:
        v, h = words_asset_value(coords.get(png, []))
        total += v
        hits += h
    for png in pngs:
        try:
            os.remove(png)
        except OSError:
            pass
    try:
        os.rmdir(tmpdir)
    except OSError:
        pass
    return total, hits


OUT = ROOT / "data" / "asset_value.json"


def main():
    global DPI, OUT
    ap = argparse.ArgumentParser()
    ap.add_argument("--names", default="")
    ap.add_argument("--limit", type=int, default=10)
    ap.add_argument("--all", action="store_true", help="전체 보유자 풀런(결과 저장·재개)")
    ap.add_argument("--dpi", type=int, default=200, help="렌더 해상도(2차 검수: 다른 값으로 대조)")
    ap.add_argument("--out", default=str(OUT), help="결과 저장 경로(2차는 별도 파일)")
    ap.add_argument("--huboids-file", default="", help="이 파일(줄당 huboid)의 인물만 처리(저장·재개)")
    args = ap.parse_args()
    DPI = args.dpi
    OUT = Path(args.out)
    d = json.loads(SLIM.read_text(encoding="utf-8"))
    people = [p for p in d["people"] if p["holdings"]]

    if args.huboids_file:
        want = {ln.strip() for ln in Path(args.huboids_file).read_text(encoding="utf-8").splitlines() if ln.strip()}
        people = [p for p in people if str(p["huboid"]) in want]
        args.all = True   # 저장·재개 경로 사용

    if args.names:
        want = set(args.names.split(","))
        for p in [p for p in people if p["name"] in want]:
            v, hits = person_value(str(p["huboid"]), p["name"])
            print(f"{p['name']} · 종목{len(p['holdings'])} · {v:,}천원 (≈{(v or 0)/100000:.2f}억) · 행{len(hits)}", flush=True)
        return

    if not args.all:
        people = sorted(people, key=lambda p: -len(p["holdings"]))[:args.limit]

    done = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    todo = [p for p in people if str(p["huboid"]) not in done]
    print(f"평가액 풀런: 대상 {len(people)} · 기처리 {len(done)} · 남은 {len(todo)}", flush=True)
    for i, p in enumerate(todo, 1):
        hb = str(p["huboid"])
        try:
            v, hits = person_value(hb, p["name"])
        except Exception as e:
            v, hits = None, []
            print(f"  ! {p['name']} 오류 {e}", flush=True)
        done[hb] = {"name": p["name"], "office": p.get("office"), "sido": p.get("sido"),
                    "party": p.get("party"), "value_thousand": v, "rows": len(hits),
                    "n_stocks": len(p["holdings"])}
        if i % 25 == 0:
            OUT.write_text(json.dumps(done, ensure_ascii=False), encoding="utf-8")
            print(f"  ...{i}/{len(todo)} 저장(누적 {len(done)})", flush=True)
    OUT.write_text(json.dumps(done, ensure_ascii=False), encoding="utf-8")
    nz = sum(1 for v in done.values() if v.get("value_thousand"))
    print(f"DONE 평가액 {len(done)}명 · 추출성공 {nz} → {OUT}", flush=True)


if __name__ == "__main__":
    main()
