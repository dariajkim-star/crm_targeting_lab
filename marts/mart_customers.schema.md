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

| name | dtype | 단위 | nullable | 산출 모듈 | 정의 (1줄) |
|---|---|---|---|---|---|
| `CLIENTNUM` | int64 | ID | no | 원본(BankChurners) | 고객 식별자. 세 소스의 **라벨 조인 키**이자 마트의 정체성. 유일. |
| `segment_id` | int64 | 범주(0–3) | no | `crm/segment/segments.py` | K-means 세그먼트 ID(1-4). features_customers에서 그대로 소비. |
| `customer_value` | float64 | 원척도(무통화, NFR3) | no | `crm/segment/value.py::customer_value` | 고객 가치 = `Total_Trans_Amt`(원척도). **가정**: 거래액이 가치의 1차 프록시(SPEC CAP-5). 정규화·로그 없음. AD-11 단일 정의. |
| `churn_score` | float32 | 확률스케일 순위신호 [0,1] | no | `crm/churn/model.py` (03) | **원(비보정) out-of-fold** 이탈 점수. **순위 전용**(2x2가 소비). 금액 곱셈 금지 — magnitude를 쓰면 총액 +19.0% 부풀림(3-2 실측). |
| `churn_prob_calibrated` | float64 | 확률 [0,1] | no | `crm/churn/calibrate.py` (3-0) | **Platt 보정** 이탈 확률. **금액 전용**(expected_saving가 소비). churn_score와 한 프레임에 공존 — 용도 혼동 주의. |
| `quadrant_official` | object (str) | 범주(ASCII enum) | no | `crm/campaign/matrix.py::assign_quadrant` | 공식 2x2 분면: `save_first`·`watch`·`low_cost_keep`·`accept_churn`. 경계 상단 `>=`(AD-12). 라벨·임계값 **단일 계산**. |
| `threshold_official_risk` | float64 | 확률스케일 [0,1] | no | `crm/campaign/matrix.py` | 이 모집단에서 실현된 위험 컷 = churn_score의 `risk_quantile=0.75` 분위. 전 행 동일(브로드캐스트). 시나리오 뷰의 기준선(AD-3). |
| `threshold_official_value` | float64 | 원척도 | no | `crm/campaign/matrix.py` | 실현된 가치 컷 = customer_value의 `value_quantile=0.50`(중위). 전 행 동일. |
| `expected_saving` | float64 | 원척도(무통화, NFR3) | no | `crm/campaign/simulate.py::expected_saving` | 1회 접촉 기대절감 = `churn_prob_calibrated · customer_value · retention_rate − cost`. **가정**: `retention_rate=0.30`·`cost_per_contact=5.0`(정책가정, NFR1). 음수 가능(=접촉 안 함). |
| `target_priority` | int64 | 순위(1..n) | no | `crm/campaign/priority.py::target_priority` | 접촉 우선순위. **정의 고정(AD-12)**: 아래 참조. |

## `target_priority` 정의 (AD-12 — 단일 소유, 여기 고정)

> **기대절감액(`expected_saving`) 내림차순 dense rank(1이 최우선). 동점 시 `customer_value` 내림차순, 그래도 동점이면 `CLIENTNUM` 오름차순 — 전순서(strict total order) 보장. 전원 10,127명에게 순위 부여(누락·동점 없음).**

- **전원 순위**: 음수 절감 고객도 순위에서 제외하지 않고 마지막에 배치한다 — 마트는 nullable 컬럼을 갖지 않으며, "순위≠추천"이다(예산·양수 컷으로 실제 **선택**하는 `campaign_selected`는 4-1b 범위).
- **dense는 여기서 무의미(inert)**: `CLIENTNUM`이 유일하므로 복합키에 중복이 없어 `dense`/`min`/`first`가 모두 `1..n`으로 동일하게 붕괴한다. 타이브레이크 체인이 실제로 발화하지 않지만(실측: 10,127개 절감액 전부 상이), 두 고객이 순위를 공유하면 Tableau 뷰가 새로고침 간 순서를 뒤바꿀 수 있으므로 전순서를 계약으로 못박는다.

## 감사 가능성 (마트=계약면)

이 마트만으로 화면의 분면·우선순위를 **검산**할 수 있어야 한다(3-0 코드리뷰 D3, 층 분리 원칙). 그래서 `expected_saving`을 **감사 컬럼으로 포함**한다 — `target_priority`가 이 축의 dense rank로 정의되므로, 이것이 없으면 마트만으로 순위를 재현할 수 없다.

## 실측 참고 (기준 아티팩트, artifact_id `9e1a4d71800f`)

- `expected_saving` 총합 ≈ **1,454,088** (정답). 위치 결합이었다면 1,994,741(+37.2%) — CLIENTNUM 라벨 조인이 유일한 방어(함정4).
- 분면 분포: `low_cost_keep` 4,624 · `accept_churn` 2,971 · `watch` 2,089 · `save_first` 443.
- 실현 컷: risk ≈ 0.1328(0.75분위) · value = 3,899(중위).
- 결측 0건 — 세 소스가 동일 10,127 CLIENTNUM을 완전 커버.
