#!/usr/bin/env python3
"""
어제·오늘 스냅샷을 비교해 변화를 정리한 changelog.json을 만든다.

워크플로우에서 fetch 직후 호출. data/changelog.json 갱신.
프론트엔드는 그 JSON을 읽어 홈에 "오늘의 변경" 박스 노출.

변화 종류:
    new          : 어제 없던 huboid가 오늘 등장
    gone         : 어제 있던 huboid가 오늘 사라짐 (사퇴·등록무효 가능)
    party        : 같은 huboid의 jdName 변경 (정당 이동)
    status       : 같은 huboid의 status 변경 (등록·사퇴·무효 등)

source(preliminary/candidates) 같은 단계끼리만 비교. 5/14 전환일은 빈
변화로 처리.
"""

from __future__ import annotations

import glob
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
KST = timezone(timedelta(hours=9))
OUT = ROOT / "data" / "changelog.json"


def latest_two(folder: str) -> tuple[Path | None, Path | None]:
    files = sorted((ROOT / folder).glob("snapshot_*.json")) if (ROOT / folder).exists() else []
    if len(files) < 2:
        return (files[-1] if files else None, None)
    return files[-1], files[-2]


def diff_snapshots(today_path: Path, yest_path: Path | None, source: str) -> dict:
    today = json.loads(today_path.read_text(encoding="utf-8"))
    today_cands = {c["huboid"]: c for c in today.get("candidates", []) if c.get("huboid")}
    today_date = today_path.stem.split("_")[-1]

    if yest_path is None:
        return {
            "source": source,
            "today_date": today_date,
            "previous_date": None,
            "summary": {"new": 0, "gone": 0, "party": 0, "status": 0},
            "samples": {"new": [], "gone": [], "party": [], "status": []},
        }

    yest = json.loads(yest_path.read_text(encoding="utf-8"))
    yest_cands = {c["huboid"]: c for c in yest.get("candidates", []) if c.get("huboid")}
    yest_date = yest_path.stem.split("_")[-1]

    def base(c: dict) -> dict:
        return {
            "name": c.get("name", ""),
            "jdName": c.get("jdName", ""),
            "sdName": c.get("sdName", ""),
            "sggName": c.get("sggName", ""),
            "sgTypecode": str(c.get("sgTypecode", "")),
        }

    new_ids = sorted(set(today_cands) - set(yest_cands))
    gone_ids = sorted(set(yest_cands) - set(today_cands))

    party_changes = []
    status_changes = []
    for hid in set(today_cands) & set(yest_cands):
        t, y = today_cands[hid], yest_cands[hid]
        if (t.get("jdName") or "") != (y.get("jdName") or ""):
            row = base(t)
            row["jdName_prev"] = y.get("jdName", "")
            party_changes.append(row)
        if (t.get("status") or "") != (y.get("status") or ""):
            row = base(t)
            row["status_prev"] = y.get("status", "")
            row["status_now"] = t.get("status", "")
            status_changes.append(row)

    new_list = [base(today_cands[h]) for h in new_ids]
    gone_list = [base(yest_cands[h]) for h in gone_ids]

    return {
        "source": source,
        "today_date": today_date,
        "previous_date": yest_date,
        "summary": {
            "new": len(new_list),
            "gone": len(gone_list),
            "party": len(party_changes),
            "status": len(status_changes),
        },
        # 화면엔 일부만 노출. 풀 데이터는 추후 변화 페이지에서 사용.
        "samples": {
            "new": new_list[:20],
            "gone": gone_list[:20],
            "party": party_changes[:20],
            "status": status_changes[:20],
        },
        "full": {
            "new": new_list,
            "gone": gone_list,
            "party": party_changes,
            "status": status_changes,
        },
    }


def main() -> None:
    # 후보 등록 시작 이후엔 candidates 우선, 그 전엔 preliminary
    cand_today, cand_yest = latest_two("data/candidates/20260603")
    if cand_today and cand_yest:
        result = diff_snapshots(cand_today, cand_yest, "candidates")
    else:
        prelim_today, prelim_yest = latest_two("data/preliminary/20260603")
        if not prelim_today:
            print("스냅샷이 없음, changelog 생략")
            return
        result = diff_snapshots(prelim_today, prelim_yest, "preliminary")

    result["generated_at"] = datetime.now(KST).isoformat(timespec="seconds")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    s = result["summary"]
    print(
        f"changelog: {result['previous_date']} → {result['today_date']} "
        f"(신규 {s['new']} · 이탈 {s['gone']} · 정당변경 {s['party']} · 상태변경 {s['status']})"
    )


if __name__ == "__main__":
    main()
