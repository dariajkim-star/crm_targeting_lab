# crm-targeting-lab (P2)

이탈위험 × 고객가치 2×2 타겟팅 의사결정 프레임. 배치 파이프라인이 데이터마트(CSV)를 만들고, Tableau Public이 그것을 표시한다. 문서 지도: [SPEC](docs/specs/spec-crm-targeting-lab/SPEC.md) · [아키텍처 스파인](docs/planning-artifacts/architecture/architecture-crm-targeting-lab-2026-07-16/ARCHITECTURE-SPINE.md) · [에픽/스토리](docs/planning-artifacts/epics.md)

> 진행 중 — **Epic 1(고객 이해 + 이탈 위험) 완료**. 현재 상태: 테스트 267개, RFM 세그먼트 4종 + 페르소나,
> XGBoost 이탈위험 분류 PR-AUC 0.956(baseline 대비 +37.6%), SHAP 요인→리텐션 액션 매핑, 학습 아티팩트
> 정체성 고정(AD-5). 다음은 Epic 2(LTV 확률 모델 데모) → Epic 3(2×2 타겟팅 + 캠페인 시뮬레이터).
> README 본편(핵심 수치·발견·한계)은 4-4에서 작성된다.

## 셋업

```
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt   # core 블록만 설치됨
.venv/Scripts/python.exe -m pytest                            # 구조 가드 포함 전체 테스트
```

requirements.txt의 모델링 블록(scikit-learn·xgboost·shap·pymc-marketing)은 주석 상태다 — 처음 필요로 하는 스토리가 설치한다.

## 데이터 확보 (스토리 1-1b)

원천 데이터는 gitignore 대상이며 아래 스크립트로 재생성한다(NFR5):

```
.venv/Scripts/python.exe pipelines/01_download.py
```

> `python -m pipelines.01_download`은 **동작하지 않는다** — 모듈명이 숫자로 시작해 유효한 파이썬 식별자가 아니다. 반드시 파일 경로로 실행할 것.

| 산출물 | 원천 | 행수 | 비고 |
|---|---|---|---|
| `data/bankchurners.parquet` | Kaggle [`sakshigoyal7/credit-card-customers`](https://www.kaggle.com/datasets/sakshigoyal7/credit-card-customers) | 10,127 | 이탈 레인. `Attrition_Flag`는 사후 단면 라벨(시계열 예측 아님) |
| `data/online_retail.parquet` | Kaggle [`mashlyn/online-retail-ii-uci`](https://www.kaggle.com/datasets/mashlyn/online-retail-ii-uci) (UCI id 502 미러) | 1,067,371 | LTV 데모 레인. 통화 **GBP** |

- kagglehub **익명 다운로드** — Kaggle 계정·API 키 불필요(P1에서 검증된 경로).
- 두 데이터셋은 **레코드 결합 불가**(모집단이 다름) — 파이프라인 전체에서 물리적으로 격리된다(AD-1).
- 원본을 **그대로** 저장한다. 컬럼 선택·필터링은 후속 단계(1-3) 소관.
- 각 산출물 옆의 `.meta.json`(입력 해시·config_hash·커밋·행수)이 신선도 계약(AD-13)이다 — 후속 단계는 이것을 검증하고, stale하면 실행을 거부한다.

**수동 폴백** (kagglehub 실패 시): 위 Kaggle 링크에서 CSV를 직접 내려받은 뒤:

```
.venv/Scripts/python.exe -c "from pathlib import Path; from crm.common.acquisition import store_csv_as_parquet; from crm import config; config.ensure_output_dirs(); store_csv_as_parquet(Path('<받은 BankChurners.csv 경로>'), config.DATA_DIR / 'bankchurners.parquet')"
```

(Online Retail II도 동일하게 `online_retail.parquet`으로.)

## 구조 규약

`tests/structure/`의 가드가 아키텍처 스파인(AD-1 레인 격리, AD-4 config 단일 출처, AD-8/9 계층·형태)을 기계적으로 강제한다. 규칙별 실스캔 범위는 [structure-guard-coverage.md](docs/implementation-artifacts/structure-guard-coverage.md) 참조.
