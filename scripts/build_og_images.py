#!/usr/bin/env python3
"""메인(/)·시뮬(/sim/) 공유 썸네일(og:image) 생성.

출력:
    assets/og.png      — 메인 허브 (1200x630)
    assets/og-sim.png  — 결과 예측 시뮬레이션 (1200x630)

브랜드: 크림 배경(#f5f1ea) + 좌측 적색 바 + Noto Serif KR(헤드라인)/Noto Sans KR.
사전투표 OG(build_og_early_voting.py)와 동일 톤.

폰트: Windows 설치 Noto KR VF 우선, 없으면 Malgun 폴백.
재생성: python scripts/build_og_images.py
"""

from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"

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
    path = SERIF_VF if serif else SANS_VF
    if path.exists():
        f = ImageFont.truetype(str(path), size)
        try:
            f.set_variation_by_axes([weight])
        except Exception:
            pass
        return f
    fb = MALGUN_BD if weight >= 700 and MALGUN_BD.exists() else MALGUN
    return ImageFont.truetype(str(fb), size)


def text_w(draw, s, f):
    b = draw.textbbox((0, 0), s, font=f)
    return b[2] - b[0]


def fit_font(draw, s, serif, size, weight, max_w):
    sz = size
    while sz > 20:
        f = font(serif, sz, weight)
        if text_w(draw, s, f) <= max_w:
            return f
        sz -= 2
    return font(serif, sz, weight)


def render(eyebrow, line1, line2, sub, info_left, url, out_name, accent_dot=True):
    img = Image.new("RGB", (W, H), CREAM)
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 14, H], fill=RED)

    x = 80
    max_w = W - x - 60

    f_eye = font(False, 28, 700)
    d.text((x, 96), eyebrow, font=f_eye, fill=RED)

    f_h1 = fit_font(d, line1, True, 96, 900, max_w)
    f_h2 = fit_font(d, line2, True, 96, 900, max_w)
    d.text((x, 184), line1, font=f_h1, fill=INK)
    d.text((x, 312), line2, font=f_h2, fill=INK)
    if accent_dot:
        l2w = text_w(d, line2, f_h2)
        d.ellipse([x + l2w + 22, 312 + 70, x + l2w + 44, 312 + 92], fill=RED)

    f_sub = fit_font(d, sub, False, 36, 600, max_w)
    d.text((x, 452), sub, font=f_sub, fill=SUB)

    f_info = font(False, 26, 500)
    d.text((x, 528), info_left, font=f_info, fill=GRAY)

    f_url = font(False, 26, 700)
    uw = text_w(d, url, f_url)
    d.text((W - 60 - uw, 528), url, font=f_url, fill=SLATE)

    out = ASSETS / out_name
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG")
    print(f"저장 → {out.relative_to(ROOT)}  ({out.stat().st_size:,} bytes)")


def main():
    # 1) 메인 허브
    render(
        eyebrow="제9회 전국동시지방선거 · 2026. 6. 3.  |  뉴탐사 데이터",
        line1="후보부터 개표까지,",
        line2="데이터로 본다",
        sub="사전투표율 · 결과 예측 시뮬 · 개표 라이브 — 매일 갱신",
        info_left="중앙선거관리위원회 데이터 기반",
        url="election2026.newtamsa.org",
        out_name="og.png",
    )
    # 2) 결과 예측 시뮬레이션 (108조 유의 — 단정 아님 명시)
    render(
        eyebrow="제9회 전국동시지방선거 · 2026. 6. 3.  |  뉴탐사 데이터",
        line1="6·3 지방선거",
        line2="결과 예측 시뮬레이션",
        sub="여론조사가 아닌 데이터 시뮬레이션 · 단정 아님",
        info_left="가정·방법론 공개 · 참고용",
        url="election2026.newtamsa.org/sim",
        out_name="og-sim.png",
        accent_dot=False,
    )


if __name__ == "__main__":
    main()
