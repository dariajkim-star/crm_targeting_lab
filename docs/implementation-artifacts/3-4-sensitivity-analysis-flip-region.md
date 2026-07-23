---
baseline_commit: 9ff1e43 (+ 3-3 최종 working tree, 443 passed / 미커밋)
baseline_passed: 443
artifact_id: 9e1a4d71800f
---

# Story 3.4: 민감도 분석과 결론 반전 구간

Status: review

## Story

As a 마케팅 의사결정자,
I want 가정이 틀렸을 때 결론이 언제 뒤집히는지를,
So that 실험 없이도 이 제안을 어디까지 신뢰할 수 있는지 안다.

## Acceptance Criteria

**AC1** — **Given** 성공률 × 건당 비용 그리드가 config에 정의됐을 때
**When** `crm/campaign/sensitivity.py`를 실행하면
**Then** ROI 등고선 데이터가 산출된다(FR14)
**And** `simulate.py`를 **파라미터만 바꿔 반복 호출**할 뿐 산식을 재구현하지 않는다(AD-9). 손익분기 판정도
`expected_saving()` 출력의 부호로 유도하며 `P*value - cost/rate` 같은 산식을 직접 쓰지 않는다.

**AC2** — **Given** 그리드와 대표값의 정합이 요구될 때
**When** config를 import하면
**Then** 대표값이 그리드에 포함되어 있음이 assert되어, 시뮬레이터 결론이 항상 민감도 곡선 위에 있다(AD-4,
P1 `current_cutoff` 이원화 사고 방지)
**And** 이 assert는 **이미 `crm/config.py`가 import 시점에 `raise`로 수행한다**(`assert`가 아니라 `raise` —
`python -O`가 assert를 벗겨도 살아있도록). 3-4는 이 가드에 **의존**하며, 그 실효를 테스트로 고정한다
(대표값을 그리드 밖으로 밀면 config import가 실패함을 합성으로 확인). config의 assert를 sensitivity가 **복제하지 않는다**.

**AC3** — **Given** 등고선이 산출됐을 때
**When** 해석을 확인하면
**Then** **"어떤 가정 구간에서 결론이 뒤집히는가"**가 명시적으로 서술된다(FR14)
**And** 손익분기가 되는 성공률·비용 조합이 수치로 제시된다.
**주의(D1)** — 실측상 **총합 순가치는 그리드 전역에서 뒤집히지 않는다**(최악 코너에서도 +299,034). 등고선을
총합으로만 그리면 밋밋하고 반전이 없다. 뒤집히는 것은 **분면별 순가치의 부호**와 **접촉가치 있는 base 비율**이다.
서술은 이 층위에서 해야 한다(근거는 결정 D1).

**AC4** — **Given** 가정의 지위를 표기해야 할 때
**When** 산출물을 확인하면
**Then** 성공률 30%·비용 5.0 등 대표값이 **"가정(업계 통용 보수값, 실측 아님)"**으로 라벨링되고 정답으로
주장되지 않는다(NFR1)
**And** 그리드에서 산출된 %positive·반전 구간은 **"이 가정 하에서"**의 조건부 결론으로 서술하며, 단일 셀의
수치를 예산 없는 사실처럼 인용하지 않는다(3-3 함정 1과 동형).

### AC 파생 — 이 스토리가 함께 닫는 계약 (필수)

**AC5 (동점 발생 확인 — 3-3 인계)** — `deferred-work.md`의 3-3 create-story 절이 *"3-4가 `RETENTION_GRID`
하단을 쓸면 절감액이 뭉개져 동점이 실제로 발생할 수 있고, 그때 이 규칙이 처음으로 실행된다 — 3-4가 동점
발생 여부를 확인해 기록할 것"*을 남겼다. **결정: 인계 전제는 틀렸다. 측정 결과 그리드 전역(25점) 동점 0건**
(근거는 결정 D3). `saving = P*value*rate - cost`는 `rate>0`에서 `P*value`의 **아핀(affine) 변환**이고,
`P*value`가 이미 10,127/10,127 distinct이므로 어떤 그리드 점에서도 distinctness가 보존된다. 이 성질을
**테스트로 고정**하고(그리드 전역 동점 없음), 리포트가 *"3-4가 동점을 발생시켜 3-3 동점 규칙을 실데이터로
검증했다"*고 **쓰지 않도록** 한다 — 그렇게 쓰면 거짓이다.

**AC6 (AD-12 자체 컷 금지 기계적 강제 — 3-3 선례)** — AD-12는 *"시뮬레이터·민감도는 이 컬럼을 소비하며
자체 컷을 만들지 않는다"*고 sensitivity를 **명시적으로** 구속하는데, 현재 기계적 가드는 `priority.py`에만 있다
(`find_priority_selfcut_violations`, 3-3 코드리뷰가 AC3의 "산문+미커밋 스크립트" 증거 문제로 신설). **결정:
대칭 가드 `find_sensitivity_selfcut_violations`를 신설한다** — `sensitivity.py`가 `.quantile`/`.percentile`/
`.median`을 호출하면 위반(fail-closed). 자기검증 픽스처를 동반한다. **이 가드는 risk_quantile 스윕(D2)과
양립한다** — 스윕은 `matrix.assign_quadrant(rule=...)`를 소비하고 분위수 계산은 `matrix.py`가 소유하므로,
`sensitivity.py` 자신은 `.quantile`을 부르지 않는다.

**AC7 (risk_quantile 분면 정의 민감도 annex — 3-1 인계, 파티 결정 b′)** — `deferred-work.md` 3-1 절이
*"risk_quantile 0.75의 대안 미검토 — 3-4가 분위수 축도 함께 쓸어보면 '분면 정의가 결론을 얼마나 좌우하는가'를
답할 수 있다"*를 넘겼다. **결정: FR14 ROI 등고선과 물리 분리된 별도 annex로 산출한다**(근거 D2). 이 annex는
`matrix.assign_quadrant(rule=QUADRANT_RULE.replace(risk_quantile=q))`를 **소비**해 0.70/0.75/0.80 분면 구성을
산출하고, **official 컬럼·마트에 아무것도 write하지 않음이 테스트로 단언**된다(AD-3 공식 vs 시나리오 분리).
서술은 "판정을 무르는 게 아니라 견고함 검산"으로 프레이밍하며, 이것이 성공률·비용과 **다른 종류의 민감도**
(구조적 vs 파라미터)임을 명시한다. **descope 불가** — 넣기로 결정했으므로 AC다.

## 이 스토리가 내린 결정 (근거 포함)

> **dev가 뒤집을 수 있으나, 뒤집는다면 근거를 여기에 덮어쓸 것.** 3-3의 D1/D2와 같은 지위다.

### D1 — "결론"의 정의: 뒤집히는 것은 총합이 아니라 분면 부호와 접촉 비율

FR14는 *"어떤 가정 구간에서 결론이 뒤집히는가"*를 요구하지만 **어떤 결론인지**는 정하지 않았다. 사전조사가
이걸 강제로 결정하게 만든다:

| 후보 "결론" | 그리드 전역 거동 | 반전 있나 |
|---|---|---|
| **총 순가치**(전원·양수 합) | 최악 코너(rate 0.10, cost 20.0)에서도 +299,034 / 양수합 +434,623 | **없음** — 항상 양수 |
| **접촉가치 있는 base 비율** | 20.27% ~ 100% | **크게 흔들림** |
| **분면별 순가치 부호** | `save_first`·`watch` 25/25 양수 / `low_cost_keep` 8/25 음수 / `accept_churn` 14/25 음수 | **분면마다 다름** |

**결정**: ROI 등고선과 반전 서술은 **총합이 아니라 (a) 분면별 순가치 부호 (b) 접촉가치 있는 base 비율**
층위에서 산출한다. 총합만 그리면 반전이 없어 FR14의 "결론 반전 구간"이 **공집합**으로 나오고, 그건 분석이
없는 게 아니라 **틀린 층위에서 본 것**이다. 실측상 실제로 뒤집히는 두 결론:

- **robust(가정에 안 흔들림)**: `save_first`·`watch`는 그리드 25점 전부에서 접촉이 순가치를 만든다. →
  *"고위험 고객 접촉은 가정 구간 전체에서 결론이 안 뒤집힌다"* 를 수치로 말할 수 있다.
- **fragile(가정이 정하는 결론)**: `low_cost_keep`는 대표값에서 +6.14(간신히 양수)지만 8/25 셀에서 음수,
  `accept_churn`은 대표값 −0.28(간신히 음수)지만 관대한 가정에서 양수. → *"이 두 분면을 접촉할지는 가정이
  정한다"* 가 정직한 결론이다.

이것이 이 프로젝트의 서명(불확실을 확실로 세탁하지 않는다)이 직접 걸리는 지점이다 — "84.8%가 접촉가치
있다"를 사실로 인용하면 그건 `(0.30, 5.0)` **한 셀**의 값이고, 등고선 전체가 답이지 한 점이 답이 아니다.

### D2 — 스윕 차원: 코어 2D(성공률×비용) + risk_quantile는 계약 박힌 별도 annex (파티 결정 b′, daria 승인 2026-07-23)

FR14와 epics AC는 **2D 그리드(성공률 × 비용)**를 요구한다. 그런데 `config.py`의 `QuadrantRule` docstring과
`deferred-work.md` 3-1 절이 *"3-4가 성공률·비용 그리드를 쓸 때 **분위수 축(risk_quantile 0.75)도 함께
쓸어보면** '분면 정의가 결론을 얼마나 좌우하는가'를 답할 수 있다 — 3-4 설계 시 판단할 것"*을 남겼다.

**파티 소환 결과(installed 팀, 2026-07-23)**: create-story 초안은 이걸 "descope 가능한 2차 robustness"로
느슨하게 뒀다. 파티가 그 느슨함을 깼다:
- **Mary(이식가치 저울 전복)** — THESIS §7이 본공연 최우선 열린 결정을 *"배제 임계의 소유권"*으로 두고
  그 옆에 crm 선례 *"컷은 고정, 반전 구간은 별도 산출물(3-4)"*을 문자 그대로 적었다. risk_quantile 스윕은
  **배제 임계 민감도의 리허설**이다 — FR 밖 곁가지가 아니라 이 스토리가 리허설로 존재하는 이유의 절반.
  이 축이 John의 "FR14에 없다"(3-0 burn 우려)를 접게 했다 — 3-0 burn은 *없던 요구를 창설*한 것이고,
  이건 3-1이 *"3-4 설계 시 판단할 것"*으로 **넘긴 판단을 수용**하는 것이라 성격이 다르다.
- **Amelia(중간 무너뜨림)** — "라벨된 2차 robustness"는 **통과 조건(AC)이 없어 썩는다.** 넣기로 했으면 AC다.
- **Sally(단일 판정 방어)** — 3-1이 힘줘 세운 "공식 2×2는 하나"가 3-4에서 물러지면 안 된다. 화면(4-3)까지
  새면 무너진다에 **명시적으로 표를 걸었다**(4-3 시나리오 뷰 감시 예약).
- **Paige(서명)** — config가 이미 0.75를 *"안 재본 가정, one scenario"*로 적어놨다. 안 재고 분면 수를
  사실처럼 실으면 **반만 맞는 문장**. → **descope 문구 삭제.**

**결정 (b′ — 계약 박힌 annex)**:
- **코어(FR14 구속) = 2D 성공률×비용 ROI 등고선 + 분면별 반전 + 손익분기 곡선.** risk_quantile은 이 등고선에
  **절대 섞지 않는다**(John 조건 — 축이 달라 겹치면 오독).
- **risk_quantile = FR14 등고선과 물리 분리된 별도 annex**로 산출하며, 이제 **descope 불가·AC 지위**(AC7).
  네 계약 하에서:
  ① `matrix.assign_quadrant(rule=QUADRANT_RULE.replace(risk_quantile=...))`를 **소비**한다 — 자체 컷 아님
     (AD-12, AC6 가드가 강제: sensitivity.py 자체 `.quantile` 0건).
  ② 산출은 **시나리오**이지 official이 아니다 — `quadrant_official` 재정의·영속화 금지(AD-3). **official
     컬럼·마트 write 0건을 테스트로 단언**(Amelia — "논의했음"이 아니라 검증 가능한 계약으로).
  ③ risk_quantile은 `expected_saving`의 입력이 **아니다**(분면 정의만 바꿈) — 성공률·비용과 **다른 종류의
     민감도**(구조적 vs 파라미터)임을 서술에서 구분.
  ④ annex 서술의 프레임은 **"판정을 무르는 게 아니라 견고함을 검산"** — 실측상 분면 정의는 rate·cost보다
     결론을 더 흔든다(0.70→0.80에서 save_first 537→348). 이걸 숨기면 세탁, 드러내면 서명.

**잔여 이견(기록)**: Sally는 이 스윕이 4-3 시나리오 뷰로 새어 official 판정을 무르게 만들 위험에 표를 걸었다.
3-4는 official/마트 write 0을 테스트로 막지만, **화면 노출 계약은 4-1/4-3 소관**이다 — 그 스토리들이 이
annex를 대시보드로 끌어오면 Sally의 우려가 실하중을 받는다.

### D3 — 동점은 그리드에서 발생하지 않는다 (3-3 인계 전제 반증)

3-3 create-story가 *"3-4가 하단을 쓸면 절감액이 뭉개져 동점이 발생할 수 있다"*고 넘겼다. **틀렸다(실측).**
`saving = P*value*rate - cost`는 `rate>0`인 한 `P*value`의 **엄격 단조 아핀 변환**이다. 아핀 변환은
distinctness를 보존하므로, `P*value`가 10,127개 전부 distinct인 이상(실측) **어떤 `(rate, cost)`에서도
saving은 10,127개 distinct**다. 그리드 전역 25점에서 동점 0건을 확인했다(아래 사전조사 「그리드」 표
`ties` 열이 전부 0). 이는 3-3의 D1이 *"음수 포함 여부가 dense rank를 바꾼다"*는 인계 전제를 실측으로
반증한 것과 **같은 성격**이다 — 인계 문구를 그대로 믿지 말고 측정할 것.

**함의**: 3-3의 동점 2·3차 키(`customer_value`·`CLIENTNUM`)는 3-4에서도 발동하지 않는다. AC1의 동점 절반은
여전히 합성 픽스처가 유일한 검증 수단이고, **3-4가 그걸 실데이터로 검증했다고 쓰면 안 된다.**

## Tasks / Subtasks

- [x] **T1** `crm/campaign/sensitivity.py::sweep_sensitivity` 그리드 스윕 구현 (AC1·AC2·D1)
  - [x] 순수 함수. **`expected_saving()`을 그리드 점마다 재호출**한다 — 산식·손익분기 재구현 금지(AD-9).
        손익분기 판정은 `expected_saving() > 0`의 부호에서 유도(`P*value - cost/rate`를 직접 쓰지 않는다).
  - [x] 스윕은 **함수 인자로 주입**(`retention_grid=RETENTION_GRID`, `cost_grid=COST_GRID` 기본값이 config
        상수 참조 — AD-4). 리터럴 재선언·config 재작성 금지. 파라미터 스윕은 파일이 아니라 인자다(AD-4).
  - [x] 산출은 **분면별 순가치 부호 + 접촉가치 base 비율** 층위(D1). 총합만 내지 말 것.
  - [x] `crm.campaign` 밖 import는 상류(matrix·simulate)만. **자체 분면 컷 금지** — 분면이
        필요하면 `matrix.assign_quadrant`을 소비만(AD-12, AC6 가드가 강제).
  - [x] 결과는 frozen dataclass로 반환(`SensitivityGrid`/`GridCell`/`QuadrantSensitivity`). 대표값
        셀이 그리드에 있음을 constructor가 assert하고 `representative_cell()`이 **자기설명**한다.
- [x] **T2** 손익분기 곡선 (AC3·D1)
  - [x] 손익분기는 `(rate, cost)` 공간의 **연속 쌍곡선족**이다(함정 5). `quadrant_breakeven_rate`가
        `expected_saving` **부호의 이분법**으로 격자에 없는 손익분기 rate를 찾는다(산식 미재구현).
  - [x] fragile 분면(`low_cost_keep`·`accept_churn`)이 부호를 바꾸는 rate를 cost별로 리포트 §③에 명시.
- [x] **T3** risk_quantile 분면 정의 민감도 annex (AC7·D2 — **descope 불가, AC 지위**)
  - [x] FR14 ROI 등고선과 **물리 분리**된 별도 함수 `risk_quantile_annex`. 등고선에 섞지 않는다(John 조건).
  - [x] `matrix.assign_quadrant(rule=QUADRANT_RULE.replace(risk_quantile=q))`를 **소비**해 0.70/0.75/0.80
        스윕. 자체 `.quantile` 호출 금지(AC6 가드). 산출은 **시나리오**, official 아님(AD-3).
  - [x] **official 컬럼·마트 write 0건**을 만족(테스트 `test_annex_writes_nothing_official_or_to_disk`가 단언).
  - [x] 서술 프레임 = **"판정을 무르는 게 아니라 견고함 검산"**(리포트 §⑤). 구조적 vs 파라미터 구분.
        실측: 0.70→0.80에서 save_first 537→348(분면 정의가 rate·cost보다 더 흔듦).
- [x] **T4** 테스트 — 행동 기반 (AC1~AC6)
  - [x] **재구현 감지 변이**: `test_sweep_flows_expected_saving_output_through_verbatim` — monkeypatch한
        sentinel이 모든 셀에 그대로 흐르고 호출 25회임을 단언(3-2 방식). 자체 산식이면 KILL.
  - [x] **AC2 config 가드 실효**: `test_config_representative_grid_guard_bites`가 그리드 밖 rep로 민 합성
        config exec이 `raise`함을 확인. `test_sensitivity_does_not_redeclare_the_grid_or_copy_the_guard`가
        sensitivity가 그리드·가드를 복제하지 **않음**을 AST로 단언.
  - [x] **AC5 동점 0건**: `test_grid_produces_no_ties_...`(성질) + `test_affine_preservation_holds_symbolically`
        (아핀 보존) + 실데이터 `test_grid_has_zero_ties_...`(D3).
  - [x] **AC6 자체컷 가드**: `find_sensitivity_selfcut_violations` self-check 4건(quantile/median KILL, 소비
        PASS, syntax fail-closed) + 모듈 AST 단언 `test_module_calls_no_quantile_percentile_or_median`.
  - [x] **AC7 annex 계약**: `test_annex_writes_nothing_official_or_to_disk`(파일 0·`to_parquet` 부재·
        `quadrant_official` literal 부재, AST) + 실데이터 하드코딩 oracle 537/443/348.
  - [x] **분면 부호 반전**: `test_robust_quadrant_never_flips_and_fragile_one_does`(합성) + 실데이터 4셀 판정.
  - [x] **동어반복 금지** — 그리드 산식을 테스트에서 재작성하지 않음(sentinel·성질·AST·실측 oracle로 검증).
  - [x] 실데이터가 검증 못 하는 것 명시 — 동점 규칙(발동 안 함), risk_quantile 스윕의 "옳음"(분면 정의 소관).
- [x] **T5** 실데이터 실행 + 리포트 (AC1·AC3·AC4)
  - [x] `docs/implementation-artifacts/sensitivity-report-3-4.md` (`scratch/run_sensitivity_3_4.py`가 생성).
  - [x] **CLIENTNUM 조인**(함정 3 — `rows aligned by POSITION: False` 확인). 위치 결합 금지.
  - [x] 25점 그리드 표(%positive·총합·분면 부호), 손익분기 곡선, **가정 라벨링**(NFR1), 무단위(NFR3).
  - [x] **함정 1(총합은 안 뒤집힌다)을 정면으로**: robust 2분면 / fragile 2분면을 나눠 서술.
  - [x] 단일 셀 수치를 사실로 인용 금지(3-3 함정 1과 동형) — "이 가정 하에서" 조건부로.
- [x] **T6** `deferred-work.md`·`sprint-status.yaml`·`structure-guard-coverage.md` 갱신
  - [x] 3-3 인계 해소 표기: **동점 발생 확인(D3, 0건)** · AD-9 캠페인 체인 4단계 완성(campaign order
        실스캔 **3 → 4**). 3-1 인계(risk_quantile)는 D2대로 해소 표기. structure-guard-coverage는 테스트가 재생성.
  - [x] **AD-9 스파인 문구 개정(D4 결정: 고침)**: 3-4가 체인 종단을 만드는 스토리이므로 스파인 AD-9 Rule과
        Structure 트리를 `matrix → simulate → priority → sensitivity`로 개정, 근거를 Change Log에 기록.
  - [x] create-story의 **결정**을 dev가 구현 후 **해소로 승격**함(deferred-work 3-1·3-3 인계 항목).

## Dev Notes

### 🚨 함정 1 — 총합 순가치는 뒤집히지 않는다 (틀린 층위의 밋밋한 등고선)

실측(사전조사): 총 순가치는 그리드 25점 전부에서 크게 양수다 — 대표값 1,454,088, 최악 코너(rate 0.10,
cost 20.0)에서도 +299,034(양수만 합하면 +434,623). **총합으로 등고선을 그리면 완만한 단조면이고 "반전
구간"이 공집합**이다. 그건 이 캠페인이 무조건 옳다는 뜻이 **아니라**, 총합이 틀린 질문이라는 뜻이다.

뒤집히는 두 결론은 **분면 부호**와 **접촉 base 비율**이다(D1). `save_first`·`watch`(고위험)는 가정 전 구간에서
접촉이 이득이고, `low_cost_keep`·`accept_churn`(저위험)은 가정이 부호를 정한다. FR14의 "결론 반전 구간"은
바로 이 fragile 분면의 손익분기 (rate, cost) 조합이다.

### 🚨 함정 2 — 그리드는 동점을 만들지 않는다 (인계 전제 반증, D3)

3-3이 *"하단에서 절감액이 뭉개져 동점 발생"*을 예상했지만 **실측 0건**(그리드 전역). `saving`은 `P*value`의
아핀 변환이고 `P*value`가 10,127 distinct라 rate>0에서 distinctness가 보존된다. 부동소수 언더플로를 의심할
만한 하단(rate 0.10)에서도 값이 뭉개지지 않는다(0.10은 그만큼 작지 않다). **리포트가 "동점 규칙을 실데이터로
검증"이라 쓰면 거짓** — 쓸 수 있는 것은 *"그리드 전역에서 동점이 없어 3-3 동점 규칙은 3-4에서도 발동하지
않았고, 규칙은 합성 픽스처가 유일한 검증 수단으로 남는다"*이다.

### 🚨 함정 3 — 두 parquet 행 오정렬 (3-3 함정 4 재발 위험)

`churn_scored.parquet`과 `bankchurners.parquet`은 **행 순서가 다르고** 둘 다 `RangeIndex`라
`Index.equals`가 `True`를 반환한다(위치 결합 시 총합 +37% 부풀림, 무예외). **T5는 반드시 `CLIENTNUM`으로
조인**한다(`scratch/run_priority_3_3.py`·`preinvest_3_4.py`가 `[guard] rows aligned by POSITION: False`를
찍는다). sensitivity는 그리드를 여러 번 도므로 **데이터 로딩·조인은 루프 밖에서 한 번**, 그 뒤 같은 프레임을
파라미터만 바꿔 재사용한다. 이 계층에 함정 4 기계적 보호는 없고(4-1 인계), CLIENTNUM 조인이 유일 방어다.

### 🚨 함정 4 — risk_quantile 스윕이 만드는 분면은 official이 아니다 (AD-3)

risk_quantile을 0.70/0.80으로 바꿔 `assign_quadrant`을 호출하면 **다른 분면 구성**이 나온다(실측:
save_first 537/443/348). 이것은 **시나리오**이지 `quadrant_official`이 아니다. AD-3(공식 vs 시나리오 분리)에
따라 이 산출을 official 컬럼으로 영속화하거나 마트로 흘리지 않는다 — 리포트 안 robustness 서술에만 쓴다.
스윕은 `matrix.assign_quadrant`을 **소비**하므로(자체 `.quantile` 없음) AC6 가드를 통과한다.

### 🚨 함정 5 — 손익분기는 격자점이 아니라 연속 곡선이다

손익분기 `P*value = cost/rate`는 (rate, cost) 공간의 **쌍곡선족**이다. 5×5 격자점의 %positive만 표로 내면
곡선을 격자에 가둔다. AC3의 "손익분기가 되는 성공률·비용 조합"은 **격자에 없는 조합**일 수 있다(예: fragile
분면 평균이 정확히 0이 되는 rate). 격자는 스캔용이고, 손익분기는 부호가 바뀌는 조합을 **해석적으로 또는
세밀 스캔으로** 짚어 수치로 제시한다.

### 🚨 함정 6 — 가정을 사실로 인용하는 것 (3-3 함정 1과 동형, 서명이 걸리는 지점)

`rate=0.30`·`cost=5.0`은 **가정(업계 통용 보수값, 실측 아님)**이다(config `# source: 정책가정`, NFR1).
그 위에서 나온 "84.8%가 접촉가치 있음"·"1,456,900 절감"은 **그 한 셀의 조건부 결론**이다. 단일 셀을 예산·가정
없이 인용하면 불확실을 확실로 세탁하는 것 — 3-4의 존재 이유가 그 반대다. 산출물은 **범위**를 말한다:
"접촉가치 base 비율은 가정에 따라 20%~100%", "fragile 분면 결론은 가정이 정한다".

### 이 스토리가 만들지 않는 것 (범위 경계)

- **예산·순위·배수 없음** — priority(3-3) 소관. sensitivity는 순가치 부호·비율·손익분기만. `priority`를
  import는 할 수 있으나(AD-9상 상류) 이 스토리는 순위/예산을 다시 다루지 않는다.
- **기대절감액 산식 없음** — `expected_saving()`을 그리드마다 **소비**만. 재구현·손익분기 산식 직접 작성 금지(AD-9).
- **자체 분면 컷 없음** — `assign_quadrant`/`QuadrantRule.replace` **소비**만. `.quantile` 금지(AD-12, AC6 가드).
- **`customer_value` 재정의·재가중 없음**(AD-11).
- **파이프라인 단계 없음** — 순수 함수 + 세션 리포트. 공식 수치의 자리는 4-1 마트 + 4-3 탭(M2 규약).
- **액션 문구 없음** — 액션 후보는 1-7 실측 매핑이 유일한 출처(회고 A6).
- **새 config 파일 없음** — 그리드는 이미 `crm/config.py`에 있다(AD-4). 그리드 값 변경도 안 한다.

### 물려받은 것 (재사용, 재발명 금지)

- **`expected_saving()`**(3-2): `(churn_prob_calibrated, value, *, retention_rate=RETENTION_SUCCESS_RATE,
  cost_per_contact=COST_PER_CONTACT) -> Series[float]`. 그리드 점마다 `retention_rate`·`cost_per_contact`만
  바꿔 재호출. 손익분기 `P*value = cost/rate`(기본값 16.67)는 이 함수 docstring이 이미 유도해 뒀다.
- **`assign_quadrant()`**(3-1): `assign_quadrant(churn_score, value, rule=QUADRANT_RULE) -> QuadrantAssignment`
  (`labels`, `thresholds`, `rule`, `population_size`). `QuadrantRule.replace(risk_quantile=...)`로 스윕용 룰 생성.
- **`crm/config.py`**: `RETENTION_GRID=(0.10,0.20,0.30,0.40,0.50)`, `COST_GRID=(1.0,2.5,5.0,10.0,20.0)`,
  `RETENTION_SUCCESS_RATE=0.30`, `COST_PER_CONTACT=5.0`, `QUADRANT_RULE`. **대표값 ∈ 그리드 assert가 이미
  import 시점 `raise`로 존재**(라인 252~261). 재선언·재작성 금지.
- **campaign 결과 관례**: frozen dataclass(`BudgetSelection`·`QuadrantAssignment`·`RandomBaseline`)에 값과
  근거를 함께 담아 "따로 다니면 모순"을 구조로 막는다. sensitivity 결과도 이 관례를 따를 것.
- **검증 패턴**: `simulate.py::_validate_axis`/`_validate_pair`, `priority.py::_validate_alignment`가 참고
  구현. **단, `Index.equals`는 라벨 정합을 보장하지 않는다**(함정 3).
- **구조 가드 대칭**: `find_priority_selfcut_violations`(checkers.py 라인 241~284)를 그대로 본떠
  `find_sensitivity_selfcut_violations`를 만든다 — `_SELFCUT_MODULE`를 sensitivity로, 나머지 동일.
- **로딩·조인**: `scratch/run_priority_3_3.py`의 `load()` + `scratch/preinvest_3_4.py`.
- **AD-5 투트랙**: 확률(금액)에는 `churn_prob_calibrated`, 분면(순위)에는 `churn_score`. sensitivity는 금액을
  쓸므로 `expected_saving`(보정확률 기반)을 스윕하고, 분면 스윕은 `churn_score` 위에서 `assign_quadrant`.

### 실측 사전조사 (2026-07-23, `scratch/preinvest_3_4.py` / baseline 443 passed / `artifact_id 9e1a4d71800f`)

**dev가 코드로 재확인할 것.** 조인은 `CLIENTNUM`(함정 3). `rows aligned by POSITION: False` 확인됨.
아래 수치는 3-2 공표 per-capita(save_first 1,415.00 등)를 정확히 재현한다 — 모델 불변, 조인 정확.

```
가정: rate ∈ {0.10,0.20,0.30,0.40,0.50}, cost ∈ {1.0,2.5,5.0,10.0,20.0}  (전부 [가정], 실측 아님)
P*value distinct 10,127 / 10,127  ->  saving은 어떤 (rate,cost)에서도 10,127 distinct (동점 0)
```

**① 그리드 — %positive와 총합 (손익분기 = P*value가 cost/rate를 넘어야 양수)**

| rate\cost | 1.0 | 2.5 | 5.0 | 10.0 | 20.0 |
|---|---|---|---|---|---|
| **0.10** | 92.30% | 55.78% | 32.10% | 22.02% | 20.27% |
| **0.20** | 100.00% | 88.71% | 55.78% | 32.10% | 22.02% |
| **0.30** | 100.00% | 96.28% | **84.79%** ← 대표 | 37.56% | 30.51% |
| **0.40** | 100.00% | 99.89% | 88.71% | 55.78% | 32.10% |
| **0.50** | 100.00% | 100.00% | 92.30% | 78.78% | 35.94% |

(%positive = 접촉가치 있는 base 비율. 총합 순가치는 최소 299,034(0.10,20.0) ~ 최대 2,497,745(0.50,1.0),
**전 셀 양수** — 함정 1. 동점은 25점 전부 0.)

**② 분면별 순가치 부호 — 무엇이 robust이고 무엇이 fragile인가 (D1의 핵심)**

| 분면 (n) | per-capita 최소 | 최대 | 양수 셀 / 25 | 결론 |
|---|---|---|---|---|
| `save_first` (443) | 453.33 | 2,365.67 | **25/25** | robust — 가정 전 구간 접촉 이득 |
| `watch` (2,089) | 109.27 | 645.34 | **25/25** | robust |
| `low_cost_keep` (4,624) | −16.29 | 17.57 | 17/25 (8 음수) | **fragile** — 대표값 +6.14, 가정이 부호 결정 |
| `accept_churn` (2,971) | −18.43 | 6.86 | 11/25 (14 음수) | **fragile** — 대표값 −0.28, 관대한 가정서 양수 |

**③ risk_quantile 스윕 (3-1 인계, D2 2차 섹션) — 분면 정의가 구성을 크게 흔든다**

```
risk_q | save_first  watch  low_cost_keep  accept_churn | risk cut
 0.70  |    537       2501       4530          2559     | 0.052812
 0.75  |    443       2089       4624          2971     | 0.132753  ← 공식(QUADRANT_RULE)
 0.80  |    348       1678       4719          3382     | 0.379394
```

`assign_quadrant(rule=QUADRANT_RULE.replace(risk_quantile=q))`로 산출(자체 컷 아님). 이것은 **시나리오**이지
official 아님(함정 4).

> **기준선**: 3-3이 `1b068da / 376`에서 시작해 `443 passed`로 닫혔다(코드리뷰 3레이어 + 파티 5건 종결).
> **주의 — 3-3 최종 상태는 커밋 `9ff1e43` 위 working tree에 있고 아직 커밋되지 않았다**(priority.py 등
> `BUDGET_BELOW_ONE_CONTACT`·overflow 가드·dtype 고정 등). dev는 이 working tree(443 passed) 위에서
> 시작한다. `artifact_id`는 `9e1a4d71800f`로 불변.

### Testing Standards

- `.venv/Scripts/python.exe -m pytest` — 현 기준선 **443 passed**, 회귀 0
- 성질 + 하드코딩 oracle + 변이 테스트, 실데이터 실행 DoD(conventions 3항)
- **재구현 감지가 이 스토리의 핵심 변이**(AD-9): `expected_saving`을 안 부르고 자체 산식을 쓰면 KILL되어야 한다
- **실데이터가 검증 못 하는 것**: 동점 규칙(발동 안 함, D3), risk_quantile 스윕의 "정당성"(분면 정의 소관)
- **문서가 테스트를 앞서지도 뒤처지지도 않기**(회고 A3)

### Project Structure Notes

```
crm/campaign/sensitivity.py                               # NEW - 그리드 스윕·손익분기·분면 반전 (AD-9 종단)
tests/campaign/test_sensitivity.py                        # NEW - 재구현감지·동점0·분면부호·config가드
tests/structure/checkers.py                               # UPDATE - find_sensitivity_selfcut_violations 신설
tests/structure/test_checkers_selfcheck.py                # UPDATE - 새 가드 self-check
tests/structure/test_repo_structure.py                    # UPDATE - 새 가드 배선 + campaign order 3→4
docs/implementation-artifacts/sensitivity-report-3-4.md   # NEW - 25점 그리드·손익분기 곡선·가정 라벨링
docs/implementation-artifacts/structure-guard-coverage.md # UPDATE - 테스트가 재생성 (campaign order 3→4, 새 가드)
docs/implementation-artifacts/deferred-work.md            # UPDATE - 3-3 인계(동점) + 3-1 인계(risk_q) 해소 표기
docs/implementation-artifacts/sprint-status.yaml          # UPDATE
```

> `AD-9 campaign order` 가드의 실스캔이 **3 → 4**로 늘어나는지 확인할 것(3-3이 3으로 만들었다:
> matrix/simulate/priority). `matrix → simulate → priority → sensitivity` 단방향이며 sensitivity가 **종단**이다.
> `find_sensitivity_selfcut_violations`는 `find_priority_selfcut_violations`의 대칭 — `_SELFCUT_MODULE`만
> `crm/campaign/sensitivity.py`로 바꾸면 나머지 로직 동일(fail-closed, self-check 동반).

### 환경 실측 (2026-07-23)

```
baseline 443 passed | artifact_id 9e1a4d71800f (8피처, OOF + Platt)
churn_prob_calibrated mean 0.1607 (= 실제 이탈률) / customer_value min 510.0
RETENTION_GRID=(0.10,0.20,0.30,0.40,0.50)  COST_GRID=(1.0,2.5,5.0,10.0,20.0)  대표값 ∈ 그리드 True
churn_scored.parquet 행 순서 != bankchurners.parquet — CLIENTNUM 조인 필수(함정 3)
그리드 전역 동점 0건 · save_first/watch 25/25 양수 · low_cost_keep/accept_churn fragile
```

### References

- [Source: docs/planning-artifacts/epics.md#Story 3.4] — AC 원문(FR14, AD-4, AD-9, NFR1)
- [Source: .../ARCHITECTURE-SPINE.md#AD-4] — 가정 파라미터 단일 출처, 그리드 대표값 포함 assert, 스윕은 인자
- [Source: .../ARCHITECTURE-SPINE.md#AD-9] — `matrix → simulate → sensitivity` 단방향, 산식 재구현 금지
- [Source: .../ARCHITECTURE-SPINE.md#AD-12] — `quadrant_official` 소비, 자체 컷 금지(민감도 명시 구속)
- [Source: .../ARCHITECTURE-SPINE.md#AD-3] — 공식 vs 시나리오 분리(risk_quantile 스윕이 official 아님)
- [Source: .../ARCHITECTURE-SPINE.md#AD-11] — `customer_value` 소비·재가중 금지
- [Source: crm/config.py] — RETENTION_GRID·COST_GRID·QUADRANT_RULE, 대표값 raise 가드, QuadrantRule.replace
- [Source: crm/campaign/simulate.py] — `expected_saving` 시그니처·손익분기 유도·재호출 계약
- [Source: crm/campaign/matrix.py] — `assign_quadrant`·`QuadrantAssignment`·`quadrant_thresholds`
- [Source: crm/campaign/priority.py] — 3-3 결과(reuse 가능), campaign 결과 dataclass 관례
- [Source: tests/structure/checkers.py] — `find_priority_selfcut_violations`(대칭 신설 대상), `_CAMPAIGN_ORDER`
- [Source: docs/implementation-artifacts/3-3-budget-constrained-target-priority.md] — 함정 4·D1·동점 인계, 변이 관례
- [Source: docs/implementation-artifacts/deferred-work.md#3-1] — risk_quantile 0.75 대안 미검토(3-4가 판단)
- [Source: docs/implementation-artifacts/deferred-work.md#3-3] — 동점 발생 확인 인계, AD-9 스파인 4단계 개정
- [Source: docs/implementation-artifacts/savings-report-3-2.md] — 분면 per-capita(1,415.00 등, 재현 확인)
- [Source: 실측 2026-07-23 scratch/preinvest_3_4.py] — 25점 그리드·동점 0·분면 robust/fragile·risk_q 스윕

## Dev Agent Record

### Agent Model Used

claude-opus-4-8 (bmad-dev-story)

### Debug Log References

- 기준선 실측: `_bmad`를 Desktop에서 프로젝트 안으로 이관한 결과 AD-4 config 가드가 `_bmad/*.toml`을
  "unexpected config file"로 잡아 baseline이 red였다(443이 아니라 442 + 1 fail). `_bmad`는 `.claude`와
  동류의 **프로젝트 툴링**이므로 `checkers.py::_SKIP_DIRS`에 추가해 해소 → 443 green 복원 후 착수.
- `scratch/run_sensitivity_3_4.py`가 신모듈로 사전조사 수치를 **정확히 재현**(84.79%, 동점 0, 537/443/348,
  분면 robust/fragile 판정). 손익분기 이분법도 대표 cost 5.0에서 accept_churn 0.3179 / low_cost_keep
  0.1346으로 대표값 근방 부호(−0.28 / +6.14)와 정합.

### Completion Notes List

- **AC1(재구현 금지)**: `sweep_sensitivity`·`quadrant_breakeven_rate` 모두 `expected_saving`을 **재호출**만
  한다. 손익분기는 산식이 아니라 **출력 부호**에서 유도(이분법). 핵심 변이 테스트가 monkeypatch sentinel의
  관통을 단언해 자체 산식을 KILL한다. 모듈 AST에 `retention_rate`/`cost_per_contact` 산술 0건도 단언.
- **AC2**: 대표값∈그리드 불변은 `config.py`의 import 시점 `raise`가 소유한다(3-4는 복제하지 않고 **의존**).
  sweep는 자기 **인자**(representative)가 **넘겨받은 그리드**에 있는지만 검사한다 — config 상수 가드와 별개.
- **AC3·D1**: 총합은 그리드 전역 양수(안 뒤집힘, 함정 1)라 "결론"을 **접촉 base 비율 + 분면 부호**로 잡았다.
  save_first·watch robust 25/25, low_cost_keep·accept_churn fragile. 손익분기는 연속 곡선으로 수치 제시(§③).
- **AC5·D3(인계 전제 반증)**: 그리드 전역 동점 0건. saving은 P*value의 아핀 변환이라 distinctness 보존.
  리포트는 "동점을 실데이터로 검증"이라 **쓰지 않는다**(거짓 방지).
- **AC6**: `find_sensitivity_selfcut_violations` 신설(priority 가드와 공유 헬퍼 `_find_selfcut_violations`로
  리팩터, 중복 제거). campaign order 실스캔 3→4. 두 가드 모두 self-check 동반, fail-closed.
- **AC7·D2(파티 b′)**: risk_quantile annex는 FR14 등고선과 물리 분리, `assign_quadrant` 소비, official/디스크
  write 0을 테스트로 단언. 프레임 "견고함 검산". 분면 정의가 rate·cost보다 더 흔듦(537→348)을 드러냄.
- **D4**: 체인 종단(sensitivity.py)을 만드는 스토리에서 스파인 AD-9 문구를 4단계로 개정(가드-문서 정합).
- **회귀**: 443 → **464 passed**(신규 21, 회귀 0). 실데이터 오라클 테스트는 parquet 부재 시 skip.

### File List

- `crm/campaign/sensitivity.py` — NEW. 그리드 스윕·손익분기 이분법·risk_quantile annex(순수 함수, frozen dataclass).
- `tests/campaign/test_sensitivity.py` — NEW. 재구현감지·동점0·분면부호·config가드·annex계약·자체컷 AST + 실데이터 오라클.
- `tests/structure/checkers.py` — UPDATE. `find_sensitivity_selfcut_violations` 신설(+공유 헬퍼 리팩터), `_bmad` skip-dir 추가.
- `tests/structure/test_checkers_selfcheck.py` — UPDATE. 새 가드 self-check 4건.
- `tests/structure/test_repo_structure.py` — UPDATE. 새 가드 배선(RULES) + coverage 재생성.
- `docs/implementation-artifacts/sensitivity-report-3-4.md` — NEW. 25점 그리드·손익분기 곡선·annex·가정 라벨링.
- `docs/implementation-artifacts/structure-guard-coverage.md` — UPDATE(테스트 재생성). campaign order 3→4, sensitivity self-cut 등재.
- `docs/implementation-artifacts/deferred-work.md` — UPDATE. 3-1(risk_q)·3-3(동점)·AD-9(4단계) 인계 해소 + 3-4 신규 deferred 2건.
- `docs/implementation-artifacts/sprint-status.yaml` — UPDATE. 3-4 in-progress→review.
- `docs/planning-artifacts/architecture/.../ARCHITECTURE-SPINE.md` — UPDATE(D4). AD-9 Rule·Structure 트리 4단계 개정.
- `scratch/run_sensitivity_3_4.py` — NEW(gitignored). 실데이터 리포트 생성기.

## Change Log

| 날짜 | 변경 |
|---|---|
| 2026-07-23 | 스토리 3-4 create-story. FR14 "결론 반전 구간"의 **"결론"을 실측으로 정의**(D1) — 총합 순가치는 그리드 전역 양수라 안 뒤집히고, 뒤집히는 것은 **분면 부호**(save_first·watch robust 25/25 / low_cost_keep·accept_churn fragile)와 **접촉 base 비율**(20%~100%). 스윕 차원 결정(D2) — 코어 2D(성공률×비용), risk_quantile은 라벨된 2차 robustness(matrix.assign_quadrant 소비, official 아님). 3-3 인계 전제 반증(D3) — **그리드 전역 동점 0건**(saving은 P*value의 아핀 변환, distinctness 보존). AC 파생 2건: AC5 동점 발생 확인(0건 고정) · AC6 `find_sensitivity_selfcut_violations` 대칭 가드 신설. 함정 6건 실측: 총합 안 뒤집힘 · 동점 없음 · 행 오정렬 CLIENTNUM 조인 · risk_q 스윕은 시나리오 · 손익분기는 연속곡선 · 가정을 사실로 인용 금지. AD-9 캠페인 체인 4단계 완성(sensitivity.py로 실스캔 3→4), 스파인 문구 개정은 dev 판단(D4 후보). Status → ready-for-dev. 기준선 443 passed / artifact_id 9e1a4d71800f |
| 2026-07-23 | **스토리 3-4 dev 구현 완료 (443 → 464 passed, 회귀 0, review 상태).** `sensitivity.py` 신설 — `sweep_sensitivity`(그리드 스윕, frozen dataclass, expected_saving 재호출만), `quadrant_breakeven_rate`(손익분기 이분법, 산식 미재구현), `risk_quantile_annex`(D2 파티 b′ — assign_quadrant 소비, official/디스크 write 0). AC1~AC7 전건 테스트 고정: 재구현감지 sentinel 변이·config 가드 실효·동점0(D3 인계 전제 반증)·자체컷 대칭가드 `find_sensitivity_selfcut_violations`·annex 계약·분면 부호 반전. **D3 반증**: 그리드 전역 동점 0건(saving은 P*value 아핀 변환→distinctness 보존) — 리포트가 "동점 실검증"이라 쓰지 않음. **D4 결정(고침)**: 체인 종단을 만드는 스토리라 스파인 AD-9 문구를 `matrix→simulate→priority→sensitivity` 4단계로 개정(가드-문서 정합, campaign order 실스캔 3→4). 기준선 복원: `_bmad` 프로젝트 이관이 AD-4 가드에 걸려 red였던 것을 `_SKIP_DIRS`에 `_bmad` 추가(`.claude` 동류 툴링)로 해소. 인계 해소: 3-1 risk_quantile(D2)·3-3 동점(D3)·AD-9 4단계(D4). 리포트 `sensitivity-report-3-4.md` 실데이터 산출(CLIENTNUM 조인, 가정 라벨링, 범위 서술). |
| 2026-07-23 | **D2 파티 종결(installed 팀, daria 승인 → b′)**. risk_quantile 스윕을 "descope 가능한 2차 robustness"에서 **계약 박힌 별도 annex(AC7 신설)**로 승격. Mary가 THESIS §7("컷은 고정·반전구간은 별도산출물 3-4")로 이식가치 저울을 뒤집어 John의 FR14-scope 반대를 접게 함(3-0 burn=없던 요구 창설 vs 이건 3-1이 넘긴 판단 수용, 성격 구분). Amelia: (b)는 AC 비어 썩는다 → **official/마트 write 0을 테스트로 단언**하는 계약으로. Sally 이견 표결: 4-3 시나리오 뷰로 새면 3-1 단일판정 무너진다에 걸고 감시 예약(잔여 이견 기록). Paige: **descope 문구 삭제**(반만 맞는 문장). 조건: FR14 ROI 등고선과 **물리 분리**. D2 본문·AC7·T3·T4 개정, 코드 불변(443 passed 유지). |
