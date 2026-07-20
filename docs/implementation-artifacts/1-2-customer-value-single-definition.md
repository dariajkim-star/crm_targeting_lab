---
baseline_commit: 4a5c7ce3aa64e43ce17a389b7926e26dd7d0a7d6
---

# Story 1.2: 고객가치 단일 정의

Status: review

## Story

As a 분석가,
I want 고객가치를 한 함수가 배타적으로 정의하기를,
so that 2×2·기대절감액·민감도·마트가 같은 고객에게 서로 다른 가치를 매기는 모순이 구조적으로 불가능해진다.

## Acceptance Criteria

**AC1 — 단일 정의 함수**
**Given** BankChurners 프레임이 주어졌을 때
**When** `crm/segment/value.py::customer_value(df)`를 호출하면
**Then** `Total_Trans_Amt` 실측 프록시 기반 `Series[float]`을 **원척도 그대로** 반환한다(정규화·로그 변환 없음 — 스케일링은 판정 단계 소관, FR10·AD-11)
**And** 함수는 순수하며 파일을 쓰지 않는다

**AC2 — 가정 라벨링**
**Given** 가치 프록시의 타당성과 한계가 문서화되어야 할 때
**When** 산출 리포트를 확인하면
**Then** 선정 근거(연간 거래액 = 수수료 수익의 1차 동인)와 한계(수익성≠거래액, 보조 지표 미반영)가 "가정"으로 라벨링되어 명시된다(NFR1)

**AC3 — 재계산 금지의 기계적 강제**
**Given** 다른 모듈이 고객가치를 필요로 할 때
**When** 코드베이스를 검사하면
**Then** `Total_Trans_Amt`를 직접 참조해 가치를 재계산·재가중하는 코드가 `value.py` 외에 존재하지 않는다
**And** 이 금지를 검증하는 테스트가 있다

## Tasks / Subtasks

- [x] **T1. `crm/segment/value.py`** (AC: 1)
  - [x] `customer_value(df: pd.DataFrame) -> pd.Series` — `Total_Trans_Amt`를 **명시적으로 `float`로 캐스팅**해 반환(실데이터 dtype은 `int64` — AC가 `Series[float]`을 요구하므로 암묵 의존 금지)
  - [x] 필수 컬럼 부재 시 명확한 예외(어떤 컬럼이 없는지 이름을 담을 것)
  - [x] 인덱스는 입력 프레임의 인덱스를 보존(정렬·재색인 금지 — 소비처가 조인한다)
  - [x] 순수 함수: 입력 프레임 변경 금지, 파일 쓰기 금지, 전역 상태 금지
  - [x] docstring에 **가치 정의 변경 절차**를 못 박을 것(AD-11: 이 함수 + 스키마 문서 + CAP-5 한계 문구를 **함께** 고쳐야 함)
- [x] **T2. 단일 정의 가드 (AC3)** ← **이 스토리의 핵심**
  - [x] `tests/structure/checkers.py`에 `find_value_recomputation_violations(root)` 추가 — `crm/` 아래에서 `Total_Trans_Amt`를 참조하는 파일을 검출하되 `crm/segment/value.py`만 예외
  - [x] **`ast` 기반**: `ast.Constant`(문자열 `"Total_Trans_Amt"` — `df["Total_Trans_Amt"]` 형태)와 `ast.Attribute`(`df.Total_Trans_Amt` 형태) 양쪽을 잡을 것. 주석·문서 문자열의 언급까지 잡는 텍스트 grep은 오탐을 낳는다
  - [x] `(violations, scanned)` 반환 규약 유지, `_is_skipped` 재사용
  - [x] `tests/structure/test_repo_structure.py`의 `RULES`에 등재(커버리지 리포트에 행이 생김)
  - [x] 자기검증 픽스처(1-1a 관례): 위반 트리(`crm/campaign/matrix.py`가 `Total_Trans_Amt` 참조) → 검출 실증, `value.py` 자신은 위반 아님 실증
- [x] **T3. 행동 기반 단위 테스트** (AC: 1)
  - [x] 반환 dtype이 float임을 검증(int64 입력에서도)
  - [x] 원척도 보존 검증: 입력 값과 출력 값이 **같은 스케일**임을 행동으로 확인(예: 두 고객의 비율이 입력 비율과 동일 — 정규화되면 깨짐)
  - [x] 인덱스 보존, 입력 프레임 불변(원본 mutation 없음)
  - [x] 컬럼 부재 시 예외 + 메시지에 컬럼명 포함
  - [x] **동어반복 금지**(P1 2-2 교훈): `df["Total_Trans_Amt"].astype(float)`를 테스트에서 재계산해 비교하지 말 것. 위 성질(스케일·인덱스·dtype·불변성)로 검증한다
- [x] **T4. 가치 프록시 리포트** (AC: 2, M3 해소)
  - [x] `docs/implementation-artifacts/value-proxy-report-1-2.md` 작성
  - [x] **실데이터 분포**: n=10,127, min 510 / median 3,899 / max 18,484, 결측 0, 0이하 0 (dev 시 코드로 재산출해 기재)
  - [x] 선정 근거와 한계를 **"가정"으로 명시 라벨링**(NFR1)
  - [x] **통화 무단위 표기**(NFR3) — BankChurners는 통화 단위가 없다. `$`·`₩` 등 기호를 절대 붙이지 말 것(P1 3-4 통화 오기 사고)
- [x] **T5. 실행·커밋**
  - [x] 실데이터로 `customer_value` 실행해 분포 수치 산출(conventions 3항)
  - [x] `pytest` 전체 green(현 기준선 **73 passed**, 회귀 0), 스토리 단위 커밋

## Dev Notes

### 🚨 최우선 인계 — BankChurners에 타깃 누수 컬럼 2개가 있다 (1-3·1-6용, 이 스토리에서 손대지 말 것)

실데이터 실측 결과:

```
Naive_Bayes_Classifier_..._1   target 상관 +1.0000
Naive_Bayes_Classifier_..._2   target 상관 -1.0000
(참고) Total_Trans_Amt         target 상관 -0.1686
```

두 컬럼은 `Attrition_Flag`로 사전 학습된 분류기 출력이며 **타깃과 완전상관**이다. 이걸 피처로 넣으면 이탈 모델 AUC가 1.0에 붙고 프로젝트 전체가 무의미해진다. Kaggle 데이터셋 설명도 삭제를 지시한다.

**이 스토리의 소관이 아니다** — 1-3(피처)에서 배제하고, 1-6에서 누수 감사로 재확인할 것. 여기 적는 이유는 이 사실이 발견된 김에 유실되지 않게 하기 위함이다. `value.py`는 `Total_Trans_Amt`만 보므로 영향 없다.

### M3 해소 — "산출 리포트"의 물리적 지위

준비도 점검 Minor M3: `customer_value()`는 순수 함수이고 파이프라인 단계가 아니다. AC2가 말하는 "산출 리포트"는 **세션 산출물**(`docs/implementation-artifacts/value-proxy-report-1-2.md`)이지 `pipelines/` 단계의 파일 출력이 아니다. 이 스토리는 **파이프라인 파일을 만들지 않는다** — `value.py`는 1-3의 `02_features`가 소비한다.

(같은 계열의 M2가 3-1에 대기 중이다: E3 산출물도 세션 리포트이고 공식 수치의 자리는 4-1 마트 + 4-3 Tableau 탭이다.)

### 1-1a/1-1b에서 물려받은 것 (재사용, 재발명 금지)

- **가드 추가 패턴**: 체커는 `(root) -> (violations, scanned)` 순수 함수, `_is_skipped(root, path)`로 도구 디렉터리 제외, `RULES` 튜플에 등재, **합성 위반 픽스처로 자기검증**. 이 관례를 그대로 따를 것 — `tests/structure/checkers.py`와 `test_checkers_selfcheck.py`를 읽고 시작하라.
- **왜 자기검증이 필수인가**: 현재 `crm/segment/`에는 `__init__.py`밖에 없어서, 새 가드가 **대상 0건으로 조용히 통과**할 수 있다. 1-1a에서 이 함정이 실제 버그 2건을 숨길 뻔했다. 픽스처가 없으면 이 가드도 장식이 된다.
- **커버리지 리포트**: `RULES`에 등재하면 `structure-guard-coverage.md`에 행이 생긴다. 대상이 0건이면 "NO FILES IN SCOPE YET"으로 표기되는데, 이 스토리에서는 `value.py`가 생기므로 **1건 이상**이 되어야 정상이다.
- **실행**: `.venv/Scripts/python.exe -m pytest`. 현 기준선 **73 passed**.
- **인코딩**: 코드·콘솔 출력은 **ASCII만**. Windows cp949 콘솔에서 한글 print가 실제로 깨졌다(이번 조사 중 재현). 한글은 문서(.md)에만.

### AD-11 정확히 읽기

> 고객가치는 `crm/segment/value.py::customer_value(df) -> Series[float]` **한 함수**만이 정의한다. 2×2·기대절감액·민감도·마트 컬럼은 모두 이 함수의 출력을 소비하며 재계산·재가중하지 않는다. **마트 컬럼은 원척도를 보존**하고 스케일링은 판정 단계에서만 수행한다.

핵심 두 가지:
1. **원척도 보존** — 여기서 정규화하면 마트 컬럼이 해석 불가능한 숫자가 된다. 스케일링이 필요하면 3-1(분면 판정)이 자기 안에서 한다.
2. **소비만, 재계산 금지** — T2의 가드가 이걸 기계적으로 강제한다. 지금 만들어두지 않으면 3-1·3-2·3-3·4-1이 각자 `Total_Trans_Amt`를 집어 쓰는 걸 막을 방법이 없다(AD-11이 존재하는 이유가 바로 그 시나리오다).

**SPEC CAP-5는 2026-07-20 개정됨**(커밋 696ffdb, 준비도 M1 해소): 원안의 "보조 지표 `Total_Revolving_Bal`·`Credit_Limit` 활용도" 문구가 AD-11과 충돌해 삭제됐다. 두 컬럼은 **가치 축에 산입하지 않으며** CAP-1 세그먼트 프로파일 서술용 참고 지표다. 리포트에서 "보조 지표 미반영"을 한계로 적을 때 이 개정을 근거로 삼을 것.

### 실데이터 사전 조사 (dev가 재확인할 것)

| 항목 | 값 |
|---|---|
| 행수 | 10,127 |
| `Total_Trans_Amt` dtype | **`int64`** ← float 캐스팅 필요 |
| 결측 | 0 |
| 0 이하 | 0건 (로그 변환 시 문제없으나 **이 스토리는 변환하지 않는다**) |
| min / median / max | 510 / 3,899 / 18,484 |

데이터는 이미 `data/bankchurners.parquet`에 있다(1-1b가 확보). **재다운로드 불필요.** 읽을 때는 `pd.read_parquet(config.DATA_DIR / "bankchurners.parquet")`.

### 이 스토리가 만들지 않는 것

- 파이프라인 단계(`02_features`는 1-3)
- RFM 지표·세그먼트(1-3, 1-4)
- 스케일링·분면 판정(3-1)
- `verify_inputs` 호출 — 이 스토리는 파이프라인이 아니므로 신선도 검증 대상이 아니다. **1-3이 그 첫 소비자**이며, 거기서 DQ2(`is_output_stale`)도 함께 다룬다

### Project Structure Notes

```
crm/segment/value.py                              # NEW - 단일 정의
tests/segment/test_value.py                       # NEW - 행동 기반 단위 테스트
tests/structure/checkers.py                       # UPDATE - 재계산 금지 가드 추가
tests/structure/test_checkers_selfcheck.py        # UPDATE - 픽스처 2건
tests/structure/test_repo_structure.py            # UPDATE - RULES에 등재
docs/implementation-artifacts/value-proxy-report-1-2.md  # NEW - 세션 리포트
```

`tests/segment/__init__.py`가 필요하다(`tests/common/` 선례).

### References

- [Source: docs/planning-artifacts/epics.md#Story 1.2] — AC 원문
- [Source: .../ARCHITECTURE-SPINE.md#AD-11] — 가치 단일 정의, 원척도 보존
- [Source: docs/specs/spec-crm-targeting-lab/SPEC.md#CAP-5] — **2026-07-20 개정본**(보조 지표 배제)
- [Source: docs/planning-artifacts/implementation-readiness-report-2026-07-20.md] — M1(해소됨)·M3(이 스토리에서 해소)
- [Source: docs/implementation-artifacts/1-1a-...md] — 가드 관례, 자기검증 필수 근거
- [Source: docs/implementation-artifacts/1-1b-...md] — 실데이터 확보, ASCII 규율
- [Source: 실데이터 실측 2026-07-20] — dtype·분포·누수 컬럼 상관

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (bmad-dev-story)

### Debug Log References

**기준선 확인**: 착수 시 HEAD `4a5c7ce`, 워킹트리 clean, `73 passed`. 사용자가 지적한 병행 세션 개입 2건 모두 실재 확인 — `4a5c7ce`(sprint-status 선커밋)와 `checkers.py`의 `_DATA_DIRS` 패치. (주의: `crm-targeting-lab`은 Desktop 저장소 안에 **중첩된 독립 git 저장소**다. 바깥 저장소에서 `git log`를 돌리면 이 프로젝트 이력이 전혀 보이지 않는다.)

**테스트 픽스처 버그 1건 (구현 아님)**: `test_does_not_reorder_values`가 처음에 NaN으로 실패했다. 원인은 `_frame` 헬퍼가 `pd.DataFrame` 생성자에 `pd.Series`(자체 0..n-1 인덱스 보유)와 `index=`를 **동시에** 넘긴 것 — pandas가 재라벨링이 아니라 **정렬(align)**을 수행해 전 행이 NaN이 됐다. 인덱스를 생성 후 대입하도록 헬퍼를 수정. 구현에는 결함이 없었으며, 이 실패는 "값 순서 보존" 테스트가 실제로 물었기에 드러났다.

**가드 실증 (AC3)**: 실제 트리를 건드리지 않고 `crm/`을 임시 디렉터리로 복사해 위반을 심는 방식으로 검증:
```
real tree copy      : scanned=10 violations=0
with planted breach : scanned=11 violations=1
   -> AD-11 single value definition: crm.campaign.matrix references
      'Total_Trans_Amt' - consume crm.segment.value.customer_value() instead
```

**실데이터 실행** (`data/bankchurners.parquet`, n=10,127) — 스토리 사전조사 수치 전부 재현 확인:
```
src dtype int64 -> out dtype float64 | missing 0 | le_zero 0
min 510 / q25 2155.5 / median 3899 / mean 4404.09 / q75 4741 / max 18484
std 3397.13 | index_equal True | top10pct_share 29.8%
```

**ASCII 규율**: 신규 파일(`value.py`, `test_value.py`, `checkers.py` 추가분) 전부 ASCII clean. 기존 `config.py`/`test_checkers_selfcheck.py`의 한글은 `config.py` docstring이 명시 허용한 `# source:` 출처 주석으로 규율 위반이 아니다.

### Completion Notes List

- **AC1 충족**: `customer_value(df)`는 `Total_Trans_Amt`를 명시적 `float` 캐스팅해 **원척도 그대로** 반환. 순수 함수(입력 불변·파일 미기록·전역 상태 없음). `.astype(float)`가 dtype 일치 시에도 복사본을 돌려주므로 반환 Series는 입력 프레임의 뷰가 아니며, 이를 별도 테스트로 실증했다.
- **AC2 충족**: `value-proxy-report-1-2.md`에 선정 근거(연간 거래액 = 수수료 수익 1차 동인)와 한계 4건을 **"[가정]"으로 명시 라벨링**. 통화 기호는 문서 전체에 한 번도 쓰지 않았다(NFR3). 한계 2번(보조 지표 미반영)은 CAP-5 개정(`696ffdb`)을 근거로 기술.
- **AC3 충족 — 이 스토리의 핵심**: `find_value_recomputation_violations`가 AST 기반으로 `ast.Constant`/`ast.Attribute` 양쪽 표기를 검출하고 `value.py`만 면제한다. `RULES` 등재로 커버리지 리포트에 **10 files scanned / 0 violations** 행 생성 — Dev Notes가 요구한 "1건 이상" 조건 충족이며 대상 0건으로 조용히 통과하는 상태가 아니다.
- **오탐 설계**: 텍스트 grep 대신 AST를 쓴 이유를 픽스처로 못박았다 — 규칙을 *설명하는* docstring/주석을 가진 모듈은 위반이 아니다(정확 문자열 일치라 산문 언급은 매치되지 않음). 산문에 반응하는 가드는 무시당한다.
- **동어반복 회피**: 단위 테스트는 `astype(float)`를 재계산해 비교하지 않는다. dtype·비율 보존(정규화/로그 변환 탐지)·절대 크기 앵커(상수 배율 탐지)·인덱스 보존·값 순서·입력 불변·뷰 아님·예외 메시지 — 각각 그럴듯한 오구현이 깨뜨릴 **성질**로 검증했다.
- **누수 컬럼 미접촉 (의도됨)**: `Naive_Bayes_Classifier_*` 2컬럼은 본 스토리 소관이 아니며 손대지 않았다. `value.py`는 `Total_Trans_Amt`만 읽으므로 영향이 없다. 배제 책임은 1-3(피처), 재확인은 1-6(누수 감사)이며 리포트 6절에 인계 기록을 남겼다.
- **테스트**: 73 passed → **87 passed** (+14: 단위 9, 가드 자기검증 5), 회귀 0.

### File List

- `crm/segment/value.py` — NEW, 가치 단일 정의
- `tests/segment/__init__.py` — NEW
- `tests/segment/test_value.py` — NEW, 행동 기반 단위 테스트 9건
- `tests/structure/checkers.py` — UPDATE, `find_value_recomputation_violations` + AD-11 상수 추가
- `tests/structure/test_checkers_selfcheck.py` — UPDATE, 자기검증 픽스처 5건 추가
- `tests/structure/test_repo_structure.py` — UPDATE, `RULES`에 AD-11 등재
- `docs/implementation-artifacts/structure-guard-coverage.md` — UPDATE, pytest 재생성(AD-11 행 추가)
- `docs/implementation-artifacts/value-proxy-report-1-2.md` — NEW, 세션 리포트
- `docs/implementation-artifacts/1-2-customer-value-single-definition.md` — UPDATE, 본 기록
- `docs/implementation-artifacts/sprint-status.yaml` — UPDATE, 1-2 상태 전이

## Change Log

| 날짜 | 변경 |
|---|---|
| 2026-07-20 | 스토리 1-2 구현: 가치 단일 정의 함수 + AD-11 재계산 금지 가드 + 프록시 리포트. 73 → 87 passed, 회귀 0. Status → review |
