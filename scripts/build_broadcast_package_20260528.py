#!/usr/bin/env python3
"""
5월 28일 14시 데이터 방송용 시뮬레이션 패키지 빌드.

클로드가 원고 작성에 활용할 수 있도록 산출 과정·근거 자료·결과를
markdown + JSON + CSV로 정리.

산출물:
    exports/claude_simulation_broadcast_20260528_1400/
      README.md
      01_방법론.md
      02_시도지사_결과.md + .json + .csv
      03_기초단체장_결과.md + .json + .csv
      04_재보궐_결과.md + .json + .csv
      05_입력_데이터.md
      06_방송_활용_가이드.md
      summary_all.json     # 통합 데이터
      __zip__/...zip       # 통째로 묶은 zip
"""

from __future__ import annotations

import csv
import json
import shutil
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXP = ROOT / "exports"
OUT = EXP / "claude_simulation_broadcast_20260528_1400"


def load_json(p: Path):
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def write(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    print(f"  · {path.relative_to(ROOT)}")


def write_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"  · {path.relative_to(ROOT)}")


def copy(src: Path, dst: Path):
    if src.exists():
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
        print(f"  · {dst.relative_to(ROOT)}")


def fmt_seat(mode_or_result, unit="곳"):
    m = mode_or_result
    if "dem_mode" in m:
        d_mode, c_mode = m["dem_mode"], m["con_mode"]
        d_ci, c_ci = m["dem_80_ci"], m["con_80_ci"]
    else:
        d_mode, c_mode = m.get("dem_mode_seats"), m.get("con_mode_seats")
        d_ci, c_ci = m.get("dem_80_ci"), m.get("con_80_ci")
    return f"민주당 **{d_mode}{unit}** (예상 범위 {d_ci[0]}~{d_ci[1]}{unit}) · " \
           f"국힘·무소속 등 **{c_mode}{unit}** (예상 범위 {c_ci[0]}~{c_ci[1]}{unit})"


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    print(f"=== {OUT.name} 빌드 ===")

    sido = load_json(EXP / "simulation_9th_sido" / "summary.json")
    bh = load_json(EXP / "simulation_9th_basic_head" / "summary.json")
    asm = load_json(EXP / "simulation_9th_assembly" / "summary.json")
    mbc = load_json(ROOT / "data" / "mbc_prior.json")

    # ============ README.md ============
    sido_mbc = sido.get("scenarios", {}).get("mbc", {})
    sido_shake = sido.get("scenarios", {}).get("shakeup", {})
    bh_shake = bh.get("scenarios", {}).get("shakeup", {})
    asm_result = asm.get("result", {})

    readme = f"""# 9회 전국동시지방선거 시뮬레이션 — 2시에 데이터 방송용 패키지

- **생성**: {datetime.now().isoformat(timespec='minutes')}
- **방송 시점**: 2026-05-28 14:00
- **분석 주체**: 시민언론 뉴탐사
- **사이트**: https://election2026.newtamsa.org/sim/
- **D-day**: 2026-06-03 (D-6)

## 한 문장 핵심

> 5/27까지 보도된 공개 여론조사와 과거 6회차(1995~2022) 개표결과를 입력으로 1만 회 시뮬레이션한 결과,
> **이재명 정부 출범 1년차** 환경 가정 시 **민주당이 광역단체장 11곳·기초단체장 다수·국회 재·보궐 11석 안팎**으로
> 우세할 수 있음. 다만 가정 자체에 불확실성이 크며 **예측·여론조사가 아닙니다**.

## 한 줄 결과 — 메인 시나리오

| 선거 | 결과 |
|---|---|
| **광역단체장** (16곳, 시도지사) | {fmt_seat(sido_mbc, '곳')} |
| **기초단체장** (226곳, 시군구청장) | {fmt_seat(bh_shake, '곳')} |
| **국회의원 재·보궐** (14석) | {fmt_seat(asm_result, '석')} |

> 광주·전남은 시도지사 한정 통합특별시로 처리해 16곳.
> 기초단체장은 시군구 단위 공개 여론조사가 부족해 과거 6회차 패턴만 사용 (정확도 ↓).

## 읽는 순서

1. `01_방법론.md` — 모델·시나리오·검증 (먼저 읽기)
2. `02_시도지사_결과.md` (+`.json` +`.csv`) — 16개 시도별 결과
3. `03_기초단체장_결과.md` (+`.json` +`.csv`) — 226곳 시군구별
4. `04_재보궐_결과.md` (+`.json` +`.csv`) — 14개 선거구별
5. `05_입력_데이터.md` — 데이터 출처·매핑·전처리
6. `06_방송_활용_가이드.md` — 원고에 쓸 표현·금지 표현·면책

## 클로드에게 (원고 작성 지침)

- 본 자료는 **여론조사·예측조사가 아닙니다.** "예측", "당선 확률 N%" 같은 단정 표현 금지.
  → "시뮬레이션 결과 N곳이 가장 자주 나왔다", "환경에 따라 N~M곳 사이로 갈렸다" 같은 표현 사용.
- 메인 시나리오는 "이재명 정부 출범 1년차" 환경 가정. **이 가정이 흔들리면 결과도 흔들림.**
  → 시청자에게 "환경 가정"임을 명확히 알릴 것.
- 후보 개별 이름을 단정적으로 거론하지 말 것. 시도·정당 단위로 추세를 말할 것.
- 공직선거법 108조에 따라 5/28부터 6/3 18:00까지 여론조사 공표·인용보도 금지.
  본 자료는 모델 출력이지만 **여론조사 결과 자체를 인용하면 위반.** 결과만 인용.
"""
    write(OUT / "README.md", readme)

    # ============ 01_방법론.md ============
    method = """# 방법론 — 모델·시나리오·검증

## 1. 모델 (계층 분해)

각 선거구의 양당 격차(margin = 민주당 진영 득표율 − 비민주당 진영 득표율)를
세 요소로 분해해서 시뮬레이션한다.

```
margin = 시대 효과(year_effect) + 지역 성향(region_lean) + 잡음(noise)
```

- **시대 효과**: 그 회차 전국 평균 — 시대 분위기 (보수 우세 시기 vs 진보 우세 시기)
- **지역 성향**: 그 시도(또는 시군구·선거구)가 전국 평균보다 얼마나 진보/보수 쪽으로 치우쳤나
- **잡음**: 같은 지역이라도 회차마다 변동 (외부 충격·후보 효과)

각 요소의 평균과 표준편차를 과거 회차 데이터에서 추정한 뒤,
9회 시뮬레이션 1만 회를 돌려 의석 분포를 산출한다.

## 2. 입력 데이터

### 2.1 과거 개표 결과 (모든 시뮬레이션의 베이스)

- **시도지사**: 1995~2022년 6회차 (3·4·5·6·7·8회 지방선거)
- **기초단체장**: 226곳 × 6회차
- **국회의원 재·보궐 (22대 결과)**: 2024-04-10 결과 (자료가 부족한 선거구의 보완용)
- 출처: 중앙선거관리위원회 선거통계시스템 OpenAPI

### 2.2 공개 여론조사 (시도지사·재·보궐만)

- **5월 27일까지 언론에 보도된 공개 여론조사**를 시뮬레이션 입력값으로 사용
- 광주·전남 통합특별시는 자료 부족 → 과거 패턴으로 보완
- 기초단체장은 시군구 단위 공개 여론조사가 충분치 않아 사용 안 함

## 3. 네 시나리오 (시도지사)

| 시나리오 | 가정 | 비고 |
|---|---|---|
| **현재 추세 (메인)** | 5/27까지 보도된 여론조사 입력 + 자료 없는 시도는 7회 환경 | **메인 시나리오** |
| **정권 출범 1년차** | 7회(2018, 박근혜 탄핵 후 문재인 정부 1년차)와 유사 환경 | 여론조사 미반영 과거 개표결과 패턴 |
| 혼합 환경 (참고) | 6회차 모두 무작위 추출 | 정치 환경 무관 평균 |
| 정권 안정기 (대안) | 5·6·8회처럼 평년 환경 | 현재와 거리 있는 대안 가설 |

## 4. 검증 (Leave-one-out 백테스트)

대상 회차를 제외하고 나머지 회차로 모델을 학습 → 그 회차 결과를 예측 → 실제와 비교.

| 대상 | 시도지사 적중률 | 기초단체장 적중률 |
|---|---|---|
| 6회 (2014, 평년) | 65% | — |
| 7회 (2018, 격변기) | 29% | 50% |
| 8회 (2022, 안정) | 88% | 81% |

→ **모델은 안정 환경에서 정확, 격변기에는 부정확.**
9회는 7회와 유사한 격변기일 가능성이 있어 신뢰구간을 보수적으로 봐야 함.

## 5. 매치업 정의

각 선거구의 매치업을 다음과 같이 정의한다.

### 5.1 시도지사·기초단체장 (양당 기반)
- 민주당 후보 vs 비민주당 후보 중 1위
- 비민주당 1위가 **국민의힘이면 빨강**, **무소속이면 회색**으로 색 구분
- 예: 전북 — 이원택(민주) vs 김관영(무소속)

### 5.2 국회의원 재·보궐 (진영 기반)
- 민주당 진영(더불어민주당·조국혁신당·진보당·정의당) 1위 vs
  비민주당 진영(국민의힘·자유와혁신·자유통일당·한동훈 보수계 무소속) 1위
- 예: 부산 북갑 — 하정우(민주) vs 한동훈(무소속, 보수계)
- 예: 평택을 — 김용남(민주) vs 유의동(국힘) (조국혁신당은 민주당 진영 2위)

## 6. 시뮬레이션 알고리즘

```python
for _ in range(10_000):
    year_eff = 시나리오에서 sampling
    for each 선거구:
        lean = Normal(region_mean, region_sd)
        noise = Normal(0, residual_sd)
        margin = year_eff + lean + noise
        winner = '민주당' if margin > 0 else '비민주당'
    count[winners 분포] += 1
```

## 7. 한계 (반드시 함께 보도)

- 과거 6회차 데이터 — 통계적 표본 적음
- 후보 개별 효과·현직 이점·정당 변동 미반영
- 사전투표 패턴 변화 미반영
- 외부 충격 (정치 사건, 경제 등) 미반영
- 메인 시나리오 가정 자체가 흔들리면 결과도 흔들림
- **예측이 아닌 과거 패턴 기반 시나리오**

## 8. 산출 도구

- 코드: `scripts/simulate_9th_sido.py` / `simulate_9th_basic_head.py` / `simulate_9th_assembly.py`
- 입력: `data/history_counting_results.json`, `data/mbc_prior.json`,
  `data/assembly_22nd_repoll_results.json`, `data/candidates/20260603/snapshot_*.json`
- 출력: `exports/simulation_9th_*/summary.json`, `*.csv`, `*.html`
- 사이트: https://election2026.newtamsa.org/sim/
"""
    write(OUT / "01_방법론.md", method)

    # ============ 02_시도지사 ============
    write_sido(sido, OUT, mbc)

    # ============ 03_기초단체장 ============
    write_basic_head(bh, OUT)

    # ============ 04_재보궐 ============
    write_assembly(asm, OUT)

    # ============ 05_입력 데이터 ============
    write_input_sources(OUT, mbc, sido)

    # ============ 06_방송 가이드 ============
    write_broadcast_guide(OUT)

    # ============ 통합 JSON ============
    summary_all = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "broadcast_at": "2026-05-28T14:00:00+09:00",
        "sido_summary": sido.get("scenarios", {}).get("mbc", {}),
        "basic_head_summary": bh.get("scenarios", {}).get("shakeup", {}),
        "assembly_summary": asm.get("result", {}),
        "mbc_prior_sources": mbc.get("sido_prior", {}),
    }
    write_json(OUT / "summary_all.json", summary_all)

    # ============ CSV 통합 ============
    copy(EXP / "simulation_9th_sido" / "summary.json", OUT / "_raw" / "simulation_9th_sido_summary.json")
    copy(EXP / "simulation_9th_basic_head" / "summary.json", OUT / "_raw" / "simulation_9th_basic_head_summary.json")
    copy(EXP / "simulation_9th_assembly" / "summary.json", OUT / "_raw" / "simulation_9th_assembly_summary.json")
    copy(EXP / "simulation_9th_sido" / "sido_marginal.csv", OUT / "_raw" / "sido_marginal.csv")
    copy(EXP / "simulation_9th_basic_head" / "sigungu_marginal.csv", OUT / "_raw" / "sigungu_marginal.csv")
    copy(EXP / "simulation_9th_sido" / "seat_distribution.csv", OUT / "_raw" / "sido_seat_distribution.csv")
    copy(EXP / "simulation_9th_basic_head" / "seat_distribution.csv", OUT / "_raw" / "basic_head_seat_distribution.csv")
    copy(EXP / "simulation_9th_assembly" / "seat_distribution.csv", OUT / "_raw" / "assembly_seat_distribution.csv")

    # ============ ZIP ============
    zip_path = OUT.parent / f"{OUT.name}.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in OUT.rglob("*"):
            if p.is_file():
                zf.write(p, p.relative_to(OUT.parent))
    print(f"\nZIP 저장: {zip_path.relative_to(ROOT)} ({zip_path.stat().st_size:,} bytes)")


def write_sido(sido, OUT, mbc):
    sc_mbc = sido.get("scenarios", {}).get("mbc", {})
    sc_shake = sido.get("scenarios", {}).get("shakeup", {})
    prior = mbc.get("sido_prior", {})

    # 시도별 매치업
    sido_rows = []
    for s, info in prior.items():
        win = "민주당" if info["margin"] > 0 else (info["con_party"] or "비민주당")
        sido_rows.append({
            "시도": s,
            "민주당 후보": info["dem_candidate"],
            "민주당 지지율(%)": info["dem_share"],
            "비민주당 1위 후보": info["con_candidate"],
            "비민주당 1위 정당": info["con_party"],
            "비민주당 1위 지지율(%)": info["con_share"],
            "격차(%p)": info["margin"],
            "추정 우세": win,
        })
    sido_rows.sort(key=lambda x: -x["격차(%p)"])

    md_rows = []
    for r in sido_rows:
        md_rows.append(
            f"| {r['시도']} | {r['민주당 후보']} ({r['민주당 지지율(%)']}%) | "
            f"{r['비민주당 1위 후보']} ({r['비민주당 1위 정당']}, {r['비민주당 1위 지지율(%)']}%) | "
            f"{r['격차(%p)']:+.1f}%p | {r['추정 우세']} |"
        )

    # 광주·전남·경북·충북은 자료 부족
    missing = [s for s in ["전남광주통합특별시", "경상북도", "충청북도"] if s not in prior]
    missing_note = ""
    if missing:
        missing_note = f"\n> ⚠️ 다음 시도는 공개 여론조사 자료 부족 — 7회(2018) 환경 가정으로 보완: {', '.join(missing)}\n"

    md = f"""# 시도지사 (광역단체장) 16곳 시뮬레이션 결과

## 결과 한 줄

**메인 시나리오 (현재 추세 반영)**
- 민주당 **{sc_mbc.get('dem_mode')}곳** (예상 범위 {sc_mbc.get('dem_80_ci',[0,0])[0]}~{sc_mbc.get('dem_80_ci',[0,0])[1]}곳)
- 국힘·무소속 등 **{sc_mbc.get('con_mode')}곳** (예상 범위 {sc_mbc.get('con_80_ci',[0,0])[0]}~{sc_mbc.get('con_80_ci',[0,0])[1]}곳)

**과거 개표결과 패턴만 (정권 출범 1년차 환경 가정)**
- 민주당 **{sc_shake.get('dem_mode')}곳** (예상 범위 {sc_shake.get('dem_80_ci',[0,0])[0]}~{sc_shake.get('dem_80_ci',[0,0])[1]}곳)
- 국힘·무소속 등 **{sc_shake.get('con_mode')}곳** (예상 범위 {sc_shake.get('con_80_ci',[0,0])[0]}~{sc_shake.get('con_80_ci',[0,0])[1]}곳)

## 두 시나리오가 모두 같은 결론을 시사하는 곳

→ 광주·전남·전북·세종·경기 등 진보 강세 지역과 대구·경북 등 보수 강세 지역.

## 두 시나리오의 차이가 큰 곳 (격전지)

→ 서울·인천·강원·충북·충남·경남 등 변동성 큰 지역.
{missing_note}
## 시도별 매치업 (5/27 공개 여론조사 기준 — 자료 있는 13개 시도)

| 시도 | 민주당 후보 | 비민주당 1위 후보 | 격차 | 추정 우세 |
|---|---|---|---|---|
{chr(10).join(md_rows)}

## 산출 과정

1. **과거 6회차(1995~2022) 광역단체장 결과**에서 시도별 평균 격차와 표준편차 추정
2. **5/27까지 보도된 시도별 여론조사**를 입력값으로 사용 (자료 있는 13개)
3. 자료 없는 3개 시도는 **7회 정권 출범 1년차 환경**으로 보완
4. 각 시뮬레이션 1회마다 시도별 격차를 정규분포에서 sampling → 양당 승자 결정
5. 1만 회 반복 → 의석 분포 산출

## 검증 (Leave-one-out 백테스트)

8회(2022) 시뮬레이션 적중률: **15/17 (88%)** — 안정 환경에서 모델 신뢰도 ↑.
7회(2018) 적중률: 5/17 (29%) — 격변기에는 모델 신뢰도 ↓.
9회는 7회와 유사한 격변기일 가능성, **결과는 보수적으로 봐야 함**.
"""
    write(OUT / "02_시도지사_결과.md", md)
    write_json(OUT / "02_시도지사_결과.json", {"scenarios": sido.get("scenarios", {}), "sido_matchup": sido_rows})

    with (OUT / "02_시도지사_결과.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(sido_rows[0].keys()))
        w.writeheader()
        w.writerows(sido_rows)
    print(f"  · {(OUT / '02_시도지사_결과.csv').relative_to(ROOT)}")


def write_basic_head(bh, OUT):
    sc_shake = bh.get("scenarios", {}).get("shakeup", {})
    sc_base = bh.get("scenarios", {}).get("baseline", {})
    sc_normal = bh.get("scenarios", {}).get("normal", {})

    # CSV: 시군구 marginal (이미 export에 있음 — 그대로 복사 메시지)
    md = f"""# 기초단체장 226곳 시뮬레이션 결과

## 결과 한 줄

**정권 출범 1년차 환경 가정 (메인)**
- 민주당 **{sc_shake.get('dem_mode')}곳** (예상 범위 {sc_shake.get('dem_80_ci',[0,0])[0]}~{sc_shake.get('dem_80_ci',[0,0])[1]}곳)
- 국힘·무소속 등 **{sc_shake.get('con_mode')}곳** (예상 범위 {sc_shake.get('con_80_ci',[0,0])[0]}~{sc_shake.get('con_80_ci',[0,0])[1]}곳)

**혼합 환경 (참고)**
- 민주당 {sc_base.get('dem_mode')}곳 (예상 범위 {sc_base.get('dem_80_ci',[0,0])[0]}~{sc_base.get('dem_80_ci',[0,0])[1]}곳)

**정권 안정기 (대안 가설)**
- 민주당 {sc_normal.get('dem_mode')}곳 (예상 범위 {sc_normal.get('dem_80_ci',[0,0])[0]}~{sc_normal.get('dem_80_ci',[0,0])[1]}곳)

→ 환경 가정에 따라 민주당 의석이 **{sc_normal.get('dem_mode')}곳에서 {sc_shake.get('dem_mode')}곳까지** 크게 다름.

## 한계 명시

- **시군구 226곳 단위 공개 여론조사는 자료 부족** → 시도지사·재보궐 시뮬과 달리 여론조사를 입력에 사용하지 못함
- 과거 6회차 개표 패턴만 사용
- 후보 개별 효과·현직 이점·지역 토호 영향 미반영 → **시도지사 시뮬보다 정확도 낮음**

## 산출 과정

1. 과거 6회차(1995~2022) 기초단체장 결과에서 시군구별 평균 격차·표준편차 추정
2. 시나리오별 시대 효과 sampling (7회 환경·6회 평균·평년 환경)
3. 1만 회 시뮬레이션 → 의석 분포 산출

## 검증 (Leave-one-out 백테스트)

- 8회(2022) 시뮬레이션 적중률: **177/219 (81%)** — 안정 환경에서 모델 신뢰도 ↑
- 7회(2018) 적중률: 114/226 (50%) — 격변기 절반 적중

## 시군구별 상세

`03_기초단체장_시군구별.csv`에서 226곳 전체 마진 확률 확인 가능.
"""
    write(OUT / "03_기초단체장_결과.md", md)
    write_json(OUT / "03_기초단체장_결과.json", {"scenarios": bh.get("scenarios", {})})
    # marginal csv 복사
    src = ROOT / "exports" / "simulation_9th_basic_head" / "sigungu_marginal.csv"
    copy(src, OUT / "03_기초단체장_시군구별.csv")


def write_assembly(asm, OUT):
    r = asm.get("result", {})
    races = asm.get("races", [])
    races_sorted = sorted(races, key=lambda x: -x.get("margin", 0))

    md_rows = []
    for p in races_sorted:
        d_name = p["dem"]["name"]
        d_party = p["dem"]["party"]
        d_mean = p["dem"]["mean"]
        c_name = p["con"]["name"]
        c_party = p["con"]["party"]
        c_mean = p["con"]["mean"]
        d_mean_s = f"{d_mean}%" if d_mean is not None else "자료 부족"
        c_mean_s = f"{c_mean}%" if c_mean is not None else "자료 부족"
        prob_d = r.get("race_dem_prob", {}).get(p["consti"], 0) * 100
        win = "민주당" if p["margin"] > 0 else c_party
        fb = " (22대 결과 보완)" if p.get("fallback") else ""
        md_rows.append(
            f"| {p['region1']} {p['region2']}{fb} | "
            f"{d_name} ({d_party}, {d_mean_s}) | "
            f"{c_name} ({c_party}, {c_mean_s}) | "
            f"{p['margin']:+.1f}%p | {prob_d:.0f}% | {win} |"
        )

    md = f"""# 국회의원 재·보궐 14개 선거구 시뮬레이션 결과

## 결과 한 줄

- 민주당 **{r.get('dem_mode')}석** (예상 범위 {r.get('dem_80_ci',[0,0])[0]}~{r.get('dem_80_ci',[0,0])[1]}석)
- 국힘·무소속 등 **{r.get('con_mode')}석** (예상 범위 {r.get('con_80_ci',[0,0])[0]}~{r.get('con_80_ci',[0,0])[1]}석)

## 핵심 변수 — 진영 매치업

매치업은 **민주당 진영 1위 vs 비민주당 진영 1위**.
- 민주당 진영: 더불어민주당·조국혁신당·진보당·정의당
- 비민주당 진영: 국민의힘·자유와혁신·자유통일당 + 한동훈(보수계 무소속)

### 특이 케이스

- **부산 북갑** — 한동훈(무소속, 보수계)이 39.3%로 1위. 박민식(국힘)이 아닌 한동훈이 비민주당 1위로 잡힘.
- **경기 평택을** — 조국(조국혁신당) 25.2%는 민주당 진영 2위. 비민주당 1위는 유의동(국힘) 21.2%.
- **전북 군산김제부안 갑/을** — 자료 부족 → 22대 결과로 보완. 9회 후보는 김의겸·박지원 등.

## 14개 선거구별 매치업

| 선거구 | 민주당 진영 1위 | 비민주당 진영 1위 | 격차 | 민주당 승리 확률 | 추정 우세 |
|---|---|---|---|---|---|
{chr(10).join(md_rows)}

## 산출 과정

1. **5/27까지 보도된 선거구별 공개 여론조사**를 입력값으로 사용
2. 보도 시점·여론조사 신뢰구간 반영. 자료 부족한 선거구는 22대 결과 보완
3. 진영 분류 — 정당명 기반 매핑 + 한동훈(무소속) 같은 보수계 명시
4. 1만 회 시뮬레이션 → 의석 분포 산출

## 경합 선거구 (확률 30~70%)

- 충남 공주부여청양 (민주당 56%) — 김영빈 vs 윤용근, 격차 +2.4%p
- 울산 남갑 (민주당 41%) — 전태진 vs 김태규, 격차 -2.2%p
- 부산 북갑 (민주당 ~30%) — 하정우 vs 한동훈, 격차 -3.2%p

→ **이 3곳이 의석 분포의 핵심 변동 요인.**

## 한계

- 14개 선거구 각각 표본 적음
- 자료 부족 선거구(6곳)는 22대 결과 + 9회 후보로 보완
- 현직 이점·후보 효과·정당 변동 미반영
"""
    write(OUT / "04_재보궐_결과.md", md)
    write_json(OUT / "04_재보궐_결과.json", {"result": r, "races": races})

    with (OUT / "04_재보궐_결과.csv").open("w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["시도", "선거구", "민주당 후보", "민주당 정당", "민주당 mean(%)", "비민주당 후보", "비민주당 정당", "비민주당 mean(%)", "격차(%p)", "민주당 승리 확률(%)", "MBC 분류"])
        for p in races_sorted:
            prob_d = r.get("race_dem_prob", {}).get(p["consti"], 0) * 100
            w.writerow([
                p["region1"], p["region2"],
                p["dem"]["name"], p["dem"]["party"], p["dem"]["mean"] if p["dem"]["mean"] is not None else "자료부족",
                p["con"]["name"], p["con"]["party"], p["con"]["mean"] if p["con"]["mean"] is not None else "자료부족",
                p["margin"], round(prob_d, 1), p.get("state_label", ""),
            ])
    print(f"  · {(OUT / '04_재보궐_결과.csv').relative_to(ROOT)}")


def write_input_sources(OUT, mbc, sido):
    md = """# 입력 데이터 — 출처·매핑·전처리

## 1. 과거 개표결과 (모든 시뮬의 베이스)

- 출처: 중앙선거관리위원회 선거통계시스템 OpenAPI
  - `VoteXmntckInfoInqireService2/getXmntckSttusInfoInqire`
  - `apis.data.go.kr/9760000/...`
- 회차: 제3회(2002) ~ 제8회(2022) 전국동시지방선거
- 단위: 시도지사·기초단체장·시도의원·구시군의회의원·교육감
- 22대 국회의원선거(2024): 재·보궐 14개 선거구 보완용

## 2. 공개 여론조사 (시도지사·재·보궐 시뮬의 입력)

- **2026년 5월 27일까지 언론에 보도된 공개 여론조사**
- 베이지안 상태공간 모형으로 통합 추정한 후보별 지지율
- 본 패키지의 시뮬레이션에서는 모델의 입력 변수로만 사용
- 여론조사 결과 자체를 인용·공표하지 않음
- 5/28 이후 추가 여론조사는 공직선거법 108조에 의해 미반영

## 3. 9회 후보 명단

- 출처: 중앙선거관리위원회 OpenAPI 후보자 정보
- 우리 사이트(election2026.newtamsa.org)가 매일 03:15 KST 자동 갱신
- 본 패키지는 2026-05-27 스냅샷 사용

## 4. 정당 진영 매핑

### 진보 진영
- 더불어민주당
- 조국혁신당
- 진보당
- 정의당
- 기본소득당
- 녹색당
- 무소속(보수계 명시 외 진보계로 알려진 인물 — 케이스별 명시)

### 보수 진영
- 국민의힘
- 자유와혁신
- 자유통일당
- 공화당
- 대한국민당
- 무소속 한동훈(보수계 무소속, 부산 북갑)

### 기타
- 개혁신당 (중도, 매치업 제외)
- 무소속 김관영(전북 시도지사) — 민주당 출신이지만 무소속 출마, 본 분석에서는 "비민주당" 카테고리

## 5. 데이터 전처리

### 시도명 정규화 (옛→신)
- 강원도 → 강원특별자치도
- 전라북도 → 전북특별자치도
- 제주도 → 제주특별자치도
- **광주광역시 + 전라남도 → 전남광주통합특별시** (시도지사 한정)

### 한 회차에 같은 시도(통합특별시)에 두 값이 있을 경우
- 광주·전남이 분리된 회차의 격차를 평균해서 통합특별시 값으로

## 6. 13개 시도 여론조사 prior 요약 (5/27 기준)
"""
    md += "\n| 시도 | 민주당 후보 | 지지율 | 비민주당 1위 | 정당 | 지지율 | 격차 |\n|---|---|---|---|---|---|---|\n"
    for s, p in mbc.get("sido_prior", {}).items():
        md += f"| {s} | {p['dem_candidate']} | {p['dem_share']}% | {p['con_candidate']} | {p['con_party']} | {p['con_share']}% | {p['margin']:+.1f}%p |\n"

    write(OUT / "05_입력_데이터.md", md)


def write_broadcast_guide(OUT):
    md = """# 방송 활용 가이드 (원고 작성자 용)

## 핵심 메시지 한 줄

> "5월 27일까지 보도된 여론조사와 과거 6회차 개표결과를 입력으로 한 시뮬레이션 결과,
> 이재명 정부 출범 1년차 환경 가정 시 민주당이 광역단체장 11곳·기초단체장 다수·국회 재·보궐 11석 안팎으로 우세."

## 허용 표현 (사용해도 OK)

- "시뮬레이션 결과 ~이 가장 자주 나왔다"
- "환경 가정에 따라 ~곳에서 ~곳까지 갈렸다"
- "과거 패턴을 보면 ~"
- "여론조사 흐름을 시뮬레이션에 입력했더니 ~"
- "8회 같은 안정 환경에선 모델이 88% 적중"
- "7회 같은 격변기에선 절반 정도만 적중 — 결과는 보수적으로"

## 금지 표현 (절대 사용 금지)

- "예측" — 본 자료는 예측이 아니라 패턴 시나리오
- "당선 확률 N%" — 시뮬레이션 출력이지 후보별 당락 확률 아님
- "여론조사 결과 ~" — 인용보도가 됨, 공직선거법 108조 위반
- "이번 선거에서 ~할 것" — 단정 표현 금지
- 특정 후보 이름을 결과와 함께 단정적으로 거론

## 시청자에게 명확히 전할 것

1. **여론조사·예측조사가 아님** — 시뮬레이션 출력
2. **메인 시나리오는 가정** — "이재명 정부 출범 1년차" 환경
3. **격변기에는 모델 신뢰도 ↓** — 백테스트 7회 29% 적중
4. **외부 변수 미반영** — 사전투표, 후보 효과, 정치 사건
5. 인용·재가공 시 위 한계를 함께 표기

## 추천 방송 흐름

### 1. 도입 (1분)
"5/27까지 보도된 공개 여론조사와 과거 8회 지방선거(1995~2022) 개표결과를
컴퓨터에 1만 번 돌려서 9회 의석 분포를 그려봤다. 예측이 아니라 시나리오다."

### 2. 광역단체장 16곳 (2분)
"메인 시나리오에선 민주당이 11곳 안팎. 광주·전남 통합·전북·세종·경기 등은 거의 확정.
서울·인천·강원·충북·충남·경남은 격전. 대구·경북은 국힘 우세."

### 3. 특이 케이스 (1.5분)
"전북은 무소속 김관영 후보가 1위. 부산 북갑은 한동훈 무소속이 1위."

### 4. 국회 재·보궐 14석 (1.5분)
"민주당 진영 11석 안팎. 충남 공주부여청양·울산 남갑·부산 북갑이 경합."

### 5. 마무리 (30초)
"여러 번 강조하지만 예측이 아니라 시뮬레이션. 환경 가정이 흔들리면 결과도 흔들린다.
6/3 18시 이후 개표가 시작되면 실제 결과를 같이 확인해보자."

## 공직선거법 108조 주의

5/28부터 6/3 18:00까지 여론조사·예측조사 공표·인용보도 금지.
- 시뮬레이션 결과는 자체 모델 출력이라 공표 가능 (운영자 법적 판단)
- 다만 "여론조사 결과" 자체를 인용하면 위반
- 본 자료의 표·숫자만 인용. "MBC 여론조사에서 ~%" 같은 직접 인용 금지

## 후속 자료

- 사이트: https://election2026.newtamsa.org/sim/
- 시도지사: /sim/sido/
- 기초단체장: /sim/basic-head/
- 재·보궐: /sim/assembly/
- 실시간 개표 (6/3 18시 이후): /#live
"""
    write(OUT / "06_방송_활용_가이드.md", md)


if __name__ == "__main__":
    main()
