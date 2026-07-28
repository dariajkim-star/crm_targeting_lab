# crm-targeting-lab (P2)

이탈위험 × 고객가치 **2×2 타겟팅 의사결정 프레임**. 배치 파이프라인이 공식 판정을 데이터마트(CSV)로 고정하고, Tableau Public은 그것을 **표시만** 한다(재계산 금지, AD-3). 공개 데이터(BankChurners)로 "누구를(2×2) → 얼마의 가치가 걸렸고(기대절감) → 누구부터(우선순위) → 그 결론은 가정에 얼마나 민감한가(스윕)"를 끝까지 잇는다.

> **Tableau Public 대시보드**: _(퍼블리시 후 링크 기입 — [절차서](docs/tableau-publish-runbook.md))_
> 게시되면 `marts/mart_customers.csv`의 내용은 공개 조회 가능해진다 — 전 컬럼이 공개 데이터셋 유래·파생값이다(4-4 공개 점검).

## 핵심 수치

전부 커밋된 파이프라인·테스트가 재현하는 값이다(마트는 결정론 — 2회 실행 바이트 동일, NFR4). 이 표는 `marts/mart_customers.schema.md`·`marts/dashboard-spec.md` 검산 앵커와 **동시 갱신 계약**이다.

| 항목 | 값 | 출처 |
|---|---|---|
| 고객 수(마트 행) | **10,127** (전원 보존, null 0) | `marts/mart_customers.csv` |
| 이탈모델 PR-AUC | **0.9508** (baseline 0.6751, lift **+40.8%**, 예측자 8) | `models/churn_model.meta.json` (03 스테이지) |
| 공식 2×2 컷 | risk **0.132753** (0.75분위) · value **3,899** (중위) | `threshold_official_*` 컬럼 |
| 분면 분포 | save_first 443 · watch 2,089 · low_cost_keep 4,624 · accept_churn 2,971 | `quadrant_official` 컬럼 |
| 기대절감 총합 | **≈ 1,454,088** (가정: 성공률 0.30·건당 비용 5.0) | `expected_saving` 컬럼 합 |
| 테스트 | 391 passed (xgboost 미설치 환경, churn 스위트 제외 기준) | `pytest` — 테스트 수는 실행 환경 기준 병기 |

## 발견 (요약)

- **타겟팅은 예산의 함수다**: 랜덤 대비 배수는 100명 접촉 x17.27에서 양수-절감 하한(8,587명) x1.18까지 단조 하락 — 헤드라인은 곡선이지 한 점이 아니다(3-3).
- **결론이 뒤집히는 건 총합이 아니라 분면 구성**: 성공률×비용 그리드 전역에서 총 순가치는 양수 유지, 뒤집히는 것은 분면별 부호와 접촉 비율(20~100%)이다(3-4).
- **점수와 확률은 한 컬럼이 못 한다**: 순위용 `churn_score`(OOF 원점수)와 금액용 `churn_prob_calibrated`(Platt)를 분리 — 혼용 시 총액 +19.0% 부풀림 실측(3-0/3-2).
- **행 순서는 계약이 아니다**: 위치 결합은 무예외로 +37.2% 오합계를 냈다 — CLIENTNUM 라벨 조인만이 방어이며 마트 조립·랭킹 입구·트립와이어 3겹으로 강제된다(함정4, 4-1a/b).

## 한계와 가정 (숨기지 않는 것)

- **두 데이터셋은 결합 불가** — BankChurners(고객 레인)와 Online Retail II(LTV 레인)는 모집단이 달라 레코드 결합이 불가능하며, 파이프라인·마트·대시보드 전 층에서 물리 격리된다(AD-1·AD-2).
- **`Attrition_Flag`는 사후 단면 라벨** — 스냅샷이지 시계열 예측이 아니다. "이탈 확률"은 이 단면의 보정 확률이다.
- **성공률 0.30·건당 비용 5.0은 정책가정** — 실측이 아니며(데이터에 캠페인 로그 없음), 민감도 스윕(3-4)이 가정 구간별 결론 반전을 표로 답한다. 리텐션율은 세그먼트 분해 근거가 없어 단일값이다.
- **통화**: 고객 레인은 무단위(원 데이터에 통화 없음 — 붙이면 날조), LTV 레인은 **GBP**.
- **Epic 2(BG/NBD LTV 데모)는 무기한 동결** — 수행하지 않았다. 대시보드 탭4는 동결 스텁이다.
- **테스트 수는 실행 환경 기준** — xgboost 설치 여부로 churn 스위트 수집이 갈린다(위 표 기준 명시).

## 문서 지도

| 문서 | 내용 |
|---|---|
| [SPEC](docs/specs/spec-crm-targeting-lab/SPEC.md) | 문제 정의·CAP·제약 |
| [아키텍처 스파인](docs/planning-artifacts/architecture/architecture-crm-targeting-lab-2026-07-16/ARCHITECTURE-SPINE.md) | AD-1~13 불변식 |
| [에픽/스토리](docs/planning-artifacts/epics.md) | 요구 분해 |
| [마트 스키마](marts/mart_customers.schema.md) | 컬럼 계약·용도/금지·AD-12 정의 |
| [대시보드 사양서](marts/dashboard-spec.md) | 탭·필드·시나리오 규약(기계 검증됨) |
| [퍼블리시 절차서](docs/tableau-publish-runbook.md) | 워크북 제작~게시 단계 |
| [sprint-status](docs/implementation-artifacts/sprint-status.yaml) | 진행·결정 이력 |

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

`tests/structure/`의 가드가 아키텍처 스파인(AD-1 레인 격리, AD-4 config 단일 출처, AD-8/9 계층·형태)을 기계적으로 강제한다. 규칙별 실스캔 범위는 [structure-guard-coverage.md](docs/implementation-artifacts/structure-guard-coverage.md) 참조. 마트·스키마·사양서·README 수치는 문서-계약 테스트(`tests/marts/`·`tests/docs/`)가 골든값과 대조한다.
