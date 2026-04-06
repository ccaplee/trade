# trade

한국투자증권 KIS Open API를 이용한 **국내 ETF 단타 자동매매** Python 프로그램

---

## 개요

| 항목 | 내용 |
|---|---|
| 대상 | 국내 상장 ETF (레버리지·인버스·섹터 ETF 포함) |
| 전략 | 모멘텀 + RSI 평균회귀 복합 단타 |
| 언어 | Python 3.10+ |
| API | 한국투자증권 KIS Open API (REST) |
| 지원 | 모의투자 / 실계좌 전환 가능 |

---

## 프로젝트 구조

```
trade/
├── main.py          # 진입점 (설정 로드 → 트레이더 실행)
├── kis_api.py       # KIS REST API 클라이언트 (토큰 발급·주문·잔고)
├── strategy.py      # 매매 전략 (모멘텀, RSI, 손익 계산)
├── trader.py        # 포지션·리스크 관리 + 메인 매매 루프
├── config.yaml      # 전략 파라미터 / ETF 유니버스 / 스케줄
├── .env.example     # 환경변수 예시
└── requirements.txt # 의존 패키지
```

---

## 매매 전략

### 진입 (BUY)
| 조건 | 기준값 (config.yaml) |
|---|---|
| 모멘텀 상승 | 최근 N봉 수익률 ≥ `momentum_threshold` (기본 0.3%) |
| RSI 과매도 | RSI ≤ `rsi_oversold` (기본 35) |

두 조건 중 하나라도 충족되면 매수 신호 발생.

### 청산 (SELL)
| 조건 | 기준값 |
|---|---|
| 이익실현 | 수익률 ≥ `take_profit` (기본 0.5%) |
| 손절 | 수익률 ≤ `-stop_loss` (기본 -0.3%) |
| RSI 과매수 | RSI ≥ `rsi_overbought` (기본 65) |

### 리스크 관리
- 동시 최대 보유 종목 수 제한 (`max_positions`)
- 1종목 최대 투자 비중 및 금액 제한 (`position_size`, `max_trade_amount`)
- 일일 누적 손실이 한도 초과 시 자동 거래 중단 (`daily_loss_limit`)
- 장 마감(기본 15:20) 전 전량 청산
- Ctrl+C 종료 시 잔여 포지션 전량 청산

---

## 설치 및 실행

### 1. 패키지 설치

```bash
pip install -r requirements.txt
```

### 2. KIS Open API 신청

1. [KIS Developers](https://apiportal.koreainvestment.com) 접속
2. 앱 등록 후 **App Key / App Secret** 발급
3. 모의투자 또는 실계좌 권한 설정

### 3. 환경변수 설정

`.env.example` 을 복사하여 `.env` 파일을 만들고 값을 채웁니다.

```bash
cp .env.example .env
```

```dotenv
KIS_APP_KEY=발급받은_앱키
KIS_APP_SECRET=발급받은_앱시크릿
KIS_ACCOUNT_NO=12345678-01   # 계좌번호
KIS_IS_MOCK=true             # 모의투자: true | 실계좌: false
```

### 4. 전략 파라미터 조정 (선택)

`config.yaml` 에서 전략, ETF 유니버스, 스케줄을 변경할 수 있습니다.

### 5. 실행

```bash
python main.py
```

실행 로그는 콘솔 및 `trading.log` 파일에 동시 기록됩니다.

---

## 주의 사항

> **⚠️ 투자 손실에 대한 책임은 사용자 본인에게 있습니다.**

- 실계좌 사용 전에 **반드시 모의투자(`KIS_IS_MOCK=true`)로 충분히 테스트**하세요.
- KIS API 호출 건수 제한(초당 20건 등)을 초과하지 않도록 `scan_interval` 을 조정하세요.
- 레버리지·인버스 ETF는 변동성이 크므로 `stop_loss` 를 반드시 설정하세요.
