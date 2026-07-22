---
baseline_commit: 504e5e6
baseline_passed: 338
---

# Story 3.2: 캠페인 기대 절감액 시뮬레이터

Status: done

## Story

As a 마케팅 의사결정자,
I want 고객별 기대 절감액을 산식으로 계산하기를,
So that 캠페인의 가치를 금액 개념으로 비교할 수 있다.

## Acceptance Criteria

**AC1** — **Given** 이탈확률·고객가치·가정 파라미터가 주어졌을 때
**When** `crm/campaign/simulate.py`가 계산하면
**Then** 기대 절감액 = `P(이탈) × 고객가치 × 리텐션 성공률 − 캠페인 비용`이 구현된다(FR12)
**And** 성공률·비용의 **기본값이 `crm/config.py` 상수를 참조**하며 리터럴로 재선언되지 않는다(AD-4)

**AC2** — **Given** 산식 테스트를 작성할 때
**When** pytest를 실행하면
**Then** 테스트는 **행동 기반**이다 — 동일 공식을 재구현해 비교하지 않고, 파라미터 단조성(성공률↑ → 절감액↑, 비용↑ → 절감액↓)과 **부호 전환 지점**으로 검증한다(NFR6)

**AC3** — **Given** 파라미터를 바꿔가며 실행해야 할 때
**When** 스윕을 수행하면
**Then** 설정 파일이 아니라 **함수 인자**로 주입된다(AD-4)

**AC4** — **Given** 통화 표기가 필요할 때
**When** 산출물을 확인하면
**Then** BankChurners **무단위** 그대로 표기되고 임의 통화 기호·환산이 없다(NFR3, P1 3-4 교훈)

### AC 파생 — 이 스토리가 함께 닫는 계약 (필수)

**AC5 (확률 컬럼 계약 — 3-0이 만든 분리를 지킨다)** — 산식의 `P(이탈)` 입력은
**`churn_prob_calibrated`**여야 한다. `churn_score`(raw OOF, 순위 전용)를 넣으면 금액이 부푼다
(실측 **+19.0%**). 이 계약이 **테스트로 고정**되어야 한다.

**AC6 (AD-11 재가중 금지 계약 테스트 — 1-2에서 인계된 미결)** — `deferred-work.md`의 1-2 항목이
*"3-2: 기대절감액 공식의 value 입력이 `customer_value()` 출력인가"*를 **소비자별 계약 테스트로**
검증하라고 남겼다. 현 AD-11 가드는 `value = customer_value(df) * 0.02` 같은 재가중을 잡지 못한다.
**sentinel Series를 monkeypatch해 그 값이 그대로 전달되는지** 검증한다.

## Tasks / Subtasks

- [x] **T1** `crm/campaign/simulate.py::expected_saving()` 구현 (AC1·AC3·AC5)
  - [x] 순수 함수. 기본값은 `crm.config` 상수 참조, 리터럴 재선언 금지
  - [x] 파라미터는 **함수 인자**로 받는다(3-4가 이 함수를 반복 호출한다)
  - [x] `crm.campaign.sensitivity` import 금지(AD-9 방향), **예산·우선순위 개념 없음**(3-3 소관)
  - [x] 확률 입력이 `churn_prob_calibrated`임을 시그니처·docstring이 못박는다
- [x] **T2** 테스트 — 행동 기반 (AC2)
  - [x] **단조성**: 성공률↑ → 절감액↑ / 비용↑ → 절감액↓ / 확률↑ → 절감액↑ / 가치↑ → 절감액↑
  - [x] **부호 전환 지점**: `p × value = cost / rate`에서 0을 지난다(아래 실측 16.67)
  - [x] **하드코딩 oracle** 1건
  - [x] **변이**: 부호 반전·항 누락·비용을 더하기 → M1~M5 전부 KILL 확인. **확률과 가치 뒤바꿈은 변이가 아니다** — 곱셈은 교환법칙이 성립해 죽일 산술 변이가 없고, 잡는 것은 범위·이름 검증이다(초판은 이 항목에 KILL 확인으로 체크했으나 실제 실행 목록에 없었다 — 코드리뷰 지적)
  - [x] **동어반복 금지** — 같은 식을 다시 써서 비교하지 말 것
- [x] **T3** 계약 테스트 2종 (AC5·AC6)
  - [x] `churn_score`를 넣으면 금액이 달라짐을 실증(둘을 혼동할 수 없게)
  - [x] **sentinel monkeypatch**로 value 입력이 `customer_value()` 출력 그대로임을 검증
- [x] **T4** 실데이터 실행 + 리포트 (AC4)
  - [x] `docs/implementation-artifacts/savings-report-3-2.md`
  - [x] 분면별 절감액 분포, 부호 전환 경계, **가정 라벨링**(NFR1), 무단위 표기
  - [x] **아래 함정 1(총합 역전)을 리포트가 정면으로 다룰 것**
- [x] **T5** `deferred-work.md`·`sprint-status.yaml` 갱신

### Review Findings

코드리뷰 2026-07-22 (3레이어: Blind Hunter / Edge Case Hunter / Acceptance Auditor).
원시 30건 → 중복병합·실물검증 후 **decision 3 · patch 15 · defer 2 · dismiss 6**.
**전건 종결(2026-07-22)**: decision은 사용자 결정 — AC5 (a)이름 검사 · 음수 가치 (c)주장 축소 ·
`retention_rate` (a)엄격 부등호. 364 → **376 passed**, 회귀 0.
Auditor가 리포트 수치를 독립 재실행해 **전건 재현 확인**(84.8%·1,454,088·경계 16.6667·분면 4종·
평균·총합·3.70배·+19.0%·분면별 양수비율까지 소수점 단위 일치). **차단급 2건은 코드가 아니라 주장이다.**

- [x] [Review][Decision] **AC5가 충족되지 않았다 — 컬럼 계약이 강제되지도 테스트되지도 않는다** — 스토리가 "이 계약이 **테스트로 고정**되어야 한다"고 명시한 유일한 AC 파생 조항이다. 실증: `expected_saving(scored["churn_score"], val)` → **예외 없이 통과, 합계 1,730,042 (+19.0%)**. `_validate_axis`는 `[0,1]`만 보고 `Series.name`을 읽지 않으며 `churn_score`도 `[0,1]`이다. 내가 AC5 근거로 내세운 테스트 2건은 둘 다 계약을 지키지 않는다 — `test_the_docstring_names_the_calibrated_column`은 **문자열 존재 검사**(어떤 구현 변경으로도 깨지지 않고, 인자 이름이 Args 절에 반드시 등장하므로 첫 assert는 실패 불가능)이고, `test_the_calibrated_column_and_the_raw_score_give_different_money`는 **단조성 테스트의 재탕**(테스트 자신이 docstring에서 "always-true statement"라고 자백). 선택지: (a) `Series.name`이 있을 때 `churn_prob_calibrated`인지 검사 — 실측상 `sc["churn_score"].name == 'churn_score'`라 실효성 있음, 단 연산 후 name이 `None`이 되는 경우가 있어 "이름이 있을 때만" 검사하는 절충이 됨 (b) 프레임+컬럼명을 받는 얇은 래퍼를 4-1 경계에 둠 (c) 함수 수준 강제는 불가능하다고 인정하고 **AC5를 미충족으로 표기**한 뒤 강제 지점을 4-1로 이관. 근거: `crm/campaign/simulate.py:97` · `tests/campaign/test_simulate.py`
- [x] [Review][Decision] **음수 `customer_value`에서 이탈확률 단조성이 역전된다 — 3-3 랭킹 계약의 전제가 깨진다** — 실측: `value=-1000`일 때 `p=0.1 → -35.0`, `p=0.9 → -275.0`. **위험할수록 기대절감이 낮아진다.** 내가 모듈 docstring과 `test_a_higher_churn_probability_saves_more`에서 "3-3의 상위 N 접촉이 이 성질 위에 선다"고 못박은 바로 그 성질이다. `crm/segment/value.py`는 `Total_Trans_Amt`를 `astype(float)`로 반환할 뿐 **비음수를 보장하지 않으며**, `simulate.py`·`matrix.py` 둘 다 "value.py가 약속하지 않으므로 검사하지 않는다"고 명시해 계약상 도달 가능하다. 현 데이터에는 음수가 없지만 계약에는 있다. 선택지: (a) `value.py`에 비음수 계약을 명시하고 소비자 테스트로 고정(AD-11 소유권상 가장 정당) (b) `simulate`·`matrix` 양쪽 값 축에 `>= 0` 검증 추가 (c) 단조성 **주장을 좁힌다**("비음수 가치 하에서") — 코드 변경 0이지만 3-3이 그 전제를 확인할 책임을 진다
- [x] [Review][Decision] **`retention_rate=0.0`을 허용한다 — 이웃 모듈은 같은 성격의 퇴화점을 거부한다** — 실측: 전 고객이 정확히 `-cost` 상수가 되어 **랭킹 정보가 완전히 소멸**한다. 3-3의 "상위 N"은 전원 동점 상태에서 인덱스 순서로 잘리고 어떤 오류도 나지 않는다. `matrix.py:126-130`은 분위수에 `0.0 < q < 1.0` **엄격 부등호**를 쓰고 이유를 "축의 한쪽을 비운다"로 적었다. 현 `RETENTION_GRID` 최소값은 0.10이라 지금은 도달하지 않지만 3-4가 그리드를 넓히면 스윕 한 칸이 조용히 무의미해진다. 선택지: (a) `0.0 < rate <= 1.0`으로 좁혀 두 모듈 정책을 일치시킴 (b) 허용을 유지하되 docstring에 "랭킹 정보 소멸"을 명시
- [x] [Review][Patch] **`cost_per_contact`의 NaN/inf가 검증을 통과한다** — `nan < 0.0`도 `inf < 0.0`도 `False`. 실측: `cost=nan`이면 전 행이 NaN이고 **`result.sum()`은 pandas가 NaN을 skip해 `0.0`** — 리포트에 "총 기대절감 0"이 확신에 찬 숫자로 찍힌다. `cost=inf`면 전원 `-inf`. `retention_rate=nan`은 `not (0.0 <= nan <= 1.0)`이 True라 **우연히** 막힌다. 데이터 축에는 `_validate_axis`가 비유한값을 명시적으로 거부하면서 같은 산술에 들어가는 가정 파라미터에는 같은 기준을 적용하지 않았다. 3-4가 그리드를 계산으로 만들면(`cost/rate` 등) 바로 밟는 경로다 [crm/campaign/simulate.py:146-151]
- [x] [Review][Patch] **리포트의 "발견 1건"이 그 자체로 비용 가정의 산물인데 무조건 사실로 서술됐다** — 함정 4를 반박하는 절 안에서 똑같이 가정 의존적인 진술을 구조적 사실로 제시한 것. 그리드 스윕 실측: `cost=5.0`에서는 부호 전환이 이탈 수용 안에만 있지만 `cost=10.0`에서 **저비용 유지 27.9% · 관망 97.2%**로 경계가 세 분면을 가로지른다. Dev Record가 이를 "사전조사를 넘어선 발견"으로 승격한 것도 함께 정정 [savings-report-3-2.md] [3-2-campaign-savings-simulator.md Completion Notes]
- [x] [Review][Patch] **상단 「전체 분포」 블록의 84.8%에 가정 라벨이 없다** — 해설은 27행 아래 §②에 있는데, 발췌·스크린샷·요약 인용은 거의 언제나 상단 블록에서 뜯긴다. 함정 4가 막으라고 지시한 지점이 정확히 여기다 [savings-report-3-2.md 「전체 분포」]
- [x] [Review][Patch] **`deferred-work.md`의 음수 인원이 1명 틀렸다** — "51.8%가 음수다(1,539명)". 실측 **1,540명**(51.8344%). 백분율은 맞고 절대수만 어긋난다 — 백분율에서 역산하며 반올림한 흔적. Blind Hunter는 이 1명 차이를 "정확히 0인 고객"으로 추정했으나 **실측 `zero=0`으로 기각**됐다 [deferred-work.md 3-2 절]
- [x] [Review][Patch] **리포트가 존재하지 않는 계약 테스트를 근거로 인용한다** — "잡는 것은 인자 이름과 계약 테스트뿐이다(`test_the_calibrated_column_...`)". 그 테스트는 오선택을 잡지 못한다(위 D1). 테스트 자신은 자백해 뒀는데 리포트만 그 자백을 반영하지 않았다 [savings-report-3-2.md]
- [x] [Review][Patch] **Dev Record의 AC5 충족 주장이 코드가 뒷받침하지 않는다** — "문구의 존재를 테스트로 고정"은 스토리가 요구한 "계약을 고정"이 아니다 [3-2-campaign-savings-simulator.md Completion Notes]
- [x] [Review][Patch] **T2 체크박스가 수행하지 않은 검증에 `[x]`를 찍었다** — "변이: 부호 반전·항 누락·비용을 더하기·**확률과 가치 뒤바꿈** → 전부 KILL 확인"인데 실제 실행한 M1~M5에 뒤바꿈 변이가 없다. Debug Log에서 스스로 "산술로는 잡히지 않는다"고 적어놓고 체크박스는 KILL로 남겼다 [3-2-campaign-savings-simulator.md T2]
- [x] [Review][Patch] **`test_probability_and_value_are_not_interchangeable`의 docstring이 과대 주장** — "swap 변이를 죽인다"고 하지만 실제로는 **호출자 오용**을 잡을 뿐이고, 통과 이유가 전적으로 `pair_for_swap()`이 고른 값이 1을 넘기 때문이다. 가치가 `[0.3, 0.8]`인 고객만 있으면 침묵한다. 곱셈은 교환법칙이 성립하므로 죽일 산술 변이는 애초에 없다 [tests/campaign/test_simulate.py]
- [x] [Review][Patch] **검증 순서가 길이 불일치를 가린다 — 3-0에서 고친 결함의 반복** — `_validate_pair`가 축 검사 뒤에 있어, `prob` 1행(NaN) vs `value` 4행이면 "1 missing value(s)"로 보고되고 **인구 규모가 다르다는 사실 자체가 화면에 안 나온다**. `calibrate.py`에서 정확히 같은 것을 고쳐놓고 새 모듈에서 반복했다 [crm/campaign/simulate.py:191-194]
- [x] [Review][Patch] **dtype 무검증 — `datetime64` 값 축이 돈으로 통과한다** — 실측 `[94670207999995.0, ...]`(나노초 정수). 유한하고 NaN이 아니며 값 축엔 범위 검사가 없어 모든 가드를 빠져나간다. `bool`도 `True→1.0`으로 통과. `DataFrame`을 넘기면 `"The truth value of a Series is ambiguous"`라는 익명 예외, `object`+문자열이면 `"could not convert string to float"` — 둘 다 Raises 절에 없는 사유이고 어느 인자인지도 안 알려준다. `matrix.py`도 같은 코드다 [crm/campaign/simulate.py:79-97]
- [x] [Review][Patch] **`_VALUE_AXIS = "customer value"`(공백) 때문에 오류 메시지가 깨진다** — `"received 3 missing customer value value(s)"`. 실제 컬럼은 `customer_value`라 사용자가 grep할 수도 없다 [crm/campaign/simulate.py:73]
- [x] [Review][Patch] **범위 검사가 문자열 라벨로 분기한다** — `if axis_name == _PROB_AXIS`. swap 방어의 유일한 축이 문자열 상수 하나에 걸려 있고, 오타나 상수 변경 시 검사가 조용히 꺼진다. 불리언 파라미터로 명시하는 편이 맞다 [crm/campaign/simulate.py:103]
- [x] [Review][Patch] **인덱스 dtype 불일치가 통과한다** — `Index.equals`는 dtype을 무시하므로 `Int64` vs `Float64` 인덱스가 통과하고, 결과는 **확률 축 인덱스를 계승**한다(인자 순서가 결정). docstring "indexed exactly like the inputs"가 이 경우 참이 아니고, 4-1이 마트에 조인할 때 라벨 타입이 갈린다 [crm/campaign/simulate.py:117-123, 202]
- [x] [Review][Patch] **리포트가 "커밋·테스트된 함수가 만든 수치"라고 하지만 집계 경로가 커밋되지 않았다** — `expected_saving()`은 Series 2개를 받는 순수 함수이고, 분면 집계·합계·84.8%를 만든 코드는 스크래치에만 있다. 재현 가능성 주장이 근거 없이 서 있다. 리포에서 `expected_saving`을 호출하는 커밋된 코드는 테스트뿐 [savings-report-3-2.md 머리말]
- [x] [Review][Patch] **`deferred-work.md`의 1-2 인계 항목이 해소·잔존 어느 쪽으로도 표기되지 않았다** — 스토리 AC6이 이 항목을 닫는다고 선언했는데 새 3-2 절만 추가됐다. 3-0에서 지적받아 고친 것과 같은 누락 [deferred-work.md 1-2 절]
- [x] [Review][Patch] **스토리 기준선 갱신 블록의 `spearman = 1.000000` 논거가 성립하지 않는다** — 스피어만 1.0은 **순위 보존**만 말한다. 어떤 단조 재보정도 스피어만을 유지하면서 모든 확률값을 바꿀 수 있는데, 이 모듈의 존재 이유가 "순위가 아니라 크기"다. 값 자체의 동일성을 제시해야 한다 [3-2-campaign-savings-simulator.md 기준선 갱신]
- [x] [Review][Patch] **테스트 위생 3건** — `pair` 픽스처를 받아놓고 안 쓰는 테스트 2건, 케이스가 하나뿐인 `@pytest.mark.parametrize`, sentinel 테스트가 `p=1.0`이라 확률 항 자체는 검증하지 못함(Auditor가 `value*0.02`·`np.log1p` 모두 KILL됨을 실증했으므로 AC6 자체는 충족 — 강화만 필요) [tests/campaign/test_simulate.py]
- [x] [Review][Defer] 반환 Series의 메모리 독립성이 계약으로 고정되지 않음 [tests/campaign/test_simulate.py] — deferred, 현 구현은 안전하나 4-1이 in-place 수정할 때를 대비한 계약이 없다
- [x] [Review][Defer] 모듈 docstring·리포트의 "확률 0.0043만 넘으면 양수" 일반화 [crm/campaign/simulate.py] — deferred, 정확히 중앙값 가치를 가진 고객 1명에 대한 진술인데 모집단 통계(84.8%)의 근거로 제시된다


## Dev Notes

### 🚨 함정 1 — 총합이 2×2 서사를 뒤집는 것처럼 보인다

실측(기본 가정 `rate=0.30`, `cost=5.0`):

| 분면 | n | 평균 절감액 | **총합** |
|---|---|---|---|
| Save 우선 | 443 | **1,415.00** | 626,845 |
| 관망 | 2,089 | 382.81 | **799,683** |
| 저비용 유지 | 4,624 | 6.14 | 28,398 |
| 이탈 수용 | 2,971 | −0.28 | −838 |

**관망의 총합이 Save 우선보다 크다.** 인원이 4.7배이기 때문이다. 이걸 그대로 실으면 독자가
*"그럼 2×2가 틀린 것 아닌가"*로 읽는다.

**정확한 해석**: 예산 제약 하에서 의미 있는 것은 **1인당 기대 절감액**이고, Save 우선이 관망의
**3.7배**다. 총합은 "그 분면 전원을 접촉했을 때"의 값이라 예산이 무한할 때만 의미가 있다.
**우선순위는 분면이 아니라 개인 단위로 매겨진다** — 그게 3-3(`target_priority`)의 일이다.

리포트가 이 구분을 **명시적으로** 다루지 않으면, 3-3이 나오기 전까지 문서가 스스로를 반박하는
상태로 남는다. 회고에서 지적된 "정책 근거로 과잉 해석" 계열의 함정이다.

### 🚨 함정 2 — 확률 컬럼을 잘못 고르면 조용히 19% 부푼다

3-0이 컬럼을 둘로 나눴다:

```
churn_score            raw OOF, 순위 전용   <- 3-1이 쓴다
churn_prob_calibrated  Platt 보정, 확률 전용 <- 3-2가 써야 한다
```

**실측**: `churn_score`를 산식에 넣으면 총합이 **1,730,042 (+19.0%)**로 부푼다. 둘 다 `[0,1]`
범위이고 컬럼명만 다르므로 **타입 시스템도 테스트도 자동으로는 잡지 못한다.** AC5가 이 계약을
테스트로 고정할 것을 요구한다.

### 🚨 함정 3 — AD-11 재가중 금지는 현 가드가 못 잡는다 (1-2 인계)

`deferred-work.md`의 1-2 항목이 명시적으로 남긴 숙제다:

> *다음은 원천 컬럼을 직접 읽지 않으므로 현 가드를 통과하지만, AD-11이 금지하는 재가중일 수 있다.*
> ```python
> value = customer_value(df) * 0.02
> value = np.log1p(customer_value(df))
> ```
> *소비자별 계약 테스트가 적절하다 — sentinel Series를 monkeypatch해 각 소비자가 그 값을 그대로
> 전달받는지 검증하는 방식.* **3-2: 기대절감액 공식의 value 입력이 `customer_value()` 출력인가**

여기서 유혹이 실재한다 — 비용 5.0과 가치 3,899가 스케일이 안 맞아 보여서 **가치를 정규화하고
싶어진다.** 그러면 금액이 금액이 아니게 되고 3-3·4-1이 전부 오염된다. **스케일 차이는 문제가
아니다**(무단위 규약).

### 🚨 함정 4 — "84.8%가 양수"는 가정의 산물이지 발견이 아니다

실측: 기본 가정에서 **8,587 / 10,127 (84.8%)**의 기대 절감액이 양수다. 부호 전환 경계는
`p × value = cost / rate = 16.67`이고, 가치 중앙값이 3,899이므로 **확률이 0.0043만 넘으면 양수**가
된다. 즉 이 84.8%는 **`cost=5.0`이라는 가정이 만든 숫자**다.

리포트가 이걸 *"거의 모든 고객에게 캠페인이 이득"*으로 읽히게 쓰면 안 된다. **비용 가정이
바뀌면 결론이 뒤집히는 구간**을 답하는 것은 3-4(CAP-7)의 일이고, 3-2는 **그 입력을 만들 뿐**이다.
`COST_GRID`가 `(1.0, 2.5, 5.0, 10.0, 20.0)`이라 3-4가 쓸어볼 범위는 이미 정해져 있다.

### 🚨 함정 5 — 액션 후보는 SPEC 예시가 아니라 실측 매핑에서 (회고 A6)

기대 절감액이 "무엇을 제안할 것인가"로 이어질 때, **SPEC CAP-3의 예시를 그대로 쓰지 말 것.**
*"한도 불만형 → 한도 상향"*은 1-7 실측에서 **부정됐다**(이용률이 낮을수록 위험, r=−0.64).
출처는 `churn-drivers-actions-1-7.md`의 실측 매핑이다. 회고 액션 A6이 이것을 요구한다.

### 이 스토리가 만들지 않는 것 (범위 경계)

- **`target_priority` 없음** — 3-3 소관(AD-12). dense rank·동점 처리·예산 컷 전부 그쪽이다.
- **예산 개념 없음** — 함수는 "이 고객 한 명을 접촉하면 얼마"만 답한다.
- **ROI 등고선 없음** — 3-4 소관. 단 3-4가 **이 함수를 파라미터만 바꿔 반복 호출**할 수 있도록
  인자 설계를 열어둘 것(AD-9: 산식 재구현 금지).
- **파이프라인 단계 없음** — 순수 함수. 공식 수치의 자리는 4-1 마트 + 4-3 탭이고 이 리포트는
  **세션 산출물**이다(1-2 M3 판정, sprint-status 헤더 M2).
- **분면 판정 없음** — `quadrant_official`을 **소비**만 한다. 자체 컷 금지(AD-12).

### 물려받은 것 (재사용, 재발명 금지)

- **`crm/config.py` 상수**: `RETENTION_SUCCESS_RATE=0.30`, `COST_PER_CONTACT=5.0`,
  `RETENTION_GRID`, `COST_GRID`. import 시점에 **대표값이 그리드 위에 있음이 검증**된다(AD-4).
  이 검증은 3-4의 결론이 항상 민감도 곡선 위에 있도록 보장한다 — 건드리지 말 것.
- **`QuadrantAssignment`**(3-1): `labels`·`thresholds`·`rule`·`population_size`를 한 계산에서
  받는다. 분면이 필요하면 이걸 쓰고 임계값을 다시 구하지 말 것.
- **검증 패턴**(3-1 외부 리뷰): 빈 입력·NaN·inf·범위 이탈·중복 인덱스·인덱스 불일치를
  fail-fast로. `matrix.py::_validate_axis`/`_validate_pair`가 참고 구현이다.
- **동어반복 회피·성질 기반·변이 테스트**, ASCII 런타임 문자열, 순수 함수.

### 실측 사전조사 (2026-07-22, 기준 `3b32749`)

**dev가 코드로 재확인할 것.**

```
가정: RETENTION_SUCCESS_RATE=0.30, COST_PER_CONTACT=5.0  (둘 다 [가정], 실측 아님)
기대절감액 > 0 : 8,587 / 10,127 (84.8%)
합계 1,454,088 | 중앙값 2.83 | 최대 2,932.3 | 최소 -3.25
부호 전환 경계: p x value = cost / rate = 16.67
churn_score(미보정)를 쓸 경우: 합계 1,730,042 (+19.0% 과대)
```

분면별은 함정 1의 표 참조.

> **기준선 갱신 (2026-07-22, 3-0 코드리뷰 종결 후)**: `3b32749 / 332` → **`504e5e6 / 338`**.
> 위 실측 수치 자체는 **모두 유효하다** — 리뷰가 바꾼 것은 가드와 문서뿐이고 `churn_prob_calibrated`
> 값은 이동하지 않았다(`spearman(churn_score, churn_prob_calibrated) = 1.000000`, 평균 0.1607 불변).
> 3-2에 영향 있는 변경 두 가지:
> - `fit_calibrator`가 계수 부호·인덱스 정렬·라벨 유한성에 **fail-fast**한다. 보정 확률을 다시 만들
>   일은 없지만, 이 함수를 호출하는 코드를 쓴다면 계약이 좁아졌다는 것을 알 것.
> - AD-5가 2차 개정됐다 — 보증 범위가 "동일 학습 **실행(run)**"이고 `churn_score`는 "그 아티팩트의
>   **OOF 형제**"다. 산식 docstring이 AD-5를 인용한다면 이 문구를 쓸 것.
> `C=1e10`(Platt 무정규화)은 **deferred이며 3-2가 기준선을 고정한 뒤에는 더 비싸진다** — 이 스토리가
> 기대절감액 수치를 리포트에 실으면 그 수치가 `C=1.0` 위에 서게 된다(`deferred-work.md` 3-0 절).

### Testing Standards

- `.venv/Scripts/python.exe -m pytest` — 현 기준선 **338 passed**, 회귀 0
- 성질 + 하드코딩 oracle + 변이 테스트, 실데이터 실행 DoD(conventions 3항)
- **문서가 테스트를 앞서지도 뒤처지지도 않기** — 리포트 수치가 바뀌면 갱신 대상 문서를 함께 확인
  (회고 A3, 3-0이 첫 적용 사례)

### Project Structure Notes

```
crm/campaign/simulate.py                              # NEW - expected_saving() (순수, 예산 무지)
tests/campaign/test_simulate.py                       # NEW - 단조성·부호전환·oracle·변이·계약 2종
docs/implementation-artifacts/savings-report-3-2.md   # NEW - 분포·경계·가정 라벨링
docs/implementation-artifacts/structure-guard-coverage.md  # UPDATE - 재생성(campaign order 2건으로)
docs/implementation-artifacts/deferred-work.md             # UPDATE
```

> `AD-9 campaign order` 가드의 실스캔이 **1 → 2**로 늘어나는지 확인할 것(3-1이 1로 만들었다).

### 환경 실측 (2026-07-22)

```
HEAD 504e5e6 | 338 passed | artifact_id 9e1a4d71800f (8피처, OOF + Platt)
churn_score mean 0.1946 / churn_prob_calibrated mean 0.1607 (= 실제 이탈률)
customer_value median 3899.0 | 분면 443/2089/4624/2971
```

### References

- [Source: docs/planning-artifacts/epics.md#Story 3.2] — AC 원문(FR12, AD-4, NFR6, NFR3)
- [Source: .../ARCHITECTURE-SPINE.md#AD-9] — `matrix -> simulate -> sensitivity` 단방향, 산식 재구현 금지
- [Source: .../ARCHITECTURE-SPINE.md#AD-4] — 가정 파라미터 단일 출처, 대표값의 그리드 포함 검증
- [Source: .../ARCHITECTURE-SPINE.md#AD-5] — 컬럼 분리(2026-07-22 개정): 금액에는 `churn_prob_calibrated`
- [Source: .../ARCHITECTURE-SPINE.md#AD-11] — `customer_value` 소비·재가중 금지
- [Source: .../ARCHITECTURE-SPINE.md#AD-12] — `quadrant_official` 소비, 자체 컷 금지
- [Source: docs/implementation-artifacts/deferred-work.md#1-2] — 3-2 계약 테스트 숙제(sentinel monkeypatch)
- [Source: docs/implementation-artifacts/deferred-work.md#A2 결정] — 투트랙 컬럼의 근거
- [Source: docs/implementation-artifacts/3-0-oof-scores-platt-calibration.md] — 보정 계약
- [Source: docs/implementation-artifacts/quadrant-report-3-1.md] — 분면 인원·정책 가설
- [Source: docs/implementation-artifacts/churn-drivers-actions-1-7.md] — 액션 후보의 유일한 출처(A6)
- [Source: docs/implementation-artifacts/epic-1-retro-2026-07-22.md] — A3·A6
- [Source: 실측 2026-07-22] — 절감액 분포·부호 전환·미보정 대비 +19.0%

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (bmad-dev-story)

### Debug Log References

**기준선**: HEAD `504e5e6`, 338 passed.

**RED**: `tests/campaign/test_simulate.py` 선작성 → `ModuleNotFoundError: crm.campaign.simulate`.

**변이 테스트를 실제로 돌렸다** — 스토리가 요구한 것은 "변이 테스트 작성"이 아니라 "전부 KILL 확인"
이므로, 산식 한 줄을 실제로 바꿔가며 5종을 검증했다:

```
M1 부호 전체 반전    -> KILLED (9건 실패)
M2 rate 항 누락      -> KILLED (5건)
M3 비용을 더하기     -> KILLED (5건)
M4 rate를 곱셈->덧셈 -> KILLED (5건)
M5 cost 항 누락      -> KILLED (5건)
```

첫 시도에서 하니스가 상대경로로 인터프리터를 못 찾아 중단됐고, **M1 변이가 소스에 남은 채로
멈췄다.** 절대경로로 고쳐 재실행하고 원본 복원을 확인했다(200행). 변이 테스트는 소스를 건드리므로
`finally` 복원이 필수라는 것을 실물로 배웠다.

**확률/가치 뒤바꿈 변이**는 산술로는 잡히지 않는다(곱셈은 교환법칙이 성립한다). 잡는 것은 **범위
계약**이다 — 확률은 `[0, 1]`이고 가치는 아니므로 검증에서 걸린다. 테스트 docstring에 이 추론을
남겼다.

**구조 가드**: `AD-9 campaign order` 실스캔 **1 → 2**(스토리 예고와 일치). 이 커버리지 문서는
`tests/structure/test_repo_structure.py`가 재생성한다 — 수동 편집 대상이 아니다.

### Completion Notes List

- **AC1 충족**: `expected_saving()`이 `P(이탈) × 고객가치 × 성공률 − 비용`을 구현한다. 기본값은
  `crm.config`의 `RETENTION_SUCCESS_RATE`·`COST_PER_CONTACT`를 **참조**하며 리터럴 재선언이 없다.
  `test_the_defaults_come_from_config`가 명시 인자 호출과 기본 호출의 동일성으로 이를 고정한다.
- **AC2 충족**: 동어반복 없음 — 산식을 테스트 안에서 다시 쓰지 않았다. 단조성 4종(성공률·비용·확률·
  가치), 부호 전환 **교차**(경계 위/아래 각 1명), 손계산 oracle 1건(p=0.40 · value=1000 · rate=0.25 ·
  cost=30 → **70.0**), 변이 5종 KILL.
- **AC3 충족**: 성공률·비용은 **키워드 인자**다. 3-4가 그리드 점을 넘겨 반복 호출한다.
  `_validate_assumptions`가 호출부 값도 검증한다 — config의 import 시점 가드는 기본값만 보고
  스윕이 만든 값은 못 본다.
- **AC4 충족**: 통화 기호·환산 없음. 리포트가 무단위임을 규약으로 명시(NFR3).
- **AC5 — 초판 미충족, 코드리뷰 후 충족**: 초판은 인자 이름과 docstring만으로 계약을 주장했고
  `test_the_docstring_names_the_calibrated_column`을 근거로 들었다. **그 테스트는 문자열 존재
  검사라 어떤 구현 변경으로도 깨지지 않는다.** 리뷰가 실증했다 — `expected_saving(sc["churn_score"],
  val)`이 예외 없이 통과해 합계 `1,730,042`(**+19.0%**)를 냈다. 지금은
  `_validate_probability_column`이 **Series 이름을 검사**해 거부한다(실데이터로 확인).
  **가드는 의도적으로 부분적이다** — `name=None`인 가공된 Series는 통과시킨다. 3-4 스윕 같은 정당한
  호출을 막지 않기 위해서이고, 그 한계를 `test_an_unnamed_probability_series_is_accepted`가
  테스트로 못박는다.
- **AC6 충족(1-2 인계)**: sentinel Series로 가치가 **그대로 통과**함을 검증
  (`rate=1.0`·`cost=0.0`·`p=1.0`이면 출력이 sentinel과 동일해야 한다). 반대 방향 테스트도 함께 두어
  재가중이 무해하지 않음을 고정했다.

**실측이 스토리 사전조사와 전건 일치**: 양수 8,587/10,127(84.8%) · 합계 1,454,088 · 중앙값 2.83 ·
최대 2,932.3 · 최소 −3.25 · 경계 16.6667 · 분면 443/2089/4624/2971 · 1인당 Save우선/관망 3.70배.

**초판이 "발견"이라 부른 것은 발견이 아니었다**: "부호 전환이 분면 하나 안에서만 일어난다"를
구조적 사실로 적었으나, `COST_GRID`를 쓸어보니 **`비용 = 10.0`에서 경계가 저비용 유지(27.9%)와
관망(97.2%)을 가로지른다.** 즉 84.8%가 가정의 산물이라고 반박하는 바로 그 절에서, 똑같이 가정
의존적인 진술을 무조건적 사실로 제시했다 — 함정 4가 경고한 패턴을 반박문 안에서 반복한 것이다.
리포트는 이제 그리드 표를 싣고 `[가정 cost=5.0 기준]`으로 라벨링한다.

**범위를 지켰다**: `target_priority` 없음, 예산 개념 없음, ROI 등고선 없음, 파이프라인 단계 없음,
자체 분면 컷 없음. `assign_quadrant`은 리포트 집계에서만 **소비**했다.

**테스트**: 338 → 364 → **376 passed** (코드리뷰 반영 +12), 회귀 0.

### File List

- `crm/campaign/simulate.py` — NEW (`expected_saving`, `SAVING_COLUMN`)
- `tests/campaign/test_simulate.py` — NEW (26건)
- `docs/implementation-artifacts/savings-report-3-2.md` — NEW
- `docs/implementation-artifacts/structure-guard-coverage.md` — UPDATE (테스트가 재생성, campaign order 1 → 2)
- `docs/implementation-artifacts/deferred-work.md` — UPDATE (3-2 절 신설 3건)
- `docs/implementation-artifacts/sprint-status.yaml` — UPDATE
- `docs/implementation-artifacts/3-2-campaign-savings-simulator.md` — UPDATE (이 파일)

## Change Log

| 날짜 | 변경 |
|---|---|
| 2026-07-22 | 코드리뷰 전건 종결 확인 후 Status → done (376 passed, 회귀 0). 다음: 3-3 create-story |
| 2026-07-22 | 코드리뷰(3레이어) 반영: **AC5가 초판에서 미충족이었음이 실증됨**(`churn_score` 오선택이 예외 없이 통과, +19.0%) → Series 이름 검사로 강제. 음수 가치에서 확률 단조성이 역전됨(실측 −35.0 vs −275.0) → 주장을 비음수로 축소하고 테스트로 명문화. `retention_rate` 0.0 금지(matrix.py 정책과 일치). cost NaN/inf·dtype(datetime→나노초)·DataFrame·검증 순서·인덱스 dtype 가드 추가. 리포트: 84.8%에 가정 라벨, "분면 하나 안에서만"이 cost=10.0에서 무너짐을 그리드 표로 정정, 재현 절차 명시. 음수 인원 1,539→1,540 정정. 364 → 376 passed |
| 2026-07-22 | 스토리 3-2 구현: `expected_saving()` 순수 함수(FR12). 변이 5종을 실제로 심어 전부 KILL 확인. 실측이 사전조사와 전건 일치(84.8%·합계 1,454,088·경계 16.6667·1인당 3.70배·오선택 +19.0%). 리포트가 함정 1(총합 역전)·함정 4(84.8%는 비용 가정의 산물)를 정면으로 다루고, 부호 전환이 이탈 수용 분면 내부에서만 일어난다는 발견을 추가. AC5·AC6 계약 테스트로 고정. 338 → 364 passed. Status → review |
| 2026-07-22 | 스토리 3-2 create-story(수동 — BMAD config가 DX_project를 가리켜 스킬 미사용). 함정 5건 실측과 함께 사전 기록: 총합이 2x2 서사를 뒤집어 보이는 것(관망 799,683 > Save 우선 626,845)·확률 컬럼 오선택 시 +19.0%·AD-11 재가중 계약 테스트(1-2 인계)·"84.8% 양수"는 비용 가정의 산물·액션 후보 출처 제한(A6). Status → ready-for-dev. 기준선 3b32749 / 332 passed |
