# 무투표 당선 선거구 기사 근거 데이터 패키지

## 기준 시점

- 스냅샷 일자: 2026-05-17
- 후보 등록 스냅샷 수집 시각: 2026-05-17T04:34:13+09:00
- 생성 시각: 2026-05-17T12:18:27+09:00

## 사용 원자료

- `data/candidates/20260603/snapshot_20260517.json`: 선관위 후보 등록 스냅샷
- `data/candidate_details.json`: 선관위 후보자 상세 공개정보
- `data/constituencies.json`: 선거구별 의원정수
- 전과 PDF 죄명 분류 결과

## 핵심 정의

- 무투표 당선 선거구: 등록 후보 수가 1명 이상이고 의원정수 이하인 선거구.
- 등록미달 선거구: 등록 후보 수가 의원정수보다 적은 선거구.
- 최근 5년 체납 이력자: `tax_arrears_5y_thousand_krw > 0`.
- 현 체납자: `tax_arrears_current_thousand_krw > 0`.
- 전과 공개 후보: 선관위 공개정보의 전과 항목이 `없음`이 아닌 후보.
- 공직 검증 전과: 전과 죄명 분류 결과에서 `공직 검증` 그룹에 하나 이상 포함된 후보.
- 공직선거법 전과: 전과 분류 문자열에 `공직선거법`이 포함된 후보.

## 산출 파일

- `uncontested_districts.csv`
- `uncontested_candidates.csv`
- `uncontested_by_party.csv`
- `uncontested_by_region.csv`
- `uncontested_by_office.csv`
- `uncontested_key_stats.json`
- `series_lead_cases.csv`
- `missing_seats.csv`
- `validation_report.txt`
- `00_CLAUDE_UNCONTESTED_SERIES_INSTRUCTIONS.md`
- `README.md`

## 보도 시 권장 표현

- "선관위 후보자 공개정보 기준"
- "2026년 5월 17일 후보 등록 스냅샷 기준"
- "인용 시 선관위 후보자 상세 페이지 원문 확인 필요"
- "전과 유형은 후보 1명이 여러 분류에 중복 포함될 수 있음"

## 헤드라인 사례 파일

`series_lead_cases.csv`는 조건을 만족한 후보만 담았습니다. 조건에 맞는 후보가 30명보다 적을 경우 보충 행을 임의로 넣지 않습니다. 이번 패키지의 조건 충족 사례는 26건입니다.

## 한계

- 스냅샷 이후 사퇴·등록무효·추가 변동은 별도 확인이 필요합니다.
- 비례대표 선거는 정당명부와 의석 배분 구조가 지역구와 다르므로 `office_type`으로 분리해 해석해야 합니다.
- 의원정수 자료와 후보 스냅샷의 선거구 키가 맞지 않는 행은 `missing_seats.csv`에 따로 분리했습니다. 추정으로 보정하지 않았습니다.
