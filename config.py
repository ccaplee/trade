"""
config.py
─────────
환경변수 및 매매 전략 파라미터를 한곳에서 관리합니다.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── KIS API 인증 ────────────────────────────────────────────────────────────────
APP_KEY: str = os.environ["KIS_APP_KEY"]
APP_SECRET: str = os.environ["KIS_APP_SECRET"]
ACCOUNT_NO: str = os.environ["KIS_ACCOUNT_NO"]      # 8자리 계좌번호
ACCOUNT_PRODUCT: str = os.environ.get("KIS_ACCOUNT_PRODUCT", "01")

ENV: str = os.environ.get("KIS_ENV", "paper")       # "real" or "paper"

# 실전 / 모의 URL 분기
REAL_URL = "https://openapi.koreainvestment.com:9443"
PAPER_URL = "https://openapivts.koreainvestment.com:29443"
BASE_URL: str = REAL_URL if ENV == "real" else PAPER_URL

# ── 매매 대상 ETF 종목 코드 ────────────────────────────────────────────────────
# KODEX200 / KODEX레버리지 / KODEX인버스2X / TIGER200 / KODEX코스닥150레버리지
ETF_SYMBOLS: list[str] = [
    "069500",  # KODEX 200
    "122630",  # KODEX 레버리지
    "252670",  # KODEX 200선물인버스2X
    "360750",  # TIGER 미국S&P500
    "233740",  # KODEX 코스닥150 레버리지
]

# ── 전략 파라미터 ────────────────────────────────────────────────────────────────
TAKE_PROFIT_PCT: float = 0.8    # 목표 수익률 (%)
STOP_LOSS_PCT: float = 0.5      # 손절 비율 (%)
MAX_POSITION_PCT: float = 20.0  # 종목당 최대 투자 비중 (계좌 대비 %)
ORDER_QTY: int = 1              # 1회 주문 수량 (주); 0 이면 예수금 비중 자동 계산

RSI_PERIOD: int = 14            # RSI 계산 기간
RSI_BUY_THRESHOLD: float = 30.0  # RSI ≤ 이 값이면 매수 신호
RSI_SELL_THRESHOLD: float = 70.0 # RSI ≥ 이 값이면 매도 신호

SHORT_MA: int = 5               # 단기 이동평균선 기간 (분봉)
LONG_MA: int = 20               # 장기 이동평균선 기간 (분봉)

# ── 스케줄 ───────────────────────────────────────────────────────────────────────
LOOP_INTERVAL_SEC: int = 60     # 매매 루프 주기 (초)

# 장 운영 시간 (KST, 24h 표현)
MARKET_OPEN_TIME: str = "09:00"
MARKET_CLOSE_TIME: str = "15:20"  # 15:20 이후 신규 진입 금지
FORCE_SELL_TIME: str = "15:25"    # 미청산 포지션 강제 청산 시각
