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
