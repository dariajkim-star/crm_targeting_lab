# 파이프라인 다이어그램 — crm-targeting-lab

ARCHITECTURE-SPINE.md의 companion. 데이터 흐름과 **두 데이터셋 격리(AD-1)**·**마트 경계(AD-2)**를 시각화한다.

## 전체 데이터 흐름

```mermaid
flowchart TD
    subgraph src["원천 (gitignore, 재생성 스크립트)"]
        BC[("BankChurners<br/>10,127 고객")]
        OR[("Online Retail II<br/>거래 ~100만 건")]
    end

    subgraph lane_a["A 레인 — 은행 카드고객 (BankChurners 계열)"]
        F1[02_features<br/>RFM 프록시 · 가치 프록시]
        S1[crm/segment<br/>K-means 세그먼트]
        C1[03_train_churn<br/>XGBoost + SHAP]
        M1[crm/campaign<br/>2×2 · 기대절감액 · 민감도]
    end

    subgraph lane_b["B 레인 — 쇼핑몰 LTV 데모 (Online Retail 계열)"]
        L1[04_ltv_demo<br/>BG/NBD + Gamma-Gamma]
    end

    subgraph marts["marts/ — 유일한 BI 계약면 (AD-2)"]
        MC["mart_customers.csv<br/>+ schema.md"]
        ML["mart_ltv_demo.csv<br/>+ schema.md"]
    end

    subgraph bi["Tableau Public (외부 도구, 사용자 실행)"]
        T1[탭1 세그먼트 현황]
        T2[탭2 이탈 위험]
        T3[탭3 타겟팅]
        T4[탭4 LTV 방법론 데모]
    end

    BC --> F1 --> S1 --> C1 --> M1 --> MC
    OR --> L1 --> ML
    MC --> T1 & T2 & T3
    ML --> T4

    lane_a x--x|"AD-1: 결합 금지"| lane_b
```

**읽는 법**: A 레인과 B 레인은 원천부터 마트까지 **한 번도 만나지 않는다**. 두 레인이 만나는 유일한 장소는 Tableau의 서로 다른 탭이며, 그마저도 조인이 아니라 **별도 전시관**이다. 이것이 AD-1(모듈 격리)과 AD-2(마트 2분할)가 함께 강제하는 구조다.

## 단계별 계약 (AD-8: 파일로만 통신)

| 단계 | 입력 | 산출물 | 소유 모듈 |
|---|---|---|---|
| `01_download` | (외부) Kaggle · UCI | `data/bankchurners.parquet`, `data/online_retail.parquet` | — |
| `02_features` | bankchurners | `data/features_customers.parquet` (RFM 프록시·가치 프록시·세그먼트) | `crm/segment` |
| `03_train_churn` | features_customers | `models/churn_model.joblib`, `data/churn_scored.parquet` (확률 + SHAP) | `crm/churn` |
| `04_ltv_demo` | online_retail | `data/ltv_customers.parquet` | `crm/ltv` |
| `05_marts` | churn_scored, ltv_customers | `marts/mart_customers.csv`, `marts/mart_ltv_demo.csv` + 스키마 2종 | `crm/campaign` |

`05_marts`는 두 입력을 읽지만 **각각 자기 마트로만 흘려보낸다** — 조인하지 않는다(AD-2).

## 판정 소유권 경계 (AD-3)

```mermaid
flowchart LR
    PY["Python 파이프라인"] -->|"공식 판정<br/>quadrant_official<br/>target_priority"| MART["marts/*.csv"]
    MART -->|"표시만"| VIEW["Tableau 공식 뷰"]
    MART -->|"임계값 파라미터로<br/>재분류"| SIM["Tableau 시나리오 뷰<br/>('공식 판정 아님' 표기 의무)"]
```

공식 라벨은 Python이 계산해 마트에 고정하고, 대시보드는 그것을 **표시**한다. 임계선을 움직이는 인터랙티브 뷰는 허용하되 시나리오임을 화면에 명시해야 한다 — 어느 것이 공식 결과인지 보는 사람이 헷갈리면 분리한 의미가 사라진다.
