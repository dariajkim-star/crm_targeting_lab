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

## Deferred from: code review of 1-2-customer-value-single-definition (2026-07-20)

- **🔵 미결 결정 — AD-11 가드의 범위(외부 리뷰 M2)**: 현재 가드는 `Total_Trans_Amt`라는 **이름의 언급 자체**를 금지한다. 이는 "재계산 금지"보다 강한 규칙이라, 다음 같은 **정당한 메타데이터도 위반으로 잡는다**:
  ```python
  REQUIRED_COLUMNS = ["CLIENTNUM", "Total_Trans_Amt"]   # 스키마 검증
  DTYPES = {"Total_Trans_Amt": "int64"}                 # dtype 카탈로그
  ValueSourceColumn = Literal["Total_Trans_Amt"]        # 타입 선언
  ```
  두 선택지 중 하나를 **명시적으로 골라야 한다**:
  - **A안**: 이름 자체를 `value.py` 소유로 확정 → 현 가드 유지 + **AD-11 원문에 "원천 컬럼의 스키마 이름도 value.py가 소유한다"를 소급 추가**(M1·CAP-5 선례와 동일 패턴). 하위 스토리가 스키마를 다루려면 `value.py`가 노출하는 심볼을 경유.
  - **B안**: 데이터 접근 문맥으로 가드를 좁힘 → AD-11 원문 유지, 대신 판별이 정적분석으로 애매해지고 우회면이 넓어짐.

  **1-3(02_features)이 첫 실소비자**이므로 그 스토리가 스키마를 실제로 어떻게 다루는지 보고 결정하는 편이 근거가 확실하다. **그때까지 이 항목은 열려 있다** — 현 가드는 A안 쪽으로 기울어 있으나 스펙이 아직 그렇게 말하지 않는다.

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
