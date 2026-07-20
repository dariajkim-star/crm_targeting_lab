---
baseline_commit: a4d304c96ffddf88557ef7a7516c7240875163e1
---

# Story 1.1b: 신선도·원자적 쓰기 규약과 데이터 확보

Status: done

## Story

As a 분석가,
I want 단계 산출물의 신선도 검증·원자적 쓰기 규약과 재실행 가능한 데이터 확보 스크립트를,
so that 이후 모든 파이프라인 단계가 stale한 부분 재실행과 반쯤 쓰인 산출물로부터 보호된다.

## Acceptance Criteria

**AC1 — 신선도·원자적 쓰기 유틸**
**Given** 신선도·원자적 쓰기 유틸을 `crm/common/`에 둘 때
**When** 유틸을 사용하면
**Then** `<output>.meta.json`(입력 파일 SHA-256·`config_hash`·코드 커밋·생성 시각·행수)을 쓰는 단일 경로가 제공된다(AD-13)
**And** 산출물 쓰기는 임시 파일 → 원자적 rename 경로만 제공하며, 실패 시 부분 산출물을 남기지 않는다(AD-13)
**And** 입력 meta 검증 함수가 (a) 입력이 자기 선행 단계 산출물인지 (b) 입력 `config_hash`가 현재 `crm/config.py` 해시와 일치하는지 확인하고 불일치 시 실패시킨다
**And** 유틸은 stateless 순수 함수이며, 쓰기 *메커니즘*은 `crm/common/atomic.py`가 단독 소유하고 *경로·정책*은 호출부(`pipelines/`)가 정한다(AD-1·AD-9, 2026-07-20 컨벤션 개정)

**AC2 — 신선도 규약 검증**
**Given** 신선도 규약을 검증해야 할 때
**When** pytest를 실행하면
**Then** `config_hash` 불일치·선행 단계 불일치 상황에서 **실패가 실제로 발생함**을 확인하는 테스트가 있다(경고로 통과하지 않음)
**And** 쓰기 도중 예외 발생 시 대상 경로에 파일이 생성되지 않음을 검증한다

**AC3 — 데이터 확보 파이프라인**
**Given** `pipelines/01_download.py`를 실행할 때
**When** BankChurners·Online Retail II를 확보하면
**Then** 두 원본이 `data/`에 저장되고 gitignore되며, 각 산출물에 `.meta.json`이 함께 기록된다(AD-13)
**And** 스크립트는 `main(input_paths, output_paths)` 시그니처를 따르고 40행 이하이며 `main` 외 `def`를 정의하지 않는다(AD-8·AD-9)
**And** 1.1a의 구조 가드 테스트가 이 새 파일에 대해 통과한다

**AC4 — 실패 처리와 문서화**
**Given** 데이터 확보가 실패하거나 원본을 구할 수 없을 때
**When** 스크립트를 실행하면
**Then** 실패가 명시적으로 보고되고 부분 산출물·빈 파일을 남기지 않는다
**And** 확보 절차와 폴백(수동 다운로드 경로)이 README에 문서화된다(NFR5)

## Tasks / Subtasks

- [x] **T1. 의존성 추가** (AC: 3)
  - [x] `requirements.txt` core 블록에 `pyarrow`(parquet 엔진 — **현재 미설치, pandas 3에서 parquet 쓰려면 필수**)와 `kagglehub` 추가 후 설치
  - [x] 설치 실측 버전을 완료 노트에 기록
- [x] **T2. `crm/common/freshness.py`** (AC: 1)
  - [x] `file_sha256(path) -> str`, `config_hash() -> str`(`crm/config.py` 소스 바이트의 SHA-256), `code_commit() -> str | None`(git 실패 시 None, 예외 전파 금지)
  - [x] `build_meta(inputs, rows, stage) -> dict` — 순수 함수, 파일 접근은 인자로 받은 경로 해싱만
  - [x] `verify_inputs(input_paths, expected_stage) -> None` — (a) 각 입력의 `.meta.json`이 존재하고 `stage`가 기대 선행 단계인지 (b) `config_hash`가 현재 값과 일치하는지 검사, **불일치 시 raise**
  - [x] stateless: 클래스·모듈 전역 가변 상태 금지(1.1a 가드가 `fit` 계열 클래스를 잡지만, 그 외 상태도 두지 말 것)
- [x] **T3. `crm/common/atomic.py`** (AC: 1)
  - [x] `atomic_write_bytes(path, data)` / `atomic_write_text(path, text)` — 동일 디렉터리 임시파일 → `os.replace`
  - [x] `atomic_write_parquet(path, df)` — 임시파일에 쓰고 rename
  - [x] `write_with_meta(path, writer, meta)` — 산출물과 `<path>.meta.json`을 **둘 다 성공했을 때만** 남기는 단일 경로. 산출물 rename 후 meta 쓰기가 실패하면 산출물도 되돌린다(meta 없는 고아 산출물은 다음 단계의 `verify_inputs`를 깨뜨림)
  - [x] 예외 시 임시파일 정리(`finally`)
- [x] **T4. 신선도·원자성 테스트** (AC: 2)
  - [x] `config_hash` 불일치 입력 → `verify_inputs`가 raise 실증
  - [x] 선행 단계 불일치(`stage` 값이 다른 meta) → raise 실증
  - [x] `.meta.json` 자체가 없는 입력 → raise 실증
  - [x] 쓰기 중 예외(writer가 raise) → 대상 경로에 파일이 **생성되지 않음** + 임시파일 잔여 0건 실증
  - [x] meta 쓰기 실패 시 산출물도 남지 않음 실증
- [x] **T5. `pipelines/01_download.py`** (AC: 3, 4)
  - [x] `main(input_paths, output_paths)` 시그니처, **40행 이하**, `main` 외 `def`/`class` 금지 — 로직은 전부 `crm/common/acquisition.py`로
  - [x] `crm/common/acquisition.py`: `acquire_kaggle_csv(slug, filename_glob, dest_parquet) -> int`(행수 반환) — 데이터셋 **비의존 범용** 헬퍼(AD-1: 레인 값이 섞이지 않음)
  - [x] 두 데이터셋을 **순차 처리**: A를 쓰고 프레임 해제(`del`) 후 B 로드(AD-1 정신을 01단계에도 적용)
  - [x] 실패 시 폴백 안내 출력 + **비영(non-zero) 종료**, 부분 산출물 없음
- [x] **T6. 구조 가드 확장 — `main` 시그니처 검증** (AC: 3, deferred D1 해소)
  - [x] `find_pipeline_shape_violations`에 `main` **존재 + 정확한 파라미터 이름 `(input_paths, output_paths)`** 검사 추가(AD-8)
  - [x] 자기검증 픽스처 추가: `main` 없음 / 파라미터 이름 다름 → 각각 검출 실증
  - [x] `deferred-work.md`의 D1 항목을 해소 처리
- [x] **T7. 커버리지 리포트 전환 확인** (AC: 3)
  - [x] `pytest` 후 `structure-guard-coverage.md`에서 **`AD-8 pipeline shape` 행이 "0 - NO FILES IN SCOPE YET" → `1`로 전환**됨을 확인하고 완료 노트에 기록(1.1a가 남긴 인계 사항)
  - [x] `AD-9 campaign order`는 여전히 0건이어야 정상(3.1 소관)
- [x] **T8. README 데이터 확보 문서화** (AC: 4)
  - [x] 실행 명령, 두 데이터 출처·라이선스, 수동 폴백 절차
  - [x] **`python -m pipelines.01_download`은 불가**(모듈명이 숫자로 시작 — 실측 확인)임을 명시하고 `python pipelines/01_download.py`로 안내
- [x] **T9. 실행·커밋**
  - [x] 실데이터 다운로드 **실제 실행**(conventions 3항 — 합성 mock 초록으로 done 금지), 행수를 완료 노트에 기록
  - [x] `pytest` 전체 green, 스토리 단위 커밋

### Review Findings

3-레이어 병렬 리뷰(2026-07-20): Blind 11건 / Edge 15건 / Auditor 7건 → 병합 후 **decision 2 / patch 15 / defer 4 / dismiss 3**. 교차 검증(2개 이상 레이어 일치) 5건. Auditor 실측 재확인: 61 passed, 실아티팩트 크기·meta 5필드·커버리지 행 전환·D1 해소 전부 사실. AC 판정 AC1 조건부 / AC2·AC3 PASS / AC4 PASS(caveat).

- [x] [Review][Decision→Patch] **DQ1. 파일 쓰기 계층 — 스토리 T5 설계 vs 스파인 컨벤션 충돌** [crm/common/acquisition.py] (auditor, F1). 스파인 Consistency Conventions와 AC1 마지막 절은 "파일 쓰기는 **오직 `pipelines/` 계층에서만**"이라고 못 박는데 `store_csv_as_parquet`가 `write_with_meta`를 직접 호출한다. **원인은 dev 일탈이 아니라 스토리 T5가 그 구조를 지시한 것.** → **사용자 결정: 옵션1 — 컨벤션을 현실에 맞게 개정**(P1 2-2 선례). 쓰기의 *메커니즘*은 `crm.common.atomic`이 단일 소유하고, *무엇을 어디에 쓸지 정하는 정책*은 `pipelines/`가 소유하는 것으로 스파인·AC1 문구를 소급 개정. 40행 제약과도 양립.
- [x] [Review][Decision→Defer] **DQ2. `verify_inputs`가 기록된 입력 해시를 대조하지 않음 — AD-13 대표 시나리오 미차단** [crm/common/freshness.py] (blind, **High**). `build_meta`는 `inputs:{name:sha256}`를 기록하지만 `verify_inputs`는 존재·파싱·stage·config_hash만 본다. AD-13이 명시한 시나리오(A가 02를 고쳐 02·05 재실행, B는 05만 재실행)에서 `crm/config.py`가 안 바뀌었으면 그대로 통과한다. → **사용자 결정: 옵션2 — 1-3으로 이월**. 지금 구현하면 검증 대상이 0건(1-1a "무의미한 초록" 함정의 재판)이고, 02가 01 산출물을 실제로 소비하는 시점에 `is_output_stale(output, inputs)`를 만들어야 실증이 가능하다. **현 한계를 `freshness.py` docstring에 정직하게 명시**(P16과 함께 처리).
- [x] [Review][Patch] P1. `write_with_meta`의 parking `os.replace`가 `try` **밖**에 있어, parking 직후~try 진입 전 예외 시 롤백 코드가 도달 불가(이전 산출물이 `.tmp`로 방치·target 소실) [crm/common/atomic.py] (edge, High)
- [x] [Review][Patch] P2. 롤백의 `os.replace(previous, target)` 자체 실패 미처리 — 원래 예외가 롤백 예외에 가려지고 previous가 영구 고아, target엔 meta 없는 새 내용(=이 모듈이 막겠다던 orphan) [crm/common/atomic.py] (blind+edge, High)
- [x] [Review][Patch] P3. meta가 유효 JSON이지만 dict가 아니면(리스트·문자열) `meta.get`에서 `AttributeError` — `StaleInputError` 아닌 무관한 크래시 [crm/common/freshness.py] (edge, High)
- [x] [Review][Patch] P4. `_atomic_write`의 `finally: tmp.unlink()`가 재예외(Windows 핸들 잠금) 시 원인 예외를 마스킹 [crm/common/atomic.py] (edge)
- [x] [Review][Patch] P5. `build_meta`의 `inputs` 키가 `path.name` — 다른 디렉터리의 동명 파일 2개면 dict 키 충돌로 한 해시가 조용히 유실 [crm/common/freshness.py] (edge)
- [x] [Review][Patch] P6. main 시그니처 체커 4중 사각지대: 중첩 `def main` 재정의가 `main_def`를 덮어써 거짓 양성/음성, `async def main` 통과, `posonlyargs`(`/`) 거짓 양성, `*args/**kwargs/kwonly/기본값` 거짓 음성, `lambda` 미검출 [tests/structure/checkers.py] (blind+edge)
- [x] [Review][Patch] P7. `test_code_commit_never_raises`가 이중 무의미 — `monkeypatch.chdir`은 `cwd=__file__.parent` 고정이라 무효과이고, 단언은 타입상 항상 참인 동어반복 [tests/common/test_freshness.py] (blind)
- [x] [Review][Patch] P8. CSV 0행(빈 파일·헤더만)이 정상 산출물로 통과 — 하류에서 원인과 먼 실패 [crm/common/acquisition.py] (edge)
- [x] [Review][Patch] P9. `output_paths` 길이 2 아님 → 맥락 없는 unpack ValueError [pipelines/01_download.py] (edge)
- [x] [Review][Patch] P10. `logging.basicConfig`가 import 시점 실행 — 이 모듈을 import하는 쪽의 로깅 설정을 덮어씀 [pipelines/01_download.py] (edge)
- [x] [Review][Patch] P11. `kaggle_csv_path`가 glob 다중 매치 시 `matches[0]` 침묵 선택 — "레이아웃 변경은 시끄럽게 실패" 의도와 배치 [crm/common/acquisition.py] (blind)
- [x] [Review][Patch] P12. `file_sha256`/`verify_inputs`에 디렉터리 경로 전달 시 `IsADirectoryError` 원인 불명 전파 [crm/common/freshness.py] (edge)
- [x] [Review][Patch] P13. AC4의 "폴백 안내 출력 + 비영 종료"가 코드에 없음(README에만 존재) — T5 체크 문구가 코드로 뒷받침되지 않음 [pipelines/01_download.py] (auditor, F2)
- [x] [Review][Patch] P14. 테스트 헬퍼 `_leftovers`가 `startswith(".")`까지 잔여물로 과잉 매칭 [tests/common/test_atomic.py] (blind)
- [x] [Review][Patch] P15. `store_csv_as_parquet`의 "determinism" 주석 과장 — `low_memory=False`는 청크 의존 dtype만 제거, parquet 바이트 해시는 여전히 환경 의존 [crm/common/acquisition.py] (blind)
- [x] [Review][Patch] P16. Dev Record 테스트 산술 오기(freshness 12 → 실제 11) [이 파일] (auditor, F3)
- [x] [Review][Defer] D1. **크래시 안전성**(예외 안전성과 별개) — parking~복원 사이 프로세스 kill/정전 시 마지막 정상 산출물이 임의 `.tmp`에 숨고 자동 복구 경로 없음. 진짜 해결은 시작 시 고아 `.tmp` 스캔·복구 루틴이며 이 스토리 범위 밖 — deferred
- [x] [Review][Defer] D2. 산출물 자체의 내용 해시가 meta에 없어 parquet 수동 변조를 탐지 못함(AD-13 계약 범위 밖, 위·변조는 non-goal) — deferred
- [x] [Review][Defer] D3. kagglehub 로컬 캐시 재사용 — 업스트림 갱신 시 재다운로드 안 함. `force_download` 노출 또는 캐시 무효화 절차 문서화 필요 — deferred
- [x] [Review][Defer] D4. 새 output이 놓인 뒤 meta 쓰기 전까지 (새 output + 옛 meta) 창 존재 — 단일 프로세스 배치 envelope에서 실해악 낮음 — deferred

Dismissed(3): `crm/config`가 `.pyc`/zipimport로 로드되는 경우(로컬 전용 envelope — 1-1a `PROJECT_ROOT` 건과 동일 근거), `STAGE_DOWNLOAD` 기본값이 공유 유틸에 있는 것(stage 지식은 레인 지식이 아님 — AD-1 위반 아님), T5의 명시적 `del` 부재(함수 스코프 종료로 실질 동일).

#### 병행 리뷰 보강 (독립 신규 컨텍스트, 2026-07-20)

> 별도 세션이 같은 커밋을 독립 리뷰했다. 발견 8건이 **전부 위 목록에 이미 포함**됐다(→ P5·P2·P11·P6·P15·DQ1·DQ2·D1). 독립 수렴이 확인됐으므로 중복 항목은 병합하고, **위 목록에 없던 두 가지만** 아래에 남긴다. 그 세션은 P1(parking이 `try` 밖)·P3(비-dict meta)·P13(AC4 코드 부재)을 잡지 못했다 — 3-레이어 병렬 리뷰가 단일 컨텍스트보다 넓다는 실측 근거.

**① 실행 재현 로그** — 위 지적 중 4건을 읽기 추론이 아니라 실제 실행으로 재현했다. patch 시 회귀 테스트의 기대 동작으로 그대로 쓸 수 있다.

| 항목 | 재현 방법 | 관측 결과 |
|---|---|---|
| P5 | `a/x.csv`(내용 `1`) + `b/x.csv`(내용 `2222`)를 `build_meta`에 함께 전달 | `len(meta['inputs']) == 1`, keys=`['x.csv']` — 한 해시 조용히 유실 |
| P2 | writer가 `ValueError("WRITER FAILED")`, 롤백 `os.replace`를 `PermissionError`로 강제 실패 | 호출부 수신 예외 = **PermissionError**(원인 `ValueError` 유실), `target.exists()==False`, 잔여 `.tmp` 1건 |
| DQ2/D2 | 정상 산출 후 parquet을 `b"TAMPERED-DIFFERENT-LENGTH"`로 덮어씀 | `verify_inputs` **통과**, meta에 `output_sha256` 필드 부재 확인 |
| D1 | `os.replace` 계측으로 parking 직후 상태 관찰 | `target` 부재 구간 실재 확인(`target_missing=True`) |

**② 외부 사실 독립 검증** — 스토리의 외부 의존 주장을 리뷰어가 직접 확인했다(위 목록에 없던 항목).

- **kagglehub 익명 다운로드**: Kaggle 공식 정책상 2024-04 이후 공개 데이터셋은 인증 불요 — 스토리의 "P1 선례" 주장 **입증**. 단 공식 문서에 *"user consent가 필요한 공개 리소스는 예외"* 단서가 있어, 향후 데이터셋 교체 시 재확인 필요.
- **두 슬러그 실존·라이선스**: Kaggle 공개 API로 확인 — `sakshigoyal7/credit-card-customers`(387,771B), `mashlyn/online-retail-ii-uci`(15,217,139B, ver.3). **둘 다 CC0: Public Domain** → AD-10(퍼블리시 시 공개 노출) 전제 충족.
- **⚠️ README 폴백 경로 주의**: UCI 공식 폴백을 문서화할 경우 `https://archive.ics.uci.edu/static/public/502/online+retail+ii.zip`은 **200 OK**지만 `https://www.uci.edu/static/public/502/...`는 **403**이다(후자는 LLM이 흔히 생성하는 오답 — 실측 확인함). 또한 UCI 원본은 **`.xlsx`**라 CSV를 가정한 폴백 코드는 `openpyxl` 없이 실패한다. 현재 README 폴백은 Kaggle 링크 기반이라 무해하나, UCI 경로로 바꾼다면 이 두 가지가 함정이다.

## Dev Notes

### 1.1a에서 물려받은 것 (재사용, 재발명 금지)

- `crm/config.py`: `RANDOM_SEED`·`PROJECT_ROOT`·`DATA_DIR`·`MODELS_DIR`·`MARTS_DIR`·`ensure_output_dirs()`. **경로를 새로 만들지 말고 import할 것.**
- `tests/structure/checkers.py`: 체커 6종. 이번에 **7번째를 만들지 말고 `find_pipeline_shape_violations`를 확장**한다(T6).
- 테스트 관례: 체커는 `scan_root` 인자를 받는 순수 함수 + `tmp_path` 합성 픽스처로 행동 검증. **동어반복 금지**(구현과 같은 계산을 테스트가 재구현하지 않는다).
- `.venv/Scripts/python.exe`로 실행. 현재 38 passed가 기준선 — 회귀 0을 유지할 것.

### ⚠️ P1 패턴을 그대로 가져오면 가드에 걸린다

P1은 `pipelines/loading.py`에 로직을 두고 `01_download.py`가 그것을 import했다. **P2에서는 이 구조가 위반이다** — 1.1a 코드리뷰 P3 패치로 `pipelines/` 하위의 `NN_<verb>.py` 아닌 모든 `.py`가 명명 위반으로 보고된다. 로직은 반드시 `crm/common/`에 둔다. 이건 AD-9(계산은 `crm/`, 오케스트레이션은 `pipelines/`)의 직접적 귀결이다.

### ⚠️ 실측으로 확인된 두 가지 (추측 아님)

1. **`python -m pipelines.01_download`은 실행 불가** — 모듈명이 숫자로 시작해 유효한 식별자가 아니다(`ImportError: No module named pipelines.01_download` 재현 확인). 스파인 운영 envelope의 "`python -m pipelines.NN_*`를 순서대로" 문구는 그대로는 실행되지 않는다. **`python pipelines/01_download.py`로 실행**하고, 스크립트 상단에 `sys.path.insert(0, ...)`로 프로젝트 루트를 넣어야 `crm` import가 된다(P1 01_download.py와 동일 처리). 이 `sys.path` 삽입은 `def`가 아니므로 40행 가드에 걸리지 않는다.
2. **`pyarrow` 미설치** — 현재 venv에 없다. pandas 3에서 `to_parquet`을 쓰려면 필수다. T1에서 추가하지 않으면 T5가 런타임에 실패한다.

### 데이터 출처 (스토리오너 결정 — 근거와 함께 기록할 것)

| 데이터셋 | 경로 | 파일 | 비고 |
|---|---|---|---|
| BankChurners | Kaggle `sakshigoyal7/credit-card-customers` | `BankChurners.csv` | 10,127행. P1에서 **kagglehub 익명 다운로드가 계정·키 없이 성공**한 선례 있음 |
| Online Retail II | Kaggle `mashlyn/online-retail-ii-uci` | `online_retail_II.csv` | UCI id 502의 Kaggle 미러. 통화 GBP |

**단일 의존성(`kagglehub`)으로 두 데이터셋을 모두 확보**하는 쪽을 택했다. UCI 공식 경로(`ucimlrepo`, id=502)를 쓰면 의존성이 하나 늘고 코드 경로가 갈라진다. 미러가 불안정하면 그때 `ucimlrepo`로 전환하고 결정을 갱신한다 — 리포트에 "UCI 502의 Kaggle 미러"임을 명시할 것.

**원본 그대로 저장한다.** 컬럼 선택·dtype 지정·필터링은 1-3(features) 소관이다. 여기서 컬럼을 고르면 레인 지식이 01단계로 새어 들어온다.

### AD-13 설계 지침

- **`config_hash`의 정의를 고정하라**: `crm/config.py` **파일 바이트의 SHA-256**. "설정 값들의 해시"가 아니다 — 주석 한 줄만 바뀌어도 해시가 바뀌는 게 의도다(보수적으로 stale을 잡는 편이 놓치는 것보다 낫다). 이 정의를 docstring에 못 박아 후속 스토리가 재해석하지 않게 할 것.
- **`code_commit()`은 실패해도 예외를 던지지 않는다** — git이 없거나 저장소 밖일 수 있다. `None`을 meta에 기록한다. 신선도 판정의 근거는 `config_hash`와 입력 해시이지 커밋이 아니다.
- **`stage` 필드로 선행 단계를 식별**한다(예: `"01_download"`). `verify_inputs(paths, expected_stage="01_download")` 형태. 파일명 규칙에 의존하지 말 것 — 이름은 바뀐다.
- **meta 없는 고아 산출물을 만들지 말 것**: 산출물 rename은 성공했는데 meta 쓰기가 실패하면, 다음 단계가 "meta 없음"으로 실패한다. `write_with_meta`가 이 조합을 원자적으로 다뤄야 한다(T3).

### AD-1 준수 포인트

- `crm/common/`은 **stateless 순수 함수만**. 1.1a 가드가 `fit`/`fit_transform`/`partial_fit` 보유 클래스를 잡지만, 그건 최소 방어선이다 — 캐시·모듈 전역 dict도 두지 말 것.
- `acquisition.py`는 **데이터셋 비의존**이어야 한다: 슬러그·글롭·목적지를 인자로 받는다. BankChurners 전용 상수를 여기 박으면 레인 지식이 공유 유틸에 들어간다.
- 두 데이터셋을 순차 처리하고 프레임을 동시에 들지 않는다(AD-1이 `05_marts`에 요구하는 것과 같은 규율).

### Testing Standards

- pytest 9.x, `testpaths = tests`, `addopts = -q`. 신규 테스트는 `tests/common/` 아래(구조 가드는 `tests/structure/` 유지).
- **가드가 실제로 무는 것을 증명**하는 1.1a 원칙을 이 스토리에도 적용: AC2의 네 가지 실패 경로가 전부 `pytest.raises`로 실증돼야 한다. "경고 로그" 통과는 AD-13 위반이다.
- **실데이터 실행이 DoD**(conventions 3항). 합성 CSV로 초록만 내고 done 처리하지 말 것 — 다운로드 실행과 행수 기록이 필요하다.

### Project Structure Notes

```
crm/common/
  freshness.py     # NEW - meta 생성·검증, config_hash
  atomic.py        # NEW - 원자적 쓰기, write_with_meta
  acquisition.py   # NEW - 데이터셋 비의존 확보 헬퍼
pipelines/
  01_download.py   # NEW - <=40행, main(input_paths, output_paths)만
tests/common/      # NEW - 신선도·원자성 테스트
tests/structure/   # UPDATE - main 시그니처 검사 + 픽스처(T6)
requirements.txt   # UPDATE - pyarrow, kagglehub
README.md          # UPDATE(없으면 NEW) - 데이터 확보 절차
```

**수정 대상 파일의 현재 상태**:
- `tests/structure/checkers.py` — `find_pipeline_shape_violations`는 현재 ① `pipelines/**/*.py` 전수 스캔 ② `NN_<verb>.py` 명명·최상위 위치 검사 ③ UTF-8 검사 ④ 40행 ⑤ `ast.walk`로 `main` 외 def/class 금지를 수행한다. T6은 여기에 **`main` 존재·시그니처 검사만 추가**한다. 기존 5개 검사를 건드리지 말 것(38 passed 회귀 금지).
- `requirements.txt` — core 블록(pandas·pytest)과 주석 처리된 모델링 블록이 있다. 신규 의존성은 **core 블록에** 추가하고, 모델링 블록의 주석은 그대로 둔다(pymc-marketing은 2-1 소관).

### References

- [Source: docs/planning-artifacts/epics.md#Story 1.1b] — AC 원문
- [Source: .../ARCHITECTURE-SPINE.md#AD-13] — meta.json 필드, 원자적 rename, 부분 산출 금지
- [Source: .../ARCHITECTURE-SPINE.md#AD-8] — `main(input_paths, output_paths)` 시그니처, 파일로만 통신
- [Source: .../ARCHITECTURE-SPINE.md#AD-9] — 40행 제한, 계산/오케스트레이션 분리
- [Source: .../ARCHITECTURE-SPINE.md#AD-1] — stateless common, 순차 처리
- [Source: .../pipeline-diagram.md#단계별 계약] — `01_download` 산출물 = `data/bankchurners.parquet`, `data/online_retail.parquet`
- [Source: docs/specs/spec-crm-targeting-lab/stack.md] — 데이터셋 규모·필드·통화
- [Source: docs/implementation-artifacts/1-1a-scaffolding-config-structure-guards.md] — 가드 API, 리뷰 교훈
- [Source: docs/implementation-artifacts/deferred-work.md] — D1(main 시그니처) 이번 해소
- [Source: 로컬 실측 2026-07-20] — pyarrow/kagglehub 미설치, `python -m` 숫자 모듈명 불가
- [Source: 웹 확인 2026-07-20] — Kaggle 슬러그 2종, UCI Online Retail II = id 502

## Dev Agent Record

### Agent Model Used

claude-opus-4-8

### Debug Log References

- `pytest`: 구현 시점 **61 passed**(1-1a 기준선 38 + freshness 11 + atomic 10 + 시그니처 픽스처 2). 코드리뷰 패치 후 **73 passed**(회귀 0).
- 설치 실측: **pyarrow 25.0.0, kagglehub 1.0.2** (T1)
- 실데이터 실행(T9): `bankchurners.parquet` **10,127행**×23컬럼(이탈 1,627 ≈ 16.1% — stack.md 명세 일치), `online_retail.parquet` **1,067,371행**×8컬럼(GBP `Price`·`Customer ID` 확인). meta 2건에 `config_hash`(9cad836d…)·`code_commit`(a4d304c) 기록, 실아티팩트로 `verify_inputs` end-to-end PASS.

### Completion Notes List

**red 단계가 롤백 버그를 잡았다.** `write_with_meta`의 최초 구현은 실패 롤백 시 meta를 무조건 삭제했는데, **이전 실행의 산출물을 복원하면서 그 짝인 이전 meta를 지우면 — 고아 방지 모듈이 고아를 제조**하는 자기모순이 된다. meta 쓰기는 원자적이며 마지막 단계이므로, 예외 시점에 디스크의 meta는 항상 이전 실행 것 → 이전 산출물 복원 시 meta도 보존, 신규 생성 실패 시에만 둘 다 제거로 수정. `test_failed_rerun_preserves_the_previous_meta_too`가 회귀 방지.

**config_hash 정의 고정**: `crm/config.py` 파일 바이트의 SHA-256(값 해시 아님 — 주석 변경도 무효화하는 게 의도, docstring에 못 박음). `code_commit()`은 절대 raise하지 않고 None 허용 — 신선도 판정의 근거가 아니라 컨텍스트.

**deferred D1 해소(T6)**: `find_pipeline_shape_violations`에 `main` 부재 + 정확한 시그니처(`input_paths, output_paths`) 검사 추가, 자기검증 픽스처 2건. **T7 확인: coverage 리포트의 `AD-8 pipeline shape` 행이 "0 - NO FILES IN SCOPE YET" → `1`로 전환**(1-1a 인계 완료), `AD-9 campaign order`는 0 유지(3.1 소관, 정상).

**P1 패턴 의도적 회피**: 로직을 `pipelines/loading.py`가 아닌 `crm/common/acquisition.py`에 배치 — 1-1a P3 패치가 만든 명명 가드에 P1 구조가 걸리기 때문(스토리 Dev Notes 예고대로). `01_download.py`는 36행, `main(input_paths, output_paths)`만 정의, 시그니처 가드 통과.

**acquisition은 데이터셋 비의존**(AD-1): 슬러그·글롭·목적지가 전부 인자. `low_memory=False`로 mixed-type 컬럼(Online Retail invoice)의 청크 의존 타이핑 방지 — 원시 아티팩트의 해시가 meta에 들어가므로 결정성이 중요.

**후속 스토리 인계**: ① 1-3은 `verify_inputs([...], expected_stage="01_download")`로 시작할 것 ② 원본은 무가공 저장 상태 — 컬럼 선택·dtype·필터는 1-3 소관 ③ Online Retail은 UCI id 502의 Kaggle 미러(`mashlyn/online-retail-ii-uci`) — 리포트 인용 시 명시 ④ 수동 폴백은 README "데이터 확보" 절.

### File List

**신규**: `crm/common/freshness.py`, `crm/common/atomic.py`, `crm/common/acquisition.py`, `pipelines/01_download.py`, `tests/common/__init__.py`, `tests/common/test_freshness.py`, `tests/common/test_atomic.py`, `README.md`
**수정**: `requirements.txt`(pyarrow·kagglehub), `tests/structure/checkers.py`(main 시그니처 검사), `tests/structure/test_checkers_selfcheck.py`(픽스처 2건), `docs/implementation-artifacts/deferred-work.md`(D1 해소), `docs/implementation-artifacts/structure-guard-coverage.md`(pytest 재생성), 이 스토리 파일, `sprint-status.yaml`
**생성(비커밋)**: `data/bankchurners.parquet(+meta)`, `data/online_retail.parquet(+meta)` — gitignore

## Change Log

| 날짜 | 변경 |
|---|---|
| 2026-07-20 | 스토리 1-1b 구현: AD-13 신선도(`freshness.py`)·원자적 쓰기(`atomic.py`)·데이터 확보(`acquisition.py`+`01_download.py`). 실데이터 10,127+1,067,371행 확보·검증. deferred D1 해소(main 시그니처 가드). 61 passed. |
| 2026-07-20 | 3-레이어 코드리뷰 반영: decision 2 해소(DQ1 컨벤션 소급 개정 / DQ2 1-3 이월) + patch 16건 전량 적용 + defer 4건. 원자성 강화(parking을 try 내부로, 롤백 실패 시 원인 예외 보존+parking 경로 안내), 체커 5중 사각지대 봉쇄(중첩 main·async·posonly·varargs·lambda), 0행 CSV 거부, 폴백 안내+비영 종료. **73 passed**, 실데이터 재실행 동일 결과. |
