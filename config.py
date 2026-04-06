"""
설정 모듈 - 환경 변수 및 매매 상수 관리
"""
import os
from dotenv import load_dotenv

load_dotenv()


# ─── KIS API 인증 ─────────────────────────────────────────────
APP_KEY: str = os.environ["KIS_APP_KEY"]
APP_SECRET: str = os.environ["KIS_APP_SECRET"]

# ─── 계좌 정보 ───────────────────────────────────────────────
ACCOUNT_NO: str = os.environ["KIS_ACCOUNT_NO"]
ACCOUNT_PRODUCT_CODE: str = os.getenv("KIS_ACCOUNT_PRODUCT_CODE", "01")

# ─── 운영 환경 ─────────────────────────────────────────────────
MODE: str = os.getenv("KIS_MODE", "paper").lower()  # "real" | "paper"
IS_PAPER: bool = MODE != "real"

REAL_BASE_URL = "https://openapi.koreainvestment.com:9443"
PAPER_BASE_URL = "https://openapivts.koreainvestment.com:29443"
BASE_URL: str = PAPER_BASE_URL if IS_PAPER else REAL_BASE_URL

# 실전/모의 거래소 구분 TR_ID 접두사
TR_ID_PREFIX: str = "V" if IS_PAPER else "T"

# ─── 매매 파라미터 ────────────────────────────────────────────
MAX_POSITION_AMOUNT: int = int(os.getenv("MAX_POSITION_AMOUNT", "500000"))
MAX_POSITIONS: int = int(os.getenv("MAX_POSITIONS", "5"))
TARGET_PROFIT_RATE: float = float(os.getenv("TARGET_PROFIT_RATE", "0.015"))
STOP_LOSS_RATE: float = float(os.getenv("STOP_LOSS_RATE", "0.007"))

# ─── ETF 선정 파라미터 ────────────────────────────────────────
ETF_SELECT_COUNT: int = 5               # 선정 ETF 수
ETF_MIN_PRICE: int = 5_000              # 최소 주가 (원)
ETF_MAX_PRICE: int = 200_000            # 최대 주가 (원)
ETF_VOLUME_RANK_COUNT: int = 30         # 거래량 순위 조회 수
# 거래량 급증 판정: 현재 분당 거래량 / 20일 평균 분당 거래량
# (현재 KIS API 분봉 조회를 통해 etf_selector에서 활용 예정)
VOLUME_SURGE_THRESHOLD: float = 2.0

# ─── 스케줄 ──────────────────────────────────────────────────
MARKET_OPEN = "09:00"
MARKET_CLOSE = "15:30"
ETF_SELECT_TIME = "09:05"              # ETF 선정 시각
FORCE_SELL_TIME = "15:20"             # 강제 청산 시각 (장 마감 전)
SCAN_INTERVAL_SECONDS: int = 10        # 매매 신호 점검 주기 (초)

# ─── 로그 설정 ────────────────────────────────────────────────
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")
LOG_FILE: str = os.getenv("LOG_FILE", "logs/trader.log")
