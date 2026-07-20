# Stack — crm-targeting-lab

## 기술 스택

Python 3.12 · pandas 3.x · scikit-learn 1.9.x · **XGBoost 3.3.x** · **SHAP 0.52.x** · **pymc-marketing 0.19.4**(BG/NBD·Gamma-Gamma — `lifetimes`는 discontinued 확인 후 공식 후속으로 교체, 적합 실패 시 코호트 기반 단순 LTV 폴백) · Tableau Public · pytest 9.x

버전은 2026-07-16 웹 검증. 상세·근거는 아키텍처 스파인의 Stack 표.

P1과 공유: .venv 격리, pytest 관례, 시드 고정. P1과 다름: FastAPI/Streamlit 없음(배치 분석 + BI가 소비층).

## 데이터 소스 (둘 다 공개, gitignore + 재생성 스크립트)

| 용도 | 데이터셋 | 규모 | 핵심 필드 | 비고 |
|---|---|---|---|---|
| 이탈 | Kaggle **Credit Card Customers (BankChurners)** | 10,127건 | `Attrition_Flag`(~16%), 인구통계, `Total_Trans_Amt/Ct`, `Total_Revolving_Bal`, `Credit_Limit`, `Months_Inactive` 등 | 카드 도메인 — 금융권 어필. 사후 스냅샷 라벨(OQ-2) |
| LTV | UCI **Online Retail II** | 거래 ~100만 건 | Invoice, StockCode, Quantity, Price(GBP), Customer ID, InvoiceDate | BG/NBD가 요구하는 거래 로그. 통화 GBP |

**레코드 결합 불가** — 서로 다른 모집단. 우회 방식은 SPEC OQ-1.

## 디렉토리 (예정 — P1 관례 미러)

```
crm-targeting-lab/
  data/                  # gitignore, 재생성 스크립트
  pipelines/             # 다운로드·features·train·simulate
  crm/                   # 계산 모듈 (rfm, churn, ltv, campaign)
  marts/                 # Tableau용 최종 데이터마트 CSV + 스키마 문서
  tests/
  docs/{specs, planning-artifacts, implementation-artifacts}
```
