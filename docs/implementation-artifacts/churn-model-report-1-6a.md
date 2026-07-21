# 이탈위험 분류 모델 비교 리포트 (스토리 1-6a)

BankChurners 고객의 **이탈 위험을 cross-sectional로 분류**하는 baseline 로지스틱 vs XGBoost 비교.
수치는 실데이터(n=10,127)로 산출했다. 라이브러리: scikit-learn 1.9.0, xgboost 3.3.0.

## 라벨 성격 — cross-sectional 분류 (AD-6/NFR2)

`Attrition_Flag`는 **사후 단면(snapshot) 라벨**이다. 이 모델은 **"이탈 위험 분류(cross-sectional)"**이지
시계열 예측이 아니다 — **관측창·예측창이 없다.** "이탈을 예측한다"는 표현을 쓰지 않으며, 산출물의
`churn_prob`는 미래 시점 확률이 아니라 **현재 스냅샷에서의 이탈 위험 점수**다. 이 한계는 그대로 인계된다.

## 데이터·설정

- **예측자(X)**: features_customers의 연속 RFM 프록시 3개 — `recency_proxy`·`frequency_proxy`·`monetary_proxy`.
  점수(R/F/M)·`segment_id`는 파생/양자화라 제외(중복 회피).
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

| 모델 | PR-AUC (5-fold CV) |
|---|---|
| 무작위 기준선(=양성 비율) | 0.1607 |
| baseline 로지스틱(StandardScaler + class_weight=balanced) | 0.4297 |
| **XGBoost** | **0.8024** |

**baseline 대비 XGBoost PR-AUC 리프트 = +86.7%** (FR5).

### +15% 목표 대비 (AC2 정직성)

목표 +15%를 **크게 상회(+86.7%)한다.** 이는 실패 조항의 반대 경우지만, 정직하게 맥락을 밝힌다:
얇은 RFM 피처셋임에도 성능이 높은 이유는 **`frequency_proxy`(연간 거래 건수, `Total_Trans_Ct`)가
이 데이터셋에서 이탈과 강하게 연관**되기 때문이다(이탈 고객은 거래가 급감). **우위의 원인은 확정하지
않는다**(리뷰 반영): 스케일링 부재 탓이 아님은 실증했으나(위), 비선형/상호작용 기여를 분리하는
ablation은 수행하지 않았다 — "비선형 포착 덕분"은 가설이지 증명된 주장이 아니다.

> **주의(정직성)**: 이 리프트는 **모델 품질의 상한이 아니다.** 피처가 3개뿐이고 라벨이 단면적이므로,
> 여기 수치를 "이탈을 몇 % 맞춘다"는 운영 성능으로 과대 해석하지 말 것. 이는 **baseline 대비 상대
> 비교**이자 타겟팅 프레임(3-x)의 입력일 뿐이다.

### `churn_prob`는 미보정 in-sample 점수다 (리뷰 반영, 정직성)

최종 모델은 전체 고객으로 학습한 뒤 **같은 고객을 채점**하므로 `churn_prob`는 out-of-fold가 아닌
**in-sample 점수**이고, `scale_pos_weight` 재가중 때문에 **보정된 확률이 아니다**(실측: 평균
churn_prob 0.260 vs 실제 이탈률 0.161). 컬럼명은 스파인(AD-5)이 고정한 것이라 유지하되, **순위
신호(누가 더 위험한가)로만 사용**할 것. calibration은 평가하지 않았다. 아래 세그먼트 평균 비교도
방향 정합의 참고일 뿐 **독립 검증·calibration 증거가 아니다**.

## 파이프라인 정합성 (참고)

산출된 `churn_prob`의 **세그먼트별 평균**은 1-5의 세그먼트별 실제 이탈률과 정합한다:

| segment_id | 평균 churn_prob | 1-5 실제 이탈률 |
|---|---|---|
| 1 (최고가치) | 0.002 | 0.0% |
| 2 | 0.070 | 4.0% |
| 3 | 0.175 | 11.6% |
| 4 (저활동) | 0.590 | 36.1% |

모델의 위험 점수가 세그먼트 가치 계층·실제 이탈과 같은 방향으로 정렬된다(파이프라인 전체 일관성).

## 산출물

- `models/churn_model.joblib` — 학습된 XGBoost(원자적 저장). gitignore.
- `data/churn_scored.parquet` — `CLIENTNUM` + `churn_prob`(+ AD-13 신선도 meta).

## 다음 스토리 인계

- **1-6b (AD-5 아티팩트 정체성)**: `churn_model.meta.json`(`artifact_id` 콘텐츠 해시·`trained_at`·seed·입력
  해시·feature 목록·라이브러리 버전) + `churn_scored`에 `artifact_id` 컬럼. 1-6a는 정체성을 **아직 부여하지
  않았다** — 1-6b가 `churn_prob`↔SHAP 결속을 위해 확립한다.
- **1-7 (SHAP)**: 동일 아티팩트(1-6b의 artifact_id)에서 SHAP을 `03_train_churn` 단계에서만 산출.
- **범위 밖**: 피처 확장(모델 성능을 높이려면 02_features에 신호 추가 — 별도 스토리), 관측/예측창(AD-6 금지).
