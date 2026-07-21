---
baseline_commit: 34b10dc
baseline_passed: 133
---

# Story 1.4: K-means 세그먼트와 안정 ID

Status: review

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

- [x] **T0. scikit-learn 설치** (AC: 1) ← **착수 전 필수, 이 스토리가 첫 설치 스토리**
  - [x] `requirements.txt` 24행 `# scikit-learn>=1.9,<2.0` **주석 해제**(README INSTALL POLICY: "처음 필요로 하는 스토리가 설치"). 설치: `.venv/Scripts/python.exe -m pip install -r requirements.txt`.
  - [x] 설치된 실제 버전을 Dev Notes·리포트에 기록. **sklearn 1.4+부터 `KMeans`의 `n_init` 기본값이 `"auto"`** — AD-7이 명시 주입을 요구하므로 `n_init`를 절대 기본값에 맡기지 말 것.
- [x] **T1. K-means 세그멘테이션 순수 모듈 `crm/segment/segments.py`** (AC: 1, 2, 3) ← 로직 소유
  - [x] `assign_segments(features: pd.DataFrame, k: int = SEGMENT_K, seed: int = RANDOM_SEED) -> pd.Series` — `segment_id`(1..k) 반환, features 인덱스 보존. 순수 함수(입력 불변·파일 미기록·전역 상태 없음, 1-2/1-3 규약 계승).
  - [x] **클러스터링 입력**: RFM **원척도 프록시**(`recency_proxy`·`frequency_proxy`·`monetary_proxy`)를 `StandardScaler`로 표준화해 사용(monetary가 수천 단위라 스케일링 없으면 거리 지배). 스케일링은 세그멘테이션 **내부**에서만 — 이건 가치 축 정규화(AD-11 금지)가 아니라 클러스터링 전처리다. 선택(원척도 vs R/F/M 점수)과 근거를 리포트에 기록. **점수(1..5)는 R이 4레벨로 거칠어** 원척도 표준화를 권고.
  - [x] **결정론(AD-7)**: `KMeans(n_clusters=k, random_state=seed, n_init=<고정값, 예: 10>)`. `n_init`·`random_state` 둘 다 명시. `StandardScaler`는 결정론적.
  - [x] **🚨 안정 ID (AC2 핵심)**: 원시 KMeans 라벨을 그대로 쓰지 말 것. 각 클러스터의 **`customer_value` 중앙값 내림차순**으로 재정렬해 `segment_id` 1..k(1=최고가치) 부여. **`customer_value`는 `monetary_proxy` 컬럼을 소비**한다 — 이 컬럼은 1-3이 `customer_value(df)` 출력을 그대로 저장한 것이라 **소비이지 재계산이 아니다**(AD-11 준수, `Total_Trans_Amt`를 명명하지 않음). 중앙값 동점 시 결정론적 tiebreak을 명시(예: 평균 내림차순 → 원시 라벨 오름차순)하고 리포트·docstring에 고정.
- [x] **T2. k 선정 분석 + `SEGMENT_K` config 등재** (AC: 1)
  - [x] elbow(inertia)·실루엣을 k 범위(예: 2..10)에서 산출하는 **세션 분석**(파이프라인 단계 아님 — M2/M3 패턴: 곡선은 리포트, 공식 수치의 자리는 산출 파이프라인·마트). seed 고정.
  - [x] 선택한 k를 `crm/config.py`에 `SEGMENT_K: int` 상수로 등재, `# source:` 주석에 **1-4 elbow/실루엣에서 선택**임을 명기. **AD-1 판단 주의**: k는 fitted threshold가 아니라 분석가가 곡선을 보고 고른 하이퍼파라미터이며(‖ `RFM_QUANTILES` 선례‖) BankChurners 레인 안에 머문다. 다른 레인에 재사용하지 않는다.
  - [x] `SEGMENT_K` 추가로 `config_hash`가 바뀐다 → 기존 `bankchurners.parquet.meta.json`이 stale가 되어 **01 재실행 후 02 재실행**이 필요(1-3에서 `RFM_QUANTILES` 추가 때 겪은 것과 동일, AD-13 over-invalidation). Debug Log에 기록.
- [x] **T3. 02_features stage 확장** (AC: 2, 3) — 세그먼트를 산출물에 추가
  - [x] `features = compute_rfm_features(df)` 다음에 `segment_id`를 붙여 쓴다(`features.assign(segment_id=assign_segments(features))`). RFM 계산은 1-3 그대로 재사용, 재발명 금지.
  - [x] **40행 예산 주의**: 현재 `02_features.py`는 정확히 40행이다(`find_pipeline_shape_violations` 강제). import 1줄 + assign 1줄을 넣으면 초과하므로 docstring을 줄이거나, `crm.segment`가 RFM+세그먼트를 함께 반환하는 얇은 조립 함수를 노출하는 방안 중 택일. `main` 외 `def`/lambda 금지 규칙은 그대로.
  - [x] 출력 스키마 확장: 산출물 컬럼 = `RFM_OUTPUT_COLUMNS + ("segment_id",)`. 상수로 고정(예: `FEATURE_TABLE_COLUMNS`)해 downstream(1-5)이 계약으로 참조.
- [x] **T4. 1-3 스테이지 출력 테스트 회귀 갱신** (AC: 2) ← **놓치면 회귀**
  - [x] `tests/segment/test_features.py::test_leakage_columns_absent_from_real_stage_output`는 **stage가 쓴 parquet 컬럼 == `RFM_OUTPUT_COLUMNS`**를 단언한다. 이제 `segment_id`가 추가되므로 이 단언이 깨진다. 새 계약(`FEATURE_TABLE_COLUMNS`)으로 갱신하되 **누수 컬럼 부재 단언은 유지**. (누수 배제는 여전히 필수다.)
- [x] **T5. 행동 기반 테스트** (AC: 1, 2, 3) — `tests/segment/test_segments.py`
  - [x] **동어반복 금지**(1-3 교훈): KMeans를 재구현해 비교하지 말 것. 성질로 검증.
  - [x] **안정 ID 가치 순서**(AC2): `segment_id` 1의 `monetary_proxy` 중앙값 ≥ segment 2 ≥ ... ≥ k. **합성 데이터로 명확한 가치 계층**(잘 분리된 3~4개 덩어리)을 만들어 segment 1이 최고가치 덩어리에 대응함을 단언. 원시 KMeans 라벨 순서와 무관함을 보여라.
  - [x] **결정론(AC3/NFR4)**: 같은 입력 2회 `assign_segments` → `segment_id` 완전 동일. **행 순서 셔플 불변**도 검증(1-3 2차 리뷰 Med-5 교훈: 같은 순서 반복만으론 부족).
  - [x] **seed 주입 실증(AC1)**: 다른 seed를 주면 (일반적으로) 다른 군집이 나오되, 같은 seed는 항상 동일 — seed가 실제로 배선됐음을 행동으로 확인.
  - [x] **tiebreak 결정론**: 중앙값 동점 클러스터가 있는 합성 케이스에서 segment_id 배정이 재실행에 고정됨을 단언.
  - [x] k 범위 밖(예: k > 표본 수, k < 2) 등 방어 정책을 정하고 테스트.
- [x] **T6. 세그먼트 리포트** (AC: 1) — `docs/implementation-artifacts/segment-report-1-4.md`
  - [x] elbow·실루엣 **수치 표**(k별 inertia·silhouette), 선택 k와 **근거**. 통화·단위 기호 금지(NFR3).
  - [x] `segment_id` → 가치 계층 매핑 표(각 segment의 크기·`monetary_proxy` 중앙값·R/F/M 프로파일 요약). "segment 1 = 최고가치"가 재실행에 고정됨을 명시(AD-7).
  - [x] 클러스터링 입력 선택(원척도 표준화)과 tiebreak 규칙을 명문화.
- [x] **T7. 실행·커밋**
  - [x] 실데이터로 02_features 재실행(01 재실행 선행) → `features_customers.parquet`에 `segment_id` 생김 확인, 세그먼트 크기·가치순 재현.
  - [x] **AD-7 수용 기준**: 02_features 2회 연속 실행 후 산출 parquet이 **바이트 동일**(또는 segment_id 완전 동일)임을 확인.
  - [x] `pytest` 전체 green. **현 기준선 133 passed, 회귀 0.** 스토리 단위 커밋. Obsidian 미러 갱신.

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

claude-opus-4-8 (bmad-dev-story)

### Debug Log References

**기준선**: HEAD `34b10dc`, 133 passed.

**scikit-learn 설치**: 미설치 확인 → `requirements.txt:24` 주석 해제 → 설치. 실제 버전
**scikit-learn 1.9.0**(+ scipy 1.18.0, joblib 1.5.3, threadpoolctl). `n_init=10` 명시 주입
(1.9는 기본값 `"auto"` — AD-7 위반 방지).

**config drift(예상된 것)**: `SEGMENT_K` 추가로 `config_hash` 변경 → 기존 `bankchurners.meta.json`
stale → `verify_inputs` 실패. 1-3 `RFM_QUANTILES` 때와 동일. 01 재실행 후 02 통과(AD-13 설계대로).

**🚨 셔플 불변 초기 실패 → 수정**: 첫 구현은 caller의 행 순서 그대로 KMeans에 넣었다. 실측 결과
**셔플 후 고객별 segment_id가 달라졌다**(KMeans는 k-means++ 초기화가 데이터 순서에 민감).
파이프라인은 고정 순서로 읽어 AD-7 "2회 바이트 동일"은 지키지만, 1-3 Med-5 교훈대로 행 순서
불변을 보장하려면 부족. **클러스터링 전 `CLIENTNUM` 정규 정렬 → fit → 원 인덱스로 복원**으로
수정. 재검증 셔플 불변 True.

**테스트 검출력(변이)**: 원시라벨 사용·가치순 반전 변이는 즉시 KILLED. 그러나 **"정규 정렬 제거"
변이가 잘 분리된 tier fixture에선 생존**(순서 무관하게 수렴) — 1-3 Med-5의 재현. 불변 테스트를
**fuzzy(비분리) fixture**로 교체하니 KILLED. 성질 테스트는 fixture가 현상을 실제로 유발해야
검출력이 생긴다.

**실데이터 실행**(n=10,127, k=4):
```
segment sizes {1:770, 2:3329, 3:2777, 4:3251}
median monetary 14621 / 4350 / 4312 / 1774 (단조 내림차순 확인)
silhouette(k=4)=0.4119 ; 02_features 2회 연속 실행 데이터 동일 True
```

### Completion Notes List

- **AC1 충족**: `KMeans(random_state=RANDOM_SEED, n_init=10)` 명시 주입. elbow/실루엣 표(k=2..10)와
  k=4 선정 근거를 `segment-report-1-4.md`에 기재(elbow는 k=4, 실루엣 최고 k=2는 고/저 2분할이라
  다운스트림 무용 → 채택 안 함). `SEGMENT_K=4`를 config에 등재(분석가 선택 하이퍼파라미터, AD-1 주의 명시).
- **AC2 충족**: 원시 라벨을 `monetary_proxy`(= 저장된 `customer_value` 출력) 중앙값 내림차순으로
  재정렬해 `segment_id` 1..4(1=최고가치). `customer_value` **소비**만 하고 재계산·`Total_Trans_Amt`
  명명 없음 → AD-11 가드 위반 0. 동점 tiebreak은 중앙값→평균→원시라벨 전순서.
- **AC3 충족(NFR4)**: 2회 실행 동일 + **행 순서 셔플 불변**(정규 정렬로 보장) + tiebreak 결정론 테스트.
  02_features 2회 실행 산출 데이터 동일 실증.
- **파이프라인**: 새 단계 없이 02_features 확장. `crm.segment.segments.build_feature_table`이 RFM+세그먼트를
  조립하고 stage는 한 함수만 호출(40행 유지, AD-9). 출력 계약 `FEATURE_TABLE_COLUMNS`(RFM + segment_id).
- **T4 회귀 갱신**: 1-3 stage 출력 테스트를 `FEATURE_TABLE_COLUMNS` 계약으로 갱신, 누수 배제 단언 유지.
- **구조 가드 전종 green**(lane·layering·pipeline-shape·AD-11·stateful-common). 커버리지 리포트 재생성.
- **테스트**: 133 → 144 → **150 passed** (외부 리뷰 6건 반영), 회귀 0.

### File List

- `crm/segment/segments.py` — NEW, K-means + 가치순 안정 ID + build_feature_table(순수)
- `crm/config.py` — UPDATE, `SEGMENT_K=4`(1-4 곡선서 선택)
- `pipelines/02_features.py` — UPDATE, build_feature_table 호출로 segment_id 산출(40행 유지)
- `requirements.txt` — UPDATE, scikit-learn 주석 해제(1-4 첫 설치)
- `tests/segment/test_segments.py` — NEW, 안정ID·결정론·셔플불변(CLIENTNUM)·seed/n_init spy·mean oracle·계약검증·군집수
- `tests/segment/test_features.py` — UPDATE, FEATURE_TABLE_COLUMNS 계약 + stage 2회 실행 결정론
- `docs/implementation-artifacts/segment-report-1-4.md` — NEW, elbow/실루엣·k근거·가치순 매핑
- `docs/implementation-artifacts/structure-guard-coverage.md` — UPDATE, pytest 재생성
- `docs/implementation-artifacts/deferred-work.md` — UPDATE, AD-1 문구 명확화 권고 기록
- `docs/implementation-artifacts/1-4-kmeans-segments-stable-ids.md` — UPDATE, 본 기록
- `docs/implementation-artifacts/sprint-status.yaml` — UPDATE, 상태 전이

## Senior Developer Review (외부 GPT, 2026-07-21)

**판정: Changes Requested** — High 1, Medium 4, Low 1. **6건 전부 실증 재현 후 처리**(반려 0).
AD-11·pipeline-shape·누수 배제는 통과 확인받음.

### 실증 확인 (패치 전)

| # | 심각도 | 주장 | 실증 |
|---|---|---|---|
| 1 | High | CLIENTNUM/index 유일성을 가정 → 같은 고객이 다른 세그먼트, 중복 index reindex 오배정 | ✅ CLIENTNUM=0 두 행이 seg 4·3, 중복 index 오배정 재현 |
| 2 | Med | KMeans가 실제 <k 군집을 만들어도 성공 처리 | ✅ 전부동일 4행 k=4 → segment 1개만, 예외 없음 |
| 3 | Med | `n_init`·`StandardScaler` 제거 변이 생존 | ✅ 둘 다 SURVIVED |
| 4 | Med | mean tiebreak 미검증(median=mean fixture) | ✅ mean 제거 변이 SURVIVED |
| 5 | Med | 파이프라인 2회 실행 동일이 자동 테스트로 미고정 | ✅ 함수 테스트뿐, 실제 stage 2회 실행 테스트 없음 |
| 6 | Low | `test_seed_is_actually_injected`가 취약(전역 최적 수렴 시 오탐 가능) | ✅ 결과기반 부등식은 안정 oracle 아님 |

### 적용한 패치

- **[High]** `assign_segments`에 **customer-table 계약 검증**: CLIENTNUM null·중복·index... 복원을
  **index reindex → CLIENTNUM 기반 map**으로 교체(중복 index에도 고객별 정확). 셔플 테스트를
  `reset_index` 후 CLIENTNUM 비교로 고쳐 "index 정렬" 변이를 사살.
- **[Med-2]** fit 후 **실제 생성 군집 수 != k면 예외**(distinct feature vector 부족 fail-fast).
- **[Med-3a]** `n_init`·`random_state`를 **생성자 spy**로 검증(결과기반 대신 인자 검사) → `n_init` 제거·
  `seed+1` 변이 KILLED. **[Med-3b]** monetary ×1e6 **스케일 불변 테스트**(fuzzy) → StandardScaler 제거 KILLED.
- **[Med-4]** median 동일·mean 다른 fixture로 **exact oracle**(B가 A보다 앞선 segment_id) → mean tiebreak 제거 KILLED.
- **[Med-5]** 실제 `02_features::main()`을 **두 독립 output에 2회 실행**해 데이터 동일 단언.
- **[Low]** 취약한 부등식 테스트를 spy 기반으로 대체(안정 oracle).
- **[AD-1 조건부]** `SEGMENT_K`의 fitted-값/​하이퍼파라미터 구분을 deferred-work에 기록(스파인 개정 사안).

### 패치 후 재검증

- 생존 변이 6종(index 정렬·StandardScaler·n_init·mean tiebreak·seed+1·cluster-count) **전부 KILLED**.
- High 재현(중복 CLIENTNUM·null·중복 index) 전부 예외 또는 고객별 정확. 실데이터 segment 분포 불변.
- 구조 가드 전종 0 위반. **144 → 150 passed**, 회귀 0.

## Change Log

| 날짜 | 변경 |
|---|---|
| 2026-07-21 | 스토리 1-4 create-story: K-means + 가치순 안정 ID + SEGMENT_K + sklearn 첫 설치 + 02_features 확장. Status → ready-for-dev. 기준선 133 passed |
| 2026-07-21 | 스토리 1-4 구현: segments.py(K-means+가치순 안정ID)·SEGMENT_K=4·02_features 확장·scikit-learn 1.9.0 설치. 셔플 불변 초기 실패→정규 정렬로 수정, fuzzy fixture로 순서민감 변이 사살. 133 → 144 passed, 회귀 0. Status → review |
| 2026-07-21 | 외부 GPT 리뷰 6건 처리(High 1·Med 4·Low 1): CLIENTNUM 계약검증+CLIENTNUM 기반 복원·실군집수 검증·n_init/seed spy·스케일 불변·mean tiebreak oracle·stage 2회 실행 테스트. 144 → 150 passed, 회귀 0 |
