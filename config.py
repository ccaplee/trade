"""
Trading configuration constants.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── KIS API credentials ────────────────────────────────────────────────────────
APP_KEY = os.environ["KIS_APP_KEY"]
APP_SECRET = os.environ["KIS_APP_SECRET"]
ACCOUNT_NUMBER = os.environ["ACCOUNT_NUMBER"]
ACCOUNT_PRODUCT_CODE = os.environ.get("ACCOUNT_PRODUCT_CODE", "01")

# ── Endpoint base URLs ─────────────────────────────────────────────────────────
TRADING_MODE = os.environ.get("TRADING_MODE", "paper").lower()
if TRADING_MODE == "real":
    BASE_URL = "https://openapi.koreainvestment.com:9443"
else:
    BASE_URL = "https://openapivts.koreainvestment.com:29443"

# ── Market session (KST) ───────────────────────────────────────────────────────
MARKET_OPEN_TIME = "09:00"
MARKET_CLOSE_TIME = "15:20"
# Trading allowed from this time after open (allow initial volatility to settle)
TRADING_START_OFFSET_MINUTES = 5

# ── ETF universe screening ─────────────────────────────────────────────────────
# Candidate ETF tickers to screen (KOSPI-listed domestic ETFs)
ETF_UNIVERSE = [
    "069500",  # KODEX 200
    "114800",  # KODEX 인버스
    "252670",  # KODEX 200선물인버스2X
    "122630",  # KODEX 레버리지
    "233740",  # KODEX 코스닥150레버리지
    "251340",  # KODEX 코스닥150선물인버스
    "261220",  # KODEX WTI원유선물(H)
    "091160",  # KODEX 반도체
    "091170",  # KODEX 은행
    "102110",  # TIGER 200
    "229200",  # KODEX 코스닥150
    "148020",  # KODEX 미국S&P500선물(H)
    "143850",  # TIGER 미국S&P500선물(H)
    "195930",  # TIGER 해외선진국MSCI World(합성)
    "130730",  # KODEX 미국채10년선물
    "305080",  # TIGER 차이나CSI300
    "200030",  # KODEX 삼성그룹
    "139220",  # TIGER 200 IT
    "266390",  # KODEX 미국FANG플러스(H)
]

TOP_N_ETF = 5  # Number of ETFs to trade simultaneously

# ── Candle / indicator settings ────────────────────────────────────────────────
CANDLE_INTERVAL_MINUTES = 5  # 5-minute candles
MA_SHORT = 5                  # Short moving average period
MA_LONG = 20                  # Long moving average period
RSI_PERIOD = 14               # RSI look-back period
RSI_OVERSOLD = 30             # RSI oversold threshold

# ── Trade execution ────────────────────────────────────────────────────────────
MAX_POSITION_RATIO = 0.20     # Max 20 % of total capital per ticker
TAKE_PROFIT_PCT = 0.015       # 1.5 % take-profit
STOP_LOSS_PCT = -0.008        # -0.8 % stop-loss (stored as negative)

# ── API token ──────────────────────────────────────────────────────────────────
TOKEN_EXPIRY_SAFETY_MARGIN_SECONDS = 60  # Refresh token this many seconds before expiry

# ── Polling interval ───────────────────────────────────────────────────────────
POLL_INTERVAL_SECONDS = 60    # Check signals every 60 s
