# Spike 3-V · 판정 — 부외(off-BS) 개별 검증

- **일자**: 2026-07-29
- **판정**: 🔴 **V1 미달 (d = 0/12) → 스파이크3 비율 결론을 철회한다.**
- **사전등록**: `spike-3v-preregistration.md` (커밋 `9d24e38`, 측정 전)
- **복명복창**: 표준 XBRL 금액이 안 잡히는 회사를 ①진짜 누락 ②다른 곳 기재 ③애초에 0으로 구분하고,
  **정상화하면 기업가치·재무비율·투자자 판단이 달라지는가**에 답한다.

---

## 0. 사전등록 대비 정정 1건 (측정 전 기록 아님 — 사실 정정)

사전등록이 모집단을 **52곳**이라 적었으나 실제 리스비용 잔차는 **71곳**이다. 52는 자본 데이터가
있어 비율 계산이 가능했던 부분집합이었다. **공시 여부를 묻는 이 검증에는 71이 옳다** —
자본 태그 유무는 리스가 부외인지와 무관하다. 표본은 71 기준으로, 사전등록한 시드로 추출했다.

---

## 1. 1단계 기계 사전선별 — 아무것도 못 갈랐다

| 신호 | 결과 |
|---|---|
| 가중평균 잔여기간·할인율 존재 → **b 확정** | **0곳 (0%)** |
| `ShortTermLeaseCost` 단독 → a 신호 | **0곳 (0%)** |
| 애매 | **71곳 (100%)** |

**예측 Q1("b가 절반 이상")이 완전히 빗나갔다.** 잔차 정의상 리스부채 태그가 없는 회사들이라
잔여기간·할인율 태그도 함께 없는 것이 자연스러웠다 — 선별 규칙이 **잔차 정의와 중복**돼 있었다.
설계 결함이며, 그래서 71곳 전부가 열람 대상이 됐다.

---

## 2. 2단계 무작위 열람 (n=12, 시드 20260729)

| 회사 | SIC | 되살림 | 판정 | 근거 (10-K 원문) |
|---|---|---|---|---|
| **WARRIOR MET COAL** | 1220 | **$131.9M** | **a** | *"leases with an initial term of **12 months or less are not recorded on its balance sheet**"* / *"primarily enters into rental agreements for certain mining equipment that are for periods of 12 months or less"* |
| SANDRIDGE ENERGY | 1311 | $0.63M | **b** | *"recognizes right-of-use assets and current and non-current lease liabilities on the balance sheet for all leases with lease terms of **greater than one year**"* |
| CERVOMED | 2834 | $0.13M | **a** | *"**short-term lease exemption** for all leases with an original term of less than 12 months"* |
| REVIVA PHARMACEUTICALS | 2834 | $0.19M | **b** | *"lease liabilities are included in lease liability, current and lease liability, **on the Company's balance sheets**"* |
| IQSTEL | 4813 | $0.11M | **a** | *"The office lease **meets the definition of a short-term lease**… does not recognize the right-of-use asset and the lease liability"* |
| INNOVATIVE PAYMENT SOLUTIONS | 5961 | $0.15M | **a** | *"practical expedient whereby operating leases with a duration of **twelve months or less are expensed as incurred**"* |
| LAREDO OIL | 1311 | $0.09M | **c** | 리스 관련 진술 전무. 본문은 *"mineral property acreage"* — **광권**이지 ASC 842 리스가 아님 |
| RIDGEWOOD ENERGY Q FUND | 1382 | $0.88M | **c** | "right-of-use"가 **BOEM/BSEE 규제 용어**(*"right-of-use and easement grant holders"*)로만 등장 |
| RIDGEWOOD ENERGY S FUND | 1382 | $0.70M | **c** | 동일 |
| RIDGEWOOD ENERGY U FUND | 1382 | $1.55M | **c** | 동일 |
| NEW CONCEPT ENERGY | 1311 | $0.05M | **c** | *"sold its oil and gas wells and **mineral leases**"* — 광권 |
| HEARTBEAM | 3841 | $0.08M | **판정보류** | 리스 관련 진술 미발견 (d로 볼 근거도 없음) |

### 집계

| 분류 | 곳 | 비중 |
|---|---|---|
| **a** 단기리스 면제 | **4** | 33% |
| **b** 태그만 누락(부채는 BS에 존재) | **2** | 17% |
| **c** ASC 842 리스가 아님(광권·규제용어) | **5** | 42% |
| **d 진짜 부외** | **0** | **0%** |
| 판정보류 | 1 | 8% |

---

## 3. 🔴 kill criteria 판정

| # | 기준 | 결과 |
|---|---|---|
| **V1** | 무작위 표본에서 **d ≥ 1곳** | 🔴 **미달 — 0곳** |
| V2 | 기계 선별 b가 100%가 아닐 것 | ✅ 통과(0%) — 그러나 §1대로 선별 자체가 무효 |

> **판정: 스파이크3의 비율 결론을 철회한다.** 사전등록 §4가 정한 그대로다. 결과를 보고 기준을
> 무르지 않는다.

**철회 범위**: "부외 리스 정상화 시 부채비율 중앙 +12.8%, 51.7%가 10% 이상 악화" 및 두 축 대조표의
부채 축 수치 전부. **52/71곳이 부외라는 전제가 표본에서 지지되지 않았다.**

**철회되지 않는 것**: §4의 구조적 발견(부외 vs 태그누락 구분 필요, 금액 축은 하나가 아님)은
**논리적 명제**이지 이 표본에 의존하지 않는다. 다만 **적용할 모집단이 사라졌다.**

---

## 4. 가장 아픈 사례 — Warrior Met Coal

표본 최대건이자 스파이크1 K3의 표적 후보였던 회사다.

- 시총 축 4.60% · 부채 축 13.7% — **두 축 모두에서 "표적"으로 잡혔다**
- 10-K 원문: *"**primarily** enters into rental agreements for certain mining equipment that are
  for periods of **12 months or less**"*
- **광산장비 단기 렌탈이다.** 자본화 의무가 없고, 되살릴 부채가 존재하지 않는다.

**우리가 리스비용×3.782로 $131.9M을 만들어냈지만, 그 부채는 실재하지 않는다.**
기계 판정만으로 배제리스트에 올렸다면 **실명이 잘못 실렸을 것이다.**

---

## 5. 새로 드러난 함정 — 업종별 용어 충돌 (c 분류 42%)

**표본의 42%가 "리스라고 부르지만 ASC 842 리스가 아닌" 경우였고, 전부 SIC 13xx(석유·가스) 계열이다.**

| 충돌 유형 | 사례 |
|---|---|
| **광권 리스**(mineral/oil & gas lease) | Laredo Oil, New Concept Energy — 자원 채굴권이지 자산 사용권이 아님 |
| **규제 용어로서의 right-of-use** | Ridgewood 3개 펀드 — BOEM/BSEE의 *"right-of-use and easement grant"*. 해저 시설 통행권 |

> **"부재 ≠ 누락"의 여섯 번째 형태 = 동음이의어.** 앞선 다섯(데이터셋 절단·파생 소계·상위 태그·
> 해당 없음·정당한 0)과 또 다르다 — **같은 단어가 업종에서 다른 것을 가리킨다.**
> **신규 계약: 개념 정의에 업종 배제 목록을 붙인다.** 리스 개념은 SIC 13xx(추출산업)에서
> 용어 충돌이 확인됐으므로 별도 처리하거나 제외한다.

---

## 6. 지금 스크리너에 남은 것

**리스·무형자산 두 개념 모두, 개별 검증을 통과한 실명 후보가 아직 0곳이다.**

| 개념 | 잔차(기계) | 개별 검증 결과 |
|---|---|---|
| 운용리스 부채 | 78 → 132(4분기) | **d = 0/12** (이 문서) |
| 무형자산 순액 | 467 → 94 → **16** | **미검증** |
| 주식보상 | 349 | **d = 0/11** (스파이크2, 개념 제외) |

**세 개념 중 둘은 개별 검증에서 생존자 0이고, 하나는 미검증이다.**

파티 결정 ①의 전방 기준(*"개별 검증 통과 실명 ≥ 1곳, 미달 시 개념 제외"*)을 리스에 적용하면
**리스도 제외 후보**다. 다만 표본이 12곳이고 그중 5곳이 c(용어 충돌)라, **c를 걷어낸 모집단에서
다시 뽑으면 결과가 달라질 수 있다** — 이건 사전등록 §6의 "표본 확대"에 해당하며 별도 표본으로
기록해야 한다.

---

## 7. daria 판정 필요

| # | 사안 |
|---|---|
| 1 | **리스 개념 처분** — 전방 기준대로 즉시 제외할 것인가, 아니면 c(SIC 13xx)를 배제한 모집단에서 **2차 표본**을 뽑아 한 번 더 볼 것인가 |
| 2 | **무형자산 16곳 개별 검증** — 유일하게 미검증으로 남은 개념. 여기서도 d=0이면 세 개념 전멸 |
| 3 | 전멸 시 **프로젝트 방향** — 개념을 더 찾을 것인가, 아니면 "이 방법으로는 진짜 누락이 거의 없다"를 **결론으로 출판**할 것인가 |

> **3번은 실패가 아니다.** 정본 문제정의는 ①②③ 구분을 산출물로 삼는다. *"XBRL 표준 금액 부재의
> 대부분은 누락이 아니라 대체 기재·정당한 0·용어 충돌이며, 진짜 누락은 극히 드물다"*는 **검증된
> 발견**이고, 그 자체로 방법론 산출물이다.
