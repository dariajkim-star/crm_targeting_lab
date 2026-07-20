---
baseline_commit: 1603cf20b61a3251aeed29846d448a87bb785f83
---

# Story 1.1a: 프로젝트 골격·설정 단일 출처·구조 가드 테스트

Status: done

## Story

As a 분석가,
I want 프로젝트 골격과 설정 단일 출처, 그리고 구조 규약을 기계적으로 강제하는 테스트를,
so that 이후 모든 코드가 첫 줄부터 AD-1 격리·AD-4 단일 출처·AD-9 의존 방향 위에서 쌓인다.

## Acceptance Criteria

**AC1 — Structural Seed**
**Given** 빈 저장소에서 Structural Seed(`crm/{config,common,segment,churn,campaign,ltv}`, `pipelines/`, `marts/`, `models/`, `tests/`)를 생성했을 때
**When** 디렉터리와 스텁 모듈을 확인하면
**Then** 스파인의 Structural Seed와 일치하고, `.gitignore`가 `data/`·`models/`를 제외하되 `marts/`는 커밋 대상 예외로 둔다(NFR5)

**AC2 — config 단일 출처**
**Given** `crm/config.py`를 작성했을 때
**When** import하면
**Then** `RANDOM_SEED`·경로·정책 가정 상수가 정의되고, 각 상수에 출처 주석(`# source: 정책가정`)이 붙어 있다
**And** 데이터에서 도출된 값이 하나도 없다(AD-1)
**And** `assert RETENTION_SUCCESS_RATE in RETENTION_GRID`·`assert COST_PER_CONTACT in COST_GRID`가 import 시점에 실행되어, 위반 시 import 자체가 실패한다(AD-4)
**And** 설정 파일은 이 파일 하나뿐이다 — 추가 YAML·TOML·JSON·`.env` 설정 파일이 존재하지 않음을 테스트가 검증한다(AD-4)

**AC3 — 구조 가드 테스트**
**Given** pytest 기반이 구성됐을 때
**When** `ast` import-graph 테스트를 실행하면
**Then** `crm/`이 `pipelines/`를 import하지 않음, `crm/segment|churn` ↔ `crm/ltv` 상호 import 없음, `crm/campaign/` 내부가 `matrix → simulate → sensitivity` 단방향임을 기계적으로 검증한다(AD-1·AD-9)
**And** `pipelines/NN_*.py`에 대해 파일당 40행 이하·`main` 외 `def` 금지를 검증한다 — **파일이 아직 없어도 규칙이 등록되어 있어, 1.1b가 첫 파이프라인을 추가하는 순간 자동 적용된다**
**And** `crm/common/`에 fit 상태를 보유한 객체가 없음(stateless 순수 함수만)을 검증한다(AD-1)

**AC4 — 가드의 자기 검증 (무의미 초록 방지)**
**Given** 1.1a 시점에는 `pipelines/`가 비어 있고 `crm/` 모듈이 스텁뿐이라, 모든 구조 가드가 **대상 0건으로 조용히 통과**할 수 있을 때
**When** 가드 테스트 스위트를 실행하면
**Then** 각 체커 함수가 **합성 픽스처(위반 사례)에 대해 실제로 위반을 검출함**을 증명하는 테스트가 함께 존재한다
**And** 실제 코드베이스 스캔 시 대상 파일 수가 0인 규칙은 그 사실을 명시적으로 기록한다(조용히 통과하지 않음)

## Tasks / Subtasks

- [x] **T1. 개발 환경 부트스트랩** (AC: 1)
  - [x] `.venv` 생성(Python 3.12 — 로컬 확인 3.12.10)
  - [x] `requirements.txt` 작성 — stack.md 전체 스택을 **선언**하되, 이 스토리에서 설치하는 것은 `pandas`·`pytest`만. **`pymc-marketing`은 설치하지 않는다**(2.1 dev의 조기 스모크 항목 — 스프린트 주석 참조)
  - [x] `pytest.ini` 작성(P1 패턴: `testpaths = tests`, `addopts = -q`)
- [x] **T2. Structural Seed 생성** (AC: 1)
  - [x] `crm/{common,segment,churn,campaign,ltv}/__init__.py` 스텁 + `crm/__init__.py`
  - [x] `pipelines/`, `marts/`, `models/`, `tests/` 디렉터리(빈 디렉터리는 git이 추적 못 하므로 `.gitkeep` 사용)
  - [x] `.gitignore` 확인 — 이미 존재하며 `data/`·`models/` 제외 + `marts/` 예외 주석이 반영돼 있음. **재작성 금지, 검토만**
- [x] **T3. `crm/config.py` 작성** (AC: 2)
  - [x] `RANDOM_SEED`, 경로 상수(`PROJECT_ROOT`/`DATA_DIR`/`MODELS_DIR`/`MARTS_DIR`)
  - [x] 정책 가정 상수 + 그리드: `RETENTION_SUCCESS_RATE`, `RETENTION_GRID`, `COST_PER_CONTACT`, `COST_GRID`
  - [x] 각 상수에 출처 주석 부착(`# source: 정책가정` / `# source: 경로규약`)
  - [x] 모듈 말미에 대표값 포함 `assert` 2건 배치(import 시점 실행)
- [x] **T4. 구조 가드 체커 구현** (AC: 3)
  - [x] `tests/structure/checkers.py` — 순수 함수 **6종**(campaign 내부 순서와 config 단일성을 별도 함수로 분리 — 사유는 완료 노트)
  - [x] 각 체커는 **스캔 루트를 인자로 받는다**(실제 코드베이스와 픽스처 양쪽에 적용 가능해야 함 — AC4의 전제)
  - [x] 각 체커는 `(violations, scanned_file_count)`를 반환한다
- [x] **T5. 실제 코드베이스 가드 테스트** (AC: 3)
  - [x] 전 체커를 `PROJECT_ROOT`에 적용해 위반 0건 검증
  - [x] `scanned_file_count == 0`인 규칙은 skip이 아니라 **명시적으로 기록**하고 통과(AC4) — `structure-guard-coverage.md` 산출
- [x] **T6. 체커 자기 검증 테스트** (AC: 4) ← **이 스토리의 핵심**
  - [x] `tmp_path`로 합성 위반 트리 동적 생성
  - [x] 위반 픽스처 각각에 대해 체커가 **위반을 검출함**을 assert
  - [x] 정상 픽스처에 대해 위반 0건임을 assert
- [x] **T7. 설정 파일 단일성 테스트** (AC: 2)
  - [x] 저장소에서 `*.yaml`·`*.yml`·`*.toml`·`*.json`·`*.ini`·`*.cfg`·`.env` 스캔 → 설정 목적 파일이 `crm/config.py` 외에 없음을 검증
  - [x] **화이트리스트 명시**: `pytest.ini`, `docs/implementation-artifacts/sprint-status.yaml` (+ `.git`/`.venv` 등 스킵 디렉터리)
- [x] **T8. 실행·커밋**
  - [x] `pytest` 전체 green 확인 (25 passed)
  - [x] 스토리 단위 커밋(conventions 8항)

### Review Findings

3-레이어 병렬 리뷰(2026-07-20): Blind Hunter 12건 / Edge Case Hunter 17건 / Acceptance Auditor 9건 → 병합 후 patch 12 / defer 2 / dismiss 7. 교차 검증(2개 이상 레이어 일치) 5건. AC 판정: 4/4 PASS(조건부 2). 참고: 리뷰 진행 중 병행 세션이 `_DATA_DIRS` 제외 패치(+회귀 테스트 2건, data/marts/models 하위 JSON은 설정이 아니라 산출물)를 선반영함 — Blind #1의 절반에 해당, 유지.

- [x] [Review][Patch] P1. config 스캔 `_SKIP_DIRS`에 `.claude`·`.vscode`·`.idea` 등 도구 디렉터리 부재 + 절대경로 `p.parts` 매칭이라 저장소 상위 경로명에 오염됨 — 상대경로 기준으로 전환 [tests/structure/checkers.py] (blind+edge+auditor)
- [x] [Review][Patch] P2. campaign 순서 체커가 tail 이름만 비교 — `import scipy.sensitivity`도 위반 오탐. `crm.campaign.` 접두 필수화 [tests/structure/checkers.py] (blind+edge)
- [x] [Review][Patch] P3. `[0-9][0-9]_*.py` glob 밖 파일(`pipelines/download.py`·하위 디렉터리)은 형태 규칙 완전 우회 + scanned에도 미집계 — 패턴 불일치 .py 자체를 명명 위반으로 보고 [tests/structure/checkers.py] (blind+edge, High)
- [x] [Review][Patch] P4. `tree.body` 최상위만 순회 — `main()` 내부 중첩 def/class로 로직 은닉 가능. `ast.walk`로 전환 [tests/structure/checkers.py] (blind+edge)
- [x] [Review][Patch] P5. 파이프라인 형태·stateful 체커가 `UnicodeDecodeError` 미처리로 크래시(cp949 파일) — 위반으로 보고하도록 처리 [tests/structure/checkers.py] (blind+edge)
- [x] [Review][Patch] P6. 커버리지 리포트 테스트 실행 순서 의존(`-k`·randomly·`-x`에서 stale 리포트 검증) + `exists()` 항진 단언 + "40 in v" 헐거운 매칭 — 순서 독립 재구성 [tests/structure/test_repo_structure.py] (blind+edge+auditor, High)
- [x] [Review][Patch] P7. 상대 import level이 패키지 깊이 초과 시 음수 슬라이스로 오동작 — 가드 추가 [tests/structure/checkers.py] (edge)
- [x] [Review][Patch] P8. `python -O` 실행 시 config assert 제거 — `if ... raise ValueError`로 전환 [crm/config.py] (edge)
- [x] [Review][Patch] P9. AC2 가드 실패 경로가 수동 실증뿐, 자동 테스트 부재 — 그리드 밖 값에서 import 실패를 증명하는 테스트 추가 [tests/structure/] (auditor)
- [x] [Review][Patch] P10. `from crm import ltv` 형태(구현 중 잡은 바로 그 버그)의 레인 회귀 픽스처 부재 [tests/structure/test_checkers_selfcheck.py] (auditor)
- [x] [Review][Patch] P11. `.env.local`·`.ENV` 등 변형 미탐 — `name.lower().startswith(".env")` [tests/structure/checkers.py] (blind+edge)
- [x] [Review][Patch] P12. config.py "ASCII-only" 독스트링과 한글 출처 주석의 자기모순 해소(주석은 AC 요구 형식이므로 독스트링 쪽 수정) + 소비처 없는 `set_global_seed()` 제거(스코프 크리프, AD-7 "글로벌 시드는 대체재 아님") [crm/config.py] (auditor)
- [x] [Review][Defer] D1. 파이프라인 `main(input_paths, output_paths)` 시그니처 존재 검증 부재 — 1.1b가 첫 파이프라인과 함께 추가하는 것이 자연 소속 [tests/structure/checkers.py] — deferred
- [x] [Review][Defer] D2. 향후 `pyproject.toml` 도입 시 AD-4 가드와 충돌 예고 — 도입 시점에 화이트리스트 등재 [tests/structure/checkers.py] — deferred

Dismissed(7): star import `crm.*`(target 자체가 이미 기록되어 실질 우회 불가), SyntaxError 파일 면제(실행 불가 코드는 위반도 비활성 — 수정 시점에 가드 작동), rglob 정션 루프(로컬 단일 사용자 envelope), mkdir 파일 충돌(예외 메시지로 충분), float 정확 일치(리터럴 유지 전제), gitignore 표기 검사(자기 저장소 통제 하), `PROJECT_ROOT` site-packages 가정(로컬 전용 envelope).

## Dev Notes

### 이 스토리의 성격 — 규칙 수립, 적용 아님

1.1a는 **규칙**을 세우고 1.1b가 **첫 적용 사례**다. 따라서:
- FR 배정이 없다(그린필드 기반 스토리 — 준비도 점검에서 정상 판정).
- 데이터를 다루지 않는다. `01_download`·meta.json·원자적 쓰기는 **전부 1.1b 소관** — 여기서 미리 만들지 말 것.
- `QUADRANT_RULE`·4분면 Enum은 AD-12상 config 소속이지만 **3.1에서 만든다**. 지금 만들면 소비처 없는 추측 코드가 된다("필요한 스토리에서 생성" 원칙).

### ⚠️ 최대 함정 — 무의미한 초록 (AC4의 존재 이유)

1.1a 시점의 코드베이스 상태:
- `pipelines/` = **빈 디렉터리** → 40행 가드가 파일 0개를 순회하고 통과
- `crm/*/` = **`__init__.py` 스텁만** → 레인 격리 가드가 import 0건을 검사하고 통과

즉 **네 개 가드 전부 아무것도 검증하지 않은 채 green**이 된다. 이 상태로 done 처리하면 1.1b~4.4 내내 "가드가 있다"고 믿으면서 실제로는 무방비다.

**해결책은 체커 자체를 테스트하는 것이다.** 체커를 `scan_root` 인자를 받는 순수 함수로 만들고, `tmp_path`에 합성 위반 트리를 세워 검출을 증명한다:

```
tmp_path/
  crm/segment/value.py        -> "from crm.ltv import x"        # 레인 위반
  crm/churn/model.py          -> "from pipelines import main"    # 계층 위반
  crm/campaign/matrix.py      -> "from crm.campaign import simulate"  # 내부 역방향 위반
  pipelines/01_x.py           -> 50줄 + def helper():            # 형태 위반 2종
  crm/common/scaler.py        -> class Scaler: def fit(self)     # stateful 위반
```

각 픽스처에 대해 `assert violations` (검출됨), 정상 트리에 대해 `assert not violations`. 이렇게 하면 실제 코드가 비어 있어도 **규칙이 살아 있음이 증명**된다.

### 체커 구현 지침

- **`ast` 파싱 사용** — 정규식 금지. `import crm.ltv`와 `from crm.ltv import x` 두 형태를 모두 잡아야 하고, 문자열·주석 안의 텍스트를 오검출하면 안 된다.
- **레인 격리(AD-1)**: `crm/segment/*`·`crm/churn/*`에서 `crm.ltv` 참조 금지, 역방향도 금지. `crm/common`은 어느 레인도 import하지 않음.
- **계층 방향(AD-9)**: `crm/**`가 `pipelines`를 import하면 위반.
- **campaign 내부 방향(AD-9)**: `matrix` → `simulate` → `sensitivity` 단방향. `matrix`가 `simulate`/`sensitivity`를, `simulate`가 `sensitivity`를 import하면 위반.
- **파이프라인 형태(AD-8·AD-9)**: `pipelines/NN_*.py` glob 대상. 40행 초과 위반, `main` 외 `def`/`class` 정의 위반. 행수는 빈 줄·주석 포함 실제 파일 행수(단순·검사 가능한 기준 유지).
- **stateful common(AD-1)**: `crm/common/**`에 `fit`/`fit_transform` 메서드를 가진 클래스, 또는 모듈 수준 가변 상태(전역 dict/list 재할당)가 있으면 위반. 완벽한 정적 판정은 불가능하므로 **`fit` 계열 메서드 보유 클래스 검출**까지를 스코프로 한다(과탐 방지, 한계는 주석에 기록).

### config.py 작성 지침

- **ASCII-only** (P1 NFR6 교훈 — Windows cp949 환경에서 한글 소스가 인코딩 사고를 낸 전례). 한글은 문서에만, 코드 주석은 영문.
- **데이터 도출값 금지**(AD-1): 분위수 경계·평균·인코딩 매핑 등은 절대 여기 두지 않는다. 지금 넣을 값은 시드·경로·정책 가정뿐.
- **대표값 assert 배치**: 모듈 최하단. P1의 `current_cutoff` 이원화 사고가 이 assert의 존재 이유 — 시뮬레이터(3.2) 결론이 민감도 곡선(3.4) 위에 없는 상태를 import 시점에 차단한다.
- 값 예시(스토리오너 재량, 근거 주석 필수): `RETENTION_SUCCESS_RATE = 0.30`(SPEC Assumptions "업계 통용 보수값, 실측 아님"), `RETENTION_GRID = (0.10, 0.20, 0.30, 0.40, 0.50)`. `COST_PER_CONTACT`는 **통화 중립**(NFR3) — 단위 없는 수치이며 주석에 "unitless, BankChurners has no currency unit"을 명시.

### T7 화이트리스트 주의

"설정 파일은 config.py 하나뿐"을 문자 그대로 스캔하면 **BMAD 자체 파일(`sprint-status.yaml`)과 `pytest.ini`가 걸린다.** AD-4의 의도는 *애플리케이션 런타임 설정*의 단일화이지 도구 설정 금지가 아니다. 화이트리스트를 명시적 상수로 두고 사유 주석을 달 것 — 나중에 누가 보고 "규칙이 느슨하다"고 오해하지 않도록.

### Project Structure Notes

스파인 Structural Seed와 1:1 정렬. 변이 없음.

```
crm-targeting-lab/
  crm/
    __init__.py
    config.py          # AD-4 단일 출처
    common/            # stateless 순수 유틸 (1.1b가 채움)
    segment/           # 1.2~1.5
    churn/             # 1.6~1.7
    campaign/          # 3.1~3.4
    ltv/               # 2.1~2.3
  pipelines/           # 1.1b가 01_download.py 추가
  marts/               # 4.1~4.2 (커밋 대상)
  models/              # gitignore
  tests/
    structure/         # 이 스토리의 가드
  requirements.txt
  pytest.ini
```

**주의**: `.gitignore`는 이미 저장소에 존재하고 `marts/` 예외 주석까지 반영돼 있다(커밋 9e6608f). **덮어쓰지 말고 검토만** 한다.

### Testing Standards

- pytest 9.x, `testpaths = tests`, `addopts = -q` (P1 패턴 계승)
- **행동 기반 테스트**(conventions·NFR6): 구현과 동일한 로직을 테스트에서 재구현해 비교하는 동어반복 금지. P1 2-2에서 이 함정이 부호 반전 버그를 통과시킨 전례가 있다 — T6가 정확히 그 교훈의 적용이다(체커 로직을 재구현하지 말고 **위반 픽스처로 행동을 검증**).
- 이 스토리는 실데이터를 다루지 않으므로 "실데이터 실행 DoD"(conventions 3항)는 해당 없음. 대신 **가드가 실제로 문다는 증명**이 DoD를 대신한다.

### References

- [Source: docs/planning-artifacts/epics.md#Story 1.1a] — AC 원문, 에픽 공통 DoD
- [Source: docs/planning-artifacts/architecture/architecture-crm-targeting-lab-2026-07-16/ARCHITECTURE-SPINE.md#AD-1] — 레인 격리, stateless common, config 데이터값 금지
- [Source: .../ARCHITECTURE-SPINE.md#AD-4] — 설정 단일 파일, 그리드 대표값 assert
- [Source: .../ARCHITECTURE-SPINE.md#AD-8] — `main(input_paths, output_paths)` 시그니처
- [Source: .../ARCHITECTURE-SPINE.md#AD-9] — 의존 방향, 40행 제한, campaign 내부 순서
- [Source: .../ARCHITECTURE-SPINE.md#Structural Seed] — 디렉터리 구조, marts 커밋 예외
- [Source: .../ARCHITECTURE-SPINE.md#Consistency Conventions] — 테스트 3종 필수, 순수 함수/쓰기 계층 분리
- [Source: docs/specs/spec-crm-targeting-lab/stack.md] — Python 3.12, pytest 9.x, 전체 스택 버전
- [Source: docs/specs/spec-crm-targeting-lab/conventions.md] — P1 계승 관례 9항
- [Source: docs/implementation-artifacts/sprint-status.yaml] — M1~M3·OQ-5·pymc-marketing 스모크 주석
- [Source: 로컬 실측 2026-07-20] — Python 3.12.10, P1 `.venv`/`pytest.ini`/`config.py` 패턴

## Dev Agent Record

### Agent Model Used

claude-opus-4-8

### Debug Log References

- `pytest` 최종: **25 passed** (자기검증 20 + 저장소 가드 5)
- 설치 실측: pandas 3.0.3, pytest 9.1.1, numpy 2.5.1 (stack.md 명세 대역 일치)

### Completion Notes List

**AC4가 실제 버그 2건을 잡았다 — 이 스토리의 핵심 성과.**
체커 자기검증 테스트를 먼저 돌렸을 때 `test_campaign_checker_flags_matrix_importing_simulate`와 `..._simulate_importing_sensitivity`가 실패했다. 원인: `_imported_modules()`가 `ast.ImportFrom`에서 **모듈명만 수집하고 임포트된 이름을 무시**해서, `from crm.campaign import simulate`가 `crm.campaign`으로만 보였다. 같은 결함이 레인 격리에도 잠재해 있었다 — `from crm import ltv`가 `crm` 임포트로 보여 **AD-1 위반을 통과시켰을 것**이다. `from X import a`에 대해 `X`와 `X.a`를 모두 수집하도록 수정. 합성 픽스처가 없었다면 이 구멍은 실제 위반이 발생하는 스토리(2.x 이후)까지 잠복했다.

**실제 저장소 실증(합성 픽스처와 별개로 수행).** 실제 트리에 위반 파일 7종을 임시 생성해 검출을 확인하고 원복했다 — 레인(절대/상대 임포트 각 1), 계층, campaign 역방향, 파이프라인 47행, `fit` 보유 클래스, 잉여 yaml. **7/7 CAUGHT.**

**AC2 assert 실증.** `RETENTION_SUCCESS_RATE`를 0.33(그리드 밖)으로 바꾸고 `import crm.config` 실행 → exit 1 + AD-4 메시지 확인 후 원복. import 시점 차단이 실제로 작동한다.

**T4 함수 수 편차(4 → 6).** 스토리는 체커 4종을 나열했으나 AC3이 요구하는 규칙은 5개(레인·계층·campaign 순서·파이프라인 형태·stateless)이고 AC2가 config 단일성을 추가로 요구한다. 규칙당 1함수로 분리하는 편이 위반 메시지와 스캔 카운트를 규칙 단위로 보고할 수 있어 그렇게 구현했다. 규칙 커버리지는 스토리보다 넓지 않다.

**`models/` 디렉터리는 커밋되지 않는다.** `.gitignore`가 `models/`를 제외하므로 `.gitkeep`도 무시된다(`git check-ignore`로 확인). 빈 디렉터리를 강제 커밋하는 대신 `config.ensure_output_dirs()`를 두어 파이프라인이 실행 시 생성하게 했다. import 시점 부작용은 피했다(설정 모듈이 파일시스템을 건드리면 안 됨).

**`crm/common` stateless 검사의 스코프 한계를 코드 주석에 명시.** 정적 분석으로 순수성을 증명할 수는 없다. AD-1을 실제로 위협하는 형태(fit 계열 메서드를 가진 클래스 = 한 레인의 수치를 담아 다른 레인으로 옮길 수 있는 그릇)만 검출하고, 광범위한 변이 분석은 과탐 방지를 위해 의도적으로 제외했다.

**후속 스토리 소관을 침범하지 않았다.** `QUADRANT_RULE`·4분면 Enum(3.1), `meta.json`·원자적 쓰기·`01_download`(1.1b), `pymc-marketing` 설치(2.1)는 손대지 않았다.

**1.1b 인계 사항**: `pipelines/`에 첫 파일이 생기는 순간 `AD-8 pipeline shape` 규칙이 0건 → 실스캔으로 전환된다. `structure-guard-coverage.md`의 해당 행이 "NO FILES IN SCOPE YET"에서 파일 수로 바뀌는지 확인할 것.

### Review Findings (code review 2026-07-20, Claude 신규 컨텍스트 — Med 1 / patch 1)

> ⚠️ **관례 편차**: conventions는 GPT 교차 리뷰를 규정한다. 이번 리뷰는 **신규 컨텍스트의 Claude**가 수행했다(구현과 동일 모델 계열). 모델 다양성이 주는 검출력은 확보하지 못했으므로, **GPT 교차 리뷰는 여전히 유효한 후속 절차**다. 아래 발견은 그 대체가 아니라 선행 통과분이다.

- [x] **[Patch][Med] AD-4 config 체커가 데이터 산출물을 오탐** — `find_extra_config_files()`가 접미사(`.json` 등)만으로 판정해 **`data/meta.json`(1.1b 산출)·마트 JSON(에픽 4)을 "unexpected config file"로 검출**한다. 현재는 해당 파일이 없어 green이지만, **1.1b가 첫 데이터를 쓰는 순간 red**가 되고 메시지가 엉뚱한 곳(설정 규칙 위반)을 가리켜 디버깅을 오도한다.
  - **실증**: 리뷰 중 `data/meta.json`·`marts/segment_profile.json`을 임시 생성 → violations 2건 검출 확인(원복함).
  - **판단**: AD-4의 의도는 *애플리케이션 설정의 단일화*이지 확장자 금지가 아니다. 파이프라인 출력은 설정이 아니다.
  - **수정**: `_DATA_DIRS = {data, marts, models}`를 **디렉터리 단위로 스캔 제외**. 파일명 화이트리스트가 아닌 디렉터리 제외를 택한 이유는 해당 트리의 파일명이 기계 생성이라 사전에 알 수 없기 때문(주석에 명시).
  - **회귀 가드 2종 추가**(AC4 철학의 연장 — 가드가 *물지 않아야 할 것을 물지 않음*도 증명 대상): `test_config_checker_ignores_data_artifacts`(데이터 산출물 3종에 무반응), `test_config_checker_still_flags_config_outside_data_dirs`(제외가 규칙 자체를 무디게 하지 않음 — `crm/settings.json`은 여전히 검출).
  - 25 → **27 passed**.

**리뷰 총평**: AC1~AC4 전부 충족. 특히 `_imported_modules()`가 상대 임포트와 `from X import a`의 `X.a` 바인딩을 모두 해석하는 점, 스코프 한계를 주석으로 남긴 점, `structure-guard-coverage.md`가 "0 - NO FILES IN SCOPE YET"을 정직하게 기록하는 점이 AC4의 취지에 부합한다. 발견된 1건은 **가드가 미래에 오작동하는 유형**으로, 이 스토리가 경계한 "무의미한 초록"의 이웃 문제(무의미한 빨강)에 해당한다.

### File List

**신규**
- `requirements.txt`
- `pytest.ini`
- `crm/__init__.py`
- `crm/config.py`
- `crm/common/__init__.py`
- `crm/segment/__init__.py`
- `crm/churn/__init__.py`
- `crm/campaign/__init__.py`
- `crm/ltv/__init__.py`
- `pipelines/.gitkeep`
- `marts/.gitkeep`
- `tests/__init__.py`
- `tests/structure/__init__.py`
- `tests/structure/checkers.py`
- `tests/structure/test_checkers_selfcheck.py`
- `tests/structure/test_repo_structure.py`
- `docs/implementation-artifacts/structure-guard-coverage.md` (테스트 생성물, 커밋 대상)

**수정**
- `docs/implementation-artifacts/1-1a-scaffolding-config-structure-guards.md` (frontmatter·체크박스·Dev Agent Record·Status)
- `docs/implementation-artifacts/sprint-status.yaml` (1-1a 상태 전이)

**미수정(의도적)**
- `.gitignore` — 이미 올바름, 검토만 수행

## Change Log

| 날짜 | 변경 |
|---|---|
| 2026-07-20 | 스토리 1-1a 구현: Structural Seed, `crm/config.py` 단일 출처(AD-4 assert 포함), 구조 가드 6종 + 자기검증. 25 passed. |
| 2026-07-20 | 3-레이어 코드리뷰 반영: patch 12건 전량 적용(P1~P12), defer 2건(deferred-work.md), dismiss 7건. 병행 세션 `_DATA_DIRS` 패치 위에 적용. **38 passed**. 핵심: 파이프라인 명명 우회 봉쇄(P3), 리포트 테스트 순서 독립화(P6), config 가드 `raise` 전환+자동 red-path 테스트(P8/P9), `from crm import ltv` 회귀 픽스처 영구화(P10), `set_global_seed` 제거(스코프 크리프). |
