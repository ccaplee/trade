# trade

한국투자증권 KIS Open API를 이용한 국내 ETF 단타 자동매매 프로그램

## 개요
- 변동성이 큰 국내 ETF를 대상으로 단타(당일 매매) 자동 실행
- Python 기반
- 한국투자증권 Open API(KIS) 활용

## 프로젝트 구조

```
trade/
├── main.py                 # 실행 진입점
├── requirements.txt        # Python 패키지 목록
├── .env.example            # 환경변수 예시 (실제 키는 .env 파일에 입력)
└── src/
    ├── kis_auth.py         # OAuth2 인증 및 토큰 관리
    ├── kis_api.py          # KIS Open API 호출 래퍼
    ├── etf_screener.py     # ETF 스크리너 (상위 5개 자동 선별)
    ├── strategy.py         # 단타 매매 전략 (변동성 돌파)
    ├── trader.py           # 메인 트레이더 (루프, 주문, 리포트)
    └── utils.py            # 로깅 및 공통 유틸리티
```

## 설치 방법

```bash
pip install -r requirements.txt
```

## 설정 방법

```bash
cp .env.example .env
```

`.env` 파일을 열고 아래 항목을 입력합니다.

| 항목 | 설명 |
|---|---|
| `KIS_APP_KEY` | KIS Open API App Key |
| `KIS_APP_SECRET` | KIS Open API App Secret |
| `KIS_ACCOUNT_NO` | 계좌번호 (예: `50123456-01`) |
| `KIS_IS_REAL` | `true` = 실전투자, `false` = 모의투자 |

> **주의**: KIS Open API 키는 [KIS Developers](https://apiportal.koreainvestment.com) 에서 발급받을 수 있습니다.

## 실행 방법

```bash
python main.py
# 또는 로그 파일 저장
python main.py --log-level DEBUG --log-file logs/trade.log
```

## 매매 전략

### ETF 선별 (EtfScreener)

장 시작 후 **10분 뒤** 거래량 순위 API를 호출하여 ETF를 자동으로 필터링합니다.

```
점수 = 거래량(정규화) × 0.5 + 당일변동성(정규화) × 0.5
```

- 상위 5개 ETF를 선별하여 매매 대상으로 설정

### 매수 조건 (변동성 돌파)

```
목표가 = 시가 + (전일 고가 - 전일 저가) × k  (k = 0.5)
현재가 >= 목표가  →  시장가 매수
```

### 매도 조건

| 조건 | 기준 |
|---|---|
| 익절 | 매수가 대비 **+1.0%** 도달 |
| 손절 | 매수가 대비 **-0.5%** 하락 |
| 강제 청산 | 오후 **15:20** 이전 전량 시장가 매도 |
| 일일 손실 한도 | 초기 자산 대비 **-3.0%** 손실 시 전량 청산 후 거래 중단 |

### 리스크 관리

- 종목당 최대 투자 비율: 총 자산의 **20%**
- 동시 최대 보유 종목 수: **5개**
- 모의투자 환경에서 충분히 테스트 후 실전 전환 권장

## 주의사항

- 본 프로그램은 **참고용**이며, 실제 투자 손익에 대한 책임은 사용자 본인에게 있습니다.
- 반드시 **모의투자** (`KIS_IS_REAL=false`) 로 충분히 테스트한 후 실전 투자에 사용하세요.
- KIS Open API 이용 약관 및 정책을 준수하여 사용하세요.
