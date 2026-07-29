# Spike 1 · T5-사전 — 가격 데이터 소스 확정과 표본 실태

- **일자**: 2026-07-29
- **판정**: FMP 현재 키 **폐기**. 설계는 `SEC 공시시점 티커 → Twelve Data → Stooq 보완`을 채택하되,
  **표본의 29.4%가 OTC**라는 실측 때문에 Stooq는 "보완용"이 아니라 **OTC 구간의 주 소스**다.
- **성격**: T5(공시 안 한 항목을 채우면 회사 값어치가 달라지나 = K3) 착수 전 데이터 확보 단계.

## 1. FMP 현재 키 — 부적합 판정

| 표본 | 결과 |
|---|---|
| 초대형주 AAPL·MSFT·JPM·COST | 200 OK |
| 대형주 DECK(약 $20B)·CROX·FIVE | **402** |
| 중소형 SFIX·GPRO·WKHS·RILY·BKKT·SNAX·GNSS | **402** |
| S&P500 구성종목 목록 | **402** |
| `from`/`to` 날짜 파라미터 | **402** (무파라미터는 최근 63일만) |

402 본문: *"This value set for 'symbol' is not available under your current subscription"* — 종목 자체가
플랜에 막혀 있다. **시가총액 크기 문턱이 아니라 소수 데모 종목만 허용하는 등급.**

> **표현 정정(지적 수용)**: "DECK도 막혔으니 전부 막혔다"는 논리적으로 증명되지 않았다. 보고 문구는
> **"초대형 4·대형 3·중소형 7 표본에서 402가 반복되어, 이 키가 K3 표본을 안정적으로 커버하지
> 못한다고 판단"**으로 쓴다. 결론(부적합)에는 지장 없으나 근거의 크기를 과장하지 않는다.

## 2. 표본 실태 — 이게 소스 선택을 결정한다

잔차 표본(리스 78 + 무형 94, 중복 제거) = **170 filing / 167 CIK**.
공시 시점 티커(`dei:TradingSymbol`, 주석 데이터셋 `txt.tsv`) 확보 현황:

| 상태 | 건 | 비중 |
|---|---|---|
| 공시에 티커 있음 | 120 | **70.6%** |
| 공시에 티커 없음 | 50 | **29.4%** |

**전체 모집단의 티커 보유율은 88.3%인데 잔차 표본은 70.6%다** — 잔차가 소형·장외로 쏠려 있다는
T3 관찰이 여기서도 재확인된다.

### 티커 없는 50건의 정체 = OTC (데이터 공백이 아니다)

- 50건 **전원이 `4-NON`**(비가속신고자), 48건은 `SecurityExchangeName`도 없음.
- 이유: 표지의 `TradingSymbol`·`Security12bTitle`은 **거래소 상장(Securities Exchange Act §12(b))**
  증권에만 붙는다. 장외 등록사(§12(g))는 이 태그가 없다.
- SEC `submissions` API 교차 확인(6건 샘플): **5건이 실제로 OTC 티커 보유**.

| CIK | 회사 | submissions 티커 | 거래소 |
|---|---|---|---|
| 1448705 | BASANITE | `BASA` | OTC |
| 20639 | AmBase | `ABCP` | OTC |
| 1784440 | BioScience Health Innovations | `BHIC` | OTC |
| 83350 | Reserve Petroleum | `RSRV` | OTC |
| 1339688 | Lion Copper & Gold | `LCGMF` | OTC |
| 1785592 | Leafly Holdings | (없음) | (없음) |

> **설계 수정 지점**: Twelve Data는 **OTC를 기본 제공하지 않는다**(제안서에서 이미 명시된 한계).
> 그런데 우리 표본의 29.4%가 정확히 그 OTC다. 따라서 Stooq는 "Twelve Data 결측 보완"이 아니라
> **OTC 구간을 담당하는 사실상의 주 소스**가 된다. 순서는 유지하되 **기대 분담률을 뒤집어 잡는다.**

## 3. 복수 티커 함정 — 실물 확인

잔차 표본 중 **20건이 복수 티커**를 보유. `dimh`(차원 해시)로 `TradingSymbol`↔`Security12bTitle`
짝짓기가 **정확히 동작**함을 확인했다:

```
0001628280-25-009464   (Ready Capital)
   RC       <- Common Stock, $0.0001 par value per share      <- 이것만 정답
   RCB      <- 6.20% Senior Notes due 2026                    <- 채권
   RCC      <- 5.75% Senior Notes due 2026                    <- 채권
   RCD      <- 9.00% Senior Notes due 2029                    <- 채권
   RC PRC   <- Preferred Stock, 6.25% Series C ...            <- 우선주
   RC PRE   <- Preferred Stock, 6.50% Series E ...            <- 우선주
```

**제목을 안 보고 첫 티커를 잡으면 회사채 가격을 주식가치로 쓴다.** 6개 중 4개가 채권인 사례가
실제 표본 안에 있다. → 보통주 선별은 `Security12bTitle`에 대한 규칙(Common Stock / Class A Common
Stock 등) 필수, 그리고 **선별 실패 건은 버리지 말고 `multiple_security_classes`로 남긴다.**

## 4. `pubfloatusd`를 주 지표로 쓰면 안 되는 추가 실증

지적된 이유(비계열 주주 한정·2분기말 기준·시점 불일치)에 더해, **값 자체의 품질 문제**를 발견:

- **Lion Copper & Gold**: `pubfloatusd` = **$23,151.3M**(약 23조 원). OTC 마이크로캡에 불가능한 값 —
  단위·스케일 오류로 보인다.
- 티커 없는 50건 중 **49건이 0 아닌 pubfloat 보유** → "pubfloat 있음"은 상장 여부의 근거가 안 된다.

→ **주 분석 배제, 민감도 분석 전용** 확정. 결측이 규모·신고자 유형과 얽혀 있다는 지적도 데이터와 정합
(티커 없는 50건 전원 4-NON).

## 5. 확정 파이프라인

```
① 표본 정리      CIK + adsh + concept + period_end, CIK 기준 중복 제거
② 시점 티커      dei:TradingSymbol (notes txt.tsv, dimh로 Security12bTitle 짝짓기)
                 └ 보통주만 선별, 실패 시 multiple_security_classes로 격리
                 └ 여기서 트랙이 갈린다 ─┬─ 티커 있음(120) → 주분석 트랙
                                        └─ 티커 없음(50)  → OTC 트랙
③ OTC 티커 보강  SEC submissions API (실측 5/6 회수)          [OTC 트랙]
④ 가격 1차       Twelve Data /time_series                     [주분석 트랙]
⑤ 가격 2차       Stooq 벌크 (OTC 트랙 주력 + ④ 결측 보완)
⑥ 결측 명시      price_source_missing (억지 대체 금지)
⑦ 산출 분리      주분석 표 / OTC 표 별도. 합산·평균 금지(daria 결정 ③)
```

**가격 시점 고정(택1, 혼용 금지)**: `DocumentPeriodEndDate` **직전 거래일 raw close × 당시 주식수**.
소급 조정된 adjusted close가 아니라 당시 실거래가를 쓰는 이유는 당시 주식수와 시점을 맞추기 위함.

**K3 결과에 반드시 병기할 계정**:
```
전체 대상 N / 시점 티커 확보 N / Twelve Data 매칭 N / Stooq 추가 매칭 N
최종 가격 가용 N / 가격 결측 N
```
이 분리가 없으면 K3가 아니라 "무료 API 복불복 테스트"가 된다.

## 6. 착수 전 남은 결정 (daria)

1. **Twelve Data 무료 키 발급** — 필요. 없으면 ④가 통째로 빈다.
2. ~~**OTC 처리 방침**~~ → **✅ 종결(daria 결정 2026-07-29): ③ 물리 분리 채택.**
   **주분석 = 거래소 상장분(120건)** · **OTC(50건)는 별도 표로 분리 산출**. 두 결과를 한 축에
   섞지 않는다. 근거: crm 3-4 D2 `risk_quantile annex` 선례 — 민감도를 official 등고선과 물리
   분리하고 official 오염 0을 테스트로 단언했던 방식 그대로. 이렇게 해야 K3 실패 시
   *"밸류에이션과 무관해서"*인지 *"OTC가 빠져 표본이 왜곡돼서"*인지 **갈라 말할 수 있다.**
   - **계약**: OTC 표는 주분석 수치에 산입 0. 별도 산출물이며, 합산·평균 금지.
   - Stooq 회수는 OTC 표 안에서 수행하고, 회수 실패분은 `price_source_missing`으로 명시.
3. **표본 크기 우려** — 상장분만 보면 120건, OTC 회수 실패 시 더 줄어든다. 단일 분기(2025Q1) 기준이라
   **분기를 늘려 표본을 키우는 선택**이 필요할 수 있다(캐시된 4개 분기 활용 가능).

## 부록 — 이번 단계에서 새로 밟은 함정

- **두 데이터셋의 `sub` 컬럼 수가 다르다**: 재무제표 벌크 36열 / 주석 40열. `pubfloatusd`·`detail`
  등은 **주석 쪽에만** 있다. 벌크만 읽고 "없는 필드"라 결론내면 오진.
- **`txt.tsv`는 기본 csv 필드 한도(131,072)를 초과**한다 — `csv.field_size_limit` 상향 필수.
  안 하면 파싱이 예외로 죽는다(조용한 결측이 아니라 크래시라 다행).
- FMP 키는 세션 스크래치패드에만 두고 저장소에 커밋하지 않았다. 스모크테스트 후 삭제.
