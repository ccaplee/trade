"""
설정 모듈
환경변수(.env)에서 KIS API 접속 정보 및 매매 파라미터를 읽어옵니다.
"""
import os
from dotenv import load_dotenv

load_dotenv()

# ── KIS API 접속 정보 ──────────────────────────────────────────────────────────
APP_KEY = os.getenv("KIS_APP_KEY", "")
APP_SECRET = os.getenv("KIS_APP_SECRET", "")
ACCOUNT_NUMBER = os.getenv("KIS_ACCOUNT_NUMBER", "")
ACCOUNT_PRODUCT_CODE = os.getenv("KIS_ACCOUNT_PRODUCT_CODE", "01")

# ── 환경 (real: 실전, paper: 모의) ─────────────────────────────────────────────
KIS_ENV = os.getenv("KIS_ENV", "paper").lower()

if KIS_ENV == "real":
    BASE_URL = "https://openapi.koreainvestment.com:9443"
else:
    BASE_URL = "https://openapivts.koreainvestment.com:29443"

# TR ID 접두사 (실전: T, 모의: V)
TR_PREFIX = "T" if KIS_ENV == "real" else "V"

# ── 매매 파라미터 ──────────────────────────────────────────────────────────────
MAX_BUY_AMOUNT = int(os.getenv("MAX_BUY_AMOUNT", "500000"))   # 1회 최대 매수금액(원)
MAX_POSITIONS = int(os.getenv("MAX_POSITIONS", "3"))           # 최대 보유 종목 수
TAKE_PROFIT_RATE = float(os.getenv("TAKE_PROFIT_RATE", "1.5"))  # 목표 수익률(%)
STOP_LOSS_RATE = float(os.getenv("STOP_LOSS_RATE", "0.7"))     # 손절 비율(%)

# 매매 대상 ETF 종목코드 목록
_raw_symbols = os.getenv("ETF_SYMBOLS", "069500,114800,122630,252670,233740,251340")
ETF_SYMBOLS = [s.strip() for s in _raw_symbols.split(",") if s.strip()]

# ── 전략 파라미터 ──────────────────────────────────────────────────────────────
RSI_PERIOD = 14          # RSI 산출 기간
RSI_BUY_THRESHOLD = 35   # RSI 매수 기준 (이하 과매도)
RSI_SELL_THRESHOLD = 65  # RSI 매도 기준 (이상 과매수)
MA_SHORT = 5             # 단기 이동평균 기간
MA_LONG = 20             # 장기 이동평균 기간
MIN_VOLUME_RATIO = 1.5   # 거래량 급증 배수 (평균 대비)

# ── 루프 주기 (초) ─────────────────────────────────────────────────────────────
POLL_INTERVAL = 30       # 시세 조회 주기(초)

# ── 장 운영 시간 (KST) ─────────────────────────────────────────────────────────
MARKET_OPEN_TIME = "09:00"
MARKET_CLOSE_TIME = "15:20"   # 15:30 마감 10분 전 신규 매수 중단

# ── 검증 ───────────────────────────────────────────────────────────────────────
def validate():
    missing = [k for k, v in {
        "KIS_APP_KEY": APP_KEY,
        "KIS_APP_SECRET": APP_SECRET,
        "KIS_ACCOUNT_NUMBER": ACCOUNT_NUMBER,
    }.items() if not v]
    if missing:
        raise ValueError(f"필수 환경변수가 설정되지 않았습니다: {', '.join(missing)}")
