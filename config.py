"""
KIS Open API 설정 및 매매 파라미터
환경변수 또는 .env 파일로 관리하는 것을 권장합니다.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── KIS API 인증 정보 ──────────────────────────────────────────────────────────
APP_KEY: str = os.environ.get("KIS_APP_KEY", "")
APP_SECRET: str = os.environ.get("KIS_APP_SECRET", "")
ACCOUNT_NO: str = os.environ.get("KIS_ACCOUNT_NO", "")   # 예: "12345678-01"
IS_PAPER: bool = os.environ.get("KIS_IS_PAPER", "true").lower() == "true"

# 실전/모의 BASE URL
BASE_URL: str = (
    "https://openapivts.koreainvestment.com:29443"
    if IS_PAPER
    else "https://openapi.koreainvestment.com:9443"
)

# ── ETF 후보 풀 ────────────────────────────────────────────────────────────────
# KOSPI·KOSDAQ 시장에 상장된 대표 ETF 티커 목록
# 실제 운영 시 원하는 종목으로 교체하세요.
ETF_UNIVERSE: list[str] = [
    "069500",  # KODEX 200
    "122630",  # KODEX 레버리지
    "252670",  # KODEX 200선물인버스2X
    "114800",  # KODEX 인버스
    "229200",  # KODEX 코스닥150
    "233740",  # KODEX 코스닥150레버리지
    "251340",  # KODEX 코스닥150선물인버스
    "102110",  # TIGER 200
    "152100",  # ARIRANG 200
    "261220",  # KODEX WTI원유선물(H)
    "292050",  # KODEX 골드선물(H)
    "091160",  # KODEX 반도체
    "091170",  # KODEX 은행
    "139660",  # TIGER 미국나스닥100
    "143850",  # TIGER 미국S&P500선물(H)
]

# ── 전략 파라미터 ──────────────────────────────────────────────────────────────
TOP_N: int = 5                  # 선별할 ETF 수
MA_SHORT: int = 5               # 단기 이동평균 기간 (5분봉 캔들 수)
MA_LONG: int = 20               # 장기 이동평균 기간
RSI_PERIOD: int = 14            # RSI 계산 기간
RSI_OVERSOLD: float = 30.0      # RSI 과매도 기준값
TAKE_PROFIT_PCT: float = 1.5    # 익절 목표 수익률 (%)
STOP_LOSS_PCT: float = 1.0      # 손절 기준 수익률 (%)
ORDER_QUANTITY: int = 1         # 1회 주문 수량 (단위: 주)
CANDLE_INTERVAL_MIN: int = 5    # 분봉 단위 (분)
LOOP_INTERVAL_SEC: int = 30     # 전략 루프 주기 (초)

# ── 장 시간 ────────────────────────────────────────────────────────────────────
MARKET_OPEN: str = "09:00"
MARKET_CLOSE: str = "15:20"     # 15:30 장 마감 전 안전 마진을 두고 청산
