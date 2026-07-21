---
baseline_commit: 34b10dc
baseline_passed: 133
---

# Story 1.4: K-means 세그먼트와 안정 ID

Status: ready-for-dev

## Story

As a 분석가,
I want 근거 있는 k로 세그먼트를 나누고 세그먼트 번호가 재실행에도 고정되기를,
so that 리포트의 "세그먼트 3"이 조용히 다른 집단을 가리키는 사고가 일어나지 않는다.

## Acceptance Criteria

**AC1 — seed 주입 + k 선정 근거**
**Given** RFM 피처가 주어졌을 때
**When** K-means를 적합하면
**Then** `random_state`·`n_init`이 `RANDOM_SEED`에서 명시적으로 주입된다(AD-7)
**And** elbow/실루엣 곡선과 k 선정 근거가 산출물에 제시된다(FR2)

**AC2 — 가치순 안정 ID**
**Given** 클러스터가 생성됐을 때
**When** 세그먼트 ID를 부여하면
**Then** 원시 클러스터 인덱스가 아니라 `customer_value` 중앙값 내림차순으로 재정렬한 안정 ID(`segment_id` 1..k)를 쓴다(AD-7)
**And** `customer_value`는 1.2의 함수 출력을 소비하며 재계산하지 않는다(AD-11)

**AC3 — 결정론**
**Given** 결정론이 요구될 때
**When** 세그멘테이션을 2회 연속 실행하면
**Then** `segment_id` 배정이 완전히 동일하다
**And** 이를 검증하는 테스트가 존재한다(NFR4)

## Tasks / Subtasks

- [ ] **T0. scikit-learn 설치** (AC: 1) ← **착수 전 필수, 이 스토리가 첫 설치 스토리**
  - [ ] `requirements.txt` 24행 `# scikit-learn>=1.9,<2.0` **주석 해제**(README INSTALL POLICY: "처음 필요로 하는 스토리가 설치"). 설치: `.venv/Scripts/python.exe -m pip install -r requirements.txt`.
  - [ ] 설치된 실제 버전을 Dev Notes·리포트에 기록. **sklearn 1.4+부터 `KMeans`의 `n_init` 기본값이 `"auto"`** — AD-7이 명시 주입을 요구하므로 `n_init`를 절대 기본값에 맡기지 말 것.
- [ ] **T1. K-means 세그멘테이션 순수 모듈 `crm/segment/segments.py`** (AC: 1, 2, 3) ← 로직 소유
  - [ ] `assign_segments(features: pd.DataFrame, k: int = SEGMENT_K, seed: int = RANDOM_SEED) -> pd.Series` — `segment_id`(1..k) 반환, features 인덱스 보존. 순수 함수(입력 불변·파일 미기록·전역 상태 없음, 1-2/1-3 규약 계승).
  - [ ] **클러스터링 입력**: RFM **원척도 프록시**(`recency_proxy`·`frequency_proxy`·`monetary_proxy`)를 `StandardScaler`로 표준화해 사용(monetary가 수천 단위라 스케일링 없으면 거리 지배). 스케일링은 세그멘테이션 **내부**에서만 — 이건 가치 축 정규화(AD-11 금지)가 아니라 클러스터링 전처리다. 선택(원척도 vs R/F/M 점수)과 근거를 리포트에 기록. **점수(1..5)는 R이 4레벨로 거칠어** 원척도 표준화를 권고.
  - [ ] **결정론(AD-7)**: `KMeans(n_clusters=k, random_state=seed, n_init=<고정값, 예: 10>)`. `n_init`·`random_state` 둘 다 명시. `StandardScaler`는 결정론적.
  - [ ] **🚨 안정 ID (AC2 핵심)**: 원시 KMeans 라벨을 그대로 쓰지 말 것. 각 클러스터의 **`customer_value` 중앙값 내림차순**으로 재정렬해 `segment_id` 1..k(1=최고가치) 부여. **`customer_value`는 `monetary_proxy` 컬럼을 소비**한다 — 이 컬럼은 1-3이 `customer_value(df)` 출력을 그대로 저장한 것이라 **소비이지 재계산이 아니다**(AD-11 준수, `Total_Trans_Amt`를 명명하지 않음). 중앙값 동점 시 결정론적 tiebreak을 명시(예: 평균 내림차순 → 원시 라벨 오름차순)하고 리포트·docstring에 고정.
- [ ] **T2. k 선정 분석 + `SEGMENT_K` config 등재** (AC: 1)
  - [ ] elbow(inertia)·실루엣을 k 범위(예: 2..10)에서 산출하는 **세션 분석**(파이프라인 단계 아님 — M2/M3 패턴: 곡선은 리포트, 공식 수치의 자리는 산출 파이프라인·마트). seed 고정.
  - [ ] 선택한 k를 `crm/config.py`에 `SEGMENT_K: int` 상수로 등재, `# source:` 주석에 **1-4 elbow/실루엣에서 선택**임을 명기. **AD-1 판단 주의**: k는 fitted threshold가 아니라 분석가가 곡선을 보고 고른 하이퍼파라미터이며(‖ `RFM_QUANTILES` 선례‖) BankChurners 레인 안에 머문다. 다른 레인에 재사용하지 않는다.
  - [ ] `SEGMENT_K` 추가로 `config_hash`가 바뀐다 → 기존 `bankchurners.parquet.meta.json`이 stale가 되어 **01 재실행 후 02 재실행**이 필요(1-3에서 `RFM_QUANTILES` 추가 때 겪은 것과 동일, AD-13 over-invalidation). Debug Log에 기록.
- [ ] **T3. 02_features stage 확장** (AC: 2, 3) — 세그먼트를 산출물에 추가
  - [ ] `features = compute_rfm_features(df)` 다음에 `segment_id`를 붙여 쓴다(`features.assign(segment_id=assign_segments(features))`). RFM 계산은 1-3 그대로 재사용, 재발명 금지.
  - [ ] **40행 예산 주의**: 현재 `02_features.py`는 정확히 40행이다(`find_pipeline_shape_violations` 강제). import 1줄 + assign 1줄을 넣으면 초과하므로 docstring을 줄이거나, `crm.segment`가 RFM+세그먼트를 함께 반환하는 얇은 조립 함수를 노출하는 방안 중 택일. `main` 외 `def`/lambda 금지 규칙은 그대로.
  - [ ] 출력 스키마 확장: 산출물 컬럼 = `RFM_OUTPUT_COLUMNS + ("segment_id",)`. 상수로 고정(예: `FEATURE_TABLE_COLUMNS`)해 downstream(1-5)이 계약으로 참조.
- [ ] **T4. 1-3 스테이지 출력 테스트 회귀 갱신** (AC: 2) ← **놓치면 회귀**
  - [ ] `tests/segment/test_features.py::test_leakage_columns_absent_from_real_stage_output`는 **stage가 쓴 parquet 컬럼 == `RFM_OUTPUT_COLUMNS`**를 단언한다. 이제 `segment_id`가 추가되므로 이 단언이 깨진다. 새 계약(`FEATURE_TABLE_COLUMNS`)으로 갱신하되 **누수 컬럼 부재 단언은 유지**. (누수 배제는 여전히 필수다.)
- [ ] **T5. 행동 기반 테스트** (AC: 1, 2, 3) — `tests/segment/test_segments.py`
  - [ ] **동어반복 금지**(1-3 교훈): KMeans를 재구현해 비교하지 말 것. 성질로 검증.
  - [ ] **안정 ID 가치 순서**(AC2): `segment_id` 1의 `monetary_proxy` 중앙값 ≥ segment 2 ≥ ... ≥ k. **합성 데이터로 명확한 가치 계층**(잘 분리된 3~4개 덩어리)을 만들어 segment 1이 최고가치 덩어리에 대응함을 단언. 원시 KMeans 라벨 순서와 무관함을 보여라.
  - [ ] **결정론(AC3/NFR4)**: 같은 입력 2회 `assign_segments` → `segment_id` 완전 동일. **행 순서 셔플 불변**도 검증(1-3 2차 리뷰 Med-5 교훈: 같은 순서 반복만으론 부족).
  - [ ] **seed 주입 실증(AC1)**: 다른 seed를 주면 (일반적으로) 다른 군집이 나오되, 같은 seed는 항상 동일 — seed가 실제로 배선됐음을 행동으로 확인.
  - [ ] **tiebreak 결정론**: 중앙값 동점 클러스터가 있는 합성 케이스에서 segment_id 배정이 재실행에 고정됨을 단언.
  - [ ] k 범위 밖(예: k > 표본 수, k < 2) 등 방어 정책을 정하고 테스트.
- [ ] **T6. 세그먼트 리포트** (AC: 1) — `docs/implementation-artifacts/segment-report-1-4.md`
  - [ ] elbow·실루엣 **수치 표**(k별 inertia·silhouette), 선택 k와 **근거**. 통화·단위 기호 금지(NFR3).
  - [ ] `segment_id` → 가치 계층 매핑 표(각 segment의 크기·`monetary_proxy` 중앙값·R/F/M 프로파일 요약). "segment 1 = 최고가치"가 재실행에 고정됨을 명시(AD-7).
  - [ ] 클러스터링 입력 선택(원척도 표준화)과 tiebreak 규칙을 명문화.
- [ ] **T7. 실행·커밋**
  - [ ] 실데이터로 02_features 재실행(01 재실행 선행) → `features_customers.parquet`에 `segment_id` 생김 확인, 세그먼트 크기·가치순 재현.
  - [ ] **AD-7 수용 기준**: 02_features 2회 연속 실행 후 산출 parquet이 **바이트 동일**(또는 segment_id 완전 동일)임을 확인.
  - [ ] `pytest` 전체 green. **현 기준선 133 passed, 회귀 0.** 스토리 단위 커밋. Obsidian 미러 갱신.

## Dev Notes

### 🚨 착수 전 — scikit-learn 설치 (이 스토리가 첫 설치 스토리)

`sklearn` 미설치 상태를 실측 확인했다. README INSTALL POLICY: 모델링 블록은 주석 상태이고
**"처음 필요로 하는 스토리가 설치한다"**. 1-4가 그 스토리다. `requirements.txt:24`
(`# scikit-learn>=1.9,<2.0`) 주석 해제 후 `-r requirements.txt` 재설치. 이는 프로젝트가
예고한 계획된 설치이지 임의 의존성 추가가 아니다. 설치 실제 버전을 기록할 것.

**sklearn 버전 함정**: 1.4+부터 `KMeans(n_init=...)` 기본값이 `"auto"`다. AD-7은 `n_init`
**명시 주입**을 요구하므로 기본값에 의존하면 위반이다. `random_state`·`n_init` 둘 다 `RANDOM_SEED`
계열에서 명시 주입.

### 🚨 AC2 핵심 — 안정 ID와 AD-11 (customer_value 소비, 재계산 금지)

AD-7·AD-11이 함께 걸린다. 원시 KMeans 라벨은 실행마다·seed마다 임의 번호라, "세그먼트 3"이
조용히 다른 집단을 가리키는 바로 그 사고를 막으려면 **`customer_value` 중앙값 내림차순 재정렬**로
`segment_id`를 정규화해야 한다(1=최고가치).

**`customer_value`를 어떻게 소비하나**: `assign_segments`가 받는 features 프레임에는 이미
`monetary_proxy` 컬럼이 있고, **이 컬럼은 1-3이 `customer_value(df)` 출력을 그대로 저장한 것**이다
(1-3 features.py: `monetary = customer_value(df)`). 따라서 `monetary_proxy`로 중앙값을 내는 것은
**1.2 함수 출력의 소비이지 재계산이 아니며**, `Total_Trans_Amt`를 명명하지 않으므로 AD-11 가드
(`find_value_recomputation_violations`)에 걸리지 않는다. **원본 bankchurners를 다시 읽거나
`customer_value`를 다시 호출하지 말 것** — 이미 저장된 출력을 쓰는 게 정확하고 싸다.

동점(median tie) 처리를 반드시 결정론적으로 고정(예: 중앙값 → 평균 → 원시 라벨). 안 그러면
AD-7 "2회 실행 바이트 동일"이 tie에서 깨진다.

### 세그먼트는 02_features 산출물의 일부다 (파이프라인 위치)

pipeline-diagram.md: `02_features` 산출물이 "RFM 프록시·가치 프록시·**세그먼트**", 로직은
`crm/segment`. 즉 **1-4는 새 파이프라인 단계를 만들지 않고** 02_features를 확장해
`features_customers.parquet`에 `segment_id` 컬럼을 추가한다. elbow/실루엣 곡선은 **세션 리포트**다
(파이프라인엔 시각화 단계가 없다 — M2/M3 패턴, 1-2/1-3과 동일).

### 1-3에서 물려받은 것 (재사용·재발명 금지)

- **features 스키마**: `RFM_OUTPUT_COLUMNS = (CLIENTNUM, recency_proxy, frequency_proxy,
  monetary_proxy, R_score, F_score, M_score)`. `assign_segments`는 이 프레임을 입력받는다.
  `monetary_proxy` = 저장된 `customer_value` 출력.
- **순수 함수·인덱스 보존·ASCII 규율·`.venv/Scripts/python.exe -m pytest`**. 코드/콘솔 출력 ASCII만
  (cp949 콘솔에서 한글 print 깨짐 실측). 한글은 .md에만.
- **stage 형태**: `main(input_paths, output_paths)`만, 40행 이하, `main` 외 def/lambda 금지
  (`find_pipeline_shape_violations`). 1-3에서 writer lambda를 `crm.common.atomic`으로 내린 선례
  참고 — 계산·조립은 `crm/`이 소유한다(AD-9).
- **원자적 쓰기·meta**: `write_parquet_with_meta` + `build_meta`. 직접 `to_parquet` 금지.
- **신선도 2단 게이트**: 02_features는 이미 `verify_inputs` + `is_output_stale(expected_stage=...)`
  배선. 스키마가 바뀌어도 게이트 구조는 유지.

### 1-3 리뷰에서 각인된 테스트 규율 (그대로 적용)

- **성질 테스트만으로는 부족**(1-2 H3, 1-3 Med-4): 안정 ID엔 **합성 데이터 하드코딩 oracle**을
  써서 segment 1이 최고가치 덩어리임을 정확히 고정. 원시 라벨 순서와의 무관함을 보여라.
- **결정론은 "행 순서 불변"까지**(1-3 Med-5): 같은 순서 2회만으론 부족. 셔플 후 CLIENTNUM 정렬 비교.
- **"문서가 테스트를 앞서지 않게"**(1-3 2차 리뷰): 리포트에 "결정론 실증"이라 쓰기 전에 실제
  셔플·재실행 테스트가 green인지 확인. AC/Task에 코드가 못 지키는 주장 금지.

### 결정론 상세 (AD-7 수용 기준)

- `KMeans`: `random_state=RANDOM_SEED`, `n_init` 고정. (`n_jobs`는 KMeans 결정론에 영향 없으나
  XGBoost는 1-6에서 `n_jobs=1` 필요 — 이 스토리 밖.)
- `StandardScaler`: 결정론적.
- `groupby`(클러스터별 중앙값)는 `sort=True` 기본. 안정 ID 재정렬의 tiebreak을 전순서로.
- **수용 기준**: 02_features 2회 실행 → 산출 parquet segment_id 완전 동일. 테스트로 고정.

### 이 스토리가 만들지 않는 것 (범위 경계)

- 세그먼트 **프로필·페르소나**(1-5). 1-4는 `segment_id`와 그 가치순 정규화까지.
- 이탈 모델(1-6), SHAP(1-7).
- 마트(4-1). segment_id는 features에 실리고, 공식 마트 컬럼은 4-1 소관.
- 새 파이프라인 단계. 02_features 확장만.

### Project Structure Notes

```
crm/segment/segments.py                    # NEW - K-means + 가치순 안정 ID (순수)
crm/config.py                              # UPDATE - SEGMENT_K 상수(1-4 곡선서 선택)
pipelines/02_features.py                   # UPDATE - segment_id를 산출물에 추가(40행 예산)
requirements.txt                           # UPDATE - scikit-learn 주석 해제
tests/segment/test_segments.py             # NEW - 안정ID·결정론·seed·tiebreak
tests/segment/test_features.py             # UPDATE - stage 출력 컬럼 계약에 segment_id 반영
docs/implementation-artifacts/segment-report-1-4.md   # NEW - elbow/실루엣·k근거·가치순 매핑
```

- 산출물 경로 불변: `data/features_customers.parquet`(정규 경로, pipeline-diagram). 컬럼만 +segment_id.
- `tests/segment/__init__.py` 이미 존재(1-2).

### References

- [Source: docs/planning-artifacts/epics.md#Story 1.4] — AC 원문(AD-7, AD-11, FR2, NFR4)
- [Source: .../ARCHITECTURE-SPINE.md#AD-7] — seed 주입, 안정 ID = customer_value 중앙값 내림차순, 2회 바이트 동일
- [Source: .../ARCHITECTURE-SPINE.md#AD-11] — customer_value 소비·재계산 금지, 스케일링은 소비 단계
- [Source: .../pipeline-diagram.md] — 02_features 산출물에 세그먼트 포함, 로직은 crm/segment
- [Source: README.md] — 모델링 블록 설치 정책(1-4가 scikit-learn 첫 설치)
- [Source: requirements.txt] — `scikit-learn>=1.9,<2.0` 핀
- [Source: docs/implementation-artifacts/1-3-...md] — features 스키마·monetary_proxy=customer_value 출력·2단 게이트·테스트 규율(성질+oracle, 순서불변)
- [Source: docs/implementation-artifacts/1-2-...md] — value.py 순수 규약, AD-11
- [Source: 실측 2026-07-21] — sklearn 미설치·features 스키마·RANDOM_SEED=42

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List

## Change Log

| 날짜 | 변경 |
|---|---|
| 2026-07-21 | 스토리 1-4 create-story: K-means + 가치순 안정 ID + SEGMENT_K + sklearn 첫 설치 + 02_features 확장. Status → ready-for-dev. 기준선 133 passed |
