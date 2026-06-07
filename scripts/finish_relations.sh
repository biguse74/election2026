#!/usr/bin/env bash
cd "$(dirname "$0")/.."
LIST=data/.dup_huboids.txt
OUT=data/stock_relations.json
rem() { python -c "import json,os;w=set(open('$LIST').read().split());d=set(json.load(open('$OUT'))) if os.path.exists('$OUT') else set();print(len(w-d))"; }
for i in $(seq 1 40); do
  R=$(rem); echo "[loop $i] 남은 $R명"; [ "$R" = "0" ] && break
  python scripts/extract_relation.py --huboids-file "$LIST" || true
  sleep 2
done
echo "RELDONE 관계 추출 완료"
