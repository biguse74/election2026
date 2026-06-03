#!/usr/bin/env python3
"""
선관위 OpenAPI를 호출해 6/3 본투표 당일 투표율과 개표 누계를 모은다.

한 번 실행 = 한 번 수집. cron 또는 GitHub Actions가 5분 간격으로 호출한다고 가정.

호출 두 종 (VoteXmntckInfoInqireService2):
  - getVoteSttusInfoInqire   ← 투표율 (시도별 + 전국 합계, 1회 호출)
  - getXmntckSttusInfoInqire ← 개표 (sg_type × 시도, 51회 호출)

6/3 18시 이전: 투표율만 들어옴, 개표는 ERROR-03.
6/3 18시 이후: 개표가 누적, 투표율은 final 값으로 고정.

산출물:
  data/live_counting/raw/openapi_<YYYYMMDD_HHMMSS>.json    # 두 API 원응답 모두
  data/live_counting/current.json                           # 프론트가 읽는 가공본
  data/live_counting/meta.json                              # 수집 텔레메트리

사용:
  python scripts/fetch_live_counting.py
  python scripts/fetch_live_counting.py --sg-id 20220601    # 8회 지선 데이터로 시뮬레이션
  python scripts/fetch_live_counting.py --skip-counting     # 투표 시간대 (개표 호출 생략)
  python scripts/fetch_live_counting.py --dry-run           # 호출만 하고 저장 생략
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

import requests

BASE_URL = "https://apis.data.go.kr/9760000/VoteXmntckInfoInqireService2"
OP_COUNTING = "getXmntckSttusInfoInqire"
OP_TURNOUT = "getVoteSttusInfoInqire"
API_KEY = os.environ.get("NEC_API_KEY", "").strip()

KST = timezone(timedelta(hours=9))
ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = ROOT / "data" / "live_counting"
RAW_DIR = OUT_DIR / "raw"

SG_LABELS = {
    "2": "국회의원",
    "3": "시도지사",
    "4": "기초단체장",
    "5": "시도의원",
    "6": "기초의원",
    "11": "교육감",
}
# 5(시도의원)·6(기초의원) 포함 — 선거구가 sggName에 들어와 기존 race_key로 유일.
# 호출량↑(17시도×5종류=85콜+페이지네이션) 및 current.json 용량↑ 감수: 워치리스트·검색이 기초의원까지 필요.
DEFAULT_SG_TYPES = ["3", "4", "5", "6", "11"]

# 9회 지선 시도 표준명. 강원·전북·제주는 신명칭.
SIDOS = [
    "서울특별시", "부산광역시", "대구광역시", "인천광역시", "광주광역시",
    "대전광역시", "울산광역시", "세종특별자치시", "경기도", "강원특별자치도",
    "충청북도", "충청남도", "전북특별자치도", "전라남도", "경상북도",
    "경상남도", "제주특별자치도",
]

ELECTION_DAY_KST = datetime(2026, 6, 3, 18, 0, tzinfo=KST)
DEFAULT_SG_ID = "20260603"


class PortalQuotaError(RuntimeError):
    """공공데이터포털 레벨 에러 (한도 초과·미등록 IP 등). 후속 호출 모두 실패하므로 fail-fast."""
    def __init__(self, code: str, msg: str):
        super().__init__(f"PortalError[{code}] {msg}")
        self.code = code
        self.msg = msg


def _pick(d: dict, *keys: str) -> Any:
    for k in keys:
        v = d.get(k)
        if v not in (None, "", "null"):
            return v
    return None


def _to_num(v: Any):
    if v is None:
        return None
    s = str(v).replace(",", "").replace("%", "").strip()
    if not s:
        return None
    try:
        f = float(s)
        return int(f) if f.is_integer() else round(f, 3)
    except ValueError:
        return None


def to_int(v: Any) -> int:
    if v in (None, "", "null"):
        return 0
    try:
        return int(str(v).replace(",", "").strip() or 0)
    except ValueError:
        return 0


# ============ 개표 호출 ============

def call_counting(sg_id: str, sg_type: str, sd_name: str) -> dict:
    """한 (sg_type, sd_name) 묶음 개표 호출. 페이지 다 받아 items 합쳐 반환."""
    items: list[dict] = []
    page = 1
    result_code = "?"
    total_count = 0
    while page <= 50:
        params = {
            "ServiceKey": API_KEY,
            "sgId": sg_id,
            "sgTypecode": sg_type,
            "sdName": sd_name,
            "pageNo": page,
            "numOfRows": 100,    # OpenAPI 가이드(v4.3) 최대값
            "resultType": "json",
        }
        # 시도지사: fetch_past_counting_results.py와 동일 규약 (sggName도 시도명).
        if sg_type == "3":
            params["sggName"] = sd_name

        res = requests.get(f"{BASE_URL}/{OP_COUNTING}", params=params, timeout=30)
        res.raise_for_status()
        payload = res.json()

        # 공공데이터포털 레벨 에러 (22=요청제한 초과, 32=미등록IP 등)
        portal = payload.get("OpenAPI_ServiceResponse", {}).get("cmmMsgHeader") if isinstance(payload, dict) else None
        if portal:
            raise PortalQuotaError(
                code=str(portal.get("returnReasonCode", "?")),
                msg=str(portal.get("returnAuthMsg") or portal.get("errMsg") or "PORTAL_ERROR"),
            )

        header = payload.get("response", {}).get("header", {})
        result_code = header.get("resultCode", "?")
        if result_code in ("INFO-03", "ERROR-03"):
            break
        if result_code not in ("INFO-00", "00"):
            raise RuntimeError(f"API error: {header}")

        body = payload.get("response", {}).get("body", {}) or {}
        wrapper = body.get("items", {})
        chunk = wrapper.get("item", []) if isinstance(wrapper, dict) else wrapper
        if isinstance(chunk, dict):
            chunk = [chunk]
        items.extend(chunk or [])

        total_count = int(body.get("totalCount", 0) or 0)
        if total_count == 0 or len(items) >= total_count:
            break
        page += 1
        time.sleep(0.2)

    return {
        "request": {"sg_id": sg_id, "sg_type": sg_type, "sd_name": sd_name},
        "result_code": result_code,
        "total_count": total_count,
        "items": items,
    }


def extract_candidates(row: dict) -> list[dict]:
    """hbj01~50 / jd01~50 / dugsu01~50 슬롯에서 후보 추출. 득표수 내림차순 정렬."""
    valid_votes = to_int(row.get("yutusu"))
    cands: list[dict] = []
    for i in range(1, 51):
        s = f"{i:02d}"
        name = (row.get(f"hbj{s}") or "").strip()
        party = (row.get(f"jd{s}") or "").strip()
        votes = to_int(row.get(f"dugsu{s}"))
        if not name and not party and votes == 0:
            continue
        share = round(votes / valid_votes * 100, 2) if valid_votes else None
        cands.append({"name": name, "jd_name": party, "votes": votes, "share_pct": share})
    cands.sort(key=lambda c: c["votes"], reverse=True)
    for idx, c in enumerate(cands, 1):
        c["current_rank"] = idx
    return cands


def race_key(row: dict) -> str:
    sg_type = str(row.get("sgTypecode", ""))
    sd = (row.get("sdName") or "").strip()
    sgg = (row.get("sggName") or "").strip()
    return "|".join(p for p in (sg_type, sd, sgg) if p)


def normalize_row(row: dict) -> dict:
    sg_type = str(row.get("sgTypecode", ""))
    candidates = extract_candidates(row)
    eligible = to_int(row.get("sunsu"))
    valid = to_int(row.get("yutusu"))
    invalid = to_int(row.get("mutusu"))
    counted = valid + invalid
    progress = round(counted / eligible * 100, 2) if eligible else None

    rank_diff = None
    if (
        len(candidates) >= 2
        and candidates[0]["share_pct"] is not None
        and candidates[1]["share_pct"] is not None
    ):
        rank_diff = round(candidates[0]["share_pct"] - candidates[1]["share_pct"], 2)

    return {
        "race_key": race_key(row),
        "sg_type_code": sg_type,
        "sg_type_label": SG_LABELS.get(sg_type, sg_type),
        "sd_name": (row.get("sdName") or "").strip(),
        "sgg_name": (row.get("sggName") or "").strip() or None,
        "wiw_name": (row.get("wiwName") or "").strip() or None,
        "eligible_voters": eligible,
        "valid_votes": valid,
        "invalid_votes": invalid,
        "progress_pct": progress,
        "rank1_minus_rank2_pp": rank_diff,
        "candidates": candidates,
    }


# ============ 투표율 호출 ============

def call_turnout(sg_id: str) -> dict:
    """전국 시도별 투표율 1회 호출. 응답이 없거나 실패해도 items=[] 반환.
    포털 레벨 한도/IP 에러는 PortalQuotaError로 즉시 전파해 main에서 fail-fast.
    """
    items: list[dict] = []
    result_code = "?"
    try:
        params = {
            "ServiceKey": API_KEY,
            "sgId": sg_id,
            "sgTypecode": 3,   # 시도지사 단위 = 지방선거 본투표율
            "pageNo": 1,
            "numOfRows": 100,    # OpenAPI 가이드(v4.3) 최대값
            "resultType": "json",
        }
        res = requests.get(f"{BASE_URL}/{OP_TURNOUT}", params=params, timeout=30)
        res.raise_for_status()
        payload = res.json()

        portal = payload.get("OpenAPI_ServiceResponse", {}).get("cmmMsgHeader") if isinstance(payload, dict) else None
        if portal:
            raise PortalQuotaError(
                code=str(portal.get("returnReasonCode", "?")),
                msg=str(portal.get("returnAuthMsg") or portal.get("errMsg") or "PORTAL_ERROR"),
            )

        header = payload.get("response", {}).get("header", {})
        result_code = header.get("resultCode", "?")
        if result_code in ("INFO-00", "00"):
            body = payload.get("response", {}).get("body", {}) or {}
            wrapper = body.get("items", {})
            chunk = wrapper.get("item", []) if isinstance(wrapper, dict) else wrapper
            if isinstance(chunk, dict):
                chunk = [chunk]
            items = chunk or []
    except PortalQuotaError:
        raise
    except Exception as e:
        print(f"  ! 투표율 호출 실패: {e}", file=sys.stderr)
    return {"result_code": result_code, "items": items}


def normalize_turnout(raw: dict) -> dict | None:
    """getVoteSttusInfoInqire 응답을 클린 스키마로 변환. 데이터 없으면 None.

    선관위 응답은 회차에 따라 필드명이 다르므로 _pick으로 여러 후보를 시도한다.
    OpenAPI v4.3 가이드 기준 분리 필드:
      psTusu     = 선거일 투표자수 (당일분)
      psEtcTusu  = 거소·사전·선상·재외 투표자수 (사전+거소 통합)
      psSunsu    = 선거일투표 선거인수
      psEtcSunsu = 거소·사전·선상·재외 선거인수
    합계 행이 빠져 있으면 시도 합산으로 추정해 national을 만든다.
    """
    items = raw.get("items") or []
    if not items:
        return None
    national: dict | None = None
    by_sido: list[dict] = []
    for it in items:
        sd_raw = (_pick(it, "sdName", "siDoNm") or "").strip()
        eligible = _to_num(_pick(it, "totSunsu", "tot_Sunsu", "elcGrpe", "elcCnt", "sunsu"))
        voted = _to_num(_pick(it, "totTusu", "tot_Tusu", "votCnt", "votngCnt", "tusu"))
        rate = _to_num(_pick(it, "Turnout", "turnout", "votRate", "votngRate"))
        if rate is None and eligible and voted:
            rate = round(voted / eligible * 100, 2)
        # 분리 필드 — 본투표(당일) vs 사전+거소
        day_voted = _to_num(_pick(it, "psTusu", "ps_Tusu"))
        early_voted = _to_num(_pick(it, "psEtcTusu", "ps_Etc_Tusu"))
        day_eligible = _to_num(_pick(it, "psSunsu", "ps_Sunsu"))
        early_eligible = _to_num(_pick(it, "psEtcSunsu", "ps_Etc_Sunsu"))
        # 사전투표가 차지하는 비중 (사전+거소) / 총투표자 * 100
        early_share = None
        if early_voted is not None and voted:
            early_share = round(early_voted / voted * 100, 2)
        # 사전+거소 투표율 = 사전투표자 / 총 선거인수 (전체 유권자 대비 사전투표 비율)
        early_pct_of_eligible = None
        if early_voted is not None and eligible:
            early_pct_of_eligible = round(early_voted / eligible * 100, 2)
        entry = {
            "sd_name": sd_raw or None,
            "eligible_voters": eligible,
            "voters_so_far": voted,
            "turnout_pct": rate,
            "day_voters_so_far": day_voted,
            "early_voters_so_far": early_voted,
            "day_eligible_voters": day_eligible,
            "early_eligible_voters": early_eligible,
            "early_share_of_total_pct": early_share,
            "early_vote_rate_pct": early_pct_of_eligible,
        }
        if sd_raw in ("합계", "계", "전국", ""):
            entry["sd_name"] = "전국"
            national = entry
        else:
            by_sido.append(entry)
    if not national and by_sido:
        def _sum(key):
            return sum((s[key] or 0) for s in by_sido if s.get(key) is not None) or None
        elig = _sum("eligible_voters")
        voted = _sum("voters_so_far")
        day_voted = _sum("day_voters_so_far")
        early_voted = _sum("early_voters_so_far")
        rate = round(voted / elig * 100, 2) if elig and voted else None
        early_share = round(early_voted / voted * 100, 2) if voted and early_voted else None
        early_pct = round(early_voted / elig * 100, 2) if elig and early_voted else None
        national = {
            "sd_name": "전국",
            "eligible_voters": elig,
            "voters_so_far": voted,
            "turnout_pct": rate,
            "day_voters_so_far": day_voted,
            "early_voters_so_far": early_voted,
            "day_eligible_voters": _sum("day_eligible_voters"),
            "early_eligible_voters": _sum("early_eligible_voters"),
            "early_share_of_total_pct": early_share,
            "early_vote_rate_pct": early_pct,
        }
    return {"national": national, "by_sido": by_sido}


# ============ 투표율 웹 스크랩 폴백 (OpenAPI INFO-03 대응) ============

_VCVP_URL = "https://info.nec.go.kr/electioninfo/electionInfo_report.xhtml"
_SIDO_FULL = {"서울":"서울특별시","부산":"부산광역시","대구":"대구광역시","인천":"인천광역시","광주":"광주광역시",
    "대전":"대전광역시","울산":"울산광역시","세종":"세종특별자치시","경기":"경기도","강원":"강원특별자치도",
    "충북":"충청북도","충남":"충청남도","전북":"전북특별자치도","전남":"전라남도","경북":"경상북도",
    "경남":"경상남도","제주":"제주특별자치도"}
_SIDO_SET = set(_SIDO_FULL.values())

# VCVP01 웹 리포트 시도 cityCode (구·시·군 드릴다운용). 행정구역 개편 반영(2026).
_SIDO_CITYCODE = {
    "서울특별시": "1100", "부산광역시": "2600", "대구광역시": "2700", "인천광역시": "2800",
    "광주광역시": "2900", "대전광역시": "3000", "울산광역시": "3100", "세종특별자치시": "5100",
    "경기도": "4100", "강원특별자치도": "5200", "충청북도": "4300", "충청남도": "4400",
    "전북특별자치도": "5300", "전라남도": "4600", "경상북도": "4700", "경상남도": "4800",
    "제주특별자치도": "4900",
}


def scrape_turnout_web(sg_id: str) -> dict | None:
    """OpenAPI가 투표율을 주지 않을 때 NEC 웹 리포트(VCVP01)를 스크랩.
    20260603 본투표 전용. 표: 시도명|선거인[당일·사전·계]|투표[당일·사전·계]|투표율%.
    반환 스키마는 normalize_turnout과 동일({national, by_sido}). 실패 시 None."""
    import re
    if sg_id != "20260603":
        return None
    eid = "00" + sg_id
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0",
               "Accept-Language": "ko-KR,ko;q=0.9",
               "Referer": f"https://info.nec.go.kr/main/showDocument.xhtml?electionId={eid}&topMenuId=VC&secondMenuId=VCVP01"}
    body = {"electionId": eid, "requestURI": f"/electioninfo/{eid}/vc/vcvp01.jsp",
            "topMenuId": "VC", "secondMenuId": "VCVP01", "menuId": "VCVP01",
            "statementId": "VCVP01_#2_SUM", "cityCode": "0", "sggTime": "30시", "timeCode": "30"}
    def _num(s):
        s = re.sub(r"[^\d.]", "", s or "")
        if not s:
            return None
        return int(float(s)) if "." not in s else float(s)
    try:
        r = requests.post(_VCVP_URL, data=body, headers=headers, timeout=25)
        r.raise_for_status()
        html = r.text
    except Exception as e:
        print(f"  ! 투표율 웹 스크랩 실패: {e}", file=sys.stderr)
        return None
    def _parse(html_text):
        nat, sidos = None, []
        for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", html_text, re.S):
            cells = [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
            if len(cells) not in (8, 9):  # 전체=8칸, 특정시각=9칸(끝 개표구 칸)
                continue
            name = cells[0]
            if name not in _SIDO_SET and name not in _SIDO_FULL and name not in ("합계", "계", "전국"):
                continue
            entry = {
                "sd_name": "전국" if name in ("합계", "계", "전국") else _SIDO_FULL.get(name, name),
                "eligible_voters": _num(cells[3]), "voters_so_far": _num(cells[6]),
                "turnout_pct": _num(cells[7]), "day_voters_so_far": _num(cells[4]),
                "early_voters_so_far": _num(cells[5]), "day_eligible_voters": _num(cells[1]),
                "early_eligible_voters": _num(cells[2]),
            }
            if entry["sd_name"] == "전국":
                nat = entry
            else:
                sidos.append(entry)
        return nat, sidos
    national, by_sido = _parse(html)
    if not national and not by_sido:
        return None
    # 오늘 시간대별 전국 누계 곡선(07시~현재) — 과거선거 비교용
    hourly = []
    cur_hour = min(max(datetime.now(KST).hour, 7), 18)
    for h in range(7, cur_hour + 1):
        for _attempt in range(2):  # 정시 스냅샷은 차트에 빠지면 안 되므로 1회 재시도
            try:
                hb = dict(body); hb["timeCode"] = str(h); hb["sggTime"] = f"{h}시"
                ht = requests.post(_VCVP_URL, data=hb, headers=headers, timeout=20).text
                nat_h, _sd = _parse(ht)
                # 0 이하는 미확정 스냅샷(마감 직후 18시 등) → 기록 안 함
                if nat_h and (nat_h.get("turnout_pct") or 0) > 0:
                    hourly.append({"time": f"{h:02d}:00", "turnout_pct": nat_h["turnout_pct"],
                                   "voters_so_far": nat_h.get("voters_so_far")})
                    break
            except Exception:
                pass
    # 이전 current.json의 hourly와 병합 — 정시 스냅샷은 고정값이므로 한 번 잡으면 유실 금지.
    # (특정 시각 POST가 간헐 실패해도 차트에서 그 점이 사라지지 않도록 시간대별 max 유지)
    try:
        prev = json.loads((OUT_DIR / "current.json").read_text(encoding="utf-8"))
        by_t = {x["time"]: x for x in hourly if x.get("turnout_pct") is not None}
        for ph in ((prev.get("turnout") or {}).get("hourly") or []):
            t, pv = ph.get("time"), ph.get("turnout_pct")
            if not t or not pv or pv <= 0:
                continue
            if t not in by_t or by_t[t].get("turnout_pct") is None or pv > by_t[t]["turnout_pct"]:
                by_t[t] = {"time": t, "turnout_pct": pv, "voters_so_far": ph.get("voters_so_far")}
        hourly = [by_t[t] for t in sorted(by_t)]
    except Exception:
        pass
    # 누계는 단조 증가 — 미확정 낮은 값(마감 직후 18시 0.x% 등)은 제거
    _clean, _mx = [], -1.0
    for x in hourly:
        v = x.get("turnout_pct")
        if v is not None and v > _mx:
            _clean.append(x); _mx = v
    hourly = _clean
    # 전국 시군구별 누계 투표율 — 17개 시도 cityCode 드릴다운(셀 구조는 시도별과 동일 8칸).
    # by_sigungu = {시도명: {"total": {합계}, "sigungu": [{name,rate,...}, ...]}}
    by_sigungu = {}
    for sd_name, code in _SIDO_CITYCODE.items():
        try:
            gb = dict(body); gb["cityCode"] = code
            gt = requests.post(_VCVP_URL, data=gb, headers=headers, timeout=20).text
            total, items = None, []
            for tr in re.findall(r"<tr[^>]*>(.*?)</tr>", gt, re.S):
                cells = [re.sub(r"<[^>]+>", "", c).strip() for c in re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)]
                if len(cells) != 8:
                    continue
                nm = cells[0]
                entry = {"name": nm, "eligible_voters": _num(cells[3]),
                         "voters_so_far": _num(cells[6]), "turnout_pct": _num(cells[7]),
                         "day_voters_so_far": _num(cells[4]), "early_voters_so_far": _num(cells[5])}
                if nm in ("합계", "계"):
                    total = entry
                else:
                    items.append(entry)
            if items or total:
                by_sigungu[sd_name] = {"total": total, "sigungu": items}
        except Exception as e:
            print(f"  ! {sd_name} 시군구 스크랩 실패: {e}", file=sys.stderr)
    # 하위호환: 서울 자치구별(seoul_gu) — 기존 라이브 섹션이 읽는 키 유지
    seoul_gu = [{"gu_name": g["name"], **{k: g[k] for k in g if k != "name"}}
                for g in (by_sigungu.get("서울특별시", {}).get("sigungu") or [])]
    return {"national": national, "by_sido": by_sido, "hourly": hourly,
            "seoul_gu": seoul_gu, "by_sigungu": by_sigungu,
            "source": "info.nec.go.kr VCVP01 (웹)"}


# ============ 개표 웹 스크랩 폴백 (OpenAPI INFO-03 대응, VCCP09) ============
# 정당명 접두 분리용 — 긴 이름 우선(부분일치 방지). codes 파일 있으면 보강.
_PARTY_NAMES = ["더불어민주당", "국민의힘", "개혁신당", "조국혁신당", "진보당", "정의당",
                "기본소득당", "사회민주당", "여성의당", "노동당", "녹색당", "자유통일당",
                "국가혁명당", "가가국민참여신당", "히시태그국민정책당", "대한국민당", "무소속"]
try:
    _pj = json.loads((ROOT / "data" / "codes" / TARGET_SG_ID / "parties.json").read_text(encoding="utf-8"))
    _PARTY_NAMES = sorted({p.get("jdName", "") for p in _pj if p.get("jdName")} | set(_PARTY_NAMES),
                          key=len, reverse=True)
except Exception:
    _PARTY_NAMES = sorted(set(_PARTY_NAMES), key=len, reverse=True)


def _split_party(s: str) -> tuple[str, str]:
    """'더불어민주당정원오' → ('더불어민주당','정원오'). '무소속한동훈' → ('무소속','한동훈')."""
    s = (s or "").strip()
    for p in _PARTY_NAMES:
        if p != "무소속" and s.startswith(p):
            return p, s[len(p):].strip()
    if s.startswith("무소속"):      # 무소속 후보도 접두 제거(이름만 남김)
        return "무소속", s[len("무소속"):].strip()
    return "무소속", s


# statementId: 선거종류별로 다르다. #3=시도지사, #4=기초단체장(시장·군수·구청장).
# 둘 다 '선거구명+후보이름(정당+성명)' 헤더행 → 득표행 → 득표율행' 3행 블록 구조라
# 이름이 표에 직접 들어와 기호 추정·사퇴 매핑이 전혀 필요 없다(엉뚱한 당선자 위험 없음).
_VCCP_STMT = {"3": "VCCP09_#3", "4": "VCCP09_#4", "11": "VCCP09_#11"}


def _vccp_rows(eid: str, sg_type: str, city_code: str, statement_id: str) -> list[list[str]] | None:
    """VCCP09 리포트 POST → '개표율·득표' 테이블 셀 2차원 리스트. 실패/없음 시 None."""
    import re as _re
    headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0",
               "Accept-Language": "ko-KR,ko;q=0.9",
               "Referer": f"https://info.nec.go.kr/main/showDocument.xhtml?electionId={eid}&topMenuId=VC&secondMenuId=VCCP09"}
    body = {"electionId": eid, "requestURI": f"/electioninfo/{eid}/vc/vccp09.jsp",
            "topMenuId": "VC", "secondMenuId": "VCCP09", "menuId": "VCCP09",
            "statementId": statement_id, "electionCode": sg_type, "cityCode": city_code,
            "sggCityCode": "0", "townCode": "-1", "sgTypecode": sg_type}
    try:
        html = requests.post(_VCVP_URL, data=body, headers=headers, timeout=25).text
    except Exception as e:
        print(f"  ! 개표 웹 스크랩 실패(sg_type={sg_type} city={city_code}): {e}", file=sys.stderr)
        return None
    tbls = [t for t in _re.findall(r"<table[^>]*>(.*?)</table>", html, _re.S) if "개표율" in t and "득표" in t]
    if not tbls:
        return None
    return [[_re.sub(r"\s+", " ", _re.sub(r"<[^>]+>", "", c)).replace("\xa0", " ").strip()
             for c in _re.findall(r"<t[dh][^>]*>(.*?)</t[dh]>", tr, _re.S)]
            for tr in _re.findall(r"<tr[^>]*>(.*?)</tr>", tbls[0], _re.S)]


def _parse_vccp_blocks(rows: list[list[str]], sg_type: str, sd_override: str | None = None,
                       sd_lookup: dict | None = None, sgg_col: str | None = None) -> list[dict]:
    """VCCP09 3행 블록(이름헤더/득표/득표율)을 races 리스트로 변환.
    - sd_override: a[0]=선거구(sgg), sd_name=인자값 (기초단체장: 시도 cityCode로 순회 시).
    - sd_lookup: a[0]=선거구(sgg), sd_name=lookup[a[0]] (국회의원 재보궐: 전국 1콜·선거구명→시도).
    - sgg_col='b1': a[0]=구시군(wiw), 선거구명은 득표행 b[1] (기초의원·시도의원 #6/#5).
    - 모두 없으면 a[0]=sd_name (시도지사)."""
    import re as _re

    def _i(s):
        s = _re.sub(r"[^\d]", "", s or "")
        return int(s) if s else 0

    label = SG_LABELS.get(sg_type, sg_type)
    races, i = [], 0
    while i < len(rows):
        a = rows[i]
        if len(a) >= 6 and a[0] and a[0] not in ("선거구명", "합계") and "계" in a:
            b = rows[i + 1] if i + 1 < len(rows) else []
            gi = a.index("계")
            wiw_name = None
            if sgg_col == "b1":
                sd_name = sd_override
                sgg_name = (b[1].strip() if len(b) > 1 and b[1].strip() else a[0])
                wiw_name = a[0]
            elif sd_lookup is not None:
                sd_name, sgg_name = sd_lookup.get(a[0]), a[0]
            elif sd_override:
                sd_name, sgg_name = sd_override, a[0]
            else:
                sd_name, sgg_name = a[0], None
            cand_strs = a[4:gi]
            votes = b[4:gi] if len(b) > gi else []
            valid = _i(b[gi]) if len(b) > gi else 0
            invalid = _i(b[gi + 1]) if len(b) > gi + 1 else 0
            eligible = _i(b[2]) if len(b) > 2 else 0
            progress = None
            if len(b) > gi + 3:
                pr = _re.sub(r"[^\d.]", "", b[gi + 3])
                progress = round(float(pr), 2) if pr else None
            cands = []
            for cs, vv in zip(cand_strs, votes):
                cs = (cs or "").strip()
                if not cs:        # 고정폭 표의 빈 후보 칼럼(기초단체장 #4) 스킵
                    continue
                pty, nm = _split_party(cs)
                if not nm:
                    continue
                v = _i(vv)
                cands.append({"name": nm, "jd_name": pty, "votes": v,
                              "share_pct": round(v / valid * 100, 2) if valid else None})
            cands.sort(key=lambda c: c["votes"], reverse=True)
            for idx, c in enumerate(cands, 1):
                c["current_rank"] = idx
            rank_diff = None
            if len(cands) >= 2 and cands[0]["share_pct"] is not None and cands[1]["share_pct"] is not None:
                rank_diff = round(cands[0]["share_pct"] - cands[1]["share_pct"], 2)
            races.append({
                "race_key": f"{sg_type}|{sd_name}|{sgg_name or ''}", "sg_type_code": sg_type, "sg_type_label": label,
                "sd_name": sd_name, "sgg_name": sgg_name, "wiw_name": wiw_name,
                "eligible_voters": eligible, "valid_votes": valid, "invalid_votes": invalid,
                "progress_pct": progress, "rank1_minus_rank2_pp": rank_diff, "candidates": cands,
            })
            i += 3
        else:
            i += 1
    return races


def scrape_counting_web(sg_id: str, sg_type: str = "3") -> list[dict] | None:
    """OpenAPI 개표가 비었을 때 NEC 웹 개표상황(VCCP09)을 스크랩(시도지사 등 전국 1콜).
    normalize_row와 동일 스키마의 races 리스트 반환. 실패 시 None."""
    if sg_id != "20260603":
        return None
    rows = _vccp_rows("00" + sg_id, sg_type, "0", _VCCP_STMT.get(sg_type, "VCCP09_#3"))
    if not rows:
        return None
    return _parse_vccp_blocks(rows, sg_type, sd_override=None) or None


def scrape_counting_basic_head(sg_id: str) -> list[dict] | None:
    """기초단체장(시장·군수·구청장) 개표 — VCCP09_#4를 17개 시도 cityCode로 순회.
    이름이 표 헤더에 직접 들어와(시도지사와 동일 구조) 기호 추정·사퇴 매핑이 불필요해 안전하다.
    세종·제주 등 기초단체장 미실시 시도는 결과 없음 → 자동 스킵."""
    if sg_id != "20260603":
        return None
    eid = "00" + sg_id
    all_races: list[dict] = []
    for sd_name, code in _SIDO_CITYCODE.items():
        rows = _vccp_rows(eid, "4", code, "VCCP09_#4")
        if not rows:
            continue
        rr = _parse_vccp_blocks(rows, "4", sd_override=sd_name)
        all_races += rr
        time.sleep(0.15)
    return all_races or None


def _assembly_sd_lookup(sg_id: str) -> dict:
    """국회의원(sgTypecode=2) 등록자료에서 선거구명(sggName)→시도(sdName) 매핑."""
    try:
        fs = sorted((ROOT / "data" / "candidates" / sg_id).glob("snapshot_*.json"))
        if not fs:
            return {}
        d = json.loads(fs[-1].read_text(encoding="utf-8"))
        cands = d if isinstance(d, list) else d.get("candidates", [])
        return {c.get("sggName"): c.get("sdName") for c in cands
                if str(c.get("sgTypecode")) == "2" and c.get("sggName")}
    except Exception:
        return {}


def scrape_counting_assembly(sg_id: str) -> list[dict] | None:
    """국회의원 재·보궐선거 개표 — VCCP09_#2, 전국 1콜(cityCode=0).
    이름이 표 헤더에 직접 들어와 안전. 선거구명→시도는 등록자료로 매핑."""
    if sg_id != "20260603":
        return None
    rows = _vccp_rows("00" + sg_id, "2", "0", "VCCP09_#2")
    if not rows:
        return None
    return _parse_vccp_blocks(rows, "2", sd_lookup=_assembly_sd_lookup(sg_id)) or None


def scrape_counting_muni_council_watch(sg_id: str) -> list[dict] | None:
    """기초의원(구시군의회의원, sgTypecode=6) — 워치리스트에 등록된 기초의원 후보의
    선거구만 콕 집어 수집(전체 기초의원 수천 선거구는 받지 않는다).
    워치리스트 후보를 등록자료로 조회해 sgTypecode=6이면 해당 시도만 VCCP09_#6 스크랩,
    그 후보가 포함된 선거구만 보존. 이름이 표에 직접 들어와 안전."""
    if sg_id != "20260603":
        return None
    try:
        wl = json.loads((ROOT / "data" / "live_counting" / "watchlist.json").read_text(encoding="utf-8"))
    except Exception:
        return None
    try:
        fs = sorted((ROOT / "data" / "candidates" / sg_id).glob("snapshot_*.json"))
        cands = json.loads(fs[-1].read_text(encoding="utf-8")) if fs else []
        cands = cands if isinstance(cands, list) else cands.get("candidates", [])
    except Exception:
        cands = []
    reg6 = {(c.get("name"), c.get("sdName")) for c in cands if str(c.get("sgTypecode")) == "6"}
    targets: dict[str, set] = {}
    for w in wl.get("candidates", []):
        if (w.get("name"), w.get("sido")) in reg6:
            targets.setdefault(w["sido"], set()).add(w["name"])
    if not targets:
        return None
    eid = "00" + sg_id
    out: list[dict] = []
    for sd_name, names in targets.items():
        code = _SIDO_CITYCODE.get(sd_name)
        if not code:
            continue
        rows = _vccp_rows(eid, "6", code, "VCCP09_#6")
        if not rows:
            continue
        for r in _parse_vccp_blocks(rows, "6", sd_override=sd_name, sgg_col="b1"):
            if any(c["name"] in names for c in r["candidates"]):
                out.append(r)
        time.sleep(0.15)
    return out or None


# ============ 가공 / 저장 ============

def build_current(
    sg_id: str,
    polled_at: datetime,
    counting_calls: list[dict],
    turnout: dict | None,
    web_races: list[dict] | None = None,
) -> tuple[dict, dict]:
    races: list[dict] = []
    seen_keys: set[str] = set()
    races_with_data = 0
    progress_sum = 0.0
    progress_count = 0

    for call in counting_calls:
        for row in call["items"]:
            # 선거구 합계행 또는 wiwName 비어있는 행만 사용 (읍면동 세부행은 드롭).
            wiw = (row.get("wiwName") or "").strip()
            if wiw and wiw != "합계":
                continue
            normalized = normalize_row(row)
            if normalized["race_key"] in seen_keys:
                continue
            seen_keys.add(normalized["race_key"])
            races.append(normalized)
            if normalized["progress_pct"] is not None:
                progress_sum += normalized["progress_pct"]
                progress_count += 1
            if normalized["candidates"]:
                races_with_data += 1

    races.sort(key=lambda r: (r["sg_type_code"], r["sd_name"], r["sgg_name"] or ""))

    avg_progress = round(progress_sum / progress_count, 2) if progress_count else None
    openapi_empty = (
        all(c["result_code"] in ("INFO-03", "ERROR-03") for c in counting_calls)
        if counting_calls else True
    )

    # OpenAPI 개표가 비었고 웹 스크랩(VCCP09) 결과가 있으면 그것으로 대체.
    source = "openapi"
    if openapi_empty and web_races:
        races = sorted(web_races, key=lambda r: (r["sg_type_code"], r["sd_name"], r["sgg_name"] or ""))
        races_with_data = sum(1 for r in races if r.get("candidates"))
        progs = [r["progress_pct"] for r in races if r.get("progress_pct") is not None]
        avg_progress = round(sum(progs) / len(progs), 2) if progs else None
        source = "web(VCCP09)"

    if polled_at < ELECTION_DAY_KST:
        phase = "pre"
    elif not races:
        phase = "official-pending"
    elif avg_progress is not None and avg_progress >= 99.0:
        phase = "final"
    else:
        phase = "live"

    current = {
        "sgId": sg_id,
        "polled_at": polled_at.isoformat(timespec="seconds"),
        "source": source,
        "phase": phase,
        "races": races,
    }
    if turnout:
        current["turnout"] = turnout

    national_turnout = (
        (turnout or {}).get("national", {}).get("turnout_pct") if turnout else None
    )
    meta = {
        "polled_at": polled_at.isoformat(timespec="seconds"),
        "source": "openapi",
        "phase": phase,
        "races_total": len(races),
        "races_with_data": races_with_data,
        "avg_progress_pct": avg_progress,
        "openapi_empty": openapi_empty,
        "progress_calc": "(yutusu + mutusu) / sunsu * 100",
        "turnout_available": bool(turnout),
        "national_turnout_pct": national_turnout,
    }
    return current, meta


def atomic_write(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def update_timeseries(
    path: Path,
    sg_id: str,
    polled_at: datetime,
    turnout: dict | None,
) -> None:
    """기존 timeseries.json을 읽어 새로 수집한 투표율 포인트를 append 후 저장.

    프론트 라인 차트가 읽는 파일. national + by_sido 양쪽 다 누적한다.
    같은 시각 중복 append를 막기 위해 polled_at이 동일하면 마지막 항목을 덮어쓴다.
    """
    if not turnout:
        return

    existing: dict = {"sgId": sg_id, "national": [], "by_sido": {}}
    if path.exists():
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            pass

    ts_iso = polled_at.isoformat(timespec="seconds")
    existing.setdefault("national", [])
    existing.setdefault("by_sido", {})
    existing["sgId"] = sg_id
    existing["updated_at"] = ts_iso

    def _append(series: list[dict], point: dict) -> None:
        if series and series[-1].get("polled_at") == point["polled_at"]:
            series[-1] = point
        else:
            series.append(point)

    nat = turnout.get("national") or {}
    if nat.get("turnout_pct") is not None:
        _append(existing["national"], {
            "polled_at": ts_iso,
            "turnout_pct": nat.get("turnout_pct"),
            "voters_so_far": nat.get("voters_so_far"),
        })

    for s in turnout.get("by_sido") or []:
        name = s.get("sd_name")
        if not name or s.get("turnout_pct") is None:
            continue
        series = existing["by_sido"].setdefault(name, [])
        _append(series, {
            "polled_at": ts_iso,
            "turnout_pct": s.get("turnout_pct"),
            "voters_so_far": s.get("voters_so_far"),
        })

    atomic_write(path, existing)


def main() -> None:
    parser = argparse.ArgumentParser(description="선관위 투개표·투표율 OpenAPI 1회 수집")
    parser.add_argument("--sg-id", default=DEFAULT_SG_ID, help="기본 20260603")
    parser.add_argument(
        "--sg-types",
        default=",".join(DEFAULT_SG_TYPES),
        help="개표 호출 대상 sgTypecode. 기본 3,4,11 (시도지사·기초단체장·교육감)",
    )
    parser.add_argument("--skip-counting", action="store_true", help="개표 호출 생략 (투표 시간대용)")
    parser.add_argument("--skip-turnout", action="store_true", help="투표율 호출 생략")
    parser.add_argument("--dry-run", action="store_true", help="저장하지 않고 stdout만 출력")
    args = parser.parse_args()

    if not API_KEY:
        sys.exit("환경변수 NEC_API_KEY가 설정되지 않았습니다.")

    sg_types = [s.strip() for s in args.sg_types.split(",") if s.strip()]
    polled_at = datetime.now(KST)
    started = time.monotonic()
    print(f"[live_counting] polled_at={polled_at.isoformat(timespec='seconds')}")
    print(f"  sg_id={args.sg_id}  sg_types={sg_types}")

    # 투표율 — 1회 호출
    turnout_raw: dict = {"result_code": "skipped", "items": []}
    turnout: dict | None = None
    if not args.skip_turnout:
        try:
            turnout_raw = call_turnout(args.sg_id)
        except PortalQuotaError as e:
            sys.exit(f"포털 한도/권한 에러 (투표율). 후속 호출 중단: {e}")
        turnout = normalize_turnout(turnout_raw)
        if not turnout:
            # OpenAPI가 투표율 미제공(6/3 당일 INFO-03) → NEC 웹 리포트 스크랩 폴백
            turnout = scrape_turnout_web(args.sg_id)
            if turnout:
                turnout_raw["result_code"] = "WEB-SCRAPE"
        if turnout:
            src = " (웹)" if turnout.get("source", "").endswith("(웹)") else ""
            print(
                f"  · 투표율{src}  전국 {turnout['national'].get('turnout_pct')}% · "
                f"시도 {len(turnout['by_sido'])}개"
            )
        else:
            print(f"  · 투표율  resultCode={turnout_raw.get('result_code')}  데이터 없음")

    # 개표 — sg_types × 시도 호출. 포털 한도 초과 감지 시 즉시 중단.
    counting_calls: list[dict] = []
    failed = 0
    portal_aborted = False
    if not args.skip_counting:
        for sg_type in sg_types:
            if portal_aborted:
                break
            for sido in SIDOS:
                try:
                    result = call_counting(args.sg_id, sg_type, sido)
                except PortalQuotaError as e:
                    print(f"  ✕ 포털 한도/권한 에러 (개표). 후속 호출 중단: {e}", file=sys.stderr)
                    portal_aborted = True
                    break
                except Exception as e:
                    failed += 1
                    print(f"  ! 실패 sg_type={sg_type} sd={sido}: {e}", file=sys.stderr)
                    continue
                counting_calls.append(result)
                print(
                    f"  · 개표 sg_type={sg_type} sd={sido:8s}  "
                    f"resultCode={result['result_code']}  rows={len(result['items'])}"
                )
                time.sleep(0.2)

    # OpenAPI 개표가 비어 있으면(INFO-03) NEC 웹 개표상황(VCCP09)을 시도지사 한정 스크랩.
    web_races = None
    _oa_empty = (all(c["result_code"] in ("INFO-03", "ERROR-03") for c in counting_calls)
                 if counting_calls else True)
    if _oa_empty and polled_at >= ELECTION_DAY_KST:
        gov = scrape_counting_web(args.sg_id, "3") or []
        if gov:
            print(f"  · 개표 웹(VCCP09 #3) 폴백: 시도지사 {len(gov)}곳")
        # 기초단체장(시장·군수·구청장) — VCCP09_#4, 17개 시도 순회. 이름 직접 포함.
        bh = scrape_counting_basic_head(args.sg_id) or []
        if bh:
            print(f"  · 개표 웹(VCCP09 #4) 폴백: 기초단체장 {len(bh)}곳")
        # 국회의원 재·보궐 — VCCP09_#2, 전국 1콜. 이름 직접 포함.
        na = scrape_counting_assembly(args.sg_id) or []
        if na:
            print(f"  · 개표 웹(VCCP09 #2) 폴백: 국회의원 재보궐 {len(na)}곳")
        # 기초의원 — 워치리스트에 등록된 기초의원 후보의 선거구만(목포 손혜원·남원 이숙자 등).
        kc = scrape_counting_muni_council_watch(args.sg_id) or []
        if kc:
            print(f"  · 개표 웹(VCCP09 #6) 폴백: 기초의원 주목 {len(kc)}곳")
        # 교육감 — VCCP09_#11, 전국 1콜(시도별). 정당 없는 단독 선출 → 정당 표기 제거.
        edu = scrape_counting_web(args.sg_id, "11") or []
        for r in edu:
            for c in r.get("candidates", []):
                c["jd_name"] = ""
        if edu:
            print(f"  · 개표 웹(VCCP09 #11) 폴백: 교육감 {len(edu)}곳")
        web_races = (gov + bh + na + kc + edu) or None

    current, meta = build_current(args.sg_id, polled_at, counting_calls, turnout, web_races)
    meta["counting_calls_total"] = len(counting_calls) + failed
    meta["counting_calls_failed"] = failed
    meta["portal_aborted"] = portal_aborted
    meta["elapsed_seconds"] = round(time.monotonic() - started, 1)

    print(
        f"\n  races={meta['races_total']}  with_data={meta['races_with_data']}  "
        f"avg_progress={meta['avg_progress_pct']}  "
        f"national_turnout={meta['national_turnout_pct']}  phase={meta['phase']}"
    )

    if args.dry_run:
        print("\n  --dry-run: 저장 생략")
        return

    raw_path = RAW_DIR / f"openapi_{polled_at.strftime('%Y%m%d_%H%M%S')}.json"
    atomic_write(
        raw_path,
        {
            "polled_at": polled_at.isoformat(timespec="seconds"),
            "counting_calls": counting_calls,
            "turnout_call": turnout_raw,
        },
    )
    atomic_write(OUT_DIR / "current.json", current)
    atomic_write(OUT_DIR / "meta.json", meta)
    update_timeseries(OUT_DIR / "timeseries.json", args.sg_id, polled_at, turnout)
    print(f"\n  저장: {raw_path.relative_to(ROOT)}")
    print(f"        {(OUT_DIR / 'current.json').relative_to(ROOT)}")
    print(f"        {(OUT_DIR / 'meta.json').relative_to(ROOT)}")
    print(f"        {(OUT_DIR / 'timeseries.json').relative_to(ROOT)}")

    # 포털 한도/권한 에러로 중단됐다면 워크플로우가 실패로 인식하도록 exit 1.
    if portal_aborted:
        sys.exit(1)


if __name__ == "__main__":
    main()
