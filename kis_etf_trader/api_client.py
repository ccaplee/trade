"""
한국투자증권 KIS Open API 클라이언트
OAuth 토큰 발급/갱신 및 REST API 호출을 담당합니다.
"""

import time
from datetime import datetime, timedelta
from typing import Any

import requests

from .config import Config
from .logger import setup_logger

logger = setup_logger(__name__)


class KISClient:
    """KIS Open API HTTP 클라이언트."""

    _TOKEN_EXPIRY_BUFFER_SEC: int = 300  # 만료 5분 전에 재발급

    def __init__(self) -> None:
        self._access_token: str = ""
        self._token_expires_at: datetime = datetime.min
        self._session = requests.Session()
        self._session.headers.update({"Content-Type": "application/json; charset=utf-8"})

    # ------------------------------------------------------------------
    # 인증
    # ------------------------------------------------------------------

    def _issue_token(self) -> None:
        """OAuth 접근 토큰을 발급받아 저장합니다."""
        url = f"{Config.base_url()}/oauth2/tokenP"
        body = {
            "grant_type": "client_credentials",
            "appkey": Config.APP_KEY,
            "appsecret": Config.APP_SECRET,
        }
        resp = self._session.post(url, json=body, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        self._access_token = data["access_token"]
        expires_in = int(data.get("expires_in", 86400))
        self._token_expires_at = datetime.now() + timedelta(seconds=expires_in)
        logger.info("KIS 접근 토큰 발급 완료 (만료: %s)", self._token_expires_at.strftime("%H:%M:%S"))

    def _ensure_token(self) -> None:
        """토큰이 유효한지 확인하고, 필요 시 재발급합니다."""
        remaining = (self._token_expires_at - datetime.now()).total_seconds()
        if not self._access_token or remaining < self._TOKEN_EXPIRY_BUFFER_SEC:
            self._issue_token()

    def _auth_headers(self, tr_id: str) -> dict[str, str]:
        self._ensure_token()
        return {
            "authorization": f"Bearer {self._access_token}",
            "appkey": Config.APP_KEY,
            "appsecret": Config.APP_SECRET,
            "tr_id": tr_id,
            "custtype": "P",
        }

    # ------------------------------------------------------------------
    # 공통 요청 헬퍼
    # ------------------------------------------------------------------

    def _get(self, path: str, tr_id: str, params: dict) -> dict[str, Any]:
        url = f"{Config.base_url()}{path}"
        headers = self._auth_headers(tr_id)
        resp = self._session.get(url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("rt_cd") != "0":
            raise RuntimeError(f"API 오류 [{tr_id}]: {data.get('msg1', '')}")
        return data

    def _post(self, path: str, tr_id: str, body: dict) -> dict[str, Any]:
        url = f"{Config.base_url()}{path}"
        headers = self._auth_headers(tr_id)
        resp = self._session.post(url, headers=headers, json=body, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if data.get("rt_cd") != "0":
            raise RuntimeError(f"API 오류 [{tr_id}]: {data.get('msg1', '')}")
        return data

    # ------------------------------------------------------------------
    # 시세 조회
    # ------------------------------------------------------------------

    def get_price(self, ticker: str) -> dict[str, Any]:
        """주식/ETF 현재가 조회 (FHKST01010100)."""
        tr_id = "FHKST01010100"
        params = {
            "fid_cond_mrkt_div_code": "J",
            "fid_input_iscd": ticker,
        }
        data = self._get("/uapi/domestic-stock/v1/quotations/inquire-price", tr_id, params)
        return data["output"]

    def get_minute_candles(self, ticker: str, time_str: str = "") -> list[dict[str, Any]]:
        """주식/ETF 분봉 조회 (FHKST03010200).

        Args:
            ticker: 종목 코드 (6자리)
            time_str: 조회 기준 시각 (HHMMSS). 빈 문자열이면 현재 시각 기준.

        Returns:
            분봉 데이터 리스트 (최신 → 과거 순)
        """
        tr_id = "FHKST03010200"
        params = {
            "fid_etc_cls_code": "",
            "fid_cond_mrkt_div_code": "J",
            "fid_input_iscd": ticker,
            "fid_input_hour_1": time_str,
            "fid_pw_data_incu_yn": "Y",
        }
        data = self._get("/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice", tr_id, params)
        return data.get("output2", [])

    def get_volume_rank(self) -> list[dict[str, Any]]:
        """거래량 상위 조회 (FHPST01710000) – ETF 필터링용."""
        tr_id = "FHPST01710000"
        params = {
            "fid_cond_mrkt_div_code": "J",
            "fid_cond_scr_div_code": "20171",
            "fid_input_iscd": "0000",
            "fid_div_cls_code": "0",
            "fid_blng_cls_code": "0",
            "fid_trgt_cls_code": "111111111",
            "fid_trgt_exls_cls_code": "000000",
            "fid_input_price_1": "",
            "fid_input_price_2": "",
            "fid_vol_cnt": "",
            "fid_input_date_1": "",
        }
        data = self._get("/uapi/domestic-stock/v1/ranking/volume", tr_id, params)
        return data.get("output", [])

    def get_fluctuation_rank(self) -> list[dict[str, Any]]:
        """등락률 상위 조회 (FHPST01700000) – 변동성 필터링용."""
        tr_id = "FHPST01700000"
        params = {
            "fid_cond_mrkt_div_code": "J",
            "fid_cond_scr_div_code": "20170",
            "fid_input_iscd": "0000",
            "fid_rank_sort_cls_code": "0",
            "fid_input_cnt_1": "0",
            "fid_prc_cls_code": "0",
            "fid_input_price_1": "",
            "fid_input_price_2": "",
            "fid_vol_cnt": "",
            "fid_trgt_cls_code": "0",
            "fid_trgt_exls_cls_code": "0",
            "fid_div_cls_code": "0",
            "fid_rsfl_rate1": "",
            "fid_rsfl_rate2": "",
        }
        data = self._get("/uapi/domestic-stock/v1/ranking/fluctuation", tr_id, params)
        return data.get("output", [])

    # ------------------------------------------------------------------
    # 주문
    # ------------------------------------------------------------------

    def buy_market_order(self, ticker: str, qty: int) -> dict[str, Any]:
        """시장가 매수 주문."""
        tr_id = "TTTC0802U" if Config.IS_REAL else "VTTC0802U"
        body = {
            "CANO": Config.CANO,
            "ACNT_PRDT_CD": Config.ACNT_PRDT_CD,
            "PDNO": ticker,
            "ORD_DVSN": "01",   # 시장가
            "ORD_QTY": str(qty),
            "ORD_UNPR": "0",
        }
        logger.info("[매수 주문] %s %d주 (시장가)", ticker, qty)
        return self._post("/uapi/domestic-stock/v1/trading/order-cash", tr_id, body)

    def sell_market_order(self, ticker: str, qty: int) -> dict[str, Any]:
        """시장가 매도 주문."""
        tr_id = "TTTC0801U" if Config.IS_REAL else "VTTC0801U"
        body = {
            "CANO": Config.CANO,
            "ACNT_PRDT_CD": Config.ACNT_PRDT_CD,
            "PDNO": ticker,
            "ORD_DVSN": "01",   # 시장가
            "ORD_QTY": str(qty),
            "ORD_UNPR": "0",
        }
        logger.info("[매도 주문] %s %d주 (시장가)", ticker, qty)
        return self._post("/uapi/domestic-stock/v1/trading/order-cash", tr_id, body)

    def get_balance(self) -> dict[str, Any]:
        """주식 잔고 조회 (TTTC8434R / VTTC8434R)."""
        tr_id = "TTTC8434R" if Config.IS_REAL else "VTTC8434R"
        params = {
            "CANO": Config.CANO,
            "ACNT_PRDT_CD": Config.ACNT_PRDT_CD,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "01",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        }
        return self._get("/uapi/domestic-stock/v1/trading/inquire-balance", tr_id, params)
