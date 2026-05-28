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


def header_html(current: str = "") -> str:
    """sim/ 페이지 공통 상단 헤더. current= 'home'·'sido'·'basic-head'·'assembly' 활성 표시."""
    def link(href, key, label):
        active = ' aria-current="page"' if current == key else ""
        cls = "sim-nav-link sim-nav-link-active" if current == key else "sim-nav-link"
        return f'<a class="{cls}" href="{href}"{active}>{label}</a>'
    nav = "".join([
        link("/sim/", "home", "시뮬레이션 홈"),
        link("/sim/sido/", "sido", "시도지사 17"),
        link("/sim/basic-head/", "basic-head", "기초단체장 226"),
        link("/sim/assembly/", "assembly", "재·보궐 14"),
    ])
    return f"""
<header class="sim-header">
  <div class="sim-header-inner">
    <a href="https://election2026.newtamsa.org/" class="sim-brand">
      <span class="sim-brand-title">뉴탐사 · 6·3 선거 2026</span>
      <span class="sim-brand-sub">결과 예측 시뮬레이션</span>
    </a>
    <nav class="sim-nav">{nav}</nav>
    <a class="sim-live-link" href="https://election2026.newtamsa.org/#live">실시간 개표 →</a>
  </div>
</header>
<style>
  body {{ margin: 0 !important; padding: 0 !important; max-width: none !important; }}
  .sim-page {{ max-width: 1100px; margin: 0 auto; padding: 20px 24px 48px; }}
  .sim-header {{
    background: #1a1a1a; color: #fff; border-bottom: 3px solid #c41e3a;
    font-family: -apple-system, 'Pretendard', sans-serif;
  }}
  .sim-header-inner {{
    max-width: 1200px; margin: 0 auto; padding: 12px 24px;
    display: flex; align-items: center; gap: 20px; flex-wrap: wrap;
  }}
  .sim-brand {{
    color: #fff; text-decoration: none; display: flex; flex-direction: column; line-height: 1.2; margin-right: auto;
  }}
  .sim-brand-title {{ font-size: 1.05rem; font-weight: 800; letter-spacing: -0.01em; }}
  .sim-brand-sub {{ font-size: 0.78rem; color: #c41e3a; font-weight: 700; }}
  .sim-nav {{ display: flex; gap: 4px; flex-wrap: wrap; }}
  .sim-nav-link {{
    color: rgba(255,255,255,0.78); text-decoration: none; font-size: 0.86rem; font-weight: 600;
    padding: 6px 12px; border-radius: 999px; transition: background 0.15s, color 0.15s;
  }}
  .sim-nav-link:hover {{ background: rgba(255,255,255,0.08); color: #fff; }}
  .sim-nav-link-active {{ background: #c41e3a; color: #fff; }}
  .sim-live-link {{
    background: #c41e3a; color: #fff; text-decoration: none; padding: 7px 14px;
    border-radius: 6px; font-size: 0.84rem; font-weight: 700;
  }}
  .sim-live-link:hover {{ background: #a31628; }}
  @media (max-width: 720px) {{
    .sim-header-inner {{ padding: 10px 16px; gap: 10px; }}
    .sim-brand-title {{ font-size: 0.95rem; }}
    .sim-brand-sub {{ font-size: 0.72rem; }}
    .sim-nav-link {{ font-size: 0.78rem; padding: 5px 10px; }}
    .sim-live-link {{ padding: 6px 12px; font-size: 0.78rem; }}
    .sim-page {{ padding: 16px 16px 40px; }}
  }}
</style>
"""


DISCLAIMER_HTML = """<div style="max-width:880px;margin:0 auto 20px;padding:12px 16px;background:#fdecea;border-left:4px solid #c41e3a;border-radius:4px;font-family:-apple-system,'Pretendard',sans-serif;font-size:0.86rem;color:#1a1a1a;line-height:1.6">
  · 본 자료는 <strong>여론조사가 아닙니다.</strong> 과거 개표결과와 5월 27일까지 언론에 보도된 공개 여론조사를 입력으로 한 시뮬레이션 결과(시나리오별 분포)입니다.<br>
  · 특정 후보·정당의 당락을 <strong>단정하지 않습니다.</strong> 메인 시나리오는 "이재명 정부 출범 1년차(7회 문재인 정부 출범 직후와 유사한 환경)" 가정.<br>
  · 인용·재가공 시 위 한계를 함께 표기해 주십시오.
</div>
"""


def inject_header_and_disclaimer(html: str, current_key: str) -> str:
    """본문 <body> 직후에 sim 헤더 + 면책 박스 삽입.
    또 기존 페이지의 max-width container를 sim-page로 감싸기.
    """
    body_open = re.search(r"<body[^>]*>", html)
    body_close = html.rfind("</body>")
    if not body_open or body_close == -1:
        return html
    start = body_open.end()
    inner = html[start:body_close]
    new = (
        html[:start]
        + "\n"
        + header_html(current_key)
        + '\n<main class="sim-page">\n'
        + DISCLAIMER_HTML
        + "\n"
        + inner
        + "\n</main>\n"
        + html[body_close:]
    )
    return new


def build_sub_page(src: Path, dst: Path, title: str, current_key: str):
    src_html = src.read_text(encoding="utf-8")
    new_html = inject_header_and_disclaimer(src_html, current_key)
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


def _load_summary(name: str) -> dict:
    p = EXPORTS / name / "summary.json"
    if p.exists():
        try:
            import json as _j
            return _j.loads(p.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def _highlight(res: dict, unit: str = "곳") -> str:
    """summary.json에서 최빈값 + 80% 범위. 양당 균형 색상."""
    def fmt(d_mode, d_lo, d_hi, c_mode, c_lo, c_hi, unit, dlabel, clabel):
        return (
            f'<div style="display:flex;gap:14px;align-items:baseline;flex-wrap:wrap">'
            f'<div><span style="color:#152484;font-weight:700;font-size:0.78em">{dlabel}</span><br>'
            f'<strong style="color:#152484">{d_mode}{unit}</strong>'
            f'<span style="color:#666;font-size:0.78em"> ({d_lo}~{d_hi})</span></div>'
            f'<div style="color:#888">vs</div>'
            f'<div><span style="color:#E61E2B;font-weight:700;font-size:0.78em">{clabel}</span><br>'
            f'<strong style="color:#E61E2B">{c_mode}{unit}</strong>'
            f'<span style="color:#666;font-size:0.78em"> ({c_lo}~{c_hi})</span></div>'
            f'</div>'
        )

    if not res:
        return "—"
    sc = res.get("scenarios") or {}
    src = None
    if "mbc" in sc:
        src = sc["mbc"]
    elif "shakeup" in sc:
        src = sc["shakeup"]
    if src:
        return fmt(
            src.get("dem_mode", "?"),
            src.get("dem_80_ci", ["?", "?"])[0],
            src.get("dem_80_ci", ["?", "?"])[1],
            src.get("con_mode", "?"),
            src.get("con_80_ci", ["?", "?"])[0],
            src.get("con_80_ci", ["?", "?"])[1],
            unit, "민주당", "국힘·무소속 등",
        )
    r = res.get("result") or {}
    if r:
        return fmt(
            r.get("dem_mode", "?"),
            r.get("dem_80_ci", ["?", "?"])[0],
            r.get("dem_80_ci", ["?", "?"])[1],
            r.get("con_mode", "?"),
            r.get("con_80_ci", ["?", "?"])[0],
            r.get("con_80_ci", ["?", "?"])[1],
            unit, "민주당", "국힘·무소속 등",
        )
    return "—"


def build_landing() -> str:
    sido_s = _highlight(_load_summary("simulation_9th_sido"), "곳")
    bh_s = _highlight(_load_summary("simulation_9th_basic_head"), "곳")
    asm_s = _highlight(_load_summary("simulation_9th_assembly"), "석")

    return """<!doctype html>
<html lang="ko"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex,nofollow">
<title>9회 지방선거 결과 예측 시뮬레이션 — 뉴탐사</title>
<style>
:root { --ink: #1a1a1a; --accent: #c41e3a; --dem: #152484; --rule: #e0e0e0; }
* { box-sizing: border-box; }
body { font-family: -apple-system, 'Pretendard', sans-serif; margin: 0; color: var(--ink); line-height: 1.55; background: #fafafa; }
h1 { font-size: 1.7rem; margin: 0 0 6px; letter-spacing: -0.01em; }
.lead { color: #555; font-size: 0.95rem; margin: 0 0 8px; }
.meta { color: #888; font-size: 0.82rem; margin: 0 0 24px; }
.intro { background: #fff8e3; border-left: 4px solid #b8860b; padding: 14px 18px; margin: 20px 0; border-radius: 4px; font-size: 0.88rem; line-height: 1.6; }
.intro strong { color: #8b6500; }
.cards { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
@media (max-width: 900px) { .cards { grid-template-columns: 1fr 1fr; } }
@media (max-width: 640px) { .cards { grid-template-columns: 1fr; } }
.card {
  display: flex; flex-direction: column; padding: 20px 22px;
  border: 1px solid #ddd; border-radius: 12px; text-decoration: none;
  color: inherit; background: #fff; transition: all 0.18s;
}
.card:hover { border-color: var(--ink); box-shadow: 0 6px 20px rgba(0,0,0,0.08); transform: translateY(-2px); }
.card-tag { display: inline-block; font-size: 0.7rem; font-weight: 700; color: var(--accent); background: rgba(196,30,58,0.08); padding: 3px 9px; border-radius: 999px; align-self: flex-start; margin-bottom: 10px; }
.card-title { font-size: 1.2rem; font-weight: 800; margin: 0 0 4px; }
.card-count { font-size: 0.8rem; color: #888; margin: 0 0 12px; }
.card-result { font-size: 0.95rem; color: #1a1a1a; padding: 8px 0; border-top: 1px dashed #e8e8e8; border-bottom: 1px dashed #e8e8e8; margin: auto 0 12px; }
.card-result strong { font-size: 1.2rem; font-weight: 900; }
.card-sub { color: #666; font-size: 0.82rem; margin: 0; line-height: 1.5; }
.cta { display: flex; justify-content: space-between; gap: 12px; margin: 28px 0 12px; flex-wrap: wrap; }
.cta-btn { background: var(--ink); color: #fff; text-decoration: none; padding: 12px 20px; border-radius: 8px; font-weight: 700; font-size: 0.92rem; }
.cta-btn-accent { background: var(--accent); }
.cta-btn:hover { opacity: 0.9; }
footer { text-align: center; color: #aaa; font-size: 0.78rem; margin-top: 48px; padding-top: 24px; border-top: 1px solid #eee; }
</style></head><body>

""" + header_html("home") + """

<main class="sim-page">

""" + DISCLAIMER_HTML + """

<h1>9회 전국동시지방선거 결과 예측 시뮬레이션</h1>
<p class="lead">시도지사 17곳 · 기초단체장 226곳 · 국회의원 재·보궐 14석 — 정당별 당선 분포 시나리오.</p>
<p class="meta">2026-05-27 기준 · 과거 6회차 개표결과 + 2026-05-27까지 보도된 공개 여론조사 · 1만 회 몬테카를로 · 시민언론 뉴탐사</p>

<div class="intro">
  <strong>읽는 법</strong> — 정치 환경에 따라 결과가 크게 달라지므로 시나리오를 분리해 보여줍니다.
  메인 시나리오는 <strong>"이재명 정부 출범 1년차"</strong>(=7회 박근혜 탄핵 후 환경) 가정 + 보도된 공개 여론조사를 참고 자료로.
  특정 후보·정당의 당락을 단정하지 않습니다. 한계는 각 페이지 하단에 명시.
</div>

<div class="cards">
  <a class="card" href="/sim/sido/">
    <span class="card-tag">광역단체장</span>
    <div class="card-title">시도지사</div>
    <p class="card-count">17개 시도 · 1만 회 시뮬레이션</p>
    <div class="card-result">""" + sido_s + """</div>
    <p class="card-sub">공개 여론조사 + 6회차 과거 개표결과 패턴. 8회 백테스트 적중률 88%.</p>
  </a>
  <a class="card" href="/sim/basic-head/">
    <span class="card-tag">기초단체장</span>
    <div class="card-title">시군구청장</div>
    <p class="card-count">226곳 · 17개 시도별 모든 시군구</p>
    <div class="card-result">""" + bh_s + """</div>
    <p class="card-sub">시군구 단위 여론조사 부족 — 과거 개표결과 패턴만. 8회 백테스트 81%.</p>
  </a>
  <a class="card" href="/sim/assembly/">
    <span class="card-tag">국회의원 재·보궐</span>
    <div class="card-title">동시 재·보궐</div>
    <p class="card-count">14개 선거구 · 진영 1위 매치업</p>
    <div class="card-result">""" + asm_s + """</div>
    <p class="card-sub">보도된 여론조사 추정치 + 22대 결과 보완. 한동훈·조국 등 분류 포함.</p>
  </a>
</div>

<div class="cta">
  <a class="cta-btn cta-btn-accent" href="https://election2026.newtamsa.org/#live">6/3 실시간 개표 화면 →</a>
  <a class="cta-btn" href="https://election2026.newtamsa.org/">메인 사이트 · 출마자 데이터</a>
</div>

<footer>
  시민언론 뉴탐사 · election2026.newtamsa.org<br>
  자료 출처: 중앙선거관리위원회 개표결과·후보자 정보 / 2026-05-27까지 언론에 보도된 공개 여론조사
</footer>

</main>
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
            build_sub_page(src, SIM_ROOT / dst_name / "index.html", title, dst_name)
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
