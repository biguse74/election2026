#!/usr/bin/env python3
"""후보자 카드 데이터 생성 — 당선 결과 페이지의 이름 클릭 → 후보 프로필 모달용.

등록 스냅샷(data/candidates/20260603/snapshot_*.json)에서 공개 선거정보만 추려
candidate_photos.json과 동일한 키로 data/candidate_cards.json을 만든다.
  by_full: 'sgTypecode|sdName|sggName|name' → card
  by_sd  : 'sgTypecode|sdName|name'         → card
개인정보(주소·생년월일 등)는 제외하고, 공개된 정당·나이·직업·학력·경력만 담는다.
"""
from __future__ import annotations
import json, glob
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SG_ID = "20260603"
OFFICES = {"2", "3", "4", "11"}  # 결과 페이지 표시 대상: 국회의원·시도지사·기초단체장·교육감
# (시도의원5·기초의원6은 수천 명이라 카드 파일에서 제외 — 필요 시 추가)
LABEL = {"2": "국회의원", "3": "시도지사", "4": "기초단체장", "5": "시도의원", "6": "기초의원", "11": "교육감"}


def main() -> int:
    fs = sorted((ROOT / "data" / "candidates" / SG_ID).glob("snapshot_*.json"))
    if not fs:
        print("등록 스냅샷 없음")
        return 1
    data = json.loads(fs[-1].read_text(encoding="utf-8"))
    cands = data if isinstance(data, list) else data.get("candidates", [])
    by_full, by_sd = {}, {}
    for c in cands:
        t = str(c.get("sgTypecode") or "")
        if t not in OFFICES:
            continue
        sd, sgg, nm = c.get("sdName") or "", c.get("sggName") or "", (c.get("name") or "").strip()
        if not (sd and nm):
            continue
        card = {
            "name": nm,
            "party": c.get("jdName") or "무소속",
            "office": LABEL.get(t, t),
            "district": sgg if sgg and sgg != sd else "",
            "age": c.get("age") or "",
            "gender": c.get("gender") or "",
            "job": c.get("job") or "",
            "edu": c.get("edu") or "",
            "career1": c.get("career1") or "",
            "career2": c.get("career2") or "",
            "huboid": c.get("huboid") or "",
            "status": c.get("status") or "",
        }
        by_full[f"{t}|{sd}|{sgg}|{nm}"] = card
        by_sd.setdefault(f"{t}|{sd}|{nm}", card)

    out = {
        "note": "후보자 카드(공개 선거정보만 — 정당·나이·직업·학력·경력). 주소 등 개인정보 제외.",
        "sgId": SG_ID,
        "source": "중앙선거관리위원회 후보자 등록 정보",
        "by_full": by_full,
        "by_sd": by_sd,
    }
    dest = ROOT / "data" / "candidate_cards.json"
    dest.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"저장: {dest.relative_to(ROOT)}  by_full={len(by_full)}  by_sd={len(by_sd)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
