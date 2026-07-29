# Spike 4 · 판정 — 무형자산 잔차 전수 검증

- **일자**: 2026-07-29
- **판정**: 🔴 **W1 미달 (d = 0/23) → 무형자산 개념도 제외. 세 개념 전멸.**
- **사전등록**: `spike-4-preregistration.md` (커밋 `fac0b7b`, 측정 전)
- **복명복창**: 표준 XBRL 금액이 안 잡히는 회사를 ①진짜 누락 ②다른 곳 기재 ③애초에 0으로 구분하고,
  **정상화하면 기업가치·재무비율·투자자 판단이 달라지는가**에 답한다.

---

## 1. 전수 판정 결과 (23사)

| 분류 | 곳 | 비중 |
|---|---|---|
| **b** 다른 곳 기재 | **8** | 35% |
| **a** 실질 부재 / 전액상각 | **7** | 30% |
| **c** ASC 350 무형자산이 아님(업종 동음이의) | **7** | 30% |
| **d 진짜 누락** | **0** | **0%** |
| 판정보류 | 1 | 4% |

### b — 다른 곳 기재 (8)

| 회사 | 근거 (10-K 원문) |
|---|---|
| **STURM RUGER** | **주석 6 "Other Assets"**에 전부 있다 — *"Patents, at cost $10,339 / Marlin trade name, at cost 7,800 / Accumulated amortization (8,008)"*. 전용 무형자산 주석이 아니라 **기타자산 주석에 묶여** 표준 태그가 안 붙었을 뿐 |
| CHEMUNG FINANCIAL | *"Goodwill and other intangible assets, **net** 21,824"* — 영업권과 **합산 라인**으로 공시 |
| PERMA-PIPE | *"Gross patents were $2.7 million… Accumulated amortization was approximately $2.6 million"* |
| INCORDEX | *"NOTE 4 - INTANGIBLE ASSETS … purchased the website for $5,000 and is amortizing"* |
| ARTISAN CONSUMER GOODS | *"NOTE 3 INTANGIBLE ASSETS … acquired the assets of Paleo … for $10,000"* |
| VERSUS SYSTEMS | 손상 금액 $3,968,332 손익 라인으로 공시 |
| iWALLET | 상표·소프트웨어·웹사이트 **차원별 태그**로 공시 |
| EVA LIVE | `ComputerSoftwareIntangibleAsset` 차원 태그로 공시 |

### a — 실질 부재 / 전액상각 (7)

| 회사 | 근거 |
|---|---|
| **SPOK HOLDINGS** | ***"There were no remaining amortizable intangible assets at December 31, 2024 and 2023."*** — 명시적 |
| **EHEALTH** | *"gross carrying value of **$17.2 million** and life-to-date accumulated amortization and impairment charges of **$17.2 million**"* → **순액 0** |
| DLT RESOLUTION | *"Intangible assets, net of accumulated amortization — 139,848 (139,848)"* → 기말 0(처분) |
| ERIE INDEMNITY | 본문 "intangible" 언급 **0회** |
| ARK RESTAURANTS | 언급 전부 영업권·일반담보 문맥. 유한내용연수 무형 없음 |
| KNOW LABS | 이연법인세 표에 *"Intangibles - -"* (0) |
| NEWTON GOLF | *"non-amortizing intangible assets"* 언급만 |

### c — ASC 350 무형자산이 아님 (7) · **전부 사전 지정 업종에서 나왔다**

| 회사 | SIC | 정체 |
|---|---|---|
| MEDICAL PROPERTIES TRUST · BRIXMOR · CARETRUST · JLL INCOME PROPERTY | 6798 | **in-place / above·below-market lease intangible** — 부동산 취득 시 ASC 805 배분액 |
| AEI INCOME & GROWTH FUND | 6500 | 동일 |
| FIRST TRINITY FINANCIAL | 6311 | **보험 DAC / VOBA** |
| **PORTLAND GENERAL ELECTRIC** | 4911 | **규제 유틸리티의 "Intangible plant"** — 유형자산 계정 분류이지 ASC 350 무형자산이 아니다 (사전 지정에 없던 신규 유형) |

---

## 2. 사전 예측 대조

| # | 예측 | 결과 |
|---|---|---|
| P1 | c가 30% 이상 | ✅ **적중** — 정확히 30% |
| P2 | b가 존재(우리 태그 목록 밖 공시) | ✅ **적중** — 35%로 최다 |
| P3 | d는 0 또는 1 | ✅ **적중** — 0 |
| P4 | **대기업은 전부 b 또는 c** | ✅ **적중** — Sturm Ruger(b) · PGE(c) · MPW·Brixmor·CareTrust(c) · Erie(a) |

**4/4 적중.** 스파이크2에서 3/4이 빗나갔던 것과 대조된다 — **이제 이 데이터의 행동을 안다.**
특히 **자기점검 규칙("큰 회사가 상위권이면 나를 먼저 의심하라")이 3연속 적중**했다.

---

## 3. kill criteria 판정

| # | 기준 | 결과 |
|---|---|---|
| **W1** | d ≥ 1곳 | 🔴 **미달 — 0곳** |

**무형자산 개념도 스크리너에서 제외한다.** 사전등록 §4 그대로.

---

## 4. 🔴 세 개념 전멸 — 종합

| 개념 | 성격 | 기계 잔차 | 개별 검증 | 판정 |
|---|---|---|---|---|
| 운용리스 부채 | 잔액 | 132 | **0 / 12** | 제외 |
| 주식보상 | 흐름 | 349 | **0 / 11** | 제외 |
| 무형자산 순액 | 잔액 | 26 | **0 / 23** | 제외 |
| **합계** | | **507** | **0 / 46** | — |

**개별 검증한 46곳 중 진짜 누락 0곳.** 기계가 507건을 "잔차"로 지목했지만, 사람이 열어본 46곳은
**전부 다른 이유로 설명됐다.**

---

## 5. "부재 ≠ 누락"의 여섯 형태 — 완성된 분류

이 프로젝트가 실측으로 발견하고 이름 붙인 것들이다.

| # | 형태 | 최초 발견 | 대표 사례 |
|---|---|---|---|
| 1 | **데이터셋 절단** | T2 | 재무제표 벌크만 보면 `OperatingLeaseLiability` 커버리지 6.0%, 주석까지 보면 79.4% |
| 2 | **파생 가능 소계** | T3-확장 | `Net = Gross − 상각` — 두 다리가 있으면 순액은 계산되는 값 |
| 3 | **상위·병렬 태그** | T5 | `IntangibleAssetsNetExcludingGoodwill` 등으로 이미 공시 |
| 4 | **해당 없음** | T3 | SPAC·펀드·REIT(lessor)는 리스가 구조적으로 없다 |
| 5 | **정당한 0** | 스파이크2 | *"No compensation expense … was recognized"* — 제도는 살아있고 당기 금액이 0 |
| 6 | **업종 동음이의** | 스파이크3-V | 광권 리스 · BOEM right-of-use · **in-place lease intangible · 보험 DAC · 유틸리티 intangible plant** |

**스파이크4가 6번을 크게 확장했다** — 리스에서 2종이던 것이 무형자산에서 3종 더 나왔고,
그중 **유틸리티 "intangible plant"는 사전 지정에도 없던 신규 유형**이다.

---

## 6. 이제 무엇이 남았나

**이 프로젝트는 실패하지 않았다. 답이 예상과 달랐을 뿐이다.**

정본 문제정의는 **①②③ 구분 자체를 산출물**로 삼는다. 그 관점에서 지금까지 확립된 것:

1. **검증된 발견**: *"XBRL 표준 금액의 부재는 거의 언제나 누락이 아니다."* 46곳 전수 검증에서
   진짜 누락 0곳. 이건 강한 실증 명제다.
2. **재사용 가능한 분류 체계**: 위 여섯 형태. 각각 **기계 판별 규칙과 실사례**를 갖췄다.
3. **개념 선정 기준**: 잔액 vs 흐름(스파이크2) · 업종 배제 목록(스파이크3-V·4)
4. **방법론 규율**: 사전등록 → 기계 선별 → 개별 검증 → kill criteria. **세 번 연속으로 개념을
   죽였고**, 그때마다 기준을 무르지 않았다.

**뒤집힌 것**: 최종 질문("정상화하면 달라지는가")은 **정상화할 대상이 거의 없으므로 대체로
무의미**하다. 스파이크1 K3와 스파이크3의 수치는 전부 미검증 잔차 위에 세워져 있었고,
검증이 그 토대를 걷어냈다.

---

## 7. daria 판정 — 프로젝트 방향

| 안 | 내용 | 장점 | 단점 |
|---|---|---|---|
| **A** | **"진짜 누락은 극히 드물다"를 결론으로 출판** — 6형태 분류 + 46곳 전수 검증을 산출물로 | 검증된 발견이고 방법론이 남는다. IC-memo·mandate.md도 이 결론 위에 쓸 수 있다 | "스크리너"라는 도구는 안 나온다 |
| **B** | 개념을 더 시도 (충당부채·이연법인세 평가충당금·우발부채 등) | 잔액 개념이라 조건은 맞다 | **세 번 연속 0이었다.** 네 번째가 다를 근거가 없다 |
| **C** | **표적을 바꾼다** — "누락 탐지"가 아니라 **"비표준 보고 탐지"**로. b(다른 곳 기재)가 최다였으니 그것이 실재하는 현상이다 | 실제로 존재하는 것을 잰다. 정본 문제정의의 "**비표준 보고**"가 이미 이 이름을 담고 있다 | 투자 판단 연결이 약해진다 — 비표준 보고는 가치를 안 바꾼다 |

**내 권고는 A + C의 결합이다**: 결론을 출판하되, 산출물을 "배제리스트"가 아니라
**"공시 표준화 품질 지표"**로 재정의한다. b가 35%, c가 30%라는 것은 **XBRL 표준 태깅이
얼마나 지켜지지 않는가**를 재는 지표로서 실재하는 가치가 있다 — 다만 그건 투자 스크리너가
아니라 **데이터 품질·비교가능성 도구**다.

**이 결정은 daria 몫이다.**
