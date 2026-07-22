---
baseline_commit: bb8ea63
baseline_passed: 313
---

# Story 3.0: OOF 점수와 Platt 보정, 목적별 컬럼 분리

Status: in-progress

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

- [x] **T1** OOF 점수 산출 (AC1·AC5)
  - [x] `crm/churn/model.py`에 OOF 경로 추가. **로직은 `crm/`에** — stage는 40행 상한(함정 1)
  - [x] 폴드 분할 seed + 폴드 모델 seed **양쪽** 명시 주입
  - [x] 기존 `score_customers`(in-sample)의 처리 결정: 삭제 vs 유지. 유지 시 **호출부 없음**을 docstring에 명시(1-6b `save_model` 선례)
- [x] **T2** Platt 보정 (AC2)
  - [x] `crm/churn/calibrate.py`(신규) — OOF 점수로 적합, 순수 함수
  - [x] **엄격 단조 성질 테스트** — 이것이 3-1 불변의 근거다
  - [x] 평균 수렴 테스트(실제 이탈률과 대조)
- [x] **T3** 컬럼 분리 + 이름 변경 (AC3)
  - [x] `churn_scored.parquet` 스키마 변경, `churn_prob` 잔존 0건 확인(`grep`)
  - [x] **ARCHITECTURE-SPINE AD-5 개정** + pipeline-diagram 개정 (함정 2)
- [x] **T4** AD-5 정체성 번들 확장 (AC4)
  - [x] `serialize_model`/`artifact_id` 경로를 번들로. **1-6b 계약 재사용, 재구현 금지**
  - [x] 보정기만 변경 시 id가 달라지는 테스트
- [x] **T5** 실데이터 실행 + 하위 문서 갱신 (AC6)
  - [x] `churn-model-report-1-6a.md` — OOF 기준 명시
  - [x] `quadrant-report-3-1.md` — 분면 인원 재산출(아래 예상치와 대조)
  - [x] `churn-drivers-actions-1-7.md` — SHAP이 OOF 모델 기준인지 확인
  - [x] `README.md` — 수치 갱신 (회고 A1 재발 방지)
- [x] **T6** `deferred-work.md`·`sprint-status.yaml` 갱신

### Review Findings

코드리뷰 2026-07-22 (3레이어: Blind Hunter / Edge Case Hunter / Acceptance Auditor).
원시 34건 → 중복병합·실물검증 후 **decision 4 · patch 15 · defer 4 · dismiss 11**.

- [ ] [Review][Decision] **freshness 게이트가 컬럼 계약을 캐시 키에 담지 않는다** — 3-0 이전 산출물이 남은 환경에서 `crm/config.py`가 불변이므로 `config_hash`도 불변 → 구 artifact_id 3자가 서로 일치 → `outputs_share_identity` True → stage 03 전체가 return. 결과적으로 **옛 in-sample `churn_prob`가 살아남고 `churn_score`는 생성되지 않는다.** `artifact_id`는 "무엇을 직렬화했는지"(bare model vs bundle)를 기록하지 않아 번들 전환도 감지 못한다. 선택지: (a) 스키마/컬럼 계약을 `config_hash`에 편입 (b) 산출물 컬럼 존재를 게이트 조건에 추가 (c) 3-0 전환은 1회성으로 보고 수동 삭제 안내만. 근거: `crm/churn/freshness.py:36-37,205-207` · `pipelines/03_train_churn.py:23-26`
- [ ] [Review][Decision] **번들 정체성이 "점수를 만든 모델"을 담지 않는다 — AD-5 보증 문구의 사정거리** — `artifact_id`는 `{최종 모델, 보정기}`를 해시하지만 저장된 `churn_score`는 **번들에 없는 k개 폴드 모델**의 산출물이다. `artifact.py`가 스스로 내건 목적("a churn_score and an explanation of it must not be presented together unless they describe the same model")이 문자 그대로는 더 이상 성립하지 않는다. 함정 4의 (ii)안 채택 결과이고 AD-5·deferred-work에 근거는 기재됐으나, **보증 문구 자체는 좁혀지지 않았다.** `test_explain.py`가 저장 점수를 버리고 `result.model.predict_proba`로 갈아탄 것이 이 균열의 실물 증거다. 선택지: (a) AD-5 보증 문구를 "설명과 보정은 동일 아티팩트, 점수는 그 아티팩트의 OOF 형제"로 축소 개정 (b) 폴드 모델까지 번들에 포함 (c) 현행 유지 + 문서 보강
- [ ] [Review][Decision] **`epics.md` 마트 스키마가 아직 단일 `churn_prob`를 요구한다 — 4-1이 개정 전 계약대로 만든다** — AD-5는 컬럼을 둘로 나눴는데 에픽은 하나를 요구한다. 이건 과거 기록이 아니라 **살아 있는 요구사항**이다. 결정 필요: `mart_customers`에 (a) `churn_prob_calibrated`만 (b) 둘 다 (c) `churn_score`만. 근거: `docs/planning-artifacts/epics.md:579` (부수적으로 :61 · :106 · :339도 개정 전 AD-5 서술)
- [ ] [Review][Decision] **`LogisticRegression()` 기본 L2(`C=1.0`)가 조용히 걸려 있다 — 교과서 Platt이 아니다** — 주석은 "No regularisation sweep ... Platt scaling is a one-parameter (plus intercept) correction by definition"이라 적어 무정규화인 것처럼 읽히지만 sklearn 기본값은 `penalty="l2", C=1.0`이다. 계수를 0쪽으로 수축시켜 보정 곡선을 평탄화하며, 표본 크기·점수 스케일에 따라 보정량이 달라진다. 선택지: (a) `C=1e10`으로 사실상 무정규화 (b) 현행 유지 + 주석을 사실대로 정정. 실측 평균 0.1607은 어느 쪽이든 충족. 근거: `crm/churn/calibrate.py:109-112`

- [x] [Review][Patch] **보정기 계수 부호 미검사 — 적용 완료 (2026-07-22)** — `coef_ <= 0`이면 `apply_calibration`이 **엄격 감소** 함수가 되는데, 절편이 평균을 실제 이탈률에 그대로 맞춰 주므로 **어떤 지표로도 드러나지 않는다**. 재현: 신호 반전 `coef=-10.49`(평균 0.2001 vs 실제 0.2000), 무신호 `coef=-0.185`. 단일 클래스 `y`는 거부하면서 같은 급의 결과를 낳는 이 경로는 열려 있던 것.
      **원 보고 정정**: 세 레이어 모두 "3-1 분면 불변이 무너진다"고 했으나 **틀렸다.** 투트랙 전환 이후 `matrix.py:74 _RISK_AXIS = "churn_score"`로 4분면은 raw OOF를 직접 읽어 보정기를 거치지 않는다. 실제 노출은 **3-2 `expected_saving`** 하나이며, "단조성 = 3-1 불변의 근거"라는 `calibrate.py`·`test_calibrate.py`의 서술은 투트랙 이전 프레이밍의 잔재였다 — 함께 정정했다.
      **현 아티팩트는 무해**: `spearman(churn_score, churn_prob_calibrated) = 1.000000`, 수치 변동 없음. 미래에 조용히 틀릴 경로를 닫은 것.
      조치: `fit_calibrator`가 `coef <= 0`에 fail-fast + 신호 반전/무신호 두 경우를 성질 테스트로 고정. **332 → 334 passed, 회귀 0** [crm/churn/calibrate.py:112] [tests/churn/test_calibrate.py]
- [x] [Review][Patch] `fit_calibrator`가 index 정렬을 검사하지 않는다 — 길이만 검사하고 `.to_numpy()`로 위치 결합. 같은 커밋의 `matrix.py`는 정확히 이 위험을 격렬히 거부하는데 더 위험한 (score, label) 짝짓기가 무방비 [crm/churn/calibrate.py:95-100]
- [x] [Review][Patch] `oof_scores`에 CV 유효성 가드 없음 — `pr_auc_cv`에는 있다. 공개 함수(`__all__`)이며 소수 클래스 < `CHURN_CV_FOLDS`일 때 경고만 뜨고 상수 점수 생성(실측: n=50·양성 3 → 고유값 3개) [crm/churn/model.py:328-330]
- [x] [Review][Patch] `_validate_scores` 오류 메시지가 `apply_calibration` 경로에서도 "fit_calibrator..."라고 말한다 — 존재하지 않는 호출을 디버깅하게 된다 [crm/churn/calibrate.py:60-72]
- [x] [Review][Patch] 검증 순서 역전 — 빈 시리즈 검사가 길이 불일치 검사보다 먼저라, 상류 조인 붕괴가 "empty score series"로 오보고된다. `y`의 유한성·dtype 검사도 없다 [crm/churn/calibrate.py:95]
- [x] [Review][Patch] 테스트 수 330 vs 332 — 실측 `--collect-only` **332**. 커밋 메시지·Completion Notes가 맞고 다음이 틀렸다 [README.md:5] [docs/implementation-artifacts/quadrant-report-3-1.md:3] [3-0-oof-scores-platt-calibration.md:343]. 회고 A1(README stale) 재발 방지를 내건 스토리에서 README가 다시 틀렸다
- [x] [Review][Patch] `quadrant-report-3-1.md`가 옛 아티팩트를 데이터 출처로 계속 지목 — `artifact_id c751c63d5b58`(in-sample)로 새 수치 443/2089/4624/2971을 재현하려다 실패한다. 실제 출처는 `9e1a4d71800f`. 또 :9 "판정 수치 자체는 세 시점에서 동일하다(실현 컷·분면 인원 불변)"는 이번 커밋이 컷을 0.126842→0.132753으로 옮겼으므로 **이제 거짓** [quadrant-report-3-1.md:6,9,10]
- [x] [Review][Patch] `churn-model-report-1-6a.md` 뒷부분 stale — :105 scored 스키마가 아직 3컬럼(`churn_prob`), :111 "artifact_id는 직렬화된 **모델** 바이트의 SHA-256"(AC4로 번들 해시가 됨), :112 컬럼명. 앞부분(:16·:36·:70~88)은 갱신됨 — 문서 앞쪽만 훑은 흔적 [churn-model-report-1-6a.md:105,111,112]
- [x] [Review][Patch] `churn-drivers-actions-1-7.md`가 머리말과 본문에서 반대로 말한다 — 머리말엔 3-0 배너, :103 「소비 규칙」엔 여전히 "`churn_prob`는 미보정 in-sample 순위 신호다 ... 확률 해석 금지". **3-2가 실제로 읽는 절**이다 [churn-drivers-actions-1-7.md:103]
- [x] [Review][Patch] `deferred-work.md` A2 이월 항목이 해소 표기 없이 "여전히 미해소"로 남았다 — 같은 파일이 :41에서 이미 `~~취소선~~ — **해소(1-6b)**` 관례를 쓰고 있는데 3-0은 새 절만 추가하고 기존 항목을 닫지 않았다. 「A2 결정」절도 전부 미래형 [deferred-work.md:44,88]
- [x] [Review][Patch] 스파인 `.memlog.md`가 개정되지 않았다 — 스토리 116행이 지목한 세 곳(`ARCHITECTURE-SPINE.md`·`pipeline-diagram.md`·**`.memlog.md`**) 중 하나가 확인 대상에서 빠졌다. Completion Notes :320-322의 "개정은 AD-5 하나로 충분했다"는 결론은 근거가 불완전 [.memlog.md:18]
- [x] [Review][Patch] `test_matrix.py` docstring이 `churn_score`를 "a probability by contract"라 부른다 — 3-0의 전체 취지(`model.py`: "it is not a probability, and story 3-0 stopped letting the name claim it was")와 정면 모순. 이름만 치환된 흔적 [tests/campaign/test_matrix.py]
- [x] [Review][Patch] AC4 실증 테스트의 "swap"이 퇴화 케이스 — `calibrator: None`은 "다른 보정기"가 아니라 "보정기 부재"다. 계수가 다른 실제 `LogisticRegression` 둘이 서로 다른 id를 낳는지는 미증명 [tests/churn/test_artifact.py]
- [x] [Review][Patch] `structure-guard-coverage.md`가 갱신됐으나 File List·AC6 갱신 대상표 어디에도 없다 — 실제 갱신 문서는 6종이 아니라 7종. Completion Notes :304 "6종 전부 처리"와 커밋 내용이 다르다 [3-0-oof-scores-platt-calibration.md:304,324-337]
- [x] [Review][Patch] `ChurnResult.calibrator: object` — `fit_calibrator`의 반환 타입이 버려져 `calibrator=None`인 결과 객체를 타입 검사기가 막지 못한다 [crm/churn/model.py]
- [x] [Review][Defer] `scale_pos_weight`가 전체 `y`에서 계산돼 폴드 모델에 상속된다 [crm/churn/model.py `make_xgboost`] — deferred, 효과는 작으나 "그 고객을 학습에 쓰지 않았다"는 주장에 하이퍼파라미터 경로의 구멍
- [x] [Review][Defer] `oof_scores`와 `pr_auc_cv`가 폴드 분할을 공유하지 않는다 [crm/churn/model.py] — deferred, 동일 폴드 학습 2회 수행 + "0.9507≈0.9508" 근거를 지킬 테스트 부재
- [x] [Review][Defer] 항등 테스트 3건 + seed 음성 단언 [tests/churn/test_calibrate.py, test_model.py] — deferred, `predict_proba`∈[0,1]·lbfgs 결정론·`to_numpy` 복사는 어떤 결함으로도 실패하지 않는다
- [x] [Review][Defer] 보정기 수렴 미검사(`max_iter`/`n_iter_`) [crm/churn/calibrate.py:112] — deferred, 현 데이터 `n_iter=8`로 여유가 크나 `ConvergenceWarning`은 조용히 통과한다

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
| `structure-guard-coverage.md` | 스캔 파일 수 18→19 / 17→18 (`calibrate.py` 신설) — **초판 표에서 누락됐다가 코드리뷰에서 발견**. 실제 갱신 대상은 6종이 아니라 7종이다 |
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

claude-opus-4-8 (bmad-dev-story 워크플로 수동 수행 — BMAD config가 DX_project를 가리켜 스킬 미사용)

### Debug Log References

**기준선**: HEAD `bb8ea63`, 313 passed.

**RED**: `tests/churn/test_calibrate.py` 선작성 → `ModuleNotFoundError: crm.churn.calibrate`.

**함정 1 실제로 걸렸다 — stage 40행**: docstring을 2줄 늘렸더니 **42행**이 되어 구조 가드가 즉시
빨간불. 두 번 압축해 40행에 맞췄다. 로직은 한 줄도 stage에 넣지 않았고 전부 `fit_and_compare` 안으로
들어갔다. 스토리가 예고한 그대로였다.

**파이프라인 재실행이 01부터 필요했다**: `verify_inputs`가 `StaleInputError: stale config for
features_customers.parquet`로 중단. 3-1이 `QUADRANT_RULE`을 추가하며 `config_hash`가 바뀐 탓이고,
3-1 스토리 Dev Notes가 예고한 그대로다. 01 → 02 → 03 순차 재실행으로 해소.

**연쇄 수정 4건** (계약 변경이 밀어낸 것):
- `tests/churn/test_artifact.py` — scored 컬럼 목록 단언이 3컬럼 → 4컬럼
- `tests/churn/test_stage.py` — `artifact_id` 비교 대상을 `.model` → `.bundle()`
- `tests/churn/test_explain.py` — SHAP 정합 테스트가 저장 점수로 riskiest를 뽑고 있었다. 저장 점수는
  이제 **폴드 모델**의 것이고 `shap_frame`은 **최종 모델**을 설명하므로, 테스트가 확인하려는 대상과
  기준이 어긋난다 → 최종 모델의 자체 점수로 교체(함정 4가 테스트에 실물로 드러난 사례)
- `crm/campaign/matrix.py` — 파라미터·축 이름 `churn_prob` → `churn_score`, 그리고 **docstring이
  stale해진 것**을 함께 정정("A2 미결"·"in-sample 아티팩트" 서술이 남아 있었다)

**AC5 결정론 실증**: 산출물 삭제 후 03을 2회 독립 실행 →
`artifact_id 9e1a4d71800f...` 동일, `churn_scored.parquet` **완전 동일**, `churn_shap.parquet`
**완전 동일**.

### Completion Notes List

- **AC1 충족**: `oof_scores()`가 `cross_val_predict` + seeded `StratifiedKFold`로 각 고객을 **그 고객을
  학습에 쓰지 않은 폴드 모델**이 채점한다. 폴드 분할과 폴드 모델 양쪽에 `seed` 명시 주입. in-sample
  재예측값은 어떤 산출물에도 남지 않는다(`score_customers` 삭제). 실측 평균 **0.1946**(구 0.1976).
  "OOF가 rename이 아님"을 성질로 고정 — in-sample 점수가 OOF보다 **기저율에서 더 멀다**는 테스트.
- **AC2 충족**: `crm/churn/calibrate.py`가 **OOF 점수로** Platt을 적합한다(in-sample로 적합하면 보정
  자체가 낙관 편향 — docstring에 명시). 실측 평균 **0.1607 = 실제 이탈률과 일치**. **엄격 단조**를
  테스트로 고정했고, 이것이 3-1 불변의 근거다.
- **AC3 충족**: `churn_scored.parquet` = `CLIENTNUM` · `churn_score` · `churn_prob_calibrated` ·
  `artifact_id`. 코드에서 `churn_prob` 잔존 **0건**(남은 2건은 이름 변경을 설명하는 주석과 부재를
  단언하는 테스트). **ARCHITECTURE-SPINE AD-5를 개정**했다 — 개정 사유·근거 스토리·이름을 유지하지
  않은 이유를 함께 기재(CAP-5 3차 개정 선례를 따름).
- **AC4 충족**: `ChurnResult.bundle()`이 `{"model", "calibrator"}`를 반환하고 stage가 이것을
  `save_model_with_identity`에 넘긴다. **계약 코드는 한 줄도 재구현하지 않았다** — `serialize_model`이
  이미 `Any`를 받으므로 직렬화 대상만 바뀌었고 `outputs_share_identity`·`identity_is_consistent`는
  그대로다. `artifact_id`가 `c751c63d5b58` → `9e1a4d71800f`로 이동(번들 구성이 바뀌었으니 정상).
- **AC5 충족**: 위 Debug Log의 2회 실행 실증.
- **AC6 충족 — 회고 A3의 첫 적용**: 갱신 대상 6종 전부 처리.
  `quadrant-report-3-1.md`(분면 재산출), `churn-model-report-1-6a.md`(해소 표기),
  `churn-drivers-actions-1-7.md`(세그먼트 평균·기준 모델 고지), `README.md`,
  `ARCHITECTURE-SPINE.md` AD-5, `deferred-work.md`·`sprint-status.yaml`.
- **판정 수치 이동 — 예고와 정확히 일치**: 분면 `446/2086/4621/2974` → **`443/2089/4624/2971`**,
  위험 컷 `0.126842` → **`0.132753`**. 원인은 보정이 아니라 **in-sample → OOF 전환**이고,
  Platt은 예고대로 한 명도 바꾸지 않았다.
- **정직성이 개선된 지점**: 3-1 리포트의 저위험 분면 실제 이탈률이 `0.00%`·`0.03%`에서
  **`0.13%`·`0.67%`**로 올라갔다. 초판의 비현실적으로 깨끗한 0%는 모델이 학습에 쓴 고객을 다시
  맞히고 있었기 때문이며, **작지만 0이 아닌 지금 수치가 실제에 가깝다.**
- **보고 지표는 불변**: `pr_auc_cv()`가 처음부터 홀드아웃이라 헤드라인 **PR-AUC 0.9508 그대로**.
  in-sample이었던 것은 저장 컬럼 하나뿐이었다는 스토리의 사전 판단이 실행으로 확인됐다.
- **1-6a·1-7 스토리 파일은 고치지 않았다**(의도) — 스토리 파일은 그 시점의 역사 기록이고, 이
  프로젝트는 옛 수치를 지우지 않고 병기해왔다(1-7 전후 병기 선례). 살아 있는 문서인 **리포트**만
  갱신했다.
- **테스트**: 313 → **332 passed** (+19), 회귀 0. 구조 가드 전종 green(stage 40행 포함).
- **`pipeline-diagram.md`는 손댈 것이 없었다** — `churn_prob`를 명명하지 않고 있었다(grep 0건).
  AD-5 docstring이 "pipeline diagram fixes that name"이라고 적고 있었으나 **실제로는 스파인에만
  있었다.** 개정은 AD-5 하나로 충분했고, 그 사실을 여기 기록한다.

### File List

- `crm/churn/calibrate.py` — NEW (`fit_calibrator`, `apply_calibration`, `CALIBRATED_COLUMN`)
- `crm/churn/model.py` — UPDATE (`oof_scores`, `SCORE_COLUMN`, `ChurnResult.calibrator`/`bundle()`, `score_customers` 삭제)
- `crm/churn/artifact.py` — UPDATE (docstring 용어)
- `crm/campaign/matrix.py` — UPDATE (축 이름 `churn_score`, stale docstring 정정)
- `pipelines/03_train_churn.py` — UPDATE (번들 저장, 40행 유지)
- `tests/churn/test_calibrate.py` — NEW (12건)
- `tests/churn/test_model.py` · `test_artifact.py` · `test_stage.py` · `test_explain.py` — UPDATE
- `tests/campaign/test_matrix.py` — UPDATE (축 이름)
- `docs/planning-artifacts/architecture/.../ARCHITECTURE-SPINE.md` — UPDATE (**AD-5 개정**)
- `docs/implementation-artifacts/quadrant-report-3-1.md` · `churn-model-report-1-6a.md` · `churn-drivers-actions-1-7.md` — UPDATE
- `docs/implementation-artifacts/deferred-work.md` · `sprint-status.yaml` · `README.md` — UPDATE
- `docs/implementation-artifacts/structure-guard-coverage.md` — UPDATE (스캔 파일 수; 초판 File List 누락분)
- `docs/planning-artifacts/architecture/.../.memlog.md` — UPDATE (**코드리뷰 반영** — 함정 2가 지목했으나 초판에서 빠졌던 세 번째 대상)
- `docs/implementation-artifacts/3-0-oof-scores-platt-calibration.md` — UPDATE (이 파일)

## Change Log

| 날짜 | 변경 |
|---|---|
| 2026-07-22 | 스토리 3-0 구현: OOF 점수(`churn_score`) + Platt 보정(`churn_prob_calibrated`) 투트랙, {model,calibrator} 번들 정체성, AD-5 개정. 분면 443/2089/4624/2971로 이동(원인은 보정 아닌 OOF 전환), PR-AUC 0.9508 불변, 2회 실행 완전 동일. 313 → 332 passed. Status → review |
| 2026-07-22 | 코드리뷰(3레이어) 반영: patch 15건 적용. 보정기 계수 부호·인덱스 정렬·OOF CV 유효성 fail-fast 추가, 오류 메시지 호출자 정정, 검증 순서 교정, `calibrator` 타입 명시, AC4 테스트를 실제 보정기 교체로 강화, 문서 7종 stale 수치·컬럼명 정정(`.memlog.md` 포함 — 초판 누락). **332 → 337 passed, 회귀 0.** decision 4건 미결 |
| 2026-07-22 | 스토리 3-0 create-story(수동 — BMAD config가 DX_project를 가리켜 스킬 미사용). A2 결정(OOF + Platt, 투트랙 컬럼)의 실행 스토리. 함정 4건 사전 기록: stage 40행 포화·`churn_prob`가 스파인에 박힌 이름·artifact_id 번들 확장·보정기는 OOF로 적합. 미해결 설계 질문 1건(SHAP 기준 모델) 명시. Status → ready-for-dev. 기준선 bb8ea63 / 313 passed |
