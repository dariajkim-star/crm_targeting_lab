---
baseline_commit: 3b32749
baseline_passed: 332
---

# Story 3.2: 캠페인 기대 절감액 시뮬레이터

Status: ready-for-dev

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

- [ ] **T1** `crm/campaign/simulate.py::expected_saving()` 구현 (AC1·AC3·AC5)
  - [ ] 순수 함수. 기본값은 `crm.config` 상수 참조, 리터럴 재선언 금지
  - [ ] 파라미터는 **함수 인자**로 받는다(3-4가 이 함수를 반복 호출한다)
  - [ ] `crm.campaign.sensitivity` import 금지(AD-9 방향), **예산·우선순위 개념 없음**(3-3 소관)
  - [ ] 확률 입력이 `churn_prob_calibrated`임을 시그니처·docstring이 못박는다
- [ ] **T2** 테스트 — 행동 기반 (AC2)
  - [ ] **단조성**: 성공률↑ → 절감액↑ / 비용↑ → 절감액↓ / 확률↑ → 절감액↑ / 가치↑ → 절감액↑
  - [ ] **부호 전환 지점**: `p × value = cost / rate`에서 0을 지난다(아래 실측 16.67)
  - [ ] **하드코딩 oracle** 1건
  - [ ] **변이**: 부호 반전·항 누락·비용을 더하기·확률과 가치 뒤바꿈 → 전부 KILL 확인
  - [ ] **동어반복 금지** — 같은 식을 다시 써서 비교하지 말 것
- [ ] **T3** 계약 테스트 2종 (AC5·AC6)
  - [ ] `churn_score`를 넣으면 금액이 달라짐을 실증(둘을 혼동할 수 없게)
  - [ ] **sentinel monkeypatch**로 value 입력이 `customer_value()` 출력 그대로임을 검증
- [ ] **T4** 실데이터 실행 + 리포트 (AC4)
  - [ ] `docs/implementation-artifacts/savings-report-3-2.md`
  - [ ] 분면별 절감액 분포, 부호 전환 경계, **가정 라벨링**(NFR1), 무단위 표기
  - [ ] **아래 함정 1(총합 역전)을 리포트가 정면으로 다룰 것**
- [ ] **T5** `deferred-work.md`·`sprint-status.yaml` 갱신

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

### Testing Standards

- `.venv/Scripts/python.exe -m pytest` — 현 기준선 **332 passed**, 회귀 0
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
HEAD 3b32749 | 332 passed | artifact_id 9e1a4d71800f (8피처, OOF + Platt)
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

### Debug Log References

### Completion Notes List

### File List

## Change Log

| 날짜 | 변경 |
|---|---|
| 2026-07-22 | 스토리 3-2 create-story(수동 — BMAD config가 DX_project를 가리켜 스킬 미사용). 함정 5건 실측과 함께 사전 기록: 총합이 2x2 서사를 뒤집어 보이는 것(관망 799,683 > Save 우선 626,845)·확률 컬럼 오선택 시 +19.0%·AD-11 재가중 계약 테스트(1-2 인계)·"84.8% 양수"는 비용 가정의 산물·액션 후보 출처 제한(A6). Status → ready-for-dev. 기준선 3b32749 / 332 passed |
