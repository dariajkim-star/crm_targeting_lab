---
baseline_commit: 1b068da
baseline_passed: 376
artifact_id: 9e1a4d71800f
---

# Story 3.3: 예산 제약 타겟 우선순위

Status: done

## Story

As a 마케팅 의사결정자,
I want 고정 예산 안에서 누구를 먼저 잡을지 순위와 그 효과를,
So that "무작위로 뿌리는 것보다 몇 배 낫다"를 수치로 말할 수 있다.

## Acceptance Criteria

**AC1** — **Given** 기대 절감액이 산출됐을 때
**When** `crm/campaign/priority.py::target_priority()`를 호출하면
**Then** 기대절감액 내림차순 dense rank(1이 최우선), 동점 시 `customer_value` 내림차순, 그래도 동점이면 `CLIENTNUM` 오름차순으로 **전순서가 보장**된다(AD-12)
**And** 동일 입력에 대해 재실행 시 순위가 바뀌지 않는다(Tableau 정렬이 새로고침마다 뒤바뀌지 않도록)

**AC2** — **Given** 고정 예산 시나리오가 주어졌을 때
**When** 예산 한도까지 상위 N명을 선택하면
**Then** 무작위 타겟 대비 기대 절감액 배수가 산출된다(FR13, 성공신호 ②)
**And** 무작위 기준선은 `RANDOM_SEED`로 고정되어 재현 가능하다(AD-7)

**AC3** — **Given** 우선순위가 `quadrant_official`과 함께 소비될 때
**When** 일관성을 검사하면
**Then** 시뮬레이터가 자체 컷을 만들지 않고 3.1의 `quadrant_official` 컬럼을 소비함이 확인된다(AD-12)

**AC4** — **Given** 예산이 0이거나 대상이 없을 때
**When** 시뮬레이터를 실행하면
**Then** 조용히 빈 결과를 반환하지 않고 명시적으로 처리·기록한다(P1 2-1 빈 모집단 교훈)

### AC 파생 — 이 스토리가 함께 닫는 계약 (필수)

**AC5 (음수 기대절감액 방침 — 3-2 인계 미결)** — `deferred-work.md` 3-2 절이 *"3-3이 우선순위를
매길 때 음수를 제외할지 순위 맨 아래에 둘지는 정해지지 않았다. 3-3이 결정하고 근거를 남길 것"*을
남겼다. **결정: 순위는 전원에게 매기고, 예산 선택에서만 제외한다** — 근거는 아래 결정 D1.
`target_priority()`는 10,127명 전원에 dense rank를 부여하고, `select_within_budget()`은
**예산 소진 AND 기대절감액 > 0** 둘 다로 자른다. **예산이 남아도 음수는 사지 않는다.**
이 두 성질이 각각 테스트로 고정되어야 한다.

**AC6 (`customer_value` 비음수 확인 — 3-2 인계)** — 3-2 코드리뷰가 단조성 주장을 "비음수 가치
하에서"로 **좁히고** 확인 책임을 3-3에 넘겼다(`simulate.py` 모듈 docstring: *"A consumer that ranks
on this output owes itself a non-negativity check on the value axis first."*). **결정: 3-3이 자기
경계에서 fail-fast한다. `crm/segment/value.py`는 건드리지 않는다** — 근거는 아래 결정 D2.

**AC7 (AD-11 소비자 계약 테스트 — 1-2 인계, 3-3 몫)** — `deferred-work.md`의 1-2 항목이 소비자별
계약 테스트를 요구하며 3-3 몫을 *"민감도 변화가 value 정의 자체를 바꾸지 않는가"*로 적었다.
**민감도는 3-4 소관이라 이 문구는 스토리 배정이 어긋나 있다.** 3-3에 실재하는 소비 지점은
**`customer_value`를 동점 2차 정렬 키로 쓰는 것**이고, 계약은 *"정렬 키로만 쓰고 값을 변형하지
않는가"*다. **주의 — 이 계약은 3-2 방식으로 검증되지 않는다**: 값 축에 `log1p` 같은 **단조 변환**을
걸면 동점 그룹 내 순서가 그대로라 sentinel 값 비교가 **조용히 통과**한다. 검증은 **동점 그룹 내
순서**로 해야 하고, 죽여야 할 변이는 **비단조 변환**(예: `-value`, `abs(value - median)`)이다.

## 이 스토리가 내린 결정 (근거 포함)

> 3-2가 미결로 넘긴 2건이다. **dev가 뒤집을 수 있으나, 뒤집는다면 근거를 여기에 덮어쓸 것.**

### D1 — 음수 1,540명: 순위는 매기되 예산 선택에서 제외

**먼저, 3-2가 남긴 전제 하나가 틀렸다.** `deferred-work.md`는 *"두 선택은 `target_priority`의
dense rank 결과를 다르게 만든다"*고 적었다. **실측상 양수 8,587명의 dense rank는 음수를 포함하든
빼든 완전히 동일하다**(dense rank는 순서 기반이라 꼬리를 떼도 머리 순위가 안 변한다 — 아래 실측
「dense rank 불변」). 차이는 **음수 1,540명 자신이 순위 숫자를 받느냐 null을 받느냐**뿐이다.
즉 이 결정은 랭킹 산식의 문제가 아니라 **마트 스키마와 선택 규칙**의 문제다.

**결정과 근거**:

| 관심사 | 처리 | 근거 |
|---|---|---|
| 순위 | 전원 10,127명 dense rank | AC1이 요구하는 **전순서 보장**을 문자 그대로 충족한다. 4-1 마트에 nullable 컬럼이 안 생기고 Tableau가 빈칸을 그리지 않는다. |
| 선택 | 예산 소진 **AND** `expected_saving > 0` | 순위 숫자가 있다고 접촉 후보인 것은 아니다. 예산이 충분해도 음수를 사면 **가치를 파괴**한다. |

**"예산만으로 자르기"를 택하지 않은 이유(실측)**: 누적 기대절감액은 **N=8,587에서 최대**가 되고
(1,456,900), 전원을 접촉하면 **1,454,088**로 **2,812 감소**한다. 예산만으로 자르는 구현은 예산이
크면 이 구간을 조용히 사들이고, "무작위 대비 배수"가 예산이 커질수록 희석된다(x1.18 → x1.00).

**이 결정이 만드는 한계(리포트에 실을 것)**: 순위가 있다는 것이 접촉 권고를 뜻하지 않는다.
마트를 그대로 읽는 4-1·4-3 소비자는 `target_priority`만 보고 상위 N을 자를 수 있고, 그때
음수 구간이 딸려 들어온다. **`target_priority`와 나란히 선택 가능 여부를 나타내는 컬럼을 함께
내보낼 것**(AC5 T2). 이것은 "검사 불가능한 것에 문서를 쓰는" 경우가 아니라 컬럼으로 검사 가능하다.

### D2 — 비음수 확인은 `target_priority()`에서 fail-fast, `value.py`는 불변

3-2 리뷰의 선택지 (a)는 `value.py`에 비음수 계약을 명시하는 것이었고 "AD-11 소유권상 가장 정당"
하다고 적혔다. **그럼에도 (a)를 택하지 않는다**: `customer_value`는 `Total_Trans_Amt`를 원 스케일로
반환하는 **정의**이고, "값이 항상 비음수"는 **현 데이터가 우연히 만족하는 성질**이다(실측 최소
510.0). 정의에 없는 것을 계약으로 승격하면 데이터의 사실을 정의의 보장으로 바꾸는 것 —
**불확실을 확실로 세탁하는 쪽**이다. 게다가 스토리 3-3이 스토리 1-2 소유의 계약을 개정하게 된다.

따라서 **소비자가 자기 전제를 자기 경계에서 검사한다**. (D2 원문 계속) `target_priority()`는 값 축에 음수가 있으면
`ValueError`로 거부하고, 메시지가 **왜**(단조성 역전 → 순위가 뒤집힘) 거부하는지 말한다.
`value.py`에 비음수 계약을 넣는 안은 `deferred-work.md`에 **AD-11 개정 사안으로 남긴다**.

## Tasks / Subtasks

- [x] **T1** `crm/campaign/priority.py::target_priority()` 구현 (AC1·AC6)
  - [x] 순수 함수. **`expected_saving()`을 소비**하거나 그 출력 Series를 받는다 — 산식 재구현 금지(AD-9)
  - [x] 정렬 키 3단: `expected_saving` 내림차순 → `customer_value` 내림차순 → `CLIENTNUM` 오름차순
  - [x] **전순서상의 위치로 순위 부여**, 1이 최우선 — CLIENTNUM 유일성 하에서 dense와 동치라
        구현은 `np.lexsort` + 위치 배정을 쓴다(`rank(method="dense")` 호출이 아니다). 초판이 이 칸에
        `method="dense"`라 적은 것은 코드와 불일치였고 코드리뷰가 정정했다 — 등가성 논거는 Completion Notes
  - [x] 값 축 **비음수 fail-fast**(D2). 거부 사유를 메시지가 설명할 것
  - [x] `crm.campaign.sensitivity` import 금지(AD-9 방향)
  - [x] **자체 분면 컷 금지** — 분면이 필요하면 `quadrant_official`을 소비만(AD-12)
- [x] **T2** `select_within_budget()` 구현 (AC2·AC4·AC5)
  - [x] **예산 소진 AND 기대절감액 > 0** 둘 다로 컷(D1). 예산이 남아도 음수는 사지 않는다
  - [x] 선택 가능 여부 컬럼을 함께 반환(D1 한계 대응)
  - [x] **예산 0 · 대상 0명 · 예산이 1명 비용에도 못 미침**을 각각 명시적으로 처리·기록(AC4).
        조용한 빈 결과 금지 — 빈 선택과 "선택할 것이 없음"을 구분해 알릴 것
  - [x] 예산 단위는 **접촉 인원 × `cost_per_contact`**. 1인 1회 가정을 명시(3-2 인계 — 아래 함정 5)
- [x] **T3** 무작위 기준선과 배수 (AC2)
  - [x] `RANDOM_SEED` 고정(AD-7). **단일 추출이 아니라 반복 추출의 평균**을 쓸 것 — 아래 함정 3
  - [x] 반복 횟수를 인자로 노출하고 리포트에 기록. 배수의 **산포**도 함께 낼 것
- [x] **T4** 테스트 — 행동 기반 (AC1~AC6)
  - [x] **동점 처리는 합성 픽스처로만 검증 가능하다** — 실데이터에 동점이 0건이다(함정 2)
  - [x] 재실행 안정성: 입력 순서를 섞어도 순위가 동일함(AC1 2항)
  - [x] dense rank 성질: 동점은 같은 순위, 다음 순위는 건너뛰지 않음
        → **"동점은 같은 순위"는 이 함수에서 관측 불가능하다.** `CLIENTNUM`이 유일하고 그것을
        강제하므로 복합 키에 중복이 생길 수 없고, `dense`·`min`·`first`가 전부 같은 `1..n`을 낸다.
        검증 가능한 실제 성질은 **`1..n` 전단사(동점 없음·결번 없음)**이며 그쪽을 테스트했다
        (`test_the_rank_is_a_bijection_onto_one_through_n`). AD-12의 "dense"는 이 조건 하에서
        무력(inert)하다는 것이 이 스토리의 발견이다 — Completion Notes 참조
  - [x] 음수 컷: 예산이 전원을 살 수 있어도 선택은 8,587명에서 멈춤
  - [x] 비음수 fail-fast, 빈 모집단·예산 0
  - [x] **변이 테스트**: 정렬 방향 반전 · 동점 키 순서 뒤바꿈 · `dense`→`min`/`first` · 음수 컷 제거
        → **전부 KILL이 아니다.** 실제 실행 결과 M1~M4·M6~M8은 KILL, **M5(양수 마스크 제거)는
        SURVIVED — 등가 변이라 어떤 테스트로도 죽일 수 없다**(1차 정렬 키가 절감액 자신이라
        `min()`이 이미 음수를 배제한다). 초판 문구가 요구한 "전부 KILL"은 성립하지 않으며,
        3-2가 확률·가치 swap 변이를 목록에서 뺀 것과 같은 성격이다. 등가성의 근거인 불변식을
        별도 테스트로 고정했고, 마스크의 실효(다중 방어)는 M9/M10으로 실측했다 — Debug Log 참조
  - [x] **동어반복 금지** — 같은 정렬을 테스트 안에서 다시 써서 비교하지 말 것
  - [x] **AC7 계약 테스트**: 동점 그룹을 만든 합성 픽스처에서 `customer_value` 2차 키가 **원 값 그대로**
        쓰임을 **그룹 내 순서**로 검증. 단조 변환(`log1p`)은 이 테스트를 통과한다는 것을 알고 갈 것 —
        죽여야 할 변이는 **비단조 변환**(`-value`, `abs(value - median)`)이다. 값 동일성 비교로
        때우면 3-2와 같은 형태의 헛도는 테스트가 된다
- [x] **T5** 실데이터 실행 + 리포트 (AC2·AC3)
  - [x] `docs/implementation-artifacts/priority-report-3-3.md`
  - [x] 예산 시나리오별 배수표, 분면 구성, **가정 라벨링**(NFR1), 무단위 표기(NFR3)
  - [x] **함정 1(배수는 예산이 커질수록 1로 수렴)을 정면으로 다룰 것**
  - [x] 3-2 리포트 §①이 남긴 "우선순위는 분면이 아니라 개인 단위"를 실제 수치로 닫을 것
- [x] **T6** `deferred-work.md`(3-2 인계 3건 + 1-2 인계 1건의 해소·잔존 표기, AD-11 개정 사안 신설)·
      `sprint-status.yaml` 갱신
  - [x] create-story가 **결정**까지만 표기해 뒀다(구현 대기). dev가 구현 후 **해소로 승격**할 것 —
        3-0·3-2가 연속으로 지적받은 누락 지점이다

### Review Findings

코드리뷰 2026-07-22 (3레이어 병렬: Blind Hunter / Edge Case Hunter / Acceptance Auditor).
원시 44건 → 중복병합·실물검증 후 **decision 2 · patch 23 · defer 2 · dismiss 6**.

**Auditor가 리포트·스토리의 측정 수치를 전건 독립 재실행해 재현 확인했다** — 84.8% · 1,454,088 ·
배수표 8행 · 2,812 · 분면 443/2089/4624/2971 · 1인당 1415.00/382.81/6.14/−0.28 · 최선최악 순위 ·
309+134 · 단일추출 x8.35~x13.82 · 동점 0건 · 최소 510.0 · 함정4의 +37.2%까지 일치. **수치 오기 0건.**
**결함은 전부 코드의 가드와 문서의 주장에 있다** — 3-2와 같은 패턴이다.

**honesty 주장 3건 중 2건 감사 통과**: M5 등가 변이 논거 **SOUND**(Blind가 NaN·−0.0·int dtype으로
깨보려다 실패, Auditor가 논증을 독립 재구성), AD-12 dense 무력성 **SOUND**. 세 번째(부분 가드)는 **실패** — D1.

- [x] [Review][Decision] **`CLIENTNUM` 대조 가드가 함정 4를 못 잡는다 — 마트 형태에서조차** — 내가 이 가드를 "4-1에서만 실효가 있다"고 `deferred-work.md`에 적었는데 **Auditor가 그 진술을 반증했다**. 실측 2종: (A) `RangeIndex` 위치 결합 → 무예외, 합계 1,994,740.8 (B) **CLIENTNUM 인덱스로 재조립한 4-1 마트 형태** + 같은 프레임의 `clientnum` → **여전히 무예외, 합계 1,994,740.8**. 이유: 함정 4가 오염시키는 것은 **절감액 축**인데 그 축은 정체성을 안 들고 다닌다. 가드가 잡는 것은 "잘못 라벨된 CLIENTNUM **컬럼**"이지 "어긋난 절감액 축"이 아니다. 리포트 §⑦과 `deferred-work.md`가 **둘 다 보호를 과장**한다. 선택지: (a) 문서만 정정하고 "이 계층에 기계적 보호는 없다"를 명시한 뒤 4-1에 넘김 (b) 세 축 모두 CLIENTNUM 인덱스를 요구하도록 계약을 좁힘 — 호출부 계약 변경 (c) 둘 다 [crm/campaign/priority.py::_validate_alignment] — **[파티 결정→defer(4-1)] 문서 정정은 완료. 계약 좁히기(세 축 CLIENTNUM 인덱스)는 인덱스가 실제로 세팅되는 4-1에서 수행 — 여기서 좁히면 done인 3-2가 비순응이 된다(레아·다나 안, daria 승인 2026-07-22).**
- [x] [Review][Decision] **AC3에 커밋된 검증이 없다** — AC3은 "`quadrant_official` 컬럼을 소비함이 **확인된다**"인데 유일한 증거가 리포트 §④ 산문과 **gitignore된** `scratch/run_priority_3_3.py`다. `test_priority.py`에 분면 단언 0건이고, 내가 넓힌 AD-9 가드는 `priority.py`가 `matrix.py`를 import하는 것을 **명시적으로 허용**한다(체인상 앞 단계라 정상). "자체 컷 금지"는 **오늘의 파일에 대해 참일 뿐 강제되지 않는다**. 선택지: (a) `priority.py`가 분위수·컷 호출을 갖지 않음을 구조 테스트로 고정 (b) AC3 검증을 4-1로 넘기고 3-3에서는 **미충족 표기** (c) 분면을 실제 소비하는 얇은 함수를 3-3에 두고 테스트 ✅적용
- [x] [Review][Patch] **`multiple_over_random`이 분모만 검사하고 분자를 안 본다 — docstring이 막는다고 선언한 값이 통과** — `multiple_over_random(-320.0, 평균100)` → **−3.2 조용히 반환**. **내 테스트가 그 구멍을 실증한다** — `test_the_multiple_is_refused_when_the_baseline_is_not_positive`가 분자에 `-1.0`을 넣고 통과한 이유는 분모가 음수였기 때문. NaN·inf도 통과 [crm/campaign/priority.py] — **✅적용(구조적 해소): 유이 통합안으로 분자가 `selection.selected_total`이 됐다 — 검증된 축 + 양수 전용 선택에서 구성되므로 유한·비음수가 구조적으로 보장되고, 임의 float을 넣는 호출 자체가 거부된다(`test_a_bare_float_numerator_is_no_longer_accepted`).**
- [x] [Review][Patch] **기준선과 비교 대상 선택을 묶는 것이 없다 — 헤드라인 수치가 조용히 어긋난다** — 실측: 8,587명 선택을 100명 기준선과 비교 → **x99**, 전 인원 합계를 2명 기준선과 → **x2.54**. 무예외·게재 가능·틀림. FR13 산출물 전체가 이 배수인데 한 줄 assert가 없다 [crm/campaign/priority.py] — **✅적용(유이 통합안, daria 승인): `multiple_over_random(selection: BudgetSelection, baseline: RandomBaseline)`로 시그니처 변경. 함수가 두 결과 객체에서 분자·분모를 직접 읽고 `n_contacts != selected_count`를 거부 — x99가 호출부에서 표현 불가능해졌다(`test_a_baseline_of_the_wrong_contact_count_is_refused`).**
- [x] [Review][Patch] **`random_baseline`이 모집단 동일성을 검증하지 않는다** — `target_priority`에서는 길이·인덱스·dtype·중복까지 잡고 **분모를 만드는 함수에서 규율을 놓았다**. 걸러진 Series를 풀로 넘기면 유효한 기준선·유효한 배수·틀린 분모 [crm/campaign/priority.py] — **[파티 결정→defer(4-1)] 통합안이 배수 경로의 오용은 닫았으나 `random_baseline` 자체는 여전히 맨 Series를 받는다. 모집단 정체성 검증은 마트가 단일 조인 지점이 되는 4-1에서 함정 4 계약 좁히기와 함께 처리(daria 승인 2026-07-22).**
- [x] [Review][Patch] **`int(budget // cost)`가 돈이 아니라 표현 오차를 floor한다 — 1명을 덜 산다** — 실측 `cost 0.1 budget 1.0 → 9`(10이어야) · `cost 1.1 budget 11.0 → 9` · `cost 3.3 budget 108.9 → 32`. 1명분 예산이 남았는데 `binding_constraint='budget'`으로 보고. 방향이 일정하지 않아 가드로만 막힌다. 현 `COST_GRID`가 이진 정확값이라 잠복이나 **3-4가 비이진 비용을 스윕하면 즉시 발동**. 비정수 cost 테스트 0건 [crm/campaign/priority.py] ✅적용
- [x] [Review][Patch] **미세 `cost_per_contact`에서 `OverflowError` — 문서화된 `ValueError` 계약 위반** — `budget=1.0, cost=5e-324` → `OverflowError`. 두 피연산자의 유한성은 보되 **몫의 유한성을 안 본다** [crm/campaign/priority.py] ✅적용
- [x] [Review][Patch] **`binding_constraint`가 세 사실을 두 라벨로 뭉갠다 — T2가 "각각"을 요구한 지점** — ①`budget=4.99, cost=5.0` → `ZERO_BUDGET`(0원과 "단가 미만"은 다른 사실). 내 테스트가 이 혼동을 **고정**해 버렸다 ②전원 음수 + `budget=0` → `no_positive_candidates`가 먼저 걸려 **예산 0이라는 사실이 사라진다** [crm/campaign/priority.py] ✅적용
- [x] [Review][Patch] **커밋된 코드가 같은 커밋의 리포트가 폐기한 수치를 들고 있다 (4곳)** — ①`multiple_over_random` docstring의 *"x1.00까지 단조 감소"* — **D1 정책은 x1.18 바닥**이고 x1.00은 내가 기각한 정책의 값. **쓰이지 않은 코드를 묘사하는 docstring** ②`RandomBaseline`·`random_baseline`·`config.py`의 *"x7.76~x14.09"* — 구현이 내는 값은 **x8.35~x13.82**이고 Auditor는 **어떤 자연스러운 seed 범위에서도 재현 실패**. 프로젝트 서명에 정면으로 걸린다 [crm/campaign/priority.py, crm/config.py] ✅적용
- [x] [Review][Patch] **`BOTH_BOUND`가 어떤 테스트도 안 거치고, 상수 대신 문자열 리터럴로 비교한다** — `affordable == positive > 0`을 만드는 테스트가 없어 **그 분기 라벨이 틀려도 초록으로 나간다** [tests/campaign/test_priority.py] ✅적용
- [x] [Review][Patch] **`clientnum.is_unique` 가드가 테스트 헬퍼 구조상 도달 불가** — `_population()`이 인덱스를 `clientnums`에서 만들어 CLIENTNUM 중복이 **항상 인덱스 가드에 먼저 걸린다**. 테스트가 `"duplicat"`만 매칭해 **어느 쪽이 발동했는지 구분도 못 한다** [tests/campaign/test_priority.py] ✅적용
- [x] [Review][Patch] **frozen dataclass가 살아있는 pandas 객체를 들어 거짓 불변성을 준다** — `result.priority.iloc[0] = 999`가 성공하고 이후 `selected_count`·`selected_total`·`binding_constraint`가 **서로 모순**한다. 클래스 docstring이 "함께 다닌다"로 막겠다던 함정. 내부 정합 단언 0건 [crm/campaign/priority.py] ✅적용
- [x] [Review][Patch] **`test_a_different_seed_gives_a_different_baseline`이 잠재 플레이크** — 4명·`n_contacts=2`면 **구별되는 쌍 합이 6개뿐**인데 8회 평균 둘의 **엄격 부등호**를 단언한다 [tests/campaign/test_priority.py] ✅적용
- [x] [Review][Patch] **`test_more_draws_shrink_the_spread_of_the_mean`에 허용오차가 없다** — 6결과 공간에서 **기댓값으로 참**이지 구성상 참이 아니다. "평균내기가 작동한다"와 "numpy RNG가 정상이다"를 구분 못 한다 [tests/campaign/test_priority.py] ✅적용
- [x] [Review][Patch] **`n_contacts`·`draws`·`seed`가 범위만 검사되고 타입 미검사** — `n_contacts=2.5`·`n_contacts=True`(bool은 int 하위형)·`draws=3.7`·`seed=-1`이 **인자도 함수도 안 알려주는** numpy 날 에러로 터진다. `_require_series`가 막으려던 실패 양식 [crm/campaign/priority.py] ✅적용
- [x] [Review][Patch] **전 인원 추출 시 `spread_total=0.0`이 구조적 0인데 측정값처럼 보고된다** — `replace=False`가 `size == len`이면 순열이라 모든 draw가 같은 합. **진짜 좁은 추정과 구분 불가능한 0폭**을 보고하며 200 × 10,127 순열을 태운다 [crm/campaign/priority.py] ✅적용
- [x] [Review][Patch] **정당한 `budget=0` 경로가 엉뚱한 메시지로 끝난다** — 실제 원인은 접촉 인원 0인데 *"기준선이 양수여야 한다"*로 거부. `n_contacts=0`을 허용해 놓고 두 함수가 **빈 캠페인의 합법성에 대해 다른 말을 한다** [crm/campaign/priority.py] — **[파티 결정→defer(4-1)] 만장일치 nit. `budget=0` 경로의 메시지 정합은 4-1에서 배제/빈 캠페인 UX를 설계할 때 함께(daria 승인 2026-07-22).**
- [x] [Review][Patch] **`selected` 마스크 dtype이 입력 dtype에 따라 달라진다** — nullable 입력이면 `BooleanDtype`, 아니면 `bool`. `target_priority` 반환은 dtype이 못박혀 있는데 `selected`는 없어 **4-1 parquet 타입이 상류에 따라 갈린다** [crm/campaign/priority.py] ✅적용
- [x] [Review][Patch] **Debug Log의 M7/M8 라벨이 실제 심은 변이와 다르다** — 실제로 심은 것은 **타이브레이크 체인을 버리고 절감액만으로 랭크**하는 변이다. 리터럴 `dense→min/first`는 죽지 않으며 테스트 파일이 그렇게 명시한다. **체크박스만 읽으면 AD-12 dense 조항이 변이 커버됐다고 결론내게 된다** [3-3-...md Debug Log] ✅적용
- [x] [Review][Patch] **T1 체크박스가 코드에 없는 `method="dense"`를 주장한다** — 구현은 `np.lexsort` + 위치 배정. 등가성 논거는 건전하나 **정정이 T4에만 있고 T1에는 없다** [3-3-...md T1] ✅적용
- [x] [Review][Patch] **T4의 "선택은 8,587명에서 멈춤"을 커밋된 테스트가 검증하지 않는다** — 45건 **전부 합성**이고 최대 픽스처 4행. 8,587 정지는 gitignore된 스크립트에서만 관측된다 [3-3-...md T4] ✅적용
- [x] [Review][Patch] **리포트 §① 8,587·10,127행의 "접촉 인원" 라벨이 틀렸다** — 10,127행이 접촉하는 것은 **8,587명**이다(윗행과 값이 같은 이유). **열 제목이 그 행에 대해 문자 그대로 거짓** [priority-report-3-3.md §①] ✅적용
- [x] [Review][Patch] **리포트의 "커밋되지 않은 것은 호출 순서 5줄뿐"이 재생성에 불충분** — §②의 반사실 열, §③의 50 seed 스윕, §④의 분면×순위 교차표가 빠졌다. Auditor가 셋 다 재구성해야 했다 — 3-2 F7 완화 문구가 **여전히 과잉 주장** [priority-report-3-3.md 머리말] ✅적용
- [x] [Review][Patch] **M9/M10의 15.0 vs 13.0을 커밋된 아티팩트로 감사할 수 없다** — `distinct` 픽스처 양수 합은 60.0이라 대응하지 않고, 그 수치를 내는 픽스처는 **커밋된 적이 없다**. 4곳에서 인용됨 [crm/campaign/priority.py, tests, Debug Log, deferred-work.md] ✅적용
- [x] [Review][Patch] **`spread_total`이 모집단 표준편차(ddof=0)인데 "산포(σ)"로 실린다** — 표본 평균의 감사 가능한 폭으로 제시되면서 규약을 어디에도 안 적었다 [crm/campaign/priority.py] ✅적용
- [x] [Review][Defer] **AD-12의 "정의를 스키마 문서에 고정한다"가 미충족** [ARCHITECTURE-SPINE.md AD-12] — deferred, `marts/` 어디에도 `target_priority`·`campaign_selected`를 명명한 스키마 문서가 없다(grep 0건). 4-1 소관이나 AD-12는 정의 소유자를 구속한다
- [x] [Review][Defer] **`_validate_axis` 반환값을 세 호출부가 버리고 같은 Series를 다시 변환한다** [crm/campaign/priority.py] — deferred, 현재는 무해하나 **검증된 배열과 정렬되는 배열이 다른 객체**라 변환에 인자가 붙는 순간 갈라진다

## Dev Notes

### 🚨 함정 1 — "무작위 대비 X배"는 예산이 정하는 숫자다

실측(기본 가정 `rate=0.30`, `cost=5.0`, 무작위는 200회 추출 평균):

| 예산 N명 | 상위 N 합계 | 무작위 평균 | **배수** |
|---|---|---|---|
| 100 | 252,376 | 14,190 | **x17.79** |
| 443 (Save 우선 인원) | 710,470 | 62,677 | **x11.34** |
| 500 | 751,237 | 72,004 | x10.43 |
| 1,000 | 1,072,479 | 143,094 | x7.49 |
| 2,532 (Save+관망) | 1,429,942 | 364,681 | x3.92 |
| 5,000 | 1,450,500 | 718,264 | x2.02 |
| 8,587 (양수 전원) | 1,456,900 | 1,232,136 | x1.18 |
| 10,127 (전원) | 1,454,088 | 1,454,088 | **x1.00** |

**배수는 예산이 커질수록 단조 감소해 1로 수렴한다.** 전원을 접촉하면 타겟팅이 무작위와
같아지는 것이 당연하기 때문이다. 그러므로 **"X배"를 예산 없이 인용하면 안 된다.**
리포트가 x17.79만 뽑아 쓰면 "이 프레임은 17.79배 낫다"로 읽히는데, 그것은 **예산이 100명일 때**의
숫자다. 성공신호 ②가 요구하는 것은 하나의 배수가 아니라 **예산-배수 곡선**이다.

3-2가 함정 4에서 "84.8%는 `cost=5.0`이 만든 숫자"라고 했던 것과 같은 계열이다. 여기서는
**예산이 그 자리에 있다.**

### 🚨 함정 2 — 동점 처리 규칙은 실데이터가 검증해주지 않는다

실측: **기대절감액 10,127개가 전부 서로 다르다**(distinct 10,127 / 10,127). 동점 그룹 0건.
`customer_value` 2차 키도, `CLIENTNUM` 3차 키도 **실데이터에서는 한 번도 발동하지 않는다.**

부동소수 곱셈 결과라 당연한 결과지만, 함의가 크다:

- **실데이터 실행은 동점 규칙이 맞는지 아무것도 말해주지 않는다.** AC1의 절반이 실행으로
  검증되지 않는다.
- 따라서 동점 규칙은 **합성 픽스처로 테스트**해야 하고, 리포트는 *"동점 규칙이 실데이터로
  확인됐다"*고 쓰면 안 된다. 쓸 수 있는 것은 *"실데이터에 동점이 없어 규칙이 발동하지 않았고,
  규칙 자체는 합성 케이스로 고정했다"*다.
- 동시에 이것은 **좋은 소식**이다 — 재실행 안정성(AC1 2항)이 동점 규칙에 의존하지 않는다.
  현 데이터에서는 1차 키만으로 전순서가 결정된다.

**3-4가 그리드를 쓸면 이 성질이 깨질 수 있다.** `rate=0.0`에 가까운 점에서는 전원이 `-cost`로
붕괴한다(3-2 리뷰가 `retention_rate > 0.0`으로 막았지만 작은 값에서는 유효숫자가 뭉갠다).
동점 규칙은 그때 실제로 쓰인다.

### 🚨 함정 3 — 무작위 기준선을 단일 추출로 만들면 배수가 흔들린다

`RANDOM_SEED`로 고정하면 **재현은 되지만 대표성은 없다.** 실측 — seed만 바꾼 50회 단일 추출:

```
N=500   : 배수가 x7.76 ~ x14.09  (기준선 산포가 평균의 62.1%)
N=2,532 : 배수가 x3.53 ~  x4.35  (산포 21.1%)
```

**같은 코드가 seed 하나로 x7.76도 x14.09도 낼 수 있다.** AD-7이 요구하는 것은 재현성이지
"seed 하나를 뽑아 그것을 사실로 제시하는 것"이 아니다. **반복 추출의 평균**을 기준선으로 쓰고
**산포를 함께 보고**할 것. 위 함정 1 표는 200회 평균이다.

이것이 이 프로젝트의 서명("불확실을 확실로 세탁하지 않는다")이 직접 걸리는 지점이다.
단일 추출 배수는 **불확실한 것을 소수점 둘째 자리까지 확실하게 보이게 만든다.**

### 🚨 함정 4 — 두 parquet의 행 순서가 다르다 (create-story가 실제로 밟았다)

**`churn_scored.parquet`의 행 순서는 `bankchurners.parquet`과 다르다.** 둘 다 평범한
`RangeIndex`를 갖기 때문에:

```python
bc.index.equals(sc.index)   # True  <- 정렬돼 있다는 뜻이 아니다
```

`simulate.py`·`matrix.py`의 `_validate_pair`는 `Index.equals`로 짝을 검사하므로 **이 오정렬을
통과시킨다.** 사전조사 초판이 정확히 이것을 밟았고, 수치가 조용히 어긋났다:

| | 위치 정렬(틀림) | CLIENTNUM 조인(맞음) |
|---|---|---|
| 양수 | 7,469 (73.8%) | **8,587 (84.8%)** |
| 음수 | 2,658 | **1,540** |
| 합계 | 1,994,741 | **1,454,088** |

**37% 부푼 총합이 어떤 예외도 없이 나왔다.** 3-2가 확률 컬럼 오선택(+19.0%)을 막으려고 이름
검사까지 넣었는데, **행 오정렬은 그보다 큰 오차를 내면서 아무 가드에도 안 걸린다.**

**T1·T5는 반드시 `CLIENTNUM`으로 조인할 것.** 그리고 `target_priority()`가 `CLIENTNUM`을 3차
정렬 키로 받는 이상 **이 함수는 `CLIENTNUM`을 이미 손에 쥐고 있다** — 인덱스 정합을 라벨로
검사할 수 있는 첫 번째 지점이다. 이 스토리가 그 검사를 놓으면 4-1 마트가 같은 함정을 밟는다.

### 🚨 함정 5 — "1인 1회"가 예산의 단위라는 가정 (3-2 인계)

`deferred-work.md` 3-2 절: *"산식이 `− cost_per_contact`로 비용을 한 번만 charge한다. 다회 접촉·
채널별 비용 차이·접촉 피로는 모델에 없다. **3-3이 예산 제약을 도입할 때 "1인 1회"가 여전히 맞는
단위인지 재검토할 것.**"*

**재검토 결과: 유지한다.** 예산 = 인원 × `cost_per_contact`로 두고, 그 이유를 리포트에 적는다 —
BankChurners에 캠페인 이력·채널·반응 라벨이 **없다.** 다회 접촉 비용을 넣으면 검증할 데이터
없이 파라미터만 늘고, 그것이 바로 세탁이다. **가정을 유지하되 가정임을 라벨링한다.**

부수 효과 하나: 비용이 전원 동일하므로 **예산 제약이 "상위 N명"과 동치**가 된다. 배낭
문제(knapsack)가 아니라 단순 절단이다. 비용이 고객별로 달라지는 순간 이 동치가 깨지고
그때는 진짜 최적화 문제가 된다 — **그 사실을 리포트에 적어 둘 것.** 지금의 단순함은 구현의
미덕이 아니라 가정의 산물이다.

### 이 스토리가 만들지 않는 것 (범위 경계)

- **ROI 등고선·민감도 스윕 없음** — 3-4 소관. `sensitivity` import 금지(AD-9).
- **기대절감액 산식 없음** — `expected_saving()`을 **소비**만. 재구현 금지(AD-9).
- **분면 판정 없음** — `quadrant_official` **소비**만. 자체 컷 금지(AD-12).
- **`customer_value` 재정의·재가중 없음**(AD-11). 비음수 **검사**는 하되 계약 개정은 안 한다(D2).
- **파이프라인 단계 없음** — 순수 함수. 공식 수치의 자리는 4-1 마트 + 4-3 탭이고 이 리포트는
  **세션 산출물**이다.
- **액션 문구 없음** — 액션 후보는 1-7 실측 매핑이 유일한 출처다(회고 A6, 함정 6은 3-2 참조).

### 물려받은 것 (재사용, 재발명 금지)

- **`expected_saving()`**(3-2): `(churn_prob_calibrated, value, *, retention_rate, cost_per_contact)
  -> Series`. `SAVING_COLUMN = "expected_saving"` 상수도 함께 있다.
- **`assign_quadrant()`**(3-1): `QuadrantAssignment(labels, thresholds, rule, population_size)`를
  한 계산에서 받는다. 분면이 필요하면 이걸 쓰고 임계값을 다시 구하지 말 것.
- **`crm/config.py`**: `RANDOM_SEED=42`, `RETENTION_SUCCESS_RATE=0.30`, `COST_PER_CONTACT=5.0`,
  `RETENTION_GRID`, `COST_GRID`. **예산 그리드는 아직 없다** — 도입한다면 AD-4를 따라 config
  단일 출처 + 대표값의 그리드 포함 검증을 함께 붙일 것.
- **검증 패턴**: 빈 입력·NaN·inf·범위 이탈·중복 인덱스·인덱스 불일치를 fail-fast로.
  `simulate.py::_validate_axis`/`_validate_pair`/`_validate_assumptions`가 참고 구현이다.
  **단, 함정 4가 보여주듯 `Index.equals`는 라벨 정합을 보장하지 않는다.**
- **AD-5 투트랙**: 확률은 `churn_prob_calibrated`, 순위는 `churn_score`. 3-3은 **금액을 정렬**
  하므로 `expected_saving`(= 보정확률 기반)을 정렬하고, `churn_score`를 직접 정렬하지 않는다.

### 실측 사전조사 (2026-07-22, HEAD `1b068da` / 376 passed / `artifact_id 9e1a4d71800f`)

**dev가 코드로 재확인할 것.** 조인은 `CLIENTNUM`(함정 4).

```
가정: RETENTION_SUCCESS_RATE=0.30, COST_PER_CONTACT=5.0  (둘 다 [가정], 실측 아님)

부호      양수 8,587 (84.8%) | 음수 1,540 | 정확히 0: 0명
음수 분포 전원 accept_churn 분면 (2,971명 중 1,540명 = 51.83%)
          -> 다른 세 분면에는 음수가 하나도 없다
동점      기대절감액 distinct 10,127 / 10,127 — 동점 0건 (함정 2)
가치      customer_value 최소 510.0, 음수 0건 -> D2 fail-fast는 현재 발동하지 않는다
누적      상위 N 누적 절감액은 N=8,587에서 최대(1,456,900),
          전원(10,127) 접촉 시 1,454,088로 2,812 감소  <- D1의 근거
분면      443 / 2,089 / 4,624 / 2,971 (save_first / watch / low_cost_keep / accept_churn)
1인당     save_first 1,415.00 | watch 382.81 | low_cost_keep 6.14 | accept_churn -0.28
```

**dense rank 불변(D1의 핵심 근거)**:
```
양수 8,587명의 dense rank는 음수 포함 여부와 무관하게 동일  -> True (실측)
최대 dense rank: 전원 10,127 | 양수만 8,587
```

배수표는 함정 1, 무작위 산포는 함정 3 참조.

> **기준선 갱신**: 3-2가 `504e5e6 / 338`에서 시작해 **`1b068da / 376`**으로 닫혔다. 위 수치는
> 3-2 리포트의 공표 수치와 **전건 일치**한다(84.8% · 1,454,088 · 1,540 · 443/2089/4624/2971 ·
> 1,415.00 / 382.81). `artifact_id`도 `9e1a4d71800f`로 동일하다 — 모델은 이동하지 않았다.

### Testing Standards

- `.venv/Scripts/python.exe -m pytest` — 현 기준선 **376 passed**, 회귀 0
- 성질 + 하드코딩 oracle + 변이 테스트, 실데이터 실행 DoD(conventions 3항)
- **실데이터가 검증하지 못하는 AC가 있다는 것을 알고 갈 것**(함정 2) — 동점 규칙은 합성 픽스처가
  유일한 검증 수단이고, 리포트가 이를 실데이터 확인인 양 쓰면 안 된다
- **문서가 테스트를 앞서지도 뒤처지지도 않기**(회고 A3)

### Project Structure Notes

```
crm/campaign/priority.py                               # NEW - target_priority(), select_within_budget()
tests/campaign/test_priority.py                        # NEW - 전순서·동점(합성)·음수컷·예산경계·변이
docs/implementation-artifacts/priority-report-3-3.md   # NEW - 예산-배수 곡선, 분면 구성, 가정 라벨링
docs/implementation-artifacts/structure-guard-coverage.md  # UPDATE - 테스트가 재생성
docs/implementation-artifacts/deferred-work.md             # UPDATE - 3-2 인계 2건 해소 + AD-11 개정 사안
docs/implementation-artifacts/sprint-status.yaml           # UPDATE
```

> `AD-9 campaign order` 가드의 실스캔이 **2 → 3**으로 늘어나는지 확인할 것(3-2가 2로 만들었다).
> `matrix -> simulate -> priority` 단방향이며 `sensitivity`는 아직 없다.

### 환경 실측 (2026-07-22)

```
HEAD 1b068da | 376 passed | artifact_id 9e1a4d71800f (8피처, OOF + Platt)
churn_score mean 0.1946 / churn_prob_calibrated mean 0.1607 (= 실제 이탈률)
customer_value median 3899.0 / min 510.0 | 분면 443/2089/4624/2971
churn_scored.parquet 행 순서 != bankchurners.parquet — CLIENTNUM 조인 필수(함정 4)
```

### References

- [Source: docs/planning-artifacts/epics.md#Story 3.3] — AC 원문(FR13, AD-12, AD-7)
- [Source: .../ARCHITECTURE-SPINE.md#AD-9] — `matrix -> simulate -> sensitivity` 단방향, 산식 재구현 금지
- [Source: .../ARCHITECTURE-SPINE.md#AD-12] — `quadrant_official` 소비, 자체 컷 금지
- [Source: .../ARCHITECTURE-SPINE.md#AD-11] — `customer_value` 소비·재가중 금지 (D2가 개정을 미룬 조항)
- [Source: .../ARCHITECTURE-SPINE.md#AD-7] — `RANDOM_SEED` 재현성 (함정 3이 그 한계를 다룬다)
- [Source: .../ARCHITECTURE-SPINE.md#AD-5] — 컬럼 분리: 금액에는 `churn_prob_calibrated`
- [Source: docs/implementation-artifacts/3-2-campaign-savings-simulator.md] — 함정 1(총합 역전)·AC5·AC6, 코드리뷰 decision 3건
- [Source: docs/implementation-artifacts/savings-report-3-2.md §①] — 1인당 vs 총합, 3.70배
- [Source: docs/implementation-artifacts/deferred-work.md#3-2] — 인계 미결 3건(음수 방침·1인 1회·단일 성공률)
- [Source: docs/implementation-artifacts/deferred-work.md#1-2] — AD-11 소비자 계약 테스트, 3-3 몫(AC7이 재해석)
- [Source: docs/implementation-artifacts/quadrant-report-3-1.md] — 분면 인원·정책 가설
- [Source: docs/implementation-artifacts/epic-1-retro-2026-07-22.md] — A3·A6
- [Source: 실측 2026-07-22] — 예산-배수 곡선·동점 0건·dense rank 불변·행 오정렬 37% 오차

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (bmad-dev-story)

### Debug Log References

**기준선**: HEAD `1b068da`, 376 passed. **종료**: 421 passed, 회귀 0.

**RED**: `tests/campaign/test_priority.py` 선작성 → `ModuleNotFoundError: crm.campaign.priority`.

**내가 쓴 테스트가 내가 쓴 가드에 걸렸다** — AC7 비단조 변이로 `lambda v: -v`(부호 반전)를 넣었는데
D2의 비음수 fail-fast가 먼저 발동했다. 순서를 뒤집으면서 비음수를 유지하는 `v.max() - v`로 교체.
두 규칙(비음수 요구 / 재가중 금지)이 같은 축에 걸려 있어 변이 설계 공간이 좁다는 뜻이다.

**변이 테스트를 실제로 심어 돌렸다**(`finally` 복원 확인 — 3-2가 변이 잔류로 배운 것):

```
M1 절감액 오름차순 정렬        -> KILLED
M2 동점 키 순서 뒤바꿈          -> KILLED  (value <-> clientnum)
M3 value 키 오름차순            -> KILLED
M4 clientnum 키 내림차순        -> KILLED
M5 양수 마스크 제거             -> SURVIVED  <- 등가 변이
M6 예산 컷 제거                 -> KILLED
M7 타이브레이크 체인 버리고 절감액만 method="min"   -> KILLED
M8 타이브레이크 체인 버리고 절감액만 method="first" -> KILLED
M9  min() 제거 + 마스크 유지    -> KILLED
M10 min() 제거 + 마스크 제거    -> KILLED
```

**M7/M8 라벨 주의(코드리뷰 정정)**: 실제 심은 변이는 "타이브레이크 체인을 버리고 절감액만으로
랭크"다. **리터럴 `dense→min/first` 변이는 죽지 않는다** — CLIENTNUM 유일성 하에서 복합 키에
동점이 없어 `dense`·`min`·`first`가 같은 `1..n`을 내기 때문이다(테스트 파일이 그렇게 명시한다).
초판 Debug Log가 이 둘을 `method="min"/"first"`로 적어 **AD-12의 dense 조항이 변이 커버된 것처럼**
읽히게 했다. M9/M10의 15.0 vs 13.0은 **커밋된 테스트가 아니라 픽스처 `[10, 5, −2]` 위의 변이 실행**
결과라, 재현하려면 그 픽스처에 변이를 다시 심어야 한다(감사 경로를 코드 주석에 명시).

**M5는 테스트 공백이 아니라 등가 변이다.** 1차 정렬 키가 기대절감액 자신이므로 상위
`positive_candidates` 순위는 **정확히** 양수 고객이고, `selected_count = min(예산, 양수인원)`이
이미 음수를 배제한다. 따라서 `& is_positive`를 지워도 **관측 가능한 차이가 없다** — 죽일 수 있는
테스트가 존재하지 않는다. 3-2가 "확률·가치 swap은 변이가 아니다(곱셈 교환법칙)"로 목록에서 뺀 것과
같은 성격이라, 체크박스에 KILL을 찍는 대신 T4 항목을 정정했다.

**그럼에도 마스크는 남겼고, 그 값을 실측했다** — `min()`을 제거한 상태에서:
```
마스크 유지 -> 선택 [10.0, 5.0]        총합 15.0   (양수만)
마스크 제거 -> 선택 [10.0, 5.0, -2.0]  총합 13.0   (음수까지 구매)
```
즉 마스크는 `selected_count`가 틀렸을 때의 다중 방어다. 등가성이 성립하는 **불변식 자체**를
`test_every_negative_saving_ranks_below_every_positive_one`이 직접 고정한다 — 1차 키가 바뀌면 이
테스트가 먼저 깨지고 마스크가 비로소 실하중을 받는다.

**AD-9 가드 확장**: `_CAMPAIGN_ORDER`에 `priority`를 넣어
`("matrix","simulate","priority","sensitivity")`로 만들었다. 실스캔 **2 → 3**(스토리 예고와 일치),
위반 0. `test_repo_structure.py`의 설명 문자열도 함께 고쳤다. **스파인 AD-9 Rule은 아직 3단계를
적고 있다** — 가드가 문서를 앞선 상태이며 `deferred-work.md`에 개정 사안으로 기록했다.

**실데이터 실행**(`scratch/run_priority_3_3.py`)이 `rows aligned by POSITION: False`를 찍는다 —
함정 4가 실물이라는 것을 매 실행이 재확인한다. 조인은 `CLIENTNUM`.

### Completion Notes List

- **AC1 충족**: `target_priority()`가 `expected_saving` 내림차순 → `customer_value` 내림차순 →
  `CLIENTNUM` 오름차순의 복합 키로 **1..n 전단사**를 만든다(실데이터 min 1 / max 10,127 / distinct
  10,127). 재실행 안정성은 입력 행 순서를 섞어 검증했다 — 순위가 **위치가 아니라 키에서** 나온다.
- **AC2 충족**: `random_baseline()`이 `RANDOM_SEED` 고정 + **200회 추출 평균**을 내고
  `multiple_over_random()`이 배수를 낸다. 배수는 x17.27(100명) → x1.18(양수 전원)의 **곡선**이며
  리포트가 단일 배수 인용을 금지한다.
- **AC3 충족**: `quadrant_official`은 `assign_quadrant()`에서 받아 **집계에만** 썼다. `priority.py`는
  `matrix`를 import하지 않고 분면 개념 자체를 모른다 — 자체 컷 0건.
- **AC4 충족**: `binding_constraint`가 다섯 가지를 구분한다 — `zero_budget` ·
  `no_positive_candidates` · `budget` · `positivity` · `budget_and_positivity`. **"아무도 안 뽑혔다"가
  한 사실이 아니라 두 사실**임을 `test_the_two_empty_outcomes_are_distinguishable`이 고정한다.
  빈 선택에서도 순위 컬럼은 전원분 그대로 반환된다(조용한 빈 프레임 금지).
- **AC5 충족(3-2 인계 종결)**: D1대로 순위는 10,127명 전원, 선택은 예산 AND 양수. **실측이 D1을
  뒷받침한다** — 예산 50,635(전원분)에서 선택은 8,587명에서 멈추고 총합 1,456,900을 얻는 반면,
  예산만으로 자르면 1,454,088로 **2,812 낮다**(x1.18 vs x1.00). 두 방침은 8,587명까지 완전히 동일하다.
- **AC6 충족(3-2 인계 종결)**: 값 축 음수를 `ValueError`로 거부하며, 메시지가 범위가 아니라 **이유**
  (단조성 역전, 실측 −35.0 vs −275.0)를 말한다 — 호출자가 clip으로 때우지 않도록. `value.py`는
  **한 글자도 고치지 않았다**(D2).
- **AC7 충족(1-2 인계 종결)**: 비단조 재가중 2종을 KILL하고, **잡지 못하는 것도 테스트로 못박았다** —
  `log1p` 같은 단조 재가중은 순위를 못 바꾸므로 이 모듈이 볼 수 없다. 3-2의 sentinel 값 비교 방식을
  그대로 가져왔다면 통과했을 것이고, 그게 create-story가 경고한 지점이다.

**AD-12의 "dense"는 이 조건 하에서 무력하다(발견)**: `CLIENTNUM`이 유일하면 복합 키에 중복이 없어
`dense`·`min`·`first`가 전부 같은 `1..n`을 낸다. 그래서 구현은 **전순서상의 위치**로 순위를 만들고
모듈 docstring이 그 등가성을 명시한다 — "dense를 골랐다"는 선택이 있었던 것처럼 읽히지 않도록.
**AD-12 문구가 실제로 사주는 것은 dense가 아니라 전순서 자체**이고, 그것이 Tableau 정렬 안정성이라는
AD-12의 목적과 정확히 일치한다.

**M5는 등가 변이다 — "전부 KILL"을 주장하지 않았다**: 양수 마스크는 제거해도 관측 가능한 차이가
없다(1차 키가 절감액이라 `min()`이 이미 음수를 배제). 3-2가 swap 변이를 목록에서 뺀 것과 같은
성격이라 T4 문구를 정정했다. 마스크는 **다중 방어**로 남겼고 그 값을 M9/M10으로 실측했다(15.0 vs 13.0).

**사전조사 수치와 실행 결과의 차이를 정정했다**: create-story 함정 1 표는 **예산만으로 자르는**
정책의 곡선이라 10,127명에서 x1.00으로 떨어진다. **D1을 구현한 실제 곡선은 x1.18에서 바닥을 친다** —
정책이 음수 구간을 사지 않기 때문이다. 리포트 §②가 두 곡선을 나란히 싣는다. 무작위 평균값도
소폭 다르다(예: 100명 14,613.6 vs 사전조사 14,190) — 추출 스트림이 다르며 리포트는 구현이 낸 값을 싣는다.

**구조 가드가 스파인 문서를 앞섰다**: `_CAMPAIGN_ORDER`를 4단계로 넓혀 실스캔 2 → 3이 됐지만
ARCHITECTURE-SPINE AD-9 Rule은 아직 3단계를 열거한다. 스토리 범위 밖이라 고치지 않고
`deferred-work.md`에 개정 사안으로 남겼다.

**범위를 지켰다**: 산식 재구현 없음(`expected_saving` 소비), 자체 분면 컷 없음, 민감도·ROI 등고선
없음, 파이프라인 단계 없음(`scratch/`는 세션 산출물), `value.py` 무변경.

**테스트**: 376 → **421 passed**, 회귀 0.

### File List

- `crm/campaign/priority.py` — NEW (`target_priority`, `select_within_budget`, `random_baseline`,
  `multiple_over_random`, `BudgetSelection`, `RandomBaseline`, 컬럼·제약 상수)
- `tests/campaign/test_priority.py` — NEW (45건)
- `crm/config.py` — UPDATE (`RANDOM_BASELINE_DRAWS = 200`, `# source: 규약`)
- `tests/structure/checkers.py` — UPDATE (`_CAMPAIGN_ORDER`에 `priority` 추가)
- `tests/structure/test_repo_structure.py` — UPDATE (AD-9 설명 문자열)
- `docs/implementation-artifacts/priority-report-3-3.md` — NEW
- `docs/implementation-artifacts/structure-guard-coverage.md` — UPDATE (테스트가 재생성, campaign order 2 → 3)
- `docs/implementation-artifacts/deferred-work.md` — UPDATE (3-2 인계 3건·1-2 인계 1건 해소 표기, 신규 3건)
- `docs/implementation-artifacts/sprint-status.yaml` — UPDATE
- `scratch/run_priority_3_3.py` — NEW (세션 산출물, 파이프라인 단계 아님)
- `docs/implementation-artifacts/3-3-budget-constrained-target-priority.md` — UPDATE (이 파일)

## Change Log

| 날짜 | 변경 |
|---|---|
| 2026-07-22 | 스토리 3-3 create-story. 3-2 인계 미결 2건을 **결정으로 닫음**(D1 음수는 순위 부여·예산 선택 제외 / D2 비음수 검사는 3-3 경계에서 fail-fast, `value.py` 불변). 3-2가 남긴 전제 하나를 실측으로 정정 — 음수 포함 여부는 양수의 dense rank를 바꾸지 않는다. 함정 5건 실측 기록: 배수가 예산 따라 x17.79→x1.00 수렴 · 실데이터 동점 0건(동점 규칙은 합성 픽스처로만 검증 가능) · 단일 seed 기준선이 배수를 x7.76~x14.09로 흔듦 · **두 parquet 행 오정렬이 모든 가드를 통과하며 총합을 37% 부풀림(사전조사가 실제로 밟음)** · 1인 1회 가정 유지 근거. 1-2 인계 항목(3-3 몫)이 "민감도"로 잘못 배정돼 있던 것을 재해석해 AC7로 세움 — 실제 소비 지점은 `customer_value` 2차 정렬 키이고, 단조 변환이 sentinel 값 비교를 조용히 통과하므로 **동점 그룹 내 순서**로 검증해야 한다. Status → ready-for-dev. 기준선 1b068da / 376 passed |
| 2026-07-22 | 스토리 3-3 구현: `target_priority()`·`select_within_budget()`·`random_baseline()`·`multiple_over_random()`. D1·D2를 코드로 확정하고 3-2 인계 3건·1-2 인계 1건을 **해소**로 승격. **실측이 D1을 뒷받침**(예산 전원분에서 8,587명 정지 → 1,456,900 vs 예산만 자르기 1,454,088, 2,812 차이). 발견 3건: **AD-12의 "dense"는 CLIENTNUM 유일성 하에서 무력**(dense/min/first 동일) · **양수 마스크는 등가 변이라 KILL 불가**(다중 방어로 유지, M9/M10으로 실효 실측) · **배수 곡선은 x1.00이 아니라 x1.18에서 바닥**(정책이 음수를 안 사므로 — 사전조사 표는 예산만 자르는 정책의 곡선이었다). AD-9 가드를 4단계로 확장(실스캔 2 → 3), 스파인 문구 갱신은 deferred. 376 → 421 passed. Status → review |
| 2026-07-22 | 코드리뷰(3레이어 병렬). Auditor가 리포트·스토리 측정 수치를 **전건 독립 재실행해 재현 확인**(수치 오기 0). 결함은 전부 가드·주장. **patch 20건 적용 + API 변경 5건은 파티 보류**. 적용: `budget//cost` 부동소수 floor를 tolerance 방식으로(3-4가 비이진 cost 스윕 시 1명 덜 사던 버그) · 몫 overflow 가드 · `binding_constraint` 세 사실 분리(`BUDGET_BELOW_ONE_CONTACT` 신설) · `selected` dtype을 bool로 고정 · `random_baseline` 타입 검사 + 전인원 추출 시 구조적 0 산포 단락 · docstring/config 4곳의 재현 불가 수치(x1.00·x7.76~x14.09) 정정 · 테스트 결함 6건(플레이크 2·도달불가 1·미테스트 BOTH_BOUND·dtype·내부정합) · **AC3 구조 가드 신설**(`find_priority_selfcut_violations` — priority.py의 quantile/percentile/median 호출 금지, self-check 4건) · T1·T4·Debug Log·리포트 §①·"5줄" 문구 정정. 421 → **441 passed**, 회귀 0. 보류 5건(D1 계약 좁히기 + `multiple_over_random`/`random_baseline` 시그니처 3종 + budget=0 메시지)은 파티 논의 후 결정. Status → in-progress |
| 2026-07-22 | 보류 5건 종결(파티 결정, daria 승인). **painpoint 재정의가 판정 기준을 바꿨다** — crm은 재무 워싱 스크리너의 리허설이고, item 3(x99)은 스크리너 헤드라인 무결성의 예행이라 nit → 필수로 승격. **적용**: `multiple_over_random(selection: BudgetSelection, baseline: RandomBaseline)` 시그니처 변경(유이 통합안) — 분자를 객체에서 직접 읽고 `n_contacts != selected_count` 거부, x99가 표현 불가능해짐. item 2는 구조적으로 함께 해소(분자가 검증된 선택의 총합이라 유한·비음수 보장). **4-1 인계 3건**: 함정 4 계약 좁히기(여기서 좁히면 done인 3-2가 비순응) · `random_baseline` 모집단 정체성 · `budget=0` 메시지. 441 → **443 passed**, 회귀 0, 리포트 수치 불변. Status → done |
