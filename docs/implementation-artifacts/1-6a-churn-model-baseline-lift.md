---
baseline_commit: a0e6013
baseline_passed: 170
---

# Story 1.6a: 이탈위험 분류 모델과 baseline 리프트

Status: ready-for-dev

> **분할 안내**: 원 스토리 1.6을 1-6a/1-6b로 분할(2026-07-21, sprint-status 헤더 주석 근거).
> **1-6a(이 스토리)** = baseline 로지스틱 + XGBoost + 불균형/CV/PR-AUC + 리프트 비교 + 라벨 표기(AD-6)
> + 누수 재감사. **1-6b** = 아티팩트 정체성(AD-5: `churn_model.meta.json`·`artifact_id`·churn_scored 결속).
> 1-7 SHAP이 1-6b의 artifact_id에 의존한다.

## Story

As a 분석가,
I want XGBoost 이탈위험 분류기와 baseline 로지스틱 비교를,
so that 모델이 단순 기준선 대비 실제로 얼마나 나은지 정직하게 말할 수 있다.

## Acceptance Criteria (1-6a 소관)

**AC1 — 두 모델 + 불균형·CV·PR-AUC + 결정론**
**Given** `pipelines/03_train_churn.py`가 피처를 읽을 때
**When** baseline 로지스틱과 XGBoost를 학습하면
**Then** 불균형 처리(`scale_pos_weight`)·교차검증이 적용되고 PR-AUC를 병행 평가한다(FR4)
**And** XGBoost는 `random_state`·**`n_jobs=1`**·`tree_method`가 고정된다(AD-7 — 스레드 수에 따른 부동소수 축약 순서 차이가 분위수 경계에서 고객을 분면 넘나들게 한다)

**AC2 — 리프트 + 정직성**
**Given** 두 모델 성능이 산출됐을 때
**When** 비교표를 확인하면
**Then** baseline 대비 PR-AUC 리프트가 수치로 제시된다(FR5)
**And** **+15% 목표 미달이어도 실패로 처리하지 않고** 미달 사실과 원인 분석을 리포트에 명시한다(정직성, P1 1-7a 선례)

**AC4 — 라벨 성격 표기(AD-6)**
**Given** 라벨 성격을 표기해야 할 때
**When** 코드 docstring·리포트·컬럼 정의를 확인하면
**Then** "이탈 위험 분류(cross-sectional)"로 표기되고 시계열 예측 표현이 쓰이지 않는다(NFR2·AD-6)

> **AC3(아티팩트 정체성, AD-5)은 1-6b로 이관.** 1-6a는 모델·점수·비교표까지. 1-6a의 `churn_scored.parquet`은
> AD-13 신선도 meta는 갖되 **AD-5 `artifact_id`는 아직 없다**(1-6b가 부여). 1-6a는 모델을 **원자적으로 저장**만 하고
> `churn_model.meta.json`(콘텐츠 해시 정체성)은 1-6b가 쓴다.

## Tasks / Subtasks

- [ ] **T0. xgboost 설치** (AC: 1) ← 착수 전 필수(모델링 블록 2번째 설치)
  - [ ] `requirements.txt`의 `# xgboost>=3.3,<4.0` 주석 해제 + 설치. 실제 버전 기록. joblib은 1-4에서 이미 설치됨.
- [ ] **T1. 순수 모델링 모듈 `crm/churn/model.py`** (AC: 1, 2, 4) ← 로직 소유
  - [ ] **예측자(X)**: features_customers의 **연속 RFM 프록시**(`recency_proxy`·`frequency_proxy`·`monetary_proxy`).
    점수(R/F/M)·`segment_id`는 이들의 파생/양자화라 **제외**(중복·순환 회피). 이 선택과 "얇은 피처셋이 리프트를
    제약한다"는 한계를 리포트에 정직히 명시.
  - [ ] **라벨(y)**: raw `Attrition_Flag == "Attrited Customer"`. **라벨을 피처 테이블에 섞지 않는다**(1-5 위생) —
    X와 y를 분리해 받는다.
  - [ ] `train_baseline(X, y, seed) -> fitted LogisticRegression`(불균형: `class_weight="balanced"`, `random_state=seed`,
    수렴 위해 `max_iter` 충분히). 스케일링 필요 시 파이프라인 내부에서(가치 축 정규화 아님).
  - [ ] `train_xgboost(X, y, seed) -> fitted XGBClassifier`(**`scale_pos_weight`=음성/양성 비율, `random_state=seed`,
    `n_jobs=1`, `tree_method` 고정**(예: `"hist"`) — AD-7). eval_metric 등 확률적/스레드 의존 요소 고정.
  - [ ] `pr_auc_cv(make_estimator, X, y, seed, n_splits) -> float`: **StratifiedKFold(seed 주입)**로 **PR-AUC(average precision)**
    교차검증 평균. baseline·XGBoost 동일 폴드. 동어반복 금지(구현 재실행-비교 아님).
  - [ ] `lift(baseline, model) -> float`: 상대 리프트((model-baseline)/baseline). +15% 목표는 **판정이 아니라 서술**.
  - [ ] `score_customers(model, X) -> Series[float]`: `churn_prob`(양성 확률). 인덱스 보존.
  - [ ] **라벨 표기(AD-6)**: 모든 docstring·주석·반환 컬럼 의미를 **"cross-sectional 이탈 위험 분류"**로. "예측(시계열)"·
    "관측창/예측창" 표현 금지.
  - [ ] **누수 재감사(sprint-status 경고)**: `Naive_Bayes_Classifier_*` 2컬럼은 X에 **절대** 없음(features_customers엔
    애초에 없지만 방어적으로 단언). `Attrition_Flag`는 y로만, X에 없음. 테스트로 못박음.
- [ ] **T2. 모델 저장 헬퍼 `crm/churn/artifact.py`(또는 common)** (AC: 1) — stage를 얇게 유지
  - [ ] `save_model(model, path)`: joblib 직렬화 → **원자적 쓰기**(1-1b atomic 패턴; `atomic_write_bytes` 재사용 또는
    temp+rename). stage가 joblib을 직접 부르지 않도록(AD-9: stage는 crm.*·pandas·logging만). **AD-5 meta.json은 여기서
    쓰지 않는다(1-6b 소관)** — 1-6a는 모델 바이트만 원자적 저장.
- [ ] **T3. 파이프라인 stage `pipelines/03_train_churn.py`** (AC: 1, 2, 4) — 얇은 오케스트레이션
  - [ ] `main(input_paths, output_paths)`만, **40행 이하**, `main` 외 def/lambda 금지(가드). 입력 2개
    (features_customers·bankchurners), 출력 2개(`models/churn_model.joblib`·`data/churn_scored.parquet`).
  - [ ] `verify_inputs([features_customers], "02_features")` + `verify_inputs([bankchurners], "01_download")`.
    이어 `is_output_stale(churn_scored, [features_customers, bankchurners], expected_stage="03_train_churn")`.
  - [ ] `crm.churn`의 고수준 함수 하나로 (X,y 구성 → 두 모델 학습 → XGBoost로 스코어 → 비교 지표)를 조립.
    `write_parquet_with_meta`로 `churn_scored.parquet`(CLIENTNUM + `churn_prob`) + AD-13 meta. `save_model`로 모델 저장.
  - [ ] 모듈명 숫자 시작이라 `python -m` 불가 — 실행 관례 docstring. **라벨 표기 AD-6** docstring에도.
- [ ] **T4. 모델 비교 리포트** (AC: 2, 4) — `docs/implementation-artifacts/churn-model-report-1-6a.md`
  - [ ] baseline vs XGBoost **PR-AUC 비교표**(CV 평균) + **리프트 수치**. ROC-AUC 병기 가능하나 **불균형이라 PR-AUC가 주지표**.
  - [ ] **+15% 미달 시 정직 처리**(AC2): 미달이면 실패 아님 — 미달 사실 + 원인(얇은 RFM 피처셋·라벨 단면성 등)을 명시.
  - [ ] **라벨 성격(AD-6)**: "cross-sectional 이탈 위험 분류, 시계열 예측 아님, 관측/예측창 없음" 한계 명시.
  - [ ] 불균형(이탈률 16.1%, scale_pos_weight≈5.22)·결정론(seed·n_jobs=1·tree_method) 기재. 통화 무단위(NFR3).
- [ ] **T5. 행동 기반 테스트** — `tests/churn/test_model.py`
  - [ ] **결정론(AD-7)**: 같은 seed 2회 학습·스코어 → `churn_prob` 완전 동일. XGBoost `n_jobs=1`·`tree_method`·`random_state`가
    실제 주입됐는지 **생성자 spy**로 검증(1-4 교훈: 결과기반은 약함).
  - [ ] **불균형 처리 실증**: `scale_pos_weight`가 음성/양성 비율로 주입됨(spy 또는 속성 확인).
  - [ ] **PR-AUC 성질**: 유의미한 신호가 있는 합성 데이터에서 두 모델 PR-AUC > 무작위 기준선(=양성비율). 동어반복 금지.
  - [ ] **리프트 산식**: 알려진 baseline/model 값 → 기대 리프트(하드코딩 oracle).
  - [ ] **누수 배제**: X에 `Naive_Bayes_Classifier_*`·`Attrition_Flag`가 없음을 단언(합성 주입 포함).
  - [ ] **라벨 매핑**: `Attrited Customer`만 양성(1), 나머지 0. 문자열 오타/공백에 강건한지 정책 명시.
  - [ ] 순수성(입력 불변), 인덱스/조인키(CLIENTNUM) 정합.
- [ ] **T6. 실행·커밋**
  - [ ] 실데이터로 03 실행 → `churn_scored.parquet`·`churn_model.joblib` 생성, 비교표 재현. 03 2회 실행 `churn_prob` 동일(AD-7).
  - [ ] `pytest` 전체 green. **현 기준선 170 passed, 회귀 0.** 스토리 단위 커밋. Obsidian 미러 갱신.

## Dev Notes

### 🚨 착수 전 — xgboost 설치 (모델링 블록 2번째)

`xgboost` 미설치 확인. `requirements.txt:25`(`# xgboost>=3.3,<4.0`) 주석 해제 후 설치. sklearn·joblib은 1-4에서
설치됨. 실제 버전 기록. **XGBoost 결정론 함정(AD-7)**: `n_jobs>1`이면 스레드별 부동소수 축약 순서가 달라져
확률이 미세하게 흔들리고, 그게 하위 분위수 경계에서 고객을 분면 넘나들게 한다 → `n_jobs=1` 필수. `tree_method`도
고정(예: `"hist"`). `random_state`도.

### 🚨 라벨은 X에 섞지 않는다 (누수 위생, 1-5 계승)

03_train_churn은 **features_customers(X=RFM 프록시) + bankchurners(y=Attrition_Flag)를 CLIENTNUM 조인**한다.
`Attrition_Flag`는 **y로만** 쓰고 피처 테이블에 넣지 않는다. `Naive_Bayes_Classifier_*` 2컬럼(타깃 상관 ±1.0)은
features_customers에 애초에 없지만(1-3 배제), 모델 X 구성에서도 **방어적으로 배제 단언**한다(sprint-status가 1-6에
누수 재감사를 명시). 예측자는 `recency_proxy`·`frequency_proxy`·`monetary_proxy` 3개.

### 얇은 피처셋 — 정직하게 (AC2 정직성과 직결)

features_customers의 RFM 프록시 3개만 예측자다. BankChurners의 다른 이탈 신호(관계 수·비활성·컨택 수 등)는
features 테이블에 없다(그건 1-3/1-4 범위였고 확장은 별도 스토리). 따라서 **모델 성능은 제한적일 수 있고 +15%
리프트에 못 미칠 수 있다.** 이는 실패가 아니라 **정직하게 보고할 사실**이다(AC2, P1 1-7a 선례). 원인(얇은 피처셋·
라벨 단면성)을 리포트에 적는다.

### AD-5는 1-6b — 지금 만들지 않는 것

1-6a는 모델을 **원자적으로 저장**하고 `churn_scored.parquet`에 AD-13 신선도 meta를 붙인다. 그러나 **AD-5
아티팩트 정체성**(`churn_model.meta.json`의 `artifact_id` 콘텐츠 해시·`trained_at`·`RANDOM_SEED`·입력 해시·feature
목록·라이브러리 버전, 그리고 `churn_scored`의 `artifact_id` 컬럼)은 **1-6b 소관**이다. 1-7 SHAP이 이 정체성에
의존하므로 1-6b에서 확립한다. 1-6a에서 임시로 흉내내지 말 것(반쪽 구현이 1-6b와 충돌).

### 결정론 상세 (AD-7)

- XGBoost: `random_state=RANDOM_SEED`, `n_jobs=1`, `tree_method="hist"`(고정). 
- LogisticRegression: `random_state=RANDOM_SEED`(solver에 따라 무영향일 수 있으나 명시), 결정론적 solver.
- CV: `StratifiedKFold(n_splits, shuffle=True, random_state=RANDOM_SEED)`.
- **수용 기준**: 03 2회 실행 → `churn_prob` 완전 동일. 테스트로 고정. (1-4 교훈: 결과 동일뿐 아니라 생성자
  인자 spy로 seed·n_jobs·tree_method 주입 검증.)

### 1-2~1-5에서 물려받은 것 (재사용·재발명 금지)

- **stage 형태**: `main(input_paths, output_paths)`만, 40행 이하, `main` 외 def/lambda 금지. writer/무거운 호출은
  crm으로 내림(1-3 write_parquet_with_meta·1-4 build_feature_table 선례). joblib.dump도 crm 헬퍼로.
- **원자적 쓰기·meta**: `write_parquet_with_meta`+`build_meta`(scored). 모델은 `atomic_write_bytes` 계열.
- **신선도 2단 게이트**: verify_inputs + is_output_stale(expected_stage). 입력 2개 각각 producer 검증.
- **CLIENTNUM 유일성·null 방어**(1-4/1-5 High 교훈): X·y 조인 전 키 유일·비null 검증. 인덱스 아닌 키로 조인.
- **테스트 규율**: 성질 + 하드코딩 oracle + 생성자 spy(결정론/하이퍼파라미터). "문서가 테스트를 앞서지 않게".
- **ASCII 규율**·`.venv/Scripts/python.exe -m pytest`.

### 이 스토리가 만들지 않는 것 (범위 경계)

- **AD-5 아티팩트 정체성**(1-6b). SHAP(1-7). 마트(4-1)·`05_marts` identity 실패(4-1/4-x).
- 피처 확장(1-3/1-4 범위, 완료). 관측/예측창(AD-6이 금지).
- 새 config 상수는 필요 시만(예: CV 폴드 수·tree_method는 config 규약 상수로 등재 검토 — 데이터 유래 아님).

### Project Structure Notes

```
crm/churn/model.py                         # NEW - 두 모델 학습/CV/PR-AUC/리프트/스코어(순수, AD-6 표기)
crm/churn/artifact.py                       # NEW - save_model(원자적 joblib). AD-5 meta는 1-6b
pipelines/03_train_churn.py                 # NEW - 얇은 stage(입력2/출력2, 40행)
tests/churn/__init__.py                      # NEW
tests/churn/test_model.py                    # NEW - 결정론 spy·불균형·PR-AUC·리프트·누수·라벨
docs/implementation-artifacts/churn-model-report-1-6a.md   # NEW - 비교표·리프트·정직성·라벨
requirements.txt                            # UPDATE - xgboost 주석 해제
crm/config.py                               # UPDATE(필요시) - CHURN_CV_FOLDS 등 규약 상수
```

- 출력: `models/churn_model.joblib`(gitignore), `data/churn_scored.parquet`(+AD-13 meta).
- `tests/churn/`는 신규 패키지(`__init__.py` 필요, `tests/segment/` 선례).

### References

- [Source: docs/planning-artifacts/epics.md#Story 1.6] — AC 원문(FR4/FR5, AD-6, NFR2, 정직성)
- [Source: .../ARCHITECTURE-SPINE.md#AD-7] — XGBoost n_jobs=1·tree_method·seed
- [Source: .../ARCHITECTURE-SPINE.md#AD-6] — 단면 라벨 표기(시계열 금지)
- [Source: .../ARCHITECTURE-SPINE.md#AD-5] — 아티팩트 정체성(1-6b가 구현, 여기선 경계만)
- [Source: docs/implementation-artifacts/sprint-status.yaml] — 1-6 분할 근거·누수 재감사 경고
- [Source: docs/implementation-artifacts/1-5-...md] — 라벨/타깃 위생, CLIENTNUM null 방어
- [Source: 실측 2026-07-21] — 이탈률 0.161, scale_pos_weight 5.224, features 스키마

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List

## Change Log

| 날짜 | 변경 |
|---|---|
| 2026-07-21 | 스토리 1-6a create-story(1-6 분할): baseline+XGBoost+불균형/CV/PR-AUC+리프트+라벨(AD-6)+누수 재감사. AD-5 정체성은 1-6b. Status → ready-for-dev. 기준선 170 passed |