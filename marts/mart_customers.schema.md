# `mart_customers.csv` — 정규 스키마 (AD-2, AD-12)

**산출 스테이지**: `pipelines/05_marts.py` (Lane A / 고객 레인 단독).
**조립 로직**: `crm/marts/customers.py::build_customer_mart` (CLIENTNUM 라벨 조인).
**기대 행 수**: **10,127** — BankChurners 원본 전 고객. 행 삭제 없음, 센티널 없음, 전 컬럼 non-nullable (AC4).
**LTV 레인 미포함**: AD-1은 두 레인 순차 처리를 규정하나, epic-2 동결로 `04_ltv` 산출물이 없다. 이 마트는 **A 레인(고객)만** 담는다. LTV 데모 마트는 4-2 범위(`crm/marts/ltv.py`, Lane B).

이 문서가 **컬럼 순서의 단일 출처**다. CSV 직렬화 순서(`crm/marts/customers.py::MART_COLUMNS`)와 정확히 일치하며, pytest가 `set(df.columns) == 이 표의 컬럼` + dtype 일치를 강제한다(AC3).

## 직렬화 규약 (AC6·NFR4 — 2회 실행 바이트 동일)

| 항목 | 값 |
|---|---|
| 인코딩 | UTF-8, **BOM 없음** |
| 개행 | `\n` (lineterminator) |
| 인덱스 | `index=False` — CLIENTNUM은 조립 시 **인덱스**, CSV엔 **첫 컬럼**으로 직렬화(`reset_index`) |
| float 포맷 | `%.6f` (float 컬럼에만 적용; int 컬럼은 정수 스펠링 유지) |
| 결측 표기 | `na_rep=""` (현 아티팩트는 결측 0건 — 방어적 고정) |
| 행 순서 | **CLIENTNUM 오름차순** (정준형; 입력 행 순서와 무관하게 바이트 동일) |

## 컬럼 (순서 = CSV 직렬화 순서)

`용도/금지` 칸은 BI 소비자를 위한 오용 방지 표기다(4-1b, 3-0 코드리뷰 D3 인계). 코드 안에서는
함수 시그니처·컬럼 이름 가드가 오선택을 막지만, **BI 드롭다운에는 가드가 없다** — 검사 불가능한
것에는 문서가 유일한 수단이다(파티 판정). 화면에 어느 컬럼을 노출할지는 4-3 소관(층 분리).

| name | dtype | 단위 | nullable | 산출 모듈 | 정의 (1줄) | 용도/금지 |
|---|---|---|---|---|---|---|
| `CLIENTNUM` | int64 | ID | no | 원본(BankChurners) | 고객 식별자. 세 소스의 **라벨 조인 키**이자 마트의 정체성. 유일. | 조인·식별 전용. 집계 금지. |
| `segment_id` | int64 | 범주(1–4) | no | `crm/segment/segments.py` | K-means 세그먼트 ID(1–4, 실측). features_customers에서 그대로 소비. | 그룹핑 전용. 크기 비교 무의미(명목 척도). |
| `customer_value` | float64 | 원척도(무통화, NFR3) | no | `crm/segment/value.py::customer_value` | 고객 가치 = `Total_Trans_Amt`(원척도). **가정**: 거래액이 가치의 1차 프록시(SPEC CAP-5). 정규화·로그 없음. AD-11 단일 정의. | 금액 축. 재가중·재계산 금지(AD-11). |
| `churn_score` | float32 | 확률스케일 순위신호 [0,1] | no | `crm/churn/model.py` (03) | **원(비보정) out-of-fold** 이탈 점수. 2x2 분면이 소비하는 순위 신호. | **순위 전용 — 금액 산식 사용 금지**(오선택 시 총합 +19.0% 부풀림, 3-2 실측: 1,730,042 vs 정답 1,454,088). |
| `churn_prob_calibrated` | float64 | 확률 [0,1] | no | `crm/churn/calibrate.py` (3-0) | **Platt 보정** 이탈 확률. expected_saving의 확률 입력. | **금액 전용 — 분면 컷 재계산에 사용 금지**(3-1은 원점수 소유; isotonic류 재보정은 분면을 바꿀 수 있음). churn_score와 한 프레임 공존 — 드롭다운 오선택 주의. |
| `quadrant_official` | object (str) | 범주(ASCII enum) | no | `crm/campaign/matrix.py::assign_quadrant` | 공식 2x2 분면: `save_first`·`watch`·`low_cost_keep`·`accept_churn`. 경계 상단 `>=`(AD-12). 라벨·임계값 **단일 계산**. | 소비 전용. 자체 컷 재계산 금지(AD-12). |
| `threshold_official_risk` | float64 | 확률스케일 [0,1] | no | `crm/campaign/matrix.py` | 이 모집단에서 실현된 위험 컷 = churn_score의 `risk_quantile=0.75` 분위. 전 행 동일(브로드캐스트). 시나리오 뷰의 기준선(AD-3). | 검산·기준선 표시 전용. |
| `threshold_official_value` | float64 | 원척도 | no | `crm/campaign/matrix.py` | 실현된 가치 컷 = customer_value의 `value_quantile=0.50`(중위). 전 행 동일. | 검산·기준선 표시 전용. |
| `expected_saving` | float64 | 원척도(무통화, NFR3) | no | `crm/campaign/simulate.py::expected_saving` | 1회 접촉 기대절감 = `churn_prob_calibrated · customer_value · retention_rate − cost`. **가정**: `retention_rate=0.30`·`cost_per_contact=5.0`(정책가정, NFR1). 음수 가능(=접촉 안 함). | 감사 컬럼(target_priority 검산용). 가정 라벨 없이 인용 금지(NFR1). |
| `target_priority` | int64 | 순위(1..n) | no | `crm/campaign/priority.py::target_priority` | 접촉 우선순위. **정의 고정(AD-12)**: 아래 참조. | **순위≠추천** — 상위 N 절단으로 캠페인 선택 대체 금지(선택은 `campaign_selected` 규칙, 아래). |

## `target_priority` 정의 (AD-12 — 단일 소유, 여기 고정)

> **기대절감액(`expected_saving`) 내림차순 dense rank(1이 최우선). 동점 시 `customer_value` 내림차순, 그래도 동점이면 `CLIENTNUM` 오름차순 — 전순서(strict total order) 보장. 전원 10,127명에게 순위 부여(누락·동점 없음).**

- **전원 순위**: 음수 절감 고객도 순위에서 제외하지 않고 마지막에 배치한다 — 마트는 nullable 컬럼을 갖지 않으며, "순위≠추천"이다(예산·양수 컷으로 실제 **선택**하는 `campaign_selected`는 4-1b 범위).
- **dense는 여기서 무의미(inert)**: `CLIENTNUM`이 유일하므로 복합키에 중복이 없어 `dense`/`min`/`first`가 모두 `1..n`으로 동일하게 붕괴한다. 타이브레이크 체인이 실제로 발화하지 않지만(실측: 10,127개 절감액 전부 상이), 두 고객이 순위를 공유하면 Tableau 뷰가 새로고침 간 순서를 뒤바꿀 수 있으므로 전순서를 계약으로 못박는다.

## `campaign_selected` — 정의는 여기 고정, 컬럼은 비탑재 (AD-12 / 4-1b D1)

**정의(AD-12 단일 소유, 여기 고정)**: *"`campaign_selected` = `target_priority ≤ 예산이 사는 접촉
수` AND `expected_saving > 0` — 산출 함수는 `crm/campaign/priority.py::select_within_budget`(단일
소유), 예산·접촉비용은 호출 인자. 예산이 남아도 음수 절감 고객은 사지 않는다(**3-3 D1** — 실측
1,456,900 vs 전원 구매 1,454,088, 출처: `priority.py` 모듈 docstring·`priority-report-3-3.md`)."*

**이 마트에 컬럼이 없는 이유(비탑재 — 4-1b D1)**: 선택은 **예산의 함수**이고 공식 단일 예산은 존재하지
않는다 — 3-3의 결론이 정확히 "배수는 예산의 함수, 헤드라인은 곡선이지 한 점이 아니다"였다. 임의의
예산 하나를 config에 박아 컬럼을 실체화하면 **시나리오 입력을 사실로 세탁**하는 것이다. 선택의
실체화는 예산이 주어지는 소비 지점(4-3 시나리오 뷰)에서 `select_within_budget` 호출로 수행한다.
`target_priority`만으로 상위 N을 잘라 선택을 흉내내면 양수 컷이 빠진다 — 위 표의 "순위≠추천" 금지
칸이 그 오용을 막는 표기다.

## 감사 가능성 (마트=계약면)

이 마트만으로 화면의 분면·우선순위를 **검산**할 수 있어야 한다(3-0 코드리뷰 D3, 층 분리 원칙). 그래서 `expected_saving`을 **감사 컬럼으로 포함**한다 — `target_priority`가 이 축의 dense rank로 정의되므로, 이것이 없으면 마트만으로 순위를 재현할 수 없다.

## 실측 참고 (기준 아티팩트, artifact_id `9e1a4d71800f`)

- `expected_saving` 총합 ≈ **1,454,088** (정답). 위치 결합이었다면 1,994,741(+37.2%) — CLIENTNUM 라벨 조인이 유일한 방어(함정4).
- 분면 분포: `low_cost_keep` 4,624 · `accept_churn` 2,971 · `watch` 2,089 · `save_first` 443.
- 실현 컷: risk ≈ 0.1328(0.75분위) · value = 3,899(중위).
- 결측 0건 — 세 소스가 동일 10,127 CLIENTNUM을 완전 커버.
