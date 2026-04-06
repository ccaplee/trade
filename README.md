# trade

한국투자증권 KIS Open API를 이용한 국내 ETF 단타 자동매매 프로그램

## 개요
- 변동성이 큰 국내 ETF를 대상으로 단타 자동매매
- Python 기반
- 한국투자증권 Open API(KIS) 활용

## 파일 구조

```
trade/
├── main.py            # 진입점
├── config.py          # API 인증 정보 및 매매 파라미터
├── kis_api.py         # KIS REST API 래퍼 (인증, 시세, 주문)
├── etf_selector.py    # 장 시작 후 거래량·변동성 기준 ETF 상위 N개 선별
├── strategy.py        # 매수/매도 신호 계산 (MA 골든크로스, RSI, 익절/손절)
├── trader.py          # 메인 트레이딩 루프
├── requirements.txt   # Python 패키지 의존성
└── .env.example       # 환경변수 예시 (실제 .env 파일은 Git에 포함 안 됨)
```

## 전략 요약

| 구분 | 조건 |
|------|------|
| ETF 선별 | 장 시작 후 거래량 순위 API에서 유니버스 내 변동성·거래량 상위 5개 자동 선별 |
| 매수 신호 | ① 5분봉 MA5 가 MA20 을 상향 돌파 (골든크로스) **OR** ② RSI(14)가 30 이하에서 반등 |
| 익절 | 매수 평균가 대비 **+1.5%** 도달 시 시장가 매도 |
| 손절 | 매수 평균가 대비 **-1.0%** 도달 시 시장가 매도 |
| 장 종료 | 15:20 이후 보유 종목 전체 강제 청산 |

## 빠른 시작

### 1. 환경 설정

```bash
pip install -r requirements.txt
cp .env.example .env
# .env 파일을 열어 KIS API 키와 계좌번호를 입력하세요.
```

### 2. .env 파일 예시

```
KIS_APP_KEY=your_app_key_here
KIS_APP_SECRET=your_app_secret_here
KIS_ACCOUNT_NO=12345678-01
KIS_IS_PAPER=true    # 모의투자: true / 실전투자: false
```

> KIS Open API 신청: https://apiportal.koreainvestment.com

### 3. 실행

```bash
python main.py
```

로그는 콘솔과 `trade.log` 파일에 동시에 기록됩니다.

## 매매 파라미터 커스터마이징

`config.py` 에서 아래 값을 조정할 수 있습니다.

| 파라미터 | 기본값 | 설명 |
|----------|--------|------|
| `TOP_N` | 5 | 선별할 ETF 수 |
| `MA_SHORT` | 5 | 단기 이동평균 기간 (봉 수) |
| `MA_LONG` | 20 | 장기 이동평균 기간 (봉 수) |
| `RSI_PERIOD` | 14 | RSI 계산 기간 |
| `RSI_OVERSOLD` | 30 | RSI 과매도 기준값 |
| `TAKE_PROFIT_PCT` | 1.5 | 익절 목표 수익률 (%) |
| `STOP_LOSS_PCT` | 1.0 | 손절 기준 수익률 (%) |
| `ORDER_QUANTITY` | 1 | 1회 주문 수량 (주) |
| `CANDLE_INTERVAL_MIN` | 5 | 분봉 단위 |
| `LOOP_INTERVAL_SEC` | 30 | 전략 루프 주기 (초) |
| `ETF_UNIVERSE` | 15개 | 매매 대상 ETF 풀 (티커 목록) |

## 주의사항

- **모의투자(`KIS_IS_PAPER=true`)로 충분히 검증 후 실전 투자로 전환하세요.**
- 자동매매는 손실 위험이 있습니다. 투자는 본인 책임입니다.
- `ORDER_QUANTITY` 를 너무 크게 설정하면 주문 금액이 커질 수 있으니 주의하세요.
- KIS API 요청 한도(초당/일별)를 초과하지 않도록 `LOOP_INTERVAL_SEC` 를 적절히 설정하세요.
