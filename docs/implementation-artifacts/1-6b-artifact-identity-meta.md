---
baseline_commit: 17fdf7e
baseline_passed: 196
---

# Story 1.6b: 아티팩트 정체성과 churn_model.meta.json (AD-5)

Status: done

> **분할 안내**: 원 스토리 1.6을 1-6a/1-6b로 분할(2026-07-21). **1-6a(done)** = 두 모델·CV·PR-AUC·리프트·라벨(AD-6)·
> 누수 재감사. **1-6b(이 스토리)** = AD-5 아티팩트 **정체성**: `models/churn_model.meta.json` + `artifact_id` +
> `churn_scored`와의 결속 + 불일치 즉시 실패. **1-7 SHAP이 이 정체성 위에 세워진다.**

## Story

As a 분석가,
I want 학습 아티팩트에 콘텐츠 해시 기반 정체성(`artifact_id`)과 메타데이터를 부여하고 점수 산출물과 결속하는 것을,
so that `churn_prob`와 (곧 나올) SHAP 해석이 **같은 학습 실행에서 나왔음을 증명**할 수 있고, 어긋나면 조용히 넘어가지 않고 즉시 실패한다.

## Acceptance Criteria (1-6b 소관 = 원 1.6의 AC3)

**AC1 — `churn_model.meta.json` 기록(AD-5)**
**Given** 학습이 끝났을 때
**When** 아티팩트를 저장하면
**Then** `models/churn_model.meta.json`에 `artifact_id`(모델 바이트의 콘텐츠 해시)·`trained_at`·`RANDOM_SEED`·
**입력 파일 해시**(features_customers·bankchurners)·**feature 목록**(`PREDICTOR_COLUMNS`)·**라이브러리 버전**이 기록된다(AD-5)

**AC2 — `churn_scored.parquet`이 `artifact_id`를 보유**
**Given** 점수가 저장될 때
**When** `churn_scored.parquet`을 확인하면
**Then** 모든 행이 모델 meta와 **동일한** `artifact_id`를 보유한다(AD-5)

**AC3 — 불일치 즉시 실패 + 재실행 유발(1-6a 잔여 High-1 해소)**
**Given** 모델과 점수가 서로 다른 실행에서 나왔을 때
**When** 정체성을 검증하면
**Then** 소비자용 검증 함수가 **즉시 실패**한다(경고 아님, AD-5)
**And** `03_train_churn`의 신선도 게이트가 **불일치를 stale로 판정**해 재실행한다(두 산출물이 한 실행으로 결속됨)

**AC4 — 결정론(AD-7)**
**Given** 동일 입력·동일 seed로 stage를 2회 실행할 때
**When** 두 실행의 `artifact_id`를 비교하면
**Then** 완전히 동일하다. seed 또는 입력이 바뀌면 `artifact_id`도 바뀐다.

> **범위 밖(명시)**: SHAP 산출(1-7), `05_marts`의 입력 identity 실패(4-1/4-x — 이 스토리는 **재사용 가능한 검증
> 함수**만 제공한다), calibration(deferred-work), 모델 성능 변경(1-6a에서 확정 — **재학습 결과가 달라지면 안 된다**).

## Tasks / Subtasks

- [x] **T1. 정체성 모듈 `crm/churn/artifact.py` 확장** (AC: 1, 2, 3, 4) ← 로직 소유, 순수 + 원자적 I/O
  - [x] `artifact_id(model_bytes: bytes) -> str`: `sha256_bytes`(1-1b `crm.common.freshness` **재사용**, 재구현 금지) 기반
        콘텐츠 해시. 순수 함수.
  - [x] `build_model_meta(model_bytes, inputs: list[Path], features: tuple[str, ...], seed: int) -> dict`:
        AD-5 필수 필드 — `artifact_id`·`trained_at`(UTC ISO, `datetime.now(timezone.utc).isoformat()`)·`random_seed`·
        `inputs`(파일명→sha256, `file_sha256` 재사용)·`features`(리스트)·`libraries`(dict).
  - [x] **`metrics` 필드 포함(결정 완료)**: `baseline_pr_auc`·`xgboost_pr_auc`·`pr_auc_lift`·`positive_rate`·`cv_folds`.
        근거: 1-6a 리뷰에서 "비교 지표가 stage 로그와 세션 리포트에만 있어 수동 복사"가 지적됨(deferred-work). 지표는
        **정체성의 일부가 아니라 정체성에 딸린 기록**이므로 `artifact_id` 계산에는 **넣지 않는다**(모델 바이트만 해시).
  - [x] `libraries`: `importlib.metadata.version()`로 `xgboost`·`scikit-learn`·`joblib`·`numpy`·`pandas` + `python`
        (`platform.python_version()`). **하드코딩 금지**(설치본과 어긋나면 기록이 거짓말이 된다).
  - [x] `save_model_with_identity(model, model_path, *, inputs, features, seed, metrics) -> str`:
        `serialize_model`(기존) → `artifact_id` 계산 → 모델 바이트 **원자적 저장** → `churn_model.meta.json` **원자적 저장**
        (`atomic_write_text` + `json.dumps(..., indent=2)`) → `artifact_id` 반환. 기존 `save_model`은 유지하거나 이 함수로
        흡수(호출부 없으면 제거 — File List에 결정 기록).
  - [x] `read_model_meta(model_path) -> dict` / `verify_artifact_identity(expected: str, actual: str, context: str) -> None`:
        불일치 시 **전용 예외로 즉시 raise**(경고·로그 아님, AD-5). 1-7·4-1이 그대로 재사용할 얇은 계약.
  - [x] **AD-5 meta 파일명 함정**: AD-5가 정한 이름은 `models/churn_model.meta.json`이다. `meta_path_for()`는
        `churn_model.joblib.meta.json`을 만든다 — **다른 파일**이다. AD-13 sibling meta와 혼동하지 말고, 이름은
        `model_path.with_suffix(".meta.json")`으로 유도할 것(경로 문자열 하드코딩 금지).
- [x] **T2. `crm/churn/model.py` — scored에 `artifact_id` 컬럼** (AC: 2)
  - [x] `attach_artifact_id(scored: pd.DataFrame, artifact_id: str) -> pd.DataFrame`(순수, 입력 불변):
        `CLIENTNUM`·`churn_prob`·`artifact_id` 3컬럼. 빈 문자열/None `artifact_id`는 **거부**(fail-fast).
  - [x] `ChurnResult`·`fit_and_compare`의 **성능·지표는 건드리지 않는다**. 1-6a 실측(baseline 0.4297 / XGBoost 0.8024 /
        +86.7%)이 그대로 재현되어야 한다 — 달라지면 1-6b가 모델을 바꾼 것이므로 원인 규명 전 커밋 금지.
- [x] **T3. stage `pipelines/03_train_churn.py` 배선** (AC: 1, 2, 3) — ⚠️ **현재 정확히 40행 = 상한**
  - [x] 순서: `verify_inputs` ×2 → 신선도 게이트(아래) → `fit_and_compare` → `save_model_with_identity`(→ `artifact_id`)
        → `attach_artifact_id` → `write_parquet_with_meta`(scored + AD-13 meta).
  - [x] **게이트 강화(AC3)**: 기존 `model_out.exists() and not is_output_stale(...)`에 더해, **모델 meta의 `artifact_id`와
        scored의 `artifact_id`가 일치할 때만 skip**. 불일치·meta 부재·읽기 실패 → **재실행**(fail-closed). 이 판정 로직은
        stage가 아니라 `crm/churn/artifact.py`의 함수 하나(예: `identity_is_consistent(model_path, scored_path) -> bool`)로
        내려 stage는 한 줄로 호출한다(40행 예산 + AD-9 얇은 stage).
  - [x] **40행 초과 시**: 로직을 stage에 쓰지 말고 `crm/`로 더 내릴 것. docstring 축약은 최후 수단. `main` 외 def/lambda
        금지(가드).
- [x] **T4. 테스트** — `tests/churn/test_artifact.py`(NEW) + `tests/churn/test_stage.py`(UPDATE)
  - [x] **정체성 결정론(AC4)**: 동일 입력·seed로 2회 → `artifact_id` 동일. **seed 변경 → 다름**, **입력 변경 → 다름**.
  - [x] **🚨 joblib 바이트 안정성 선검증(착수 직후 첫 실험)**: `serialize_model`의 바이트가 재실행 간 **완전 동일**한지
        먼저 확인하라. 동일하면 그대로 진행. **동일하지 않으면**(joblib/xgboost가 타임스탬프·메모리 주소·딕셔너리 순서를
        섞는 경우) `artifact_id`를 **정규 페이로드**로 재정의한다: `model.get_booster().save_raw(raw_format="json")` +
        `sorted(model.get_params())`의 정규 JSON을 해시. 어느 쪽을 택했든 **근거와 실측을 Debug Log에 기록**하고
        docstring에 정의를 못박을 것(후속 스토리가 해시 정의를 추측하지 않게).
  - [x] **meta 스키마**: AD-5 필수 필드 전부 존재 + 타입 검증. `libraries`가 실제 설치 버전과 일치(하드코딩 변이 KILL).
  - [x] **결속(AC2)**: scored의 `artifact_id` 유니크값이 1개이고 모델 meta의 값과 동일.
  - [x] **불일치 즉시 실패(AC3)**: scored의 `artifact_id`를 손으로 바꾼 뒤 `verify_artifact_identity` → **raise**.
        경고만 하고 통과하는 구현은 이 테스트로 KILL.
  - [x] **stage 통합(AC3)**: ① 정상 2회 실행 → 2회차 skip, `artifact_id`·`churn_prob` 동일. ② scored의 `artifact_id`를
        변조 → **재실행되어** 일관성 복구. ③ 모델 meta 삭제 → 재실행. ④ 모델 파일 삭제 → 재실행(1-6a 회귀).
  - [x] **원자성**: meta 쓰기 실패 시 옛 모델/옛 meta가 남는지(1-1b `write_with_meta` 계약과 동일한 성질) —
        monkeypatch로 실패 주입.
  - [x] 순수성(입력 프레임 불변), ASCII 런타임 문자열.
- [x] **T5. 문서** (AC: 1, 2, 3)
  - [x] `docs/implementation-artifacts/churn-model-report-1-6a.md` — UPDATE: "1-6b 인계" 절을 **완료 상태로 갱신**하고
        실제 `artifact_id`·meta.json 실물(필드 포함 발췌)을 붙인다. 새 리포트 파일을 만들지 말 것(지표 리포트는 1-6a 소유).
  - [x] `docs/implementation-artifacts/deferred-work.md` — UPDATE: 1-6a 잔여 3건 중 **①두 산출물 원자성**(게이트로 해소)과
        **②지표 machine-readable 저장**(meta.json `metrics`로 해소)을 **해소 표기**(`~~취소선~~ — 해소(1-6b)` 패턴, 기존 항목
        서식 따를 것). **③calibration은 미해소로 유지**.
  - [x] `docs/implementation-artifacts/structure-guard-coverage.md` — pytest로 재생성.
- [x] **T6. 실행·커밋**
  - [x] 실데이터로 03 재실행 → `churn_model.meta.json` 생성, `churn_scored.parquet`에 `artifact_id` 컬럼.
        **2회 실행 결정론**(`artifact_id`·`churn_prob` 동일) 실증.
  - [x] `.venv/Scripts/python.exe -m pytest` 전체 green. **기준선 196 passed, 회귀 0.** 스토리 단위 커밋. Obsidian 미러 갱신.

## Dev Notes

### 이 스토리의 한 문장

**모델 바이트를 해시해 이름표를 만들고, 그 이름표를 점수 산출물에 새기고, 이름표가 어긋나면 즉시 실패시킨다.**
모델 성능·지표·라벨 표기는 1-6a에서 끝났다 — 여기서 숫자가 바뀌면 잘못한 것이다.

### `artifact_id`가 해결하는 실제 문제 (1-6a 리뷰 High-1 잔여)

`models/`는 gitignore라 사후 탐지가 불가능하다(AD-5 Prevents). 1-6a는 `save_model` → `write_parquet_with_meta`
**사이에 crash**하면 "새 모델 + 옛 점수"가 공존하는 창을 남겼다. 완전성 게이트(model 존재 + scored 신선)로
skip-forever는 막았지만 **두 산출물이 같은 실행에서 나왔는지는 증명하지 못했다.**

1-6b의 해법: 점수에 모델의 콘텐츠 해시를 새긴다. 그러면 그 창에서 crash가 나도 다음 실행이 **불일치를 보고 재실행**하고,
소비자(1-7 SHAP·4-1 마트)는 **읽는 순간 검증**할 수 있다. crash 창 자체가 사라지는 건 아니다 — **탐지 불가에서
자동 복구로** 바뀌는 것이다. 리포트에 이 정확한 표현으로 쓸 것(과장 금지).

### `artifact_id`의 정의와 한계 (docstring에 못박을 것)

- **정의**: 모델 **바이트**의 SHA-256. 따라서 *같은 데이터·같은 seed*로 재학습하면 **같은 id**가 나온다(의도된 성질 —
  내용이 같으면 같은 아티팩트다).
- **한계(정직하게 기재)**: `artifact_id`는 **입력 드리프트를 탐지하지 않는다.** 그건 AD-13 `.meta.json`(config_hash +
  input hash)의 일이고 이미 stage 게이트에 배선돼 있다. 두 장치는 **역할이 다르다**: AD-13 = "다시 계산해야 하나?",
  AD-5 = "이 두 산출물이 같은 실행에서 나왔나?". 둘을 하나로 합치려 하지 말 것.
- 입력 해시·seed·feature 목록은 meta.json에 **기록**되지만 `artifact_id` **계산에는 들어가지 않는다**(그것들이 바뀌면
  모델 바이트가 바뀌고, 바이트가 안 바뀌었다면 그건 같은 모델이 맞다).

### 재사용할 것 (재발명 금지)

| 필요 | 이미 있는 것 | 위치 |
|---|---|---|
| 해시 | `sha256_bytes` / `file_sha256` | `crm/common/freshness.py` |
| 원자적 바이트/텍스트 쓰기 | `atomic_write_bytes` / `atomic_write_text` | `crm/common/atomic.py` |
| parquet + AD-13 meta | `write_parquet_with_meta` / `build_meta` | `crm/common/atomic.py`·`freshness.py` |
| 모델 직렬화 | `serialize_model`(bytes 반환 — 1-6a가 **이 스토리를 위해** 이렇게 설계함) | `crm/churn/artifact.py` |
| 신선도 2단 게이트 | `verify_inputs` + `is_output_stale` | `crm/common/freshness.py` |
| feature 목록 | `PREDICTOR_COLUMNS` | `crm/churn/model.py` |

`hashlib`·`json`을 stage에서 직접 부르지 말 것(AD-9: stage는 `crm.*`·pandas·logging만).

### 구조 가드 — 걸리기 쉬운 지점

- **AD-9 stage 형태**: `pipelines/03_train_churn.py`는 **현재 정확히 40행(상한)**. 한 줄이라도 늘리려면 다른 줄을 줄이거나
  로직을 `crm/`로 내려야 한다. `main` 외 def/class/**lambda** 전면 금지(중첩 포함).
- **AD-1 레인**: `crm/churn`은 `crm/ltv`를 참조 불가. 정체성 코드는 **`crm/churn/artifact.py`**에 둔다 —
  `crm/common`에 두면 stateful-common·레인 가드와 부딪히고, 이 계약은 churn 레인 소유다.
- **AD-11**: `Total_Trans_Amt`를 어떤 형태로도 언급 금지(`features` 목록은 `PREDICTOR_COLUMNS` = RFM 프록시 3개라 무관).
- **AD-4**: 새 config 상수는 필요할 때만. `artifact_id` 해시 알고리즘 이름 같은 건 상수화하지 말고 코드에 고정.
- **AD-1(데이터 유래 금지)**: 실측 지표(0.8024 등)를 config나 코드에 하드코딩하지 말 것 — meta.json에 **런타임 기록**이다.

### 1-6a에서 물려받은 규율

- 테스트는 **성질 + 하드코딩 oracle + 배선 실증**. 1-6a 리뷰 교훈: 함수 단위 테스트는 stage 배선 회귀를 못 잡는다 →
  `tests/churn/test_stage.py`의 실제 `main()` 실행 패턴(`_load_stage_03`·`_seed_inputs`)을 **그대로 재사용**한다.
- **fail-fast > 조용한 관용**: 1-6a High-2(알 수 없는 라벨을 0으로) 교훈. 불일치·부재·파싱 실패는 전부 **실패 또는 재실행**,
  경고 후 진행 금지.
- **문서가 테스트를 앞서지 않기**: 리포트에 "정체성이 보장된다"고 쓰기 전에 그 성질을 KILL하는 테스트가 있어야 한다.
- ASCII 런타임 문자열, `.venv/Scripts/python.exe -m pytest`, 순수 함수 우선.

### 예상 마찰 (미리 알고 시작할 것)

1. **joblib 바이트 비안정성** — T4 첫 항목. 안정하지 않으면 정규 페이로드 해시로 전환(경로 이미 명시).
2. **config drift 없음 예상** — 새 config 상수를 안 넣으면 `config_hash` 불변 → 01/02 재실행 불필요. 1-3/1-4/1-6a처럼
   전체 재실행이 필요하지 않을 가능성이 높다(상수를 추가하면 필요해진다 — 추가를 피할 이유).
3. **scored 스키마 변경** — `artifact_id` 컬럼이 추가되면 **기존 `churn_scored.parquet`은 구 스키마**다. 게이트가
   meta 부재/불일치로 재실행하므로 자동 해소되지만, 테스트 픽스처가 구 스키마를 가정하지 않는지 확인할 것.
4. **`pandas 3.0.3` + `pyarrow 25`** 환경. 문자열 컬럼 반복은 parquet에서 dictionary 인코딩되므로 10,127행 × 64자
   해시의 저장 비용은 무시할 수준이다(컬럼으로 두라는 AC를 우회하지 말 것).

### Project Structure Notes

```
crm/churn/artifact.py                    # UPDATE - artifact_id·build_model_meta·save_model_with_identity·
                                         #          read_model_meta·verify_artifact_identity·identity_is_consistent
crm/churn/model.py                       # UPDATE - attach_artifact_id(순수). 모델·지표 로직은 불변
pipelines/03_train_churn.py              # UPDATE - identity 배선 + 게이트 강화 (⚠️ 40행 상한)
tests/churn/test_artifact.py             # NEW    - 정체성 결정론·meta 스키마·불일치 실패·원자성
tests/churn/test_stage.py                # UPDATE - 변조/삭제 시 재실행, 2회 실행 identity 동일
docs/implementation-artifacts/churn-model-report-1-6a.md      # UPDATE - 1-6b 인계 절 완료화 + meta 실물
docs/implementation-artifacts/deferred-work.md                 # UPDATE - 잔여 2건 해소 표기
docs/implementation-artifacts/structure-guard-coverage.md      # UPDATE - 재생성
```

- 출력: `models/churn_model.joblib` + **`models/churn_model.meta.json`**(둘 다 gitignore),
  `data/churn_scored.parquet`(+ AD-13 `.meta.json`, + `artifact_id` 컬럼).
- 새 config 상수 없음이 기본값. 새 모듈 없음 — 기존 `crm/churn/artifact.py` 확장.

### 환경 실측 (2026-07-21)

```
python 3.12.10 | xgboost 3.3.0 | scikit-learn 1.9.0 | joblib 1.5.3
pandas 3.0.3 | numpy 2.5.1 | pyarrow 25.0.0
HEAD 17fdf7e | 196 passed
```

### References

- [Source: docs/planning-artifacts/epics.md#Story 1.6] — AC3 원문(meta.json 필드·scored artifact_id 보유)
- [Source: .../ARCHITECTURE-SPINE.md#AD-5] — 정체성 규칙, 05_marts 즉시 실패, models/ gitignore 근거
- [Source: .../ARCHITECTURE-SPINE.md#AD-9] — stage 얇음(40행·main only), 레인·계층
- [Source: .../ARCHITECTURE-SPINE.md#AD-13] — config_hash·input hash는 **다른 장치**(역할 혼동 금지)
- [Source: docs/implementation-artifacts/1-6a-churn-model-baseline-lift.md] — 리뷰 High-1 잔여, `serialize_model` 설계 의도
- [Source: docs/implementation-artifacts/deferred-work.md#1-6a] — 이 스토리가 해소할 2건, 유지할 1건(calibration)
- [Source: docs/planning-artifacts/epics.md#Story 1.7] — 소비자 계약(동일 artifact_id 유래 검증, 불일치 즉시 실패)
- [Source: 실측 2026-07-21] — 라이브러리 버전·기준선 196 passed

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (bmad-dev-story)

### Debug Log References

**기준선**: HEAD `b79e92b`, 196 passed. 새 의존성 없음, 새 config 상수 없음 → `config_hash` 불변 → 01/02 재실행 불필요
(예상대로 03만 재실행됨).

**joblib 바이트 안정성 선검증(T4 첫 항목, 결론: 안정)**:
```
동일 프로세스 2회 fit -> sha256 2c25ea56... 동일 (249,652 bytes)
별도 프로세스 2회 실행  -> sha256 2c25ea56... 동일
booster.save_raw(json)  -> 50d341de... 동일 (대체 경로도 안정하나 불필요)
```
→ `artifact_id = sha256(joblib bytes)`로 **확정**. 정규 페이로드 대체 경로는 쓰지 않았고, 정의를 `artifact.py`
모듈 docstring에 못박았다.

**stage 40행 예산**: identity 배선으로 43행 → docstring 3줄 축약·주석 2줄→1줄·`if __name__` 앞 공백 1줄 정리로
정확히 40행. 판정 로직은 `identity_is_consistent` 한 줄 호출로 crm에 내림(AD-9).

**`write_with_meta` 확장(재사용 결정)**: AD-5 record는 `churn_model.meta.json`이라 `meta_path_for()`가 만드는
AD-13 sibling(`churn_model.joblib.meta.json`)과 이름이 다르다. 롤백 로직을 복제하는 대신 `write_with_meta`에
선택 인자 `meta_path`를 추가(기본값은 기존 동작 그대로 = 하위호환). 덕분에 모델+정체성 기록도 1-1b와 **동일한
all-or-nothing 계약**을 갖는다.

**실데이터 결과**(n=10,127):
```
artifact_id 2f7f09ec0703de6b3057b2fa2ab6d9922d41597adc166da05d7c4334a742851d
churn_scored 10,127행 전부 동일 id (unique = 1)
metrics 기록: baseline 0.4297 / xgb 0.8024 / lift +86.7% / positive_rate 0.1607 -> 1-6a와 완전 일치(모델 불변 확인)
2회차 실행 -> skip(trained_at 불변), 별도 출력 경로 재실행 -> artifact_id·churn_prob 완전 동일(AD-7)
```

**테스트 검출력(변이 5종, 전부 KILLED)**:
| 변이 | 결과 |
|---|---|
| `verify_artifact_identity`가 raise 대신 통과 | KILLED (test_verify_artifact_identity_raises_on_mismatch) |
| `identity_is_consistent`가 항상 True | KILLED (test_tampered_scored_identity_forces_a_rerun) |
| `artifact_id`가 모델 바이트를 무시(상수 해시) | KILLED (test_artifact_id_changes_when_the_training_data_changes) |
| `libraries` 버전 하드코딩 | KILLED (test_meta_library_versions_are_read_from_the_environment) |
| `attach_artifact_id`가 빈 id 허용 | KILLED (test_attach_artifact_id_rejects_a_missing_id) |

### Completion Notes List

- **AC1 충족**: `models/churn_model.meta.json`에 `artifact_id`·`trained_at`(UTC ISO)·`random_seed`·입력 2건 sha256·
  `features`(RFM 프록시 3개)·`libraries`(6종, `importlib.metadata` 실측)·`metrics`(5개) 기록. 실물은 1-6a 리포트에 첨부.
- **AC2 충족**: `churn_scored.parquet`이 `CLIENTNUM`·`churn_prob`·`artifact_id` 3컬럼. 10,127행 전부 동일 id.
- **AC3 충족**: `verify_artifact_identity`는 불일치 시 `ArtifactIdentityError`로 **즉시 raise**(경고 아님).
  stage 게이트는 `identity_is_consistent`(fail-closed)로 불일치·기록 부재·읽기 실패를 전부 **재실행**으로 처리 —
  변조·meta 삭제·모델 삭제 3종 통합 테스트로 실증. 정상 상태에서는 skip(무한 재실행 아님)도 테스트로 고정.
- **AC4 충족**: 동일 입력·seed 2회 → `artifact_id` 동일(실데이터 + 합성 양쪽). seed 변경·입력 변경 → 다른 id.
- **모델 불변 확인**: 1-6a 실측 지표(0.4297 / 0.8024 / +86.7% / 0.1607)가 소수점까지 동일 재현. 1-6b는 정체성만 추가했다.
- **정직성**: crash 창은 사라지지 않았다. "탐지 불가 → 자동 복구"로 바뀐 것이며 코드 docstring·리포트·deferred-work에
  같은 표현으로 기재했다.
- **`save_model` 유지 결정**: 호출부는 없지만 "정체성 없는 저장"과 "정체성 있는 저장"의 대비를 남기는 편이 후속
  스토리에 안전하다고 판단해 유지하고, docstring에 파이프라인은 `save_model_with_identity`를 쓴다고 명시했다.
- **구조 가드 전종 green**(stage 40행·main only·레인·계층·AD-11·stateless common·config 단일).
- **테스트**: 196 → **224 passed**, 회귀 0.

### File List

- `crm/churn/artifact.py` — UPDATE, `artifact_id`·`model_meta_path`·`library_versions`·`build_model_meta`·
  `save_model_with_identity`·`read_model_meta`·**`read_verified_model_meta`**·`verify_artifact_identity`·
  `identity_is_consistent`·`ArtifactIdentityError`. 리뷰 반영으로 `save_model` 삭제
- `crm/churn/model.py` — UPDATE, `attach_artifact_id`(순수) + `ChurnResult.metrics()`
- `crm/common/atomic.py` — UPDATE, `write_with_meta(..., meta_path=None)` 선택 인자(하위호환)
- `pipelines/03_train_churn.py` — UPDATE, identity 배선 + 게이트 강화(40행 유지)
- `tests/churn/test_artifact.py` — NEW, 정체성 정의·meta 스키마·라이브러리 실측·원자성·결속·fail-closed 24건
- `tests/churn/test_stage.py` — UPDATE, 정체성 스탬프·변조/기록삭제 재실행·정상 skip 4건 추가
- `docs/implementation-artifacts/churn-model-report-1-6a.md` — UPDATE, AD-5 정체성 절 + meta.json 실물
- `docs/implementation-artifacts/deferred-work.md` — UPDATE, 1-6a 잔여 2건 해소 표기(calibration은 유지)
- `docs/implementation-artifacts/1-6b-artifact-identity-meta.md` — UPDATE, 본 기록
- `docs/implementation-artifacts/sprint-status.yaml` — UPDATE, 상태 전이

## Senior Developer Review (외부 GPT, 2026-07-21)

**판정: Request changes** — High 1, Medium 4, Low 2. **7건 전부 처리**(반려 0).
설계 방향(콘텐츠 해시·metrics 분리·AD-5/AD-13 분리·fail-closed 게이트)은 통과 확인받음.

### 실증 확인 (패치 전, `scratch/repro_1_6b.py`)

| # | 심각도 | 주장 | 실증 |
|---|---|---|---|
| 1 | **High** | 게이트가 meta와 scored만 비교하고 **디스크 모델 바이트를 검증하지 않음** | ✅ seed 7 모델로 바꿔치기 → `identity_is_consistent` **True**, stage **skip**, 바꿔치기 유지 |
| 2 | Med | 학습 seed와 meta 기록 seed가 어긋날 수 있음 | ✅ config를 7로 바꿔도 모델은 seed 42 산물인데 meta엔 **7** 기록 |
| 3 | Med | `artifact_id`는 same run이 아니라 same content | ✅ 2회 실행 `trained_at` 다르나 id 동일, runB 모델+runA 점수 조합 통과 |
| 4 | Med | `save_model`이 유효 meta를 `{}`로 덮어씀 | ✅ 7필드 → `{}` 확인 |
| 5 | Med | `write_with_meta(meta_path=target)` 허용 | ✅ 모델 파일에 JSON만 남고 **오류 없음** |
| 6-7 | Low | 결정론 주장 범위·fail-closed 원인 은폐 | ✅ 확인 |

### 적용한 패치

- **[High]** `read_verified_model_meta()` 신설 — 기록 + **디스크 파일 sha256**을 함께 검증. `identity_is_consistent`가
  이 함수만 사용하도록 교체(소비자 1-7·4-1도 이것을 쓴다). `read_model_meta`에 **id 형식 검증**(64자 소문자 hex) 추가 —
  `42`·대문자·63자 등은 거부. 재현 시나리오를 그대로 회귀 테스트로 고정(바꿔치기·1바이트 손상·파일 부재).
- **[Med-1]** stage가 `seed = config.RANDOM_SEED` 한 값을 잡아 **`fit_and_compare`와 meta 양쪽에 주입**(AD-7 명시 주입).
  `monkeypatch`로 seed 7을 넣고 **실제 모델이 seed 7 산물인지 해시로 대조**하는 테스트 추가.
- **[Med-2]** 문구 정정: "같은 학습 실행" → **"같은 모델 내용"**. 모듈 docstring·리포트·예외 메시지 전부.
  `run_id`(nonce) 분리는 요구하는 소비자가 없어 도입하지 않음(근거를 docstring에 기재).
- **[Med-3]** `save_model` **삭제**(`__all__` 포함). 호출부 0건 확인 후 제거 — "대비용 보존"은 근거가 못 된다는 지적 수용.
- **[Med-4]** `write_with_meta`가 `target`과 `meta_path`의 **resolve() 동일성**을 거부(symlink·alias 포함). 회귀 테스트 추가.
- **[Low-1]** 결정론 주장을 **고정 실행 환경 범위**로 한정(인터프리터·라이브러리·플랫폼 이동 시 다른 id 가능,
  단 방향은 보수적 안전). docstring·리포트에 명시.
- **[Low-2]** `identity_is_consistent`가 재실행 **사유를 로깅**(모델 해시 불일치 / 컬럼 부재 / 다중 id / 값 불일치 /
  scored 부재). 원인 은폐 없이 비싼 재학습의 이유를 남긴다.

### 패치 후 재검증

- 재현 스크립트 재실행: High **False→재실행으로 원본 복구**, Med-1 **meta 7 = 실제 학습 7**, Med-3 **함수 부재로 재현 불가**,
  Med-4 **ValueError로 거부**. Med-2는 설계상 유지(문구로 해소).
- 변이(파일 해시 검증 제거) → 테스트 4건 동시 **KILLED**.
- 실데이터 재검증: 디스크 해시 = meta = scored id, seed 42, lift +86.7%(1-6a 불변). 구조 가드 전종 0 위반.
- **224 → 237 passed**, 회귀 0.

## Senior Developer Review 2차 (외부 GPT, 2026-07-21)

**판정: Request changes** — High 1, Medium 5, Low 3.
**결과: 6건은 1차에서 이미 반영된 항목(리뷰어가 diff의 pre-image를 현재 코드로 읽음), 3건은 유효한 신규 지적 → 처리.**

### 이미 반영돼 있던 항목 (HEAD 실물 대조)

리뷰가 인용한 코드는 전부 `3acfe8b` **이전** 상태다. `rereview-1-6b.fixes.full.diff`의 `-` 라인(제거된 코드)을
현재 코드로 읽은 것으로 보인다. HEAD(`5d894c6`) 실물:

| 2차 지적 | HEAD 실물 | 위치 |
|---|---|---|
| High-1 모델 바이트 미검증 | `expected = read_verified_model_meta(model_path)[...]` (파일 sha256 검증 포함) | `artifact.py` |
| Med-1 seed 미주입 | `seed = config.RANDOM_SEED` → `fit_and_compare(..., seed=seed)` + meta | `03_train_churn.py:29-32` |
| Med-3 `meta_path==target` | `must differ from the output path` 가드 | `atomic.py:102` |
| Med-4 `save_model` 잔존 | 함수·`__all__` 모두 부재(`grep -c "def save_model(" = 0`) | `artifact.py` |
| Low-2 id 형식 미검증 | `_ID_PATTERN = re.compile(r"\A[0-9a-f]{64}\Z")` | `artifact.py:84` |
| Med-2 same run 문구 | 이미 "same model content"로 정정 완료 | docstring·리포트·예외 메시지 |

재현 스크립트로도 재확인: High **False→재실행 복구**, Med-1 **meta 7 = 실제 학습 7**,
Med-3(=1차 Med-4) **ValueError 거부**, Med-4(=1차 Med-3) **함수 부재**.

### 유효한 신규 지적 (실증 후 처리)

- **[Med-5-2] nullable stamp가 `TypeError`를 던짐** — ✅ **실재 확인**: `artifact_id` 컬럼이 전부 `pd.NA`이면
  `ids[0] != expected`가 `pd.NA`가 되고 caller의 `if`에서 `TypeError: boolean value of NA is ambiguous`가
  **fail-closed 함수 밖으로 전파**됐다. → null·비문자열 stamp를 명시 거부하고 `False` 반환. 변이(가드 제거)로 KILL 확인.
- **[Med-5-3] 예외 catch 범위** — 유효. parquet 백엔드가 무엇을 던지든 게이트의 답은 "재계산"이므로
  read 구간을 `except Exception`으로 넓히고 **그 판단 근거를 주석에 명시**(넓힌 게 실수로 보이지 않도록).
  깨진 parquet 파일 회귀 테스트 추가.
- **[Med-5-1] 모델 파일 부재 시 True 가능** — ❌ **재현 실패**: `read_verified_model_meta`가 이미 존재를 검사해
  `False`였다. 다만 "stage의 `exists()`에 우연히 기대고 있다"는 우려는 타당하므로 **helper 단독 호출 회귀 테스트**를 추가해
  고정했다(1-7·4-x가 직접 재사용할 때를 대비).
- **[Low-1] cross-process 결정론이 테스트로 고정 안 됨** — 유효. 같은 pytest 프로세스 2회 학습은 근거가 약하다는 지적
  수용 → **subprocess로 인터프리터를 새로 띄워 2회 실행하고 id 동일성을 검증**하는 테스트 추가.
- **[Low-3] seed/데이터 변경 테스트가 계약을 과잉 주장** — 유효. 계약은 "바이트가 다르면 id가 다르다"이지
  "seed가 다르면 반드시 바이트가 다르다"가 아니다. → 테스트명을 `..._on_this_fixture`로 바꾸고 **픽스처 기반 회귀임을
  주석에 명시**(계약 진술이 아님).
- **[리뷰어 지적] 재현 스크립트의 Med-3 출력이 고정 문자열** — 타당. `hasattr`·`__all__`을 **실제로 검사**하도록 수정.

### 재검증

- 237 → **242 passed**, 회귀 0. 구조 가드 전종 0 위반. 변이(NA 가드 제거) KILLED.

## Change Log

| 날짜 | 변경 |
|---|---|
| 2026-07-21 | 스토리 1-6b create-story: AD-5 정체성(artifact_id·churn_model.meta.json·scored 결속·불일치 즉시 실패·게이트 강화). meta에 `metrics` 포함 결정. Status → ready-for-dev. 기준선 196 passed |
| 2026-07-21 | 스토리 1-6b 구현: artifact_id=sha256(joblib bytes) 확정(바이트 안정성 실측), meta.json 7필드+metrics, scored 결속, 게이트 fail-closed, write_with_meta meta_path 확장. 1-6a 지표 완전 재현. 196 → 224 passed, 회귀 0. Status → review |
| 2026-07-21 | 스토리 1-6b done. 외부리뷰 2라운드(1차 7건·2차 신규 3건) 반영 완료, 242 passed. 1-7 SHAP이 read_verified_model_meta/verify_artifact_identity를 인계받는다 |
| 2026-07-21 | 2차 재리뷰: 9건 중 6건은 1차 반영분 재지적(pre-image 오독, HEAD 대조로 확인), 신규 3건 처리 — NA/비문자열 stamp fail-closed 복구(TypeError 전파 실재), 예외 범위 확대+근거 주석, subprocess 결정론 테스트, 테스트 문구 정정. 237 → 242 passed |
| 2026-07-21 | 외부 GPT 리뷰 7건 처리(High 1·Med 4·Low 2): 디스크 모델 해시 검증(read_verified_model_meta)·id 형식 검증·seed 명시 주입·save_model 삭제·meta_path 충돌 차단·"same run"→"same content" 문구 정정·재실행 사유 로깅. 224 → 237 passed, 회귀 0 |
