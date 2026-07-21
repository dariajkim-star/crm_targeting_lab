---
baseline_commit: 047d2c1
baseline_passed: 150
---

# Story 1.5: 세그먼트 프로필과 페르소나

Status: ready-for-dev

## Story

As a 마케팅 의사결정자,
I want 각 세그먼트가 누구인지 프로필과 페르소나로 읽히기를,
so that 이후 리텐션 액션을 사람 단위로 상상할 수 있다.

## Acceptance Criteria

**AC1 — 프로필 요약 + 페르소나**
**Given** 세그먼트가 확정됐을 때
**When** 프로필 리포트를 생성하면
**Then** 세그먼트별 인구통계·행동 지표 요약표와 고객 수·비중이 산출된다
**And** 페르소나 4~6개가 정의된다(FR3)

**AC2 — 재현성 + 무단위**
**Given** 리포트에 수치가 인용될 때
**When** 출처를 확인하면
**Then** 모든 수치가 커밋된 코드 경로로 재현 가능하고 출처가 명시된다(conventions 4항)
**And** 금액성 지표는 BankChurners **무단위**로 표기되고 임의 통화 기호를 붙이지 않는다(NFR3)

**AC3 — 정직성(k와 페르소나 수)**
**Given** 세그먼트 수가 k에 따라 달라질 때
**When** 페르소나가 4개 미만 또는 6개 초과로 나오면
**Then** 페르소나를 억지로 맞추지 않고 실제 k와 그 사유를 리포트에 기록한다(정직성)

## Tasks / Subtasks

- [ ] **T1. 세그먼트 프로필 순수 모듈 `crm/segment/profile.py`** (AC: 1, 2) ← 로직 소유(재현성의 코드 경로)
  - [ ] `segment_profiles(features: pd.DataFrame, raw: pd.DataFrame) -> pd.DataFrame` — segment_id별 요약(순수 함수, 입력 불변·파일 미기록). segment_id를 인덱스로, 컬럼은 `n`·`share`(비중)·수치 지표 중앙값(나이·재직개월·신용한도·이용률·`monetary_proxy`·`frequency_proxy`·`recency_proxy` 등).
  - [ ] `segment_category_shares(features, raw, column) -> pd.DataFrame` — segment_id × 범주 비율표(성별·학력·소득·카드등급·혼인). 각 행 합=1.
  - [ ] **인구통계는 raw bankchurners에 있고 features에는 없다** → `CLIENTNUM`으로 조인. 조인은 **features 기준 left**(세그먼트 있는 고객 집합), 조인 키 유일성은 1-4가 이미 보장(재확인 방어 권장).
  - [ ] **🚨 AD-11**: profile.py는 `crm/` 아래이므로 **`Total_Trans_Amt`를 어떤 형태로도 명명 금지**. 가치 지표는 features의 `monetary_proxy`(= 저장된 `customer_value` 출력)를 소비. raw에서 뽑는 인구통계는 **화이트리스트**로 명시(`Total_Trans_Amt`·누수 컬럼 절대 제외). `find_value_recomputation_violations` 가드가 이 파일을 스캔한다.
  - [ ] **CAP-5 준수**: `Total_Revolving_Bal`·`Credit_Limit`은 **프로파일링 참고 지표**로만 사용(가치 축 산입 금지, 2026-07-20 개정). 프로필 표에 넣는 건 허용, 가치로 합산·재가중은 금지.
- [ ] **T2. 프로필 리포트 + 페르소나** (AC: 1, 2, 3) — `docs/implementation-artifacts/segment-profile-report-1-5.md`
  - [ ] segment_id별(1..4) **요약표**: 고객 수·비중, 수치 지표 중앙값, 주요 범주 분포(성별·소득·카드등급 등). 수치는 T1 함수로 산출(재현 가능, AC2).
  - [ ] **페르소나 4개**(현재 k=4). 각 페르소나: 한 줄 정체성 + 가치/행동 특징 + 대표 인구통계 + (다음 스토리를 위한) 리텐션 가설. **가치순(segment 1=최고가치)** 서술.
  - [ ] **AC3 정직성**: 현재 `SEGMENT_K=4`라 페르소나 정확히 4개(4~6 범위 내). 이 사실과 "k가 바뀌면 페르소나 수도 따라간다"를 리포트에 명시. 억지 분할·병합 금지.
  - [ ] **NFR3 무단위**: `monetary_proxy` 등 **우리가 산출한 금액성 지표에 통화 기호 금지**. ⚠️ 단, `Income_Category` 라벨은 데이터셋 원본 범주 문자열("Less than $40K" 등)이라 **원문 그대로** 인용(우리가 붙인 기호가 아님) — 이 구분을 리포트에 한 줄 명기.
  - [ ] **정직성(데이터 품질)**: `Education_Level` Unknown ~15%·`Income_Category` Unknown ~11%·`Marital_Status` Unknown ~7%. **Unknown을 버리거나 대치하지 말고 하나의 범주로 표기**. `Card_Category`는 Blue ~93%, Platinum 20명 — 소셀 주의(비율만으로 과대해석 금지)를 각주로.
  - [ ] **출처 명시(AC2/conventions 4)**: 각 수치의 출처(함수·입력 파일)를 리포트에 기재. 재현 커맨드 한 줄 포함.
- [ ] **T3. 행동 기반 테스트** (AC: 1, 2) — `tests/segment/test_profile.py`
  - [ ] **동어반복 금지**: 구현 집계를 재구현해 비교하지 말 것. 성질로 검증.
  - [ ] `n` 합 = 전체 고객 수, `share` 합 = 1(부동소수 허용오차). `segment_category_shares` 각 세그먼트 행 합 = 1.
  - [ ] **1-4 정합성**: segment 1의 `monetary_proxy` 중앙값이 가장 높고 segment 4로 단조 감소(1-4 가치순 안정 ID와 일치). 이게 프로필과 세그먼트 정의의 연결을 실증.
  - [ ] **조인 정확성**: 특정 CLIENTNUM의 인구통계가 raw의 그 고객 값과 일치(합성 데이터로).
  - [ ] **Unknown 보존**: `Unknown` 범주가 결과에서 사라지지 않음(드롭·대치 안 함).
  - [ ] **순수성**: 입력 프레임 불변, 파일 미기록.
  - [ ] **AD-11**: 프로필 산출물에 `Total_Trans_Amt` 컬럼이 없음(가치는 monetary_proxy로만).
  - [ ] 방어: features에 있는 CLIENTNUM이 raw에 없을 때 정책(명확한 실패 또는 문서화된 처리).
- [ ] **T4. 실행·커밋**
  - [ ] 실데이터(features_customers + bankchurners, n=10,127)로 프로필 산출 → 리포트 수치 재현. 무단위·Unknown 정직 표기 확인.
  - [ ] `pytest` 전체 green. **현 기준선 150 passed, 회귀 0.** 스토리 단위 커밋. Obsidian 미러 갱신.

## Dev Notes

### 이 스토리의 성격 — 세션 리포트 + 재현 가능한 코드 경로

파이프라인은 5단계(01..05)뿐이고 프로필/​페르소나 **시각화·서술 단계는 없다**(M2/M3 패턴, 1-2/1-3/1-4와
동일). 따라서 1-5는 **새 파이프라인 단계를 만들지 않는다**. 대신:
- **재현성의 코드 경로**(AC2): 프로필 수치를 산출하는 **순수 함수를 `crm/segment/profile.py`에 커밋**하고
  테스트한다. "리포트 수치가 커밋된 코드로 재현 가능"의 실체가 이 함수다.
- **리포트**: `segment-profile-report-1-5.md`(세션 산출물). 함수 출력을 표·페르소나로 옮긴다.
- 공식 수치의 최종 자리는 **4-1 마트 + 4-3 Tableau 탭**이다(리포트는 사람이 읽는 요약).

### 🚨 데이터 위치 — 인구통계는 features가 아니라 raw에 있다

`features_customers.parquet`에는 **`CLIENTNUM` + RFM + `segment_id`만** 있다(1-3/1-4). 나이·성별·학력·
소득·카드등급 같은 **인구통계는 raw `bankchurners.parquet`에만** 있다. 그래서 프로필은 두 파일을
**`CLIENTNUM`으로 조인**해야 한다. 두 파일 모두 BankChurners 레인이라 AD-1 위반이 아니다(레인 격리는
BankChurners↔Online Retail 사이의 문제). 조인 키는 1-4에서 유일성을 강제했으므로 안전하나, profile
함수도 방어적으로 재확인하는 편이 좋다(1-4 High 교훈: 유일성 가정은 검증과 함께).

### 🚨 AD-11 — 프로필에서도 Total_Trans_Amt 명명 금지

profile.py는 `crm/` 아래라 가드(`find_value_recomputation_violations`) 스캔 대상이다. 가치 지표가
필요하면 **features의 `monetary_proxy`(= 저장된 `customer_value` 출력)를 소비**한다. raw에서 인구통계를
뽑을 때 컬럼을 **화이트리스트로 명시**하고 거기에 `Total_Trans_Amt`나 누수 컬럼(`Naive_Bayes_Classifier_*`)을
**절대 넣지 말 것**. 실수로 `raw["Total_Trans_Amt"]`를 쓰면 가드가 즉시 잡는다(1-3에서 검증된 동작).

**CAP-5(2026-07-20 개정)**: `Total_Revolving_Bal`·`Credit_Limit`은 **프로파일링 참고 지표**다. 프로필
표에 분포로 넣는 건 정당하나 **가치로 합산·재가중은 금지**(가치는 `monetary_proxy` 단일).

### NFR3 무단위 — 그리고 예외 하나 (Income_Category)

`monetary_proxy` 등 **우리가 산출한 금액성 지표에는 통화 기호를 붙이지 않는다**(P1 3-4 통화 오기 사고).
**단 예외**: `Income_Category`의 라벨 자체가 데이터셋 원본 문자열이다 — `"Less than $40K"`, `"$40K - $60K"`,
`"$120K +"` 등. 이건 **우리가 붙인 기호가 아니라 데이터의 범주값**이므로 원문 그대로 인용한다. 리포트에
이 구분을 한 줄 명기해 "통화 기호를 붙였다"는 오해를 차단할 것.

### 정직성 (AC3 + 데이터 품질)

- **페르소나 수 = k**: 현재 `SEGMENT_K=4` → 페르소나 정확히 4개(4~6 범위 내, AC3 조건 자동 충족).
  억지로 나누거나 합치지 말 것. "k가 바뀌면 페르소나 수도 따라간다"를 리포트에 명시.
- **Unknown을 숨기지 말 것**: 실측 Unknown 비중 — Education ~15%, Income ~11%, Marital ~7%. 버리거나
  대치하면 프로필이 실제보다 깨끗해 보인다. **Unknown을 하나의 범주로** 표기하고 비중을 드러낸다.
- **소셀 주의**: `Card_Category`는 Blue ~93%(9,436) / Silver 555 / Gold 116 / **Platinum 20명**. 세그먼트별로
  쪼개면 Platinum 셀이 한 자릿수가 된다 — 비율만으로 과대 서술 금지, 각주로 표본 크기 경고.

### 실데이터 사전 조사 (dev가 재확인)

| 항목 | 값 |
|---|---|
| 조인 | features(10,127) ⋈ raw(10,127) on CLIENTNUM = 10,127 (완전 일치) |
| segment_id | 1..4 (1-4), 가치 중앙값 14621/4350/4312/1774 |
| 인구통계 후보(raw) | Customer_Age, Gender, Dependent_count, Education_Level, Marital_Status, Income_Category, Card_Category, Months_on_book, Total_Relationship_Count, Credit_Limit*, Total_Revolving_Bal*, Avg_Utilization_Ratio (*CAP-5 참고지표) |
| Unknown 비중 | Education 0.15 / Income 0.11 / Marital 0.074 |
| Card 분포 | Blue 9436 / Silver 555 / Gold 116 / Platinum 20 |

### 1-2~1-4에서 물려받은 것 (재사용·재발명 금지)

- **순수 함수·인덱스 보존·ASCII 규율**(코드·콘솔 ASCII만, 한글은 .md). `.venv/Scripts/python.exe -m pytest`.
- **가치는 소비만**(AD-11): `monetary_proxy` 사용, `customer_value` 재계산·`Total_Trans_Amt` 명명 금지.
- **CLIENTNUM 유일성**(1-4 High 교훈): 조인 전 유일성 방어. 인덱스가 아니라 키로 조인·정렬.
- **테스트 규율**(1-3/1-4 리뷰): 성질 테스트 + 재현 가능 수치. 집계를 재구현해 비교하는 동어반복 금지.
  "문서가 테스트를 앞서지 않게" — 리포트에 "재현 가능"이라 쓰기 전에 그 수치를 내는 함수가 테스트로
  green인지 확인.

### 이 스토리가 만들지 않는 것 (범위 경계)

- 이탈 모델·리스크(1-6). 페르소나의 "리텐션 가설"은 서술일 뿐 모델 아님.
- 액션 매핑(1-7). 1-5는 "누구인가"까지, "무엇을 할까"는 1-7.
- 마트(4-1)·대시보드(4-3). 프로필의 공식 자리는 거기.
- 새 파이프라인 단계·config 상수. segment_id·features는 그대로 소비.

### Project Structure Notes

```
crm/segment/profile.py                     # NEW - 세그먼트 프로필/카테고리 집계(순수, AD-11 준수)
tests/segment/test_profile.py              # NEW - 성질·조인·Unknown보존·AD-11·1-4정합성
docs/implementation-artifacts/segment-profile-report-1-5.md   # NEW - 요약표 + 페르소나 4개
```

- 입력: `data/features_customers.parquet`(segment_id) + `data/bankchurners.parquet`(인구통계). 신규 산출
  파이프라인 파일 없음.
- `tests/segment/__init__.py` 이미 존재.

### References

- [Source: docs/planning-artifacts/epics.md#Story 1.5] — AC 원문(FR3, NFR3, conventions 4, 정직성)
- [Source: .../ARCHITECTURE-SPINE.md#AD-11] — 가치 소비·재계산 금지(프로필도 monetary_proxy 소비)
- [Source: docs/specs/spec-crm-targeting-lab/SPEC.md#CAP-5] — Total_Revolving_Bal·Credit_Limit는 참고지표
- [Source: docs/implementation-artifacts/1-4-...md] — segment_id·가치순·CLIENTNUM 유일성 교훈
- [Source: docs/implementation-artifacts/1-3-...md] — features 스키마·monetary_proxy=customer_value 출력·누수 컬럼
- [Source: 실측 2026-07-21] — 조인 완전일치·Unknown 비중·Card 소셀·Income 라벨의 $ 표기

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List

## Change Log

| 날짜 | 변경 |
|---|---|
| 2026-07-21 | 스토리 1-5 create-story: 세그먼트 프로필/카테고리 집계 순수 함수 + 페르소나 4개 리포트. AD-11 monetary_proxy 소비·Unknown 정직 표기·Income $ 라벨 구분. Status → ready-for-dev. 기준선 150 passed |