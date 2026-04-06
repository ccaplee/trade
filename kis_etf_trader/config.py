"""
설정 관리 모듈
환경변수 및 매매 파라미터를 관리합니다.
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # KIS API 인증 정보
    APP_KEY: str = os.getenv("APP_KEY", "")
    APP_SECRET: str = os.getenv("APP_SECRET", "")
    CANO: str = os.getenv("CANO", "")
    ACNT_PRDT_CD: str = os.getenv("ACNT_PRDT_CD", "01")
    IS_REAL: bool = os.getenv("IS_REAL", "false").lower() == "true"

    # API 엔드포인트
    REAL_URL: str = "https://openapi.koreainvestment.com:9443"
    MOCK_URL: str = "https://openapivts.koreainvestment.com:29443"

    @classmethod
    def base_url(cls) -> str:
        return cls.REAL_URL if cls.IS_REAL else cls.MOCK_URL

    # 매매 파라미터
    MAX_POSITIONS: int = int(os.getenv("MAX_POSITIONS", "5"))
    BUY_AMOUNT: int = int(os.getenv("BUY_AMOUNT", "100000"))
    TAKE_PROFIT_PCT: float = float(os.getenv("TAKE_PROFIT_PCT", "1.5"))
    STOP_LOSS_PCT: float = float(os.getenv("STOP_LOSS_PCT", "0.8"))

    # 기술적 지표 파라미터
    MA_SHORT: int = 5      # 단기 이동평균 기간 (5분봉 MA5)
    MA_LONG: int = 20      # 장기 이동평균 기간 (5분봉 MA20)
    RSI_PERIOD: int = 14   # RSI 산출 기간
    RSI_OVERSOLD: float = 30.0   # RSI 과매도 기준

    # ETF 선별 파라미터
    ETF_TOP_N: int = 5                # 상위 ETF 선별 개수
    ETF_VOLUME_WEIGHT: float = 0.5    # 거래량 가중치
    ETF_VOLATILITY_WEIGHT: float = 0.5  # 변동성 가중치

    # 스케줄 설정 (분 단위)
    CANDLE_INTERVAL_MIN: int = 5    # 분봉 기준
    SCREENING_INTERVAL_MIN: int = 10  # ETF 재선별 주기

    # 장 운영 시간 (KST)
    MARKET_OPEN: str = "09:00"
    MARKET_CLOSE: str = "15:30"
    SCREENING_START: str = "09:05"  # ETF 선별 시작 시각 (장 시작 후 5분)
