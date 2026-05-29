#!/usr/bin/env python3
"""사전투표율 페이지 전용 공유 썸네일(og:image) 생성.

출력: assets/og-early-voting.png (1200x630, OG/트위터 표준 비율)

브랜드:
    - 크림 배경(#f5f1ea) + 좌측 적색 바(#c41e3a) — 기존 assets/og.svg와 통일
    - Noto Serif KR(헤드라인) + Noto Sans KR(부제·정보)
    - 헤드라인은 '우리 지역' 차별점을 전면에

폰트: Windows에 설치된 변동축(VF) Noto KR 사용. 없으면 Malgun으로 폴백.
재생성: python scripts/build_og_early_voting.py
"""

from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "og-early-voting.png"

W, H = 1200, 630
CREAM = (245, 241, 234)
INK = (26, 26, 26)
RED = (196, 30, 58)
SLATE = (95, 106, 120)
GRAY = (136, 136, 136)
SUB = (74, 74, 74)

FONTS_DIR = Path(r"C:\Windows\Fonts")
SERIF_VF = FONTS_DIR / "NotoSerifKR-VF.ttf"
SANS_VF = FONTS_DIR / "NotoSansKR-VF.ttf"
MALGUN = FONTS_DIR / "malgun.ttf"
MALGUN_BD = FONTS_DIR / "malgunbd.ttf"


def font(serif: bool, size: int, weight: int):
    """VF Noto를 우선, 실패 시 Malgun으로 폴백한 폰트 반환."""
    path = SERIF_VF if serif else SANS_VF
    if path.exists():
        f = ImageFont.truetype(str(path), size)
        try:
            f.set_variation_by_axes([weight])  # wght 축
        except Exception:
            pass
        return f
    # 폴백
    fb = MALGUN_BD if weight >= 700 and MALGUN_BD.exists() else MALGUN
    return ImageFont.truetype(str(fb), size)


def text_w(draw, s, f):
    b = draw.textbbox((0, 0), s, font=f)
    return b[2] - b[0]


def fit_font(draw, s, serif, size, weight, max_w):
    """max_w를 넘지 않도록 폰트 크기를 줄여 맞춘다."""
    sz = size
    while sz > 20:
        f = font(serif, sz, weight)
        if text_w(draw, s, f) <= max_w:
            return f
        sz -= 2
    return font(serif, sz, weight)


def main():
    img = Image.new("RGB", (W, H), CREAM)
    d = ImageDraw.Draw(img)

    # 좌측 적색 바
    d.rectangle([0, 0, 14, H], fill=RED)

    x = 80
    max_w = W - x - 60  # 우측 여백

    # 1) eyebrow (적색, 자간 느낌으로 공백 삽입)
    eyebrow = "9회 전국동시지방선거 · 2026. 6. 3.  |  뉴탐사 데이터"
    f_eye = font(False, 28, 700)
    d.text((x, 96), eyebrow, font=f_eye, fill=RED)

    # 2) 헤드라인 (Noto Serif, 900) — 2줄
    line1 = "우리 지역은 4년 전보다"
    line2 = "빠른가, 느린가"
    f_h1 = fit_font(d, line1, True, 96, 900, max_w)
    f_h2 = fit_font(d, line2, True, 96, 900, max_w)
    d.text((x, 184), line1, font=f_h1, fill=INK)
    d.text((x, 312), line2, font=f_h2, fill=INK)
    # 헤드라인 강조 — line2 옆 적색 강조점
    l2w = text_w(d, line2, f_h2)
    d.ellipse([x + l2w + 22, 312 + 70, x + l2w + 44, 312 + 92], fill=RED)

    # 3) 부제 (Noto Sans, 500)
    sub = "17개 시도 사전투표율 — 8회 지선 ‘같은 시각’과 직접 비교"
    f_sub = fit_font(d, sub, False, 36, 600, max_w)
    d.text((x, 452), sub, font=f_sub, fill=SUB)

    # 4) 하단 정보 — 출처 / URL
    info = "중앙선거관리위원회 실측 · 30분마다 자동 갱신"
    f_info = font(False, 26, 500)
    d.text((x, 528), info, font=f_info, fill=GRAY)

    url = "election2026.newtamsa.org/early-voting"
    f_url = font(False, 26, 700)
    uw = text_w(d, url, f_url)
    d.text((W - 60 - uw, 528), url, font=f_url, fill=SLATE)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    img.save(OUT, "PNG")
    print(f"저장 → {OUT.relative_to(ROOT)}  ({OUT.stat().st_size:,} bytes, {W}x{H})")


if __name__ == "__main__":
    main()
