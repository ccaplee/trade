"""
KIS Open API 설정 파일
환경변수 또는 .env 파일에서 설정값을 로드합니다.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── KIS API 인증 정보 ──────────────────────────────────────────────────────────
APP_KEY: str = os.environ["KIS_APP_KEY"]
APP_SECRET: str = os.environ["KIS_APP_SECRET"]
CANO: str = os.environ["KIS_CANO"]          # 계좌번호 앞 8자리
ACNT_PRDT_CD: str = os.environ.get("KIS_ACNT_PRDT_CD", "01")  # 계좌상품코드

# 모의투자 여부 (True: 모의, False: 실전)
IS_PAPER_TRADING: bool = os.environ.get("KIS_PAPER_TRADING", "true").lower() == "true"

if IS_PAPER_TRADING:
    BASE_URL = "https://openapivts.koreainvestment.com:29443"
else:
    BASE_URL = "https://openapi.koreainvestment.com:9443"

# ── 매매 파라미터 ──────────────────────────────────────────────────────────────
# ETF 후보 풀 (장 시작 후 거래량·변동성 상위 N개를 동적으로 선별)
ETF_CANDIDATE_COUNT: int = 5          # 선별할 ETF 개수
CANDLE_INTERVAL: str = "5"            # 분봉 단위 (5분)

MA_SHORT: int = 5                     # 단기 이동평균 기간
MA_LONG: int = 20                     # 장기 이동평균 기간
RSI_PERIOD: int = 14                  # RSI 기간
RSI_OVERSOLD: float = 30.0            # RSI 과매도 임계값

PROFIT_TAKE_PCT: float = 1.5          # 익절 수익률 (%)
STOP_LOSS_PCT: float = 0.8            # 손절 손실률 (%)

ORDER_AMOUNT_KRW: int = 500_000       # 종목당 주문 금액 (원)

# ── 스케줄 ────────────────────────────────────────────────────────────────────
MARKET_OPEN: str = "09:00"            # 장 시작 시각
MARKET_CLOSE: str = "15:20"          # 장 종료 전 청산 시각
SCAN_START_OFFSET_MIN: int = 10       # 장 시작 후 N분 뒤부터 ETF 스캔
LOOP_INTERVAL_SEC: int = 30           # 메인 루프 주기 (초)
