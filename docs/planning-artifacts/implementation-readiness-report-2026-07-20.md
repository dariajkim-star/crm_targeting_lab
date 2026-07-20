---
stepsCompleted: [1, 2, 3, 4, 5, 6]
inputDocuments:
  - docs/specs/spec-crm-targeting-lab/SPEC.md
  - docs/specs/spec-crm-targeting-lab/stack.md
  - docs/specs/spec-crm-targeting-lab/conventions.md
  - docs/planning-artifacts/architecture/architecture-crm-targeting-lab-2026-07-16/ARCHITECTURE-SPINE.md
  - docs/planning-artifacts/architecture/architecture-crm-targeting-lab-2026-07-16/pipeline-diagram.md
  - docs/planning-artifacts/epics.md
---

# Implementation Readiness Assessment Report

**Date:** 2026-07-20
**Project:** crm-targeting-lab (P2)

## Document Inventory

| 유형 | 파일 | 상태 |
|---|---|---|
| PRD | 없음 — **의도적 부재**: conventions 1항 SPEC-first 경로. SPEC.md(CAP-1~8)가 요구사항 원천 | 대체 문서로 진행 |
| SPEC | `docs/specs/spec-crm-targeting-lab/SPEC.md` + companions(stack.md, conventions.md) | 단일본, 충돌 없음 |
| Architecture | `docs/planning-artifacts/architecture/architecture-crm-targeting-lab-2026-07-16/ARCHITECTURE-SPINE.md` + pipeline-diagram.md | 단일본(스파인, status: final) |
| Epics & Stories | `docs/planning-artifacts/epics.md` (4에픽/19스토리, 커밋 d7aea87) | 단일본 |
| UX | 없음 — **의도적 부재**: 자체 UI 없음, 외부 BI(Tableau). 화면 계약은 대시보드 사양서(스토리 4.3 산출물) 소관 | 해당 없음 |

중복(whole+sharded) 없음. `.memlog.md`는 스킬 작업 로그로 평가 대상 아님.

## PRD(=SPEC) Analysis

**방법 주의**: epics.md의 FR 목록을 신뢰하지 않고 SPEC + 스파인에서 **독립 재추출** 후 대조했다(epics.md 작성자와 이 점검자가 같은 세션이라는 한계는 있으나, 원문 대조는 수행).

### Functional Requirements (SPEC 재추출 → epics FR 번호 대조)

| SPEC 원천 | 요구사항 요지 | epics FR | 대조 |
|---|---|---|---|
| CAP-1 intent | RFM 프록시 지표 산출 | FR1 | 일치 |
| CAP-1 intent+success | K-means 세그먼트 + k 근거(elbow/실루엣) | FR2 | 일치(+AD-7 안정 ID 부가) |
| CAP-1 success | 프로필 리포트 + 페르소나 4~6 | FR3 | 일치 |
| CAP-2 intent | XGBoost + scale_pos_weight + CV + PR-AUC | FR4 | 일치 |
| CAP-2 success | baseline 대비 PR-AUC +15% 리프트 제시 | FR5 | 일치 |
| CAP-3 intent | SHAP 전역·개별 해석 | FR6 | 일치(+AD-5 아티팩트 고정 부가) |
| CAP-3 success | 세그먼트별 요인 top5 + 액션 매핑 | FR7 | 일치 |
| CAP-4 intent | BG/NBD+Gamma-Gamma(pymc-marketing) 12개월 LTV, 실패 시 코호트 폴백 | FR8 | 일치 |
| CAP-4 success | 적합도 요약 + 독립 산출물 명시 | FR9 | 일치(+MAP 라벨링 부가) |
| CAP-5 intent | 고객가치 = Total_Trans_Amt 실측 프록시 | FR10 | **부분 — Δ1 참조(보조 지표 문구)** |
| CAP-5 intent+success | 4분면 분류 + 분면별 고객수·정책 제안 + 근거·한계 | FR11 | **부분 — Δ2 참조(매트릭스 시각화)** |
| CAP-6 intent | 기대 절감액 산식 | FR12 | 일치 |
| CAP-6 intent+success | 고정 예산 우선순위 + 무작위 대비 X배 | FR13 | 일치 |
| CAP-7 | 그리드 ROI 등고선 + 결론 반전 구간 해석 | FR14 | 일치 |
| CAP-8+AD-2 | mart_customers + 스키마 | FR15 | 일치 |
| CAP-8+AD-2 | mart_ltv_demo + 스키마 | FR16 | 일치 |
| CAP-8 | 대시보드 사양서 4탭 | FR17 | 일치 |
| CAP-8+OQ-5 | Tableau 퍼블리시 + README 링크(분업) | FR18 | 일치 |

SPEC에서 재추출한 요구사항 18건, epics FR 18건 — **번호 체계 1:1 대응, 유실·중복 없음**. 델타 2건은 아래.

**Δ1 (CAP-5 보조 지표 문구)**: SPEC CAP-5 intent는 "보조 지표 `Total_Revolving_Bal`·`Credit_Limit` 활용도"를 언급하나, FR10/AD-11은 가치 정의를 `Total_Trans_Amt` **단일**로 고정했다. 이는 스파인 AD-11이 **의도적으로 닫은 문**이다("보조 지표 허용 문구가 이원화의 문을 연다"). 스파인이 SPEC보다 후행 결정이므로 구현 방향은 FR10이 맞다 — 다만 SPEC 문구가 소급 개정되지 않아 **문서 간 표면 불일치**로 남아 있다.

**Δ2 (CAP-5 매트릭스 시각화)**: CAP-5 success는 "매트릭스 **시각화** + 분면별 고객 수·정책 제안"인데, 스토리 3.1 AC는 판정·고객수·정책 제안까지만 명시하고 시각화 산출물을 명시하지 않는다. 시각화는 E4(Tableau 타겟팅 탭)로 이연된 구조인데, 그 연결이 어느 AC에도 적혀 있지 않다.

### Non-Functional Requirements (SPEC Constraints + Success signal 재추출)

| SPEC 원천 | epics NFR | 대조 |
|---|---|---|
| 가정 파라미터 "가정" 라벨링 | NFR1 | 일치 |
| 라벨 단면성 표기 | NFR2 | 일치 |
| 통화 규율(원 통화·환산 금지) | NFR3 | 일치 |
| 재현성(시드·파이프라인 스크립트화) + AD-7 | NFR4 | 일치(바이트 동일로 강화) |
| 데이터·아티팩트 gitignore + 마트 예외 | NFR5 | 일치 |
| 테스트 필수(RFM·산식) + 스파인 테스트 3종 | NFR6 | 일치(4종으로 확장) |
| 공개 노출(AD-10) | NFR7 | 일치 |
| 5분 파악(Success signal ③) | NFR8 | 일치 |
| 신선도·원자적 쓰기(AD-13) | NFR9 | 일치 |

SPEC 제약 중 "데이터 분리"·"데이터마트 계약"·"LTV 라이브러리"는 NFR가 아닌 FR/AC(1.1a import-graph, 4.1/4.2, 2.2)로 흡수 — 누락 아님.

### Additional Requirements

- Non-goals 5종(A/B·실시간 서빙·추천·레코드 결합·시계열 예측) — 위반하는 스토리 없음(step-03에서 재검).
- OQ-5(Tableau 계정)만 미결 — 4.4 blocked-external 분업으로 흡수됨. **사용자 계정 확보 여부는 여전히 미확인** — P1 3-3 SAS 선례처럼 dev 전 확인 권장.
- Assumptions 4건(공개 데이터 다운로드 가능·프록시 타당성·성공률 30% 보수값·표준 스택) — 스토리 AC에 반영 확인.

### PRD Completeness Assessment

SPEC은 CAP별 intent/success 구조로 명확하고, 스파인과의 델타 3건(마트 2분할·pymc-marketing·4탭)은 이미 소급 개정되어 반영돼 있다. 잔여 표면 불일치는 Δ1 하나(CAP-5 보조 지표 문구). 전반 판정: **요구사항 원천으로서 충분**.

## Epic Coverage Validation

### Coverage Matrix

기계 추출(grep 기반 FR 태그 → 스토리 트레이스) + AC 본문 수동 확인 병행. FR10은 1차 기계 추출에서 누락으로 나왔으나 **추출 패턴의 한계**(괄호 중간 위치 `…, FR10·AD-11)` 미매칭)로 확인 — AC 본문에 실재(epics.md:200).

| FR | Epic/Story | AC 검증 | 상태 |
|---|---|---|---|
| FR1 | E1 / 1.3 | R·F·M 정의 1줄 + 구간화 근거 AC | ✓ |
| FR2 | E1 / 1.4 | elbow/실루엣 + 안정 ID AC | ✓ |
| FR3 | E1 / 1.5 | 프로필 표 + 페르소나 4~6 AC(k 불일치 시 정직 기록 포함) | ✓ |
| FR4 | E1 / 1.6 | scale_pos_weight·CV·PR-AUC AC | ✓ |
| FR5 | E1 / 1.6 | 리프트 수치 + 미달 명시 AC | ✓ |
| FR6 | E1 / 1.7 | 03 단계 단독 산출 + 읽기 전용 AC | ✓ |
| FR7 | E1 / 1.7 | top5 → 액션 번역 AC | ✓ |
| FR8 | E2 / 2.1+2.2 | 입력 형태 확보 + 적합 + 폴백 AC | ✓ |
| FR9 | E2 / 2.3 | 적합도 + 비결합 명시 AC | ✓ |
| FR10 | E1 / 1.2 | 단일 함수·원척도·재계산 금지 테스트 AC | ✓ |
| FR11 | E3 / 3.1 | QUADRANT_RULE·Enum·경계 테스트·분면별 고객수 AC | ✓ (Δ2: 시각화 연결 미명시) |
| FR12 | E3 / 3.2 | 산식 + config 참조 + 행동 기반 테스트 AC | ✓ |
| FR13 | E3 / 3.3 | 전순서 + 무작위 대비 배수 AC | ✓ |
| FR14 | E3 / 3.4 | 등고선 + 반전 구간 해석 AC | ✓ |
| FR15 | E4 / 4.1 | 유일 writer·행수 보존·바이트 동일 AC | ✓ |
| FR16 | E4 / 4.2 | 2분할·GBP 명시·부분 산출 금지 AC | ✓ |
| FR17 | E4 / 4.3 | 4탭 + AD-3 체크리스트 AC | ✓ |
| FR18 | E4 / 4.4 | blocked-external 분업 + 절차서 AC | ✓ |

### Missing Requirements

없음.

### Coverage Statistics

- SPEC 재추출 FR: 18 / epics 커버: 18 / **커버리지 100%**
- epics에만 있고 SPEC에 없는 FR: 0 (1.1a/1.1b는 FR 무배정 기반 스토리 — 그린필드 표준 패턴, 이슈 아님)

## UX Alignment Assessment

### UX Document Status

**Not Found — 의도적 부재이며 UX가 "암시"되지도 않는다.** 자체 UI가 없다: 서빙 API도 프론트엔드도 없고(SPEC non-goal: 실시간 서빙), 소비 계층은 외부 BI 도구(Tableau Public)다. P1(Streamlit 대시보드 보유)과 달리 P2는 세션이 렌더링하는 화면 자체가 없다.

### 화면 계약의 대체 소유자

UI 스펙의 역할은 세 겹으로 분산 소유된다:

1. **대시보드 사양서**(스토리 4.3 산출물) — 4탭 구성·시트·필드 매핑. UX 문서의 기능적 등가물.
2. **AD-3** — 시나리오 뷰 검사 4항목(제목 접두·별도 탭·배경색·임계값 병기)이 사양서에 강제 편입됨(4.3 AC 확인).
3. **AD-10** — 퍼블리시 = 공개 노출 규칙.

P1 준비도 점검 때 "2.5 dev 컨텍스트에 UX 레퍼런스 첨부" 권고 선례가 있다. P2 등가물: **4.3 create-story 시 Tableau Public 갤러리의 세그먼트/이탈 대시보드 레퍼런스 + AD-3 체크리스트를 dev 컨텍스트에 첨부** 권장(Minor, 차단 아님).

### Alignment Issues

없음 — UX 부재가 PRD(SPEC)·Architecture와 정합적이다(스파인 Deferred 1항이 "워크북 내부 구조는 사양서 소관"을 명시).

### Warnings

없음.

## Epic Quality Review

### 에픽 구조 검증

| 검사 | 결과 |
|---|---|
| 사용자 가치 중심 | ✓ 4에픽 모두 사용자 결과 서술("누가 왜 떠나는가"·"방법론 데모"·"누구를 얼마의 비용으로"·"5분 파악"). 기술 마일스톤 에픽 없음 |
| 에픽 독립성 | ✓ E1 단독 성립. E2는 E1·E3 없이 성립(격리 레인). E3는 E1만 소비. E4는 E1~E3 소비(정상 후행). **역방향(EN이 EN+1 요구) 없음** |
| 파일 churn | ✓ 에픽별 대상 모듈 분리(segment/churn ↔ ltv ↔ campaign ↔ marts). config.py 공유는 AD-4 의도된 단일 출처 |
| 그린필드 셋업 | ✓ 1.1a가 Structural Seed 담당(스파인에 스타터 템플릿 미지정 — 표준 패턴). 1.1a/1.1b는 FR 무배정 기반 스토리로 허용 범위 |
| DB/엔티티 타이밍 | ✓ 마트 컬럼은 4.1/4.2에서만, 모델 아티팩트는 1.6에서만 생성 — 선행 대량 생성 없음 |

### 스토리 의존성 검증 (전수)

- E1: 1.1a → 1.1b → 1.2 → 1.3 → 1.4(1.2+1.3 소비) → 1.5 → 1.6 → 1.7(1.6 소비) — 전방 의존 0
- E2: 2.1 → 2.2 → 2.3 — 전방 의존 0
- E3: 3.1(1.2·1.6 소비) → 3.2 → 3.3(3.1+3.2 소비) → 3.4(3.2 반복 호출) — 전방 의존 0
- E4: 4.1 → 4.2 → 4.3 → 4.4 — 전방 의존 0
- 참고: 1.1a AC의 "1.1b가 추가하는 순간 자동 적용" 문구는 **서술적 예고이지 의존이 아님** — 1.1a는 파일 부재 상태에서 단독 완결(AC에 명시됨).

### AC 품질

Given/When/Then 형식 전 스토리 준수. 에러 경로 AC 존재 확인: 1.1b(다운로드 실패·부분 산출 금지), 2.2(폴백 발동 명시), 3.3(예산 0·빈 대상), 4.2(레인 편측 실패). P1 준비도 점검에서 잡혔던 "에러경로 AC 부재" 유형 재발 없음.

### 발견 사항

#### 🔴 Critical — 0건

#### 🟠 Major — 0건

#### 🟡 Minor — 3건

**M1. SPEC CAP-5 보조 지표 문구 소급 개정 필요 (= Δ1)**
AD-11/FR10이 가치 정의를 `Total_Trans_Amt` 단일로 고정했으나 SPEC CAP-5 intent의 "보조 지표 활용" 문구가 남아 있다. P1 2-2 선례(구현이 계약 의미를 바꾸면 스펙 소급 개정) 적용 대상. **권고**: 1.2 dev 전 SPEC 한 줄 개정(보조 지표는 프로파일 서술용으로 강등, 가치 축 산입 금지 명시).

**M2. E3 산출물의 물리적 위치 미매핑 (Δ2 포함)**
파이프라인은 01→02→03→04→05 다섯 단계뿐이고 campaign 계산은 05_marts가 소비한다(스파인 다이어그램 P5→CAMP). 따라서 E3 스토리(3.1~3.4)의 실데이터 실행 산출물(분면별 고객수, X배, ROI 등고선, 매트릭스 시각화)은 **공식 마트 반영 전의 세션 리포트**다 — 이 지위가 epics.md 어디에도 명시돼 있지 않다. CAP-5 success의 "매트릭스 시각화"가 어느 산출물(리포트 차트 vs Tableau 탭)로 이행되는지도 미지정. **권고**: 3.1 create-story 시 Dev Notes에 "E3 산출물 = `docs/implementation-artifacts/` 리포트(P1 관례), 공식 수치·시각화의 최종 자리는 4.1 마트 + 4.3 Tableau 타겟팅 탭"을 명시. 코드·구조 변경 불요.

**M3. 1.2 "산출 리포트" 생산 주체 모호**
`customer_value()`는 순수 함수인데 1.2 AC의 "산출 리포트"를 누가 만드는지(파이프라인 단계 아님 — M2와 동일 계열) 미지정. **권고**: M2와 같은 해법 — create-story Dev Notes에서 리포트 = 세션 산출물로 명시. 차단 아님.

### 모범 사례 체크리스트

- [x] 에픽이 사용자 가치 전달
- [x] 에픽 독립 성립
- [x] 스토리 크기 적정(1.1 분할 기완료, 1.6이 상대적으로 큼 — P1 1-5 유사 규모 소화 선례로 수용)
- [x] 전방 의존 없음
- [x] 테이블/컬럼 필요 시점 생성
- [x] AC 명확·검증 가능
- [x] FR 추적성 유지(18/18)

## Summary and Recommendations

### Overall Readiness Status

**READY** — Critical 0 / Major 0 / Minor 3. 세 건 모두 차단 아님, 지정된 시점(스토리 create/dev)에 흡수 가능.

### Critical Issues Requiring Immediate Action

없음.

### Minor Issues 처리 계획

| # | 이슈 | 처리 시점 |
|---|---|---|
| M1 | SPEC CAP-5 "보조 지표 활용" 문구가 AD-11 단일 정의와 표면 불일치 | **1.2 dev 전** SPEC 한 줄 소급 개정 |
| M2 | E3 산출물(등고선·매트릭스 시각화)의 물리적 지위 미명시 — 세션 리포트 vs 공식 마트/Tableau | **3.1 create-story** Dev Notes에 명시 |
| M3 | 1.2 "산출 리포트" 생산 주체 모호 | **1.2 create-story** Dev Notes에 명시(M2 동일 해법) |

### 외부 의존 알림 (이슈 아님, 관리 항목)

- **OQ-5 Tableau Public 계정** — 4.4 blocked-external 분업으로 설계돼 있어 차단 없음. 단 P1 3-3(SAS 계정 확인 후 풀 스코프 전환) 선례처럼, **E4 착수 전 사용자 계정 확보를 확인**하면 4.4 스코프를 확정할 수 있다.
- **pymc-marketing 첫 실사용** — 2.2에 폴백 AC가 있어 리스크는 흡수돼 있으나, E2가 이 프로젝트에서 검증 안 된 유일한 신규 스택이다. 2.1 dev 시 조기 스모크(임포트+초소형 적합) 권장.

### Recommended Next Steps

1. `_bmad/bmm/config.yaml`의 `planning_artifacts`/`implementation_artifacts`를 P2 경로로 전환(sprint-status.yaml이 P1 폴더에 생성되는 것 방지).
2. `bmad-sprint-planning` 실행 → 4에픽/19스토리 sprint-status.yaml 생성(M1~M3·OQ-5를 상단 주석으로 이월).
3. Fresh context에서 스토리 1.1a create-story → dev-story 사이클 개시.

### Final Note

이 점검은 3개 카테고리(커버리지/정합성/품질)에서 Minor 3건을 식별했다. FR 커버리지 100%(18/18), 전방 의존 0, 에러경로 AC 재발 0. 점검자: 세션(Opus 4.8) — epics.md 작성 세션과 동일하다는 한계를 명시하며, SPEC 원문 독립 재추출로 보완했다.
