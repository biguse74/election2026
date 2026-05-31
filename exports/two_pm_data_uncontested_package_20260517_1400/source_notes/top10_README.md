# Top 10 전과 원문 세부 추출 패키지

## 기준

- 기준 후보: `uncontested_candidates.csv`에서 `important_categories`에 사기·횡령·배임·뇌물 중 하나 이상이 포함된 무투표 당선 후보 10명
- 기준일: 2026-06-03
- 생성 시각: 2026-05-17T15:26:15+09:00

## 파일

- `top10_offense_details.csv`: 한 행이 전과 기록 1건입니다.
- `top10_offense_summary.csv`: 후보 단위 요약입니다.
- `top10_pdf_raw/`: 후보별 PDF 표 전사와 기존 추출 텍스트입니다.
- `top10_extraction_log.txt`: 후보별 접근·추출 로그입니다.
- `top10_validation.txt`: 자체 검증 결과입니다.

## 처리 원칙

- 죄명·형량·처분일자는 원문 표기를 `_raw` 컬럼에 보존했습니다.
- 처분기관과 확정 여부는 PDF 표에 별도 칼럼이 없어 비워 두었습니다.
- PDF 표에 연번 칼럼이 없어 표 순서를 `offense_seq`로 기록했습니다.
- 인용 시 선관위 후보자 상세 페이지 원문 확인 필요.
