---
baseline_commit: caf16e6
baseline_passed: 272
---

# Story 3.1: 2×2 공식 판정

Status: review

> **에픽 순서 주의**: 에픽1 회고(2026-07-22) 결정으로 실행 순서가 **에픽1 → 에픽3 → 에픽2 → 에픽4**로
> 바뀌었다. 이 스토리가 에픽3의 첫 스토리이며, 에픽2(LTV 데모)는 AD-1 격리 레인이라 뒤로 미뤄졌다.
> 근거: `epic-1-retro-2026-07-22.md` 4-2절.

## Story

As a 마케팅 의사결정자,
I want 이탈위험 × 고객가치 4분면 판정이 한 곳에서만 내려지기를,
So that 대시보드의 "Save 우선" 분면과 캠페인 타겟 리스트가 어긋나지 않는다.

## Acceptance Criteria

**AC1** — **Given** 이탈확률과 `customer_value`가 주어졌을 때
**When** `crm/campaign/matrix.py::assign_quadrant()`를 호출하면
**Then** `quadrant_official`이 산출되고, 임계 방식·값·경계 포함 규칙(상단 `>=`)은 `crm/config.py`의 `QUADRANT_RULE`에서만 온다(AD-12)
**And** 4분면 라벨 4종(Save 우선/관망/저비용 유지/이탈 수용)은 config의 **Enum**으로 고정되며 자유 문자열이 아니다

**AC2** — **Given** `matrix.py`의 책임 범위를 검사할 때
**When** 코드를 확인하면
**Then** 예산·비용 개념을 알지 못한다(4분면은 예산과 무관, AD-9)
**And** `customer_value`를 재계산하지 않고 1-2 함수 출력을 소비한다(AD-11)

**AC3** — **Given** 경계값 고객이 존재할 때
**When** 임계값과 정확히 같은 값을 가진 고객을 판정하면
**Then** `>=` 규칙에 따라 결정론적으로 상단 분면에 배정되고, 이를 검증하는 경계 테스트가 있다

**AC4** — **Given** 판정 결과가 산출됐을 때
**When** 리포트를 확인하면
**Then** 분면별 고객 수와 분면별 정책 제안이 제시된다(FR11)
**And** 가치 프록시의 근거·한계가 재명시된다(NFR1)

### AC 파생 — 이 스토리가 함께 답해야 하는 설계 질문 (필수)

**AC5 (임계 방식 선정 근거)** — `QUADRANT_RULE`이 채택한 임계 방식의 **선정 근거를 리포트에 기재**한다.
아래 Dev Notes의 실측 사전조사가 보여주듯 **중앙값 컷은 이 데이터에서 붕괴한다**. 방식 선택은 이
스토리의 핵심 판단이며, 근거 없이 관례("2×2니까 중앙값")로 고르지 말 것.

**AC6 (A2 결합 회피)** — 채택한 임계 방식이 **`churn_prob`의 절대값에 의존하는지 순위에만 의존하는지**를
명시한다. 절대 확률 임계를 택하면 **미해결 A2(calibration)가 이 스토리로 들어온다**(Dev Notes 참조).

## Tasks / Subtasks

- [x] **T1** `crm/config.py`에 `QUADRANT_RULE` + 4분면 Enum 추가 (AC1)
  - [x] Enum 멤버 **값은 ASCII** — 한글 라벨은 표시층 소관 (config docstring의 인코딩 규약)
  - [x] `# source:` 주석으로 출처 표기, **AD-1 준수 확인**(데이터 유래 값 하드코딩 금지 — 아래 함정 1)
  - [x] config 변경 → `config_hash` 변경 → **01·02·03 재실행 필요**(1-3/1-4/1-6a/1-7 선례)
- [x] **T2** `crm/campaign/matrix.py::assign_quadrant()` 구현 (AC1·AC2·AC3)
  - [x] 순수 함수. 예산·비용 인자 없음, `crm.campaign.simulate`/`sensitivity` import 없음
  - [x] `customer_value` 재계산 없음, `Total_Trans_Amt` 미명명(AD-11 가드)
  - [x] 경계 포함 규칙 `>=` 상단, 결정론
- [x] **T3** 테스트 (AC1·AC2·AC3)
  - [x] **성질 기반**: 분면 배타·망라(모든 행이 정확히 1개 분면), 단조성(위험↑ → 상단 분면 유지)
  - [x] **경계 테스트**: 임계값과 정확히 같은 값 → 상단 배정
  - [x] **하드코딩 oracle** 1건
  - [x] **변이 테스트**: `>` vs `>=` 뒤바꿈, 두 축 혼동, 라벨 순서 뒤바꿈 → 전부 KILL 확인
  - [x] Enum 자유문자열 금지 정적 검사
- [x] **T4** 구조 가드 (AC2)
  - [x] AD-9 `crm/campaign/` 내부 방향(`matrix` → `simulate` → `sensitivity`) 체커를 `RULES`에 등재
  - [x] **합성 위반 픽스처로 자기검증** — `matrix.py`가 유일 파일이라 대상이 적다. 1-1a 교훈: 픽스처 없으면 가드가 장식이 된다
  - [x] `structure-guard-coverage.md` 재생성 — `AD-9 campaign order` 행이 **0 → 실스캔**으로 전환되는지 확인(1-1a 인계 항목)
- [x] **T5** 실데이터 실행 + 리포트 (AC4·AC5·AC6)
  - [x] `docs/implementation-artifacts/quadrant-report-3-1.md` 작성
  - [x] 분면별 고객 수(실측), 분면별 정책 제안, 임계 방식 선정 근거, 가치 프록시 한계 재명시
  - [x] **무단위 표기**(NFR3) — 통화 기호 금지
- [x] **T6** `deferred-work.md`·`sprint-status.yaml` 갱신

## Dev Notes

### 🚨 함정 1 — AD-1과 AD-12가 정면 충돌한다 (이 스토리의 핵심 판단)

- **AD-12**: 임계 **방식·값**은 `crm/config.py`의 `QUADRANT_RULE`이 선언한다
- **AD-1**: config에 **데이터 유래 값을 두는 것은 금지**다 — *"분위수 경계·스케일러 상태·인코딩: 전부 금지"*

즉 `QUADRANT_RULE`에 `churn_threshold = 0.1607` 같은 **실측 경계를 박으면 AD-1 위반**이다.

**선례가 답을 갖고 있다** — 1-3의 RFM이 같은 충돌을 이미 통과했다:

> config에는 **개수**(`RFM_QUANTILES=5`, 선험 규약)만 두고, **경계는 런타임 산출**. 실데이터 경계
> (R `[0,1,2,3,6]` 등)는 **리포트에 기재**하고 config에는 넣지 않았다.

따라서 `QUADRANT_RULE`은 **"어떻게 자를지"(방식)를 선언**하고, **잘린 값은 런타임 산출 + 리포트 기재**다.
그리고 그 실측 임계값은 **AD-3에 따라 마트의 `threshold_official_*` 컬럼**으로 나가야 한다(4-1 소관,
이 스토리는 함수가 그 값을 **반환**하도록 설계만 해두면 된다).

> ⚠️ 1-4의 `SEGMENT_K=4` 선례와 혼동하지 말 것. `k`는 **분석가가 곡선을 보고 고른 하이퍼파라미터**라
> config 등재가 허용됐고(deferred-work에 AD-1 문구 명확화가 미결로 남아 있음), **분위수 경계는 다르다.**

### 🚨 함정 2 — 실측: 중앙값 컷은 이 데이터에서 붕괴한다

`churn_prob` 분포가 극단적으로 치우쳐 있다(실측, `data/churn_scored.parquet` 8피처 산출물):

```
count 10127 | mean 0.19757 | std 0.35678 | min 0.00001 | max 0.99998
 50%  0.00511    60%  0.01484    70%  0.05380    75%  0.12684    80%  0.37538    90%  0.97166
churn_prob < 0.001 인 행: 2854 / 10127
```

**중앙값이 0.0051이다.** 중앙값 컷을 쓰면 **이탈확률 0.5% 고객에게 "고위험" 라벨**이 붙는다. 실제
이탈률은 16.07%이므로 이 라벨은 의미가 없고, "Save 우선"에 1,273명이 들어가는데 그중 대다수가
사실상 위험하지 않다. **대시보드에서 가장 먼저 지적당할 지점이다.**

**후보 방식별 실측 분면 인원** (가치 축은 `customer_value` 중앙값 3,899 고정):

| 임계 방식 | churn 컷 | Save 우선 | 관망 | 저비용 유지 | 이탈 수용 |
|---|---|---|---|---|---|
| 중앙값 (q0.50) | 0.00511 | 1,273 | 3,791 | 3,794 | 1,269 |
| q0.75 | 0.12684 | 446 | 2,086 | 4,621 | 2,974 |
| 실제 이탈률 0.1607 고정 | 0.16070 | 415 | 1,995 | 4,652 | 3,065 |
| q(1−기저율) = q0.8393 | 0.77607 | 307 | 1,321 | 4,760 | 3,739 |

**dev가 코드로 재확인할 것.** 위 수치는 스토리 작성 시점 산출물 기준이며, config 변경으로 재실행하면
바뀔 수 있다.

### 🚨 함정 3 — 임계 방식 선택이 미결 A2와 결합한다

에픽1 회고의 **A2(`churn_prob` 확률 vs 순위)가 아직 열려 있다.** 실측(`deferred-work.md`의
「calibration 실측」절): 평균 0.1976 vs 실제 0.1607(**23% 과대**), 7분위는 **약 20배 과대**인 **비선형 왜곡**.

- **분위수 방식**(q0.75 등)을 택하면 → **순위만 쓴다** → **보정과 무관** → A2가 이 스토리로 들어오지 않는다
- **절대 확률 방식**(0.1607 고정)을 택하면 → **미보정 확률의 절대값에 의존** → **A2가 3-1의 문제가 된다**

**권고**: 분위수 방식을 택해 3-1을 A2로부터 격리하라. 절대 확률 방식을 택하려면 **A2를 먼저 닫아야 한다.**
어느 쪽이든 **AC6이 이 결합 여부를 리포트에 명시할 것을 요구한다.**

### 🚨 함정 4 — Enum 값은 ASCII, 한글 라벨은 표시층

`crm/config.py` docstring이 못 박은 규약: *"everything the RUNTIME parses — names, values, messages —
stays ASCII"* (P1의 cp949 콘솔 사고 교훈). AC1이 요구하는 4분면 라벨은 한글이지만, **Enum 멤버 값에
한글을 넣지 말 것.** ASCII 식별자를 값으로 두고, 한글 표기는 리포트·대시보드 표시층이 매핑한다.

### 이 스토리가 만들지 않는 것 (범위 경계)

- **파이프라인 단계 없음** — 1-2가 이미 판정한 사안이다: *"E3 산출물도 **세션 리포트**이고 공식 수치의
  자리는 **4-1 마트 + 4-3 Tableau 탭**이다."* `matrix.py`는 순수 함수이고 `05_marts`가 소비한다.
- **`target_priority` 없음** — 3-3 소관(AD-12).
- **기대절감액·예산·비용 없음** — 3-2 소관. `matrix.py`는 이 개념들을 **알아서는 안 된다**(AC2).
- **마트 컬럼 배선 없음** — 4-1 소관. 단, 함수가 실측 임계값을 반환해 4-1이 `threshold_official_*`을
  채울 수 있게 **설계**해둘 것(AD-3).

### 물려받은 것 (재사용, 재발명 금지)

- **`customer_value` 소비 경로**: `features_customers.parquet`의 `monetary_proxy`가 1-4가 저장한
  `customer_value()` 출력이다. 1-4·1-5가 이 컬럼을 소비하는 방식을 그대로 따를 것. `value.py`를
  다시 호출할지 저장된 컬럼을 읽을지는 dev 판단이나, **어느 쪽이든 재계산·재가중 금지**(AD-11).
- **가드 추가 패턴**: 체커는 `(root) -> (violations, scanned)` 순수 함수, `_is_skipped()`로 도구
  디렉터리 제외, `RULES` 튜플 등재, **합성 위반 픽스처로 자기검증**. `tests/structure/checkers.py`와
  `test_checkers_selfcheck.py`를 읽고 시작하라.
- **동어반복 회피**: 구현과 같은 공식을 재구현해 비교하지 말 것. 그럴듯한 오구현이 깨뜨릴 **성질**로
  검증한다(1-2 선례).
- **fail-fast > 조용한 관용**: 1-6a/1-6b/1-7에서 확립. 빈 입력·결측 임계는 예외로.

### Testing Standards

- `.venv/Scripts/python.exe -m pytest` — 현 기준선 **272 passed**, 회귀 0
- 성질 + 하드코딩 oracle + 변이 테스트, 실데이터 실행 DoD(conventions 3항)
- **문서가 테스트를 앞서지 않기** — 리포트에 쓰기 전에 그 성질을 KILL하는 테스트가 있어야 한다
  (에픽1 회고가 이 에픽의 최대 자산으로 지목한 규율)
- 재산출 시 **갱신 대상 문서를 함께 확인**할 것 (회고 A3 — README stale 재발 방지)

### Project Structure Notes

```
crm/config.py                     # UPDATE - QUADRANT_RULE + 4분면 Enum (ASCII 값)
crm/campaign/matrix.py            # NEW - assign_quadrant() (순수, 예산 무지)
tests/campaign/test_matrix.py     # NEW - 성질·경계·oracle·변이
tests/structure/checkers.py       # UPDATE - AD-9 campaign order 체커
docs/implementation-artifacts/quadrant-report-3-1.md      # NEW - 분면 인원·정책·임계 근거
docs/implementation-artifacts/structure-guard-coverage.md # UPDATE - 재생성
docs/implementation-artifacts/deferred-work.md            # UPDATE - 미룬 항목
```

### 환경 실측 (2026-07-22)

```
HEAD caf16e6 | 272 passed | 산출물 artifact_id c751c63d5b58 (8피처)
python 3.12.10 | xgboost 3.3.0 | scikit-learn 1.9.0 | pandas 3.0.3 | numpy 2.4.6 | shap 0.52.0
churn_prob: mean 0.19757 / median 0.00511 / 실제 이탈률 0.1607
customer_value: median 3899.0 / mean 4404.1 / max 18484.0
```

### References

- [Source: docs/planning-artifacts/epics.md#Story 3.1] — AC 원문(FR11, AD-12)
- [Source: .../ARCHITECTURE-SPINE.md#AD-12] — `QUADRANT_RULE` 단일 소유, Enum 고정, 시뮬레이터는 소비만
- [Source: .../ARCHITECTURE-SPINE.md#AD-3] — 공식 판정은 Python, 마트 `threshold_official_*`, BI는 표시만
- [Source: .../ARCHITECTURE-SPINE.md#AD-9] — `matrix.py` → `simulate.py` → `sensitivity.py` 단방향, matrix는 예산 무지
- [Source: .../ARCHITECTURE-SPINE.md#AD-1] — config에 데이터 유래 값 금지 (함정 1의 근거)
- [Source: .../ARCHITECTURE-SPINE.md#AD-11] — `customer_value` 단일 정의, `Total_Trans_Amt` 이름 봉인
- [Source: docs/specs/spec-crm-targeting-lab/SPEC.md#CAP-5] — 2×2 정의, 가치 축 단일 프록시, 3차 개정 이력
- [Source: docs/implementation-artifacts/1-2-customer-value-single-definition.md#M3] — E3 산출물의 물리적 지위(세션 리포트)
- [Source: docs/implementation-artifacts/1-3-rfm-proxy-features.md] — config는 방식, 경계는 런타임 (함정 1의 선례)
- [Source: docs/implementation-artifacts/deferred-work.md#calibration 실측] — A2 근거 (함정 3)
- [Source: docs/implementation-artifacts/epic-1-retro-2026-07-22.md] — 에픽 순서 변경, A2·A3 액션
- [Source: 실측 2026-07-22] — churn_prob·customer_value 분포, 후보 방식별 분면 인원

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (bmad-dev-story)

### Debug Log References

**기준선**: HEAD `84f39ef`, 272 passed. (frontmatter의 `baseline_commit: caf16e6`은 create-story
시점 값이라 스킬 규약대로 보존했다. 그 사이 커밋은 문서 전용 2건 — `6075d11` 스토리 파일, `84f39ef` A5.)

**RED 확인**: `tests/campaign/test_matrix.py` 선작성 → `ModuleNotFoundError: crm.campaign.matrix`.

**테스트 결함 2건을 GREEN 단계에서 자체 검출** (구현 결함 아님):

1. **픽스처가 WATCH 셀을 만들지 못했다** — 초기 픽스처는 risk와 value가 모두 오름차순이라 **두 축이
   완전 동조**했다. 고위험·저가치 조합이 생길 수 없어 `test_all_four_quadrants_are_reachable`이
   실패했다. 이 테스트가 없었으면 **규칙의 1/4을 한 번도 실행하지 않은 채 전부 초록**이었을 것이다.
   가치 축을 비동조 배열로 교체.
2. **경계 테스트가 자기 꼬리를 물었다** — "임계값 바로 아래" 고객을 만들려고 행을 추가하거나 ULP만큼
   내렸더니, **그 고객이 곧 분위수를 정의하는 순서통계량**이라 임계값이 함께 움직여 영원히 경계에
   머물렀다. n=5로 바꿔 분위수가 데이터 포인트에 **정확히** 떨어지게 하고(q0.75 → position 3),
   "바로 아래"는 **다른 고객**으로 검증하도록 교체.

**회귀 1건 발생·해소 — `config.py`에는 dataclass를 둘 수 없다(실측)**:
`@dataclasses.dataclass`로 `QuadrantRule`을 만들자 `test_config_grid_guard_raises_on_out_of_grid_value`가
`AttributeError: 'NoneType' object has no attribute '__dict__'`로 죽었다. 원인은 그 가드 테스트가
config 소스를 **`sys.modules`에 없는 합성 모듈명**으로 `exec`하기 때문 — dataclass 생성 중
`dataclasses`가 필드 어노테이션의 ClassVar 여부를 판정하려 `sys.modules.get(cls.__module__).__dict__`를
조회하고 None을 만난다. **`NamedTuple`로 교체**해 해소(`__annotations__`를 직접 읽어 무관).
가드를 약화시키는 방향은 택하지 않았다 — 1-2 M2의 A안 논리와 동일하게, 실재하는 가드를 가정을 위해
무디게 하는 건 순서가 거꾸로다. 제약은 `QuadrantRule` docstring과 deferred-work에 기재.

**변이 테스트 6종 전부 KILLED** (구현을 실제로 훼손하고 `tests/campaign/` 실행, 매회 원복):

| 변이 | 결과 |
|---|---|
| M1 경계 `>=` → `>` | KILLED (1건) |
| M2 두 축 뒤바꿈 (risk ↔ value) | KILLED (7건) |
| M3 WATCH ↔ LOW_COST_KEEP 라벨 뒤바꿈 | KILLED (7건) |
| M4 `rule` 무시하고 0.5 하드코딩 (AD-12) | KILLED (6건) |
| M5 가치 축 부등호 반전 | KILLED (4건) |
| M6 NaN 검사 제거 (fail-fast 무력화) | KILLED (2건) |

> 1차 변이 실행에서 6종 전부 "SURVIVED"로 나왔는데 **판정 하네스의 버그**였다 — pytest `-q`의 마지막
> 줄이 카운트가 아니라 `FAILED ...` 줄이라 grep이 빗나갔다. 종료코드 기반으로 고쳐 재실행. 변이가
> 파일에 실제 적용됐는지 `diff`로 확인하는 단계도 함께 추가했다.

**실데이터 실행**: 10,127행 전량 판정. 실현 컷 risk `0.126842` / value `3899.0`. 4분면 합 = 10,127(행 수
보존), 라벨 집합 = Enum 4종과 정확히 일치.

### Completion Notes List

- **AC1 충족**: `assign_quadrant()`가 `quadrant_official`을 산출하고, 임계 방식·분위수·경계 규칙은
  전부 `crm/config.py::QUADRANT_RULE`에서만 온다. 라벨은 `Quadrant` Enum 4종. **M4 변이(rule 무시)가
  6건 실패로 죽어** 규칙이 실제로 config에서 온다는 것이 실증됐다.
- **AC2 충족**: `matrix.py`는 예산·비용 인자도 개념도 갖지 않는다. `crm.campaign.simulate`/`sensitivity`
  import 없음 — 구조 가드 `AD-9 campaign order`가 **0 → 실스캔 1건**으로 전환되며 위반 0(1-1a 인계
  항목 완료). `customer_value` 출력을 Series 인자로 **소비**만 하고 `Total_Trans_Amt`를 명명하지
  않는다 → AD-11 가드 scanned 16 → 17, 위반 0.
- **AC3 충족**: 경계 고객은 `>=`로 상단 배정. n=5 픽스처에서 분위수가 데이터 포인트에 정확히 떨어지게
  해 **진짜 경계 고객**을 만들었고, M1 변이가 이 테스트 하나로 죽는다.
- **AC4 충족**: `quadrant-report-3-1.md`에 분면별 고객 수·비율·평균값·정책 제안, 가치 프록시 근거와
  한계 4건 재명시. 무단위 표기(통화 기호 0회).
- **AC5 충족 — 이 스토리의 핵심 판단**: 임계 방식은 **분위수**(risk q0.75 / value q0.50). 후보 5종
  비교표를 리포트에 실었다. **중앙값 컷은 실측에서 붕괴**한다(median 0.00511 → 이탈확률 0.5% 고객에게
  "고위험" 라벨). **실제 이탈률 0.1607 고정과 q(1−기저율)은 AD-1 위반으로 탈락** — 0.1607은 라벨에서
  읽은 값이다. config에는 분위수 레벨만, 실현 컷(0.126842)은 런타임 산출 + 리포트 기재(1-3 RFM 선례).
- **AC6 충족**: 두 컷 모두 분위수 → **순위만 사용, 보정된 크기 미사용** → **미결 A2가 이 스토리로
  들어오지 않는다.** 강한 단조 비선형 변환을 걸어도 판정이 한 건도 바뀌지 않음을
  `test_a_strictly_increasing_transform_of_risk_changes_nothing`이 고정한다. **3-2는 면제되지 않는다**
  (기대절감액은 확률을 곱셈의 크기로 쓴다) — 리포트에 경고로 명시.
- **사후 확인(판정에 미사용)**: 분면별 실제 이탈률이 save_first 69.96% / watch 62.99% vs
  low_cost_keep 0.00% / accept_churn 0.03%로 갈린다. 축이 의미 있게 작동한다는 신호지만 **in-sample이라
  낙관 편향**임을 리포트에 고지했고, 성능 근거로 인용하지 말 것을 명기했다.
- **config 재실행 영향 없음**: `QUADRANT_RULE` 추가로 `config_hash`가 바뀌지만, `matrix.py`는 파이프라인
  단계가 아니라 순수 함수라 산출물을 만들지 않는다. 기존 산출물은 그대로 두고 판정만 세션에서 수행했다
  (M2 판정 — E3 산출물은 세션 리포트, 공식 자리는 4-1 마트).
- **테스트**: 272 → **294 passed** (+22), 회귀 0. 구조 가드 전종 green.
- **리뷰 번들 작성 중 자체 발견 1건**: AC6의 단조불변 논증은 경우가 둘인데(임계값이 순서통계량 **사이**
  vs 데이터 포인트에 **정확히**) 테스트가 전자만 덮고 있었다. 리포트는 일반적으로 주장하고 있었으므로
  "문서가 테스트를 앞선" 상태였다 — 후자 케이스 테스트를 추가해 해소(293 → 294).

### File List

- `crm/config.py` — UPDATE (`Quadrant` Enum, `QuadrantRule` NamedTuple, `QUADRANT_RULE`, `BOUNDARY_UPPER_INCLUSIVE`, import-time 검증 2종)
- `crm/campaign/matrix.py` — NEW (`assign_quadrant`, `quadrant_thresholds`, `QuadrantThresholds`)
- `tests/campaign/__init__.py` — NEW
- `tests/campaign/test_matrix.py` — NEW (21건)
- `docs/implementation-artifacts/quadrant-report-3-1.md` — NEW
- `docs/implementation-artifacts/structure-guard-coverage.md` — UPDATE (자동 재생성)
- `docs/implementation-artifacts/deferred-work.md` — UPDATE (3-1 보류 3건)
- `docs/implementation-artifacts/sprint-status.yaml` — UPDATE (3-1 review, epic-3 in-progress)
- `docs/implementation-artifacts/3-1-official-quadrant-assignment.md` — UPDATE (이 파일)

## Change Log

| 날짜 | 변경 |
|---|---|
| 2026-07-22 | 스토리 3-1 구현: `QUADRANT_RULE`(분위수 risk q0.75 / value q0.50, `>=` 상단) + `Quadrant` Enum(ASCII) + `assign_quadrant()`. 실현 컷 0.126842 / 3899.0, 분면 446/2086/4621/2974. AC5 근거로 중앙값 붕괴·AD-1 탈락 후보 기재, AC6은 순위 전용이라 A2 비결합 확정. 변이 6종 KILL. config에 dataclass 불가(AD-4 가드 exec) 실측 → NamedTuple. 272 → 294 passed(+1은 리뷰 번들 작성 중 발견한 단조불변 on-point 케이스), 회귀 0. Status → review |
| 2026-07-22 | 스토리 3-1 create-story(수동 — BMAD config가 DX_project를 가리켜 스킬 미사용). AD-1 vs AD-12 충돌·중앙값 컷 붕괴·A2 결합 3건을 실측과 함께 사전 기록. Status → ready-for-dev. 기준선 caf16e6 / 272 passed |
