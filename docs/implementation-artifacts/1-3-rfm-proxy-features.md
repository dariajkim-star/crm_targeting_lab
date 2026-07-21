---
baseline_commit: 7082de0
baseline_passed: 99
---

# Story 1.3: RFM 프록시 지표 산출

Status: review

## Story

As a 분석가,
I want BankChurners 변수로 RFM 프록시 지표를 산출하기를,
so that 카드 고객을 행동 기반으로 세분화할 재료가 생긴다.

## Acceptance Criteria

**AC1 — RFM 도출 정의와 구간화 근거의 문서화**
**Given** `pipelines/02_features.py`가 원본을 읽을 때
**When** RFM 프록시를 산출하면
**Then** R·F·M 각각이 어떤 원본 변수에서 어떻게 도출됐는지 리포트에 1줄씩 정의된다(FR1)
**And** 구간화 방식(분위수 vs 고정 경계)의 선택과 근거가 기록되며, 경계는 **BankChurners 분포에서만** 도출된다(AD-1)

**AC2 — 행동 기반 산식 테스트**
**Given** RFM 산식이 구현됐을 때
**When** pytest를 실행하면
**Then** 산식 테스트는 **행동 기반**이다 — 구현과 동일한 공식을 재구현해 비교하는 동어반복 검증이 아니라, 알려진 입력→기대 순위/구간 관계로 검증한다(NFR6, P1 2-2 부호반전 교훈)

**AC3 — 산출물 + meta, config drift 시 실패**
**Given** 02 단계가 완료됐을 때
**When** 산출물을 확인하면
**Then** 피처 파일과 `<output>.meta.json`이 함께 쓰이고, 입력 meta의 `config_hash`가 현재 `config.py` 해시와 불일치하면 단계가 실패한다(AD-13)

### AC 파생 — 이 스토리가 함께 닫는 두 부채 (사용자 인계, 필수)

**AC4 — 직접 입력 콘텐츠 드리프트 탐지(`is_output_stale`)** *(2차 리뷰 후 범위 축소)*
**Given** `02_features`가 자기 이전 출력과 meta를 남긴 상태에서 **직접 입력** parquet의 **내용이 바뀌었을 때**(config는 그대로)
**When** 02를 재실행하면
**Then** stale로 판정되어 재계산이 강제된다(출력 meta의 stage·config_hash 드리프트도 함께 stale)
**And** 이 판정을 실증하는 테스트가 존재한다

> **범위 (과잉주장 금지, 2차 리뷰 High-2)**: 이 AC는 **직접 입력**의 콘텐츠·자기 stage/config 드리프트만 다룬다. **전이적 staleness와 05-only 재실행 방지는 이 AC의 범위가 아니다** — 입력이 바이트 동일하나 그 원천이 바뀌고 하위 stage만 재실행되는 경우는 오케스트레이터 DAG 검증 또는 재귀 의존성 검증이 있어야 잡히며, 05·오케스트레이터가 생기는 후속 스토리로 이관한다(deferred-work.md). 순수 코드 변경(config 무변)도 범위 밖.
>
> **근거**: `verify_inputs`는 입력의 `config_hash`·producer stage만 보고 **입력 파일 자신의 SHA-256을 대조하지 않는다**. 1-3이 **첫 stage-to-stage 소비자**이므로 소비 stage가 자기 이전 출력 meta의 `inputs` 해시(+stage·config_hash)를 현재 상태와 대조하는 `is_output_stale(output, inputs, expected_stage)`를 구현·배선한다.

**AC5 — 누수 컬럼 배제(1-6 감사 이전의 1차 방어선)**
**Given** BankChurners 원본에 `Naive_Bayes_Classifier_*` 2개 컬럼이 있을 때
**When** 02_features의 피처 산출물을 확인하면
**Then** 이 2개 컬럼은 **어떤 형태로도 피처 산출물에 실리지 않는다**
**And** 이 배제를 검증하는 테스트가 존재한다(1-6 누수 감사가 재확인하되, 여기가 첫 방어선)

## Tasks / Subtasks

- [x] **T1. RFM 프록시 순수 계산 모듈 `crm/segment/features.py`** (AC: 1, 5) ← 로직 소유
  - [x] R·F·M 원척도 프록시를 산출하는 순수 함수. 입력 프레임 불변, 파일 쓰기·전역 상태 금지(AD-1/AD-9, 1-2 `value.py` 선례).
  - [x] **R (Recency 프록시)** ← `Months_Inactive_12_mon`. **극성 반전 주의**: 값이 클수록 "덜 최근"이다. Recency 점수는 비활성 개월이 **적을수록 높게** 나와야 한다. 이 반전을 코드와 리포트 양쪽에 명시.
  - [x] **F (Frequency 프록시)** ← `Total_Trans_Ct`(12개월 거래 건수).
  - [x] **🚨 M (Monetary 프록시)** ← **`crm.segment.value.customer_value(df)` 출력을 소비**한다. `Total_Trans_Amt`를 **직접 명명하지 않는다**(AD-11 이름 소유권 — T4 참조). M축은 곧 고객가치 축이므로 이건 우회가 아니라 의미적으로 정확한 배선이다.
  - [x] 반환 프레임 인덱스/조인키 규약: `CLIENTNUM`을 보존해 1-4 K-means·1-6이 조인할 수 있게 한다(정렬·재색인 금지, 소비처가 조인 — 1-2 규약 계승).
  - [x] **구간화(binning)** — AC1이 요구하는 "방식 선택+근거". 권고: **분위수 기반 5분위 점수(1..5)**. 이유: RFM 관례이고, 고정 경계는 BankChurners 분포를 봐야 정할 수 있어 결국 데이터 유래인데 분위수가 더 투명하다. **경계는 입력 프레임에서 런타임 산출**하며 `config.py`에 하드코딩 금지(AD-1: 데이터 유래 값을 config에 park하면 레인 누수). 최종 방식은 dev가 분포를 보고 확정하되(AC1이 허용), 선택 근거를 리포트에 기록.
  - [x] **결정론(AD-7)**: 동일 입력 → 동일 구간 배정. 분위수 동점(tie)·경계 포함 규칙(`>=` 등)을 명시적으로 고정. `pd.qcut`의 duplicate-edge 처리(`duplicates="drop"` 등)를 의식적으로 선택하고 근거를 남길 것 — `Total_Trans_Ct` 같은 이산 분포는 분위수 경계가 겹칠 수 있다(실데이터로 확인하라).
- [x] **T2. 파이프라인 stage `pipelines/02_features.py`** (AC: 1, 3, 4, 5) ← 얇은 오케스트레이션
  - [x] `main(input_paths, output_paths)` **시그니처만**. **파일당 40행 이하**, `main` 외 `def`/`class`/`lambda` 금지, 허용 호출은 `crm.*`·pandas read/write·logging뿐(AD-8/AD-9, `find_pipeline_shape_violations`가 강제 — 01_download.py 선례를 그대로 따르라).
  - [x] 시작 시 `verify_inputs([bankchurners.parquet], expected_stage="01_download")` 호출(사용자 인계 착수점). 이어 **T3의 `is_output_stale`로 콘텐츠 드리프트도 점검**.
  - [x] `crm.segment.features`의 함수로 RFM 산출 → `crm.common.atomic.write_with_meta`로 (`data/features_customers.parquet` + meta) 원자적 기록(정규 경로는 pipeline-diagram.md 기준). meta는 `build_meta(stage="02_features", inputs=[bankchurners.parquet], rows=...)`.
  - [x] `01_download`가 모듈명 숫자 시작이라 `python -m` 불가했던 것과 동일 — 실행 관례(`.venv/Scripts/python.exe pipelines/02_features.py`)를 docstring에 적고 README 있으면 정합.
- [x] **T3. DQ2 직접 입력 드리프트 탐지 — `is_output_stale(output, inputs, *, expected_stage)` in `crm/common/freshness.py`** (AC: 4) ← **사용자 지정 필수**
  - [x] 소비 stage가 **자기 이전 출력의 meta**를 읽어, 그 `inputs[name]` 해시를 **현재 입력 파일의 `file_sha256`과 대조**하고, 출력 meta의 **stage·config_hash**도 cache key로 검사한다. 하나라도 불일치 → stale. 출력 또는 meta 부재 → stale(=최초 실행). 순수·무상태(읽기만), 인터페이스는 freshness.py 기존 규약과 일관되게.
  - [x] freshness.py 모듈 docstring을 정정: **직접 입력 드리프트만 해소**로 명시하고, 미해결(전이적 staleness·순수 코드변경·산출물 자체 변조)을 명확히 구분해 남긴다. **거짓 완결 주장 금지** — "DQ2 CLOSED"라 쓰지 않는다.
  - [x] 02_features에 배선: `verify_inputs`(선행 stage/​config 게이트) **다음에** `is_output_stale`(콘텐츠 드리프트 게이트)를 둔다 — 두 게이트의 역할이 다르다(전자=잘못된 producer/​config drift, 후자=같은 producer의 입력 내용 변화).
- [x] **T4. AD-11 이름 소유권 — M축 배선의 정당성 확보** (AC: 5, AD-11) ← **가드 건드리기 전 반드시 이 순서**
  - [x] `features.py`는 `Total_Trans_Amt`를 **문자열/​어트리뷰트/​타입선언/​eval·query/​심볼 import 어떤 형태로도 명명하지 않는다.** M은 `customer_value(df)` 출력으로만 얻는다.
  - [x] 기존 가드 `find_value_recomputation_violations`가 이 파일을 스캔하므로 **새 위반이 0건이어야 정상**이다. 스캔 대상이 1건 늘었는지 커버리지 리포트로 확인(대상 0건 조용한 통과 금지 — 1-1a 교훈).
  - [x] **만약** 스키마/dtype 메타데이터 목적으로 `Total_Trans_Amt` 이름이 정말 필요해지면, **가드를 고치기 전에** deferred-work.md의 우선순위를 적용: (1) 가치 축 컬럼을 피처 스키마에서 제외 (2) `value.py`가 좁은 스키마 API 노출 (3) 실사례 근거로 B안 재검토. **본 스토리는 (1)로 충분하다** — M축을 `customer_value()`로 소비하면 이름을 부를 이유가 없다. 가드 완화는 마지막 수단.
- [x] **T5. 행동 기반 테스트** (AC: 2, 4, 5) — `tests/segment/test_features.py`
  - [x] **동어반복 금지**(P1 2-2·1-2 리뷰 교훈): 구현 공식을 재구현해 비교하지 말 것. 대신 **성질**로 검증: F 프록시가 큰 고객이 F 점수 ≥ 작은 고객(단조성); R은 **비활성 개월이 적은 고객이 R 점수가 높다**(극성 반전이 지켜지는지 — 부호 실수를 잡는 핵심 테스트); M 점수가 `customer_value` 순위와 단조.
  - [x] **성질만으로는 부족**(1-2 리뷰 H3 교훈: clip/piecewise/normalize 변이가 성질 테스트를 통과했다): 최소 1건 **하드코딩 oracle** — 손으로 만든 소형 분포에서 각 고객의 기대 구간 번호를 상수로 못박아 비교. 상단 클리핑·구간 재스케일·경계 오프바이원을 잡는다.
  - [x] **AC4 실증**: 임시 디렉터리에 02 출력+meta를 만든 뒤 입력 parquet 내용을 바꿔 `is_output_stale`가 True를 반환하는지, 안 바꾸면 False인지. 최초 실행(출력 부재)도 stale로 처리되는지.
  - [x] **AC5 실증**: 실제/합성 프레임을 features 함수에 넣고 산출 컬럼 집합에 `Naive_Bayes_Classifier_*`가 **없음**을 단언.
  - [x] 결정론(AD-7): 같은 입력 2회 산출 → 구간 배정 완전 동일.
- [x] **T6. RFM 프록시 리포트** (AC: 1) — `docs/implementation-artifacts/rfm-proxy-report-1-3.md`
  - [x] R·F·M **각 1줄** 도출 정의(원본 변수 → 프록시). M줄은 "Total_Trans_Amt를 `customer_value()`로 소비"라고 적어도 됨(리포트는 .md 세션 문서라 AD-11 가드 대상 아님 — 가드는 `crm/` .py의 AST 상수만 스캔).
  - [x] 구간화 방식 선택+근거, 경계가 BankChurners 분포에서만 도출됨을 명시(AD-1). **실데이터 분위수 경계 수치를 코드로 산출해 기재**(conventions 3항).
  - [x] R 극성 반전을 "가정/​해석 주의"로 라벨링. 통화·단위 기호 금지(NFR3).
- [x] **T7. 실행·커밋**
  - [x] 실데이터(`data/bankchurners.parquet`, n=10,127)로 02_features 실행 — 피처 parquet+meta 생성 확인, RFM 분포·분위수 경계 재현.
  - [x] `pytest` 전체 green. **현 기준선 99 passed, 회귀 0.** 스토리 단위 커밋.
  - [x] Obsidian 미러 갱신(에픽 공통 DoD).

## Dev Notes

### 🚨 최우선 설계 판단 — RFM의 M축과 AD-11 이름 소유권 충돌 (이 스토리의 핵심)

RFM의 Monetary는 자연스럽게 `Total_Trans_Amt`다. 그런데 **AD-11(2026-07-20 A안)**은 `value.py`를 제외한 `crm/` 아래 어떤 모듈도 `Total_Trans_Amt`를 **어떤 형태로도 명명하지 못하게** 한다(문자열·어트리뷰트·타입선언·eval/query·심볼 import). `find_value_recomputation_violations`가 fail-closed로 강제한다.

**해소: M축 = `customer_value(df)` 출력 소비.** 이건 가드를 피하려는 우회가 아니라 **AD-11이 의도한 바로 그 배선**이다 — "2×2·기대절감액·민감도·마트 컬럼은 모두 `customer_value` 출력을 소비하며 재계산하지 않는다"에 RFM의 M도 포함된다. 게다가 M축과 고객가치 축은 **같은 것**이므로 의미적으로도 정확하다.

deferred-work.md가 명시한 인계와 정확히 일치한다:
> "1-3 이후 실소비자가 스키마에서 컬럼명이 필요해질 수 있다. 그때 우선순위는 (1) 가치 축 컬럼을 피처 스키마에서 제외 (2) `value.py`가 좁은 스키마 API 노출 (3) B안 재검토. 가드 완화는 마지막 수단."

→ **본 스토리는 (1)에서 끝난다.** M을 `customer_value()`로 소비하면 이름을 부를 일이 없다. **가드에 손대지 말 것.** dtype/스키마 목적으로 이름이 필요하다고 느껴지면, 그건 대개 피처 산출물이 원컬럼을 그대로 실으려 할 때다 — 싣지 마라(AC5의 누수 배제와 같은 정신: 피처는 파생 지표만 담는다).

### 🚨 누수 컬럼 2개 — 1-2에서 인계된 최우선 사실 (AC5)

실측(1-2 dev): `Naive_Bayes_Classifier_..._1` 은 `Attrition_Flag`와 **상관 +1.0000**, `..._2`는 **-1.0000**. 타깃으로 사전학습된 분류기 출력이라 피처에 넣으면 1-6 이탈모델 AUC가 1.0에 붙어 **프로젝트 전체가 무의미**해진다. Kaggle 설명도 삭제를 지시.

**1-3이 raw→features 컬럼 선택의 첫 지점**이므로 여기가 1차 방어선이다. 피처 산출물에 이 2컬럼이 **절대 실리지 않게** 하고 테스트로 못박는다. 1-6이 누수 감사로 재확인한다(중복 방어는 의도된 것).

### DQ2 — `verify_inputs`의 구멍과 `is_output_stale` (AC4, 사용자 지정)

freshness.py 모듈 docstring이 스스로 밝힌 한계(그대로 인용 요지): `build_meta`는 각 입력의 SHA-256을 기록하지만 `verify_inputs`는 **그 기록 해시를 현재 입력과 대조하지 않는다.** 그래서 AD-13 대표 시나리오(누가 02 코드/입력을 바꾸고 02·05만, 동료가 05만 재실행 → 새 피처와 옛 확률이 섞인 마트)가 `config.py`만 그대로면 **조용히 통과**한다.

**부분적으로** 닫는다: 소비 stage가 자기 이전 출력 meta의 **stage·config_hash + 직접 입력 해시**를 현재 상태와 대조(`is_output_stale(output, inputs, expected_stage)`). 이건 stage가 실제로 다른 stage 출력을 소비해야 테스트 가능한데, **1-3이 그 최초 지점**이다(01→02).

주의: `is_output_stale`은 `verify_inputs`를 **대체하지 않고 보완**한다.
- `verify_inputs`: 입력이 올바른 producer 산출인가 + config drift가 없는가 (게이트 A)
- `is_output_stale`: 내 이전 출력이 자기 stage·config·**직접 입력** 기준으로 stale한가 (게이트 B)

두 게이트를 02_features에 순서대로 배선한다. **닫지 못한 것(2차 리뷰 High-2, 정직하게)**: ① 전이적 staleness — 위 "대표 시나리오"의 **05-only 재실행은 이 게이트로 잡히지 않는다**(05의 직접 입력 `features`가 바이트 동일하면 fresh). 오케스트레이터 DAG 또는 재귀 의존성 검증이 있어야 하며 후속 스토리 소관 ② 순수 코드 변경(config 무변) ③ 산출물 자신의 콘텐츠 해시 부재(수동 변조). 모두 deferred-work.md 기록. **"DQ2 완전 해소"라 쓰지 말 것.**

### 1-1a/1-1b/1-2에서 물려받은 것 (재사용, 재발명 금지)

- **파이프라인 stage 형태**: `pipelines/01_download.py`를 읽고 그대로 따르라 — `sys.path.insert`, `main(input_paths, output_paths)`, `if __name__` 가드, 40행 이하, `main` 외 `def` 금지. `find_pipeline_shape_violations`(checkers.py:237)가 async·nested main·lambda·시그니처까지 검사한다.
- **원자적 쓰기**: `crm.common.atomic.write_with_meta(target, writer, meta)` — 이미 (output+meta) 원자성·롤백을 보장한다. **직접 `to_parquet` 쓰지 말 것.** writer는 `lambda tmp: frame.to_parquet(tmp, index=False)` 형태.
- **meta 조립**: `crm.common.freshness.build_meta(stage, inputs, rows)`. 입력 파일명 유일성은 이미 강제됨.
- **순수 함수 규약(1-2 value.py)**: 입력 프레임 불변, 인덱스/조인키 보존, 파일 미기록. `customer_value`가 인덱스를 보존하므로 `features`도 같은 인덱스 위에서 합칠 수 있다.
- **가드 추가 관례**: 새 구조 가드를 추가한다면 `(root)->(violations, scanned)` 순수 함수 + `_is_skipped` + `RULES` 등재 + **자기검증 합성 픽스처**. 단, 본 스토리는 새 구조 가드가 꼭 필요하진 않다(AC5 누수 배제는 features 산출물에 대한 **행동 테스트**로 충분하고, AD-11은 기존 가드가 이미 커버). 새 가드를 만들면 대상 0건 조용한 통과를 픽스처로 방지.
- **실행/​인코딩**: `.venv/Scripts/python.exe -m pytest`. 코드·콘솔 출력은 **ASCII만**(cp949 콘솔에서 한글 print 깨짐 실증됨). 한글은 .md 문서에만.

### 실데이터 사전 조사 (dev가 코드로 재확인할 것)

| 항목 | 값 |
|---|---|
| 행수 | 10,127 |
| RFM 원본 후보 | R←`Months_Inactive_12_mon`, F←`Total_Trans_Ct`, M←`customer_value()`(=Total_Trans_Amt 파생) |
| `Total_Trans_Ct` 성격 | 이산(정수) — 분위수 경계 **중복 가능**, `qcut` duplicates 처리 필요 |
| `Months_Inactive_12_mon` 성격 | 소범위 이산(0~6 부근 예상) — **극성 반전** + 분위수 겹침 주의 |
| 누수 컬럼 | `Naive_Bayes_Classifier_*` 2개 — **피처에서 배제**(AC5) |
| 데이터 위치 | `data/bankchurners.parquet` (1-1b 확보, 재다운로드 불필요) |

읽기: `pd.read_parquet(config.DATA_DIR / "bankchurners.parquet")`. 위 성격 수치는 **추정**이니 dev가 실측으로 확정하고 리포트에 기재.

### 이 스토리가 만들지 않는 것 (범위 경계)

- K-means 세그먼트·안정 ID(1-4). 1-3은 세그먼트의 **재료(RFM 피처)**만 만든다.
- 이탈 모델·누수 **감사**(1-6). 1-3은 누수 컬럼 **배제**만; 감사·재확인은 1-6.
- 03_train_churn이 소비할 예측 피처/​라벨 전체 세트 설계 — 02_features가 이후 확장될 수 있으나, 1-3 범위는 RFM 프록시 컬럼 + 조인키다. 03이 추가로 필요로 하는 컬럼은 1-6에서 같은 stage를 확장하며 정한다(과범위 금지).
- 스케일링·분면 판정(3-1). RFM 점수 구간화는 세그먼테이션용이며 가치 축 정규화가 아니다.

### Project Structure Notes

```
crm/segment/features.py                    # NEW - RFM 프록시 순수 계산 (M은 customer_value 소비)
pipelines/02_features.py                   # NEW - 얇은 stage (main만, <=40행)
crm/common/freshness.py                    # UPDATE - is_output_stale() 추가 + KNOWN LIMITATION 갱신
tests/segment/test_features.py             # NEW - 행동 기반 + 하드코딩 oracle + AC4/AC5 실증
tests/common/test_freshness.py             # UPDATE - is_output_stale 단위 테스트
docs/implementation-artifacts/rfm-proxy-report-1-3.md   # NEW - 세션 리포트
```

- `tests/segment/__init__.py`는 1-2에서 이미 존재.
- 피처 산출물 경로: **`config.DATA_DIR / "features_customers.parquet"`** — pipeline-diagram.md가 지정한 정규 이름(임의 제안 아님, 03_train_churn이 이 이름으로 소비). meta는 `write_with_meta`가 형제 `.meta.json`으로 자동 생성.
- 02_features 배선 시 `is_output_stale`이 참조할 "이전 출력"은 곧 이 features_customers.parquet 자신 → 최초 실행엔 부재 → stale 처리(정상).

### References

- [Source: docs/planning-artifacts/epics.md#Story 1.3] — AC 원문(FR1, AD-1, NFR6, AD-13)
- [Source: .../ARCHITECTURE-SPINE.md#AD-1] — 두 레인 물리 격리, 경계는 자기 레인 분포에서만
- [Source: .../ARCHITECTURE-SPINE.md#AD-7] — 결정론적 재현
- [Source: .../ARCHITECTURE-SPINE.md#AD-8/AD-9] — stage `main` 시그니처, 40행·의존 방향
- [Source: .../ARCHITECTURE-SPINE.md#AD-11] — 가치 축 단일 정의 + 이름 소유권(M축 배선 근거)
- [Source: .../ARCHITECTURE-SPINE.md#AD-13] — 신선도 meta·부분 재실행 게이트
- [Source: crm/common/freshness.py 모듈 docstring] — KNOWN LIMITATION "1-3으로 예약"(DQ2)
- [Source: docs/implementation-artifacts/deferred-work.md] — AD-11 A안 근거, 실소비자 우선순위 (1)→(2)→(3)
- [Source: docs/implementation-artifacts/1-2-...md] — 누수 컬럼 상관, value.py 순수함수 규약, 1-2 리뷰 H3(성질 테스트만으로 부족)
- [Source: docs/implementation-artifacts/1-1b-...md] — atomic write·build_meta·실데이터 확보
- [Source: 실데이터 컬럼 실측 2026-07-21] — BankChurners 22피처+2누수, RFM 원본 후보

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (bmad-dev-story)

### Debug Log References

**기준선**: HEAD `7082de0`, 99 passed. (중첩 독립 저장소 — 바깥 Desktop에서 git log 안 보임.)

**verify_inputs가 config drift로 02를 막음 (설계대로)**: config.py에 `RFM_QUANTILES`를
추가하자 `config_hash`가 바뀌어 기존 `bankchurners.parquet.meta.json`이 stale 판정 →
02가 `StaleInputError`로 중단. 이는 AD-13의 의도된 over-invalidation(바이트 해시)이며 버그가
아니다. 정상 흐름대로 `01_download`를 재실행해 stage 01 meta를 새 config 해시로 갱신한 뒤
02가 통과했다. (config 변경 시 파이프라인 상단부터 재실행하는 것이 AD-13 규약.)

**pipeline-shape 가드 2건 즉시 반려**: 초안 02_features가 (a) 41행(>40) (b) `write_with_meta`
호출의 `lambda tmp: ...` writer로 걸렸다. lambda 금지는 "stage는 main만 정의"의 일부.
→ writer 클로저를 `crm/common/atomic.py::write_parquet_with_meta`로 내려 메커니즘을 crm
계층이 소유하게 하고(AD-9), docstring 1줄 축약으로 40행 맞춤. 재검사 위반 0.

**실데이터 실행** (`data/bankchurners.parquet`, n=10,127):
```
02_features: features_customers.parquet rows=10127
cols: CLIENTNUM, recency_proxy, frequency_proxy, monetary_proxy, R_score, F_score, M_score
leakage cols present: []   monetary dtype: float64
R_score dist {1:737, 2:3846, 3:3282, 4:2262}  (4 buckets - 이산 붕괴, 문서화됨)
F_score dist {1:2076,2:2089,3:2077,4:1914,5:1971}  M_score dist ~2025 each (clean 5)
R vs recency corr -0.97 (반전 확인)   F vs freq corr +0.948
재실행 시 "is fresh, skipping" — is_output_stale skip 동작 확인
```

**테스트 검출력 실증 (1-2 리뷰 H3 교훈 계승)**: features 함수에 변이를 주입해 사살 확인.
R 반전 제거·M 상단 클립·누수 passthrough는 즉시 KILLED. 그러나 **"F가 monetary 소스를
쓰는" 변이가 최초에 생존** — `_spread` 픽스처에서 거래건수·금액이 함께 증가해 구분 불가했다.
F·M을 **반의존(anti-correlated)**으로 배치한 판별 테스트(`test_frequency_and_monetary_use_distinct_sources`)를
추가해 사살 확인. 성질 테스트만으로는 부족하다는 1-2 교훈이 이 스토리에서도 재현됐다.

### Completion Notes List

- **AC1 충족**: R←`Months_Inactive_12_mon`(극성 반전), F←`Total_Trans_Ct`, M←`customer_value()`
  각 1줄 정의를 `rfm-proxy-report-1-3.md`에 기재. 분위수 방식 선택 근거 + 실데이터 경계
  (R `[0,1,2,3,6]`·F `[10,41,61,73,83,139]`·M `[510,1914,3192.4,4267,4926,18484]`) 기록.
  경계는 런타임 산출, config엔 개수(`RFM_QUANTILES=5`, 선험 규약)만 — AD-1 준수.
- **AC2 충족**: 행동 기반 테스트 13건 + 하드코딩 oracle 1건. 동어반복(자체 qcut 재계산)
  없음. 변이 4종(R 반전·M 클립·F/M 소스 혼동·누수 passthrough) 전부 KILLED.
- **AC3 충족**: `write_parquet_with_meta`로 (parquet+meta) 원자적 기록. config drift 시
  `verify_inputs`가 실제로 stage를 중단시킴을 실행 중 확인(위 Debug Log).
- **AC4 (DQ2 부분 해소 — 리뷰 후 정정)**: `is_output_stale(output, inputs, *, expected_stage)`가
  소비 stage 자기 출력의 **stage·config_hash·직접 입력 해시**를 cache key로 검사. 02_features에
  `verify_inputs` 다음 2단 게이트로 배선. **닫지 못한 것은 정직하게 남김**(리뷰 High-2): 전이적
  staleness(05-only 재실행)·순수 코드변경·산출물 자체 변조 → deferred-work.md. 초기 "DQ2 CLOSED"
  과잉주장은 리뷰에서 지적받아 삭제. 단위 테스트 11건(config drift·stage 불일치·빈 입력 포함).
- **AC5 충족**: `RFM_OUTPUT_COLUMNS` 화이트리스트로 파생 지표만 산출 → `Naive_Bayes_Classifier_*`
  2컬럼 구조적 배제. 합성 누수 컬럼 주입 테스트로 실증. 1-6 감사가 재확인.
- **AD-11**: `features.py`는 `customer_value(df)`만 소비하고 `Total_Trans_Amt`를 명명하지
  않음. `find_value_recomputation_violations` scanned 10→11, 위반 0. 가드 무수정.
- **구조 가드 전종 green**: lane·layering·pipeline-shape·stateful-common·config·AD-11 모두 0 위반.
  커버리지 리포트 자동 재생성(pipeline shape 2 scanned, AD-11 11 scanned).
- **테스트**: 99 → 119 → 128 → **133 passed** (외부 리뷰 1·2차 반영), 회귀 0.

### File List

- `crm/segment/features.py` — NEW, RFM 프록시 순수 계산(M은 customer_value 소비)
- `pipelines/02_features.py` — NEW, 얇은 stage(main만, 40행), 2단 신선도 게이트
- `crm/common/freshness.py` — UPDATE, `is_output_stale()` 추가 + DQ2 docstring 정정
- `crm/common/atomic.py` — UPDATE, `write_parquet_with_meta()` 헬퍼(lambda를 crm으로 내림)
- `crm/config.py` — UPDATE, `RFM_QUANTILES=5`(선험 규약 상수)
- `tests/segment/test_features.py` — NEW, 행동 기반(5·10명 축별 oracle·qcut 엣지·순서불변·실누수명+실 stage 호출)
- `tests/common/test_freshness.py` — UPDATE, `is_output_stale`(config drift·stage·empty·OSError fail-closed)
- `docs/implementation-artifacts/rfm-proxy-report-1-3.md` — NEW, 세션 리포트(DQ2 한계 정정)
- `docs/implementation-artifacts/deferred-work.md` — UPDATE, 전이적 staleness·코드지문 미해결 기록
- `docs/implementation-artifacts/structure-guard-coverage.md` — UPDATE, pytest 재생성
- `docs/implementation-artifacts/1-3-rfm-proxy-features.md` — UPDATE, 본 기록
- `docs/implementation-artifacts/sprint-status.yaml` — UPDATE, 상태 전이

## Senior Developer Review (외부 GPT, 2026-07-21)

**판정: Changes Requested** — High 2, Medium 4, Low 2. **8건 전부 실증 재현 후 처리**(반려 0).
AD-11 배선·pipeline-shape·게이트 순서는 통과 확인받음.

### 실증 확인 (패치 전)

| # | 심각도 | 주장 | 실증 |
|---|---|---|---|
| 1 | High | `is_output_stale`가 출력 meta의 `config_hash`·stage 미검사 → 거짓 fresh | ✅ config drift·stage 불일치 둘 다 `False`(fresh) 반환 |
| 2 | High | "DQ2 CLOSED"·05-only 차단 주장이 전이적 staleness에 대해 거짓 | ✅ 코드상 직접 입력만 봄 — 성립 |
| 3 | Med | `qcut(duplicates="drop")` code가 비연속 → 점수 갭·전부동일 0점·NaN 초과점 | ✅ `[0,0,1,1,2,2]`→`[1,1,1,1,3,3]`(2 누락), 전부동일→0, NaN 반전→6 |
| 4 | Med | 하드코딩 oracle이 M축만 고정 → R clip 변이 생존 | ✅ R clip upper=3 SURVIVED |
| 5 | Med | 결정론 테스트가 행 순서 무관(AD-7) 미검증 | ✅ 동일순서 반복만 확인 |
| 6 | Med | AC5 테스트가 실컬럼명이 아닌 축약 가짜명 사용 | ✅ 표적 재부착 변이 미탐 |
| 7 | Low | unreadable meta에 `OSError` 미포함(문서와 불일치) | ✅ 권한/락은 crash |
| 8 | Low | `inputs=={}`+빈 입력을 fresh 판정 | ✅ 네트워크 stage 재사용 시 영구 fresh |

### 적용한 패치

- **[High-1]** `is_output_stale(output, inputs, *, expected_stage)`로 시그니처 변경 — 출력 meta의
  `stage == expected_stage` + `config_hash == config_hash()`를 cache key에 추가. RFM_QUANTILES
  변경 후 상위 meta 갱신 시나리오가 이제 stale 판정(실증 재확인 True). 02_features 배선 갱신.
- **[High-2]** "DQ2 CLOSED"·"canonical scenario blocked" 문구 **삭제**, freshness.py docstring·
  리포트를 "직접 입력 드리프트만 해소"로 정정. 전이적 staleness·순수 코드변경을 deferred-work에
  근거와 함께 기록(오케스트레이터 DAG 검증은 05 생기는 스토리 소관).
- **[Med-3]** 살아남은 code를 **dense-rank**해 갭 제거, 전부동일→단일버킷(1점), **NaN 거부**(fail-fast),
  `quantiles>=2` 검증, 빈 프레임 안전. "no gaps regardless" 거짓 주석 정정.
- **[Med-4]** R·F·M **축별 exact oracle** 추가(`[5,4,3,2,1]`/`[1,2,3,4,5]`/`[1,2,3,4,5]`) — R clip·
  F clip 변이 KILLED. (※ 2차 리뷰에서 버킷 수 팽창 변이 생존 발견 → 아래 2차 라운드에서 보강.)
- **[Med-5]** `random_state` 셔플 후 CLIENTNUM 정렬 비교로 **행 순서 불변** 직접 검증(동률 다수 fixture).
- **[Med-6]** 실제 누수 컬럼명 2개 전체를 fixture에 사용. (※ 2차 리뷰: 실제 stage 미호출 지적 → 아래 보강.)
- **[Low-7]** meta read에 `OSError` 포함, 입력 해시 실패도 fail-closed(True).
- **[Low-8]** 빈 입력은 `ValueError`(소비 stage 전용 계약 명시).

### 패치 후 재검증 (1차)

- High-1 config drift → stale True 재확인. 구조 가드 전종 0 위반. **119 → 128 passed**, 회귀 0.

### 2차 재리뷰 (외부 GPT, 2026-07-21) — Changes Requested → 4건 닫음

1차 판정 후 재리뷰가 **"문서가 테스트보다 앞서 결승선을 끊었다"**를 지적했다. 코드 방향은 맞지만
일부는 테스트/문서가 코드 현실을 앞질렀다. 4건 전부 실증 후 처리:

- **[High-2 doc 모순]** 하단 Completion Notes·docstring은 정정됐으나 **상단 AC4·T3·Dev Notes에
  05-only 차단 주장이 남아** 코드와 모순이었다. AC4를 "직접 입력 콘텐츠 드리프트 탐지"로
  **범위 축소**, T3 제목·Dev Notes DQ2 절을 동일 계약으로 통일. "05-only는 이 게이트로 안 잡힘"을
  명시.
- **[Med-4 잔여]** 5명/5분위 oracle은 **버킷 수 팽창 변이**(`quantiles + int(nunique>quantiles)`)를
  못 잡았다(실증: 5명 oracle 통과, 100명서 51% 상이). **10명/5분위 exact oracle**(`[1,1,2,2,3,3,4,4,5,5]`)
  추가 → 해당 변이 KILLED 재확인.
- **[Med-6 잔여]** stage 테스트가 실제 `main()`을 호출하지 않아 "원본을 기록하는" pipeline 회귀를
  못 잡았다. `importlib`로 `pipelines/02_features.py`를 로딩해 **실제 `main([src],[target])` 호출** +
  01_download meta 준비. 회귀 주입 시 FAIL 확인.
- **[Med-3 잔여]** 빈 프레임·`quantiles=1` 테스트가 없어 "4종 통과" 문구가 과장이었다.
  `test_empty_frame_returns_empty_feature_table`·`test_quantiles_below_two_are_rejected` 추가
  (빈 프레임은 `customer_value`까지 end-to-end).
- **[Low-7 잔여]** `OSError` fail-closed에 회귀 테스트 부재 → meta read·`file_sha256` 각각 monkeypatch로
  `PermissionError`/`OSError` 주입해 stale True 실증.

**2차 재검증**: 버킷 팽창·stage 회귀 변이 KILLED, 엣지 테스트 전부 green, 구조 가드 0 위반.
**128 → 133 passed**, 회귀 0.

## Change Log

| 날짜 | 변경 |
|---|---|
| 2026-07-21 | 스토리 1-3 create-story: RFM 프록시 + M축 AD-11 배선(customer_value 소비) + DQ2 is_output_stale + 누수 배제. Status → ready-for-dev. 기준선 99 passed |
| 2026-07-21 | 스토리 1-3 구현: features.py(RFM 프록시)·02_features(2단 게이트)·is_output_stale·누수 배제·분위수 리포트. 99 → 119 passed, 회귀 0. Status → review |
| 2026-07-21 | 외부 GPT 리뷰 8건 처리(High 2·Med 4·Low 2): High-1 config/stage cache key·High-2 과잉주장 정정+defer·Med-3 qcut dense-rank/엣지·Med-4 축별 oracle·Med-5 순서불변·Med-6 실누수명·Low-7 OSError·Low-8 빈입력. 119 → 128 passed, 회귀 0 |
| 2026-07-21 | 2차 재리뷰 4건 처리: High-2 AC4·T3·Dev Notes 범위 축소(05-only 차단 주장 삭제)·Med-4 10명 oracle로 버킷팽창 변이 사살·Med-6 실제 stage main() 호출 테스트·Med-3 빈프레임+quantiles=1 테스트·Low-7 OSError 회귀 테스트. 128 → 133 passed, 회귀 0 |
