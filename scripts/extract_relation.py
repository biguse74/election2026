# -*- coding: utf-8 -*-
"""재산신고서에서 보유 주식의 '관계(본인/배우자/장남…)'를 좌표 OCR로 추출.

표는 [구분 | 관계 | 권리명세(종목 수량) | 가액 | 비고]. 관계 칸은 좌측, 셀병합으로
블록당 1회만 표기 → 각 주식 행을 '가장 가까운 관계 라벨'에 귀속(nearest-label).
수량주로 행을 찾아 매칭하므로 평가액·종목명 OCR 오류와 무관.

출력: data/stock_relations.json  { huboid: [{"수량주":N, "관계":"본인"}...] }
사용: python scripts/extract_relation.py --names 최기영
      python scripts/extract_relation.py --all   (저장·재개)
      python scripts/extract_relation.py --huboids-file FILE
"""
import argparse
import glob
import importlib.util
import json
import os
import re
import tempfile
from pathlib import Path

import fitz

ROOT = Path(__file__).resolve().parent.parent
SLIM = ROOT / "stocks" / "stock_holdings.json"
OUT = ROOT / "data" / "stock_relations.json"

# 평가액 추출기의 좌표 OCR 헬퍼 재사용
_spec = importlib.util.spec_from_file_location("av", ROOT / "scripts" / "extract_asset_value.py")
av = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(av)

REL = ["본인", "배우자", "장남", "장녀", "차남", "차녀", "삼남", "모", "부",
       "자부", "며느리", "손자", "손녀", "조모", "조부", "제", "매"]
QTY = re.compile(r"^(\d{1,3}(?:,\d{3})*)\s*주?$")


def person_relations(huboid, holdings):
    folder = next(iter(glob.glob(str(ROOT / f"data/disclosure_archive/{huboid}_*/재산"))), None)
    if not folder:
        return None
    tmp = tempfile.mkdtemp(dir=str(av.CACHE))
    pngs = []
    for pi, pdf in enumerate(sorted(glob.glob(os.path.join(folder, "*.PDF")))):
        doc = fitz.open(pdf)
        for pno in range(len(doc)):
            p = os.path.join(tmp, f"{pi}_{pno}.png")
            doc[pno].get_pixmap(dpi=200).save(p)
            pngs.append(p)
    coords = av.ocr_coords_multi(pngs)
    # 페이지별: 관계 라벨(좌측) + 수량 토큰(권리명세 칸) 수집
    rows = []          # (qty_value, y, page_idx)
    rels = []          # (rel_text, y, page_idx)
    for pidx, png in enumerate(pngs):
        ws = coords.get(png, [])
        if not ws:
            continue
        W = max((x + w for _, x, _, w in ws), default=1)
        for t, x, y, w in ws:
            if t in REL and x < W * 0.34:
                rels.append((t, y, pidx))
            m = QTY.match(t)
            if m and W * 0.42 < x < W * 0.72:
                rows.append((int(m.group(1).replace(",", "")), y, pidx))
    for png in pngs:
        try:
            os.remove(png)
        except OSError:
            pass
    try:
        os.rmdir(tmp)
    except OSError:
        pass
    if not rels or not rows:
        return None

    def nearest_rel(y, pidx):
        same = [(t, ry) for t, ry, rp in rels if rp == pidx]
        if not same:
            return None
        return min(same, key=lambda z: abs(z[1] - y))[0]

    out, used = [], set()
    for h in holdings:
        q = h.get("수량주")
        if not q:
            out.append({"수량주": q, "관계": None})
            continue
        cand = [(i, y, p) for i, (qv, y, p) in enumerate(rows) if qv == q and i not in used]
        if not cand:
            out.append({"수량주": q, "관계": None})
            continue
        i, y, p = cand[0]
        used.add(i)
        out.append({"수량주": q, "관계": nearest_rel(y, p)})
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--names", default="")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--huboids-file", default="")
    args = ap.parse_args()
    d = json.loads(SLIM.read_text(encoding="utf-8"))
    people = [p for p in d["people"] if p["holdings"]]

    if args.names:
        want = set(args.names.split(","))
        for p in [p for p in people if p["name"] in want]:
            rels = person_relations(str(p["huboid"]), p["holdings"])
            print(f"=== {p['name']} ===")
            for h, r in zip(p["holdings"], rels or []):
                print(f"  {h['종목']:18s} {h.get('수량주')}주 → {r['관계']}")
        return

    if args.huboids_file:
        want = {ln.strip() for ln in Path(args.huboids_file).read_text(encoding="utf-8").splitlines() if ln.strip()}
        people = [p for p in people if str(p["huboid"]) in want]

    done = json.loads(OUT.read_text(encoding="utf-8")) if OUT.exists() else {}
    todo = [p for p in people if str(p["huboid"]) not in done]
    print(f"관계 추출: 대상 {len(people)} · 남은 {len(todo)}", flush=True)
    for i, p in enumerate(todo, 1):
        hb = str(p["huboid"])
        try:
            rels = person_relations(hb, p["holdings"])
        except Exception as e:
            rels = None
            print(f"  ! {p['name']} {e}", flush=True)
        done[hb] = rels or []
        if i % 25 == 0:
            OUT.write_text(json.dumps(done, ensure_ascii=False), encoding="utf-8")
            print(f"  ...{i}/{len(todo)}", flush=True)
    OUT.write_text(json.dumps(done, ensure_ascii=False), encoding="utf-8")
    nz = sum(1 for v in done.values() if any(r.get("관계") for r in v))
    print(f"DONE 관계 {len(done)}명 · 관계붙음 {nz}명 → {OUT}")


if __name__ == "__main__":
    main()
