"""
config.py – 한국투자증권 KIS Open API 설정 파일

실제 운용 시 이 파일을 직접 수정하거나 환경변수로 관리하세요.
절대 API 키를 소스코드에 하드코딩하여 공개 저장소에 올리지 마세요.
"""

import os

# ── KIS API 인증 정보 ─────────────────────────────────────────────────────────
# 한국투자증권 KIS Developers (https://apiportal.koreainvestment.com) 에서 발급
APP_KEY: str = os.environ.get("KIS_APP_KEY", "YOUR_APP_KEY_HERE")
APP_SECRET: str = os.environ.get("KIS_APP_SECRET", "YOUR_APP_SECRET_HERE")

# 실전투자: "https://openapi.koreainvestment.com:9443"
# 모의투자: "https://openapivts.koreainvestment.com:9443"
BASE_URL: str = os.environ.get(
    "KIS_BASE_URL", "https://openapivts.koreainvestment.com:9443"
)

# ── 계좌 정보 ──────────────────────────────────────────────────────────────────
# CANO: 계좌번호 앞 8자리, ACNT_PRDT_CD: 계좌 상품코드 뒤 2자리
CANO: str = os.environ.get("KIS_CANO", "12345678")
ACNT_PRDT_CD: str = os.environ.get("KIS_ACNT_PRDT_CD", "01")

# ── 매매 전략 파라미터 ─────────────────────────────────────────────────────────
# ETF 후보 유니버스 – 거래량/변동성 상위 N개를 선별할 초기 풀
ETF_UNIVERSE: list[str] = [
    "069500",  # KODEX 200
    "114800",  # KODEX 인버스
    "122630",  # KODEX 레버리지
    "252670",  # KODEX 200선물인버스2X
    "233740",  # KODEX 코스닥150레버리지
    "229200",  # KODEX 코스닥150
    "091160",  # KODEX 반도체
    "091170",  # KODEX 은행
    "102110",  # TIGER 200
    "148020",  # KBSTAR 200
    "261220",  # KODEX WTI원유선물(H)
]

# 선별 상위 ETF 개수
TOP_N_ETF: int = 5

# 단타 전략 – 이동평균 기간 (5분봉 캔들 수 기준)
MA_SHORT: int = 5   # 단기 이동평균
MA_LONG: int = 20   # 장기 이동평균

# RSI 기간 (5분봉 캔들 수 기준)
RSI_PERIOD: int = 14
RSI_OVERSOLD: float = 30.0   # RSI 과매도 임계값

# 익절/손절 비율
TAKE_PROFIT_RATE: float = 0.015   # 1.5% 익절
STOP_LOSS_RATE: float = 0.008     # 0.8% 손절

# 리스크 관리
MAX_POSITION_RATIO: float = 0.20  # 계좌 잔고 대비 종목당 최대 투자 비율 (20%)
MAX_POSITIONS: int = 3            # 동시 최대 보유 종목 수

# ── 스케줄러 설정 ──────────────────────────────────────────────────────────────
CANDLE_INTERVAL_MIN: int = 5      # 캔들 봉 단위 (분)
POLL_INTERVAL_SEC: int = 30       # 신호 체크 주기 (초)

# 장 운영 시간 (KST)
MARKET_OPEN_TIME: str = "09:00"
MARKET_CLOSE_TIME: str = "15:20"  # 15:30 마감 전 10분에 전량 청산 고려

# ── 로그 설정 ─────────────────────────────────────────────────────────────────
LOG_LEVEL: str = os.environ.get("LOG_LEVEL", "INFO")
LOG_FILE: str = "trading.log"
