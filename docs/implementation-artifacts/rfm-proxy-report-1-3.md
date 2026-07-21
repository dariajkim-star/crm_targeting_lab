# RFM 프록시 지표 리포트 (스토리 1-3)

BankChurners 레인에는 구매 이벤트 로그가 없다. 따라서 R·F·M을 데이터셋이 실제로
담은 요약 컬럼에서 **프록시**로 구성한다. 수치는 실데이터(`data/bankchurners.parquet`,
n=10,127)로 산출했으며 통화·단위 기호를 붙이지 않는다(NFR3 — BankChurners는 통화 단위가
없다).

## R·F·M 도출 정의 (FR1, 각 1줄)

- **R (Recency 프록시)** ← `Months_Inactive_12_mon`. 최근 12개월 비활성 개월 수.
  **극성 반전**: 값이 클수록 "덜 최근"이므로 Recency 점수는 이를 뒤집는다 —
  비활성 개월이 **적을수록 R 점수가 높다**.
- **F (Frequency 프록시)** ← `Total_Trans_Ct`. 최근 12개월 거래 **건수**.
- **M (Monetary 프록시)** ← `crm.segment.value.customer_value(df)` 출력(원천은
  `Total_Trans_Amt`, 최근 12개월 거래 **금액**). 원컬럼을 직접 명명하지 않고
  가치 함수 출력을 소비한다 — 아래 [AD-11] 참조.

## 구간화 방식 선택과 근거 (AC1)

**방식: 분위수(quantile) 5분위 점수, `pd.qcut(duplicates="drop")`.**

- **왜 분위수인가**: RFM의 고전적 관례이고, 고정 경계는 어차피 분포를 봐야 정할 수
  있어 결국 데이터 유래가 된다. 분위수는 경계 산출 규칙이 투명하고 재현 가능하다.
- **경계는 BankChurners 분포에서만 도출**한다(AD-1). 분위수 경계는 입력 프레임에서
  **런타임 산출**하며 `crm/config.py`에 하드코딩하지 않는다 — 데이터 유래 값을 config에
  park하면 레인 간 누수가 된다. config에 있는 것은 분위수 **개수**(`RFM_QUANTILES=5`,
  선험적 규약)뿐이다.
- **결정론(AD-7)**: `qcut`은 고정 분포에서 항상 같은 경계를 그린다. 동일 입력 2회 산출이
  완전히 동일함을 테스트로 실증(`test_deterministic_across_runs`).

### 실데이터 분위수 경계 (dev 산출, 2026-07-21)

| 축 | 원본 | 달성 버킷 수 | 경계 |
|---|---|---|---|
| R | `Months_Inactive_12_mon` | **4** (5 목표에서 붕괴) | `[0, 1, 2, 3, 6]` |
| F | `Total_Trans_Ct` | 5 | `[10, 41, 61, 73, 83, 139]` |
| M | `customer_value()` | 5 | `[510, 1914, 3192.4, 4267, 4926, 18484]` |

### [가정/한계] R 프록시의 저해상도 — 정직하게 기록

`Months_Inactive_12_mon`은 **0~6의 7개 정수 레벨**뿐이고 1·2·3에 전체의 **약 92%**가
몰려 있다(1→2233, 2→3282, 3→3846). 5분위를 목표해도 중복 경계 때문에 **4개 버킷으로
붕괴**한다. 이는 **데이터의 성질이지 코드 결함이 아니다** — `duplicates="drop"`으로 붕괴를
받아들이고, R 점수는 F·M보다 해상도가 낮다는 사실을 여기 명시한다. R 점수 분포(반전 후):
`{1: 737, 2: 3846, 3: 3282, 4: 2262}`.

R을 억지로 5등분(예: `rank(method="first")` 후 qcut)하면 **같은 비활성 개월 고객이 서로
다른 점수**를 받아 해석 불가능해지므로 채택하지 않았다.

## 산출물

- 파일: `data/features_customers.parquet` (pipeline-diagram.md 정규 경로, 03_train_churn 소비)
- 컬럼: `CLIENTNUM, recency_proxy, frequency_proxy, monetary_proxy, R_score, F_score, M_score`
- 형제 meta: `features_customers.parquet.meta.json` (stage `02_features`, 입력
  `bankchurners.parquet` 해시, `config_hash`, 행수 10,127)

### [설계] 누수 컬럼 배제 (AC5 — 1-6 감사 이전 1차 방어선)

`Naive_Bayes_Classifier_*` 2개(타깃 상관 ±1.0000)는 산출 컬럼 집합
(`RFM_OUTPUT_COLUMNS`)에 **아예 선택되지 않는다**. 파생 지표만 담는 화이트리스트
방식이라 원본에 무엇이 붙어 있어도 새어들지 않으며, `test_leakage_columns_are_excluded`가
합성 누수 컬럼을 심어 배제를 실증한다. 1-6 누수 감사가 재확인한다.

## [AD-11] M축과 가치 축 이름 소유권

M(Monetary)은 곧 고객가치 축이다. AD-11(2026-07-20 A안)은 `value.py`를 제외한 `crm/`의
어떤 모듈도 `Total_Trans_Amt`를 명명하지 못하게 하므로, `features.py`는 **`customer_value(df)`
출력을 소비**한다. 이는 가드 우회가 아니라 AD-11이 의도한 배선이며(모든 소비자는
`customer_value`를 소비·재계산 금지), 의미적으로도 M축=가치축이라 정확하다. 기존 가드
`find_value_recomputation_violations`가 `features.py`를 스캔하고 위반 0건임을 확인했다.

리포트(.md)에서 `Total_Trans_Amt`를 언급하는 것은 가드 대상이 아니다 — 가드는 `crm/`의
`.py` AST 상수/어트리뷰트만 검사한다.

## 다음 스토리 인계

- **1-4 (K-means)**: 이 표의 R/F/M(원척도 또는 점수)을 소비한다. `CLIENTNUM`으로 조인하고,
  `customer_value` 중앙값 내림차순 안정 ID를 부여할 때 `monetary_proxy`가 아니라 1-2
  `customer_value()`를 소비할 것(AD-11).
- **1-6 (이탈 모델)**: 누수 컬럼 감사에서 `Naive_Bayes_Classifier_*` 2개가 피처에
  없음을 재확인. 02_features가 예측 피처를 추가로 실어야 하면 같은 stage를 확장한다.
- **DQ2**: 02는 `verify_inputs`(producer/config) + `is_output_stale`(입력 콘텐츠 드리프트)
  2단 게이트를 통과해야 재계산한다. 산출물 **자체**의 콘텐츠 해시(수동 변조 탐지)는 여전히
  계약 밖이다(deferred-work.md 1-1b).
