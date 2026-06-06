# -*- coding: utf-8 -*-
"""원본 대조 검증 도구용 로컬 서버(멀티스레드).

사용:
  1) 검증 도구 생성:  python scripts/build_verify_tool.py
  2) 이 서버 실행:     python scripts/serve.py
  3) 크롬에서 열기:    http://localhost:8900/verify.html

멀티스레드라 PDF를 빠르게 넘겨도 동시 요청을 거부하지 않는다.
프로젝트 루트를 서빙하므로 원본 PDF(data/disclosure_archive/...)도 함께 열린다.
종료: 이 창에서 Ctrl+C.
"""
import os
from functools import partial
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PORT = 8900


def main():
    os.chdir(ROOT)  # 프로젝트 루트 서빙
    handler = partial(SimpleHTTPRequestHandler, directory=str(ROOT))
    srv = ThreadingHTTPServer(("127.0.0.1", PORT), handler)
    print("=" * 56)
    print("  원본 대조 검증 서버 실행 중 (멀티스레드)")
    print(f"  → 크롬에서 열기:  http://localhost:{PORT}/verify.html")
    print("  → 종료: 이 창에서 Ctrl+C")
    print("=" * 56, flush=True)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n서버 종료.")


if __name__ == "__main__":
    main()
