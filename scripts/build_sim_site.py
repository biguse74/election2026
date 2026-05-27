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

RELEASE_ISO = "2026-06-03T18:00:00+09:00"
PREVIEW_TOKEN = "newtamsa-2026"


GATE_JS = """(function () {
  // 공직선거법 108조 — 6/3 18:00 KST 전엔 콘텐츠 숨김.
  // ?preview=newtamsa-2026 으로 운영자 검증 가능.
  var RELEASE_AT = Date.parse('""" + RELEASE_ISO + """');
  var params = new URLSearchParams(location.search);
  var preview = params.get('preview') === '""" + PREVIEW_TOKEN + """';
  var now = Date.now();
  var locked = now < RELEASE_AT && !preview;

  document.addEventListener('DOMContentLoaded', function () {
    var lock = document.getElementById('sim-gate-lock');
    var content = document.getElementById('sim-gate-content');
    if (!lock || !content) return;
    if (locked) {
      content.style.display = 'none';
      lock.style.display = 'block';
      var diff = RELEASE_AT - now;
      var d = Math.floor(diff / 86400000);
      var h = Math.floor((diff % 86400000) / 3600000);
      var m = Math.floor((diff % 3600000) / 60000);
      var label = document.getElementById('sim-gate-countdown');
      if (label) {
        if (d > 0) label.textContent = 'D-' + d + ' (' + d + '일 ' + h + '시간 ' + m + '분)';
        else if (h > 0) label.textContent = '' + h + '시간 ' + m + '분 후 공개';
        else label.textContent = m + '분 후 공개';
      }
    } else {
      lock.style.display = 'none';
      content.style.display = 'block';
      if (preview) {
        var banner = document.createElement('div');
        banner.style.cssText = 'background:#fff8e3;border-left:4px solid #b8860b;padding:8px 14px;margin-bottom:12px;font-size:0.82rem;color:#8b6500;font-weight:600';
        banner.textContent = '⚠️ 미리보기 모드 — 외부 공개 금지. 운영자 검증용만.';
        content.insertBefore(banner, content.firstChild);
      }
    }
  });
})();
"""


GATE_LOCK_HTML = """<div id="sim-gate-lock" style="display:none;max-width:760px;margin:80px auto;padding:36px 32px;border:1px solid #ddd;border-radius:10px;background:#fafafa;text-align:center;font-family:-apple-system,'Pretendard',sans-serif;color:#1a1a1a;line-height:1.6">
  <div style="font-size:0.85rem;color:#b3261e;font-weight:700;margin-bottom:8px;letter-spacing:0.04em">⚠️ 공직선거법 제108조</div>
  <h1 style="font-size:1.4rem;margin:0 0 14px">선거일 투표마감 이후에만 공개됩니다</h1>
  <p style="color:#555;margin:0 0 18px;font-size:0.92rem">
    공직선거법 제108조에 따라 선거 6일 전부터 투표마감 시각(2026-06-03 18:00 KST)까지는<br>
    여론조사·시뮬레이션 결과의 공표·인용보도가 금지됩니다.
  </p>
  <div style="display:inline-block;padding:10px 22px;background:#1a1a1a;color:#fff;border-radius:6px;font-weight:700;font-variant-numeric:tabular-nums">
    <span style="display:block;font-size:0.72rem;font-weight:400;opacity:0.7">공개까지</span>
    <span id="sim-gate-countdown" style="font-size:1.2rem">—</span>
  </div>
  <p style="color:#999;font-size:0.78rem;margin:18px 0 0">시민언론 뉴탐사 · 9회 전국동시지방선거 시뮬레이션</p>
</div>
"""


def inject_gate(html: str, page_title: str) -> str:
    """exports의 HTML에 게이트 wrapper 삽입.
    원본은 <body>...<h1>...</h1>...</body> 구조. body 직후에 lock, h1 부터 닫는 body까지를 content로 감싼다.
    """
    # <body> 직후 컨텐츠 시작 위치 찾기
    body_open = re.search(r"<body[^>]*>", html)
    body_close = html.rfind("</body>")
    if not body_open or body_close == -1:
        return html
    start = body_open.end()
    inner = html[start:body_close]
    new_inner = (
        GATE_LOCK_HTML
        + '\n<div id="sim-gate-content" style="display:none">\n'
        + inner
        + "\n</div>\n"
        + '<script src="/sim/_gate.js" defer></script>\n'
    )
    return html[:start] + new_inner + html[body_close:]


def build_sub_page(src: Path, dst: Path, title: str):
    src_html = src.read_text(encoding="utf-8")
    new_html = inject_gate(src_html, title)
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
.cards { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
@media (max-width: 640px) { .cards { grid-template-columns: 1fr; } }
.card { display: block; padding: 20px 22px; border: 1px solid #ddd; border-radius: 10px; text-decoration: none; color: inherit; background: #fff; transition: all 0.15s; }
.card:hover { border-color: #1a1a1a; box-shadow: 0 4px 12px rgba(0,0,0,0.06); transform: translateY(-1px); }
.card-title { font-size: 1.15rem; font-weight: 800; margin: 0 0 6px; }
.card-sub { color: #555; font-size: 0.88rem; margin: 0 0 10px; }
.card-meta { color: #999; font-size: 0.78rem; }
.intro { background: #fff8e3; border-left: 4px solid #b8860b; padding: 14px 18px; margin: 22px 0; border-radius: 4px; font-size: 0.88rem; }
.intro strong { color: #8b6500; }
</style></head><body>

""" + GATE_LOCK_HTML + """
<div id="sim-gate-content" style="display:none">

<h1>9회 전국동시지방선거 의석 시뮬레이션</h1>
<p class="sub">2026-05-27 작성 · 과거 6회차(3~8회) 개표결과 기반 몬테카를로 1만회 · 시민언론 뉴탐사</p>

<div class="intro">
  <strong>읽는 법</strong> — 정치 환경에 따라 결과가 크게 달라지므로 세 시나리오(혼합·평년·정권심판)로 분리해 보여줍니다.
  단일 예측이 아닙니다. 모델 한계는 각 페이지 하단의 "모델 한계" 섹션에 명시.
</div>

<div class="cards">
  <a class="card" href="/sim/sido/">
    <div class="card-title">시도지사 17석</div>
    <p class="card-sub">광역단체장 17개 시도. 데이터 깨끗·해석 명확.</p>
    <div class="card-meta">베이스 모델 정확도 · 8회 백테스트 88%</div>
  </a>
  <a class="card" href="/sim/basic-head/">
    <div class="card-title">기초단체장 226석</div>
    <p class="card-sub">시군구 기초단체장. 후보 효과 큼 → 시도지사보다 모델 신뢰 ↓.</p>
    <div class="card-meta">베이스 모델 정확도 · 8회 백테스트 81%</div>
  </a>
</div>

<p style="text-align:center;color:#aaa;font-size:0.75rem;margin-top:40px">시민언론 뉴탐사 · election2026.newtamsa.org</p>

</div>
<script src="/sim/_gate.js" defer></script>
</body></html>
"""


def main():
    SIM_ROOT.mkdir(parents=True, exist_ok=True)
    print("=== sim/ 빌드 ===")

    # 게이트 JS
    (SIM_ROOT / "_gate.js").write_text(GATE_JS, encoding="utf-8")
    print(f"  · {(SIM_ROOT / '_gate.js').relative_to(ROOT)}")

    # robots.txt — sim/ 디렉터리 검색엔진 차단 (선거법 + 사후 비공개 안전망)
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

    # 두 시뮬레이션 페이지 (exports 결과를 게이트 wrap)
    sido_src = EXPORTS / "simulation_9th_sido" / "index.html"
    bh_src = EXPORTS / "simulation_9th_basic_head" / "index.html"
    if sido_src.exists():
        build_sub_page(sido_src, SIM_ROOT / "sido" / "index.html", "시도지사")
    else:
        print(f"  ! {sido_src.relative_to(ROOT)} 없음 — simulate_9th_sido.py 먼저 실행")
    if bh_src.exists():
        build_sub_page(bh_src, SIM_ROOT / "basic-head" / "index.html", "기초단체장")
    else:
        print(f"  ! {bh_src.relative_to(ROOT)} 없음 — simulate_9th_basic_head.py 먼저 실행")

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

    print("\n사이트 통합 완료. 미리보기 URL:")
    print("  https://election2026.newtamsa.org/sim/?preview=" + PREVIEW_TOKEN)
    print("  https://election2026.newtamsa.org/sim/sido/?preview=" + PREVIEW_TOKEN)
    print("  https://election2026.newtamsa.org/sim/basic-head/?preview=" + PREVIEW_TOKEN)
    print(f"\n공개 시각: {RELEASE_ISO}")


if __name__ == "__main__":
    main()
