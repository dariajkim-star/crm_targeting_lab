---
baseline_commit: 223bce7
project: 워싱 스크리너 (본공연)
kind: spike
---

# Spike 1: SEC peer 공시 격차 실측 — 가설이 성립하는가

Status: ready-for-dev

> **거처 안내**: 스크리너는 아직 스캐폴딩 전이다. 이 문서는 `crm-targeting-lab/docs/screener/`에
> 임시 거주하며, 스크리너 리포지터리 생성 시 `THESIS.md`와 함께 이동한다(회고 A5와 한 묶음).

## 이것은 스토리가 아니라 스파이크다

**산출물은 코드가 아니라 판정이다.** 그럼발 경고("이 데이터로 이게 되긴 하냐")에 답하는 것이
목적이고, **kill criteria를 먼저 적고 시작한다** — 죽을 수 없는 스파이크는 스파이크가 아니라
자기충족 예언이다. 여기서 나온 코드는 전부 버릴 수 있다고 전제한다(스캐폴딩 전이므로 실제로 버린다).

crm 등가물: 1-2/1-3(가치 축·프록시를 데이터가 명명하게 한 스토리). 그때의 교훈 — **문서가 실측을
앞서지 않는다** — 이 스파이크의 지배 규율이다.

## Spike

As 워싱 스크리너의 방법론 검증자,
I want SEC 공시 데이터에서 **peer 공시 격차가 실제로 벌어지는지**와 그 격차가 **밸류에이션과
연결되는지**를 실측하기를,
so that "누락 지표 → 배제" 가설이 성립하는지를 **데이터 탓 없이** 판정하고, 성립하지 않으면
스크리너를 설계하기 전에 죽인다.

## 선행 확정 사항 (THESIS §7, 재론 금지)

- **원료 = SEC EDGAR.** DART·병행 기각(레짐 교란 / 조인 폭발). daria 결정 2026-07-28.
- **peer = 업종 × 레짐 코호트.** 레짐 축은 filer status(SRC scaled disclosure), 자산밴드 아님.
- **`opacity_rank`는 레짐 통제 후 잔차만 잰다.** 통제 전 원지표는 official 산출물 비탑재.
- **출력 설계**: `opacity_rank`(순위 전용) + 배제리스트(행마다 이유 한 줄, 머리말 "미배제 ≠ 클린
  인증") + 되살린 밸류 델타(금액 축 동행).

## 착수 전 이미 확인된 사실 (2026-07-28, 실측)

다시 조사하지 말 것. 아래는 실제 호출 결과다.

| 항목 | 확인 내용 |
|---|---|
| `xbrl/frames` API | 동작. `https://data.sec.gov/api/xbrl/frames/us-gaap/{tag}/USD/{period}.json` |
| 호출 조건 | **User-Agent 헤더 필수** — 없으면 403. 일반 fetch 도구는 차단된다 |
| 벌크 | `https://www.sec.gov/files/dera/data/financial-statement-data-sets/2024q4.zip` → 200 |
| 주석(notes) 벌크 | Financial Statement **and Notes** Data Sets는 존재하나 **URL 패턴 미확인**(추정 2건 404) — T1 과제 |

**커버리지 격차가 실재한다는 1차 증거** (CY2024 기준, frames 응답의 distinct CIK):

| 개념 | filer 수 | 비고 |
|---|---|---|
| `Assets` (CY2024Q4I) | **6,249** | 분모 후보 — 사실상 전수 |
| `ShareBasedCompensation` (CY2024) | **4,557** | 분모 대비 −27% |
| `OperatingLeaseLiability` (CY2024Q4I) | **4,064** | 분모 대비 **−35%** |

**이 표는 가설을 증명하지 않는다.** 격차가 존재한다는 것만 보여주며, 그 격차가 *누락*인지는
AC3이 판정한다. 이 구분이 이 스파이크 전체의 심장이다.

## Acceptance Criteria

**AC1 — 원료 접근 경로 확정 (T1)**
Given SEC 데이터를 반복 취득해야 할 때
When 취득 경로를 확정하면
Then ①frames API ②Financial Statement Data Sets 벌크 ③**Financial Statement and Notes Data Sets**
(주석 레벨) 각각의 URL 패턴·갱신 주기·파일 구성이 문서화되고, **주석 레벨 데이터에 실제로 도달
가능한지**가 예/아니오로 판정된다.
And 접근 규약을 기록한다: User-Agent 필수, SEC 권고 요청률 준수, 원본 응답은 캐시하여 재호출 없이
재현 가능(crm AD-13 신선도 meta 계승 — 취득 시각·SHA-256 동반).
> **아니오인 경우도 유효한 결과다.** 주석 레벨이 안 되면 격차는 재무제표 본문 태그로만 재게 되고,
> 그때 스크리너가 볼 수 있는 "누락"의 범위가 좁아진다 — 그 축소를 **문서에 적고** 진행할지 여부를
> daria가 판정한다.

**AC2 — peer 셀 크기 분포 실측 (T2)**
Given peer = 업종 × 레짐 코호트일 때
When SIC 코드(EDGAR `submissions` 메타데이터, 무료)와 filer status로 전 filer를 분할하면
Then **셀 크기 분포**(중앙값·1분위·n<10 셀의 비중)가 산출되고, `opacity_rank`가 통계적으로 말이
되는 최소 셀 크기를 만족하는 filer 비율이 보고된다.
And GICS를 쓰지 않는 근거(라이선스)와 SIC의 알려진 한계(자기신고·갱신 지연·복합기업 오분류)를
함께 기록한다.
> **레아 조건**: *"n=4에서 '얘만 누락'이라고 말하는 건 통계가 아니라 인상이다."* 최소 셀 크기
> 미달 filer를 어떻게 처리할지(제외 / 상위 SIC로 롤업 / 랭크 미부여)는 **실측 분포를 보고** 정한다 —
> 지금 정하지 않는다.

**AC3 — 부재 ≠ 누락: 대체 설명 반증 (T3) — 이 스파이크의 최대 난관**
Given 어떤 filer가 어떤 개념을 보고하지 않았을 때
When 그 부재를 "누락"으로 부르기 전에
Then 최소 세 가지 대체 설명이 각각 **얼마나 설명하는지 정량화**된다:
1. **해당 없음** — 운용리스가 실제로 없는 기업(부재가 정직한 사실)
2. **다른 태그** — 동일 실질을 다른 us-gaap 개념/확장 태그로 보고
3. **기간 정렬** — 비12월 결산 등으로 해당 프레임에 안 잡힘
And 세 설명을 통제한 뒤 **남는 잔차**가 전체 부재의 몇 %인지 보고한다.
> **이것이 crm 1-7의 등가물이다.** `Months_Inactive_12_mon`의 평균 |SHAP| 0.0000을 그대로 실었으면
> *"비활성 개월은 이탈과 무관"*이라는 정반대 결론이 나갈 뻔했다. 여기서 대체 설명을 통제하지 않으면
> **"리스가 없는 회사"가 워싱 기업으로 배제리스트에 오른다** — 실명이 실린 채로.

**AC4 — 레짐 통제의 실효 확인 (T4)**
Given SRC의 scaled disclosure가 존재할 때
When 코호트 통제 전후의 격차를 비교하면
Then **통제가 격차를 실제로 얼마나 깎는지**가 수치로 보고된다.
And 통제 후에도 남는 격차가 무의미한 수준이면, 그 사실이 kill criteria로 직행한다.
> 통제가 격차를 거의 다 먹어치우면 — 우리가 재던 게 워싱이 아니라 기업 규모였다는 뜻이다.

**AC5 — 밸류에이션 연결 (T5)**
Given 격차가 통제 후에도 남을 때
When 그 격차와 밸류에이션 지표의 관계를 보면
Then **"되살린 델타"가 성립하는지** — 누락된 항목을 peer 중앙값 등으로 채워 넣었을 때 밸류에이션이
유의미하게 움직이는지 — 가 실측된다.
> 여기가 진짜 승부처다. 격차가 있어도 밸류에이션이 안 움직이면 **투자 의사결정과 무관한 지표**이고,
> 스크리너는 존재 이유가 없다. AC3보다 통과가 어려울 수 있다.

**AC6 — kill criteria와 판정 문서 (T6)**
Given 위 실측이 끝났을 때
When 판정을 내리면
Then `spike-1-verdict.md`가 작성되고, 아래 kill criteria에 대해 **각각 통과/미달을 명시**한다.
And 미달 항목이 있으면 **가설 수정 또는 중단 권고**를 적는다 — "그래도 해보자"는 금지(그럼발 조항).

### Kill criteria (착수 전 확정 — 사후 조정 금지)

| # | 기준 | 미달 시 |
|---|---|---|
| K1 | AC3 잔차가 전체 부재의 **의미 있는 비중**을 차지 | 부재가 전부 설명되면 → **가설 사망**. 우리가 재던 건 사업 실태였다 |
| K2 | AC4 레짐 통제 후에도 격차가 **남는다** | 통제가 다 먹으면 → 우리가 재던 건 기업 규모다 |
| K3 | AC5 밸류에이션이 **움직인다** | 안 움직이면 → 투자 무관 지표. 스크리너 존재 이유 소멸 |
| K4 | AC2 최소 셀 크기를 만족하는 filer가 **모집단의 유의미한 몫** | 대부분 미달이면 → 커버리지가 너무 좁아 스크리너로 못 씀 |

**"의미 있는 비중"의 구체 수치는 실측을 보고 daria가 정한다** — 지금 숫자를 박으면 그게 곧
결론을 미리 정하는 것이다. 다만 **판정 전에 정한다**(결과를 보고 기준을 고르면 세탁이다).

## Tasks / Subtasks

- [x] **T1 — 취득 경로 확정** (AC1): 3종 전부 도달 확인, **주석 레벨 = 예**(축소 불필요).
      판정: `spike-1-t1-acquisition.md`. 부수 수확 — `sub.tsv`가 `sic`·`afs`·`pubfloatusd`·`detail`을
      전부 들고 있어 peer/레짐 축에 외부 조인이 불필요(함정4 노출면 감소). 함정 3건 기록
      (주석 데이터셋 2025Q3 분기→월간 전환 · `.tsv` 확장자 · 단일 월 계절 편향).
- [ ] **T2 — peer 축 구축** (AC2): 셀 크기 분포는 **T1이 선산출**(4개 분기, filer 5,367). 남은 것 =
      **peer 정의 확정**(daria + 레아 판정: SIC2×filer-status / SIC3 타협 / 개념별 선택적 통제)
      + SIC 한계 기록.
- [ ] **T3 — 부재 분해** (AC3): 대체 설명 3종 각각의 설명량 정량화 → 잔차 산출. **가장 오래 걸린다.**
- [ ] **T4 — 레짐 통제 전후 비교** (AC4).
- [ ] **T5 — 밸류에이션 연결** (AC5): 되살린 델타 성립 여부.
- [ ] **T6 — 판정 문서** (AC6): `spike-1-verdict.md`, kill criteria 전건 판정.

## Dev Notes

### crm에서 가져오는 것 (회고 §6 이식 부품 중 이 스파이크에 해당하는 것)

- **문서가 실측을 앞서지 않기** — 이 스파이크의 지배 규율. 리포트에 쓰기 전에 그 성질을 KILL하는
  검증이 있어야 한다. crm에서 이 규율이 과잉주장 4건을 되돌렸다.
- **동어반복 회피** — 구현을 재계산해 비교하지 말고, 그럴듯한 오구현이 깨뜨릴 **성질**로 검증.
- **조인 계약(함정4)** — 스크리너는 공시·peer·가격을 조인하고 또 조인한다. CIK를 라벨 조인 키로
  고정하고, 위치 결합을 물리적으로 불가능하게. crm에서 행 오정렬이 총합을 **+37.2%** 부풀렸는데
  **예외가 하나도 안 났다**. 스파이크 단계에서도 이건 지킨다.
- **환경 의존은 수치에 병기** — 취득 시점·프레임·모집단을 모든 수치에 붙인다.

### 아직 하지 않는 것

- 스캐폴딩(레인 격리·config 단일 출처·구조 가드) — 판정이 나온 뒤 회고 A5와 함께.
- `opacity_rank` 구현 — 스파이크는 **성립 여부**만 본다. 순위 산출은 첫 정식 스토리.
- mandate.md / IC-memo — 배제 기준 확정 후.

### 참고

- [SEC EDGAR APIs](https://www.sec.gov/search-filings/edgar-application-programming-interfaces)
- [Financial Statement Data Sets](https://www.sec.gov/data-research/sec-markets-data/financial-statement-data-sets)
- [Financial Statement and Notes Data Sets](https://www.sec.gov/data-research/sec-markets-data/financial-statement-notes-data-sets)
- [SRC 정의 개정(scaled disclosure)](https://www.sec.gov/resources-small-businesses/small-business-compliance-guides/amendments-smaller-reporting-company-definition)
- 결정 근거: `docs/THESIS.md` §7

## Change Log

| 날짜 | 변경 |
|---|---|
| 2026-07-28 | 스파이크 최초 작성. daria의 SEC 결정(파티 A4) 직후. kill criteria 4건 착수 전 확정. 1차 증거(커버리지 격차 실재) 동봉. |
