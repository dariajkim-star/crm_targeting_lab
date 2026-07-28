---
baseline_commit: 29449a9630d0f8096ddf08ee9833a8a0138bb0a5
---

# Story 4.1b: 계약 좁히기·오용 방지 — 아티팩트 주변 경화

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a 마트·캠페인 산출물의 소비자(코드 소비자와 BI 소비자 모두),
I want 함정4류 오정렬이 **호출부에서 표현 불가능**해지고, 마트 오용(+19% 컬럼 오선택)이 계약·문서 층에서 방지되기를,
so that 4-1a가 만든 올바른 아티팩트가 **주변 코드와 소비자에 의해 다시 오염될 수 없는** 상태로 잠긴다.

## 배경 — 이 스토리가 4-1 분할의 뒤쪽이다

4-1a(done, 커밋 `8832c62`·`3a918d8`·`9eb3556`)가 **디스크에 올바른 마트**를 올렸다 — CLIENTNUM 라벨 조인, 정규 스키마, 결정론, AD-5 게이트. 이 스토리(**4-1b**)는 그 **주변을 경화**한다: 3-3 파티 인계 3건(구item1·4·5) + 1-2 인계 절반(호출부 재가중) + 3-0 D3 인계(오용 표기) + 3-2 F7 재발 건(세션 리포트 경로). 세로선은 1-6a/b 선례 그대로 — 먼저 정확한 아티팩트(4-1a), 그다음 계약을 좁혀 오용을 막는다(4-1b).

**본공연 이식 메모**: 워싱 스크리너는 조인이 훨씬 많아 "오정렬이 표현 불가능한 계약"의 가치가 crm보다 크다(3-3 파티 명시). 이 스토리가 그 계약의 최종 리허설이다. [Source: deferred-work.md "3-3 코드리뷰 보류 5건 파티 결정"]

## Acceptance Criteria

**AC1 — `target_priority` 3축 CLIENTNUM 인덱스 요구 (구item1, 함정4 계약 좁히기)**
Given `target_priority(expected_saving, value, clientnum)`이 호출될 때
When 세 축 중 하나라도 인덱스 이름이 `CLIENTNUM`이 아니거나(`index.name != "CLIENTNUM"`) 정수 dtype 인덱스가 아니면
Then **즉시 `ValueError`** — 메시지는 "위치 결합이 아니라 CLIENTNUM 조인으로 축을 만들라"를 지목한다. `RangeIndex` 축이 이 함수에 도달하는 것 자체가 표현 불가능해진다.
And 기존 부분 가드(인덱스가 CLIENTNUM일 **때만** 컬럼과 대조)는 전제조건이 강제되므로 **항상** 발동하는 전면 가드로 승격된다. `select_within_budget`은 `target_priority`를 경유하므로 자동 승계.
And **`expected_saving`(3-2)의 시그니처·출력 계약은 바꾸지 않는다** — RangeIndex 출력은 여전히 유효하며, 좁히는 것은 **랭킹 계층의 입구**뿐이다(3-2 done 계약 보존, 3-3 파티 결정 그대로).
> **실측 근거**: 함정4는 절감액 축을 오염시키는데 그 축은 정체성을 안 들고 다녀서, (A) RangeIndex 위치 결합과 (B) 4-1 마트 형태 **둘 다** 무예외로 1,994,740.8을 낸다 — 부분 가드는 4-1에서도 실효가 없었다(3-3 코드리뷰 Auditor 반증). 입구에서 인덱스 자체를 요구하는 것이 유일한 전면 방어다. [Source: deferred-work.md "CLIENTNUM 라벨 대조 가드가 함정 4를 못 잡는다"]

**AC2 — `random_baseline` 모집단 정체성 (구item4)**
Given `random_baseline(expected_saving, n_contacts=...)`이 호출될 때
When `expected_saving` 축이 AC1과 같은 CLIENTNUM 인덱스 요건을 충족하지 않으면
Then 즉시 실패한다. 기준선이 **어느 모집단**에서 뽑혔는지가 축의 정체성으로 보장된다(통합안 `multiple_over_random`이 배수 경로는 닫았으나 이 함수 자체는 맨 Series를 받던 구멍).

**AC3 — 빈 캠페인 메시지가 원인을 말한다 (구item5)**
Given `selected_count == 0`인 `BudgetSelection`과 `n_contacts == 0`인 `RandomBaseline`으로 `multiple_over_random`을 호출할 때
When 현재는 `baseline.mean_total > 0` 검사가 먼저 걸려 **"기준선이 양수여야 한다"**는 오진 메시지가 나오면
Then 검사 순서를 바꿔 **"접촉 인원이 0"**(빈 캠페인 — `binding_constraint`를 인용해 zero_budget인지 budget_below_one_contact인지 no_positive_candidates인지)을 먼저 명명한다. 배수는 정의 불가가 맞고, **이유**가 맞아야 한다(3-3 파티 만장일치 nit).

**AC4 — `campaign_selected` 정의 고정, 컬럼은 비탑재 (AD-12 / 스토리 결정 D1)**
Given AD-12가 `campaign_selected` 정의의 스키마 문서 고정을 요구할 때(3-3 코드리뷰 인계)
When `marts/mart_customers.schema.md`를 갱신하면
Then **정의를 고정한다**: *"`campaign_selected` = `target_priority <= 예산이 사는 접촉 수` AND `expected_saving > 0` — 산출 함수는 `select_within_budget`(단일 소유), 예산·비용은 호출 인자."*
And **마트에 컬럼은 싣지 않으며 그 사유를 같은 절에 명시한다**(D1): 공식 단일 예산이 존재하지 않고(3-3 결론 — "배수는 예산의 함수, 헤드라인은 곡선이지 한 점이 아니다"), 예산은 정책가정이 아니라 **시나리오 입력**이다. 임의의 예산 하나를 config에 박아 컬럼을 만들면 시나리오 입력을 사실로 세탁하는 것. 선택의 실체화는 예산이 주어지는 소비 지점(4-3 시나리오 뷰)의 몫.
And pytest가 스키마 문서에 `campaign_selected` 정의 절이 존재함을 검증한다(4-1a의 문서-파싱 테스트 패턴 확장).

**AC5 — 마트 오용 방지 표기 (3-0 D3 인계, +19% 방어)**
Given `churn_score`·`churn_prob_calibrated`가 BI 드롭다운에 나란히 뜨고 둘 다 [0,1]일 때
When `mart_customers.schema.md`의 컬럼 표에 **`용도/금지` 칸**을 추가하면
Then `churn_score` 행에 *"순위 전용 — 금액 산식 사용 금지(오선택 시 총합 +19.0% 부풀림, 실측 1,730,042)"*, `churn_prob_calibrated` 행에 *"금액 전용 — 분면 컷 재계산에 사용 금지(3-1은 원점수 소유)"*가 명기된다.
And pytest가 두 문구의 존재를 검증한다(문서=계약, 4-1a 패턴).
And **층 분리 준수**: 마트는 감사 가능성(두 컬럼 모두 유지), 화면 노출 제어(뷰에서 `churn_score` 제외 여부)는 **4-3 소관**으로 남긴다 — Sally 액션과 정합. CSV 자체에 헤더 주석은 넣지 않는다(결정론 직렬화 6종 계약 훼손).

**AC6 — `customer_value` 호출부 재가중 보호 (1-2 인계 절반, sentinel)**
Given `crm/marts/customers.py`가 `customer_value`를 실제 호출하는 **첫 커밋 코드**일 때
When `crm.marts.customers.customer_value`를 sentinel Series(서로 다른 3점 이상)로 monkeypatch하고 마트를 조립하면
Then 마트의 `customer_value` 컬럼이 sentinel과 **정확히 동일**하다(`*0.02`·`log1p` 등 호출부 재가중 전부 KILL — 값 동일성 방식, 3-2 `expected_saving` 내부 sentinel 테스트와 같은 계열). 이것으로 1-2 인계의 남은 절반("호출부 재가중 무보호")이 닫힌다.
> 주의: 3-3의 동점-순서 방식이 아니라 3-2의 값-동일성 방식이다 — 마트 컬럼은 값 자체가 계약이므로 단조 변환도 잡힌다. [Source: deferred-work.md "customer_value() 출력의 재가중 금지"]

**AC7 — 세션 리포트 커밋 경로 규약 (3-2 F7·3-3 재발 종결 / 스토리 결정 D2)**
Given 세션 리포트 집계 경로가 두 번 연속 미커밋(`scratch/`)으로 지적됐을 때
When 경로 규약을 확정하면
Then **선택지 ③+①의 혼합을 채택한다**(D2): (a) **공식 수치의 집은 마트와 골든 테스트다** — 분면 분포·컷·총합은 4-1a가 이미 커밋된 테스트로 고정했고, 마트에서 검산 가능한 수치는 리포트가 마트를 인용한다. (b) 마트에서 검산 **불가능**한 세션 수치(예: 배수 곡선)는 리포트 본문에 호출 순서 명시 + **"세션 산출(재현 각주 필수)"** 라벨을 규약으로 못박는다. (c) 이 규약을 `docs/specs/spec-crm-targeting-lab/conventions.md`에 명문화한다.
And 06 stage 신설·`reports/` 디렉터리는 **도입하지 않는다** — AD-2가 05를 `marts/` 유일 writer로 고정했고, 새 집계 스테이지는 에픽4에 실수요가 생길 때(4-3) 재검토.

## Tasks / Subtasks

- [x] **T1 — 랭킹 계층 계약 좁히기** (AC1, AC2)
  - [x] `_require_clientnum_index(series, axis_name)` 신설: `index.name == "CLIENTNUM"` + 정수 dtype. `_validate_alignment` 앞에서 세 축 검사(정체성 → 정합 → 내용). **빈 축은 dtype 검사를 건너뛰고**(빈 인덱스는 object dtype — 오진 방지) 기존 "empty" 가드가 명명하도록 통과시킴.
  - [x] `random_baseline`에 동일 요건 적용 (AC2).
  - [x] 부분 가드 조건문(`index.name == _CLIENTNUM_AXIS and`) 제거 — 무조건 대조로 승격, 주석으로 4-1b 승격 명시.
  - [x] docstring 갱신: `_validate_alignment`("partial by design" 제거)·`target_priority`(인덱스 요건+Raises)·`random_baseline`(모집단 정체성 주석). simulate.py는 무변경(문구 정합 확인만).
  - [x] 호출부: 전 픽스처 `_population`(CLIENTNUM 인덱스)로 이미 순응 — 수정 0. 신규 거부 테스트 4건: RangeIndex 거부·CLIENTNUM 명명 float 인덱스 거부·random_baseline 거부·select_within_budget 승계.
- [x] **T2 — 빈 캠페인 메시지** (AC3)
  - [x] `multiple_over_random`: `selected_count == 0` 검사를 n_contacts 대조 뒤·`mean_total` 검사 앞에 삽입, `binding_constraint` 인용.
  - [x] 기존 빈-빈 테스트를 원인 명명 테스트로 재편 + zero_budget/budget_below_one_contact 파라미터화 + **진짜 non-positive 분모 케이스 분리 신설**(선택 1명 + 음수 우세 모집단 — 캠페인이 비어 있지 않을 때만 "positive baseline"이 정당).
- [x] **T3 — 스키마 문서 경화** (AC4, AC5)
  - [x] `용도/금지` 칸 추가(7번째 칸 — `_schema_columns`의 cells[0]/[1] 불변 확인) + 칸 도입 배경 문단(BI 드롭다운 무가드, 층 분리). `campaign_selected` 절 신설(정의 + 비탑재 사유 D1 + "순위≠추천" 연결).
  - [x] 테스트: 금지 문구 2건(+19.0% 포함)·campaign_selected 절(select_within_budget·비탑재·양수 컷) 존재 단언, `_schema_row` 헬퍼 신설.
- [x] **T4 — 호출부 sentinel 테스트** (AC6)
  - [x] sentinel을 **CLIENTNUM 키 매핑**으로 주입(픽스처가 소스를 셔플하므로 위치 기반이면 페어링이 깨짐) → 마트 컬럼 == sentinel 정확 일치(`assert_series_equal`). 값 동일성 방식이라 단조 재가중(log1p)도 KILL.
  - [x] deferred-work.md 1-2 인계 항목 해소 주석.
- [x] **T5 — 세션 리포트 규약 명문화** (AC7)
  - [x] `conventions.md` 10번 신설: 공식 수치=마트+골든 테스트, 세션 수치=호출 순서+세션 산출 라벨(재현 각주: seed·draws·호출 체인), 06 stage·reports/ 비도입(AD-2). 4번 규율의 구체화로 위치.
  - [x] deferred-work.md 3-2 F7 항목 + 구item1·4·5 항목에 종결 주석.
- [x] **T6 — 회귀·문서 DoD** (전 AC)
  - [x] **370 passed**(기준선 360 → +10: 거부 4·메시지 3·스키마 2·sentinel 1), 1 skipped(xgboost), 회귀 0. `marts/mart_customers.csv` **바이트 불변**(git 무변경 — 순수 경화 DoD).
  - [x] 문서 체크리스트 DoD(에픽1 A3 첫 적용): schema.md ✓ conventions.md ✓ deferred-work.md ✓(1-2 인계·F7·구item1/4/5 5곳 종결) 스토리 파일 ✓. README 수치 무관(마트 값 불변) ✓.

## Dev Notes

### 계약 좁히기의 정확한 경계 (틀리기 쉬운 지점)

- **좁히는 것**: `target_priority`·`select_within_budget`(경유)·`random_baseline`의 **입력 인덱스 요건**.
- **좁히지 않는 것**: `expected_saving`(3-2 done — RangeIndex 출력 유효), `assign_quadrant`(3-1 done), `customer_value`(1-2 done). 이들의 시그니처·출력을 건드리면 done 스토리 계약 위반.
- `multiple_over_random`은 이미 결과 객체 2개를 받는 통합안(3-3) — AC3의 메시지 순서만 손댄다.
- 함수 시그니처는 그대로: `target_priority(expected_saving, value, clientnum)` — 바뀌는 건 **받아들이는 축의 형태**뿐.

### 현재 코드 실측 (전부 이 세션에서 확인)

- `priority.py:293` 부분 가드: `if expected_saving.index.name == _CLIENTNUM_AXIS and not np.array_equal(...)` — AC1 후 조건부 제거 대상. `_CLIENTNUM_AXIS = "CLIENTNUM"` 상수 재사용.
- `priority.py` `_validate_alignment`은 이미 인덱스 동일성·dtype·유일성 검사 보유 — 신규 헬퍼는 **이름·정수 dtype**만 추가하면 됨(중복 검사 금지).
- `multiple_over_random`(priority.py:621~): 검사 순서 = isinstance 2건 → `n_contacts != selected_count` → `mean_total > 0`. AC3는 `selected_count == 0`을 **n_contacts 대조 뒤, mean_total 앞**에 넣는 게 자연스러움(빈-빈 케이스는 n_contacts 대조를 통과함: 0==0).
- `crm/marts/customers.py::build_customer_mart`: `priority = target_priority(saving, value, clientnum)` — 세 축 모두 `bc.index`(CLIENTNUM, int64) 공유. **이미 순응, 무변경**.
- `tests/campaign/test_priority.py::_population`: `pd.Index(clientnums, name="CLIENTNUM")` — 이미 순응. 파일 내 다른 즉석 픽스처는 dev가 grep으로 확인.
- 4-1a 리뷰 P1로 조인 키는 이미 NaN 거부·정수 dtype 강제 — 마트 쪽 인덱스 위생은 완비. 이 스토리는 **랭킹 계층 입구**를 같은 수준으로 올리는 것.

### 스키마 문서 테스트 주의 (4-1a에서 온 함정)

`tests/marts/test_customers.py::_schema_columns`가 표를 `|` split으로 파싱하며 `cells[1]`에서 dtype을 뽑는다 — **칸을 추가하면 위치가 밀릴 수 있으니** 칸 순서는 기존 6칸 뒤에 `용도/금지`를 붙이는 게 안전(cells[0]·[1] 불변). 골든 단언(risk 컷 0.132753, 분포 4624/2971/2089/443)은 값 불변이므로 건드릴 일 없음 — 빨개지면 마트 값을 바꾼 것이니 멈추고 원인 규명.

### 결정 기록 (create-story가 내린 것 — dev는 따르되 이견 시 HALT)

- **D1 (AC4)**: `campaign_selected` 컬럼 비탑재. 근거: 공식 단일 예산 부재(3-3 "헤드라인은 곡선"), 예산=시나리오 입력, 임의 예산 config화는 세탁. AD-12 의무는 "정의를 marts 문서에 명명"이며 컬럼 탑재를 요구하지 않음(3-3 코드리뷰 원문 확인). 에픽 분할 노트의 "budget=0 UX와 한 몸" 처리도 AC3(메시지)로 충족.
- **D2 (AC7)**: 06 stage·reports/ 비도입. 근거: AD-2 유일 writer 원칙, 4-1a 골든 테스트가 집계 경로의 커밋된 실체, 실수요(4-3) 전 스테이지 신설은 투기.

### 범위 밖 (하지 말 것)

- `expected_saving`·`assign_quadrant` 시그니처 변경(위 경계 참조).
- 화면·뷰에서 `churn_score` 제외 — **4-3 소관**(층 분리, Sally 액션).
- risk_quantile annex 노출 규칙 — 4-3 소관.
- LTV 마트(4-2, blocked)·Tableau 사양(4-3)·README(4-4).

### Testing standards

- 행동 기반(동어반복 금지): 계약 테스트는 "거부됨"을 단언(RangeIndex → ValueError, 메시지 매칭), sentinel은 값 동일성.
- 문서=계약 테스트: 스키마 문서 파싱 단언(4-1a 패턴 계승).
- 실데이터 오라클은 parquet 부재 시 skip(3-4 관례). xgboost 부재 환경에서 `tests/churn` collection 에러는 기지 사항 — 회귀 기준선 360(churn 제외).

### Project Structure Notes

- **수정**: `crm/campaign/priority.py`(좁히기+메시지), `marts/mart_customers.schema.md`(칸+절), `tests/campaign/test_priority.py`, `tests/marts/test_customers.py`, `docs/specs/spec-crm-targeting-lab/conventions.md`, `docs/implementation-artifacts/deferred-work.md`(종결 주석).
- **신규 파일 없음, 신규 모듈 없음** — 이 스토리는 순수 경화다.
- 40행 제약·구조 가드 영향 없음(pipelines 무변경). AD-12 selfcut 가드는 priority.py에 quantile류 호출만 금지 — 이번 변경과 무충돌.

### References

- [Source: docs/planning-artifacts/epics.md#Story 4.1] — 분할 노트(4-1b 범위 6건 열거)
- [Source: docs/implementation-artifacts/deferred-work.md] — "3-3 코드리뷰 보류 5건 파티 결정"(구item1·4·5 원문) · "CLIENTNUM 라벨 대조 가드가 함정 4를 못 잡는다"(Auditor 반증·1,994,740.8) · "customer_value() 출력의 재가중 금지"(1-2 인계 절반) · "4-1 입력"(+19% 오용 실측·층 분리) · "세션 리포트의 집계 경로"(F7 재발·선택지 3종) · "AD-12의 정의 고정 미충족"(campaign_selected)
- [Source: docs/implementation-artifacts/4-1a-customer-mart-assembly-schema.md] — 선행 스토리 전문(구현·리뷰 처분·환경 주의)
- [Source: crm/campaign/priority.py, crm/marts/customers.py, tests/campaign/test_priority.py, tests/marts/test_customers.py] — 실측 시그니처·가드·픽스처
- [Source: docs/THESIS.md §7] — 배제 임계 비준(config 고정+annex) — D1의 "시나리오 입력 vs 정책가정" 구분과 같은 원칙 계열

## Dev Agent Record

### Agent Model Used

claude-opus-5 (Claude Code, dev-story workflow)

### Debug Log References

- **빈 축 vs dtype 검사 순서**: `_population([], [], [])`의 빈 인덱스는 object dtype이라 정수 검사가 "empty"보다 먼저 오진 — `_require_clientnum_index`가 빈 축의 dtype 검사를 건너뛰어 기존 empty 가드가 실패를 명명하도록 함(이름 검사는 빈 축에도 적용).
- **기존 테스트 영향 정확히 1건**: `test_the_multiple_is_refused_when_the_baseline_is_not_positive`(빈-빈 케이스)가 AC3로 red — 의도된 red. 원인 명명 테스트로 재편하고, non-positive 분모의 정당한 케이스(선택 1명·음수 우세 모집단, 분모 실측 음수)를 분리 신설.
- **sentinel 페어링 함정**: 4-1a 픽스처가 세 소스를 셔플하므로 위치 기반 sentinel은 페어링이 깨짐 — CLIENTNUM 키 매핑으로 주입.

### Completion Notes List

- ✅ **AC1**: 랭킹 계층(target_priority·select_within_budget 경유) 3축 CLIENTNUM 정수 인덱스 요구. RangeIndex 표현 불가능화, 3-3 부분 가드 → 전면 가드 승격. `expected_saving`(3-2) 계약 불변.
- ✅ **AC2**: `random_baseline` 동일 요건 — 모집단 정체성이 축의 인덱스로 감사 가능.
- ✅ **AC3**: 빈 캠페인 메시지가 `binding_constraint` 인용으로 원인 명명(3종 구분 테스트). "positive baseline"은 캠페인이 비어 있지 않을 때만.
- ✅ **AC4 (D1)**: `campaign_selected` 정의 스키마 고정 + 컬럼 비탑재(예산=시나리오 입력, 임의 config화는 세탁). 문서 파싱 테스트 고정.
- ✅ **AC5**: 스키마 `용도/금지` 칸 — churn_score "금액 산식 금지(+19.0%)"·churn_prob_calibrated "분면 컷 재계산 금지" + 전 컬럼 표기. 뷰 노출 제어는 4-3 인계 유지.
- ✅ **AC6**: customer_value 호출부 sentinel — 1-2 인계 남은 절반 종결. deferred-work 5곳 종결 주석.
- ✅ **AC7 (D2)**: 세션 리포트 규약 conventions.md 10번 명문화. 06 stage·reports/ 비도입.
- **회귀**: 360 → **370 passed**(+10), 1 skipped, 회귀 0. **마트 CSV 바이트 불변**(순수 경화 DoD). 마트 골든값 전부 유지.
- **4-3 인계**: 뷰에서 `churn_score` 노출 여부(Sally) · risk_quantile annex 노출 규칙 · `campaign_selected` 실체화(시나리오 뷰에서 `select_within_budget` 호출).

### File List

**수정** (신규 파일 0 — 순수 경화)
- `crm/campaign/priority.py` — `_require_clientnum_index` 신설·3축+baseline 적용·부분 가드 전면화·빈 캠페인 메시지·docstring 정합
- `marts/mart_customers.schema.md` — 용도/금지 칸(+배경 문단)·campaign_selected 절
- `tests/campaign/test_priority.py` — 거부 4·메시지 3(재편 1 포함)·non-positive 분모 분리
- `tests/marts/test_customers.py` — 스키마 금지 문구·campaign_selected 절·sentinel(`_schema_row` 헬퍼)
- `docs/specs/spec-crm-targeting-lab/conventions.md` — 10번 세션 리포트 규약
- `docs/implementation-artifacts/deferred-work.md` — 종결 주석 5곳(1-2 인계·F7·구item1/4/5)
- `docs/implementation-artifacts/sprint-status.yaml` — 상태 갱신

### Change Log

- 2026-07-24: 4-1b 구현 — 랭킹 계층 CLIENTNUM 인덱스 계약(함정4 전면 방어), 빈 캠페인 원인 명명, campaign_selected 정의 고정(컬럼 비탑재 D1), 스키마 용도/금지 칸(+19% 방어), customer_value 호출부 sentinel(1-2 인계 종결), 세션 리포트 규약(D2). 370 passed, 마트 바이트 불변.

---

**기준선**: 4-1a done 커밋 `9eb3556`. 이 환경(xgboost 미설치) 360 passed(churn 제외). 마트 골든값: 총합 1,454,088 · risk 컷 0.132753 · 분포 4624/2971/2089/443 — **이 스토리에서 마트 값은 단 하나도 변하면 안 된다**(순수 경화의 정의).

**Ultimate context engine analysis completed — comprehensive developer guide created.**
