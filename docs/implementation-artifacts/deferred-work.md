# Deferred Work — crm-targeting-lab

의도적으로 미룬 항목을 근거와 함께 기록한다(conventions 5항).

## Deferred from: code review of 1-1a-scaffolding-config-structure-guards (2026-07-20)

- ~~**파이프라인 `main(input_paths, output_paths)` 시그니처 존재 검증**~~ — **해소(1-1b)**: `find_pipeline_shape_violations`에 main 부재·시그니처 불일치 검사 추가, 자기검증 픽스처 2건 동반.
- **`pyproject.toml` 도입 시 AD-4 config 가드 충돌 예고**
 — `.toml`이 금지 확장자라 표준 패키징 파일 도입 순간 오탐. 도입하는 스토리가 `_CONFIG_WHITELIST`에 사유 주석과 함께 등재할 것.

## Deferred from: code review of 1-1b-freshness-atomic-write-data-acquisition (2026-07-20)

- **크래시 안전성(예외 안전성과 별개)** — `write_with_meta`는 parking → 쓰기 → meta 순서라, parking과 복원 사이에 프로세스가 kill되거나 정전이 나면 마지막 정상 산출물이 임의 이름의 `.tmp`에 숨는다. 재실행 시 새 uuid를 쓰므로 자동 복구 경로가 없다. 진짜 해결은 파이프라인 시작 시 고아 `.tmp` 스캔·복구 루틴이며, 이 스토리 범위를 넘는다. 로컬 배치 envelope에서 발생 확률이 낮아 미룬다.
- **산출물 자체의 내용 해시 부재** — meta의 `inputs`는 생산 단계가 *읽은* 파일의 해시이고 산출물 자신의 해시는 없다. parquet을 수동 변조해도 meta가 남아 있으면 `verify_inputs`를 통과한다. AD-13 규칙이 요구하는 범위(선행 stage + config_hash)는 충족하며 위·변조 탐지는 계약 밖이다. 후속 스토리가 이 한계를 알고 있어야 한다.
- **kagglehub 로컬 캐시 재사용** — 업스트림 데이터가 갱신돼도 캐시가 있으면 재다운로드하지 않아 stale 데이터가 "신선" 판정될 수 있다. `force_download` 파라미터 노출이나 캐시 무효화 절차 문서화가 필요하다. 두 데이터셋 모두 고정 스냅샷 성격이라 당장은 위험이 낮다.
- **(새 output + 옛 meta) 창** — `write_with_meta`는 output rename 직후·meta 쓰기 직전 구간에서 옛 meta와 새 output이 공존한다. 단일 프로세스 배치 실행 envelope에서는 이 창을 관측할 동시 실행이 없어 실해악이 낮다.

## Deferred from: code review of 1-3-rfm-proxy-features (2026-07-21, 외부 GPT 리뷰)

- **전이적(transitive) staleness — downstream-only 재실행 미방지 (리뷰 High-2)**: `is_output_stale`은
  소비 stage의 **직접** 입력 드리프트(+자기 config·stage)만 본다. 입력 artifact가 바이트
  동일하지만 그 artifact의 **원천**이 그 사이 바뀌었고 하위 stage만 재실행되면
  탐지하지 못한다(예: `bankchurners` v2로 바뀌었는데 02는 안 돌리고 05만 → 05의 직접 입력
  `features`는 v1 그대로라 fresh). 진짜 해결은 **오케스트레이터 레벨 DAG 위상 검증** 또는
  입력 meta를 따라 올라가는 **재귀 의존성 검증**이며, 파이프라인에 05·오케스트레이터가
  생기는 스토리(3-x/4-x)의 소관이다. 1-3의 docstring·리포트는 이 한계를 명시하도록 정정했다.
- **코드 변경(config 무변) 미탐지 (리뷰 High-1 잔여)**: `config_hash`는 `config.py` 바이트만
  본다(AD-13 규약). stage 코드(`features.py`)만 바뀌고 config를 안 건드리면 산출물이 stale로
  잡히지 않는다. stage 코드 지문(모듈 해시)을 cache key에 넣는 것은 **모든 stage에 적용되는
  아키텍처 변경**이라 스토리 패치가 아니라 AD-13 개정 사안이다. 도입 시 `code_commit`이 "context
  only, never a gate"라는 현 규약과의 정합을 함께 정리할 것. 현재는 config drift + producer/stage
  검사로 실증된 거짓-fresh는 닫았고, 순수 코드 변경은 알고 감수한 한계로 문서화했다.

## Deferred from: code review of 1-6a-churn-model-baseline-lift (2026-07-21, 외부 GPT 리뷰)

- ~~**두 산출물(model+scored)의 실행 단위 원자성 (리뷰 High-1 잔여)**~~ — **해소(1-6b)**: `artifact_id`(모델 바이트
  SHA-256)를 `churn_scored`의 모든 행에 새기고, stage 신선도 게이트가 `identity_is_consistent`로 불일치를 **stale로
  판정해 재실행**한다. crash 창 자체는 남지만 **탐지 불가 → 자동 복구**로 바뀌었다(과장 금지: 창이 사라진 게 아니다).
- ~~**비교 지표의 machine-readable 저장 (리뷰 문서 정직성)**~~ — **해소(1-6b)**: `churn_model.meta.json`에 `metrics`
  블록(baseline/xgb PR-AUC·lift·positive_rate·cv_folds)을 기록. **`artifact_id` 계산에는 넣지 않는다** — 지표는
  정체성의 일부가 아니라 정체성에 딸린 기록이고, 넣으면 같은 모델이 지표만 바뀌어도 다른 id를 갖게 된다.
- **churn_prob calibration (리뷰 Med-6)**: in-sample·미보정 점수임을 문서화했고 순위 신호로만 쓰도록
  제한했다. 진짜 확률이 필요해지면(예: 기대절감액 계산이 확률 해석을 요구하면) OOF calibration을 별도
  스토리로 — 3-2 시뮬레이터 설계 시 확률 vs 순위 요구를 확정할 것.

## Deferred from: code review of 1-4-kmeans-segments-stable-ids (2026-07-21, 외부 GPT 리뷰)

- **AD-1 문구 명확화 — fitted 값 vs 분석가 선택 하이퍼파라미터 (리뷰 조건부 통과)**: `SEGMENT_K=4`는
  `RFM_QUANTILES`(순수 관례)와 달리 **실데이터 곡선(elbow/silhouette)을 보고** 고른 값이라 "데이터
  유래"에 가깝다. 리뷰는 코드 결함으로 보진 않았으나(선택된 모델 하이퍼파라미터를 버전관리하는 건
  일반적 ML 설계) AD-1 문구가 다음을 아키텍처 수준에서 구분하는 편이 안전하다: ①fitted 통계량·경계값
  (분위수 경계·스케일러 상태·인코딩)은 config 하드코딩 **금지** ②분석가가 곡선을 보고 선택해 버전관리하는
  **lane-specific 모델 하이퍼파라미터**(k, 향후 XGBoost 트리 수 등)는 config **허용**. ARCHITECTURE-SPINE
  AD-1 개정 사안이라 스토리 패치가 아닌 별도 정리로 미룬다. 현재는 `SEGMENT_K` 주석이 이 구분을 설명한다.

## Deferred from: code review of 1-2-customer-value-single-definition (2026-07-20)

- ~~**미결 결정 — AD-11 가드의 범위(외부 리뷰 M2)**~~ — **해소(2026-07-20, A안 채택)**: 사용자 결정으로 **"이름 자체를 `value.py`가 소유"**로 확정. **SPEC CAP-5(2차 개정)·ARCHITECTURE-SPINE AD-11에 소급 반영 완료**, 가드는 코드 변경 없이 그대로 유지. 채택 근거: ①B안("데이터 접근 문맥만 금지")은 `df[X]`의 X가 가치 축인지 정적분석으로 판별 불가라 결국 경로 화이트리스트로 근사하게 되고, **가드가 복잡해질수록 이번 리뷰처럼 옆문이 생긴다** ②아래 오탐 사례는 **현 트리에 하나도 실재하지 않는다** — 가정을 위해 실재하는 가드를 약화시키는 건 순서가 거꾸로 ③A안은 코드 변경 0(문구만 개정), B안은 체커 재작성+픽스처 재설계. **감수하는 비용**: 1-3 이후 실소비자가 스키마에서 컬럼명이 필요해질 수 있다. 그때 우선순위는 (1) 가치 축 컬럼을 피처 스키마에서 제외 (2) `value.py`가 좁은 스키마 API 노출 (3) 실사례를 근거로 B안 재검토. 원래 지적된 오탐 사례:
  ```python
  REQUIRED_COLUMNS = ["CLIENTNUM", "Total_Trans_Amt"]   # 스키마 검증
  DTYPES = {"Total_Trans_Amt": "int64"}                 # dtype 카탈로그
  ValueSourceColumn = Literal["Total_Trans_Amt"]        # 타입 선언
  ```
  **1-3 인계**: 위 형태가 실제로 필요해지면 **가드를 고치기 전에** 위 우선순위 (1)→(2)를 먼저 검토할 것. 가드 완화는 마지막 수단이다.

- **`customer_value()` 출력의 재가중 금지는 이 가드가 보장하지 않음(외부 리뷰 Defer)**: 다음은 원천 컬럼을 직접 읽지 않으므로 현 가드를 통과하지만, AD-11이 금지하는 재가중일 수 있다.
  ```python
  value = customer_value(df) * 0.02
  value = np.log1p(customer_value(df))
  ```
  모든 산술을 금지하면 3-1 판정·3-2 기대절감액 계산까지 오탐하므로 **이 체커 하나로 풀 문제가 아니다.** 소비자별 계약 테스트가 적절하다 — sentinel Series를 monkeypatch해 각 소비자가 그 값을 그대로 전달받는지 검증하는 방식.
  - **3-1**: 스케일링이 분면 판정 내부에만 머무는가
  - **3-2**: 기대절감액 공식의 value 입력이 `customer_value()` 출력인가
  - **3-3**: 민감도 변화가 value 정의 자체를 바꾸지 않는가
  - **4-1**: 마트의 원척도 컬럼이 `customer_value()` 결과와 동일한가
