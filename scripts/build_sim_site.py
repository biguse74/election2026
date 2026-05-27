#!/usr/bin/env python3
"""
exports/simulation_*/ 결과를 site root의 /sim/ 폴더로 빌드.

· /sim/index.html           — 두 시뮬 진입 랜딩
· /sim/sido/index.html      — 시도지사 시뮬 (게이트 포함)
· /sim/basic-head/index.html — 기초단체장 시뮬 (게이트 포함)
· /sim/_gate.js             — 공직선거법 108조 게이트 (6/3 18:00 KST 전 콘텐츠 숨김)

게이트 미리보기 우회: URL에 ?preview=newtamsa-2026 추가.

사용:
    python scripts/build_sim_site.py
"""

from __future__ import annotations

import re
import shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
EXPORTS = ROOT / "exports"
SIM_ROOT = ROOT / "sim"

# 게이트는 제거하고 면책 박스로 대체.
# 이 자료는 여론조사·예측조사가 아닌 과거 개표결과 기반 시뮬레이션이므로
# 공직선거법 108조의 직접 적용 대상이 아니라는 게 운영자(뉴탐사)의 법적 판단.
# 다만 만약을 위해 면책 박스로 분쟁 시 방어 근거 확보 + robots.txt로 검색엔진 차단 유지.

DISCLAIMER_HTML = """<div style="max-width:880px;margin:0 auto 20px;padding:14px 18px;background:#fdecea;border-left:4px solid #c41e3a;border-radius:4px;font-family:-apple-system,'Pretendard',sans-serif;font-size:0.86rem;color:#1a1a1a;line-height:1.6">
  <strong style="color:#b3261e;display:block;margin-bottom:4px;font-size:0.92rem">⚠️ 자료의 성격 안내 · 반드시 읽어주세요</strong>
  · 본 자료는 <strong>여론조사·예측조사 결과가 아닙니다</strong>. 과거 개표결과와 <strong>2026년 5월 27일까지 언론에 보도된 공개 여론조사</strong>를 입력으로 한 시뮬레이션의 출력 분포입니다.<br>
  · 특정 후보·정당의 당락을 <strong>단정하지 않습니다</strong>. 환경에 따른 시나리오별 의석 분포를 보여주는 패턴 자료입니다.<br>
  · 메인 시나리오는 <strong>"이재명 정부 출범 1년차"</strong> 가정 + (시도지사·재보궐의 경우) 5월 27일까지 보도된 여론조사 추정치 prior.<br>
  · 외부 충격·후보 효과·정당 변동·사전투표 패턴 변화 등은 미반영. 모델 잡음 SD를 보수적으로 둠.<br>
  · 인용·재가공 시 위 한계를 반드시 함께 표기해 주십시오. 보도된 여론조사 prior 사용은 모델 내부 변수이며 여론조사 인용보도가 아닙니다.
</div>
"""


def inject_disclaimer(html: str) -> str:
    """본문 <body> 직후에 면책 박스 삽입. 기존 페이지의 .legal 박스는 그대로 유지."""
    body_open = re.search(r"<body[^>]*>", html)
    if not body_open:
        return html
    start = body_open.end()
    return html[:start] + "\n" + DISCLAIMER_HTML + "\n" + html[start:]


def build_sub_page(src: Path, dst: Path, title: str):
    src_html = src.read_text(encoding="utf-8")
    new_html = inject_disclaimer(src_html)
    # 기존 페이지에 있던 '6/3 18시 전 금지' 빨간 박스는 제거 (이제 즉시 공개)
    new_html = re.sub(
        r'<div class="legal">.*?</div>',
        "",
        new_html,
        count=1,
        flags=re.DOTALL,
    )
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text(new_html, encoding="utf-8")
    print(f"  · {dst.relative_to(ROOT)}")


def build_landing() -> str:
    return """<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>9회 지방선거 시뮬레이션 — 뉴탐사</title>
<style>
body { font-family: -apple-system, 'Pretendard', sans-serif; max-width: 900px; margin: 0 auto; padding: 28px 24px; color: #1a1a1a; line-height: 1.55; }
h1 { font-size: 1.6rem; margin: 0 0 8px; }
.sub { color: #666; font-size: 0.9rem; margin: 0 0 24px; }
.cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: 14px; }
@media (max-width: 900px) { .cards { grid-template-columns: 1fr 1fr; } }
@media (max-width: 640px) { .cards { grid-template-columns: 1fr; } }
.card { display: block; padding: 20px 22px; border: 1px solid #ddd; border-radius: 10px; text-decoration: none; color: inherit; background: #fff; transition: all 0.15s; }
.card:hover { border-color: #1a1a1a; box-shadow: 0 4px 12px rgba(0,0,0,0.06); transform: translateY(-1px); }
.card-title { font-size: 1.15rem; font-weight: 800; margin: 0 0 6px; }
.card-sub { color: #555; font-size: 0.88rem; margin: 0 0 10px; }
.card-meta { color: #999; font-size: 0.78rem; }
.intro { background: #fff8e3; border-left: 4px solid #b8860b; padding: 14px 18px; margin: 22px 0; border-radius: 4px; font-size: 0.88rem; }
.intro strong { color: #8b6500; }
</style></head><body>

""" + DISCLAIMER_HTML + """

<h1>9회 전국동시지방선거 의석 시뮬레이션</h1>
<p class="sub">2026-05-27 작성 · 과거 6회차(3~8회) 개표결과 기반 몬테카를로 1만회 · 시민언론 뉴탐사</p>

<div class="intro">
  <strong>읽는 법</strong> — 정치 환경에 따라 결과가 크게 달라지므로 세 시나리오(혼합·평년·정권심판)로 분리해 보여줍니다.
  단일 예측이 아닙니다. 모델 한계는 각 페이지 하단의 "모델 한계" 섹션에 명시.
</div>

<div class="cards">
  <a class="card" href="/sim/sido/">
    <div class="card-title">시도지사 17석</div>
    <p class="card-sub">광역단체장 17개 시도. 공개 여론조사 + 역사 패턴.</p>
    <div class="card-meta">8회 백테스트 88%</div>
  </a>
  <a class="card" href="/sim/basic-head/">
    <div class="card-title">기초단체장 226석</div>
    <p class="card-sub">시군구 기초단체장. 17개 시도별 모든 시군구.</p>
    <div class="card-meta">8회 백테스트 81%</div>
  </a>
  <a class="card" href="/sim/assembly/">
    <div class="card-title">국회의원 재·보궐 14석</div>
    <p class="card-sub">6/3 동시 재보궐 14개 선거구. 보도된 여론조사 추정치 + 22대 fallback.</p>
    <div class="card-meta">언론 보도 기반 · 정량 검증 안 됨</div>
  </a>
</div>

<p style="text-align:center;color:#aaa;font-size:0.75rem;margin-top:40px">시민언론 뉴탐사 · election2026.newtamsa.org</p>

</body></html>
"""


def main():
    SIM_ROOT.mkdir(parents=True, exist_ok=True)
    print("=== sim/ 빌드 ===")

    # 이전 빌드의 게이트 JS는 제거 (이제 즉시 공개)
    gate_js_path = SIM_ROOT / "_gate.js"
    if gate_js_path.exists():
        gate_js_path.unlink()
        print(f"  · {gate_js_path.relative_to(ROOT)} (제거)")

    # robots.txt — sim/ 디렉터리 검색엔진 차단 유지 (카톡·구글 미리보기 사고 방지)
    robots = ROOT / "robots.txt"
    if not robots.exists():
        robots.write_text("User-agent: *\nDisallow: /sim/\n", encoding="utf-8")
        print(f"  · {robots.relative_to(ROOT)} (신규)")
    else:
        cur = robots.read_text(encoding="utf-8")
        if "/sim/" not in cur:
            cur = cur.rstrip() + "\nDisallow: /sim/\n"
            robots.write_text(cur, encoding="utf-8")
            print(f"  · {robots.relative_to(ROOT)} (갱신)")

    # 세 시뮬레이션 페이지 (exports 결과를 disclaimer wrap)
    pages = [
        ("시도지사", "sido", "simulation_9th_sido"),
        ("기초단체장", "basic-head", "simulation_9th_basic_head"),
        ("국회의원 재·보궐", "assembly", "simulation_9th_assembly"),
    ]
    for title, dst_name, exp_name in pages:
        src = EXPORTS / exp_name / "index.html"
        if src.exists():
            build_sub_page(src, SIM_ROOT / dst_name / "index.html", title)
        else:
            print(f"  ! {src.relative_to(ROOT)} 없음")

    # 랜딩
    (SIM_ROOT / "index.html").write_text(build_landing(), encoding="utf-8")
    print(f"  · {(SIM_ROOT / 'index.html').relative_to(ROOT)}")

    # noindex meta — 두 sub 페이지에도 추가
    for p in [SIM_ROOT / "sido" / "index.html", SIM_ROOT / "basic-head" / "index.html"]:
        if not p.exists():
            continue
        html = p.read_text(encoding="utf-8")
        if '<meta name="robots"' not in html:
            html = html.replace("<head>", '<head>\n<meta name="robots" content="noindex,nofollow">', 1)
            p.write_text(html, encoding="utf-8")

    print("\n사이트 통합 완료. 공개 URL (게이트 해제됨):")
    print("  https://election2026.newtamsa.org/sim/")
    print("  https://election2026.newtamsa.org/sim/sido/")
    print("  https://election2026.newtamsa.org/sim/basic-head/")


if __name__ == "__main__":
    main()
