#!/usr/bin/env python3
"""
선관위 info.nec.go.kr 사전투표진행상황(VCAP01) 스크래퍼.

배경:
    선관위 OpenAPI(ErVotingSttusInfoInqireService)는 사전투표율을 사후에만
    제공한다. 실시간 시간대별 누적은 info.nec.go.kr의 JSF 페이지가 유일.
    그 페이지의 form POST endpoint를 흉내내 시도별 누적률을 받아온다.

저장 구조 (fetch_early_voting.py와 동일):
    data/early_voting/<sgId>/
      ├── snapshots/snapshot_YYYYMMDD_HHMM.json   # 수집 시점별 raw
      ├── timeseries.json                         # 프론트용 시계열 (시도)
      └── latest.json                             # 최신 1건 (띠배너용)

전략:
    1) 1일차(prevoteDate1=5/29), 2일차(prevoteDate2=5/30)에 대해
       가장 최근 시간 코드(예: 08, 09, 10…)부터 거꾸로 시도.
    2) 0건이면 한 시간 전으로. 둘 다 0이면 해당 일차 건너뜀.
    3) 양일 누적(voted_d1 + voted_d2)을 timeseries에 한 줄로 append.

cron(*/30) 마다 호출. NEC가 정시 발표(매 시각 00분 무렵)이라
30분 간격이면 매 정시 한 번씩 새 데이터를 확보.
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

URL = "https://info.nec.go.kr/electioninfo/electionInfo_report.xhtml"
ELECTION_ID = "0020260603"
TARGET_SG_ID = "20260603"
KST = timezone(timedelta(hours=9))

ROOT_DIR = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT_DIR / "data" / "early_voting" / TARGET_SG_ID
SNAPSHOT_DIR = OUT_DIR / "snapshots"
TIMESERIES_PATH = OUT_DIR / "timeseries.json"
LATEST_PATH = OUT_DIR / "latest.json"

# NEC의 시도 명칭을 9회 표준 명칭으로 통일 (이미 같지만 안전망).
SIDO_ALIAS = {
    "강원도": "강원특별자치도",
    "전라북도": "전북특별자치도",
}

# 시간 코드는 보통 "07","08",…,"18" (1일차 19시 마감 표시는 19) 또는
# 2일차도 동일 패턴. 18시 이후엔 마감 표기.
HOUR_CODES = ["18", "17", "16", "15", "14", "13", "12", "11", "10", "09", "08", "07"]


def now_kst() -> datetime:
    return datetime.now(KST)


def build_body(date_code: str, time_code: str) -> dict:
    return {
        "electionId":    ELECTION_ID,
        "requestURI":    f"/electioninfo/{ELECTION_ID}/vc/vcap01.jsp",
        "topMenuId":     "VC",
        "secondMenuId":  "VCAP01",
        "menuId":        "VCAP01",
        "statementId":   "VCAP01_#1",  # cityCode=0(전국)
        "prevoteDate1":  "20260529",
        "prevoteDate2":  "20260530",
        "cityCode":      "0",
        "dateCode":      date_code,
        "timeCode":      time_code,
    }


HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0",
    "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
    "Referer": f"https://info.nec.go.kr/main/showDocument.xhtml?electionId={ELECTION_ID}&topMenuId=VC&secondMenuId=VCAP01",
}

# 시도 row 추출 정규식: <td class="firstTh alignL">시도명</td> (3 alignR td) 형태
ROW_RE = re.compile(
    r'<td[^>]*class="firstTh alignL"[^>]*>\s*([^<]+?)\s*</td>'
    r'\s*<td[^>]*alignR[^>]*>\s*([\d,]+)\s*</td>'
    r'\s*<td[^>]*alignR[^>]*>\s*([\d,]+)\s*</td>'
    r'\s*<td[^>]*alignR[^>]*>\s*([\d.\-]+)\s*</td>',
    re.DOTALL,
)


def parse_table(html: str) -> tuple[dict | None, list[dict]]:
    """HTML 파싱 → (national, by_sido). 데이터 없으면 (None, [])."""
    rows = ROW_RE.findall(html)
    if not rows:
        return None, []
    national = None
    by_sido = []
    for name, voters, voted, turnout in rows:
        name = name.strip()
        try:
            v = int(voters.replace(",", ""))
            t = int(voted.replace(",", ""))
            r = float(turnout)
        except ValueError:
            continue
        rec = {"voters": v, "voted": t, "turnout": round(r, 2)}
        if name == "합계":
            national = rec
        else:
            sd = SIDO_ALIAS.get(name, name)
            rec_sd = {"sdName": sd, **rec}
            by_sido.append(rec_sd)
    return national, by_sido


def fetch_one(date_code: str, time_code: str) -> tuple[dict | None, list[dict]]:
    """주어진 일차·시각으로 한 번 POST. 결과 없으면 (None, [])."""
    try:
        r = requests.post(URL, data=build_body(date_code, time_code),
                          headers=HEADERS, timeout=20)
        r.raise_for_status()
    except requests.RequestException as e:
        print(f"      요청 실패 (date={date_code}, time={time_code}): {e}", file=sys.stderr)
        return None, []
    national, by_sido = parse_table(r.text)
    return national, by_sido


def fetch_latest_for_day(date_code: str) -> tuple[dict | None, list[dict], str | None]:
    """해당 일차의 가장 최근 시간 데이터를 찾아 반환. (national, by_sido, time_code).

    NEC 페이지는 미래 시각을 받아도 row 자체는 반환하되 voters/voted 모두 0인
    스켈레톤을 준다. voted>0 일 때만 채택 — 그러지 않으면 한 시간 전으로.
    """
    for hc in HOUR_CODES:
        national, by_sido = fetch_one(date_code, hc)
        if national and by_sido and national.get("voted", 0) > 0:
            return national, by_sido, hc
    return None, [], None


def fetch_all_hours_for_day(date_code: str) -> dict[int, tuple[dict, list[dict]]]:
    """해당 일차 07~18시 전 시각을 훑어 데이터 있는 시각만 수집.

    반환: {hour_int: (national, by_sido)} — voted>0 인 시각만.
    한 번 실행으로 그날 모든 시각을 확보 → 루프/cron이 몇 번 누락돼도
    다음 1회 실행이 공백을 자동으로 메운다(자가 치유).
    """
    out: dict[int, tuple[dict, list[dict]]] = {}
    for h in range(7, 19):
        national, by_sido = fetch_one(date_code, f"{h:02d}")
        if national and by_sido and national.get("voted", 0) > 0:
            out[h] = (national, by_sido)
    return out


def merge_days(d1: tuple, d2: tuple) -> tuple[dict | None, list[dict]]:
    """1일차·2일차 결과를 시도 단위로 합산. d2가 없으면 d1만."""
    nat1, by1 = d1[0], d1[1]
    nat2, by2 = d2[0], d2[1]

    if not nat1 and not nat2:
        return None, []

    # 시도별 voters는 같으므로 한쪽 최대, voted는 합산
    sido_index = {}
    for s in by1:
        sido_index[s["sdName"]] = {
            "voters": s["voters"], "voted_d1": s["voted"], "voted_d2": 0,
        }
    for s in by2:
        cur = sido_index.setdefault(s["sdName"], {"voters": s["voters"], "voted_d1": 0, "voted_d2": 0})
        cur["voters"] = max(cur["voters"], s["voters"])
        cur["voted_d2"] = s["voted"]

    by_sido = []
    for sd, c in sido_index.items():
        voted = c["voted_d1"] + c["voted_d2"]
        voters = c["voters"]
        turnout = round(voted / voters * 100.0, 2) if voters else 0.0
        by_sido.append({"sdName": sd, "voters": voters, "voted": voted, "turnout": turnout})

    total_voted = sum(s["voted"] for s in by_sido)
    total_voters = sum(s["voters"] for s in by_sido)
    national = {
        "voters": total_voters,
        "voted": total_voted,
        "turnout": round(total_voted / total_voters * 100.0, 2) if total_voters else 0.0,
    }
    return national, by_sido


def load_timeseries() -> dict:
    if TIMESERIES_PATH.exists():
        try:
            return json.loads(TIMESERIES_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"sgId": TARGET_SG_ID, "snapshots": []}


def append_timeseries(
    ts: dict, at: datetime, by_sido: list[dict], national: dict,
    day1_time_code: str | None, day2_time_code: str | None,
) -> bool:
    # 1차 dedup: 같은 (day1,day2) 시각코드 조합이 이미 있으면 skip.
    #   한 시각당 1엔트리만 유지 → 수집 시점(at)이 달라도 중복 누적 방지.
    code_key = (day1_time_code, day2_time_code)
    if code_key != (None, None):
        for s in ts.get("snapshots", []):
            if (s.get("day1_time_code"), s.get("day2_time_code")) == code_key:
                return False
    # 2차 dedup: 같은 분(分)에 이미 적재된 게 있으면 skip (안전망).
    at_key = at.strftime("%Y-%m-%dT%H:%M")
    for s in ts.get("snapshots", []):
        if s.get("at", "").startswith(at_key):
            return False
    ts.setdefault("snapshots", []).append({
        "at": at.isoformat(timespec="seconds"),
        "day1_time_code": day1_time_code,
        "day2_time_code": day2_time_code,
        "by_sido": by_sido,
        "national": national,
    })
    ts["snapshots"].sort(key=lambda s: s["at"])
    ts["updated_at"] = at.isoformat(timespec="seconds")
    return True


def main() -> None:
    started_at = now_kst()
    print("=" * 60)
    print(f"사전투표율 스크래핑 — info.nec.go.kr VCAP01 (전 시각 수집)")
    print(f"  실행 시각 (KST): {started_at.isoformat(timespec='seconds')}")
    print("=" * 60)

    print("[1일차 5/29] 07~18시 전 시각 수집…")
    day1 = fetch_all_hours_for_day("1")
    print(f"  → 확보 시각: {sorted(day1)}" if day1 else "  → 데이터 없음")

    print("[2일차 5/30] 07~18시 전 시각 수집…")
    day2 = fetch_all_hours_for_day("2")
    print(f"  → 확보 시각: {sorted(day2)}" if day2 else "  → 데이터 없음")

    if not day1 and not day2:
        print()
        print("=" * 60)
        print("양일 모두 데이터 없음 → 저장 생략.")
        print("=" * 60)
        return

    ts = load_timeseries()
    added = 0

    # 1일차 엔트리: 1일차 단독 누적
    for h in sorted(day1):
        nat, by = day1[h]
        at = datetime(2026, 5, 29, h, 0, 0, tzinfo=KST)
        if append_timeseries(ts, at, by, nat, f"{h:02d}", None):
            added += 1

    # 1일차 최종(가용 최대 시각) — 2일차 양일누적 계산용 기준
    day1_final = day1[max(day1)] if day1 else None

    # 2일차 엔트리: 양일 누적 = 1일차 최종 + 2일차 시각
    for h in sorted(day2):
        nat2, by2 = day2[h]
        if day1_final:
            nat_m, by_m = merge_days((day1_final[0], day1_final[1]), (nat2, by2))
        else:
            nat_m, by_m = nat2, by2
        at = datetime(2026, 5, 30, h, 0, 0, tzinfo=KST)
        if append_timeseries(ts, at, by_m, nat_m, None, f"{h:02d}"):
            added += 1

    # 최신 상태 결정 (2일차가 있으면 양일 누적, 없으면 1일차 최신)
    if day2:
        hmax2 = max(day2)
        nat2, by2 = day2[hmax2]
        if day1_final:
            latest_nat, latest_by = merge_days((day1_final[0], day1_final[1]), (nat2, by2))
        else:
            latest_nat, latest_by = nat2, by2
        latest_d1_code = f"{max(day1):02d}" if day1 else None
        latest_d2_code = f"{hmax2:02d}"
    else:
        hmax1 = max(day1)
        latest_nat, latest_by = day1[hmax1]
        latest_d1_code, latest_d2_code = f"{hmax1:02d}", None

    latest = {
        "sgId": TARGET_SG_ID,
        "fetched_at": started_at.isoformat(timespec="seconds"),
        "source": "info.nec.go.kr/VCAP01 (scrape)",
        "day1_time_code": latest_d1_code,
        "day2_time_code": latest_d2_code,
        "by_sido": sorted(latest_by, key=lambda s: s["sdName"]),
        "national": latest_nat,
    }

    # idempotent: 새 데이터(새 시각)나 수치 변동이 없으면 파일을 건드리지 않는다.
    #   → 작업 스케줄러/cron이 자주 돌아도 노이즈 커밋이 생기지 않음(fetched_at만 바뀌는 쓰기 방지).
    def _payload(d):  # 비교용 — 수집 시각(fetched_at)은 제외
        return {k: d[k] for k in d if k != "fetched_at"}
    prev_latest = None
    if LATEST_PATH.exists():
        try:
            prev_latest = json.loads(LATEST_PATH.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            prev_latest = None
    data_changed = (prev_latest is None) or (_payload(prev_latest) != _payload(latest))

    if added > 0:
        ts["updated_at"] = started_at.isoformat(timespec="seconds")
        TIMESERIES_PATH.write_text(json.dumps(ts, ensure_ascii=False, indent=2), encoding="utf-8")
        SNAPSHOT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = started_at.strftime("%Y%m%d_%H%M")
        snapshot = {
            "sgId": TARGET_SG_ID,
            "fetched_at": started_at.isoformat(timespec="seconds"),
            "source": "info.nec.go.kr/VCAP01 (scrape)",
            "day1_time_code": latest_d1_code,
            "day2_time_code": latest_d2_code,
            "national": latest_nat,
            "by_sido": latest_by,
        }
        (SNAPSHOT_DIR / f"snapshot_{stamp}.json").write_text(
            json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")

    if data_changed:
        LATEST_PATH.write_text(json.dumps(latest, ensure_ascii=False, indent=2), encoding="utf-8")

    cur_label = (f"2일차 {latest_d2_code}시" if day2 else f"1일차 {latest_d1_code}시")
    print()
    print(f"최신: {cur_label} · 전국 {latest_nat['turnout']}% ({latest_nat['voted']:,}/{latest_nat['voters']:,})")
    print("=" * 60)
    if added > 0:
        print(f"  - timeseries 신규 추가: {added}건 (총 {len(ts['snapshots'])}건) → 파일 갱신")
    elif data_changed:
        print("  - 새 시각 없음 · 수치만 변동 → latest.json만 갱신")
    else:
        print("  - 변동 없음 → 파일 미갱신 (커밋 noise 없음)")
    print("=" * 60)


if __name__ == "__main__":
    main()
