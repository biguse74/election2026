# -*- coding: utf-8 -*-
"""무소속·정당이동 단체장 사례 — 최종 표(CSV+MD)+요약 생성.
independent_heads.json(선관위 데이터) + 웹검색 계열확인(아래 KYE)을 결합.
"""
import csv
import json
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
R = ROOT / "data" / "research"
d = json.loads((R / "independent_heads.json").read_text(encoding="utf-8"))

# 웹검색으로 확인한 2026 무소속 당선자 계열 (근거 기사 제목+URL). 근거 없으면 '불명'.
KYE = {
    "오태완": ("국민의힘 계열", "국힘 복당 후 공천배제로 무소속 출마·3선",
             "경남 기초단체장 무소속 돌풍(서울경제)", "https://www.sedaily.com/article/20051755"),
    "전화식": ("국민의힘 계열", "국힘 경선 불만 무소속 출마, 국힘 당원 600여명 집단탈당 지지",
             "국힘 텃밭 경북서 무소속 군수 4명(한국일보)", "https://www.hankookilbo.com/news/article/A2026060413280003894"),
    "황이주": ("국민의힘 계열", "보수 아성(경북) 속 무소속 파란",
             "보수 아성 속 울진·울릉·청도·성주서 무소속 파란(뉴스핌)", "https://www.newspim.com/news/view/20260604000946"),
    "남한권": ("국민의힘 계열", "보수 아성(경북) 속 무소속 파란",
             "보수 아성 속 울진·울릉·청도·성주서 무소속 파란(뉴스핌)", "https://www.newspim.com/news/view/20260604000946"),
    "박권현": ("국민의힘 계열", "보수 아성(경북) 속 무소속 파란",
             "보수 아성 속 울진·울릉·청도·성주서 무소속 파란(뉴스핌)", "https://www.newspim.com/news/view/20260604000946"),
    "조규일": ("국민의힘 계열", "2022 국힘 당선→2026 무소속 출마(국힘 공천 배제 흐름)",
             "선관위 정당이동(국민의힘→무소속)", "info.nec.go.kr"),
    "김윤철": ("국민의힘 계열", "2022 국힘 당선→2026 무소속 당선",
             "선관위 정당이동(국민의힘→무소속)", "info.nec.go.kr"),
    "강진원": ("더불어민주당 계열", "민주 경선 거부당해 무소속 출마, 민주후보 17%p차 제침·징검다리 4선",
             "강진원 무소속으로 징검다리 4선(아시아투데이)", "https://www.asiatoday.co.kr/kn/view.php?key=20260604010001319"),
    "김신": ("더불어민주당 계열", "민주 소속이었으나 도당 감점→무소속, 민주후보 꺾음",
            "5전6기 무소속 김신 완도군수 당선(머니투데이)", "https://www.mt.co.kr/policy/2026/06/04/2026060401191557459"),
    "박성현": ("더불어민주당 계열", "민주 경선 컷오프(공천배제)→무소속, 현직 민주 정인화 꺾음(호남 5연속 무소속)",
             "공천 배제 딛고 무소속 박성현 광양시장 당선(한국일보)", "https://www.hankookilbo.com/news/article/A2026060400150002860"),
    "이홍기": ("확인 필요", "거창(영남) 무소속 당선이나 개별 계열 근거 미확보", "—", "—"),
}


def lineage_from_dir(direction):
    # 정당이동 방향으로 계열 추정
    prog = ("더불어민주당", "조국혁신당", "진보당", "정의당")
    cons = ("국민의힘", "개혁신당", "우리공화당")
    a, b = direction.split("→")
    side = lambda p: "진보" if p in prog else ("보수" if p in cons else None)
    s = side(b) or side(a)
    return {"진보": "더불어민주당(진보) 계열", "보수": "국민의힘(보수) 계열"}.get(s, "불명")


rows = []
# (C) 정당변경 동일후보 — 계열은 이동 방향으로(선관위 확정)
for x in d["정당변경동일후보"]:
    nm = x["후보명"]
    if nm in KYE:
        ky, why, title, url = KYE[nm]
    else:
        ky, why, title, url = lineage_from_dir(x["방향"]), f"정당이동 {x['방향']}", "선관위 정당이동", "info.nec.go.kr"
    rows.append({
        "권역": x["권역"], "시도": x["시도"], "시군구": x["시군구"], "후보명": nm,
        "2022_정당": x["2022_정당"], "2022_득표율": x["2022_득표율"], "2022_당락": x["2022_당락"],
        "2026_정당": x["2026_정당"], "2026_득표율": x["2026_득표율"], "2026_당락": x["2026_당락"],
        "2026_사전투표율": x["사전투표율"], "2026_당일투표율": x["당일투표율"],
        "계열추정": ky, "근거": f"{why} / {title} {url}", "매칭확신도": x["매칭확신도"],
    })
# (A) 2026 무소속 당선자 중 위 표에 없는 사람 추가
seen = {(r["시군구"], r["후보명"]) for r in rows}
turn = {}
tp = ROOT / "data" / "live_counting" / "turnout_party.json"
for p in json.loads(tp.read_text(encoding="utf-8"))["points"]:
    turn[(p["sd"], p["sgg"])] = (p["early"], p["day"])
SD_NORM = {"전라북도": "전북특별자치도", "강원도": "강원특별자치도"}
for x in d["무소속당선"]["2026"]:
    if (x["시군구"], x["후보명"]) in seen:
        continue
    ky, why, title, url = KYE.get(x["후보명"], ("불명", "근거 미확보", "—", "—"))
    e, day = turn.get((SD_NORM.get(x["시도"], x["시도"]), x["시군구"]), (None, None))
    rows.append({
        "권역": x["권역"], "시도": x["시도"], "시군구": x["시군구"], "후보명": x["후보명"],
        "2022_정당": "", "2022_득표율": "", "2022_당락": "",
        "2026_정당": "무소속", "2026_득표율": x["득표율"], "2026_당락": "당선",
        "2026_사전투표율": e, "2026_당일투표율": day,
        "계열추정": ky, "근거": f"{why} / {title} {url}", "매칭확신도": "상(2026 무소속 당선·웹확인)",
    })

rows.sort(key=lambda r: ({"호남": 0, "영남": 1, "기타": 2}[r["권역"]], r["시도"], r["시군구"]))
cols = ["권역", "시도", "시군구", "후보명", "2022_정당", "2022_득표율", "2022_당락",
        "2026_정당", "2026_득표율", "2026_당락", "2026_사전투표율", "2026_당일투표율",
        "계열추정", "근거", "매칭확신도"]
with (R / "independent_heads_final.csv").open("w", encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=cols)
    w.writeheader()
    w.writerows(rows)

# 마크다운 표
md = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
for r in rows:
    md.append("| " + " | ".join(str(r[c]) if r[c] is not None else "" for c in cols) + " |")
(R / "independent_heads_table.md").write_text("\n".join(md), encoding="utf-8")

print(f"행 {len(rows)} → independent_heads_final.csv · independent_heads_table.md")
print("\n[계열 분포]")
print(" 정당변경+무소속 표 계열:", dict(Counter(r["계열추정"] for r in rows)))
print("\n[무소속 당선 권역 분포]")
for yr in ("2022", "2026"):
    rc = Counter(x["권역"] for x in d["무소속당선"][yr])
    print(f"  {yr}: 호남 {rc['호남']} 영남 {rc['영남']} 기타 {rc['기타']}")
