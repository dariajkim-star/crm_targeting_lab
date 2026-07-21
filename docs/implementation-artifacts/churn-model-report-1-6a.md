# 이탈위험 분류 모델 비교 리포트 (스토리 1-6a)

BankChurners 고객의 **이탈 위험을 cross-sectional로 분류**하는 baseline 로지스틱 vs XGBoost 비교.
수치는 실데이터(n=10,127)로 산출했다. 라이브러리: scikit-learn 1.9.0, xgboost 3.3.0.

> **⚠️ 1-7에서 예측자가 확장됐다(2026-07-21).** 1-6a는 RFM 프록시 **3개**로 학습했고, 1-7이 이탈 신호
> **5개**를 raw 프레임에서 추가해 **8개**로 재학습했다(CAP-3 요인 해석이 3피처로는 순환논법이 되기 때문;
> `Credit_Limit`은 외부 리뷰 권고에 따른 ablation에서 기여 미미 — PR-AUC +0.005·전역 9/9위 — 로 제외).
> 아래 표는 **3피처(1-6a) / 8피처(1-7) 전후를 병기**한다. 옛 수치를 지우지 않는 이유는 리프트가 어떻게
> 움직였는지가 그 자체로 발견이기 때문이다.

## 라벨 성격 — cross-sectional 분류 (AD-6/NFR2)

`Attrition_Flag`는 **사후 단면(snapshot) 라벨**이다. 이 모델은 **"이탈 위험 분류(cross-sectional)"**이지
시계열 예측이 아니다 — **관측창·예측창이 없다.** "이탈을 예측한다"는 표현을 쓰지 않으며, 산출물의
`churn_prob`는 미래 시점 확률이 아니라 **현재 스냅샷에서의 이탈 위험 점수**다. 이 한계는 그대로 인계된다.

## 데이터·설정

- **예측자(X) — 8개**(1-7 확장): features 유래 3개(`recency_proxy`·`frequency_proxy`·`monetary_proxy`)
  + raw 유래 5개(`Total_Relationship_Count`·`Contacts_Count_12_mon`·`Total_Amt_Chng_Q4_Q1`·
  `Total_Ct_Chng_Q4_Q1`·`Avg_Utilization_Ratio`). `Credit_Limit`은 ablation(리뷰 권고) 결과 제외. 점수(R/F/M)·`segment_id`는 파생/양자화라 제외.
  `Months_Inactive_12_mon`은 `recency_proxy`와 **값이 동일**해 제외(중복 투입 시 한쪽 SHAP이 0이 되어
  "비활성은 무관"이라는 거짓 해석을 만든다 — 실측 확인). **확장은 raw 경유라 `features_customers`는 불변**이며
  1-4 세그먼트·1-5 페르소나는 회귀 0이다.
- **라벨(y)**: `Attrition_Flag == "Attrited Customer"`(1), 그 외 0. **X와 엄격 분리**(라벨을 피처에 섞지 않음).
- **누수 재감사(sprint-status 경고)**: `Naive_Bayes_Classifier_*` 2컬럼(타깃 상관 ±1.0)은 X에 없음.
  `Attrition_Flag`도 X에 없음. `build_xy`가 방어적으로 단언(테스트 고정). → AUC=1.0 무의미 누수 차단.
- **불균형**: 이탈률 **16.07%**(1,627 / 10,127). XGBoost `scale_pos_weight = 음성/양성 ≈ 5.22`,
  baseline 로지스틱 `class_weight="balanced"`.
- **baseline 스케일링(리뷰 반영)**: L2 로지스틱은 스케일 불변이 아니므로 baseline에 `StandardScaler`를
  적용했다 — 미스케일 baseline이 리프트를 부풀릴 위험을 차단. (실측: 이 데이터에선 스케일 유무가
  baseline PR-AUC를 사실상 바꾸지 않았다 0.4286→0.4297 — 우위가 스케일링 부재 탓이 아님을 확인.)
- **결정론(AD-7)**: XGBoost `random_state=42`·**`n_jobs=1`**·`tree_method="hist"` 고정. CV는
  `StratifiedKFold(shuffle, random_state=42)` + **CLIENTNUM 정규 정렬**(행 순서가 CV 수치를 못 바꾸게).
  03 2회 실행 `churn_prob` 동일은 **회귀 테스트로 고정**(`test_stage_output_is_deterministic_across_two_runs`).

## 모델 비교 — PR-AUC (주지표)

불균형(16%)이라 **PR-AUC(average precision)를 주지표**로 삼는다. ROC-AUC는 기저율만 겨우 넘는 모델도
후하게 평가한다. 5-fold 교차검증 평균:

| 모델 | PR-AUC — 3피처(1-6a) | PR-AUC — 8피처(1-7) |
|---|---|---|
| 무작위 기준선(=양성 비율) | 0.1607 | 0.1607 |
| baseline 로지스틱(StandardScaler + class_weight=balanced) | 0.4297 | **0.6751** |
| **XGBoost** | **0.8024** | **0.9508** |
| **리프트(FR5)** | **+86.7%** | **+40.8%** |

**리프트가 +86.7% → +40.8%로 떨어졌는데, 모델은 좋아졌다.** 두 모델이 같은 피처를 받으므로 baseline도
함께 강해졌고(0.4297 → 0.6751), 리프트는 **XGBoost의 품질이 아니라 baseline 대비 상대 우위**를 재는
값이기 때문이다. 절대 성능은 0.8024 → 0.9508로 올랐다. +15% 목표는 **판정이 아니라 서술**이며(AC2),
두 구성 모두 상회한다.

### +15% 목표 대비 (AC2 정직성)

목표 +15%를 두 구성 모두 상회한다(3피처 +86.7% / 8피처 +40.8%). 실패 조항의 반대 경우지만 맥락을
정직하게 밝힌다: 두 구성 모두에서 **`frequency_proxy`(연간 거래 건수)가 가장 강한 신호**이며(1-7 SHAP
전역 1위, 평균 |SHAP| 2.87), 이탈 고객은 거래가 급감한다. **우위의 원인은 확정하지 않는다**(리뷰 반영):
스케일링 부재 탓이 아님은 실증했으나, 비선형/상호작용 기여를 분리하는 ablation은 수행하지 않았다.

> **주의(정직성)**: 이 리프트는 **모델 품질의 상한이 아니다.** 라벨이 단면적이고 피처가 8개로 제한되므로,
> 여기 수치를 "이탈을 몇 % 맞춘다"는 운영 성능으로 과대 해석하지 말 것. 특히 **8피처 PR-AUC 0.9508은
> in-sample CV 값**이며, 실제 운영 성능이 아니다. 이는 **baseline 대비 상대 비교**이자 타겟팅
> 프레임(3-x)의 입력일 뿐이다.

### `churn_prob`는 미보정 in-sample 점수다 (리뷰 반영, 정직성)

최종 모델은 전체 고객으로 학습한 뒤 **같은 고객을 채점**하므로 `churn_prob`는 out-of-fold가 아닌
**in-sample 점수**이고, `scale_pos_weight` 재가중 때문에 **보정된 확률이 아니다**(8피처 실측: 평균
churn_prob 0.195 vs 실제 이탈률 0.161 — 3피처 때의 0.260보다 가까워졌으나 여전히 보정된 값이 아니다). 컬럼명은 스파인(AD-5)이 고정한 것이라 유지하되, **순위
신호(누가 더 위험한가)로만 사용**할 것. calibration은 평가하지 않았다. 아래 세그먼트 평균 비교도
방향 정합의 참고일 뿐 **독립 검증·calibration 증거가 아니다**.

## 파이프라인 정합성 (참고)

산출된 `churn_prob`의 **세그먼트별 평균**은 1-5의 세그먼트별 실제 이탈률과 정합한다:

| segment_id | 평균 churn_prob (3피처) | 평균 churn_prob (8피처) | 1-5 실제 이탈률 |
|---|---|---|---|
| 1 (최고가치) | 0.002 | 0.003 | 0.0% |
| 2 | 0.070 | 0.055 | 4.0% |
| 3 | 0.175 | 0.138 | 11.6% |
| 4 (저활동) | 0.590 | 0.432 | 36.1% |

모델의 위험 점수가 세그먼트 가치 계층·실제 이탈과 같은 방향으로 정렬된다(파이프라인 전체 일관성).

## 산출물

- `models/churn_model.joblib` — 학습된 XGBoost(원자적 저장). gitignore.
- `models/churn_model.meta.json` — **AD-5 정체성 기록(1-6b에서 추가)**. gitignore.
- `data/churn_scored.parquet` — `CLIENTNUM` + `churn_prob` + **`artifact_id`**(+ AD-13 신선도 meta).
- `data/churn_shap.parquet` — **1-7 추가**. `CLIENTNUM` + 예측자 8개의 SHAP 값 + `artifact_id`(+ AD-13 meta).
  요인 해석은 [churn-drivers-actions-1-7.md](churn-drivers-actions-1-7.md).

## 아티팩트 정체성 (AD-5, 1-6b에서 확립)

`artifact_id`는 **직렬화된 모델 바이트의 SHA-256**이다. 같은 데이터·같은 seed로 재학습하면 같은 id가 나온다
(내용이 같으면 같은 아티팩트). 실측 재현: 별도 출력 경로로 stage를 다시 돌려도 id와 `churn_prob`이 완전 동일.

```json
{
  "artifact_id": "c751c63d5b58...",
  "trained_at": "2026-07-21T...(재산출)",
  "random_seed": 42,
  "inputs": { "features_customers.parquet": "540dba50...", "bankchurners.parquet": "2b48a9f6..." },
  "features": ["recency_proxy", "frequency_proxy", "monetary_proxy", "Total_Relationship_Count",
               "Contacts_Count_12_mon", "Total_Amt_Chng_Q4_Q1", "Total_Ct_Chng_Q4_Q1",
               "Avg_Utilization_Ratio"],
  "libraries": { "python": "3.12.10", "xgboost": "3.3.0", "scikit-learn": "1.9.0",
                 "joblib": "1.5.3", "numpy": "2.4.6", "pandas": "3.0.3" },
  "metrics": { "baseline_pr_auc": 0.6751..., "xgboost_pr_auc": 0.9508...,
               "pr_auc_lift": 0.4084..., "positive_rate": 0.1606596227905599, "cv_folds": 5.0 }
}
```

`churn_scored.parquet`·`churn_shap.parquet`의 10,127행 전부가 이 `artifact_id` 하나를 보유한다(unique = 1).
검증은 세 가지가 모두 일치할 때만 통과한다: **디스크의 모델 바이트** · **meta 기록** · **점수에 찍힌 id**.

**정직한 표현 (외부 리뷰 반영)**:
- `artifact_id`가 증명하는 것은 **같은 모델 내용**이지 **같은 학습 실행**이 아니다. 동일 데이터·동일 seed로
  재학습하면 같은 id가 나오므로(의도된 성질) 이전 동일 실행의 점수도 검증을 통과한다. 실행 단위 구분이
  필요해지면 별도 `run_id`(nonce)가 필요하지만, 현재 어떤 하위 스토리도 그것을 요구하지 않는다.
- crash 창 자체는 사라지지 않았다. 그 창에서 죽으면 **다음 stage 실행에서 탐지되어 재학습**된다(즉시 복구 아님).
- 바이트 재현성은 **고정 실행 환경 기준**이다(python 3.12.10 / joblib 1.5.3 / xgboost 3.3.0 실측). 인터프리터·
  라이브러리·플랫폼이 바뀌면 같은 의미의 모델도 다른 id가 나올 수 있다 — 재학습을 유발할 뿐 오탐(다른 모델을
  같다고 인정)은 아니므로 보수적으로 안전한 방향이다.

**역할 구분(혼동 금지)**: `artifact_id`(AD-5)는 "이 산출물들이 같은 모델을 가리키나"를 답하고, `.meta.json`의
`config_hash`+입력 해시(AD-13)는 "다시 계산해야 하나"를 답한다. 입력 드리프트 탐지는 AD-13의 일이다.

위 `metrics` 블록 덕분에 이 표의 숫자는 손으로 옮겨 적은 값이 아니라 아티팩트에 기록된 값이다.

## 다음 스토리 인계

- ~~**1-7 (SHAP)**~~ — **완료(2026-07-21)**: SHAP을 `03_train_churn`에서만 산출해 `churn_shap.parquet`으로
  저장하고, 세 산출물이 동일 `artifact_id`를 보유하도록 결속했다. 예측자도 8개로 확장됐다(위 전후 비교).
- **4-1/4-x (마트)**: `05_marts`가 입력 `artifact_id` 불일치 시 즉시 실패 — `read_verified_model_meta`·
  `verify_artifact_identity`·`outputs_share_identity`를 재사용한다.
- **범위 밖**: 범주형 피처 인코딩(AD-7 사전순 매핑 설계 필요 — deferred-work), 관측/예측창(AD-6 금지).
