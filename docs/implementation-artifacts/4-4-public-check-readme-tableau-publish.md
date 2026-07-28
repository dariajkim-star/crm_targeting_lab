---
baseline_commit: 1927df0
---

# Story 4.4: 공개 점검·README·Tableau 퍼블리시 (blocked-external)

Status: done

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a 포트폴리오 독자,
I want 링크 하나로 5분 안에 전체 스토리를 파악하기를,
so that 이 프로젝트가 무엇을 했고 무엇을 하지 않았는지 빠르게 판단된다.

## 배경 — 에픽4 마지막 스토리, 분업 설계

**blocked-external 분업**(FR18·conventions 7항·P1 3-3 선례): **세션 몫** = 공개 점검 + README 본편 + 퍼블리시 절차서(마트·스키마·사양서는 4-1a/4-3에서 이미 산출). **daria 몫** = Tableau Public 계정 확인(OQ-5)·워크북 제작(`marts/dashboard-spec.md` 그대로)·퍼블리시·링크 확보. **링크 미확보는 세션 산출물의 done을 블로킹하지 않는다**(epics AC 명시). 이 스토리의 done = 세션 몫 완결.

## Acceptance Criteria

**AC1 — 공개 안전 점검 (AD-10·NFR7 / 스토리 결정 D1)**
Given 퍼블리시 전 안전 점검이 필요할 때
When 마트·커밋 이력을 검사하면
Then ①`mart_customers.csv`의 전 컬럼이 공개 데이터셋(BankChurners) 유래·파생값만 담음을 컬럼 단위로 확인하고 그 결과를 점검 기록으로 남긴다(스키마 문서의 산출 모듈 칸이 근거 — CLIENTNUM도 공개 원본의 ID임을 명시) ②**커밋 이력 전체**에 `data/`·`models/` 아티팩트(parquet·joblib) 유입이 0건임을 스캔으로 확인(P1 3-4 선례) ③게시 시 마트 내용이 공개 조회 가능해진다는 사실을 README·절차서에 명시.
And **현재 트리의 무결은 pytest로 영구 고정**(D1): 추적 파일에 `.parquet`·`.joblib` 0건 단언 — 일회 감사가 아니라 회귀 가드.

**AC2 — README 본편 (NFR8·성공신호 ③④ / 스토리 결정 D2)**
Given 독자가 README를 읽을 때
When 5분 안에 파악을 시도하면
Then **핵심 수치표**(분면 분포·공식 컷·기대절감 총합·PR-AUC/lift·마트 행수)·**발견 요약**·**한계**·**문서 지도**가 구성된다.
And **모든 가정이 명시된다**: 데이터 결합 불가(AD-1) · `Attrition_Flag` 라벨 단면성(스냅샷, 시계열 예측 아님) · 성공률 0.30/비용 5.0 정책가정 · 통화 무단위(고객 레인)/GBP(LTV 레인).
And **미달·미수행이 숨겨지지 않는다**: epic-2 동결(LTV 데모 미수행)·Tableau 링크 상태(확보 전이면 자리 표시)·단일 리텐션율의 분해 불가.
And 수치는 **재현 가능한 커밋 경로가 뒷받침하는 값만** 싣고(conventions 4항), 테스트 수는 실행 환경 기준을 병기한다(D2 — xgboost 유무로 수가 갈리는 사실을 숨기지 않는다).

**AC3 — 퍼블리시 절차서 (FR18)**
Given daria가 세션 없이 워크북을 만들 때
When `docs/tableau-publish-runbook.md`를 따르면
Then 단계별 절차가 완결된다: ⓪Tableau Public 계정 확인(OQ-5) → ①마트 CSV 연결 → ②`dashboard-spec.md`대로 탭·시트 제작(숨김 필드·시나리오 규약·캡션 규약 포함) → ③**검산 앵커 대조**(사양서 표) → ④AD-3 4항목 자가 점검 → ⑤퍼블리시(공개 조회 가능 고지 포함) → ⑥링크를 README 자리 표시에 기입.
And 각 단계에 "무엇이 어긋나면 무엇을 의심하라"가 붙는다(사양서 검산 앵커의 연장).

**AC4 — 문서=계약 기계 검증 (4-3 패턴)**
Given README가 계약면이 될 때
When pytest를 실행하면
Then 신설 테스트가 검증한다: ①README 핵심 수치표의 골든값(분면 분포·컷·총합)이 `tests/marts` 골든과 동일 문자열 ②가정 4종 문구 존재 ③추적 파일 아티팩트 0건(AC1) ④절차서에 검산 앵커 대조 단계 존재. 슬라이스는 4-3 견고화 헬퍼 패턴(양 앵커 단언).

## Tasks / Subtasks

- [x] **T1 — 공개 점검** (AC1)
  - [x] 커밋 이력 스캔(`git log --all --name-only` → parquet/joblib 검색) 결과를 스토리 Dev Record에 기록. 마트 컬럼 유래 점검표(스키마 산출 모듈 칸 대조) 동봉.
  - [x] `tests/docs/test_public_release.py`(신규 패키지): git 추적 파일에 `.parquet`·`.joblib` 0건 단언.
- [x] **T2 — README 본편 재작성** (AC2)
  - [x] stale 헤더(에픽3 진행 중·338개) 교체 → 본편: 한 단락 요지 → 핵심 수치표 → 발견 3~5줄 → 한계·가정 → 문서 지도(SPEC·스파인·에픽·스키마·사양서·절차서) → 재현 절차(기존 셋업 절 유지).
  - [x] 수치: 분면 4,624/2,971/2,089/443 · 컷 0.132753/3,899 · 총합 ≈1,454,088 · PR-AUC 0.9508(+40.8%) · 10,127행. 테스트 수는 환경 기준 병기.
- [x] **T3 — 퍼블리시 절차서** (AC3)
  - [x] `docs/tableau-publish-runbook.md` 신설: AC3 ⓪~⑥ + 단계별 의심 포인트. OQ-5(계정 미확인)를 ⓪단계 전제로 명시.
- [x] **T4 — 문서=계약 테스트** (AC4)
  - [x] README 수치표·가정 문구·절차서 앵커 단언(4-3 `_slice`/`_section` 패턴 재사용 — 중복 구현 대신 공용화 검토, 과하면 로컬 복제 허용).
- [x] **T5 — 회귀·마감** (전 AC)
  - [x] 전체 회귀 0(기준선 **391 passed**, churn 제외). 마트·스키마·사양서·crm·pipelines **바이트 불변**.
  - [x] 문서 체크리스트 DoD: README·runbook·스토리·sprint-status. epic-4 잔여 확인(4-2 blocked 유지).

## Dev Notes

### 스토리 결정 (create-story — 이견 시 HALT)

- **D1 (AC1)**: 커밋 이력 스캔은 일회 감사(기록), 현재 트리 무결은 pytest 영구 가드 — 이력은 불변이라 반복 검사가 무의미하고, 미래 유입은 트리 검사가 잡는다.
- **D2 (AC2)**: README 테스트 수는 "churn 제외 391(xgboost 미설치 환경)" 기준 병기 — 단일 수를 확정 사실처럼 쓰면 환경 의존을 숨긴다(4-1a Debug Log 선례). 골든 수치는 환경 무관(마트 결정론).
- **D3 (AC3)**: 절차서 위치 `docs/tableau-publish-runbook.md` — 사용자 실행 문서라 marts/(데이터 계약면)가 아닌 docs/.

### 실측 재료

- README 현황: 헤더 stale(에픽3 진행 중·338), 본편 "4-4에서 작성" 명시 — 셋업·데이터 확보 절은 유효하니 보존.
- 골든값 출처: `tests/marts/test_customers.py` 골든 단언 + `marts/dashboard-spec.md` 검산 앵커(동시 갱신 계약 3중화됨 — README가 세 번째 사본이 되니 동시 갱신 계약 명시).
- PR-AUC 0.9508·lift +40.8%: `models/churn_model.meta.json` metrics(커밋 경로: 03 스테이지 산출).
- gitignore: `data/`·`models/` 제외 확인 완료(1-1a 테스트 존재).

### 범위 밖

- 워크북 제작·퍼블리시·링크 확보 — **daria 몫**(절차서가 안내). 링크 미확보로 done 블로킹 금지.
- 사양서·스키마·마트·코드 변경 — 읽기 전용. 에픽4 회고는 별도.

### Testing standards

- 4-3 교훈 3종 적용: 미검증 항목=표류 항목(수치표 전 골든 단언) · 종료 앵커 단언 · 표는 파싱하는 칸만 출처.

### Project Structure Notes

- **신규**: `docs/tableau-publish-runbook.md`, `tests/docs/__init__.py`, `tests/docs/test_public_release.py`.
- **수정**: `README.md`, sprint-status, 스토리 파일.
- **불변**: marts/*·crm/*·pipelines/*·tests/marts/*.

### References

- [Source: docs/planning-artifacts/epics.md#Story 4.4] — AC 원문(AD-10·NFR7·NFR8·FR18)
- [Source: README.md] — 현행 구조(보존 절 확인)
- [Source: marts/dashboard-spec.md] — 검산 앵커·제작 규약(절차서가 참조)
- [Source: docs/implementation-artifacts/sprint-status.yaml OQ-5] — 계정 미확인·blocked-external 설계

## Dev Agent Record

### Agent Model Used

claude-opus-5 (Claude Code, dev-story workflow)

### Debug Log References

- **공개 점검 실측(AC1, 2026-07-24)**: `git log --all --name-only` 전 이력 스캔 — `.parquet`·`.joblib`·`.pkl` 유입 **0건**. CSV 히트는 툴링 매니페스트(.claude/_bmad)와 의도된 `marts/mart_customers.csv`(AD-2)뿐. 현재 추적 파일 아티팩트 0건 — `tests/docs/test_public_release.py`가 영구 가드로 고정. 마트 컬럼 유래: 전 10컬럼이 스키마 문서 산출 모듈 칸 기준 BankChurners 유래·파생(CLIENTNUM은 공개 원본의 ID).
- **줄바꿈 함정 재발·즉시 검출**: 절차서의 "공개 조회 가능"이 줄바꿈에 갈라져 계약 테스트 red — 4-3 교훈이 이번엔 red로 먼저 잡았다(문서-계약 테스트가 일하는 증거).

### Completion Notes List

- ✅ **AC1**: 이력 스캔 0건(기록 위) + 트리 무결 pytest 영구 가드(추적 parquet/joblib/pkl 0, 추적 CSV는 마트 유일) + 공개 고지(README·절차서).
- ✅ **AC2**: README 본편 — 핵심 수치표(골든 3중 동시 갱신 계약 명시)·발견 4줄·한계와 가정(4종+동결+환경 병기 D2)·문서 지도 7항·링크 자리 표시. 셋업·데이터 확보 절 보존.
- ✅ **AC3**: `docs/tableau-publish-runbook.md` ⓪~⑥ + 단계별 의심 포인트. OQ-5는 ⓪ 전제.
- ✅ **AC4**: `tests/docs/` 신설 6건 — 추적 아티팩트 0·마트 유일 CSV·README 골든 라벨 일치·가정 4종·미수행 정직·절차서 앵커.
- **회귀**: 391 → **397 passed**(+6), 마트·사양서·crm·pipelines 바이트 불변.
- **daria 몫(비블로킹)**: 계정 확인(OQ-5)→워크북→퍼블리시→링크 기입 — 절차서 체크리스트만 남음.

### File List

**신규**: `docs/tableau-publish-runbook.md`, `tests/docs/__init__.py`, `tests/docs/test_public_release.py`
**수정**: `README.md`(본편 재작성, 셋업 절 보존), sprint-status, 스토리 파일

### 공개 점검 — 마트 컬럼 유래 점검표 (AC1 ①, 리뷰 결함2 반영)

| 컬럼 | 산출 모듈 | 유래 |
|---|---|---|
| `CLIENTNUM` | 원본(BankChurners) | 공개 원본의 고객 ID 그대로 |
| `segment_id` | `crm/segment/segments.py` | BankChurners RFM 프록시의 K-means 파생 |
| `customer_value` | `crm/segment/value.py` | BankChurners `Total_Trans_Amt` 원척도 |
| `churn_score` | `crm/churn/model.py` | BankChurners 피처 8종의 OOF 모델 점수 |
| `churn_prob_calibrated` | `crm/churn/calibrate.py` | 위 점수의 Platt 보정 |
| `quadrant_official` | `crm/campaign/matrix.py` | 위 두 축의 분위 컷 파생 |
| `threshold_official_risk` | `crm/campaign/matrix.py` | churn_score 0.75분위(모집단 파생) |
| `threshold_official_value` | `crm/campaign/matrix.py` | customer_value 중위(모집단 파생) |
| `expected_saving` | `crm/campaign/simulate.py` | 보정확률×가치×정책가정 산식 파생 |
| `target_priority` | `crm/campaign/priority.py` | expected_saving 순위 파생 |

전 10컬럼이 공개 데이터셋(BankChurners) 유래·파생 + 선언된 정책가정뿐 — 외부·비공개 정보 유입 0.

### Senior Developer Review (AI) — 2026-07-24

**방식**: 3레이어 병렬(Blind/Edge/Auditor) → 파티 판정(daria 전권 위임). **Auditor: AC 전건 부분 충족(Major 1) — done 전 수정 권고 → 전건 처분 후 done.**

**핵심 결함과 처분(전건 해소, 401 passed)**:
- [x] **H1/결함1 (Major) — README "391 passed"가 자기 커밋으로 즉시 stale**: "미검증 항목=표류 항목"의 교과서적 재발(보호 안 된 유일한 수치 칸이 표류). → done 커밋 기준 최종 수치(401)로 마지막에 기입 + "done 커밋 기준" 명시.
- [x] **H3/E6 (High) — 골든 하드코딩 4중 사본**: `tests/marts/goldens.py` **단일 출처 모듈 신설** — 마트 골든 테스트·README 계약 테스트가 전부 import, 문서 3종은 사본임을 명시. 표류 시 한 지점에서 전부 red.
- [x] **H2 (High) — PR-AUC 출처가 미커밋 아티팩트인데 "전부 커밋" 주장**: 표 서두·출처 칸 정직화("gitignored 아티팩트, 03 재실행으로 재생성") + 테스트가 "재생성" 문구 단언.
- [x] **E2 (High, false green) — git quotepath 이스케이프로 비ASCII CSV 가드 통과**: `-c core.quotepath=false` + `-z` + UTF-8 bytes 디코딩.
- [x] **E1 (High) — git 부재/비리포/타임아웃이 "위반"으로 오판**: skip 처리(환경 부재≠위반, D2 정신).
- [x] **E3/E4 (High) — 아티팩트 가드 커버리지**: `data/`·`models/` **경로 프리픽스 단언**(닫힌 집합 — xgboost `model.json`까지 커버) + 확장자 17종 확대.
- [x] **결함2 — 컬럼 단위 점검표 미동봉**: 위 표로 동봉.
- [x] **결함3/M3/M4/E12/E13/E14 — 절차서 보강**: 전 단계 의심 포인트·탭4 스텁 지시·10컬럼 타입 전열거·표기 무시+±1 대조 규칙·range 모드 파라미터·budget=0 캡션. 테스트 단언 추가.
- [x] **E8/E10/결함4 — 슬라이스 견고화**: `_readme_section` 양 앵커 단언·라인 정규식, 정직 절 검사를 절-한정으로.
- [x] **결함5 — 발견 절 수치 무방비**: x17.27·8,587·+19.0%·+37.2% 단언 신설.
- [x] **E11/L3 — 링크 자리 가드**: "자리 표시 OR 공개 링크" 양자택일 단언.
- [x] **M5/M6 — 검산 기준**: ±1 허용오차 명시, 절차서 수치 사본 제거(사양서 표 단일 포인터).
- **기각**: E5(fixture CSV 예외 — 신규 CSV red는 의도된 공개 게이트 마찰), E7/E9(헤딩 유연화 — 구조 고정이 목적), L1(done 처리로 해소), E15(skip 로직에 흡수), 7(±1은 문서에 명시로 충분).

### Change Log

- 2026-07-24: 4-4 세션 몫 구현 — 공개 점검(이력 0건+영구 가드), README 본편(골든 수치표·가정·정직 절), 퍼블리시 절차서. 397 passed, 마트·코드 불변.
- 2026-07-24: 코드리뷰(3레이어+파티) 반영 — goldens.py 단일 출처 신설(4중 사본 해소), README 정직화(테스트 수 done 기준·PR-AUC 출처), git subprocess 견고화(quotepath false green 봉인·skip), 경로 프리픽스 가드, 절차서 전면 보강, 슬라이스 양 앵커. 397→401 passed(회귀 0), 마트·사양서·코드 불변.

---

**기준선**: 4-3 done 커밋 `1927df0`. 이 환경 **391 passed**(churn 제외). 마트·사양서·코드 바이트 불변이 DoD.

**Ultimate context engine analysis completed — comprehensive developer guide created.**
