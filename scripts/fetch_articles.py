#!/usr/bin/env python3
"""
뉴탐사 '공천대란' 페이지가 사용하는 구글 시트 CSV를 받아
site/data/articles.json으로 변환한다.

원본 페이지: https://newtamsa.org/p/gongcheon
시트 컬럼: 날짜, 제목, URL, 카테고리, 태그(콤마구분), 기자

사용:
    python scripts/fetch_articles.py

산출물:
    site/data/articles.json
    {
      "updated_at": "...",
      "source_url": "https://newtamsa.org/p/gongcheon",
      "sheet_url": "...",
      "articles": [
        {"date","title","url","category","tags":[...],"author"}, ...
      ]
    }

매칭은 클라이언트(site/js/main.js)에서 후보 이름·정당 기준으로 한다.
스크립트는 데이터 정규화만 책임진다.
"""

from __future__ import annotations

import csv
import io
import json
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

SHEET_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/"
    "1r1ph786QUFGC_rHIOEUdOeQ6L-MvRtcHJvbW6yDJOVA/gviz/tq?tqx=out:csv&gid=0"
)
SOURCE_PAGE = "https://newtamsa.org/p/gongcheon"

ROOT_DIR = Path(__file__).resolve().parent.parent
OUT_FILE = ROOT_DIR / "data" / "articles.json"

KST = timezone(timedelta(hours=9))


def fetch_csv() -> str:
    res = requests.get(SHEET_CSV_URL, timeout=30)
    res.raise_for_status()
    # 구글 시트는 UTF-8로 응답
    return res.text


def parse_rows(text: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(text))
    articles: list[dict] = []
    for row in reader:
        title = (row.get("제목") or "").strip()
        url = (row.get("URL") or "").strip()
        if not title or not url:
            continue
        tags_raw = (row.get("태그") or "")
        tags = [t.strip() for t in tags_raw.split(",") if t.strip()]
        articles.append({
            "date": (row.get("날짜") or "").strip(),
            "title": title,
            "url": url,
            "category": (row.get("카테고리") or "").strip(),
            "tags": tags,
            "author": (row.get("기자") or "").strip(),
        })
    # url 기준 중복 제거 (시트 입력 실수 방어)
    seen: set[str] = set()
    deduped: list[dict] = []
    for a in articles:
        if a["url"] in seen:
            continue
        seen.add(a["url"])
        deduped.append(a)
    return deduped


def main() -> None:
    print(f"구글 시트에서 CSV 수신: {SHEET_CSV_URL}")
    text = fetch_csv()
    articles = parse_rows(text)
    print(f"기사: {len(articles)}건")

    payload = {
        "updated_at": datetime.now(KST).isoformat(timespec="seconds"),
        "source_url": SOURCE_PAGE,
        "sheet_url": SHEET_CSV_URL,
        "count": len(articles),
        "articles": articles,
    }

    OUT_FILE.parent.mkdir(parents=True, exist_ok=True)
    OUT_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(f"저장: {OUT_FILE.relative_to(ROOT_DIR)}")


if __name__ == "__main__":
    main()
