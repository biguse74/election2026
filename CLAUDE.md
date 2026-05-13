# 9회 전국동시지방선거 데이터 트래커

## 프로젝트 개요

2026년 6월 3일 시행되는 제9회 전국동시지방선거의 후보·투개표·당선인 데이터를 자동 수집하고 정적 사이트로 시각화하는 저널리즘 도구. 뉴탐사(newtamsa.org) 내부 분석 메인, 6/3 방송 보조 데이터로 사용.

- **라이브**: https://biguse74.github.io/election2026/
- **저장소**: https://github.com/biguse74/election2026 (Public)
- **소유자**: biguse74 (biguse@newtamsa.org, 기자)

---

## 결정적 상수

- **선거 ID**: `sgId=20260603`
- **선거일**: 2026-06-03
- **후보자등록일**: 2026-05-14 ~ 05-15
  - **5/14 이후 예비후보 API 조회 불가** → 5/13까지 일일 스냅샷 보관 필수
- **전남광주통합특별시 출범**: 2026-07-01 (선거는 그 전, 행정구역은 17개 시도 유지)
- **API 인증키**: 환경변수 `NEC_API_KEY` (GitHub Secrets에도 같은 이름으로 등록)
  - 공공데이터포털 일반 인증키, 5개 서비스(후보자·투개표·당선인·코드·사전투표) 모두 동일 키

---

## 파일 구조

```
~/Developer/election2026/
├── index.html                # 루트 → /site/ 리다이렉트
├── site/                     # 정적 사이트 (GitHub Pages 배포 대상)
│   ├── index.html            # 가벼운 스켈레톤 (Leaflet CDN 포함)
│   ├── css/main.css
│   ├── js/main.js            # SPA - SECTIONS 패턴 기반
│   ├── data/
│   │   ├── parties.json      # 정당별 색상 매핑 (수동 유지)
│   │   └── nominations.json  # 공천 확정 데이터 (수동, 기사 기반)
│   └── assets/geo/
│       ├── sido.geojson      # 17개 시도 폴리곤 (1MB)
│       └── sigungu.geojson   # 255개 시군구 폴리곤 (3.5MB)
├── scripts/
│   ├── fetch_codes.py        # 선거 코드 (시도·시군구·선거구·정당·직업·학력)
│   ├── fetch_preliminary.py  # 예비후보 (~5/13까지 매일)
│   ├── fetch_candidates.py   # 후보 (5/14 이후 매일)
│   └── fetch_geo.py          # vuski/admdongkor에서 행정동 받아 shapely로 dissolve
├── data/                     # 자동 fetch 결과 (Actions가 커밋)
│   ├── codes/
│   ├── preliminary/20260603/snapshot_YYYYMMDD.json
│   └── candidates/20260603/snapshot_YYYYMMDD.json
├── .github/workflows/
│   ├── fetch_preliminary.yml # 매일 KST 03:00 (5/14 이후 자동 스킵)
│   └── fetch_candidates.yml  # 매일 KST 03:15 (5/14 이전 자동 스킵)
└── requirements.txt
```

> 작업 디렉터리는 `~/Developer/election2026` 고정. iCloud / Downloads는 sync 충돌·파일 eviction 이슈로 회피한다.

---

## 선거 종류 코드 (sgTypecode)

| 코드 | 선거 | 9회 지선 | 예비단계 |
|------|------|:--------:|:--------:|
| 1 | 대통령선거 | - | - |
| 3 | 시도지사 | ○ | ○ |
| 4 | 구시군장 (기초단체장) | ○ | ○ |
| 5 | 시도의원 | ○ | ○ |
| 6 | 구시군의회의원 | ○ | ○ |
| 7 | 비례대표국회의원 | - | - |
| 8 | 광역의원비례 | ○ | ✕ |
| 9 | 기초의원비례 | ○ | ✕ |
| 10 | 교육의원 | (일몰) | - |
| 11 | 교육감 | ○ | ○ |

비례(8, 9)는 예비후보 등록 제도가 없다. 후보등록일에 정당이 명부 제출.

---

## 행정구조 특수 케이스 (반드시 숙지)

### 전남광주통합특별시 (시도지사 한정 통합)

- **시도지사 선거만** 광주광역시 + 전라남도 → '전남광주통합특별시' 1개 선거구로 통합
- 다른 선거(교육감, 기초단체장, 시도의원 등)는 광주/전남 분리 유지
- **데이터 함정**: API를 `sdName=광주광역시`로 호출해도, `sdName=전라남도`로 호출해도 통합특별시 시도지사 후보가 **둘 다 반환됨** → 중복 발생
- **대응**:
  - `fetch_*.py`에서 저장 직전 `dedupe_by_huboid()`로 원본 단계 dedup (5/12부터 적용)
  - `main.js` 로딩 시점에도 `dedupeByHuboid()`로 한 번 더 (구 스냅샷 호환 + 안전망)
  - `SIDO_ALIASES`로 광주·전남 상세 페이지 진입 시 통합특별시 후보 lookup

### 제주특별자치도

- 기초자치단체 없음 → 기초단체장(`sgTypecode=4`) 선거 미실시
- 행정시(제주시·서귀포시) 시장은 도지사가 임명
- `ABSENCE_NOTES['제주특별자치도']['4']`로 안내 메시지 표시

### 세종특별자치시

- 단층제 → 기초자치단체 없음 (제주와 유사)
- 기초단체장 데이터 0일 가능성 → `ABSENCE_NOTES` 추가 필요 (데이터 확인 후 작업할 것)

---

## 프론트엔드 아키텍처

### SECTIONS 패턴 (단일 source of truth)

```js
const SECTIONS = [
  { id: 'chief',    sgTypecode: '3',  title: '시도지사',   useAlias: true, card: true, detail: { layout: 'single' } },
  { id: 'head',     sgTypecode: '4',  title: '기초단체장', card: true, detail: { layout: 'grid', groupBy: c => c.sggName || c.wiwName } },
  { id: 'sidoMp',   sgTypecode: '5',  title: '시도의원',   card: true },
  { id: 'educator', sgTypecode: '11', title: '교육감',     card: true, detail: { layout: 'single' } },
];
```

이 배열이 홈 카드 통계와 상세 페이지 렌더링을 모두 driving. 신규 선거 추가 시 이 배열에만 추가하면 자동으로 양쪽에 반영된다.

### 핵심 규칙

1. **빈 섹션 자동 숨김**: `candidates.length === 0`이면 안 그림
2. **`ABSENCE_NOTES` 예외**: 행정구조상 부재인 경우 컨텍스트 메시지로 표시 (제주 기초단체장 같은 경우)
3. **로딩 시점 1회 dedup**: `state.data.candidates = dedupeByHuboid(data.candidates)` — 이후 모든 필터는 깨끗한 데이터 가정
4. **시도 정렬**: 행정안전부 표준 순서 (`SIDO_ORDER`) — 가나다순 아님
5. **시군구 정렬**: 가나다순 (`koSort`)
6. **공천 확정 표시**: `nominations.json` 매칭 시 후보명 옆에 빨간 "공천" 배지
7. **URL 라우팅**: hash 기반. `#` = 홈, `#서울특별시` = 상세

### 데이터 흐름

```
중앙선관위 OpenAPI (5개 서비스)
  ↓ scripts/fetch_*.py  (GitHub Actions, KST 03:00·03:15)
  ↓
data/{preliminary|candidates}/20260603/snapshot_YYYYMMDD.json
  ↓ Actions가 git commit & push
  ↓ GitHub Pages 자동 배포
  ↓
site/js/main.js가 최근 14일 거꾸로 훑어 최신 스냅샷 fetch
  ↓ dedupeByHuboid 1회
  ↓ SECTIONS 기반 렌더링
```

---

## 자주 쓰는 명령어

```bash
# 일일 작업 시작
cd ~/Developer/election2026 && git pull

# 로컬 사이트 확인
python -m http.server 8000
# → http://localhost:8000/site/

# 수동 fetch (API 키 필요)
export NEC_API_KEY=<발급키>           # GitHub Secrets에 동일 값
python scripts/fetch_preliminary.py
python scripts/fetch_candidates.py
python scripts/fetch_codes.py
python scripts/fetch_geo.py

# 워크플로우 수동 트리거 / 상태 확인
gh workflow run fetch_preliminary.yml
gh run list --limit 5
gh run view <run-id> --log
```

---

## 코딩 컨벤션

- **응답 언어**: 한국어 (사용자가 한국어 기자)
- **사실 정확성 최우선**: 기자 직업 특성. 추측은 반드시 명시하고, 검증 가능한 사실에만 기반한다
- **빈 섹션은 숨김**, 특별 케이스는 `ABSENCE_NOTES`로
- **시도 alias 매핑**은 `SIDO_ALIASES` 한 곳에서만 관리
- **CSS 변수** (`--ink`, `--accent` 등) 사용, 하드코딩 색상 지양
- **Pretendard + Noto Serif KR** 폰트 조합 (편집·저널리즘 미감)
- **Leaflet CDN** 사용 (별도 빌드 단계 없음)
- **zsh** + `setopt interactive_comments` (`#` 주석 명령어 OK)

---

## 자주 등장하는 작업 패턴

| 사용자 요청 | 손볼 곳 |
|------------|---------|
| "X 선거도 보여줘" | `SECTIONS` 배열에 항목 추가 |
| "Y 시도의 Z 선거가 없는 이유 설명" | `ABSENCE_NOTES`에 한 줄 추가 |
| "공천 확정 후보 갱신" | `site/data/nominations.json` 수동 편집 |
| "정당 색상 추가/변경" | `site/data/parties.json` 수정 |
| "디자인 손봐줘" | `site/css/main.css`, `frontend-design` 스킬 참고 |
| "fetch 스크립트 동작 이상" | GitHub Actions 로그 먼저 확인 (`gh run view`) |

---

## 알려진 미해결 항목 (TODO)

- [ ] 6/3 실시간 개표 데이터 (선관위 OpenAPI 미제공). A+D 조합으로:
      · **A. `info.nec.go.kr` 스크래퍼** — 본가 사이트 내부 fetch endpoint 파악(5/말),
        Python 스크립트로 5~10분 간격 폴링, `data/tally/snapshot_*.json` 저장
      · **D. 출구조사 (저녁 7:30)** — 방송 3사 컨소시엄 결과를 수동 입력하는
        `data/exit_poll.json` 1회용 데이터. UI에 "출구조사 (가) 1위" 형태
      · **본가동 일정**: 5/말~6/2 정찰·PoC, 6/3 18:00부터 가동, 익일 KST 03시
        OpenAPI 정식 결과로 자동 전환(이미 candidates→preliminary 전환 패턴 재사용)
- [ ] 사전투표·투개표·당선인 fetcher 미구현 (선거 후 약 8월 데이터 갱신 대응)
- [ ] 시도의원·구시군의회의원 상세 페이지 섹션 (데이터량이 커서 collapsible UI 필요)

---

## 외부 의존성

- **공공데이터포털 API**: `https://apis.data.go.kr/9760000/...` (HTTP, HTTPS 아님)
  - `PofelcddInfoInqireService` (예비후보·후보)
  - `VoteXmntckInfoInqireService2` (투개표)
  - `WinnerInfoInqireService2` (당선인)
  - `CommonCodeService` (코드)
  - `ErVotingSttusInfoInqireService` (사전투표)
- **GeoJSON 소스**: `github.com/vuski/admdongkor` ver20260201 (2026-02-01 화성 4개구 반영)
- **Leaflet**: 1.9.4 (CDN)
- **Pretendard + Noto Serif KR**: Google Fonts (CDN)
- **Python**: 3.13 (conda base)
- **주요 패키지**: `requests`, `shapely>=2.0`

---

## 사용자 컨텍스트

- 한국어 기자 (`biguse74@newtamsa.org`, 뉴탐사)
- 회사 MacBook Pro, conda Python 3.13, zsh
- 다른 작업: 방송 스크립트 → 기사 변환, 송고용 PPT, 인터뷰 기사 등 (관련 스킬은 별도 위치)
- 트래커 운영뿐 아니라 그 데이터로 기사·방송 작성에도 사용

---

## 시도 17개 표준 명칭 (코드 매칭용)

선관위 API가 반환하는 정식 명칭. 다른 표기 사용 금지.

```
서울특별시 / 부산광역시 / 대구광역시 / 인천광역시 / 광주광역시
대전광역시 / 울산광역시 / 세종특별자치시
경기도 / 강원특별자치도 / 충청북도 / 충청남도
전북특별자치도 / 전라남도 / 경상북도 / 경상남도 / 제주특별자치도
```

⚠️ `강원도` → `강원특별자치도` (2023), `전라북도` → `전북특별자치도` (2024) 명칭 변경 반영됨.

⚠️ 시도지사 선거 데이터에서만 `전남광주통합특별시`가 `sggName`으로 등장.
