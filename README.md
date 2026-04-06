# trade

한국투자증권 KIS Open API를 이용한 국내 ETF 단타 자동매매 프로그램

## 개요

- 변동성이 큰 국내 ETF를 대상으로 단타 자동매매
- Python 기반
- 한국투자증권 Open API(KIS) 활용

## 기능

| 항목 | 내용 |
|------|------|
| ETF 선정 | 장 시작 후 거래량 × 변동성 점수 상위 5개 자동 선별 |
| 매수 조건 | 5분봉 MA5가 MA20을 상향 돌파(골든 크로스), 또는 RSI ≤ 30 반등 |
| 익절 조건 | 매수 대비 +1.5% 이상 수익 |
| 손절 조건 | 매수 대비 -0.8% 이하 손실 |
| 리스크 관리 | 종목당 최대 투자금 20% 제한 |
| 운영 모드 | 실전투자(real) / 모의투자(paper) 전환 가능 |

## 파일 구조

```
trade/
├── config.py          # 설정 상수 (API 인증 정보, 매매 파라미터)
├── kis_api.py         # KIS Open API 래퍼 (인증·시세·주문)
├── strategy.py        # 기술적 지표 및 매수·매도 신호 로직
├── trader.py          # 메인 트레이딩 루프
├── requirements.txt   # Python 의존성
└── .env.example       # 환경변수 템플릿
```

## 설치 및 실행

### 1. 의존성 설치

```bash
pip install -r requirements.txt
```

### 2. 환경변수 설정

`.env.example`을 복사하여 `.env`로 저장 후 실제 값 입력:

```bash
cp .env.example .env
# .env 파일을 편집하여 API 키, 계좌번호 등 입력
```

```
KIS_APP_KEY=발급받은_앱키
KIS_APP_SECRET=발급받은_앱시크릿
ACCOUNT_NUMBER=계좌번호(숫자8자리)
ACCOUNT_PRODUCT_CODE=01
TRADING_MODE=paper   # paper(모의) 또는 real(실전)
```

> KIS Open API 신청: https://apiportal.koreainvestment.com

### 3. 실행

```bash
python trader.py
```

장 중(09:00~15:20 KST)에만 매매가 실행되며, 장 마감 전 미청산 포지션은 자동 청산됩니다.

## 주요 파라미터 (`config.py`)

| 파라미터 | 기본값 | 설명 |
|----------|--------|------|
| `TOP_N_ETF` | 5 | 선정 ETF 수 |
| `CANDLE_INTERVAL_MINUTES` | 5 | 캔들 주기 (분) |
| `MA_SHORT` | 5 | 단기 이동평균 기간 |
| `MA_LONG` | 20 | 장기 이동평균 기간 |
| `RSI_PERIOD` | 14 | RSI 계산 기간 |
| `RSI_OVERSOLD` | 30 | RSI 과매도 기준 |
| `MAX_POSITION_RATIO` | 0.20 | 종목당 최대 투자 비율 |
| `TAKE_PROFIT_PCT` | 0.015 | 익절 기준 (+1.5%) |
| `STOP_LOSS_PCT` | -0.008 | 손절 기준 (-0.8%) |
| `POLL_INTERVAL_SECONDS` | 60 | 신호 점검 주기 (초) |

## 주의사항

- 본 프로그램은 **교육 및 참고 목적**으로 제공되며, 실제 투자에 의한 손실에 대해 책임지지 않습니다.
- 실전 투자 전 반드시 **모의투자(`TRADING_MODE=paper`)** 로 충분히 테스트하세요.
- KIS Open API 이용 약관을 반드시 확인하고 준수하세요.
