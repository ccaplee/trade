# trade

한국투자증권 KIS Open API를 이용한 국내 ETF 단타 자동매매 프로그램

## 개요
- 변동성이 큰 국내 ETF를 대상으로 단타 자동매매
- Python 기반 (asyncio + REST/WebSocket)
- 한국투자증권 Open API(KIS) 활용
- RSI, 이동평균, 볼린저 밴드 기반 복합 신호 전략
- 손절/익절 자동 관리 및 장 마감 전 강제 청산

## 프로젝트 구조

```
trade/
├── config/
│   └── config.yaml       # API 키, 계좌정보, 전략 파라미터 설정
├── src/
│   ├── __init__.py
│   ├── kis_api.py         # KIS REST API / WebSocket 클라이언트
│   ├── strategy.py        # 단타 매매 전략 (RSI + MA + 볼린저 밴드)
│   ├── trader.py          # 매매 실행 및 포지션 관리
│   └── utils.py           # 설정 로드, 로깅 등 유틸리티
├── logs/                  # 매매 로그 (자동 생성)
├── main.py                # 진입점
└── requirements.txt
```

## 설치

```bash
pip install -r requirements.txt
```

## 설정

`config/config.yaml`을 열어 아래 항목을 실제 값으로 교체하세요.

```yaml
kis:
  mock: true                         # 모의투자: true | 실투자: false
  mock_app_key: "YOUR_MOCK_APP_KEY"
  mock_app_secret: "YOUR_MOCK_APP_SECRET"
  account_no: "XXXXXXXX"             # 계좌번호 앞 8자리
```

KIS Open API 신청: https://apiportal.koreainvestment.com

## 실행

```bash
python main.py
```

## 매매 전략

### 매수 조건 (아래 4가지 중 2개 이상 충족)
| 조건 | 설명 |
|------|------|
| RSI | RSI ≤ 35 (과매도 구간) |
| 이동평균 | 단기 MA(5) ≥ 장기 MA(20) (상승 추세) |
| 볼린저 밴드 | 현재가 ≤ 볼린저 중간선 (저가 매수) |
| 거래량 | 현재 거래량 ≥ 평균 거래량 × 1.5배 |

### 매도 조건
| 조건 | 설명 |
|------|------|
| 손절 | 수익률 ≤ -1.5% |
| 익절 | 수익률 ≥ +1.0% |
| RSI 과매수 | RSI ≥ 70 |
| 장 마감 | 15:20 이후 강제 청산 |

### 리스크 관리
- 종목당 최대 매수금액: 50만원 (설정 가능)
- 최대 동시 보유 종목: 3개
- 일일 최대 손실 한도: -3%

## 모니터링 종목 (기본값)

| 종목코드 | 이름 |
|---------|------|
| 069500 | KODEX 200 |
| 114800 | KODEX 인버스 |
| 122630 | KODEX 레버리지 |
| 252670 | KODEX 200선물인버스2X |
| 102110 | TIGER 200 |
| 367380 | KODEX 미국나스닥100 |
| 233740 | KODEX 코스닥150 레버리지 |

## 주의사항

> ⚠️ **이 프로그램은 교육 및 참고 목적으로 제공됩니다.**
> 실투자 사용 시 발생하는 손실에 대해 책임지지 않습니다.
> 반드시 모의투자(`mock: true`)로 충분히 검증 후 실투자에 적용하세요.
