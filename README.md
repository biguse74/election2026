# 9회 전국동시지방선거 (2026.6.3) 데이터 수집

선관위 OpenAPI에서 제공하는 5개 서비스의 데이터를 수집·저장한다.

## 데이터 구조

```
data/
├── codes/                              # 코드정보 (1회 수집 후 거의 변동 없음)
│   ├── elections.json                  # 전체 선거 목록
│   └── 20260603/                       # 9회 지선 sgId
│       ├── gusigun.json                # 구시군 코드
│       ├── parties.json                # 정당 코드
│       ├── jobs.json                   # 직업 코드
│       ├── educations.json             # 학력 코드
│       └── constituencies/             # 선거종류별 선거구 코드
│           ├── sgType_3.json           # 시도지사
│           ├── sgType_4.json           # 구시군장
│           ├── sgType_5.json           # 시도의원
│           ├── sgType_6.json           # 구시군의회의원
│           ├── sgType_8.json           # 광역의원비례
│           ├── sgType_9.json           # 기초의원비례
│           └── sgType_11.json          # 교육감
│
├── preliminary/                        # 예비후보자 (5/13까지만 조회 가능)
│   └── 20260603/
│       └── snapshot_YYYYMMDD.json      # 일자별 스냅샷
│
├── candidates/                         # 후보자 (5/14 ~)
│   └── 20260603/
│       └── snapshot_YYYYMMDD.json
│
└── results/                            # 선거 결과 (8월 이후 OpenAPI 갱신)
    └── 20260603/
        ├── early_voting.json           # 사전투표 결과
        ├── vote_status.json            # 투표 결과
        ├── counting.json               # 개표 결과
        └── winners.json                # 당선인
```

## 일정 변수 (중요)

| 시점 | OpenAPI 상태 |
|------|--------------|
| ~ 5/13 | 예비후보자 정보 조회 가능 |
| **5/14** | **예비후보자 정보 조회 불가로 전환** |
| 5/14 ~ | 후보자 정보 조회 가능 |
| 5/29 ~ 5/30 | 사전투표 (결과는 6월 이후 OpenAPI 반영) |
| 6/3 | 본투표. **OpenAPI는 실시간 결과를 제공하지 않음** |
| 약 8월 초 | 투개표·당선인·사전투표 정보 OpenAPI 갱신 |

→ **예비후보자 데이터는 사라지기 전 매일 스냅샷 필수**

## 실행

```bash
pip install -r requirements.txt
export NEC_API_KEY=<공공데이터포털_인증키>
python scripts/fetch_codes.py
```

## API 명세

| API | sgTypecode 사용 | 비고 |
|-----|-----------------|------|
| 코드정보 | 0(대표명),1~11 | 모든 다른 API의 기반 |
| 후보자정보 | 3,4,5,6,8,9,11 | 9회 지선 기준 |
| 투개표정보 | 3 (지선 대표값) | 시도지사 기준으로 시군구 단위 집계 |
| 당선인정보 | 3,4,5,6,8,9,11 | |
| 사전투표 | - | erVotingDiv (0=전체,1=1일차,2=2일차) |

## 인증키 관리

- 로컬 개발: `.env` 파일에 저장 (커밋 금지, `.gitignore`에 포함됨)
- GitHub Actions: 레포 Settings → Secrets and variables → Actions → `NEC_API_KEY` 등록
