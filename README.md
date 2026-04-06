# trade

한국투자증권 KIS Open API를 이용한 국내 ETF 단타 자동매매 프로그램

## 개요
- 변동성이 큰 국내 ETF를 대상으로 단타 자동매매
- Python 기반
- 한국투자증권 Open API(KIS) 활용

## 주요 기능

| 기능 | 설명 |
|------|------|
| ETF 자동 선별 | 장 시작 10분 후, 거래량·등락률 순위를 결합해 상위 5개 ETF를 자동 선별 |
| 매수 신호 | 5분봉 MA5가 MA20을 상향 돌파(골든크로스) 또는 RSI ≤ 30 과매도 반등 시 |
| 익절 | 매수 후 **+1.5%** 이상 수익 시 시장가 매도 |
| 손절 | 매수 후 **-0.8%** 이하 손실 시 시장가 매도 |
| 장 종료 청산 | 15:20 이전 보유 중인 모든 포지션을 자동 청산 |

## 파일 구조

```
trade/
├── main.py           # 진입점 – 메인 루프
├── config.py         # API 키, 매매 파라미터 설정
├── kis_api.py        # KIS REST API 래퍼 (인증, 시세, 주문)
├── etf_selector.py   # 상위 ETF 자동 선별
├── strategy.py       # 매매 전략 (MA 교차, RSI)
├── trader.py         # 주문 실행 & 포지션 관리
├── requirements.txt  # 의존 패키지
└── .env.example      # 환경변수 예시
```

## 설치 및 실행

### 1. 의존 패키지 설치

```bash
pip install -r requirements.txt
```

### 2. 환경변수 설정

```bash
cp .env.example .env
# .env 파일을 열어 실제 KIS API 키와 계좌 정보를 입력
```

`.env` 파일 예시:

```
KIS_APP_KEY=발급받은_앱키
KIS_APP_SECRET=발급받은_시크릿키
KIS_CANO=계좌번호8자리
KIS_ACNT_PRDT_CD=01
KIS_PAPER_TRADING=true   # 모의투자는 true, 실전은 false
```

> **KIS Open API 키 발급**: [한국투자증권 개발자센터](https://apiportal.koreainvestment.com) 에서 앱 등록 후 발급

### 3. 실행

```bash
python main.py
```

## 파라미터 조정

`config.py` 에서 주요 매매 파라미터를 변경할 수 있습니다.

| 변수 | 기본값 | 설명 |
|------|--------|------|
| `ETF_CANDIDATE_COUNT` | 5 | 감시할 ETF 개수 |
| `CANDLE_INTERVAL` | `"5"` | 분봉 단위 (분) |
| `MA_SHORT` | 5 | 단기 이동평균 기간 |
| `MA_LONG` | 20 | 장기 이동평균 기간 |
| `RSI_PERIOD` | 14 | RSI 계산 기간 |
| `RSI_OVERSOLD` | 30.0 | RSI 과매도 기준값 |
| `PROFIT_TAKE_PCT` | 1.5 | 익절 수익률 (%) |
| `STOP_LOSS_PCT` | 0.8 | 손절 손실률 (%) |
| `ORDER_AMOUNT_KRW` | 500,000 | 종목당 주문 금액 (원) |
| `SCAN_START_OFFSET_MIN` | 10 | 장 시작 후 ETF 스캔 시작까지 대기 시간 (분) |
| `LOOP_INTERVAL_SEC` | 30 | 메인 루프 주기 (초) |

## 주의사항

- **모의투자로 충분히 테스트한 후 실전 전환**을 권장합니다.
- 본 프로그램은 교육·참고 목적으로 제공되며, 투자 손실에 대한 책임은 사용자 본인에게 있습니다.
- KIS Open API 호출 제한(초당 20건 등)을 준수하도록 설계되어 있으나, API 정책 변경 시 `kis_api.py`를 조정하세요.
