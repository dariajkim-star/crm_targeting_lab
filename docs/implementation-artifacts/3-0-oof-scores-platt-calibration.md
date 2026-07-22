---
baseline_commit: bb8ea63
baseline_passed: 313
---

# Story 3.0: OOF 점수와 Platt 보정, 목적별 컬럼 분리

Status: ready-for-dev

> **이 스토리는 `epics.md`의 FR에서 유도되지 않았다.** 에픽1 회고 액션 **A2**와 스토리 3-1 **외부 리뷰
> M3**가 합쳐져 드러난 요구사항이다. FR12(기대절감액 산식)는 `P(이탈)`을 입력으로 요구하면서 **그 값이
> 보정된 확률이어야 한다는 말을 하지 않았다.** 새 요구사항을 만드는 것이 아니라 **FR12가 성립하기 위한
> 전제를 뒤늦게 명시**하는 것이며, FR 커버리지 매핑은 바뀌지 않는다.
> 근거: `deferred-work.md` 「A2 결정」절 · `epics.md` Epic 3 머리말 · `epic-1-retro-2026-07-22.md`

## Story

As a 캠페인 의사결정자,
I want 이탈 점수가 **자기가 외운 고객을 다시 맞힌 값이 아니고**, 금액 계산에 쓰는 확률이 **실제 이탈률과
맞기를**,
So that 기대절감액이 계통적으로 부풀지 않고, 4분면 판정과 금액 계산이 서로 다른 숫자를 쓴다는 사실이
컬럼 이름에 드러난다.

## 문제 정의 — 두 단계가 서로 다른 문제를 푼다

| 단계 | 푸는 문제 | 방법 |
|---|---|---|
| **1단계 OOF** | 모델이 **학습에 쓴 고객을 다시 맞히며** 점수·성능을 부풀리는 문제 | 각 고객을 그 고객을 학습에 쓰지 않은 폴드 모델로 예측 |
| **2단계 Platt** | 점수를 **확률로 해석**할 수 없는 문제 | OOF 예측값에 Platt scaling |

**컬럼 계약 (투트랙)** — 하나의 컬럼에 두 역할을 시키지 않는다:

```
quadrant_official (3-1)  <- churn_score            raw OOF, 순위 전용
expected_saving   (3-2)  <- churn_prob_calibrated  Platt 보정, 확률 해석 전용
```

4분면은 순위만 필요하므로 1단계까지로 운영 가능하고, 기대절감액은 숫자를 **실제 확률로 쓰므로**
2단계까지 필요하다.

## Acceptance Criteria

**AC1 (OOF 점수)** — **Given** 학습 데이터가 주어졌을 때
**When** `03_train_churn`이 점수를 산출하면
**Then** 각 고객의 `churn_score`는 **그 고객을 학습에 사용하지 않은 폴드 모델**의 예측값이다
**And** 폴드 분할과 각 폴드 모델이 `RANDOM_SEED`를 명시 수신한다(AD-7)
**And** 전체 데이터로 재예측한 값(in-sample)은 어떤 산출물에도 남지 않는다

**AC2 (Platt 보정)** — **Given** OOF 점수가 산출됐을 때
**When** Platt scaling을 적합하면
**Then** `churn_prob_calibrated`가 산출되고 그 **평균이 실제 이탈률에 수렴**한다
**And** 보정기는 **OOF 점수로 적합**한다(in-sample 점수로 적합하면 보정 자체가 낙관 편향된다)
**And** 보정 방식이 **엄격 단조**임이 테스트로 고정된다 — 순위 보존이 3-1 불변의 근거다

**AC3 (컬럼 분리와 이름)** — **Given** 두 컬럼이 산출됐을 때
**When** `churn_scored.parquet` 스키마를 확인하면
**Then** `CLIENTNUM` · `churn_score` · `churn_prob_calibrated` · `artifact_id`를 갖는다
**And** **`churn_prob`라는 이름은 어디에도 남지 않는다** — 확률이 아닌 값에 `prob`을 쓰지 않는다
**And** **ARCHITECTURE-SPINE AD-5와 pipeline-diagram이 함께 개정된다**(아래 함정 2)

**AC4 (AD-5 정체성 확장)** — **Given** 보정기가 두 번째 적합 객체일 때
**When** `artifact_id`를 계산하면
**Then** **모델과 보정기를 함께 담은 번들**의 바이트에서 산출된다
**And** 보정기만 바뀌어도 `artifact_id`가 달라진다(테스트로 실증)
**And** 1-6b의 정체성 계약(`outputs_share_identity`·`identity_is_consistent`)을 **재구현하지 않고 재사용**한다

**AC5 (결정론)** — **Given** 동일 입력·seed일 때
**When** 2회 연속 실행하면
**Then** `churn_score`·`churn_prob_calibrated`·`artifact_id`가 **완전히 동일**하다(NFR4)

**AC6 (하위 문서 갱신 — 회고 A3의 첫 적용)** — **Given** 점수가 바뀌어 수치가 이동할 때
**When** 산출물을 확인하면
**Then** **수치가 실린 모든 문서가 함께 갱신**된다(아래 「갱신 대상 문서」 목록)
**And** 각 문서에 **어느 점수 기준인지**가 명시된다

## Tasks / Subtasks

- [ ] **T1** OOF 점수 산출 (AC1·AC5)
  - [ ] `crm/churn/model.py`에 OOF 경로 추가. **로직은 `crm/`에** — stage는 40행 상한(함정 1)
  - [ ] 폴드 분할 seed + 폴드 모델 seed **양쪽** 명시 주입
  - [ ] 기존 `score_customers`(in-sample)의 처리 결정: 삭제 vs 유지. 유지 시 **호출부 없음**을 docstring에 명시(1-6b `save_model` 선례)
- [ ] **T2** Platt 보정 (AC2)
  - [ ] `crm/churn/calibrate.py`(신규) — OOF 점수로 적합, 순수 함수
  - [ ] **엄격 단조 성질 테스트** — 이것이 3-1 불변의 근거다
  - [ ] 평균 수렴 테스트(실제 이탈률과 대조)
- [ ] **T3** 컬럼 분리 + 이름 변경 (AC3)
  - [ ] `churn_scored.parquet` 스키마 변경, `churn_prob` 잔존 0건 확인(`grep`)
  - [ ] **ARCHITECTURE-SPINE AD-5 개정** + pipeline-diagram 개정 (함정 2)
- [ ] **T4** AD-5 정체성 번들 확장 (AC4)
  - [ ] `serialize_model`/`artifact_id` 경로를 번들로. **1-6b 계약 재사용, 재구현 금지**
  - [ ] 보정기만 변경 시 id가 달라지는 테스트
- [ ] **T5** 실데이터 실행 + 하위 문서 갱신 (AC6)
  - [ ] `churn-model-report-1-6a.md` — OOF 기준 명시
  - [ ] `quadrant-report-3-1.md` — 분면 인원 재산출(아래 예상치와 대조)
  - [ ] `churn-drivers-actions-1-7.md` — SHAP이 OOF 모델 기준인지 확인
  - [ ] `README.md` — 수치 갱신 (회고 A1 재발 방지)
- [ ] **T6** `deferred-work.md`·`sprint-status.yaml` 갱신

## Dev Notes

### 🚨 함정 1 — stage 03이 **정확히 40행**이다

`pipelines/03_train_churn.py`는 현재 **40행 = AD-9 상한에 딱 붙어 있다**. OOF와 보정이 추가되는데
**한 줄도 늘릴 수 없다.** `main` 외 `def`/`class`/**lambda** 금지(중첩 포함).

→ **모든 로직은 `crm/`으로.** 1-7이 같은 상황에서 `build_shap_output()` 한 함수로 묶어 해결했다.
같은 패턴으로 `fit_and_compare`가 OOF·보정까지 포함해 `ChurnResult`에 담아 반환하는 편이 자연스럽다.

### 🚨 함정 2 — `churn_prob`는 아키텍처 스파인에 박힌 이름이다

`crm/churn/model.py::score_customers` docstring이 이렇게 적고 있다:

> *"the column is named `churn_prob` because the architecture spine (AD-5, pipeline diagram) fixes
> that name, but the value is an UNCALIBRATED, IN-SAMPLE risk score"*

**실제로 박혀 있다** — `ARCHITECTURE-SPINE.md` **AD-5(86·88행)**, `pipeline-diagram.md`, `.memlog.md`.
따라서 이름 변경은 **스토리 패치가 아니라 스파인 개정**이다.

**선례를 따를 것**: SPEC CAP-5는 3차까지 개정됐고(1-2·1-7), AD-11은 1-2 결정을 **소급 반영**했다.
개정할 때 **개정 사유·날짜·근거 스토리**를 함께 적는 것이 이 프로젝트 관례다.

> ⚠️ 이름을 바꾸지 않고 `churn_prob`를 유지하는 선택지도 있었으나 **기각됐다**(사용자 결정 2026-07-22):
> 투트랙에서 이 컬럼은 "확률이 아니라 순위용 점수"가 되는데, 확률이 아니라고 문서에 적으면서 이름을
> `prob`으로 두는 것은 이 프로젝트가 반복 정정해온 형태다(1-6b "자동 복구", 1-7 "한도 불만형").

### 🚨 함정 3 — `artifact_id`는 1-6b가 외부 리뷰 2라운드로 굳힌 계약이다

현재 `artifact_id` = **모델 바이트 SHA-256**. 보정기가 생기면 **번들**이 된다.

- **재구현 금지.** `outputs_share_identity`·`identity_is_consistent`·`verify_artifact_identity`는
  그대로 재사용하고, **직렬화 대상만** 번들로 바꾼다.
- **게이트는 디스크의 바이트까지 해시해 비교한다**(1-6b 외부 리뷰 High). 기록만 믿으면 바꿔치기를
  놓친다 — 번들로 바꿔도 이 성질이 유지되어야 한다.
- **P1 선례 있음**: 챌린저 아티팩트를 `{"model", "calibrator"}`로 묶은 것이 P1 1.5 코드리뷰 교훈이다
  ("서빙에 필요한 전 구성요소를 함께 저장"). 그 패턴을 그대로 가져올 것.

### 🚨 함정 4 — 보정기는 **OOF 점수로** 적합해야 한다

in-sample 점수로 Platt을 적합하면 **보정 자체가 낙관 편향**된다. 순서가 중요하다:

```
1) 폴드별 학습 -> OOF 점수 산출
2) OOF 점수 + y 로 Platt 적합
3) 최종 모델은 전체 데이터로 학습(배포용), 보정기는 2)의 것
```

3)의 최종 모델과 1)의 폴드 모델은 **다른 객체**다. `churn_score` 컬럼에 들어가는 것은 **1)의 OOF
값**이고, SHAP이 설명하는 것은 **3)의 최종 모델**이다 — **이 둘이 어긋나는 것을 어떻게 처리할지가
이 스토리의 미해결 설계 질문이다.** 두 갈래가 보인다:

- (i) SHAP도 OOF 기준으로 재정의 → 일관되나 비용이 크고 AD-5 "동일 아티팩트" 계약을 흔든다
- (ii) SHAP은 최종 모델 유지 + **문서에 "점수는 OOF, 설명은 최종 모델"을 명시** → 계약은 유지되나
  설명과 점수가 엄밀히 같은 모델이 아니다

**dev가 판단하고 근거를 리포트에 남길 것.** AD-5의 원래 취지("확률과 설명이 어긋나면 리텐션 액션
근거가 무너진다")에 비추어 어느 쪽이 덜 나쁜지가 기준이다.

### 실측 사전조사 (2026-07-22, `scratch/a2_calibration_experiment.py`)

**dev가 코드로 재확인할 것.** 아래는 스토리 작성 시점 실측이다.

| 점수 | 고유값 | 3-1 판정 변경 | 평균 확률 | PR-AUC |
|---|---|---|---|---|
| in-sample (현재) | 10,091 | 220 (2.17%) | 0.1976 | 0.9825 |
| OOF 미보정 | 10,115 | — (기준) | 0.1946 | 0.9507 |
| **OOF + Platt (채택)** | 9,760 | **0 (0.00%)** | **0.1607** | **0.9507** |
| OOF + isotonic (기각) | 95 | 58 (0.57%) | 0.1607 | 0.9492 |

- **실제 이탈률 0.1607** — Platt이 정확히 맞춘다.
- **Platt은 PR-AUC를 잃지 않는다**(0.9507 = OOF와 동일). 순위를 안 바꾸기 때문이다.
- **예상 분면 이동**: `446/2086/4621/2974` → **`443/2089/4624/2971`**. 원인은 **보정이 아니라
  in-sample → OOF 전환**이다(220명).

### 보고 수치는 사실상 안 바뀐다 (안심 재료)

`pr_auc_cv()`는 **이미 StratifiedKFold 홀드아웃**으로 채점한다. 1-6a 헤드라인 **PR-AUC 0.9508**이
그 값이고 실측 OOF **0.9507**과 사실상 같다. 즉 **리포트는 이미 정직한 수치를 쓰고 있었고
`churn_prob` 컬럼 하나만 in-sample로 남아 있던 내부 불일치**였다. 이 스토리는 새 기준을 도입하는 게
아니라 **그 불일치를 없앤다.**

### 갱신 대상 문서 (AC6 — 회고 A3의 첫 적용)

회고에서 *"'문서가 테스트를 앞서지 않기'는 있는데 '뒤처지지 않기'가 없다"*는 지적이 나왔고(README
stale 사고), A3가 그 보완을 요구한다. **이 스토리가 그 체크리스트의 첫 사례다.**

| 문서 | 갱신 이유 |
|---|---|
| `churn-model-report-1-6a.md` | 점수 기준이 OOF로 바뀜 |
| `quadrant-report-3-1.md` | 분면 인원 재산출 |
| `churn-drivers-actions-1-7.md` | SHAP 기준 모델 명시(함정 4) |
| `README.md` | 헤드라인 수치 |
| `ARCHITECTURE-SPINE.md` AD-5 · `pipeline-diagram.md` | 컬럼명 개정 |
| `deferred-work.md` · `sprint-status.yaml` | 상태 |

### 이 스토리가 만들지 않는 것

- **마트 컬럼 배선 없음** — 4-1 소관. 단 두 컬럼이 마트로 나갈 수 있게 산출물에 담기만 한다.
- **기대절감액 계산 없음** — 3-2 소관. 이 스토리는 **입력을 준비**할 뿐이다.
- **3-1 판정 로직 변경 없음** — `assign_quadrant`은 손대지 않는다. 입력 컬럼명만 바뀐다.
- **isotonic 경로 없음** — 기각됐다(위 표). 되살리려면 A2를 다시 열어야 한다.

### 물려받은 것 (재사용, 재발명 금지)

- **1-6b 정체성 계약** — 외부 리뷰 2라운드로 굳었다. 직렬화 대상만 바꾼다.
- **`build_xy`** — 예측자 8개 확정(1-7). 손대지 않는다.
- **`pr_auc_cv`** — 이미 홀드아웃. OOF 산출과 **중복 계산하지 말 것**(같은 폴드를 두 번 돌리게 된다).
- **fail-fast > 조용한 관용**, **동어반복 회피**, **성질 + oracle + 변이 테스트**.

### Testing Standards

- `.venv/Scripts/python.exe -m pytest` — 현 기준선 **313 passed**, 회귀 0
- **엄격 단조 성질 테스트가 이 스토리의 핵심 테스트다** — 3-1 불변의 근거이므로,
  `tests/campaign/test_matrix.py`의 단조 불변 테스트와 **짝을 이룬다**
- **문서가 테스트를 앞서지 않기** + **뒤처지지도 않기**(AC6)

### Project Structure Notes

```
crm/churn/calibrate.py            # NEW - Platt 적합/적용 (순수)
crm/churn/model.py                # UPDATE - OOF 경로, ChurnResult 확장, churn_prob 제거
crm/churn/artifact.py             # UPDATE - 번들 직렬화(계약은 재사용)
pipelines/03_train_churn.py       # UPDATE - ⚠️ 40행 상한, 로직 금지
tests/churn/test_calibrate.py     # NEW - 엄격 단조·평균 수렴·결정론
tests/churn/test_model.py         # UPDATE - OOF 성질
tests/churn/test_artifact.py      # UPDATE - 보정기 변경 시 id 변화
tests/churn/test_stage.py         # UPDATE - 새 스키마
docs/planning-artifacts/architecture/.../ARCHITECTURE-SPINE.md  # UPDATE - AD-5 개정
docs/planning-artifacts/architecture/.../pipeline-diagram.md    # UPDATE - 컬럼명
(+ 위 「갱신 대상 문서」 전부)
```

### 환경 실측 (2026-07-22)

```
HEAD bb8ea63 | 313 passed | 산출물 artifact_id c751c63d5b58 (8피처, in-sample)
python 3.12.10 | xgboost 3.3.0 | scikit-learn 1.9.0 | pandas 3.0.3 | numpy 2.4.6
stage 03_train_churn: 정확히 40행 (AD-9 상한)
```

### References

- [Source: docs/implementation-artifacts/deferred-work.md#A2 결정] — 결정 근거·실측표·대가
- [Source: docs/implementation-artifacts/epic-1-retro-2026-07-22.md#A2] — 액션 원문
- [Source: docs/implementation-artifacts/3-1-official-quadrant-assignment.md#M3] — isotonic 반례
- [Source: docs/implementation-artifacts/quadrant-report-3-1.md] — 순위 전용 계약, 예상 분면 이동
- [Source: .../ARCHITECTURE-SPINE.md#AD-5] — 동일 아티팩트 계약, `churn_prob` 이름 (개정 대상)
- [Source: .../ARCHITECTURE-SPINE.md#AD-7] — seed 명시 주입 (폴드 분할 포함)
- [Source: .../ARCHITECTURE-SPINE.md#AD-9] — stage 40행, main only
- [Source: docs/implementation-artifacts/1-6b-artifact-identity-meta.md] — 정체성 계약(재사용)
- [Source: ob_storage/.../12_P1_에픽1_완료_요약.md] — P1 `{"model","calibrator"}` 번들 선례
- [Source: 실측 2026-07-22] — `scratch/a2_calibration_experiment.py`

## Dev Agent Record

### Agent Model Used

### Debug Log References

### Completion Notes List

### File List

## Change Log

| 날짜 | 변경 |
|---|---|
| 2026-07-22 | 스토리 3-0 create-story(수동 — BMAD config가 DX_project를 가리켜 스킬 미사용). A2 결정(OOF + Platt, 투트랙 컬럼)의 실행 스토리. 함정 4건 사전 기록: stage 40행 포화·`churn_prob`가 스파인에 박힌 이름·artifact_id 번들 확장·보정기는 OOF로 적합. 미해결 설계 질문 1건(SHAP 기준 모델) 명시. Status → ready-for-dev. 기준선 bb8ea63 / 313 passed |
