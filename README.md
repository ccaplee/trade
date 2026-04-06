# trade

한국투자증권 KIS Open API를 이용한 국내 ETF 단타 자동매매 프로그램

## 개요
- 변동성이 큰 국내 ETF를 대상으로 단타 자동매매
- Python 기반
- 한국투자증권 Open API(KIS) 활용

## 파일 구조

| 파일 | 역할 |
|---|---|
| `config.py` | API 키, 계좌번호, 전략 파라미터 설정 |
| `kis_api.py` | KIS REST API 연동 (인증, 시세, 주문, 잔고) |
| `trader.py` | ETF 선정, 매수/매도 신호, 리스크 관리 |
| `main.py` | 진입점 – 스케줄러, 장 시간 체크, 종료 처리 |
| `requirements.txt` | Python 의존 패키지 |

## 전략

### ETF 선정
장 시작 후 `ETF_UNIVERSE` 내 종목의 거래량 × 변동성 점수를 계산하여 상위 5개를 자동 선별합니다.

### 매수 조건 (둘 중 하나 충족 시)
1. **골든크로스** – 5분봉 MA5 가 MA20 을 상향 돌파
2. **RSI 반등** – RSI(14)가 30 이하에서 30 초과로 반등

### 매도 조건
- **익절**: 매수 평균가 대비 +1.5% 이상
- **손절**: 매수 평균가 대비 -0.8% 이하
- **장 마감**: 15:20 도달 시 전체 청산

### 리스크 관리
- 종목당 최대 투자금: 주문 가능 잔고의 20%
- 동시 최대 보유 종목: 3개

## 설치 및 실행

```bash
# 1. 의존 패키지 설치
pip install -r requirements.txt

# 2. 환경변수로 API 인증정보 설정 (또는 config.py 직접 수정)
export KIS_APP_KEY="YOUR_APP_KEY"
export KIS_APP_SECRET="YOUR_APP_SECRET"
export KIS_CANO="12345678"          # 계좌번호 앞 8자리
export KIS_ACNT_PRDT_CD="01"        # 계좌 상품코드

# 모의투자 (기본값) – 실전 시 BASE_URL 변경
export KIS_BASE_URL="https://openapivts.koreainvestment.com:9443"

# 3. 실행
python main.py
```

## 주요 설정 (`config.py`)

| 파라미터 | 기본값 | 설명 |
|---|---|---|
| `TOP_N_ETF` | 5 | 선별할 ETF 수 |
| `MA_SHORT` / `MA_LONG` | 5 / 20 | 이동평균 기간 (5분봉 캔들 수) |
| `RSI_PERIOD` | 14 | RSI 계산 기간 |
| `RSI_OVERSOLD` | 30 | RSI 과매도 임계값 |
| `TAKE_PROFIT_RATE` | 0.015 | 익절 수익률 (1.5%) |
| `STOP_LOSS_RATE` | 0.008 | 손절 손실률 (0.8%) |
| `MAX_POSITION_RATIO` | 0.20 | 종목당 최대 투자 비율 (20%) |
| `MAX_POSITIONS` | 3 | 동시 최대 보유 종목 수 |
| `POLL_INTERVAL_SEC` | 30 | 신호 체크 주기 (초) |

## 주의사항
- **모의투자 환경에서 충분히 테스트한 후 실전 투자에 사용하세요.**
- API 키와 계좌번호는 절대 소스코드에 하드코딩하여 공개 저장소에 올리지 마세요.
- 자동매매는 시장 상황에 따라 예상치 못한 손실이 발생할 수 있습니다.
