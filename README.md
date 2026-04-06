# trade

한국투자증권 KIS Open API를 이용한 국내 ETF 단타 자동매매 프로그램

## 개요

- 변동성이 큰 국내 ETF를 대상으로 단타 자동매매
- Python 기반 (3.11+)
- 한국투자증권 Open API(KIS) 활용
- 실전투자 / 모의투자 모두 지원

## 프로젝트 구조

```
trade/
├── main.py                        # 프로그램 진입점
├── requirements.txt
├── .env.example                   # 환경변수 템플릿
└── kis_etf_trader/
    ├── config.py                  # 설정 (환경변수, 매매 파라미터)
    ├── logger.py                  # 로깅 설정
    ├── api_client.py              # KIS API HTTP 클라이언트
    ├── etf_selector.py            # ETF 자동 선별
    ├── indicators.py              # 기술적 지표 (MA, RSI)
    ├── risk_manager.py            # 포지션 및 리스크 관리
    ├── strategy.py                # 매매 전략 (신호 생성)
    └── trader.py                  # 메인 트레이딩 루프
```

## 매매 전략

### ETF 선별
- 장 시작 9시 5분 이후, 10분마다 자동 갱신
- 거래량 순위 + 등락률 순위를 복합 점수로 계산하여 상위 5개 ETF 선별

### 매수 조건 (둘 중 하나 충족 시)
1. **골든 크로스**: 5분봉 MA5가 MA20을 상향 돌파
2. **RSI 반등**: RSI가 30 이하로 진입 후 30 초과로 반등

### 매도 조건
- **익절**: 매수 평균 단가 대비 +1.5% 이상 수익
- **손절**: 매수 평균 단가 대비 -0.8% 이상 손실
- **마감 청산**: 장 마감 5분 전(15:25) 전량 청산

### 리스크 관리
- 최대 동시 보유 종목: 5개
- 종목당 매수 금액: 10만 원 (설정 가능)
- 매수 수량 = `BUY_AMOUNT ÷ 현재가` (정수 절사)

## 설치 및 실행

### 1. 패키지 설치

```bash
pip install -r requirements.txt
```

### 2. 환경변수 설정

```bash
cp .env.example .env
# .env 파일을 열어 APP_KEY, APP_SECRET, CANO 등을 실제 값으로 수정
```

| 변수 | 설명 | 기본값 |
|---|---|---|
| `APP_KEY` | KIS API 앱 키 | (필수) |
| `APP_SECRET` | KIS API 앱 시크릿 | (필수) |
| `CANO` | 계좌번호 8자리 | (필수) |
| `ACNT_PRDT_CD` | 계좌 상품 코드 | `01` |
| `IS_REAL` | `true`: 실전, `false`: 모의 | `false` |
| `MAX_POSITIONS` | 최대 동시 보유 종목 수 | `5` |
| `BUY_AMOUNT` | 종목당 매수 금액 (원) | `100000` |
| `TAKE_PROFIT_PCT` | 익절 기준 (%) | `1.5` |
| `STOP_LOSS_PCT` | 손절 기준 (%) | `0.8` |

### 3. 실행

```bash
python main.py
```

로그는 콘솔과 `logs/` 디렉터리에 날짜별로 저장됩니다.

## 주의사항

- **모의투자에서 충분히 테스트한 후 실전 전환을 권장합니다.**
- KIS Open API는 [한국투자증권 홈페이지](https://apiportal.koreainvestment.com/)에서 신청합니다.
- 초단타 매매 특성상 수수료·슬리피지를 반드시 고려하세요.
- 본 프로그램은 투자 손실에 대한 책임을 지지 않습니다.
