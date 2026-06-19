#!/usr/bin/env python3
"""호남 41개 시군 기초단체장 '개표현황(투표구별)' xlsx → 시군별 CSV + _manifest.json.

입력:  tmp/honam_umd/*.xlsx  (선거통계시스템 VCVP01에서 시군별로 받은 투표구별 개표 xlsx)
출력:  data/honam_umd/<시도>_<시군>.csv  +  data/honam_umd/_manifest.json
형식:  scripts/convert_nec_dongbyul_xlsx.py 와 동일 스키마(그 헬퍼를 그대로 재사용).

검증:
 1) 동소계(subtotal)+특수투표(special) 투표수 합 == 선거구합계(race_total) 투표수
 2) 각 행: 후보 득표수 합 == 유효표_계
무투표 시군: 개표가 없으므로 헤더+메모행만 남기고 manifest에 status=무투표 기록.
합계 불일치는 보정하지 않고 manifest에 그대로 기록한다(정확성 최우선).
"""
from __future__ import annotations
import csv, json, sys, unicodedata, importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IN_DIR = ROOT / "tmp/honam_umd"
OUT_DIR = ROOT / "data/honam_umd"

# 검증된 변환기 헬퍼 재사용 (수정하지 않음)
spec = importlib.util.spec_from_file_location("conv", ROOT / "scripts/convert_nec_dongbyul_xlsx.py")
conv = importlib.util.module_from_spec(spec); spec.loader.exec_module(conv)

# 호남 41개 시군 표준(전주는 완산+덕진 보고서를 전주시로 병합)
GWANGJU = ["동구", "서구", "남구", "북구", "광산구"]
JEONNAM = ["목포시", "여수시", "순천시", "나주시", "광양시", "담양군", "곡성군", "구례군", "고흥군", "보성군",
           "화순군", "장흥군", "강진군", "해남군", "영암군", "무안군", "함평군", "영광군", "장성군", "완도군", "진도군", "신안군"]
JEONBUK = ["전주시", "군산시", "익산시", "정읍시", "남원시", "김제시", "완주군", "진안군", "무주군", "장수군",
           "임실군", "순창군", "고창군", "부안군"]
CANON = [("광주광역시", g) for g in GWANGJU] + [("전라남도", g) for g in JEONNAM] + [("전북특별자치도", g) for g in JEONBUK]

def nfc(s): return unicodedata.normalize("NFC", s or "")

def parse_xlsx(path: Path):
    """convert_nec_dongbyul_xlsx.main()의 파싱부를 그대로 따와 (cands, rows) 반환."""
    rows = conv.read_sheet_rows(path)
    if len(rows) < 8:
        raise ValueError(f"행 수 부족({len(rows)})")
    row6 = rows[5] if len(rows) > 5 else []
    row7 = rows[6] if len(rows) > 6 else []
    cands, cand_count = conv.extract_candidate_columns(row6, row7)
    sgg_name = ""; cur_dong = "전체"; out = []
    for r_idx in range(6, len(rows)):
        r = rows[r_idx]
        if not r: continue
        first = (r[0] or "").strip() if r and r[0] else ""
        if not first: continue
        if first not in ("계", "소계", "관내사전투표", "거소·선상투표", "관외사전투표", "국외부재자투표") \
                and not conv.DONG_PAT.match(first):
            sgg_name = first
            box_name = (r[1] or "").strip() if len(r) > 1 else ""; offset = 2
        else:
            box_name = first; offset = 1
        if not box_name: continue
        kind = conv.classify(box_name)
        if kind == "box":
            m = conv.DONG_PAT.match(box_name)
            if m: cur_dong = m.group(1)
        elif kind in ("special", "race_total"):
            cur_dong = "전체"
        eligible = conv.to_int(r[offset]) if len(r) > offset else None
        voted = conv.to_int(r[offset + 1]) if len(r) > offset + 1 else None
        cand_votes = [conv.to_int(r[offset + 2 + i]) if len(r) > offset + 2 + i else None for i in range(cand_count)]
        total_valid = conv.to_int(r[offset + 2 + cand_count]) if len(r) > offset + 2 + cand_count else None
        invalid = conv.to_int(r[offset + 3 + cand_count]) if len(r) > offset + 3 + cand_count else None
        abstain = conv.to_int(r[offset + 4 + cand_count]) if len(r) > offset + 4 + cand_count else None
        d = {"선거구명": sgg_name, "동": cur_dong, "투표구명": box_name, "분류": kind,
             "선거인수": eligible, "투표수": voted}
        for c, v in zip(cands, cand_votes):
            d[f"{c['party']}_{c['name']}".strip("_")] = v
        d["유효표_계"] = total_valid; d["무효투표수"] = invalid; d["기권자수"] = abstain
        out.append(d)
    return cands, out

def verify(rows, cands):
    """반환: dict(검증 결과). 불일치는 기록만."""
    candcols = [f"{c['party']}_{c['name']}".strip("_") for c in cands]
    # 1) 행별 후보합 == 유효표_계
    row_bad = []
    for r in rows:
        cs = sum(r.get(c) or 0 for c in candcols)
        vc = r.get("유효표_계")
        if vc is not None and cs != vc:
            row_bad.append((r["투표구명"], cs, vc))
    # 2) subtotal+special 투표수 == race_total 투표수
    rt = next((r["투표수"] for r in rows if r["분류"] == "race_total"), None)
    sub = sum(r["투표수"] or 0 for r in rows if r["분류"] in ("subtotal", "special"))
    total_ok = (rt is not None and rt == sub)
    return {"race_total_투표수": rt, "subtotal+special_합": sub, "합계검증_통과": total_ok,
            "후보합_불일치행수": len(row_bad), "불일치샘플": row_bad[:5]}

def write_csv(path, rows):
    fields = list(rows[0].keys())
    with path.open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader(); w.writerows(rows)

# 시군명 → (시도, 시군) 역매핑 (호남 41개 시군명은 서로 유일). 전주 완산/덕진은 전주시로.
SGG2SD = {}
for _sd, _sgg in CANON:
    SGG2SD[nfc(_sgg)] = (_sd, _sgg)
SGG2SD[nfc("전주시완산구")] = ("전북특별자치도", "전주시")
SGG2SD[nfc("전주시덕진구")] = ("전북특별자치도", "전주시")

def route_sigungu(parsed_rows):
    """파싱된 행의 '선거구명'으로 (시도, 시군) 판정. 못 찾으면 None."""
    names = [nfc(r.get("선거구명") or "") for r in parsed_rows if r.get("선거구명")]
    for nm in names:
        if nm in SGG2SD: return SGG2SD[nm]
    # 부분일치(완산/덕진 등 변형 대비)
    for nm in names:
        for key, val in SGG2SD.items():
            if key in nm or nm in key: return val
    return None

def merge_jeonju(parsed_list):
    """완산·덕진 두 보고서 → 전주시 1개. 동/투표구 행은 이어붙이고 race_total은 합산."""
    cands = parsed_list[0][0]
    candcols = [f"{c['party']}_{c['name']}".strip("_") for c in cands]
    merged = []; rt = {"선거구명": "전주시", "동": "전체", "투표구명": "계", "분류": "race_total",
                       "선거인수": 0, "투표수": 0, **{c: 0 for c in candcols}, "유효표_계": 0, "무효투표수": 0, "기권자수": 0}
    for _, rows in parsed_list:
        for r in rows:
            if r["분류"] == "race_total":
                for k in ("선거인수", "투표수", "유효표_계", "무효투표수", "기권자수", *candcols):
                    rt[k] = (rt.get(k) or 0) + (r.get(k) or 0)
            else:
                merged.append(r)
    return cands, [rt] + merged

def main():
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    manifest = {"generated_by": "build_honam_umd.py", "input": str(IN_DIR), "rows": {}}
    # 1) 모든 xlsx 파싱 → 시군별 그룹(내용 기반 라우팅)
    files = sorted(IN_DIR.glob("*.xlsx")) if IN_DIR.exists() else []
    groups = {}; unrouted = []
    for p in files:
        try:
            cands, rows = parse_xlsx(p)
        except Exception as e:
            unrouted.append((p.name, f"파싱오류 {e}")); continue
        key = route_sigungu(rows)
        if not key:
            unrouted.append((p.name, "선거구명 라우팅 실패")); continue
        groups.setdefault(key, []).append((p.name, cands, rows))
    # 2) 시군별 CSV + 검증
    done = miss = 0
    for sd, sgg in CANON:
        out_csv = OUT_DIR / f"{sd}_{sgg}.csv"
        grp = groups.get((sd, sgg))
        if not grp:
            with out_csv.open("w", encoding="utf-8-sig", newline="") as f:
                f.write("선거구명,동,투표구명,분류,비고\n")
                f.write(f"{sgg},전체,,무투표또는미수집,\"xlsx 없음 — 무투표 당선이거나 아직 미다운로드\"\n")
            manifest["rows"][f"{sd}_{sgg}"] = {"status": "무투표또는미수집", "xlsx": None}
            miss += 1; print(f"  ⚠ {sd} {sgg}: xlsx 없음"); continue
        try:
            if len(grp) >= 2:  # 전주(완산+덕진) 등 분할 보고서 병합
                cands, rows = merge_jeonju([(c, r) for _, c, r in grp])
            else:
                cands, rows = grp[0][1], grp[0][2]
            src = [n for n, _, _ in grp]
            write_csv(out_csv, rows)
            v = verify(rows, cands)
            manifest["rows"][f"{sd}_{sgg}"] = {"status": "ok", "xlsx": src, "행수": len(rows), "후보수": len(cands), **v}
            done += 1
            flag = "✓" if v["합계검증_통과"] and v["후보합_불일치행수"] == 0 else "✗검증주의"
            print(f"  {flag} {sd} {sgg}: {len(rows)}행 합계검증={v['합계검증_통과']} 후보합불일치={v['후보합_불일치행수']}")
        except Exception as e:
            manifest["rows"][f"{sd}_{sgg}"] = {"status": "error", "error": str(e), "xlsx": [n for n, _, _ in grp]}
            print(f"  ✗ {sd} {sgg}: 오류 {e}")
    if unrouted:
        manifest["라우팅실패"] = unrouted
        print("\n⚠ 라우팅 실패 파일:", unrouted)
    manifest["요약"] = {"총시군": len(CANON), "처리완료": done, "미수집무투표": miss, "입력xlsx": len(files)}
    (OUT_DIR / "_manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"\n총 {len(CANON)}시군 | 처리 {done} | 미수집/무투표 {miss} | 입력 {len(files)}개")
    print(f"→ {OUT_DIR}/  +  _manifest.json")

if __name__ == "__main__":
    main()
