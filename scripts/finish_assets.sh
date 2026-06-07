#!/usr/bin/env bash
# 3차 OCR(300dpi) 자동 재시작 → 합의 → 사이트 빌드까지 무인 완주.
cd "$(dirname "$0")/.."
LIST=data/.disagree_huboids.txt
OUT=data/asset_value_300.json
rem() { python -c "import json,os;w=set(open('$LIST').read().split());d=set(json.load(open('$OUT'))) if os.path.exists('$OUT') else set();print(len(w-d))"; }
for i in $(seq 1 60); do
  R=$(rem); echo "[loop $i] 남은 $R명"; [ "$R" = "0" ] && break
  python scripts/extract_asset_value.py --huboids-file "$LIST" --dpi 300 --out "$OUT" || true
  sleep 2
done
echo "=== 3차 OCR 완료 → 합의 계산 ==="
python scripts/consensus_assets.py
echo "=== 사이트 데이터 재빌드 ==="
python scripts/build_stock_watch.py
echo "ALLDONE 합의값 반영 완료(커밋 대기)"
