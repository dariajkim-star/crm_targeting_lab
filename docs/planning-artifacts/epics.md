---
stepsCompleted: [1, 2, 3, 4]
inputDocuments:
  - docs/specs/spec-crm-targeting-lab/SPEC.md
  - docs/specs/spec-crm-targeting-lab/stack.md
  - docs/specs/spec-crm-targeting-lab/conventions.md
  - docs/planning-artifacts/architecture/architecture-crm-targeting-lab-2026-07-16/ARCHITECTURE-SPINE.md
  - docs/planning-artifacts/architecture/architecture-crm-targeting-lab-2026-07-16/pipeline-diagram.md
---

# crm-targeting-lab (P2) - Epic Breakdown

## Overview

이 문서는 crm-targeting-lab의 에픽·스토리 분해다. **PRD는 없다** — conventions.md 1항(SPEC-first 경로)에 따라 SPEC(CAP-1~8·제약·non-goal)이 요구사항 원천이고, 아키텍처 스파인(AD-1~13)이 기술 요구사항 원천이다. 아래 FR/NFR은 그 두 문서에서 추출·번호화한 것이며, 새로운 요구사항을 만들지 않는다.

## Requirements Inventory

### Functional Requirements

FR1: RFM 프록시 지표를 BankChurners 변수에서 산출한다(구간화 방식은 데이터 분포를 보고 결정하되 BankChurners 분포에서만 도출). — CAP-1
FR2: K-means로 고객 세그먼트를 분리하고 k 선정 근거(elbow/실루엣)를 제시한다. 클러스터는 `customer_value` 중앙값 내림차순 안정 ID(`segment_id` 1..k)로 정규화한다. — CAP-1, AD-7
FR3: 세그먼트별 인구통계·행동 프로파일과 페르소나 4~6개를 문서로 산출한다. — CAP-1
FR4: XGBoost로 이탈위험 확률을 추정한다. 불균형 처리(scale_pos_weight)·교차검증·PR-AUC 병행 평가를 포함한다. — CAP-2
FR5: baseline 로지스틱 회귀를 학습하고 PR-AUC 리프트(+15% 목표)를 비교표로 제시한다. — CAP-2
FR6: SHAP 전역·개별 해석을 `03_train_churn` 단계에서 산출하고 아티팩트로 고정한다(후속 단계는 읽기만). — CAP-3, AD-5
FR7: 세그먼트별 이탈요인 top5를 리텐션 액션으로 번역한 매핑 문서를 산출한다. — CAP-3
FR8: Online Retail II에 BG/NBD + Gamma-Gamma(pymc-marketing)를 적용해 12개월 기대 LTV를 고객별로 추정한다. 적합 실패 시 코호트 기반 단순 LTV로 폴백한다. — CAP-4
FR9: LTV 모델 적합도 요약과 **2×2와 결합하지 않는 독립 산출물**임을 산출물에 명시한다. MAP 적합 시 "구간 없는 점추정"으로 라벨링한다. — CAP-4, AD-1
FR10: 고객가치를 `crm/segment/value.py::customer_value(df) -> Series[float]` 단일 함수가 정의한다(현 정의: `Total_Trans_Amt` 실측 프록시). 모든 소비자는 이 출력만 쓰고 재계산·재가중하지 않는다. — CAP-5, AD-11
FR11: `assign_quadrant()` 단일 함수가 `quadrant_official`(Save 우선/관망/저비용 유지/이탈 수용)을 산출하고, 분면별 고객 수·정책 제안과 가치 프록시의 근거·한계를 산출물에 명시한다. — CAP-5, AD-12
FR12: 기대 절감액 = P(이탈) × 고객가치 × 리텐션 성공률 − 캠페인 비용 산식을 구현한다(기본값은 `crm/config.py` 참조). — CAP-6, AD-4
FR13: 고정 예산 제약 하 `target_priority`(기대절감액 내림차순 dense rank, 동점 시 `customer_value` 내림차순, 그래도 동점이면 `CLIENTNUM` 오름차순)를 산출하고 "무작위 타겟 대비 기대 절감액 X배"를 제시한다. — CAP-6, AD-12
FR14: 리텐션 성공률 × 건당 비용 그리드에서 ROI 등고선을 산출하고 "어떤 가정 구간에서 결론이 뒤집히는가"를 해석한다. 산식은 `simulate.py`를 반복 호출할 뿐 재구현하지 않는다. — CAP-7, AD-9
FR15: `marts/mart_customers.csv` + `.schema.md`를 산출한다(BankChurners 전 고객 행 수 보존, 공식 판정 컬럼·`threshold_official_*` 포함). — CAP-8, AD-2, AD-3
FR16: `marts/mart_ltv_demo.csv` + `.schema.md`를 산출한다(모집단 필터를 스키마 문서에 명시). — CAP-8, AD-2
FR17: 대시보드 사양서를 산출한다 — 고객분석 3탭 + LTV 데모 1탭 = 4탭, AD-3 시나리오 뷰 검사 체크리스트 4항목 포함. — CAP-8, AD-3
FR18: Tableau Public 워크북 제작·퍼블리시 및 README 링크 연결(외부 의존 분업 — 세션은 마트·사양서까지, 실행은 사용자). — CAP-8, OQ-5, AD-10

### NonFunctional Requirements

NFR1: 실측이 아닌 파라미터(리텐션 성공률·건당 비용·가치 프록시)는 산출물에서 "가정"으로 라벨링하고 근거·한계를 병기한다.
NFR2: `Attrition_Flag`는 사후 단면 라벨이다 — 코드·리포트·대시보드 전반에서 "이탈 위험 분류(cross-sectional)"로 표기하고 시계열 예측으로 제시하지 않는다. (AD-6)
NFR3: 금액은 데이터 원 통화 그대로(BankChurners 무단위, Online Retail II GBP), 무단 환산 금지. 예산 시나리오는 통화 중립. (P1 3-4 통화 오기 교훈)
NFR4: 결정론적 재현 — 모든 확률적 연산이 단일 `RANDOM_SEED`를 명시 수신하고, 파이프라인 2회 연속 실행 시 두 마트 CSV가 **바이트 동일**해야 한다. (AD-7)
NFR5: 데이터·모델 아티팩트는 gitignore하고 재생성 스크립트로 대체한다. 마트 CSV는 커밋 대상 예외.
NFR6: pytest 필수 — ① RFM 산식·기대절감액 산식(**행동 기반**, 동어반복 검증 금지) ② 마트 스키마 일치(AD-2) ③ 결정론 바이트 동일(AD-7) ④ `ast` import-graph 레인 격리·의존 방향(AD-1·AD-9).
NFR7: 퍼블리시는 공개 노출이다 — 마트에는 공개 데이터셋 유래 값만 담는다. 전제가 깨지면 게시하지 않고 로컬 Tableau Desktop Public Edition으로 축소한다. (AD-10)
NFR8: README + Tableau 링크로 **5분 안에 전체 스토리 파악** 가능해야 한다.
NFR9: 산출물 신선도 — 각 단계는 `<output>.meta.json`(입력 SHA-256·`config_hash`·커밋·시각·행수)을 쓰고, 입력 meta 불일치 시 실패한다. 마트 쓰기는 임시파일 → 원자적 rename. (AD-13)

### Additional Requirements

아키텍처 스파인(AD-1~13)에서 도출된, 스토리 경계와 AC에 직접 영향을 주는 기술 요구사항:

- **스타터 템플릿 없음** — 그린필드. 첫 스토리가 Structural Seed(`crm/`·`pipelines/`·`marts/`·`tests/` + `crm/config.py`)를 세운다.
- **AD-1 레인 물리 격리**: `crm/churn/`·`crm/segment/` ↔ `crm/ltv/` 상호 import 금지, 한 레인 도출값의 타 레인 유입 금지(하드코딩·config 등재·공유 유틸 fit 상태 포함), `crm/common/`은 stateless 순수 함수만, `05_marts`는 두 레인을 순차 처리(동시 스코프 보유 금지).
- **AD-2 마트 2분할**: 마트는 정확히 2개, `.schema.md`가 정규·망라적, `pipelines/05_marts.py`가 `marts/`의 유일 writer, 행 수 보존 assert.
- **AD-3 판정 소유권**: 공식 판정은 Python이 계산해 마트 컬럼으로 고정, BI는 표시만. 시나리오 뷰는 검사 가능한 4항목 충족, `_scenario` 접미. README 수치는 공식 뷰에서만.
- **AD-4 설정 단일 출처**: `crm/config.py` 하나뿐(추가 YAML/TOML/JSON/.env 금지), 기본값이 상수를 참조, import 시점 `assert RETENTION_SUCCESS_RATE in RETENTION_GRID` 등 대표값 포함 검증.
- **AD-5 아티팩트 정체성**: `churn_prob`·SHAP·요인 top5는 동일 학습 아티팩트에서 산출, `models/churn_model.meta.json`의 `artifact_id` 불일치 시 `05_marts` 즉시 실패.
- **AD-8 파일로만 통신**: 각 단계는 `main(input_paths, output_paths)` 시그니처만, 단계 간 전역 상태·메모리 공유 금지.
- **AD-9 의존 방향**: `pipelines/` → `crm/` → `crm/config.py` 단방향, `pipelines/NN_*.py`는 파일당 40행 이하·`main` 외 `def` 금지, `crm/campaign/` 내부는 `matrix.py` → `simulate.py` → `sensitivity.py`.
- **CSV 직렬화 고정**: `na_rep=""`, `float_format="%.6f"`, utf-8(BOM 없음), `lineterminator="\n"`, `index=False`, 컬럼 순서는 스키마 문서 순서. 센티널 결측 표현 금지.
- **스택 고정**: Python 3.12 / pandas 3.x / scikit-learn 1.9.x / XGBoost 3.3.x / SHAP 0.52.x / pymc-marketing 0.19.4 / pytest 9.x.
- **운영 envelope**: 로컬 배치 실행만 — 서버·API·스케줄러·컨테이너·클라우드·CI는 스코프 밖.
- **외부 의존 분업**(conventions 7): Tableau 워크북 제작·퍼블리시는 사용자 실행. 세션 산출물(마트·사양서)은 이에 블로킹되지 않는다.

### UX Design Requirements

**해당 없음** — 자체 UI가 없다. 소비 계층은 외부 BI 도구(Tableau Public)이며, 화면 설계는 UX 스펙이 아니라 **대시보드 사양서**(FR17)가 소유한다. AD-3(시나리오 뷰 표기 체크리스트)·AD-10(공개 노출)이 그 사양서의 제약이다.

### FR Coverage Map

| FR | Epic | 비고 |
|---|---|---|
| FR1 RFM 프록시 지표 | Epic 1 | BankChurners 분포에서만 도출(AD-1) |
| FR2 K-means 세그먼트 + k 근거 | Epic 1 | 안정 ID 정렬에 FR10 출력 소비 |
| FR3 세그먼트 프로필·페르소나 | Epic 1 | |
| FR4 XGBoost 이탈위험 확률 | Epic 1 | |
| FR5 baseline 대비 PR-AUC 리프트 | Epic 1 | 성공신호 ① |
| FR6 SHAP 산출·아티팩트 고정 | Epic 1 | AD-5 단일 아티팩트 |
| FR7 요인 top5 → 리텐션 액션 매핑 | Epic 1 | |
| FR8 BG/NBD + Gamma-Gamma LTV | Epic 2 | 폴백 분기 존재 |
| FR9 적합도 요약 + 비결합 명시 | Epic 2 | AD-1 |
| **FR10 `customer_value` 단일 정의** | **Epic 1** | **AD-11. `crm/segment/value.py` = 세그먼트 레인 소속이므로 E1이 소유하고 E3가 소비(역방향 의존 회피)** |
| FR11 `assign_quadrant` 2×2 판정 | Epic 3 | AD-12 |
| FR12 기대절감액 산식 | Epic 3 | AD-4 기본값 |
| FR13 `target_priority` + 무작위 대비 X배 | Epic 3 | AD-12 전순서, 성공신호 ② |
| FR14 민감도 ROI 등고선 + 반전 구간 | Epic 3 | AD-9 재구현 금지 |
| FR15 `mart_customers.csv` + 스키마 | Epic 4 | AD-2, AD-3 |
| FR16 `mart_ltv_demo.csv` + 스키마 | Epic 4 | AD-2 |
| FR17 대시보드 사양서(4탭 + AD-3 체크리스트) | Epic 4 | |
| FR18 Tableau 퍼블리시 + README 링크 | Epic 4 | blocked-external 분업, 성공신호 ③ |

FR 18/18 커버, 미매핑 없음.

## Epic List

### Epic 1: 고객 이해 — 세그먼트와 이탈 위험
BankChurners 레인 전체. 파이프라인 골격·`crm/config.py`·AD-13 meta 규약을 세운 뒤, 고객가치 단일 정의 → RFM 세그먼트 → XGBoost 이탈위험 → SHAP 요인 해석까지 완결한다. 이 에픽만으로 "누가 있고, 누가 왜 떠나는가"에 답하는 독립 산출물(세그먼트 프로필·페르소나·이탈 모델 비교표·액션 매핑)이 남는다.
**FRs covered:** FR1, FR2, FR3, FR4, FR5, FR6, FR7, FR10

### Epic 2: LTV 확률 모델 데모
Online Retail II 격리 레인. BG/NBD + Gamma-Gamma(pymc-marketing)로 12개월 기대 LTV를 추정하고, 적합 실패 시 코호트 기반 단순 LTV로 폴백한다. 2×2와 결합하지 않는 독립 방법론 데모임을 산출물에 명시한다. E1·E3와 상호 독립이며, 에픽 경계가 곧 AD-1 물리 격리다.
**FRs covered:** FR8, FR9

### Epic 3: 타겟팅 의사결정 프레임
E1의 이탈확률과 `customer_value`를 소비해 2×2 공식 판정 → 캠페인 시뮬레이터 → 민감도 분석을 완결한다. 판정 규칙은 AD-12에 따라 단일 함수가 소유하고, 가정 파라미터는 AD-4 단일 출처를 참조한다. "누구를 우선 잡고, 얼마 쓰고, 그 결론이 어느 가정 구간에서 뒤집히는가"에 답한다.
**FRs covered:** FR11, FR12, FR13, FR14

### Epic 4: 데이터마트와 BI 공개
두 레인의 산출물을 마트 2종 + 정규 스키마 문서로 고정하고(`05_marts`가 유일 writer), 4탭 대시보드 사양서와 README를 산출한 뒤 Tableau Public에 공개한다. 5분 안에 전체 스토리가 전달되는 공개 산출물이 목표다. FR18은 세션이 실행할 수 없어 P1 3-3 선례대로 분업(`blocked-external`)한다.
**FRs covered:** FR15, FR16, FR17, FR18

---

## 에픽 공통 DoD

P1 선례 계승(conventions 2·3·6·8·9항). 모든 에픽은 아래를 충족해야 done이다.

1. **실데이터 실행** — 합성 mock 초록만으로 done 금지. 실데이터 실행이 리포트 수치를 만든다.
2. **정직성** — 목표 미달·네거티브 결과를 산출물에 명시한다. 미달은 실패가 아니다.
3. **3-레이어 코드리뷰**(Blind/Edge/Auditor) → triage → 스토리 파일 기록.
4. **스토리 단위 커밋**, 데이터·모델 아티팩트 gitignore.
5. **옵시디언 미러** — 에픽 요약을 `ob_storage/신용평가_CRM_사이드프로젝트/`에 기록(에픽 종료까지 미루지 않고 중간 미러 허용 — P1 2-2 선례).

---

## Epic 1: 고객 이해 — 세그먼트와 이탈 위험

BankChurners 레인 전체. 파이프라인 골격·`crm/config.py`·AD-13 meta 규약을 세운 뒤, 고객가치 단일 정의 → RFM 세그먼트 → XGBoost 이탈위험 → SHAP 요인 해석까지 완결한다.

### Story 1.1a: 프로젝트 골격·설정 단일 출처·구조 가드 테스트

As a 분석가,
I want 프로젝트 골격과 설정 단일 출처, 그리고 구조 규약을 기계적으로 강제하는 테스트를,
So that 이후 모든 코드가 첫 줄부터 AD-1 격리·AD-4 단일 출처·AD-9 의존 방향 위에서 쌓인다.

**Acceptance Criteria:**

**Given** 빈 저장소에서 Structural Seed(`crm/{config,common,segment,churn,campaign,ltv}`, `pipelines/`, `marts/`, `models/`, `tests/`)를 생성했을 때
**When** 디렉터리와 스텁 모듈을 확인하면
**Then** 스파인의 Structural Seed와 일치하고, `.gitignore`가 `data/`·`models/`를 제외하되 `marts/`는 커밋 대상 예외로 둔다(NFR5)

**Given** `crm/config.py`를 작성했을 때
**When** import하면
**Then** `RANDOM_SEED`·경로·정책 가정 상수가 정의되고, 각 상수에 출처 주석(`# source: 정책가정`)이 붙어 있다
**And** 데이터에서 도출된 값이 하나도 없다(AD-1)
**And** `assert RETENTION_SUCCESS_RATE in RETENTION_GRID`·`assert COST_PER_CONTACT in COST_GRID`가 import 시점에 실행되어, 위반 시 import 자체가 실패한다(AD-4)
**And** 설정 파일은 이 파일 하나뿐이다 — 추가 YAML·TOML·JSON·`.env` 설정 파일이 존재하지 않음을 테스트가 검증한다(AD-4)

**Given** pytest 기반이 구성됐을 때
**When** `ast` import-graph 테스트를 실행하면
**Then** `crm/`이 `pipelines/`를 import하지 않음, `crm/segment|churn` ↔ `crm/ltv` 상호 import 없음, `crm/campaign/` 내부가 `matrix → simulate → sensitivity` 단방향임을 기계적으로 검증한다(AD-1·AD-9)
**And** `pipelines/NN_*.py`에 대해 파일당 40행 이하·`main` 외 `def` 금지를 검증한다 — **파일이 아직 없어도 규칙이 등록되어 있어, 1.1b가 첫 파이프라인을 추가하는 순간 자동 적용된다**
**And** `crm/common/`에 fit 상태를 보유한 객체가 없음(stateless 순수 함수만)을 검증한다(AD-1)

### Story 1.1b: 신선도·원자적 쓰기 규약과 데이터 확보

As a 분석가,
I want 단계 산출물의 신선도 검증·원자적 쓰기 규약과 재실행 가능한 데이터 확보 스크립트를,
So that 이후 모든 파이프라인 단계가 stale한 부분 재실행과 반쯤 쓰인 산출물로부터 보호된다.

**Acceptance Criteria:**

**Given** 신선도·원자적 쓰기 유틸을 `crm/common/`에 둘 때
**When** 유틸을 사용하면
**Then** `<output>.meta.json`(입력 파일 SHA-256·`config_hash`·코드 커밋·생성 시각·행수)을 쓰는 단일 경로가 제공된다(AD-13)
**And** 산출물 쓰기는 임시 파일 → 원자적 rename 경로만 제공하며, 실패 시 부분 산출물을 남기지 않는다(AD-13)
**And** 입력 meta 검증 함수가 (a) 입력이 자기 선행 단계 산출물인지 (b) 입력 `config_hash`가 현재 `crm/config.py` 해시와 일치하는지 확인하고 불일치 시 실패시킨다
**And** 유틸은 stateless 순수 함수이며, 쓰기 *메커니즘*은 `crm/common/atomic.py`가 단독 소유하고 *경로·정책*은 호출부(`pipelines/`)가 정한다(AD-1·AD-9, 2026-07-20 컨벤션 개정)

**Given** 신선도 규약을 검증해야 할 때
**When** pytest를 실행하면
**Then** `config_hash` 불일치·선행 단계 불일치 상황에서 **실패가 실제로 발생함**을 확인하는 테스트가 있다(경고로 통과하지 않음)
**And** 쓰기 도중 예외 발생 시 대상 경로에 파일이 생성되지 않음을 검증한다

**Given** `pipelines/01_download.py`를 실행할 때
**When** BankChurners·Online Retail II를 확보하면
**Then** 두 원본이 `data/`에 저장되고 gitignore되며, 각 산출물에 `.meta.json`이 함께 기록된다(AD-13)
**And** 스크립트는 `main(input_paths, output_paths)` 시그니처를 따르고 40행 이하이며 `main` 외 `def`를 정의하지 않는다(AD-8·AD-9)
**And** 1.1a의 구조 가드 테스트가 이 새 파일에 대해 통과한다

**Given** 데이터 확보가 실패하거나 원본을 구할 수 없을 때
**When** 스크립트를 실행하면
**Then** 실패가 명시적으로 보고되고 부분 산출물·빈 파일을 남기지 않는다
**And** 확보 절차와 폴백(수동 다운로드 경로)이 README에 문서화된다(NFR5)

### Story 1.2: 고객가치 단일 정의

As a 분석가,
I want 고객가치를 한 함수가 배타적으로 정의하기를,
So that 2×2·기대절감액·민감도·마트가 같은 고객에게 서로 다른 가치를 매기는 모순이 구조적으로 불가능해진다.

**Acceptance Criteria:**

**Given** BankChurners 프레임이 주어졌을 때
**When** `crm/segment/value.py::customer_value(df)`를 호출하면
**Then** `Total_Trans_Amt` 실측 프록시 기반 `Series[float]`을 **원척도 그대로** 반환한다(정규화·로그 변환 없음 — 스케일링은 판정 단계 소관, FR10·AD-11)
**And** 함수는 순수하며 파일을 쓰지 않는다

**Given** 가치 프록시의 타당성과 한계가 문서화되어야 할 때
**When** 산출 리포트를 확인하면
**Then** 선정 근거(연간 거래액 = 수수료 수익의 1차 동인)와 한계(수익성≠거래액, 보조 지표 미반영)가 "가정"으로 라벨링되어 명시된다(NFR1)

**Given** 다른 모듈이 고객가치를 필요로 할 때
**When** 코드베이스를 검사하면
**Then** `Total_Trans_Amt`를 직접 참조해 가치를 재계산·재가중하는 코드가 `value.py` 외에 존재하지 않는다
**And** 이 금지를 검증하는 테스트가 있다

### Story 1.3: RFM 프록시 지표 산출

As a 분석가,
I want BankChurners 변수로 RFM 프록시 지표를 산출하기를,
So that 카드 고객을 행동 기반으로 세분화할 재료가 생긴다.

**Acceptance Criteria:**

**Given** `pipelines/02_features.py`가 원본을 읽을 때
**When** RFM 프록시를 산출하면
**Then** R·F·M 각각이 어떤 원본 변수에서 어떻게 도출됐는지 리포트에 1줄씩 정의된다(FR1)
**And** 구간화 방식(분위수 vs 고정 경계)의 선택과 근거가 기록되며, 경계는 **BankChurners 분포에서만** 도출된다(AD-1)

**Given** RFM 산식이 구현됐을 때
**When** pytest를 실행하면
**Then** 산식 테스트는 **행동 기반**이다 — 구현과 동일한 공식을 재구현해 비교하는 동어반복 검증이 아니라, 알려진 입력→기대 순위/구간 관계로 검증한다(NFR6, P1 2-2 부호반전 교훈)

**Given** 02 단계가 완료됐을 때
**When** 산출물을 확인하면
**Then** 피처 파일과 `<output>.meta.json`이 함께 쓰이고, 입력 meta의 `config_hash`가 현재 `config.py` 해시와 불일치하면 단계가 실패한다(AD-13)

### Story 1.4: K-means 세그먼트와 안정 ID

As a 분석가,
I want 근거 있는 k로 세그먼트를 나누고 세그먼트 번호가 재실행에도 고정되기를,
So that 리포트의 "세그먼트 3"이 조용히 다른 집단을 가리키는 사고가 일어나지 않는다.

**Acceptance Criteria:**

**Given** RFM 피처가 주어졌을 때
**When** K-means를 적합하면
**Then** `random_state`·`n_init`이 `RANDOM_SEED`에서 명시적으로 주입된다(AD-7)
**And** elbow/실루엣 곡선과 k 선정 근거가 산출물에 제시된다(FR2)

**Given** 클러스터가 생성됐을 때
**When** 세그먼트 ID를 부여하면
**Then** 원시 클러스터 인덱스가 아니라 `customer_value` 중앙값 내림차순으로 재정렬한 안정 ID(`segment_id` 1..k)를 쓴다(AD-7)
**And** `customer_value`는 1.2의 함수 출력을 소비하며 재계산하지 않는다(AD-11)

**Given** 결정론이 요구될 때
**When** 세그멘테이션을 2회 연속 실행하면
**Then** `segment_id` 배정이 완전히 동일하다
**And** 이를 검증하는 테스트가 존재한다(NFR4)

### Story 1.5: 세그먼트 프로필과 페르소나

As a 마케팅 의사결정자,
I want 각 세그먼트가 누구인지 프로필과 페르소나로 읽히기를,
So that 이후 리텐션 액션을 사람 단위로 상상할 수 있다.

**Acceptance Criteria:**

**Given** 세그먼트가 확정됐을 때
**When** 프로필 리포트를 생성하면
**Then** 세그먼트별 인구통계·행동 지표 요약표와 고객 수·비중이 산출된다
**And** 페르소나 4~6개가 정의된다(FR3)

**Given** 리포트에 수치가 인용될 때
**When** 출처를 확인하면
**Then** 모든 수치가 커밋된 코드 경로로 재현 가능하고 출처가 명시된다(NFR/conventions 4항)
**And** 금액성 지표는 BankChurners **무단위**로 표기되고 임의 통화 기호를 붙이지 않는다(NFR3)

**Given** 세그먼트 수가 k에 따라 달라질 때
**When** 페르소나가 4개 미만 또는 6개 초과로 나오면
**Then** 페르소나를 억지로 맞추지 않고 실제 k와 그 사유를 리포트에 기록한다(정직성)

### Story 1.6: 이탈위험 분류 모델과 baseline 리프트

As a 분석가,
I want XGBoost 이탈위험 분류기와 baseline 로지스틱 비교를,
So that 모델이 단순 기준선 대비 실제로 얼마나 나은지 정직하게 말할 수 있다.

**Acceptance Criteria:**

**Given** `pipelines/03_train_churn.py`가 피처를 읽을 때
**When** baseline 로지스틱과 XGBoost를 학습하면
**Then** 불균형 처리(`scale_pos_weight`)·교차검증이 적용되고 PR-AUC를 병행 평가한다(FR4)
**And** XGBoost는 `random_state`·**`n_jobs=1`**·`tree_method`가 고정된다(AD-7 — 스레드 수에 따른 부동소수 축약 순서 차이가 분위수 경계에서 고객을 분면 넘나들게 한다)

**Given** 두 모델 성능이 산출됐을 때
**When** 비교표를 확인하면
**Then** baseline 대비 PR-AUC 리프트가 수치로 제시된다(FR5)
**And** **+15% 목표 미달이어도 실패로 처리하지 않고** 미달 사실과 원인 분석을 리포트에 명시한다(정직성, P1 1-7a 선례)

**Given** 학습이 끝났을 때
**When** 아티팩트를 저장하면
**Then** `models/churn_model.meta.json`에 `artifact_id`(콘텐츠 해시)·`trained_at`·`RANDOM_SEED`·입력 파일 해시·feature 목록·라이브러리 버전이 기록된다(AD-5)
**And** `churn_scored.parquet`이 `artifact_id`를 보유한다

**Given** 라벨 성격을 표기해야 할 때
**When** 코드 docstring·리포트·컬럼 정의를 확인하면
**Then** "이탈 위험 분류(cross-sectional)"로 표기되고 시계열 예측 표현이 쓰이지 않는다(NFR2·AD-6)

### Story 1.7: SHAP 이탈요인 해석과 리텐션 액션 매핑

As a 마케팅 의사결정자,
I want 세그먼트별 이탈 요인 top5와 그에 대응하는 리텐션 액션을,
So that "위험하다"가 아니라 "그래서 무엇을 하라"까지 전달된다.

**Acceptance Criteria:**

**Given** 1.6의 학습 아티팩트가 있을 때
**When** SHAP을 산출하면
**Then** SHAP 값과 요인 top5가 **`03_train_churn` 단계에서만** 계산되어 아티팩트로 저장되고, 후속 단계는 읽기만 한다(FR6·AD-5 — 재학습 금지만으로는 부족)
**And** SHAP 배경 샘플링이 `RANDOM_SEED`를 수신한다(AD-7)

**Given** `churn_prob`와 SHAP 해석이 함께 소비될 때
**When** 정체성을 검증하면
**Then** 둘이 동일 `artifact_id`에서 유래함이 확인되고, 불일치 시 즉시 실패한다(AD-5)

**Given** 전역·개별 SHAP 해석이 나왔을 때
**When** 액션 매핑 문서를 확인하면
**Then** 세그먼트별 이탈요인 top5가 구체적 리텐션 액션으로 번역된다(예: 거래 감소형 → 사용처 쿠폰, 한도 불만형 → 한도 상향 제안)(FR7)
**And** 액션은 실측이 아닌 제안임이 라벨링된다(NFR1)

---

## Epic 2: LTV 확률 모델 데모

Online Retail II 격리 레인. 2×2와 결합하지 않는 독립 방법론 데모다. 에픽 경계가 곧 AD-1 물리 격리다.

### Story 2.1: 거래 로그 정제와 고객 단위 요약

As a 분석가,
I want Online Retail II 거래 로그를 고객 단위 RFM 요약으로 정제하기를,
So that BG/NBD가 요구하는 입력 형태(frequency·recency·T·monetary)가 갖춰진다.

**Acceptance Criteria:**

**Given** 원본 거래 로그가 주어졌을 때
**When** `pipelines/04_ltv_demo.py`가 정제하면
**Then** 반품·취소·결측 고객 ID 처리 규칙이 명시적으로 적용되고 각 규칙의 제거 행수가 로깅된다(FR8 전제 — BG/NBD 입력 형태 확보)
**And** 모집단 필터(최소 거래건수 등)와 그 사유가 문서에 기록된다(AD-2 — 이후 마트 스키마에 명시될 값)

**Given** 고객 단위 요약이 산출됐을 때
**When** 컬럼을 확인하면
**Then** 금액은 **GBP 원 통화 그대로**이며 무단 환산이 없다(NFR3)
**And** 고객 식별자는 원본 키(`Customer ID`)를 보존한다

**Given** AD-1 격리가 적용될 때
**When** `crm/ltv/` 모듈을 검사하면
**Then** `crm/segment`·`crm/churn`을 import하지 않고, BankChurners 유래 값(상수·경계·인코딩)을 일절 쓰지 않는다

### Story 2.2: BG/NBD + Gamma-Gamma 12개월 기대 LTV

As a 분석가,
I want 확률적 구매 모델로 고객별 12개월 기대 LTV를 추정하기를,
So that 단순 과거 합계가 아닌 확률 모델 기반 가치 추정 역량을 보인다.

**Acceptance Criteria:**

**Given** 고객 단위 요약이 주어졌을 때
**When** pymc-marketing으로 BG/NBD와 Gamma-Gamma를 적합하면
**Then** `random_seed`·`chains`·`draws`·`tune`이 `crm/config.py`에 고정되어 주입된다(AD-7 — MCMC는 확률적이다)
**And** 고객별 12개월 기대 LTV 테이블이 산출된다(FR8)

**Given** 적합 방식을 선택해야 할 때
**When** MAP 경로를 택하면
**Then** 산출물이 **"구간 없는 점추정"**으로 라벨링되고 MAP이 검증기간 구매횟수를 과대예측하는 경향이 한계로 기록된다(NFR1)

**Given** pymc-marketing 적합이 실패할 때
**When** 폴백이 작동하면
**Then** 코호트 기반 단순 LTV로 대체되고, 폴백 발동 사실·사유·방법 차이가 산출물에 명시된다(정직성)
**And** 폴백이 조용히 성공한 것처럼 보이지 않는다

**Given** 결정론이 요구될 때
**When** 적합을 2회 연속 실행하면
**Then** LTV 산출값이 동일하다(NFR4)

### Story 2.3: 적합도 요약과 비결합 경계 문서화

As a 포트폴리오 독자,
I want LTV 모델이 얼마나 맞는지와 이것이 2×2와 무관한 산출물임을 분명히 알기를,
So that 두 데이터셋이 결합됐다는 오해가 생기지 않는다.

**Acceptance Criteria:**

**Given** LTV 모델이 적합됐을 때
**When** 적합도 요약을 확인하면
**Then** 검증 기간 실제 대비 예측 비교 등 적합도 지표가 제시된다(FR9)
**And** 과대/과소 예측 경향이 정직하게 기록된다

**Given** 독자가 2×2와의 관계를 물을 때
**When** 리포트 서두를 읽으면
**Then** **"CAP-5의 2×2와 결합하지 않는 독립 산출물이며 모집단이 다르다"**가 명시된다(FR9·AD-1)
**And** 왜 결합이 불가능한지(레코드 수준 매핑 부재)가 1문단으로 설명된다

**Given** 격리를 기계적으로 보장해야 할 때
**When** import-graph 테스트를 실행하면
**Then** 이 에픽의 산출 경로 어디에서도 BankChurners 레인과의 결합이 검출되지 않는다(AD-1)

---

## Epic 3: 타겟팅 의사결정 프레임

E1의 이탈확률과 `customer_value`를 소비해 2×2 공식 판정 → 시뮬레이터 → 민감도를 완결한다. 판정 규칙은 단일 함수가 소유한다.

### Story 3.1: 2×2 공식 판정

As a 마케팅 의사결정자,
I want 이탈위험 × 고객가치 4분면 판정이 한 곳에서만 내려지기를,
So that 대시보드의 "Save 우선" 분면과 캠페인 타겟 리스트가 어긋나지 않는다.

**Acceptance Criteria:**

**Given** 이탈확률과 `customer_value`가 주어졌을 때
**When** `crm/campaign/matrix.py::assign_quadrant()`를 호출하면
**Then** `quadrant_official`이 산출되고, 임계 방식·값·경계 포함 규칙(상단 `>=`)은 `crm/config.py`의 `QUADRANT_RULE`에서만 온다(AD-12)
**And** 4분면 라벨 문자열 4종(Save 우선/관망/저비용 유지/이탈 수용)은 config의 Enum으로 고정되며 자유 문자열이 아니다

**Given** `matrix.py`의 책임 범위를 검사할 때
**When** 코드를 확인하면
**Then** 예산·비용 개념을 알지 못한다(4분면은 예산과 무관, AD-9)
**And** `customer_value`를 재계산하지 않고 1.2 함수 출력을 소비한다(AD-11)

**Given** 경계값 고객이 존재할 때
**When** 임계값과 정확히 같은 값을 가진 고객을 판정하면
**Then** `>=` 규칙에 따라 결정론적으로 상단 분면에 배정되고, 이를 검증하는 경계 테스트가 있다

**Given** 판정 결과가 산출됐을 때
**When** 리포트를 확인하면
**Then** 분면별 고객 수와 분면별 정책 제안이 제시된다(FR11)
**And** 가치 프록시의 근거·한계가 재명시된다(NFR1)

### Story 3.2: 캠페인 기대 절감액 시뮬레이터

As a 마케팅 의사결정자,
I want 고객별 기대 절감액을 산식으로 계산하기를,
So that 캠페인의 가치를 금액 개념으로 비교할 수 있다.

**Acceptance Criteria:**

**Given** 이탈확률·고객가치·가정 파라미터가 주어졌을 때
**When** `crm/campaign/simulate.py`가 계산하면
**Then** 기대 절감액 = P(이탈) × 고객가치 × 리텐션 성공률 − 캠페인 비용이 구현된다(FR12)
**And** 성공률·비용의 **기본값이 `crm/config.py` 상수를 참조**하며 리터럴로 재선언되지 않는다(AD-4)

**Given** 산식 테스트를 작성할 때
**When** pytest를 실행하면
**Then** 테스트는 **행동 기반**이다 — 동일 공식을 재구현해 비교하지 않고, 파라미터 단조성(성공률↑ → 절감액↑, 비용↑ → 절감액↓)과 부호 전환 지점으로 검증한다(NFR6)

**Given** 파라미터를 바꿔가며 실행해야 할 때
**When** 스윕을 수행하면
**Then** 설정 파일이 아니라 **함수 인자**로 주입된다(AD-4)

**Given** 통화 표기가 필요할 때
**When** 산출물을 확인하면
**Then** BankChurners 무단위 그대로 표기되고 임의 통화 기호·환산이 없다(NFR3, P1 3-4 교훈)

### Story 3.3: 예산 제약 타겟 우선순위

As a 마케팅 의사결정자,
I want 고정 예산 안에서 누구를 먼저 잡을지 순위와 그 효과를,
So that "무작위로 뿌리는 것보다 몇 배 낫다"를 수치로 말할 수 있다.

**Acceptance Criteria:**

**Given** 기대 절감액이 산출됐을 때
**When** `crm/campaign/priority.py::target_priority()`를 호출하면
**Then** 기대절감액 내림차순 dense rank(1이 최우선), 동점 시 `customer_value` 내림차순, 그래도 동점이면 `CLIENTNUM` 오름차순으로 **전순서가 보장**된다(AD-12)
**And** 동일 입력에 대해 재실행 시 순위가 바뀌지 않는다(Tableau 정렬이 새로고침마다 뒤바뀌지 않도록)

**Given** 고정 예산 시나리오가 주어졌을 때
**When** 예산 한도까지 상위 N명을 선택하면
**Then** 무작위 타겟 대비 기대 절감액 배수가 산출된다(FR13, 성공신호 ②)
**And** 무작위 기준선은 `RANDOM_SEED`로 고정되어 재현 가능하다(AD-7)

**Given** 우선순위가 `quadrant_official`과 함께 소비될 때
**When** 일관성을 검사하면
**Then** 시뮬레이터가 자체 컷을 만들지 않고 3.1의 `quadrant_official` 컬럼을 소비함이 확인된다(AD-12)

**Given** 예산이 0이거나 대상이 없을 때
**When** 시뮬레이터를 실행하면
**Then** 조용히 빈 결과를 반환하지 않고 명시적으로 처리·기록한다(P1 2-1 빈 모집단 교훈)

### Story 3.4: 민감도 분석과 결론 반전 구간

As a 마케팅 의사결정자,
I want 가정이 틀렸을 때 결론이 언제 뒤집히는지를,
So that 실험 없이도 이 제안을 어디까지 신뢰할 수 있는지 안다.

**Acceptance Criteria:**

**Given** 성공률 × 건당 비용 그리드가 config에 정의됐을 때
**When** `crm/campaign/sensitivity.py`를 실행하면
**Then** ROI 등고선 데이터가 산출된다(FR14)
**And** `simulate.py`를 파라미터만 바꿔 반복 호출할 뿐 산식을 재구현하지 않는다(AD-9)

**Given** 그리드와 대표값의 정합이 요구될 때
**When** config를 import하면
**Then** 대표값이 그리드에 포함되어 있음이 assert되어, 시뮬레이터 결론이 항상 민감도 곡선 위에 있다(AD-4, P1 `current_cutoff` 이원화 사고 방지)

**Given** 등고선이 산출됐을 때
**When** 해석을 확인하면
**Then** **"어떤 가정 구간에서 결론이 뒤집히는가"**가 명시적으로 서술된다(FR14)
**And** 손익분기가 되는 성공률·비용 조합이 수치로 제시된다

**Given** 가정의 지위를 표기해야 할 때
**When** 산출물을 확인하면
**Then** 성공률 30% 등 대표값이 "가정(업계 통용 보수값, 실측 아님)"으로 라벨링되고 정답으로 주장되지 않는다(NFR1)

---

## Epic 4: 데이터마트와 BI 공개

두 레인 산출물을 마트 2종 + 정규 스키마로 고정하고, 4탭 사양서·README를 산출한 뒤 Tableau Public에 공개한다.

### Story 4.1: 고객 마트와 정규 스키마

As a BI 소비자,
I want 고객 단위 분석 결과가 스키마가 고정된 단일 CSV로 제공되기를,
So that Tableau가 중간 산출물이 아닌 안정된 계약면만 소비한다.

**Acceptance Criteria:**

**Given** `pipelines/05_marts.py`가 두 레인 입력을 읽을 때
**When** `marts/mart_customers.csv`를 생성하면
**Then** 이 스크립트가 `marts/`의 **유일한 writer**이며 다른 단계·모듈은 쓰지 않는다(FR15·AD-2)
**And** 두 레인은 순차 처리된다 — A 마트를 쓰고 프레임을 해제한 뒤 B를 로드하며, 두 프레임이 동시에 스코프에 존재하지 않는다(AD-1)

**Given** `mart_customers.schema.md`가 작성될 때
**When** 스키마를 확인하면
**Then** 모든 컬럼이 `name | dtype | 단위 | nullable | 산출 모듈 | 정의 1줄`로 망라 열거되고, `quadrant_official`·`target_priority`·`segment_id`·`churn_prob`·`customer_value`·`threshold_official_*`가 포함된다(AD-2·AD-3)
**And** pytest가 `set(df.columns) == schema.columns`와 dtype 일치를 검증한다

**Given** 행 수 보존이 요구될 때
**When** 마트를 생성하면
**Then** BankChurners 원본 전 고객 행 수가 보존되고(산출 불가 값은 행 삭제가 아니라 null) `05_marts`가 기대 행 수를 assert한다(AD-2)
**And** 센티널(`-1`·`"NULL"`·`0`)로 결측을 표현하지 않으며, non-nullable 컬럼에 null이 있으면 실패한다

**Given** 아티팩트 정체성을 검증할 때
**When** 입력의 `artifact_id`가 불일치하면
**Then** `05_marts`가 경고가 아니라 **즉시 실패**한다(AD-5)

**Given** 결정론이 요구될 때
**When** 파이프라인을 2회 연속 실행하면
**Then** 마트 CSV가 **바이트 동일**하고 `tests/test_determinism`이 이를 검증한다(NFR4·AD-7)
**And** 직렬화가 고정된다(`na_rep=""`, `float_format="%.6f"`, utf-8 BOM 없음, `lineterminator="\n"`, `index=False`, 스키마 순서)

### Story 4.2: LTV 데모 마트와 스키마

As a BI 소비자,
I want LTV 데모 결과가 고객 마트와 물리적으로 분리된 별도 CSV로 제공되기를,
So that 두 데이터셋이 결합됐다는 인상이 산출물 수준에서 차단된다.

**Acceptance Criteria:**

**Given** LTV 산출물이 준비됐을 때
**When** `marts/mart_ltv_demo.csv`를 생성하면
**Then** 마트는 정확히 2개이며 두 마트를 조인하는 코드·워크북 계산이 존재하지 않는다(FR16·AD-2)
**And** 금액 컬럼 단위가 **GBP**로 스키마에 명시된다(NFR3)

**Given** `mart_ltv_demo.schema.md`를 작성할 때
**When** 스키마를 확인하면
**Then** 모집단 필터(최소 거래건수 등)와 기대 행 수가 명시되고 4.1과 동일한 망라성 규칙을 따른다
**And** MAP 적합 시 "구간 없는 점추정"이 컬럼 정의에 반영된다(NFR1)

**Given** 한 레인이 실패할 때
**When** `05_marts`를 실행하면
**Then** 두 레인 중 하나만 실패해도 나머지 마트를 갱신하지 않는다(AD-13 부분 산출 금지)
**And** 마트 쓰기는 임시 파일 → 원자적 rename으로 수행된다

### Story 4.3: 대시보드 사양서

As a 워크북 제작자(사용자),
I want 무엇을 어떤 탭에 어떻게 그릴지가 명세된 사양서를,
So that 세션 없이도 Tableau 워크북을 규약대로 만들 수 있다.

**Acceptance Criteria:**

**Given** 마트 2종이 확정됐을 때
**When** 사양서를 작성하면
**Then** 고객분석 3탭(`mart_customers`) + LTV 방법론 데모 1탭(`mart_ltv_demo`) = **4탭** 구성과 각 탭의 시트·차트·필드 매핑이 명세된다(FR17)
**And** 각 탭이 어느 마트에 연결되는지 명시되고 두 마트를 조인하는 계산필드를 금지한다(AD-2)

**Given** 시나리오 뷰가 허용될 때
**When** 사양서의 체크리스트를 확인하면
**Then** AD-3 검사 가능한 4항목이 그대로 실린다 — ① 시트 제목이 `[시나리오] `로 시작 ② 공식 뷰와 다른 탭 ③ 다른 배경색 ④ 현재 임계값과 공식 임계값 병기
**And** 시나리오 계산필드는 `_scenario` 접미를 갖고 `_official` 컬럼을 재계산하는 계산필드를 만들지 않음이 명시된다

**Given** BI의 역할 경계를 규정할 때
**When** 사양서를 읽으면
**Then** 공식 판정은 Python이 계산해 마트 컬럼으로 고정되어 있고 **BI는 표시하며 재계산하지 않음**이 선언된다(AD-3)
**And** README·발표자료의 모든 스크린샷·수치는 공식 뷰에서만 취한다는 규칙이 포함된다

### Story 4.4: 공개 점검·README·Tableau 퍼블리시 (blocked-external)

As a 포트폴리오 독자,
I want 링크 하나로 5분 안에 전체 스토리를 파악하기를,
So that 이 프로젝트가 무엇을 했고 무엇을 하지 않았는지 빠르게 판단된다.

**Acceptance Criteria:**

**Given** 퍼블리시 전 안전 점검이 필요할 때
**When** 마트 내용을 검사하면
**Then** 공개 데이터셋(BankChurners·Online Retail II) 유래 값만 포함됨이 확인된다(AD-10·NFR7)
**And** 커밋 이력에 데이터·모델 아티팩트 유입이 0건임이 확인된다(P1 3-4 공개점검 선례)
**And** 게시 시 마트 내용이 공개 조회 가능해진다는 사실이 문서에 명시된다

**Given** README를 작성할 때
**When** 독자가 읽으면
**Then** 핵심 수치표·발견·한계·문서 지도가 5분 내 파악 가능하게 구성된다(NFR8, 성공신호 ③)
**And** 모든 가정(데이터 결합 불가, 라벨 단면성, 성공률·비용 가정, 통화)이 명시된다(성공신호 ④)
**And** 목표 미달 지표가 있으면 숨기지 않고 표기된다(정직성)

**Given** 세션이 Tableau를 실행할 수 없을 때
**When** 이 스토리를 관리하면
**Then** **`blocked-external`로 분업**된다 — 세션은 마트·스키마·사양서·README 초안·퍼블리시 절차서까지 산출하고, 워크북 제작·퍼블리시·링크 확보는 사용자가 수행한다(FR18, conventions 7항, P1 3-3 선례)
**And** 사용자 실행 절차가 단계별로 문서화된다
**And** Tableau 링크 미확보가 나머지 산출물의 done을 블로킹하지 않는다
