# config.py - KIS Open API 설정 및 거래 파라미터

# ── KIS API 인증 정보 ──────────────────────────────────────────────────────────
APP_KEY = "YOUR_APP_KEY"          # 한국투자증권 앱 키
APP_SECRET = "YOUR_APP_SECRET"    # 한국투자증권 앱 시크릿

# 실전투자: "https://openapi.koreainvestment.com:9443"
# 모의투자: "https://openapivts.koreainvestment.com:29443"
BASE_URL = "https://openapivts.koreainvestment.com:29443"

# ── 계좌 정보 ──────────────────────────────────────────────────────────────────
ACCOUNT_NO = "50123456"   # 계좌번호 앞 8자리
ACCOUNT_CODE = "01"       # 계좌 상품코드 (보통 "01")

# ── 거래 환경 플래그 ──────────────────────────────────────────────────────────
# True: 모의투자, False: 실전투자
IS_PAPER_TRADING = True

# ── 전략 파라미터 ──────────────────────────────────────────────────────────────
MA_SHORT = 5          # 단기 이동평균 기간 (5분봉 캔들 수)
MA_LONG = 20          # 장기 이동평균 기간 (5분봉 캔들 수)
RSI_PERIOD = 14       # RSI 계산 기간
RSI_OVERSOLD = 30     # RSI 과매도 기준값

# ── 수익/손실 비율 ─────────────────────────────────────────────────────────────
TAKE_PROFIT_RATE = 0.015   # 익절 기준 (1.5%)
STOP_LOSS_RATE = 0.008     # 손절 기준 (0.8%)

# ── 리스크 관리 ────────────────────────────────────────────────────────────────
MAX_POSITION_RATIO = 0.20  # 종목당 최대 투자금 비율 (20%)
MAX_POSITIONS = 3          # 동시 보유 최대 종목 수
TOP_ETF_COUNT = 5          # 선별할 상위 ETF 수

# ── 트레이딩 루프 설정 ─────────────────────────────────────────────────────────
LOOP_INTERVAL_SEC = 30     # 매매 루프 주기 (초)
MARKET_OPEN = "09:00"      # 장 시작 시각
MARKET_CLOSE = "15:20"     # 장 마감 시각 (동시호가 전 매도 마감)

# ── ETF 후보 종목 풀 (KOSPI/KOSDAQ ETF 일부) ──────────────────────────────────
# 실행 시 거래량/변동성 기준으로 이 풀에서 상위 5개를 자동 선별합니다.
ETF_UNIVERSE = [
    "069500",  # KODEX 200
    "114800",  # KODEX 인버스
    "122630",  # KODEX 레버리지
    "252670",  # KODEX 200선물인버스2X
    "229200",  # KODEX 코스닥150
    "233740",  # KODEX 코스닥150 레버리지
    "251340",  # KODEX 코스닥150선물인버스
    "091160",  # KODEX 반도체
    "091170",  # KODEX 은행
    "102110",  # TIGER 200
    "148020",  # KBSTAR 200
    "278540",  # KODEX MSCI Korea TR
    "kodex_bio",  # placeholder — 종목코드로 교체 필요
]

# 종목코드 형식 오류 방지용 필터 (6자리 숫자만 허용)
ETF_UNIVERSE = [code for code in ETF_UNIVERSE if code.isdigit() and len(code) == 6]
