---
baseline_commit: a40fefa
---

# Story 4.3: 대시보드 사양서

Status: review

<!-- Note: Validation is optional. Run validate-create-story for quality check before dev-story. -->

## Story

As a 워크북 제작자(사용자),
I want 무엇을 어떤 탭에 어떻게 그릴지가 명세된 사양서를,
so that 세션 없이도 Tableau 워크북을 규약대로 만들 수 있고, 화면 층에서 공식 판정이 물러지거나(annex 오노출) 오용되는(+19% 드롭다운) 일이 사양 수준에서 차단된다.

## 배경 — 이 스토리는 문서가 산출물이다

4-1a/4-1b가 마트를 만들고 잠갔다. 4-3은 **그 마트를 소비하는 화면의 계약**을 쓴다 — 코드 0줄, 사양서 1부 + 문서-계약 테스트. Tableau 실행은 세션이 못 하므로(conventions 7항) 워크북 제작·퍼블리시는 4-4 사용자 분업이고, 이 스토리의 done은 **사양서가 기계 검증 가능하게 완결**되는 것이다. Sally 열린 액션 2건(A8 SHAP≠인과 화면 전달 · B8 annex 노출 감시)이 여기서 종결된다.

**OQ-5 무관**: Tableau Public 계정 미확인은 4-4 스코프 문제다 — 사양서 작성은 계정이 필요 없다.

## Acceptance Criteria

**AC1 — 4탭 구성·마트 연결·조인 금지 (FR17·AD-2 / 스토리 결정 D1)**
Given 고객 마트가 확정되고 LTV 마트는 epic-2 동결로 부재할 때
When `marts/dashboard-spec.md`를 작성하면
Then 고객분석 3탭(`mart_customers` 연결)의 시트·차트·필드 매핑이 **전부 명세**되고, LTV 방법론 데모 1탭은 **동결 스텁**으로 명세된다(D1): 탭 자리·비결합 원칙(두 마트 조인 계산필드 금지, AD-2)·"epic-2 동결로 데이터 부재, 4-2 해동 시 시트 매핑 작성"을 명시하되 시트·필드 매핑은 쓰지 않는다.
And 각 탭이 어느 마트(파일 경로)에 연결되는지 명시되고, **두 마트를 조인하는 계산필드 금지**가 명문 조항으로 실린다.
And FR17 커버리지가 "4-3+4-2 합"임과 4-2 blocked 사실을 사양서 머리말이 정직하게 명시한다(NFR 정직성 — 4-1a "LTV 레인 미수행" 선례).

**AC2 — 시나리오 뷰 규약 + `campaign_selected` 실체화 (AD-3 / 스토리 결정 D3)**
Given 시나리오 뷰가 허용될 때
When 사양서의 시나리오 절을 확인하면
Then AD-3 검사 가능 4항목이 그대로 실린다 — ①시트 제목 `[시나리오] ` 접두 ②공식 뷰와 다른 탭 ③다른 배경색 ④현재 임계값과 공식 임계값(`threshold_official_*`) 병기.
And 시나리오 계산필드는 `_scenario` 접미를 갖고, **`_official` 컬럼을 재계산하는 계산필드 금지**가 명시된다.
And **`campaign_selected_scenario`가 여기서 실체화된다**(D3, 4-1b 인계): 예산 파라미터 `[budget]`을 받아 `(target_priority <= FLOOR([budget]/5.0)) AND (expected_saving > 0)` — 산식의 출처는 `mart_customers.schema.md`의 AD-12 고정 정의임을 명시(재계산이 아니라 **비탑재 정의의 시각화** — `campaign_selected`는 official 마트 컬럼이 아니므로 AD-3와 무충돌). `cost_per_contact=5.0`이 정책가정임을 병기.

**AC3 — BI 역할 경계 (AD-3)**
Given BI의 역할 경계를 규정할 때
When 사양서를 읽으면
Then "공식 판정은 Python이 계산해 마트 컬럼으로 고정, **BI는 표시하며 재계산하지 않는다**"가 선언되고, README·발표자료의 모든 스크린샷·수치는 **공식 뷰에서만** 취한다는 규칙이 포함된다.

**AC4 — `churn_score` 필드 비노출 (스토리 결정 D2, 3-0 D3 인계 종결)**
Given 마트 CSV에 `churn_score`·`churn_prob_calibrated`가 나란히 실려 있을 때
When 사양서의 필드 매핑을 확인하면
Then **`churn_score`는 어떤 탭·시트·드롭다운에도 노출 필드로 등장하지 않으며**, "데이터 원본에서 숨김(hide) 처리" 조항이 실린다. 근거 병기: 화면에 필요 없고(분면은 `quadrant_official`, 기준선은 `threshold_official_risk`가 담당) 노출 시 금액 산식 오선택으로 총합 +19.0% 부풀림(3-2 실측). 감사 필요 시 마트 CSV·스키마 문서를 직접 본다(층 분리: 마트=감사, 화면=오용 방지 — 3-0 D3 층 분리 제안의 최종 형태).

**AC5 — risk_quantile annex 비노출 (3-4 인계, Sally B8 종결)**
Given 3-4가 annex의 official 오염 0을 코드 층에서 단언했지만 화면 계약은 4-3 몫일 때
When 사양서를 확인하면
Then **"risk_quantile annex(0.70/0.80 분면 구성)는 대시보드에 탭·시트·파라미터로 싣지 않는다"**가 금지 조항으로 실린다. 시나리오 파라미터는 성공률·비용(3-4 코어 2D)만 허용 — 분면 정의(risk_quantile)를 화면에서 흔들면 "공식 2×2는 하나"(3-1·AD-12)가 화면에서 물러진다(3-4 Sally 잔여 이견의 화면 계약 종결).

**AC6 — SHAP≠인과 경고 화면 전달 (1-7 인계, Sally/A8 종결)**
Given 요인·리텐션 액션이 화면 어딘가에 언급될 때
When 사양서를 확인하면
Then 세그먼트 탭의 요인·액션 표기는 **텍스트 캡션만** 허용되고(SHAP 데이터는 gitignored `data/churn_shap.parquet` — 마트·공개면에 없음), 캡션 규약이 명시된다: `churn-drivers-actions-1-7.md`의 문구를 출처로 쓰며 **"요인은 모델의 판단 근거이지 인과가 아니다"** 경고와 **"액션은 실측 아닌 제안"** 라벨을 캡션마다 병기. 이 경고 없이 요인을 표시하는 시트는 사양 위반임이 명시된다.

**AC7 — 문서=계약 기계 검증 (AD-2 확장, 4-1a 패턴)**
Given 사양서가 계약면일 때
When pytest를 실행하면
Then `tests/marts/test_dashboard_spec.py`가 검증한다: ①사양서의 노출 필드 집합이 `MART_COLUMNS`의 부분집합(존재하지 않는 필드 명세 불가) ②`churn_score` ∉ 노출 필드 ③금지 조항 3종(마트 조인·`_official` 재계산·annex) 문구 존재 ④AD-3 4항목·`_scenario` 규칙·SHAP≠인과 경고 문구 존재 ⑤`campaign_selected_scenario` 산식이 `target_priority`·`expected_saving > 0`을 담음.

## Tasks / Subtasks

- [x] **T1 — `marts/dashboard-spec.md` 작성: 구조·탭** (AC1, AC3)
  - [x] 머리말: 목적·역할 경계(AD-3 선언)·FR17 커버리지 정직 명시(4-2 blocked)·스크린샷 규칙. 마트 연결: `marts/mart_customers.csv`(+스키마 문서 참조).
  - [x] **탭1 「타게팅 2×2」(공식)**: 분면 산점도(x=`churn_prob_calibrated`, y=`customer_value`, 색=`quadrant_official`) + 기준선(`threshold_official_risk`·`threshold_official_value` 상수선) + 분면별 인원·기대절감 합 요약표. 실측 기대값 병기(4624/2971/2089/443 — 검산용).
  - [x] **탭2 「캠페인 우선순위」(공식+시나리오)**: 공식 시트 = `target_priority` 정렬 리스트 + `expected_saving` 막대(가정 라벨 캡션). 시나리오 시트 = AC2의 `campaign_selected_scenario`(예산 파라미터) — AD-3 4항목 적용.
  - [x] **탭3 「세그먼트 프로필」(공식)**: `segment_id`별 인원·가치·분면 구성 + AC6 캡션 규약(요인·액션 텍스트).
  - [x] **탭4 「LTV 방법론 데모」(동결 스텁, D1)**: 자리·비결합 원칙·부재 사유만.
  - [x] 필드 매핑 표: `노출 필드 | 탭 | 용도` — 기계 파싱 가능한 형식(테스트가 읽는 단일 출처). `churn_score`는 **숨김 필드 절**에 별도 기재(D2 근거 포함).
- [x] **T2 — 금지 조항·시나리오 규약 절** (AC2, AC4, AC5)
  - [x] 금지 조항 3종: 마트 조인 계산필드 / `_official` 재계산 계산필드 / annex(risk_quantile) 화면 반입.
  - [x] 시나리오 규약: AD-3 4항목 체크리스트 원문 + `_scenario` 접미 + `campaign_selected_scenario` 산식·출처·정책가정 라벨.
- [x] **T3 — 문서=계약 테스트** (AC7)
  - [x] `tests/marts/test_dashboard_spec.py` 신설: 필드 매핑 표 파싱(⊆ `MART_COLUMNS`, `churn_score` 부재), 금지 조항·경고 문구·산식 존재 단언. 파싱 헬퍼는 4-1a `_schema_columns` 패턴(칸 위치 견고성 — 4-1b 리뷰 교훈: 셀 단위 검사).
- [x] **T4 — 인계 종결 기록** (AC5, AC6)
  - [x] sprint-status 액션 아이템 갱신: Sally A8(SHAP≠인과 화면 전달)·B8(annex 감시) → done, 마트 오용 방지(3-0 D3) → done. deferred-work의 "SHAP 인과 해석 금지의 문서 강제"·"risk_quantile annex 화면 노출" 항목에 종결 주석.
  - [x] **문서 체크리스트 DoD**: dashboard-spec.md(신설) · sprint-status(액션 3건) · deferred-work(종결 2곳) · 스토리 파일. 마트·스키마 문서 무변경 확인(이 스토리는 소비만).
- [x] **T5 — 회귀** (전 AC)
  - [x] 전체 스위트 회귀 0(이 환경 기준선 **375 passed**, churn 제외 — xgboost 부재). 마트 CSV·schema.md **바이트 불변**(4-3은 마트를 읽기만 한다).

## Dev Notes

### 이 스토리의 결정 (create-story가 내림 — dev는 따르되 이견 시 HALT)

- **D1 (AC1)**: LTV 탭 = 동결 스텁. 3탭만 쓰면 FR17 위반, 4탭 풀명세는 존재하지 않는 데이터의 사양(세탁). 스텁이 정직한 중간값 — 4-1a "A 레인만 수행" 선례.
- **D2 (AC4)**: `churn_score` 화면 비노출(숨김). 3-0 D3 층 분리 제안("마트에서 점수를 빼는 선택을 안 해도 된다")의 완성 — 마트는 두 컬럼 유지(감사), 화면은 숨김(오용 방지). 화면에 이 컬럼이 필요한 시트가 하나도 없음을 T1 매핑이 증명한다.
- **D3 (AC2)**: `campaign_selected`는 시나리오 계산필드로 실체화. AD-12 정의(스키마 고정)의 시각화이지 official 재계산이 아님 — official 마트 컬럼이 아니고, 예산은 시나리오 입력(4-1b D1)이므로 파라미터가 정확히 맞는 자리. `FLOOR([budget]/5.0)`의 5.0은 `COST_PER_CONTACT` 정책가정 — 캡션 라벨 필수.
- **D4 (AC5)**: annex 전면 비반입. 시나리오 파라미터는 rate·cost만(3-4 코어 2D와 동일 경계 — "분면 정의는 흔들지 않는다"가 화면 계약).

### 실측 재료 (전부 이 세션·리포지토리에서 확인)

- 마트 컬럼 = `MART_COLUMNS` 10개(`crm/marts/customers.py`) — 사양서 노출 필드는 이 중 9개(churn_score 제외) 이하.
- 골든값(검산용 병기): risk 컷 0.132753 · value 컷 3899 · 분포 4624/2971/2089/443 · 총합 1,454,088.
- SHAP≠인과 문구 원문: `churn-drivers-actions-1-7.md:12` — *"SHAP은 인과가 아니다: 아래 '요인'은 모델이 위험 점수를 매길 때 그렇게 판단한 근거이지..."*. 액션 라벨: "실측 아닌 제안"(1-7 AC).
- annex 계약: `3-4-...md` AC7/D2 b′ — annex는 `assign_quadrant(rule=...replace(risk_quantile=q))` 소비, official/마트 write 0 테스트 단언 완료. **화면 계약만 이 스토리 몫.**
- `select_within_budget` 정의: `target_priority ≤ 예산÷비용` AND `expected_saving > 0`(스키마 문서 AD-12 절 — 4-1b가 고정).

### 범위 밖 (하지 말 것)

- 워크북 실제 제작·퍼블리시·README — **4-4**(blocked-external, OQ-5 계정 확인 필요).
- 마트·스키마·crm 코드 변경 — 이 스토리는 **읽기 전용 소비자**. 코드 변경이 필요해 보이면 HALT.
- `mart_ltv_demo` 관련 일체(4-2 blocked).
- RandomBaseline 모집단 지문(4-1b 이연) — 사양서가 배수를 화면에 싣지 않으므로 무관(배수 곡선은 세션 리포트 소관, conventions 10번).

### Testing standards

- 문서=계약: 존재 단언은 **절/칸 한정**으로(4-1b 리뷰 교훈 — 전문 검색은 우연 통과), 필드 매핑은 `MART_COLUMNS`와 기계 대조.
- 이 스토리 테스트는 실데이터 불필요(문서 파싱만) — skip 없음.

### Project Structure Notes

- **신규**: `marts/dashboard-spec.md`(사양서 — 마트와 함께 다니는 소비 계약면), `tests/marts/test_dashboard_spec.py`.
- **수정**: sprint-status(액션 종결)·deferred-work(종결 주석)·스토리 파일.
- **불변**: `marts/mart_customers.csv`·`.schema.md`·`crm/*`·`pipelines/*` 전부.

### References

- [Source: docs/planning-artifacts/epics.md#Story 4.3] — AC 원문(FR17·AD-2·AD-3)
- [Source: docs/implementation-artifacts/3-4-sensitivity-analysis-flip-region.md#D2] — annex 계약 b′·Sally 우려 원문
- [Source: docs/implementation-artifacts/churn-drivers-actions-1-7.md] — SHAP≠인과 문구·액션 매핑(캡션 출처)
- [Source: marts/mart_customers.schema.md] — 컬럼·용도/금지·campaign_selected 정의(AD-12)
- [Source: docs/implementation-artifacts/deferred-work.md "4-1 입력"] — +19% 오용 실측·층 분리 제안
- [Source: docs/implementation-artifacts/epic-3-retro-2026-07-23.md#B8] — Sally 액션 원문

## Dev Agent Record

### Agent Model Used

claude-opus-5 (Claude Code, dev-story workflow)

### Debug Log References

- **슬라이스 앵커 함정(자가 검출)**: 사양서 머리말이 "탭4"를 본문보다 먼저 언급해, 테스트의 bare-substring 앵커(`find("탭3")`~`find("탭4")`)가 역방향 슬라이스 → 빈 문자열로 우연 통과할 뻔 — red로 잡혀 heading 앵커(`### 탭3`)로 수정. 같은 계열로 "재계산이 아니다" 문구가 줄바꿈에 갈라져 red — 사양서 줄바꿈 조정. 문서-계약 테스트의 red-green 사이클이 실제로 작동함을 확인.

### Completion Notes List

- ✅ **AC1 (D1)**: 4탭 명세 — 고객 3탭 풀명세 + LTV 탭 동결 스텁(부재 사유·비결합 원칙·"4-2 해동 시"). FR17 커버리지 정직 명시.
- ✅ **AC2 (D3)**: 시나리오 규약(AD-3 4항목·`_scenario` 접미·`_official` 재계산 금지) + `campaign_selected_scenario` 실체화(산식=스키마 AD-12 정의의 시각화, 예산 파라미터, 정책가정 라벨).
- ✅ **AC3**: BI 역할 경계 선언 + 스크린샷 공식 뷰 한정 규칙.
- ✅ **AC4 (D2)**: `churn_score` 화면 비노출(숨김 필드 절, +19% 근거) — 노출 필드는 정확히 9개(전 컬럼 − churn_score)임을 테스트가 양방향 단언(누락도 초과도 불가).
- ✅ **AC5 (D4)**: annex 반입 금지 조항("탭·시트·파라미터 어느 형태로도") — Sally B8 종결.
- ✅ **AC6**: 탭3 캡션 규약(경고 2문구 병기 의무, 미병기=사양 위반, 텍스트 캡션만) — Sally A8 종결.
- ✅ **AC7**: 문서-계약 테스트 10건 — 필드 매핑 ⊆ MART_COLUMNS 기계 대조, 절/셀 한정 단언(4-1b 교훈).
- **회귀**: 375 → **385 passed**(+10), 1 skipped, 회귀 0. **마트 CSV·schema.md·crm·pipelines 바이트 불변**(읽기 전용 소비자 DoD).
- **인계 종결**: Sally A8(에픽1부터 2회고 이월)·B8·3-0 D3 오용 방지 — sprint-status 액션 3건 done, deferred-work 2곳 종결 주석. **Sally 라인 전체 종결.**
- **4-4 인계**: 워크북 제작·퍼블리시·README·공개 점검(OQ-5 계정 확인 선행). 검산 앵커 표가 워크북 대조 절차의 재료.

### File List

**신규**
- `marts/dashboard-spec.md` — 대시보드 사양서(계약면)
- `tests/marts/test_dashboard_spec.py` — 문서-계약 테스트 10건

**수정**
- `docs/implementation-artifacts/sprint-status.yaml` — 상태 + Sally 액션 3건 done
- `docs/implementation-artifacts/deferred-work.md` — 종결 주석 2곳(annex 화면·SHAP 문서 강제)

### Change Log

- 2026-07-24: 4-3 구현 — 대시보드 사양서(4탭·노출 필드 9종 단일 출처·금지 조항 3종·AD-3 시나리오 규약·campaign_selected_scenario 실체화·SHAP≠인과 캡션 규약) + 문서-계약 테스트 10건. 385 passed, 마트·코드 바이트 불변. Sally 인계 라인(A8·B8·오용 방지) 전체 종결.

---

**기준선**: 4-1b done 커밋 `a40fefa`. 이 환경(xgboost 미설치) **375 passed**(churn 제외). 이 스토리는 마트를 **읽기만** 한다 — 마트·스키마·코드 바이트 불변이 DoD.

**Ultimate context engine analysis completed — comprehensive developer guide created.**
