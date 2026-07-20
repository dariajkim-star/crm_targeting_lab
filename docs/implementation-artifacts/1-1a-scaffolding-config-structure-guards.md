# Story 1.1a: 프로젝트 골격·설정 단일 출처·구조 가드 테스트

Status: ready-for-dev

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

- [ ] **T1. 개발 환경 부트스트랩** (AC: 1)
  - [ ] `.venv` 생성(Python 3.12 — 로컬 확인 3.12.10)
  - [ ] `requirements.txt` 작성 — stack.md 전체 스택을 **선언**하되, 이 스토리에서 설치하는 것은 `pandas`·`pytest`만. **`pymc-marketing`은 설치하지 않는다**(2.1 dev의 조기 스모크 항목 — 스프린트 주석 참조)
  - [ ] `pytest.ini` 작성(P1 패턴: `testpaths = tests`, `addopts = -q`)
- [ ] **T2. Structural Seed 생성** (AC: 1)
  - [ ] `crm/{common,segment,churn,campaign,ltv}/__init__.py` 스텁 + `crm/__init__.py`
  - [ ] `pipelines/`, `marts/`, `models/`, `tests/` 디렉터리(빈 디렉터리는 git이 추적 못 하므로 `.gitkeep` 사용)
  - [ ] `.gitignore` 확인 — 이미 존재하며 `data/`·`models/` 제외 + `marts/` 예외 주석이 반영돼 있음. **재작성 금지, 검토만**
- [ ] **T3. `crm/config.py` 작성** (AC: 2)
  - [ ] `RANDOM_SEED`, 경로 상수(`PROJECT_ROOT`/`DATA_DIR`/`MODELS_DIR`/`MARTS_DIR`)
  - [ ] 정책 가정 상수 + 그리드: `RETENTION_SUCCESS_RATE`, `RETENTION_GRID`, `COST_PER_CONTACT`, `COST_GRID`
  - [ ] 각 상수에 출처 주석 부착(`# source: 정책가정` / `# source: 경로규약`)
  - [ ] 모듈 말미에 대표값 포함 `assert` 2건 배치(import 시점 실행)
- [ ] **T4. 구조 가드 체커 구현** (AC: 3)
  - [ ] `tests/structure/checkers.py` — 순수 함수 4종: `find_lane_violations()`, `find_layering_violations()`, `find_pipeline_shape_violations()`, `find_stateful_common_violations()`
  - [ ] 각 체커는 **스캔 루트를 인자로 받는다**(실제 코드베이스와 픽스처 양쪽에 적용 가능해야 함 — AC4의 전제)
  - [ ] 각 체커는 `(violations, scanned_file_count)`를 반환한다
- [ ] **T5. 실제 코드베이스 가드 테스트** (AC: 3)
  - [ ] 4개 체커를 `PROJECT_ROOT`에 적용해 위반 0건 검증
  - [ ] `scanned_file_count == 0`인 규칙은 skip이 아니라 **명시적으로 로그/기록**하고 통과(AC4)
- [ ] **T6. 체커 자기 검증 테스트** (AC: 4) ← **이 스토리의 핵심**
  - [ ] `tests/structure/fixtures/` 아래 합성 위반 트리 생성(또는 `tmp_path`로 동적 생성)
  - [ ] 위반 픽스처 각각에 대해 체커가 **위반을 검출함**을 assert
  - [ ] 정상 픽스처에 대해 위반 0건임을 assert
- [ ] **T7. 설정 파일 단일성 테스트** (AC: 2)
  - [ ] 저장소에서 `*.yaml`·`*.yml`·`*.toml`·`*.json`·`.env` 스캔 → 설정 목적 파일이 `crm/config.py` 외에 없음을 검증
  - [ ] **제외 대상 화이트리스트 필요**: `docs/implementation-artifacts/sprint-status.yaml`(BMAD 추적 파일), `pytest.ini`, `.venv/`, `.git/` — 이건 애플리케이션 설정이 아님
- [ ] **T8. 실행·커밋**
  - [ ] `pytest` 전체 green 확인
  - [ ] 스토리 단위 커밋(conventions 8항)

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

### Debug Log References

### Completion Notes List

### File List
