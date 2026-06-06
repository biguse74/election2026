# -*- coding: utf-8 -*-
"""주식 데이터 전체 자동 재빌드 — 한 번에(원클릭).

순서:
  1) build_stock_slim       raw OCR → 공개 슬림본(garble 원본 복원)
  2) auto_correct_names     KRX 사전 기반 종목명 오타 교정표 재생성(--apply)
  3) consensus_assets       3해상도(150·200·300) 평가액 다수결 합의
  4) build_stock_watch      자동교정+수동교정+합의 평가액 적용 → 사이트 데이터
  5) audit_stocks           평가액 검수 리포트(로컬)

기자가 계속 신경 쓰지 않아도, 이 한 줄이면 최신 보정이 모두 반영된다:
  python scripts/rebuild_stocks_all.py
"""
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STEPS = [
    ("슬림 재생성", ["build_stock_slim.py"]),
    ("종목명 자동교정", ["auto_correct_names.py", "--apply"]),
    ("평가액 3해상도 합의", ["consensus_assets.py"]),
    ("watch 빌드(사이트 데이터)", ["build_stock_watch.py"]),
    ("평가액 검수 리포트", ["audit_stocks.py"]),
]


def main():
    for i, (label, args) in enumerate(STEPS, 1):
        print(f"\n{'='*60}\n[{i}/{len(STEPS)}] {label}\n{'='*60}", flush=True)
        r = subprocess.run([sys.executable, str(ROOT / "scripts" / args[0])] + args[1:])
        if r.returncode != 0:
            print(f"  ! 실패({label}) — 중단", flush=True)
            sys.exit(r.returncode)
    print(f"\n{'='*60}\n전체 재빌드 완료. 사이트 데이터(stocks/stock_holdings.json) 갱신됨.\n"
          f"커밋: git add -A && git commit && git push\n{'='*60}")


if __name__ == "__main__":
    main()
