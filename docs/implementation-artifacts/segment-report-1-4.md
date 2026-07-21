# 세그먼트 리포트 (스토리 1-4)

BankChurners 고객을 RFM 프록시로 K-means 세그먼트한다. 수치는 실데이터
(`data/features_customers.parquet`, n=10,127)로 산출했으며 통화·단위 기호를 붙이지 않는다
(NFR3 — BankChurners는 통화 단위가 없다). 사용 라이브러리: scikit-learn 1.9.0.

## 클러스터링 입력과 전처리

- **입력**: RFM **원척도 프록시** `recency_proxy`·`frequency_proxy`·`monetary_proxy`.
  점수(1..5)는 R이 4레벨로 거칠어 원척도가 더 많은 신호를 담는다.
- **전처리**: `StandardScaler` 표준화(monetary가 수천 단위라 미표준화 시 거리 지배).
  이 스케일링은 클러스터링 전처리이지 가치 축 정규화(AD-11 금지)가 아니다 — 마트는 원척도 보존.
- **결정론(AD-7)**: `KMeans(n_clusters=k, random_state=42, n_init=10)`. `n_init`을 명시
  (sklearn 1.4+ 기본값 `"auto"`에 의존하지 않음). 클러스터링 전 **CLIENTNUM 정규 정렬**로
  행 순서 불변 보장(KMeans는 k-means++ 초기화가 데이터 순서에 민감).

## k 선정 근거 (AC1)

k=2..10에서 elbow(inertia)·실루엣 산출(seed 42):

| k | inertia | silhouette |
|---|---|---|
| 2 | 19523.4 | **0.4771** |
| 3 | 13216.1 | 0.3726 |
| **4** | **8877.2** | **0.4119** |
| 5 | 6914.2 | 0.4256 |
| 6 | 5725.9 | 0.4344 |
| 7 | 4948.4 | 0.4367 |
| 8 | 4426.1 | 0.4452 |
| 9 | 3943.8 | 0.4473 |
| 10 | 3496.3 | 0.4535 |

**선택: k=4.**
- **elbow**: inertia 한계 감소가 2→3(-6307)→4(-4339)까지 급락 후 4→5(-1963)에서 평탄해진다.
  k=4가 팔꿈치다.
- **[가정/판단] 실루엣 k=2가 최고(0.477)이나 채택하지 않는다**: k=2는 고/저 가치 2분할일 뿐이라
  다운스트림(1-5 페르소나 4~6개, 3-x 2×2 타겟팅)에 쓸 해상도가 없다. k=4는 분리도(0.412)와
  실행가능성(actionable 세그먼트 수)의 균형이며, `SEGMENT_K`로 config에 고정했다.
- **AD-1**: k는 fitted threshold가 아니라 분석가가 곡선을 보고 고른 하이퍼파라미터이며
  (`RFM_QUANTILES` 선례), BankChurners 레인 안에서만 도출·사용한다.

## 안정 ID (AC2) — 가치 계층 매핑

원시 KMeans 라벨은 실행/​seed마다 임의 번호다. **`monetary_proxy`(= 1-3이 저장한
`customer_value` 출력) 중앙값 내림차순**으로 재정렬해 `segment_id` 1..4를 부여한다(1=최고가치).
`customer_value`는 **소비**할 뿐 재계산하지 않으며 `Total_Trans_Amt`를 명명하지 않는다(AD-11).
중앙값 동점 시 tiebreak은 **중앙값 → 평균 → 원시 라벨**의 전순서로 고정(AD-7).

| segment_id | n | monetary 중앙값 | frequency 중앙값 | recency(비활성월) 중앙값 | 해석(참고) |
|---|---|---|---|---|---|
| 1 | 770 | 14621 | 110.5 | 2 | 최고가치·고빈도 (챔피언) |
| 2 | 3329 | 4350 | 75 | 2 | 중가치 주력 |
| 3 | 2777 | 4312 | 73 | 3 | 중가치·상대적 비활성 |
| 4 | 3251 | 1774 | 38 | 2 | 저가치·저빈도 |

segment 1의 monetary 중앙값이 가장 높고 4로 갈수록 단조 감소한다(재실행에 고정, AD-7).
전체 실루엣(k=4) = 0.4119.

## 결정론 실증 (AC3 / NFR4)

- `assign_segments` 2회 실행 → `segment_id` 완전 동일(테스트 `test_deterministic_across_runs`).
- **행 순서 셔플 후 고객별 동일**(`test_invariant_to_row_order`, fuzzy fixture로 순서민감성
  실검출). 정규 정렬 제거 변이는 이 테스트가 사살함을 확인.
- 02_features **2회 연속 실행 → 산출 parquet 데이터 동일** 실증.

## 다음 스토리 인계

- **1-5 (프로필·페르소나)**: `FEATURE_TABLE_COLUMNS`(RFM + `segment_id`)를 소비. 위 프로파일 표를
  페르소나 서술의 출발점으로. `customer_value`가 필요하면 1-2 함수 출력(`monetary_proxy`)을 소비.
- **4-1 (마트)**: `segment_id`는 원척도 가치와 함께 마트에 실린다. 스케일링된 클러스터링 입력은
  산출물에 남기지 않는다(원척도 보존).
- **범위 밖**: 세그먼트 프로필 서술(1-5), 이탈 모델(1-6). 1-4는 `segment_id`와 가치순 정규화까지.
