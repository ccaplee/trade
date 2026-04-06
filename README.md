# trade

한국투자증권 KIS Open API를 이용한 국내 ETF 단타 자동매매 Python 프로그램

---

## 개요

| 항목 | 내용 |
|------|------|
| 언어 | Python 3.11+ |
| API | 한국투자증권 KIS Open API (실전 / 모의 지원) |
| 전략 | RSI + 이동평균 교차 기반 단타 (익절·손절 자동 적용) |
| 실행 단위 | 매 60 초 (설정 변경 가능) |

---

## 파일 구조

```
trade/
├── .env.example      # 환경변수 템플릿 (복사 후 .env 로 사용)
├── config.py         # API 인증 정보 및 전략 파라미터
├── kis_api.py        # KIS Open API 클라이언트 (토큰·주문·잔고·차트)
├── strategy.py       # 단타 전략 (RSI + MA 교차, 익절/손절)
├── trader.py         # 메인 자동매매 루프
├── utils.py          # 로깅, 장 운영 시간 유틸
└── requirements.txt  # 의존 패키지
```

---

## 설치

```bash
pip install -r requirements.txt
```

---

## 환경 변수 설정

```bash
cp .env.example .env
```

`.env` 파일을 열고 아래 항목을 채워 넣습니다.

| 변수 | 설명 |
|------|------|
| `KIS_APP_KEY` | KIS Open API App Key |
| `KIS_APP_SECRET` | KIS Open API App Secret |
| `KIS_ACCOUNT_NO` | 계좌번호 앞 8자리 |
| `KIS_ACCOUNT_PRODUCT` | 상품코드 (일반 위탁: `01`) |
| `KIS_ENV` | `paper` (모의) 또는 `real` (실전) |

> ⚠️ `.env` 파일은 절대 저장소에 커밋하지 마세요.

---

## 전략 파라미터 (`config.py`)

| 파라미터 | 기본값 | 설명 |
|----------|--------|------|
| `ETF_SYMBOLS` | 5개 종목 | 매매 대상 ETF 종목코드 |
| `TAKE_PROFIT_PCT` | `0.8` % | 익절 목표 수익률 |
| `STOP_LOSS_PCT` | `0.5` % | 손절 허용 손실률 |
| `MAX_POSITION_PCT` | `20.0` % | 종목당 최대 투자 비중 |
| `ORDER_QTY` | `1` | 1회 주문 수량 (`0` = 자동 계산) |
| `RSI_PERIOD` | `14` | RSI 계산 기간 |
| `RSI_BUY_THRESHOLD` | `30.0` | 매수 RSI 기준 |
| `RSI_SELL_THRESHOLD` | `70.0` | 매도 RSI 기준 |
| `SHORT_MA` | `5` | 단기 이동평균 기간 (분봉) |
| `LONG_MA` | `20` | 장기 이동평균 기간 (분봉) |
| `LOOP_INTERVAL_SEC` | `60` | 매매 루프 주기 (초) |

---

## 매매 전략 상세

### 매수 조건 (두 조건 모두 충족)
1. RSI ≤ `RSI_BUY_THRESHOLD` (과매도 구간)
2. 단기 이동평균 > 장기 이동평균 (골든크로스)

### 매도 조건 (하나라도 충족)
- 수익률 ≥ `TAKE_PROFIT_PCT` % → 익절
- 수익률 ≤ `-STOP_LOSS_PCT` % → 손절
- RSI ≥ `RSI_SELL_THRESHOLD` (과매수 구간)
- 단기 이동평균 < 장기 이동평균 (데드크로스)

### 장 마감 자동 청산
- `FORCE_SELL_TIME` (기본 15:25) 도달 시 미청산 포지션 전량 시장가 매도

---

## 실행

```bash
python trader.py
```

로그는 콘솔과 `trader.log` 파일에 동시에 기록됩니다.

---

## 주의사항

- 이 프로그램은 실제 투자 손실을 유발할 수 있습니다.
- 반드시 **모의투자 환경** (`KIS_ENV=paper`) 에서 충분히 테스트한 후 실전에 적용하세요.
- 한국투자증권 KIS Open API 이용 약관을 준수해야 합니다.
