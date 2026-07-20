# Deferred Work — crm-targeting-lab

의도적으로 미룬 항목을 근거와 함께 기록한다(conventions 5항).

## Deferred from: code review of 1-1a-scaffolding-config-structure-guards (2026-07-20)

- ~~**파이프라인 `main(input_paths, output_paths)` 시그니처 존재 검증**~~ — **해소(1-1b)**: `find_pipeline_shape_violations`에 main 부재·시그니처 불일치 검사 추가, 자기검증 픽스처 2건 동반.
- **`pyproject.toml` 도입 시 AD-4 config 가드 충돌 예고** — `.toml`이 금지 확장자라 표준 패키징 파일 도입 순간 오탐. 도입하는 스토리가 `_CONFIG_WHITELIST`에 사유 주석과 함께 등재할 것.
