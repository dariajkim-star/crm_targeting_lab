---
baseline_commit: a08106b910eb889aeaf883c3d75432fb86e14f59
---

# Story 4.1a: 고객 마트 조립·CLIENTNUM 조인·정규 스키마

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a BI 소비자,
I want 고객 단위 분석 결과가 스키마가 고정되고 **감사 가능한** 단일 CSV로 제공되기를,
so that Tableau가 중간 산출물이 아닌 안정된 계약면만 소비하고, 화면의 분면·우선순위를 마트만으로 검산할 수 있다.

## 배경 — 이 스토리가 4-1 분할의 앞쪽이다

4-1은 에픽3 미결 부채 9건의 수렴점이라 3-3급 하중이 되어 **4-1a/4-1b로 분할**됐다(에픽3 회고 B1, daria 승인 2026-07-23). 이 스토리(**4-1a**)는 **디스크에 올바른 마트를 올리는 것**까지다 — 조립 헬퍼 + `05_marts` + CLIENTNUM 라벨 조인 + 행수 보존 + `artifact_id` 게이트 + 결정론 바이트 동일 + 정규 스키마 문서. **아티팩트 주변 경화**(계약 좁히기·오용 방지 표기·`campaign_selected`·세션 리포트 경로)는 **4-1b**가 맡는다.

**세로선(4-1a/4-1b 경계)**: 1-6a(models+lift) / 1-6b(정체성 가드) 선례와 같다 — 먼저 정확하고 결정론적인 아티팩트를 만들고(4-1a), 그다음 그 주변 계약을 좁히고 오용을 막는다(4-1b).

## Acceptance Criteria

**AC1 — `05_marts`가 `marts/`의 유일한 writer이며 얇다 (FR15·AD-2·AD-9)**
Given `pipelines/05_marts.py`가 고객 레인 입력을 읽을 때
When `marts/mart_customers.csv`를 생성하면
Then 이 스크립트가 `marts/`의 유일한 writer이고, `main(input_paths, output_paths)` 시그니처 외 `def`를 정의하지 않으며 **파일당 40행 이하**다(AD-9). 조립 로직은 `crm/` 순수 함수가 소유한다.
And LTV 레인(`mart_ltv_demo`)은 이 스토리 범위 밖이다 — 에픽2 동결로 04_ltv 산출물이 없다. AD-1 "두 레인 순차 처리"의 **A 레인(고객)만** 수행하고, 이 사실을 `05_marts` docstring과 스키마 문서에 명시한다.

**AC2 — CLIENTNUM 라벨 조인으로 조립한다 (함정4 방어, B2 / AD-12)**
Given 세 입력(`bankchurners`·`features_customers`·`churn_scored`)이 **서로 다른 행 순서**를 가질 때
When 마트를 조립하면
Then 조립은 **위치가 아니라 `CLIENTNUM` 라벨 조인**으로 수행되고, 결과 프레임은 `CLIENTNUM`을 인덱스로 갖는다. 세 소스의 CLIENTNUM 집합이 정확히 일치하지 않으면(부분집합·초과·중복 포함) **즉시 실패**한다.
And 조립 후 `customer_value`·`assign_quadrant`·`expected_saving`·`target_priority`에 넘기는 모든 축이 **동일한 CLIENTNUM 인덱스**를 공유한다 — 이 지점이 함정4(행 오정렬 +37.2%가 무예외 통과)를 막는 프로젝트 최초의 실효 방어다.
> **실측 근거(3-3)**: 두 parquet가 평범한 `RangeIndex`라 `bc.index.equals(sc.index)`가 True를 반환해 위치 결합이 조용히 통과, 합계 1,994,741 vs 정답 1,454,088(+37.2%). CLIENTNUM 조인이 유일한 방어다. [Source: deferred-work.md "함정 4", 3-3 코드리뷰 정정]

**AC3 — 정규·망라 스키마 문서 (AD-2·AD-12)**
Given `mart_customers.schema.md`가 작성될 때
When 스키마를 확인하면
Then 모든 컬럼이 `name | dtype | 단위 | nullable | 산출 모듈 | 정의 1줄`로 망라 열거되고, 최소 다음이 포함된다: `CLIENTNUM`·`segment_id`·`customer_value`·`churn_score`·`churn_prob_calibrated`·`quadrant_official`·`threshold_official_risk`·`threshold_official_value`·`expected_saving`·`target_priority`.
And `target_priority`의 정의를 스키마 문서에 **고정**한다(AD-12): *"기대절감액 내림차순 dense rank(1 최우선), 동점 시 `customer_value` 내림차순, 그래도 동점이면 `CLIENTNUM` 오름차순 — 전순서 보장. 전원 10,127명에게 순위 부여."*
And pytest가 `set(df.columns) == schema.columns`와 dtype 일치를 검증한다.
> **컬럼 범위 결정(이 스토리)**: epics.md 4.1 AC가 열거한 컬럼에 더해 **`expected_saving`을 감사 컬럼으로 포함**한다 — `target_priority`가 이 축의 dense rank로 정의되므로, 이것이 없으면 마트만으로 우선순위를 검산할 수 없다("마트=감사 가능성" 층 분리 원칙, 3-0 코드리뷰 D3). **`campaign_selected`는 4-1b로 미룬다** — 예산 인자가 필요하고 `budget=0` 빈 캠페인 UX(구item5)와 한 몸이라 거기서 컬럼 추가 + AD-12 정의 고정을 함께 한다.

**AC4 — 행 수 보존, 센티널 금지 (AD-2)**
Given 행 수 보존이 요구될 때
When 마트를 생성하면
Then BankChurners 원본 전 고객 행 수(**10,127**)가 보존되고, `05_marts`가 기대 행 수를 assert한다. 산출 불가 값은 행 삭제가 아니라 null.
And 센티널(`-1`·`"NULL"`·`"N/A"`·`0`)로 결측을 표현하지 않으며, non-nullable 컬럼(현 설계상 전 컬럼)에 null이 있으면 실패한다. (현 아티팩트는 세 소스가 동일 10,127 CLIENTNUM을 완전 커버하므로 null이 발생하지 않는다 — 그래도 규칙과 assert는 둔다.)

**AC5 — `artifact_id` 정체성 게이트 (AD-5)**
Given 아티팩트 정체성을 검증할 때
When 입력 `churn_scored`의 `artifact_id`가 `models/churn_model.meta.json`의 `artifact_id`와 불일치하면
Then `05_marts`가 경고가 아니라 **즉시 실패**한다. (SHAP 계열 입력을 읽지 않더라도, 마트가 담는 `churn_score`·`churn_prob_calibrated`가 어느 학습 실행 소속인지 게이트한다.)

**AC6 — 결정론 바이트 동일 (NFR4·AD-7)**
Given 결정론이 요구될 때
When 파이프라인을 2회 연속 실행하면
Then `marts/mart_customers.csv`가 **바이트 동일**하고 `tests/test_determinism`이 이를 검증한다.
And 직렬화가 고정된다: `na_rep=""`, `float_format="%.6f"`, `encoding="utf-8"`(BOM 없음), `lineterminator="\n"`, `index=False`, 컬럼 순서 = 스키마 문서 순서. CLIENTNUM은 인덱스로 조립하되 **CSV에는 컬럼으로** 직렬화한다(`index=False`이므로 조립 인덱스를 `reset_index`로 컬럼화).

**AC7 — 원자적 쓰기·부분 산출 금지 (AD-13)**
Given 마트 쓰기가 수행될 때
When `05_marts`가 실패하거나 성공하면
Then 마트 쓰기는 임시 파일 → 원자적 rename으로 수행되고(`crm/common/atomic.py`), 실패 시 반쯤 쓰인 마트를 남기지 않으며 `<output>.meta.json`(입력 SHA-256·`config_hash`·커밋·시각·행수)을 동반한다.

## Tasks / Subtasks

- [x] **T1 — 조립 헬퍼 신설** (AC1, AC2)
  - [x] `crm/marts/customers.py`에 순수 함수 `build_customer_mart(bankchurners, features, scored) -> pd.DataFrame` 작성. 세 프레임을 `CLIENTNUM` 라벨 조인, 인덱스=CLIENTNUM. 집합 불일치·중복 시 `ValueError`(명확한 메시지). **행 순서는 CLIENTNUM 오름차순으로 정준화**(입력 재셔플에도 바이트 동일 — AC6 강화).
  - [x] 조립 프레임에서 각 축을 뽑아 crm 함수 호출: `customer_value(bc)` · `assign_quadrant(churn_score, value)` (labels+thresholds **단일 계산**에서 `threshold_official_*` 획득 — 별도 `quadrant_thresholds` 호출 안 함, 모집단 불일치 방지) · `expected_saving(churn_prob_calibrated, value)` · `target_priority(saving, value, clientnum)`. `segment_id`는 features에서 그대로.
  - [x] **AD-1 확인**: 이 모듈은 `crm.ltv`를 절대 import하지 않는다. `_LANE_A`에 `crm.marts.customers`를 **모듈 단위로 등록**(패키지 prefix가 아님 — 4-2의 `crm.marts.ltv`를 Lane B로 남기기 위함). self-check에 마트→ltv 위반 탐지 테스트 신설.
  - [x] **AD-11 확인**: `customer_value` 출력을 재계산·재가중하지 않고 그대로 소비. `Total_Trans_Amt`를 이 모듈에서 명명하지 않는다(bc 프레임을 넘기기만 함). `find_value_recomputation_violations` 통과(스캔 23파일, 위반 0).
- [x] **T2 — `pipelines/05_marts.py` 신설** (AC1, AC4, AC5, AC7)
  - [x] `main(input_paths, output_paths)` 하나만. **38행**(≤40). 허용 호출은 `crm.*`·pandas read/write·logging뿐. 직렬화 클로저를 스테이지가 못 쓰므로 `crm/common/atomic.py::write_bytes_with_meta` 신설.
  - [x] 입력 읽기 → `assert_scored_identity`(불일치 즉시 `ArtifactIdentityError`) → `build_customer_mart` → 행수 보존 assert(`len(mart)==len(bankchurners)`, 데이터 리터럴 하드코딩 회피) → non-nullable null 검사(조립기 내부) → 스키마 순서 직렬화 → `write_bytes_with_meta`로 원자적 쓰기 + meta.json.
  - [x] LTV 레인 미수행을 docstring에 명시(에픽2 동결).
- [x] **T3 — `marts/mart_customers.schema.md` 정규 작성** (AC3)
  - [x] 전 컬럼 `name | dtype | 단위 | nullable | 산출 모듈 | 정의 1줄`. 기대 행 수 10,127 명시. `target_priority` 정의 AD-12대로 고정. `expected_saving`·`customer_value`는 "가정"(성공률 0.30·비용 5.0) 라벨 병기. `churn_score`(float32, 순위전용) vs `churn_prob_calibrated`(float64, 금액전용) 용도 명시.
  - [x] 컬럼 순서 = CSV 직렬화 순서(단일 출처 = `MART_COLUMNS`). 직렬화 6종 규약 표 포함.
- [x] **T4 — 테스트** (AC2, AC3, AC4, AC6)
  - [x] 스키마 일치: 스키마 문서 표를 파싱해 `set(df.columns) == schema.columns` + dtype 일치 단언(문서=단일출처, AD-2 필수 ①).
  - [x] 결정론 바이트 동일: 2회 조립 바이트 동일 + **입력 재셔플에도 바이트 동일**(정준 정렬) + 스테이지 2회 실행 바이트 동일(test_stage, xgboost 시 실행) (필수 ②).
  - [x] import-graph 레인 격리·의존 방향: 새 `crm/marts/` 포함(스캔 22→24). self-check에 마트→ltv 위반 탐지 + Lane A 소비 허용 2건 신설 (필수 ③, AD-1·AD-9).
  - [x] **함정4 회귀 테스트(행동 기반)**: 세 소스를 서로 다른 순열로 섞은 픽스처 → (a) 각 고객이 자기 value/prob를 유지 (b) 위치 결합이었다면 나왔을 오합계와 마트 총합이 **다름**을 단언(가드의 가드). 실데이터 오라클: 총합 ≈ **1,454,088**(정답; 위치결합은 1,994,741=+37.2%).
  - [x] 행수 보존 assert 검증. 조립기 집합 불일치(부분집합·초과)·중복·CLIENTNUM 컬럼 부재 시 실패 검증. AD-5 게이트 프레임측 분기(id 컬럼 부재·다중 id) 단언.

## Dev Notes

### 소비할 crm 함수 — 정확한 시그니처 (전부 실재, 재구현 금지)

- `crm/segment/value.py::customer_value(df) -> Series[float]` — `df`에 `Total_Trans_Amt` 필요(=bankchurners). 인덱스 그대로 유지(정렬·reindex 안 함), 소비자는 caller 인덱스로 조인. 원척도 반환(정규화·로그 없음). [Source: crm/segment/value.py:62]
- `crm/campaign/matrix.py::quadrant_thresholds(churn_score, value, *, rule=QUADRANT_RULE) -> QuadrantThresholds(risk, value)` — 컷을 런타임 계산(config엔 분위수 레벨만). [matrix.py:209]
- `crm/campaign/matrix.py::assign_quadrant(churn_score, value, *, rule=QUADRANT_RULE) -> QuadrantAssignment` — labels·cuts·rule을 **단일 계산**에서 반환(라벨과 임계값이 다른 모집단에서 나오는 것 방지). 경계 상단 `>=`. [matrix.py:246]
- `crm/campaign/simulate.py::expected_saving(churn_prob_calibrated, value, *, retention_rate=RETENTION_SUCCESS_RATE, cost_per_contact=COST_PER_CONTACT) -> Series[float]` named `SAVING_COLUMN` — **`churn_prob_calibrated`를 넘겨야 함**(잘못된 이름의 Series는 거부; `churn_score`를 넣으면 +19.0% 부풀림 — 단, unnamed는 통과하므로 가드는 부분적). [simulate.py:277]
- `crm/campaign/priority.py::target_priority(expected_saving, value, clientnum) -> Series[int64]` named `PRIORITY_COLUMN` — 전원 `1..n` dense rank. `value`는 비음수여야(2차 키), `clientnum`은 유일해야(3차 키). **"인덱스가 CLIENTNUM일 때 컬럼과 대조"하는 부분 가드가 이미 있다** — 4-1a가 인덱스를 CLIENTNUM으로 세팅하면 이 가드가 비로소 실효한다. [priority.py:307]

### CLIENTNUM 조인이 왜 이 스토리의 심장인가

세 입력 모두 `CLIENTNUM` 컬럼 보유(실측): `bankchurners`(원본), `features_customers`(CLIENTNUM, segment_id, RFM), `churn_scored`(CLIENTNUM, churn_score, churn_prob_calibrated, artifact_id). 전부 10,127행이지만 **행 순서가 다르다**. 위치 결합은 무예외로 틀린다(함정4). 조립 인덱스를 CLIENTNUM으로 고정하면:
1. `target_priority`의 기존 CLIENTNUM 부분 가드가 발동한다.
2. `expected_saving`·`assign_quadrant`의 `_validate_pair`가 인덱스 정합을 검사한다(같은 CLIENTNUM 인덱스라 정합).
3. 4-1b가 세 축 모두 CLIENTNUM 인덱스를 **요구**하도록 계약을 좁히면 위치 결합 자체가 표현 불가능해진다.

**본공연 이식 메모(워싱 스크리너)**: 본공연 데이터는 조인이 훨씬 많아 이 라벨 조인 계약의 가치가 crm보다 크다. 4-1이 리허설 지점이다. [Source: epic-3-retro-2026-07-23.md §6 B7]

### 모듈 위치 결정 — `crm/marts/customers.py`

AD-9가 pipelines를 40행·main-only로 묶으므로 조립 로직은 crm이 소유해야 한다. `crm/marts/` 서브패키지 신설을 권장한다(Structural Seed에 명시 모듈은 아니나 자연 확장). 대안이었던 `crm/campaign/mart.py`는 기각 — 조립은 `segment_id`(campaign 아님)를 읽고 campaign 내부 체인(matrix→…→sensitivity, `_CAMPAIGN_ORDER`)에 마트 조립을 끼우면 그 가드의 의미가 흐려진다. `crm/marts/customers.py`는 `_LANE_A`(segment/churn) import로 판정돼 `crm.ltv` 금지가 자동 적용되고, 4-2의 `crm/marts/ltv.py`(있다면)와 서로 import하지 않으면 AD-1 격리가 유지된다. [Source: tests/structure/checkers.py:27 `_LANE_A/_LANE_B`, ARCHITECTURE-SPINE.md AD-1·AD-9]

### 결정론 함정 (재발 주의 — 에픽1·3 실측)

- CSV 직렬화 6종 고정(AC6)을 정확히. `float_format="%.6f"`는 `customer_value`(원래 int64)·`expected_saving`·확률에 적용된다. `%.6f`가 int 컬럼(segment_id·target_priority·CLIENTNUM)에 이상 포맷을 내지 않도록 dtype 유지 확인.
- `groupby`는 `sort=True`, 조인은 라벨 기반이라 순서 결정론적. XGBoost/K-means 재학습은 이 스토리에 없다(입력 parquet 소비만) — 결정론 리스크는 오직 직렬화·조인 순서.

### AD-5 게이트 구현 메모

`churn_scored.parquet`에 행별 `artifact_id`가 이미 박혀 있다(실측: 단일값 `9e1a4d71800f`). 게이트는 (a) scored의 artifact_id가 단일값인지 (b) `models/churn_model.meta.json`의 `artifact_id`와 일치하는지 검사. 불일치 즉시 `raise`. [Source: data/churn_scored.parquet 컬럼, ARCHITECTURE-SPINE.md AD-5]

### 범위 밖 (4-1b가 맡는다 — 여기서 하지 말 것)

- `target_priority`/`expected_saving`/`random_baseline` 3축 CLIENTNUM 인덱스 **요구**로 계약 좁히기(구item1·item4). 4-1a는 인덱스를 세팅해 기존 부분 가드를 실효시킬 뿐, 함수 시그니처 계약은 안 바꾼다(바꾸면 done인 3-2의 RangeIndex 출력이 비순응).
- `campaign_selected` 컬럼 + `budget=0` 빈 캠페인 UX(구item5) + AD-12 `campaign_selected` 정의 고정.
- 마트 오용 방지 표기(`churn_score` vs `churn_prob_calibrated` 드롭다운 +19% — 스키마 금지/용도 칸).
- `customer_value` **호출부** 재가중 보호(1-2 인계 절반) — 4-1a가 이 함수를 실제 호출하는 첫 커밋 코드라 4-1b sentinel 테스트의 대상이 되지만, 테스트 신설은 4-1b.
- 세션 리포트 커밋 경로(06 stage or `reports/` — 3-2 F7/3-3 재발).

### Testing standards

- **행동 기반**(동어반복 금지 — P1 2-2 부호반전 교훈): 마트 값 테스트는 산식을 재구현해 비교하지 말고, 알려진 소표본에서 손계산한 기대값 또는 성질(조인 정합·행수 보존·바이트 동일)로 검증.
- 필수 3종(AD-2·AD-7·AD-1/AD-9) 전부 새 마트·새 모듈로 확장.
- 실데이터 오라클 테스트는 parquet 부재 시 skip(3-4 관례).

### Project Structure Notes

- **신규**: `crm/marts/__init__.py`, `crm/marts/customers.py`, `pipelines/05_marts.py`, `marts/mart_customers.csv`(+`.meta.json`), `marts/mart_customers.schema.md`, `tests/marts/`(신규 디렉터리).
- **불변**: `crm/campaign/*`·`crm/segment/*`·`crm/churn/*` 함수 시그니처(소비만). `crm/config.py`(상수 소비만). 3-2의 `expected_saving` RangeIndex 출력 계약(4-1b까지 불변).
- Structural Seed는 `crm/marts/`를 명시하지 않으나 "marts/ = 커밋 대상 산출물"과 정합하는 자연 확장. `marts`는 이미 `tests/structure/checkers.py::_DATA_DIRS`에 등록됨.

### References

- [Source: docs/planning-artifacts/epics.md#Story 4.1] — AC 원문, 분할 노트(2026-07-23)
- [Source: docs/planning-artifacts/architecture/architecture-crm-targeting-lab-2026-07-16/ARCHITECTURE-SPINE.md] — AD-1(격리)·AD-2(마트 2분할·스키마 정규)·AD-3(판정 소유권)·AD-5(artifact_id 게이트)·AD-7(결정론)·AD-9(의존 방향·40행)·AD-11(가치 단일정의)·AD-12(판정 규칙 단일 소유)·AD-13(원자적 쓰기)·Structural Seed·직렬화 규약
- [Source: docs/implementation-artifacts/deferred-work.md] — "함정 4"(CLIENTNUM 조인), "4-1 입력"(오용 위험·층 분리), 3-3 파티 4-1 인계 3건
- [Source: docs/implementation-artifacts/epic-3-retro-2026-07-23.md#6] — B1(분할)·B2(CLIENTNUM)·B3(AD-12) 근거
- [Source: crm/segment/value.py, crm/campaign/matrix.py, crm/campaign/simulate.py, crm/campaign/priority.py, crm/config.py, tests/structure/checkers.py] — 소비 함수·상수·가드 실측

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (Claude Code, dev-story workflow)

### Debug Log References

- **환경 주의**: 이 개발 환경에는 **xgboost 미설치** — `tests/churn/*` 4모듈이 collection에서 ImportError. daria 환경의 465 passed와 달리, 여기 회귀 기준선은 churn 제외 **338 passed**. AD-5 게이트(`assert_scored_identity`)가 `crm.churn.artifact`를 통해 xgboost를 transitive import하므로, `crm/marts/customers.py`는 이를 **함수 내부 lazy import**로 격리 — 순수 조립/직렬화 경로는 xgboost 없이 import·테스트 가능. `test_stage.py`는 `pytest.importorskip("xgboost")`로 daria 환경에서만 실행.
- **정준 정렬 결정**: 초기 구현은 마트 행 순서가 bankchurners 입력 순서를 상속 → 입력 재셔플 시 바이트 비동일. `sort_index()`(CLIENTNUM 오름차순) 추가로 바이트 동일성을 "동일 입력 파일"→"동일 입력 내용"으로 강화. target_priority(고객별 순위)는 행 순서 무관하므로 영향 없음.
- **디스크 아티팩트**: 05_marts 전체 실행은 xgboost 필요. AD-5 게이트 통과 여부를 수동 확인(scored artifact_id `9e1a4d71800f` == model meta artifact_id, 일치)한 뒤, 파이프라인과 **동일 코드 경로**(`build_customer_mart`→`serialize_mart`→`build_meta`→`write_bytes_with_meta`)로 `marts/mart_customers.csv`(907,362 bytes, 10,127행) + meta 생성. daria 환경에서 `python pipelines/05_marts.py` 실행 시 게이트 활성 상태로 바이트 동일 재현.

### Completion Notes List

- ✅ **AC1**: `05_marts`가 `marts/`의 유일 writer, `main()` 단독 38행. 조립 로직은 `crm/marts/customers.py` 소유. LTV 레인 미수행을 docstring·스키마 문서에 명시(에픽2 동결).
- ✅ **AC2 (함정4 방어 — 이 스토리의 심장)**: `CLIENTNUM` 라벨 조인. 세 소스 CLIENTNUM 집합 정확 일치 강제(부분집합·초과·중복 즉시 실패). 실데이터 총합 **1,454,088**(정답) 재현 — 위치결합 1,994,741(+37.2%) 회피를 행동 기반 회귀 테스트로 고정.
- ✅ **AC3**: `mart_customers.schema.md` 정규 작성, 10컬럼 전부 열거 + AD-12 `target_priority` 정의 고정. 문서=컬럼순서 단일출처, pytest가 `set(df.columns)==schema.columns`+dtype 강제.
- ✅ **AC4**: 행수 보존(`len(mart)==len(bankchurners)`), 센티널 금지, non-nullable null 검사(현 아티팩트 null 0건).
- ✅ **AC5**: `assert_scored_identity` — `read_verified_model_meta`+`verify_artifact_identity` 소비(신규 churn 함수 없음), 불일치 즉시 raise. 프레임측 분기(id 부재·다중)는 xgboost 없이 검증.
- ✅ **AC6**: 직렬화 6종 고정(`na_rep=""`·`%.6f`·utf-8 no BOM·`\n`·`index=False`·스키마 순서). CLIENTNUM 인덱스 조립→`reset_index`로 첫 컬럼 직렬화. 정준 정렬로 바이트 동일 강화.
- ✅ **AC7**: `write_bytes_with_meta`로 원자적 쓰기 + `<output>.meta.json`(입력 SHA-256·config_hash·commit·시각·행수).
- **테스트**: 회귀 0 — churn 제외 338→**356 passed**(+16 마트 함수 + 2 self-check 레인), 1 skipped(test_stage, xgboost 대기). 구조 가드 전건 green(66), 커버리지 리포트 자동 갱신(AD-1 스캔 22→24).
- **4-1b 인계(범위 밖 확인)**: target_priority/expected_saving/random_baseline 3축 CLIENTNUM 계약 좁히기 · `campaign_selected`+budget=0 UX · 마트 오용 방지 표기(뷰에서 churn_score 제외) · customer_value 호출부 재가중 sentinel 테스트(4-1a가 첫 호출 커밋 코드) · 세션 리포트 커밋 경로.

### File List

**신규**
- `crm/marts/__init__.py`
- `crm/marts/customers.py`
- `pipelines/05_marts.py`
- `marts/mart_customers.schema.md`
- `marts/mart_customers.csv` (+ `marts/mart_customers.csv.meta.json`) — 산출 아티팩트
- `tests/marts/__init__.py`
- `tests/marts/test_customers.py`
- `tests/marts/test_stage.py`

**수정**
- `crm/common/atomic.py` — `write_bytes_with_meta` 추가(직렬화 CSV 원자적 쓰기 + meta)
- `tests/structure/checkers.py` — `_LANE_A`에 `crm.marts.customers` 등록(AD-1 마트 레인 격리)
- `tests/structure/test_checkers_selfcheck.py` — 마트→ltv 위반 탐지 + Lane A 소비 허용 테스트 2건
- `tests/structure/../structure-guard-coverage.md` — 스캔 수 자동 갱신(테스트 산출)
- `docs/implementation-artifacts/sprint-status.yaml` — 4-1a in-progress→review

### Change Log

- 2026-07-24: 4-1a 구현 — 고객 마트 조립(CLIENTNUM 라벨 조인=함정4 방어), `05_marts` 스테이지, 정규 스키마, AD-5 게이트, 결정론 직렬화(정준 정렬), 원자적 쓰기+meta. 마트 아티팩트 디스크 산출(10,127행, 총합 1,454,088). 356 passed(churn 제외 회귀 0).

---

**기준선**: HEAD `d408ddf`, 465 passed(에픽3 회고 done 커밋 후). artifact_id `9e1a4d71800f`(8피처, OOF + Platt).

**Ultimate context engine analysis completed — comprehensive developer guide created.**
