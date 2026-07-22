---
baseline_commit: c702b95
baseline_passed: 242
---

# Story 1.7: SHAP 이탈요인 해석과 리텐션 액션 매핑

Status: done

> **범위 확대 결정(2026-07-21)**: 원 스토리는 SHAP만이었으나, **예측자 3개(RFM 프록시)로는 CAP-3이 성립하지 않는다**는
> 것이 실증됐다 — "거래가 줄어서 이탈 위험이 높다"는 순환논법이고, SPEC CAP-3이 예시로 든 **"한도 불만형 → 한도 상향"**을
> 판별할 피처가 X에 없다. 따라서 이 스토리는 **이탈 신호 피처 확장 → SHAP → 액션 매핑**을 한 줄기로 수행한다.
> 확장은 **raw 프레임 경유**라 `features_customers`(CAP-1 세그멘테이션 소관)는 **손대지 않는다** → 1-4/1-5 회귀 0.
>
> **분할 사전 승인**: dev 컨텍스트가 부족하면 **1-7a(피처 확장 + 모델 재산출) / 1-7b(SHAP + 액션 매핑)**으로 나누고
> sprint-status를 갱신할 것(1-6 분할 선례). 나눌 경우 1-7b가 1-7a의 새 `artifact_id`를 인계받는다.

## Story

As a 마케팅 의사결정자,
I want 세그먼트별 이탈 요인 top5와 그에 대응하는 리텐션 액션을,
so that "위험하다"가 아니라 "그래서 무엇을 하라"까지 전달된다.

## Acceptance Criteria

**AC0 — 예측자 확장(신규, CAP-3 성립 조건)**
**Given** 이탈 요인을 해석해야 할 때
**When** 모델의 예측자 집합을 확인하면
**Then** RFM 프록시 3개에 더해 **raw 프레임의 이탈 신호 컬럼**이 포함되어 요인 top5 산출이 가능하다
**And** `features_customers`는 **변경되지 않는다**(CAP-1 소관 — 1-4 세그먼트·1-5 페르소나 산출물 회귀 0)
**And** 누수 배제가 유지된다: `Attrition_Flag`·`Naive_Bayes_Classifier_*` 2컬럼은 X에 **절대** 없다

**AC1 — SHAP은 `03_train_churn`에서만 계산(FR6·AD-5)**
**Given** 1.6의 학습 아티팩트가 있을 때
**When** SHAP을 산출하면
**Then** SHAP 값과 요인 top5가 **`03_train_churn` 단계에서만** 계산되어 아티팩트로 저장되고, 후속 단계는 읽기만 한다
**And** SHAP 배경 샘플링이 `RANDOM_SEED`를 수신한다(AD-7)

**AC2 — 정체성 결속(AD-5)**
**Given** `churn_prob`와 SHAP 해석이 함께 소비될 때
**When** 정체성을 검증하면
**Then** 둘이 동일 `artifact_id`에서 유래함이 확인되고, 불일치 시 **즉시 실패**한다

**AC3 — 액션 매핑(FR7·NFR1)**
**Given** 전역·개별 SHAP 해석이 나왔을 때
**When** 액션 매핑 문서를 확인하면
**Then** **세그먼트별** 이탈요인 top5가 구체적 리텐션 액션으로 번역된다
**And** 액션은 **실측이 아닌 제안**임이 라벨링된다

**AC4 — 결정론(AD-7)**
**Given** 동일 입력·동일 seed로 stage를 2회 실행할 때
**When** SHAP 산출물을 비교하면
**Then** 완전히 동일하다(배경 샘플링 포함).

> **범위 밖**: 범주형 피처 인코딩(아래 Dev Notes 참조 — 별도 스토리), 2×2 매트릭스(3-1), 마트(4-1),
> calibration(deferred-work), 관측/예측창(AD-6 금지).

## Tasks / Subtasks

- [x] **T0. shap 설치** (AC: 1) ← 착수 전 필수(모델링 블록 3번째·마지막 설치)
  - [x] `requirements.txt:26`의 `# shap>=0.52,<0.53` 주석 해제 + 설치. **최신 0.52.0** 확인됨. 실제 버전 기록.
  - [x] 설치 직후 **스모크 테스트**: `shap.TreeExplainer(fitted_xgb)` 생성 + 소량 샘플 `shap_values` 산출이
        현 xgboost 3.3.0 / numpy 2.5.1 / pandas 3.0.3 조합에서 동작하는지 확인(2-1 pymc 선례 — 미검증 스택은 먼저 찔러본다).
- [x] **T1. 예측자 확장 — `crm/churn/model.py`** (AC: 0) ← 순수 함수, features 테이블 불변
  - [x] `PREDICTOR_COLUMNS`(RFM 3개, features 유래)는 유지하고 **`RAW_PREDICTOR_COLUMNS`를 신설**해 raw에서 가져온다:
        `Total_Relationship_Count`·`Months_Inactive_12_mon`·`Contacts_Count_12_mon`·`Total_Amt_Chng_Q4_Q1`·
        `Total_Ct_Chng_Q4_Q1`·`Avg_Utilization_Ratio`·`Credit_Limit`. **총 10개 예측자.**
  - [x] `build_xy`가 두 출처를 합쳐 X를 만든다. 기존 검증은 **전부 유지**: 키 유일·비null, 양방향 집합 일치,
        정규 정렬(mergesort), 라벨 어휘 fail-fast, **누수 방어 단언**(target·`Naive_Bayes_Classifier_*` 배제 — 이제
        raw에서 컬럼을 가져오므로 이 단언이 **실제로 일할 차례**다), 수치·유한성 검사.
  - [x] **AD-11 절대 금지**: `Total_Trans_Amt`를 어떤 형태로도 명명하지 말 것(문자열·어트리뷰트·타입 선언·import).
        가치 축은 이미 `monetary_proxy`로 들어와 있다. 가드가 fail-closed로 잡는다.
  - [x] **`Credit_Limit`·`Avg_Utilization_Ratio` 사용 근거를 docstring에 명시**: SPEC CAP-5는 이들을 **가치 축에
        산입하는 것**을 금지했을 뿐(프로파일링 전용 참고 지표), **이탈 위험의 예측자로 쓰는 것은 다른 사안**이다.
        SPEC CAP-3의 "한도 불만형 → 한도 상향 제안"이 성립하려면 이 신호가 X에 있어야 한다. 리뷰어가 반드시 물어볼 지점이니
        코드에 근거를 남길 것.
  - [x] **제외 결정 기록**: `Avg_Open_To_Buy`(= Credit_Limit − Total_Revolving_Bal, 완전 중복), 범주형 5종
        (`Gender`·`Education_Level`·`Income_Category`·`Marital_Status`·`Card_Category`)은 **이번 범위 밖** —
        AD-7이 요구하는 **사전순 고정 인코딩**이 별도 설계 사안이고, 인구통계 피처는 리텐션 액션으로 번역 불가
        ("30대라서 이탈 위험" → 실행 가능한 액션 없음). deferred-work에 근거와 함께 기록.
- [x] **T2. 모델 재산출 + 1-6a 리포트 갱신** (AC: 0) ← 숫자가 바뀐다, 정직하게
  - [x] 실데이터로 03 재실행. **`artifact_id`가 바뀐다**(피처가 바뀌었으니 당연 — 정체성 장치가 제대로 도는 증거).
  - [x] `churn-model-report-1-6a.md` **UPDATE**: 3피처 → 10피처 비교표(baseline/XGBoost PR-AUC·리프트 **전후 병기**),
        변경 사유(CAP-3 성립 조건), 새 `artifact_id`·meta 실물. **옛 수치를 지우지 말고 "1-7에서 확장" 이력으로 남길 것.**
  - [x] 리프트가 **떨어질 수도 있다**(baseline도 같이 강해지므로). 떨어져도 실패 아님 — 1-6a AC2 정신 그대로,
        사실과 원인을 적는다. **+15% 목표는 서술이지 게이트가 아니다.**
- [x] **T3. SHAP 산출 모듈 `crm/churn/explain.py`(NEW)** (AC: 1, 4) ← 순수, 파일 I/O 없음
  - [x] `shap_values(model, x, seed=RANDOM_SEED, background_size=...) -> pd.DataFrame`:
        `shap.TreeExplainer` 사용. **배경 샘플을 `RANDOM_SEED`로 뽑아 명시 주입**(AC1의 "배경 샘플링이 seed 수신").
        반환은 `CLIENTNUM` 인덱스 × 피처별 SHAP 값. 인덱스·컬럼 순서 정규화(결정론).
  - [x] `global_importance(shap_df) -> pd.Series`: 피처별 **평균 |SHAP|** 내림차순(전역 요인).
  - [x] `segment_top_drivers(shap_df, segment_ids, top_n=5) -> pd.DataFrame`: **세그먼트별** 평균 |SHAP| top5.
        세그먼트는 `features_customers.segment_id`(1-4 안정 ID)로 조인 — **재계산 금지, 읽기만**.
        동점 시 정렬이 흔들리지 않도록 **2차 정렬키(피처명)** 고정(AD-7).
  - [x] 순수성: 파일을 읽거나 쓰지 않는다. shap import는 이 모듈만(AD-9: stage는 `crm.*`만).
- [x] **T4. 아티팩트 저장 + 정체성 결속 — stage `pipelines/03_train_churn.py`** (AC: 1, 2) — ⚠️ **현재 정확히 40행**
  - [x] 출력 3개로 확장: `models/churn_model.joblib` · `data/churn_scored.parquet` · **`data/churn_shap.parquet`**(NEW).
        SHAP 산출물도 `attach_artifact_id`로 **동일 `artifact_id` 스탬프** + AD-13 meta.
  - [x] **40행 예산**: 배선이 늘어나므로 로직을 `crm/`으로 더 내릴 것. 후보 — `crm/churn/artifact.py`에
        `identity_is_consistent`를 **여러 산출물**에 대해 검사하는 형태로 일반화(예: `identity_is_consistent(model, [scored, shap])`),
        또는 `crm/churn/explain.py`에 "SHAP 프레임 조립" 고수준 함수 하나. **stage에 로직을 쓰지 말 것.**
  - [x] **신선도 게이트 확장**: SHAP 산출물이 없거나 `artifact_id`가 어긋나면 **재실행**(1-6b fail-closed 계약 그대로).
        1-6b가 만든 `read_verified_model_meta`·`verify_artifact_identity`·`identity_is_consistent`를 **재사용**(재구현 금지).
- [x] **T5. 액션 매핑 문서** (AC: 3) — `docs/implementation-artifacts/churn-drivers-actions-1-7.md`(NEW)
  - [x] **전역 요인 순위**(평균 |SHAP|) + **세그먼트별 top5** 표. 세그먼트는 1-5 페르소나 이름과 함께 표기.
  - [x] 요인 → **구체적 리텐션 액션** 번역. SPEC 예시 방향: 거래 감소형 → 사용처 쿠폰, **한도 불만형 → 한도 상향 제안**,
        비활성 장기 → 리액티베이션 캠페인, 컨택 과다 → 불만 해소·이탈 방지 상담.
  - [x] **NFR1 라벨링 필수**: 모든 액션에 "**실측 효과가 아닌 제안**"임을 명시. 리텐션 성공률은 config의 **가정값**이고
        강건성은 3-4 소관임을 함께 적을 것.
  - [x] **정직성**: SHAP은 **모델이 그렇게 판단한 이유**이지 **인과가 아니다**. "요인"이라는 단어가 인과로 읽히지 않도록
        한 문단 할애. 1-6a의 미보정 `churn_prob`(순위 신호) 한계도 재확인.
  - [x] 금액성 지표는 **무단위**(NFR3), 통화 기호 금지.
- [x] **T6. 테스트** — `tests/churn/test_explain.py`(NEW) + `test_model.py`·`test_stage.py`(UPDATE)
  - [x] **결정론(AC4)**: 같은 seed 2회 → SHAP 값 완전 동일. **배경 샘플링에 seed가 실제로 주입됐는지** params/spy로 검증
        (1-4·1-6a 교훈: 결과 동일만으로는 약하다).
  - [x] **SHAP 성질(oracle)**: TreeExplainer의 가법성 — `base_value + sum(shap_values) ≈ model 출력(margin)`.
        허용 오차를 명시하고 **동어반복 금지**(shap 재호출 비교 아님).
  - [x] **누수 배제 재확인(AC0)**: raw에서 컬럼을 가져오므로 `Naive_Bayes_Classifier_*`·`Attrition_Flag`가 X에
        섞이지 않음을 **합성 주입**으로 실증. 1-6a 테스트를 새 피처셋에 맞춰 갱신.
  - [x] **세그먼트 top5**: 알려진 SHAP 픽스처 → 기대 순위(하드코딩 oracle). **동점 시 결정론** 고정.
  - [x] **stage 통합**: ① SHAP 산출물 생성·`artifact_id` 일치 ② SHAP 파일 삭제 → **재실행** ③ SHAP의 `artifact_id`
        변조 → **재실행** ④ 정상 3종 → **skip**(무한 재실행 아님) ⑤ 2회 실행 SHAP 동일.
  - [x] 순수성(입력 프레임 불변), ASCII 런타임 문자열.
- [x] **T7. 실행·커밋**
  - [x] 실데이터 03 재실행 → 3개 산출물 + meta. 2회 실행 결정론 실증.
  - [x] `.venv/Scripts/python.exe -m pytest` 전체 green. **기준선 242 passed, 회귀 0.**
  - [x] **README 갱신(에픽1 마감 겸)**: `README.md:4`의 `> 진행 중 — Epic 1 초입.`이 **stale**하다 —
        실제는 에픽1 완료. 진행 상태 + 핵심 수치(테스트 수·PR-AUC·세그먼트/페르소나·아티팩트 정체성)를 한 줄로 갱신.
        **본편(핵심 수치·발견·한계)은 4-4 소관이라는 문장은 유지**.
  - [x] 스토리 단위 커밋. Obsidian 미러 갱신.

## Dev Notes

### 이 스토리가 존재하는 진짜 이유 (읽고 시작할 것)

SPEC은 **"산출물은 모델이 아니라 타겟팅 의사결정 프레임"**이라고 선언한다. CAP-3은 그 프레임의 "그래서 뭘 하라"를
담당한다. 그런데 1-6a의 예측자는 **RFM 프록시 3개**뿐이었고, 그건 세그멘테이션(CAP-1)용으로 만든 테이블을
**재사용한 결과이지 설계된 피처셋이 아니다**. 그 상태로 SHAP을 돌리면 나오는 답은:

> "거래가 줄어서(frequency↓) 이탈 위험이 높습니다"

이건 요인이 아니라 **정의의 재진술**이다. 마케터가 이걸 받고 할 수 있는 일이 없다. 그래서 이 스토리는 SHAP 배관을
깔기 **전에** 해석할 값어치가 있는 피처를 X에 넣는다.

### 확장 방식 — 왜 raw 경유인가 (비용 최소 경로)

`build_xy(features, raw)`는 **이미 raw 프레임을 받고 있다**(y를 뽑으려고). 여기서 예측자를 더 가져오면:

| | 영향 |
|---|---|
| `features_customers` | **불변** → 1-3 산출물 그대로 |
| 1-4 세그먼트·1-5 페르소나 | **불변** → 회귀 0 |
| 이탈 모델 지표·`artifact_id` | **변경**(의도) → 1-6a 리포트 갱신 |

`features_customers`에 컬럼을 추가하는 경로였다면 1-4 K-means 입력이 바뀌어 **세그먼트 ID가 통째로 흔들리고**
1-5 페르소나·리포트가 전부 무효화된다. 그 길로 가지 말 것.

### 예측자 최종 셋 (10개)

**features 유래(3)**: `recency_proxy`, `frequency_proxy`, `monetary_proxy`
**raw 유래(7)**: `Total_Relationship_Count`, `Months_Inactive_12_mon`, `Contacts_Count_12_mon`,
`Total_Amt_Chng_Q4_Q1`, `Total_Ct_Chng_Q4_Q1`, `Avg_Utilization_Ratio`, `Credit_Limit`

- 전부 **수치형**이라 `build_xy`의 유한·수치 검사를 그대로 통과한다(범주형을 넣으면 그 검사부터 손봐야 한다).
- `Months_Inactive_12_mon`·`Contacts_Count_12_mon`은 BankChurners에서 가장 잘 알려진 이탈 신호다.
- `Credit_Limit`·`Avg_Utilization_Ratio`가 SPEC CAP-3의 **"한도 불만형"** 액션을 가능하게 하는 유일한 경로다.

### 🚨 절대 건드리지 말 것

- **`Total_Trans_Amt`** — AD-11. `crm/` 아래 어떤 모듈도 이 이름을 문자열·어트리뷰트·타입·import 어떤 형태로도
  명명할 수 없다(가드가 fail-closed). 가치 축은 `monetary_proxy`로 이미 들어와 있다.
- **`Naive_Bayes_Classifier_*` 2컬럼** — 타깃 상관 ±1.0. 이제 raw에서 컬럼을 뽑으므로 **실수로 딸려올 위험이 처음으로 실재한다.**
  `build_xy`의 방어 단언이 이번엔 진짜로 일한다. 화이트리스트 방식(명시한 컬럼만)으로 가져오고, 와일드카드 금지.
- **`features_customers` 스키마** — 1-3 소관. 이 스토리는 읽기만 한다.

### 재사용할 것 (1-6b가 깔아둔 것)

| 필요 | 이미 있는 것 | 위치 |
|---|---|---|
| 모델+기록 정체성 검증 | `read_verified_model_meta`(디스크 해시까지) | `crm/churn/artifact.py` |
| 불일치 즉시 실패 | `verify_artifact_identity` | 〃 |
| 게이트용 fail-closed 판정 | `identity_is_consistent` | 〃 |
| 산출물에 정체성 스탬프 | `attach_artifact_id` | `crm/churn/model.py` |
| 원자적 (출력+meta) | `write_parquet_with_meta`·`build_meta` | `crm/common/atomic.py`·`freshness.py` |
| 신선도 2단 게이트 | `verify_inputs`·`is_output_stale` | `crm/common/freshness.py` |

**재구현 금지.** 특히 정체성 검증을 SHAP용으로 새로 짜지 말 것 — 1-6b가 외부 리뷰 2라운드를 거쳐 굳힌 계약이다.

### SHAP 사용 시 함정 (shap 0.52.0)

- **TreeExplainer 모드**: `feature_perturbation="tree_path_dependent"`는 배경 데이터가 필요 없고,
  `"interventional"`은 배경 샘플이 필요하다. **AC1이 "배경 샘플링이 RANDOM_SEED를 수신"을 요구하므로 배경 샘플을
  쓰는 경로를 택하고, 샘플링에 seed를 명시 주입**한다. 어느 모드를 썼는지 docstring에 못박을 것.
- **출력 형태**: 이진 분류에서 shap 버전·모델 타입에 따라 `(n, features)` 또는 `(n, features, 2)`가 나온다.
  **실제 shape를 먼저 확인하고** 양성 클래스 축을 명시적으로 고르라(암묵 인덱싱 금지 — 조용히 음성 클래스를 해석하게 된다).
- **결정론**: 배경 샘플 순서·행 순서가 값에 영향을 준다. `build_xy`의 정규 정렬(CLIENTNUM mergesort)을 유지하고
  배경 샘플도 seed로 고정. **2회 실행 완전 동일**이 수용 기준이다.
- **비용**: 10,127행 × 10피처 TreeExplainer는 로컬에서 초 단위다. 문제되면 배경 샘플 크기를 config 상수로
  (규약 상수 — 데이터 유래 아님).

### 구조 가드 — 걸리기 쉬운 지점

- **AD-9 stage 40행**: 현재 **정확히 40행**. 출력이 2→3개로 늘어난다. **로직은 전부 `crm/`으로.**
  `main` 외 def/class/**lambda** 금지(중첩 포함).
- **AD-1 레인**: `crm/churn`은 `crm/ltv` 참조 불가. SHAP 코드는 `crm/churn/explain.py`.
- **AD-1 무상태 common**: `crm/common`에 fit 상태를 두지 말 것. explainer는 churn 레인 소유.
- **AD-4**: 새 상수(배경 샘플 크기·top_n)는 **규약**이지 데이터 유래 값이 아님을 `# source:` 주석으로 밝힐 것.
  config를 건드리면 `config_hash`가 바뀌어 **01·02부터 재실행**해야 한다(1-3/1-4/1-6a 선례) — 예상하고 시작할 것.

### 1-6a/1-6b에서 물려받은 규율

- **fail-fast > 조용한 관용**: 불일치·부재·파싱 실패는 재실행 또는 예외. 경고 후 진행 금지.
- **테스트는 성질 + 하드코딩 oracle + 배선 실증**. 함수 테스트는 stage 배선 회귀를 못 잡는다 →
  `tests/churn/test_stage.py`의 `_load_stage_03`·`_seed_inputs` 패턴 재사용.
- **문서가 테스트를 앞서지 않기**: 리포트에 쓰기 전에 그 성질을 KILL하는 테스트가 있어야 한다.
- **정직한 표현**: 과장 금지. 1-6b 리뷰에서 "자동 복구"→"다음 실행에서 탐지·재학습"으로 정정한 선례.
- ASCII 런타임 문자열, `.venv/Scripts/python.exe -m pytest`, 순수 함수 우선.

### 에픽1 마감 스토리 (이후 흐름)

이 스토리가 done이면 **에픽1 전체 done** → `epic-1-retrospective`(optional). 그다음은 에픽2(LTV 데모).
포트폴리오 관점에서 진짜 승부처는 **에픽3(2×2 + 캠페인 시뮬레이터)**이며, 이 스토리의 산출물(요인·액션)이
3-2 시뮬레이터의 "무엇을 제안할 것인가"에 직접 연결된다.

### Project Structure Notes

```
crm/churn/explain.py                    # NEW - SHAP 산출·전역 중요도·세그먼트 top5 (순수)
crm/churn/model.py                      # UPDATE - RAW_PREDICTOR_COLUMNS, build_xy 확장
crm/churn/artifact.py                   # UPDATE(가능성) - 다산출물 정체성 검사 일반화
pipelines/03_train_churn.py             # UPDATE - 출력 3개, SHAP 배선 (⚠️ 40행 상한)
crm/config.py                           # UPDATE(필요시) - SHAP_BACKGROUND_SIZE·DRIVER_TOP_N (규약 상수)
requirements.txt                        # UPDATE - shap 주석 해제
tests/churn/test_explain.py             # NEW - 결정론·가법성·세그먼트 top5
tests/churn/test_model.py               # UPDATE - 확장 피처셋·누수 재감사
tests/churn/test_stage.py               # UPDATE - SHAP 산출물·정체성·재실행
docs/implementation-artifacts/churn-drivers-actions-1-7.md   # NEW - 요인→액션 매핑
docs/implementation-artifacts/churn-model-report-1-6a.md     # UPDATE - 3→10피처 전후 비교
docs/implementation-artifacts/deferred-work.md               # UPDATE - 범주형 인코딩 등 보류 근거
docs/implementation-artifacts/structure-guard-coverage.md    # UPDATE - 재생성
README.md                               # UPDATE - stale한 "Epic 1 초입" 정정
```

- 출력 추가: `data/churn_shap.parquet`(+ AD-13 meta, + `artifact_id` 컬럼).

### 환경 실측 (2026-07-21)

```
python 3.12.10 | xgboost 3.3.0 | scikit-learn 1.9.0 | joblib 1.5.3
pandas 3.0.3 | numpy 2.5.1 | pyarrow 25.0.0 | shap 0.52.0 (설치 예정, 최신)
HEAD c702b95 | 242 passed | 1-6a 실측(3피처): baseline 0.4297 / XGBoost 0.8024 / +86.7%
```

### References

- [Source: docs/planning-artifacts/epics.md#Story 1.7] — AC 원문(FR6/FR7, AD-5, AD-7, NFR1)
- [Source: .../ARCHITECTURE-SPINE.md#AD-5] — SHAP은 03에서만 계산, 후속 단계 읽기 전용, artifact_id 결속
- [Source: .../ARCHITECTURE-SPINE.md#AD-7] — SHAP 배경 샘플링 seed 수신 명시
- [Source: .../ARCHITECTURE-SPINE.md#AD-11] — Total_Trans_Amt 이름 봉인(가드 fail-closed)
- [Source: docs/specs/spec-crm-targeting-lab/SPEC.md#CAP-3] — 요인→액션 번역, "한도 불만형" 예시
- [Source: docs/specs/.../SPEC.md#CAP-5] — Credit_Limit·Total_Revolving_Bal은 **가치 축 산입 금지**(예측자 사용은 별개)
- [Source: docs/implementation-artifacts/1-6b-artifact-identity-meta.md] — 정체성 계약·외부리뷰 2라운드 교훈
- [Source: docs/implementation-artifacts/1-6a-churn-model-baseline-lift.md] — 누수 재감사·+15% 서술 원칙
- [Source: 실측 2026-07-21] — features/raw 스키마, shap 0.52.0

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (bmad-dev-story)

### Debug Log References

**기준선**: HEAD `c702b95`, 242 passed.

**shap 설치 부작용(기록)**: `shap 0.52.0`이 numba를 끌어오며 **numpy를 2.5.1 → 2.4.6으로 다운그레이드**했다.
설치 직후 전체 스위트를 먼저 돌려 **242 passed 유지**를 확인하고 진행. meta.json `libraries`에 2.4.6으로 기록된다.

**스모크 테스트에서 잡은 스택 함정 2건**:
1. `shap.TreeExplainer(model, feature_perturbation="interventional")`이 **`NotImplementedError: Categorical
   split is not yet supported`**로 실패. 원인은 데이터가 아니라 **xgboost 3.3의 `XGBClassifier`가
   `enable_categorical=True`를 기본으로 켜는 것** — shap는 플래그만 보고 거부한다. `enable_categorical=False`를
   명시하니 해결됐고 **예측은 비트 단위로 동일**함을 실측 확인(모델을 바꾼 게 아님).
2. 배경 데이터를 DataFrame으로 넘기면 shap 내부 Independent masker가 **`max_samples=100`으로 조용히 절삭**한다
   (`Background dataset has 200 samples but max_samples=100`). config에 200을 선언한 채 100이 쓰이면 기록이
   거짓이 되므로 `shap.maskers.Independent(bg, max_samples=len(bg))`로 명시 전달하도록 수정.

**출력 형태 확인**: 이 스택에서 이진 `XGBClassifier`의 SHAP은 `(n, features)` **2D**. 3D 분기는 방어용으로
남겼으나 **현 스택에선 도달하지 않는다**(변이 테스트에서 생존 — 코드 결함이 아니라 도달 불가 분기).

**예측자 10개 → 9개로 정정(실측 발견)**: 계획은 raw 7컬럼 추가(총 10)였으나, 1차 산출에서
`Months_Inactive_12_mon`의 평균 |SHAP|이 **정확히 0.0000**으로 나왔다. 원인: **1-3의 `recency_proxy`가
이 컬럼 그 자체**(값 동일 실측)라 XGBoost가 한쪽만 쓰고 다른 쪽에 기여를 0으로 배분한 것. 그대로 뒀다면
리포트에 "비활성 개월은 이탈과 무관"이라는 **정반대 결론**이 실릴 뻔했다. 중복 컬럼을 제외해 **9개**로 확정.

**config drift(예상대로)**: `SHAP_BACKGROUND_SIZE`·`DRIVER_TOP_N` 추가 → `config_hash` 변경 → 01·02 재실행 후 03.

**stage 40행 예산**: 출력 3개·SHAP 배선으로 44행 → docstring 3줄 축약·`from __future__` 제거·공백 정리로 40행.
판정 로직은 `outputs_share_identity`(가변 인자) 한 줄 호출로 crm에 내림.

**실데이터 결과**(n=10,127, 이탈률 16.07%):
```
예측자 9개 | baseline 0.6947 | XGBoost 0.9559 | lift +37.6% | artifact_id b598a867de07
전역 요인 top3: frequency_proxy 2.872 / monetary_proxy 1.538 / Avg_Utilization_Ratio 0.550
churn_scored·churn_shap 10,127행 전부 동일 artifact_id (unique=1)
```

**정직한 발견**: **리프트가 +86.7% → +37.6%로 떨어졌다.** 두 모델이 같은 피처를 받아 baseline이 함께 강해진
결과(0.4297 → 0.6947)이고, 절대 성능은 0.8024 → 0.9559로 올랐다. 리프트는 품질의 상한이 아니라 상대 우위다.
또한 **SPEC CAP-3이 예시로 든 "한도 불만형"은 실증되지 않았다** — 이용률이 **낮은** 고객이 위험하고(r=−0.58)
`Credit_Limit`은 방향성이 없다(r=+0.01). 예시에 데이터를 맞추지 않고 어긋남을 리포트에 기록했다.

**테스트 검출력(변이 5종)**:
| 변이 | 결과 |
|---|---|
| 세그먼트를 인덱스가 아닌 위치로 정렬 | KILLED |
| 동점 정렬키(피처명) 제거 | KILLED |
| SHAP 산출물 정체성 미검사(첫 산출물만) | KILLED |
| 배경 샘플링 seed 무시(`random_state=None`) | **1차 SURVIVED** → 테스트 보강 후 KILLED |
| SHAP 3D 분기에서 음성 클래스 선택 | SURVIVED — **도달 불가 분기**(현 스택은 2D). 결함 아님 |

seed 변이가 살아남은 이유가 교훈적이다: "다른 seed면 배경이 다르다"만 검사하면 **seed를 아예 안 쓰는
구현도 통과**한다(둘 다 무작위라 어차피 다르다). **같은 seed면 같은 배경**이라는 재현성 검사를 추가해 잡았다.

### Completion Notes List

- **AC0 충족**: 예측자 9개(features 3 + raw 6). `features_customers`는 **한 줄도 바뀌지 않았고** 1-4 세그먼트·
  1-5 페르소나 산출물은 회귀 0. 누수 방어 단언이 raw 경유로 처음 실효를 갖게 됐고, 실제 컬럼명 2개를 합성 주입해 실증.
- **AC1 충족**: `crm/churn/explain.py`가 SHAP을 소유하고 `03_train_churn`에서만 호출된다. 배경 샘플은
  `RANDOM_SEED`로 뽑아 명시 주입(spy로 실증), interventional 모드 명시.
- **AC2 충족**: `churn_shap.parquet`이 모델·점수와 **동일 `artifact_id`**를 보유. 게이트가 세 산출물을 함께
  검사(`outputs_share_identity`)해 SHAP 삭제·변조 시 재실행. 1-6b 계약 재사용, 재구현 없음.
- **AC3 충족**: `churn-drivers-actions-1-7.md` — 전역 요인 9개 순위 + 세그먼트별 top5 + 액션 매핑.
  모든 액션에 "실측 아닌 제안" 라벨, SHAP≠인과 문단, 무단위 표기.
- **AC4 충족**: 같은 seed 2회 SHAP 완전 동일(함수·stage 양쪽 회귀 테스트).
- **모델은 의도적으로 바뀌었다**(1-6b와 다른 점): 피처가 늘었으니 `artifact_id`·지표가 바뀌는 게 정상이며,
  1-6a 리포트에 **전후 병기**로 남겼다(옛 수치 삭제 없음).
- **README stale 정정**: "Epic 1 초입" → 에픽1 완료 + 핵심 수치. 본편은 4-4 소관 문장 유지.
- **구조 가드 전종 green**(stage 40행·main only·레인·계층·AD-11·무상태 common·config 단일).
- **테스트**: 242 → **267 passed**, 회귀 0.

### File List

- `crm/churn/explain.py` — NEW, `shap_frame`·`build_shap_output`·`global_importance`·`segment_top_drivers`(순수)
- `crm/churn/model.py` — UPDATE, `RAW_PREDICTOR_COLUMNS`·`ALL_PREDICTOR_COLUMNS`, `build_xy` 화이트리스트 확장,
  `enable_categorical=False`, `ChurnResult.x`
- `crm/churn/artifact.py` — UPDATE, `outputs_share_identity`(다산출물), 기본 features를 9개로
- `crm/config.py` — UPDATE, `SHAP_BACKGROUND_SIZE`·`DRIVER_TOP_N`(규약 상수)
- `pipelines/03_train_churn.py` — UPDATE, 출력 3개·SHAP 배선·게이트 확장(40행 유지)
- `requirements.txt` — UPDATE, shap 주석 해제(1-7 설치)
- `tests/churn/test_explain.py` — NEW, 결정론·가법성 oracle·양성클래스·세그먼트 정렬 14건
- `tests/churn/test_model.py` — UPDATE, 확장 피처셋 픽스처 + AC0 회귀 6건
- `tests/churn/test_stage.py` — UPDATE, 3출력 픽스처 + SHAP 정체성/재실행 4건
- `tests/churn/test_artifact.py` — UPDATE, 픽스처를 새 스키마로(서브프로세스 스크립트 포함)
- `docs/implementation-artifacts/churn-drivers-actions-1-7.md` — NEW, 요인→액션 매핑
- `docs/implementation-artifacts/churn-model-report-1-6a.md` — UPDATE, 3피처/9피처 전후 병기
- `docs/implementation-artifacts/deferred-work.md` — UPDATE, 범주형 인코딩 등 보류 + 실측 교훈 3건
- `docs/implementation-artifacts/1-7-shap-drivers-retention-actions.md` — UPDATE, 본 기록
- `docs/implementation-artifacts/sprint-status.yaml` — UPDATE, 상태 전이
- `README.md` — UPDATE, stale한 "Epic 1 초입" 정정
- `docs/specs/spec-crm-targeting-lab/SPEC.md` — UPDATE, CAP-5 3차 개정(가치 축 금지 범위 명시, 리뷰 ②)

## Senior Developer Review (외부 GPT, 2026-07-21)

**판정**: ② Med(SPEC 모호) · ③ Pass · ④ Pass+계약 보강 · ⑦ Med(fail-open). **4건 전부 처리**(반려 0).

### 처리 내역

- **[② Med] `Credit_Limit` — ablation이 결정**: 리뷰어가 제시한 제거 기준 3개(PR-AUC 차이 미미 / SHAP 순위
  낮음 / 세그먼트 top5 부재)를 실측했더니 **전부 충족**: PR-AUC +0.005(0.9508→0.9559), 전역 요인 **9/9위**,
  세그먼트 top5 등장 4개 중 1개. → **예측자에서 제거**(최종 8개). "한도 불만형을 식별할 유일한 방법"이라는
  약한 근거도 코드에서 제거(리뷰 지적대로 SPEC 예시에 맞추려는 문구였음). **SPEC CAP-5 3차 개정**: 금지
  범위를 "가치 산식·LTV·가치 축·가치 기반 우선순위"로 명시하고, 예측자 사용은 별개 사안임을 SPEC이 소유
  (코드 주석이 SPEC을 재해석하지 않도록). `Avg_Utilization_Ratio`는 이 개정 근거로 유지.
- **[③ Pass] `enable_categorical=False` 유지**: "호환성 우회"가 아니라 **수치형 전용 입력 계약의 명문화**로
  문구 교정. 리뷰 제안대로 3중 검사 테스트 추가(params=False + X 전 컬럼 수치형 + booster feature_types에
  'c' 없음).
- **[④ Pass] `Months_Inactive_12_mon` 제외 유지, recency 정의 불변**: 리뷰 지적대로 근본 문제는 계산식이
  아니라 **계보 미명시**. identity alias 계약 테스트 2건 추가 — ①실데이터에서 `recency_proxy` ==
  `Months_Inactive_12_mon` 검증(1-3이 정의를 바꾸면 이 테스트가 터져 재검토를 강제) ②정적으로
  `Months_Inactive_12_mon ∉ ALL_PREDICTOR_COLUMNS`. 문서 표현도 "별도 요인이 아니다" →
  "recency_proxy로 이미 포함돼 있다"로 교정.
- **[⑦ Med] 3D 분기 삭제 → fail-fast**: 리뷰 재현 시나리오가 정확했다 — `[positive, negative]` 순서의 3D
  출력이면 기존 코드는 **음성 클래스를 골라 형태가 멀쩡한 숫자를 반환**한다(조용히, 그럴듯하게 틀림).
  2D + shape 일치 외 전부 `ValueError`. monkeypatch로 그 시나리오 그대로 회귀 테스트 추가 —
  이전 변이 테스트에서 "도달 불가라 생존"이던 분기가 **삭제로 해소**됐다.

### 재검증

- 8피처 재산출: baseline 0.6751 / XGBoost 0.9508 / lift **+40.8%** / `artifact_id c751c63d5b58`.
  1-6a 리포트·요인 문서 전면 갱신(세그먼트 top5 구성도 소폭 변동 — 재산출 반영).
- 2회 실행 결정론: `artifact_id`·scored·shap 완전 동일. 구조 가드 0 위반.
- **267 → 272 passed**, 회귀 0.

## Change Log

| 날짜 | 변경 |
|---|---|
| 2026-07-21 | 외부 GPT 리뷰 4건 처리: Credit_Limit ablation 후 제거(8피처, lift +40.8%)·SPEC CAP-5 3차 개정(금지 범위 명시)·enable_categorical 문구 교정+3중 검사·recency identity alias 계약 테스트·SHAP 3D 분기 삭제(fail-fast). 267 → 272 passed |
| 2026-07-21 | 스토리 1-7 구현: 예측자 9개 확장(raw 경유, features 테이블 불변)·SHAP(interventional·seed 주입)·3산출물 정체성 결속·요인→액션 매핑. baseline 0.6947/xgb 0.9559/lift +37.6%(리프트 하락은 baseline 강화 탓, 절대성능 상승). 중복 컬럼(Months_Inactive) 실측 발견해 제외. 242 → 267 passed, 회귀 0. Status → review |
| 2026-07-21 | 스토리 1-7 create-story: 예측자 확장(raw 경유 7컬럼 추가, features_customers 불변) + SHAP(03 전용·seed 주입) + artifact_id 결속 + 세그먼트별 요인 top5→액션 매핑. 3피처로는 CAP-3 불성립이라는 실증이 범위 확대 근거. Status → ready-for-dev. 기준선 242 passed |
