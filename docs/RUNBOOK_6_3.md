# 6·3 본방 운영 체크리스트

> 2026년 6월 3일 제9회 전국동시지방선거 라이브 운영 매뉴얼.
> 인쇄/태블릿으로 들고 보면서 시간대별 점검 → 이상 시 즉시 대응.

---

## 0. 핵심 상수

- **선거 ID**: `0020260603` (info.nec.go.kr), `sgId=20260603` (OpenAPI)
- **선거일**: 2026-06-03 (수)
- **본투표 시간**: 06:00 ~ 18:00 KST
- **개표 시작**: 18:00 KST
- **사이트**: https://election2026.newtamsa.org/
- **저장소**: https://github.com/biguse74/election2026
- **공공데이터 한도**: **10,000회/일** (예상 사용 5,448회, 마진 45%)
- **응급 연락**: `biguse@newtamsa.org` · GitHub 알림은 모바일 앱 푸시

---

## 1. 자동으로 도는 것 (사람 개입 불필요)

| 시각 (KST) | 워크플로우 | 발화 횟수 | 동작 |
|---|---|---|---|
| 6/3 03:00 | `fetch_preliminary` | 1회 | **자동 스킵** (5/14 이후 가드) |
| 6/3 03:15 | `fetch_candidates` | 1회 | 후보자 스냅샷 + index.html 갱신 |
| 6/3 03:45 | `fetch_early_voting` | 1회 | 사전투표 통계 최종 확정 |
| **6/3 06:00 ~ 17:55** | `fetch_live_counting` | 144회 (5분) | 투표율만, `--skip-counting` |
| **6/3 18:00 ~ 20:55** | `fetch_live_counting` | 36회 (5분) | 풀 호출 — 투표율 + 개표 |
| **6/3 21:00 ~ 익일 05:55** | `fetch_live_counting` | 54회 (10분) | 풀 호출, 빈도 완화 |
| 6/4 06:00 ~ 11:30 | `fetch_live_counting` | 12회 (30분) | 보조 — 익일 정식 결과 대비 |
| 6/3 매 10분 | `probe_nec_site` | 144회 | 선관위 VC 페이지 활성화 감시 |

브랜드 타이틀도 6/3 KST 00:00부터 자동 전환 (출마자 → 실시간).

---

## 2. 시간대별 사람 점검

### ⏰ 6/2 (D-1) — 사전 준비

- [ ] **Secret 재확인**: GitHub Settings → Secrets → `NEC_API_KEY` 살아있는지
- [ ] **워크플로우 활성**: Actions 탭에서 5/24~6/2 정찰 cron이 녹색으로 잘 도는지 한 번 훑기
- [ ] **모바일·PC 둘 다 사이트 열어 화면 확인** (정상 동작 + 캐시 새로고침)
- [ ] **OG 메타 수동 갱신 (선택)**: `index.html` `<meta og:title>`을 "실시간"으로 변경하여 카톡 공유 시 새 텍스트
- [ ] **fetch_articles cron 시프트 (선택)**: KST 09:00·15:00·21:00 → 09:02·15:02·21:02로 옮기면 라이브 수집과 충돌 없음
- [ ] **트래픽 대비 (선택)**: Cloudflare 무료 플랜을 사이트 앞에 둘지 결정. 평소 트래픽 < 100MB/일이면 GitHub Pages 그대로 충분

### ⏰ 6/3 05:50 — 자동 수집 직전

- [ ] PC + 폰 모두 열어두고 대기
- [ ] Actions 탭에서 다음 워크플로우 발화 확인:
  - `fetch_candidates` 03:15 → 녹색?
  - `fetch_early_voting` 03:45 → 녹색?

### ⏰ 6/3 06:00 — 본투표 시작

- [ ] **05~10분 안에** 라이브 화면 새로고침해서 첫 투표율 수집값 표시되는지 확인
- [ ] phase 배너가 **"본투표 진행 중"** (파란색) 인지
- [ ] 사전투표 비교 박스 표시 정상 (8회·7회 사전+거소 비율 보임)

### ⏰ 6/3 09:00 · 12:00 · 15:00 — 진행 중간 체크

- [ ] 라이브 투표율 차트에 9회 라인이 점점 길어지고 있는지
- [ ] 시도 카드 17개 모두 데이터 들어오는지
- [ ] **누락된 시도**가 있다면: Actions → 가장 최근 `fetch_live_counting` 로그 확인. `resultCode=INFO-03` (정상) vs `code=22` (한도 초과)

### ⏰ 6/3 13:00 — 사전투표 합산 점프

- [ ] 차트에서 12→13시 점프가 보이는지 (8회 +23.3%p, 7회 +23.8%p 수준)
- [ ] 사전투표 비교 박스에 **9회 라이브 점프량**도 표시됐는지

### ⏰ 6/3 17:55 — 본투표 마감 직전

- [ ] 최종 투표율 박스 갱신 확인
- [ ] 출구조사 데이터 입력 준비 (방송 3사 컨소시엄 발표 18:00):
  ```
  파일: data/exit_poll.json
  편집 → git commit + push → 1~2분 후 라이브 화면 반영
  ```
  ⚠️ `released_at`을 발표 시각 18:00:00 KST로 설정해야 그 전에 노출 안 됨

### ⏰ 6/3 18:00 — 개표 시작

- [ ] phase 배너가 **"개표 진행 중"** (녹색) 으로 자동 전환됐는지
- [ ] **5~15분 안에 첫 개표 데이터**가 들어오는지 (시도지사·기초단체장 race 카드 등장)
- [ ] 만약 18:30까지 데이터 0이면: phase가 **"개표 데이터 수신 대기"** (노랑) 유지 — OpenAPI 갱신 늦은 것. 자동 수집이 계속 시도하므로 기다림

### ⏰ 6/3 19:30 — 사전+잔여 합산 시점

- [ ] 8회처럼 19:30 시점에 사전·잔여 투표분 합산 점프가 들어오는지 (투표율 최종값 확정)

### ⏰ 6/3 22:00 ~ 익일 03:00 — 개표 격전

- [ ] race 카드의 "8회 당선" 비교가 정상 표시되는지
- [ ] **정당 유지/탈환 추세** 배지가 개표율 10%↑ race에 등장하는지
- [ ] 차트의 라이브 라인 끝점이 18:00 이후로 계속 연장되는지

### ⏰ 6/4 06:00 — 익일 정리

- [ ] phase 배너가 **"최종 결과"** (검정) 으로 전환됐는지 (avg_progress ≥ 99%)
- [ ] 안 됐으면 phase는 **"개표 진행 중 · 정식 결과 대기"** (노랑) 유지 — 30분 보조 수집이 6/4 06:00~11:30 동안 도는 중
- [ ] 브랜드 타이틀이 **"6·3 지방선거 결과"**로 자동 전환

---

## 3. 비상 대응

### 🚨 OpenAPI 호출 한도 초과 (resultCode=22)

**증상**: Actions 로그에 `resultCode=22` 또는 `LIMITED_NUMBER_OF_SERVICE_REQUESTS_EXCEEDS_ERROR`

**대응** (즉시):
1. Actions → `fetch_live_counting` → 가장 최근 실패 워크플로우 확인
2. 임시로 수집 간격 늘리기:
   - `.github/workflows/fetch_live_counting.yml` 편집
   - `*/5 9-11 3 6 *` → `*/10 9-11 3 6 *` (격렬 개표를 10분으로)
   - 커밋·푸시 → 즉시 적용
3. 익일까지 한도 리셋 (00:00 KST 추정)

### 🚨 GitHub Actions cron이 안 도는 경우

**증상**: 30분 동안 신규 워크플로우 실행이 없음

**대응**:
1. Actions 탭 → `fetch_live_counting` → **Run workflow** 수동 트리거
2. 옵션: `mode=auto`, `sg-id=20260603`
3. 안 되면 로컬에서 직접:
   ```powershell
   $env:NEC_API_KEY = '<발급키>'
   python scripts\fetch_live_counting.py
   # → data/live_counting/*.json 갱신 → 수동 commit·push
   ```

### 🚨 라이브 화면이 안 갱신됨 (stale 5분↑)

**증상**: 화면 상단 배지가 빨간색 "갱신 지연 N분 전"

**대응**:
1. Actions 로그 확인 — 수집이 도는데 push가 reject 되는지
2. push 충돌이면 다음 cron이 rebase 후 재시도 — 1~2회 수집 지연 정상
3. 5회 이상 실패면 수동 트리거

### 🚨 선관위 사이트 VC 활성화 알림 (probe_nec_site exit 1)

**증상**: 모바일/이메일에 `Failure` 알림

**대응**: 가능하면 환영. fallback 스크래퍼를 시작할 시점.
1. 로컬에서 `python scripts/probe_nec_site.py --verbose`로 확인
2. 새로 들어온 endpoint (`/main/main_vote.jsp` 등) 파악
3. 시간 여유 있으면 스크래퍼 작성. 없으면 OpenAPI 자동 수집만 유지

### 🚨 출구조사 입력 누락

**증상**: 18:00 발표 후에도 라이브 화면에 출구조사 영역 안 보임

**확인**:
1. `data/exit_poll.json` 의 `released_at`이 과거 시각인지
2. 라이브 화면이 그 후 1회 재수집했는지 (자동 새로고침 60초마다)
3. JSON 파일에 sgg_name 등 키 매칭 — 시도지사는 `null` 또는 sd_name과 동일값 OK (자동 정규화)

---

## 4. 자주 쓰는 명령어

```powershell
# 사이트 로컬 미리보기
cd C:\Users\bigus\Documents\Codex\2026-05-16\github-https-github-com-biguse74-election2026
python -m http.server 8000

# 워크플로우 상태 (gh CLI 있을 때)
gh run list --workflow=fetch_live_counting.yml --limit 5
gh run view <RUN_ID> --log

# 수동 수집 (API 키 필요)
$env:NEC_API_KEY = '<발급키>'
python scripts\fetch_live_counting.py --sg-id 20260603
python scripts\fetch_live_counting.py --dry-run             # 호출만, 저장 X
python scripts\fetch_live_counting.py --skip-counting       # 투표율만

# 선관위 사이트 정찰
python scripts\probe_nec_site.py --verbose

# 출구조사 데이터 갱신 후 push
git add data/exit_poll.json
git commit -m "출구조사 발표값 입력"
git push
```

---

## 5. 사이트 주요 URL

| 라우트 | 용도 |
|---|---|
| `/` | 홈 — 출마자 통계 |
| `/#live` | **실시간 개표** (본방용) |
| `/#trend` | 출마자 한눈에 |
| `/#schedule` | 선거 일정 |
| `/#history` | 지난 선거 결과 |

---

## 6. 6/3 이후 정리

### 6/4 ~ 6/7

- [ ] **fetch_past_counting 워크플로우 1회 실행** — 9회 결과를 history에 추가 (만 2개월 안)
- [ ] OG 메타 원복 (선택)
- [ ] 데이터 분할 최적화 검토 (`history_counting_results.json` 크기 30MB → 1/5 분리 가능)

### 만 2개월 후 (2026-08-03 즈음)

- 공식 통계 안정화 시점 (가이드 명시: "선거 종료 후 두 달 이내")
- `fetch_past_counting` 다시 실행 → 9회 데이터 완성
- 사이트 평소 모드 (`#trend`·`#history`)로 점차 전환
