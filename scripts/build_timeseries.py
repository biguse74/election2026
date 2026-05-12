#!/usr/bin/env python3
"""
모든 일자별 스냅샷을 훑어 시계열 데이터셋을 만든다.

산출물: data/timeseries.json
형식:
{
  "generated_at": "...",
  "series": [
    {"date": "20260506", "source": "preliminary", "total": 9780,
     "by_party": {"더불어민주당": 3200, ...},
     "by_section": {"3": 100, "4": 1300, ...}},
    ...
  ]
}

워크플로우에서 매 fetch 후 호출.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KST = timezone(timedelta(hours=9))
OUT = ROOT / "data" / "timeseries.json"


def main() -> None:
    series = []
    sources = [
        ("preliminary", "data/preliminary/20260603"),
        ("candidates", "data/candidates/20260603"),
    ]
    for source, folder in sources:
        for path in sorted((ROOT / folder).glob("snapshot_*.json")) if (ROOT / folder).exists() else []:
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
            except Exception:
                continue
            cs = data.get("candidates", [])
            date_str = path.stem.split("_")[-1]
            party_count = {}
            sg_count = {}
            for c in cs:
                j = c.get("jdName") or "무소속"
                party_count[j] = party_count.get(j, 0) + 1
                sg = str(c.get("sgTypecode", ""))
                sg_count[sg] = sg_count.get(sg, 0) + 1
            series.append({
                "date": date_str,
                "source": source,
                "total": len(cs),
                "by_party": party_count,
                "by_section": sg_count,
            })

    # 날짜·소스 정렬
    series.sort(key=lambda r: (r["date"], r["source"]))

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps(
            {"generated_at": datetime.now(KST).isoformat(timespec="seconds"), "series": series},
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print(f"timeseries: {len(series)}일치 (preliminary+candidates 통합)")


if __name__ == "__main__":
    main()
