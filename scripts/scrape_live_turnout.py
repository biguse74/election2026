# -*- coding: utf-8 -*-
"""본투표 당일 투표율 스크래퍼 — info.nec.go.kr VCVP01 페이지.
OpenAPI(getVoteSttusInfoInqire)가 6/3 당일 INFO-03(데이터없음)을 주므로,
NEC 웹 리포트(electionInfo_report.xhtml, statementId=VCVP01_#2_SUM)를 직접 긁는다.
표 컬럼: 시도명 | 선거인[당일·사전신고·계] | 투표자[당일·사전접수·계] | 투표율%
출력: data/live_counting/current.json 의 turnout 블록 갱신(races는 보존).
"""
import json, os, re, sys
from datetime import datetime, timezone, timedelta
import requests

RID = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EID = "0020260603"
URL = "https://info.nec.go.kr/electioninfo/electionInfo_report.xhtml"
KST = timezone(timedelta(hours=9))
OUT = os.path.join(RID, "data", "live_counting", "current.json")
HEADERS = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0",
           "Accept-Language": "ko-KR,ko;q=0.9",
           "Referer": f"https://info.nec.go.kr/main/showDocument.xhtml?electionId={EID}&topMenuId=VC&secondMenuId=VCVP01"}
SIDO_FULL = {"서울":"서울특별시","부산":"부산광역시","대구":"대구광역시","인천":"인천광역시","광주":"광주광역시",
    "대전":"대전광역시","울산":"울산광역시","세종":"세종특별자치시","경기":"경기도","강원":"강원특별자치도",
    "충북":"충청북도","충남":"충청남도","전북":"전북특별자치도","전남":"전라남도","경북":"경상북도",
    "경남":"경상남도","제주":"제주특별자치도"}
SIDO_SET = set(SIDO_FULL.values())  # 풀네임 17개

def num(s):
    s = re.sub(r"[^\d.]", "", s or "")
    try: return int(float(s)) if s and "." not in s else (float(s) if s else None)
    except: return None

def fetch(time_code="30"):
    body = {"electionId": EID, "requestURI": f"/electioninfo/{EID}/vc/vcvp01.jsp",
            "topMenuId": "VC", "secondMenuId": "VCVP01", "menuId": "VCVP01",
            "statementId": "VCVP01_#2_SUM", "cityCode": "0",
            "sggTime": f"{time_code}시", "timeCode": time_code}
    r = requests.post(URL, data=body, headers=HEADERS, timeout=25)
    r.raise_for_status()
    return r.text

def parse(html):
    national, by_sido = None, []
    for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html, re.S):
        cells = [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
        if len(cells) != 8:
            continue
        name = cells[0]
        if name not in SIDO_SET and name not in SIDO_FULL and name not in ("합계", "계", "전국"):
            continue
        rate = num(cells[7])
        entry = {
            "sd_name": "전국" if name in ("합계","계","전국") else SIDO_FULL.get(name, name),
            "day_eligible_voters": num(cells[1]),
            "early_eligible_voters": num(cells[2]),
            "eligible_voters": num(cells[3]),
            "day_voters_so_far": num(cells[4]),
            "early_voters_so_far": num(cells[5]),
            "voters_so_far": num(cells[6]),
            "turnout_pct": rate,
        }
        if entry["sd_name"] == "전국":
            national = entry
        else:
            by_sido.append(entry)
    return national, by_sido

def main():
    html = fetch("30")
    national, by_sido = parse(html)
    if not national and not by_sido:
        print("투표율 데이터 없음(아직 미공표) — current.json 미변경", file=sys.stderr)
        return 0
    now = datetime.now(KST)
    turnout = {"national": national, "by_sido": by_sido,
               "source": "info.nec.go.kr VCVP01 (웹 리포트)", "scraped_at": now.isoformat()}
    # 기존 current.json의 races 보존
    cur = {}
    if os.path.exists(OUT):
        try: cur = json.load(open(OUT, encoding="utf-8"))
        except: cur = {}
    cur.update({"sgId": "20260603", "polled_at": now.isoformat(),
                "source": "info.nec.go.kr", "phase": "voting",
                "turnout": turnout})
    cur.setdefault("races", [])
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    json.dump(cur, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    nt = national or {}
    print(f"투표율 갱신: 전국 {nt.get('turnout_pct')}% (투표 {nt.get('voters_so_far'):,} / 선거인 {nt.get('eligible_voters'):,}) · 시도 {len(by_sido)}곳 · {now.strftime('%H:%M')}")
    return 0

if __name__ == "__main__":
    sys.exit(main())
