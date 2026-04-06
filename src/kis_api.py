"""
KIS Open API 호출 래퍼 모듈

주요 기능:
- 거래량 상위 종목 조회 (ETF 필터)
- 종목 현재가 조회
- 주식 주문 (매수 / 매도)
- 잔고 조회
"""
import logging
import time
from typing import Any

import requests

from .kis_auth import KISAuth

logger = logging.getLogger(__name__)

# KIS API 호출 간격 (초) – Rate limit 방어
_API_CALL_INTERVAL = 0.2


def _sleep():
    time.sleep(_API_CALL_INTERVAL)


class KISApi:
    """KIS Open API 호출 클래스"""

    def __init__(self, auth: KISAuth):
        self.auth = auth

    def _get(self, path: str, tr_id: str, params: dict) -> dict:
        url = f"{self.auth.base_url}{path}"
        headers = self.auth.get_headers(tr_id)
        resp = requests.get(url, headers=headers, params=params, timeout=10)
        resp.raise_for_status()
        _sleep()
        return resp.json()

    def _post(self, path: str, tr_id: str, body: dict) -> dict:
        url = f"{self.auth.base_url}{path}"
        headers = self.auth.get_headers(tr_id)
        resp = requests.post(url, headers=headers, json=body, timeout=10)
        resp.raise_for_status()
        _sleep()
        return resp.json()

    # ------------------------------------------------------------------
    # 시세 조회
    # ------------------------------------------------------------------

    def get_volume_rank(
        self,
        fid_input_iscd: str = "0000",  # 전체
        fid_trgt_cls_code: str = "0",  # 전체
        fid_vol_cnt: str = "100000",   # 최소 거래량 필터
    ) -> list[dict]:
        """
        거래량 순위 조회 (국내주식 거래량순위)
        TR_ID: FHPST01710000
        """
        params = {
            "fid_cond_mrkt_div_code": "J",  # 주식
            "fid_cond_scr_div_code": "20171",
            "fid_input_iscd": fid_input_iscd,
            "fid_div_cls_code": "0",
            "fid_blng_cls_code": "0",
            "fid_trgt_cls_code": fid_trgt_cls_code,
            "fid_trgt_exls_cls_code": "0",
            "fid_input_price_1": "",
            "fid_input_price_2": "",
            "fid_vol_cnt": fid_vol_cnt,
            "fid_input_date_1": "",
        }
        data = self._get(
            "/uapi/domestic-stock/v1/quotations/volume-rank",
            "FHPST01710000",
            params,
        )
        return data.get("output", [])

    def get_price(self, stk_cd: str) -> dict:
        """
        주식 현재가 조회
        TR_ID: FHKST01010100
        """
        params = {
            "fid_cond_mrkt_div_code": "J",
            "fid_input_iscd": stk_cd,
        }
        data = self._get(
            "/uapi/domestic-stock/v1/quotations/inquire-price",
            "FHKST01010100",
            params,
        )
        return data.get("output", {})

    def get_price_chart(self, stk_cd: str, period_code: str = "D") -> list[dict]:
        """
        주식 일/주/월/년 OHLCV 조회
        TR_ID: FHKST03010100
        period_code: D(일), W(주), M(월), Y(년)
        """
        params = {
            "fid_cond_mrkt_div_code": "J",
            "fid_input_iscd": stk_cd,
            "fid_input_date_1": "",
            "fid_input_date_2": "",
            "fid_period_div_code": period_code,
            "fid_org_adj_prc": "0",
        }
        data = self._get(
            "/uapi/domestic-stock/v1/quotations/inquire-daily-price",
            "FHKST03010100",
            params,
        )
        return data.get("output2", [])

    def get_minute_chart(self, stk_cd: str, time_str: str = "090000") -> list[dict]:
        """
        주식 분봉 데이터 조회
        TR_ID: FHKST03010200
        """
        params = {
            "fid_etc_cls_code": "",
            "fid_cond_mrkt_div_code": "J",
            "fid_input_iscd": stk_cd,
            "fid_input_hour_1": time_str,
            "fid_pw_data_incu_yn": "N",
        }
        data = self._get(
            "/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice",
            "FHKST03010200",
            params,
        )
        return data.get("output2", [])

    def get_etf_info(self, stk_cd: str) -> dict:
        """
        ETF 종목 정보 조회
        TR_ID: FHPST02400000
        """
        params = {
            "fid_cond_mrkt_div_code": "J",
            "fid_input_iscd": stk_cd,
        }
        data = self._get(
            "/uapi/domestic-stock/v1/quotations/inquire-price",
            "FHKST01010100",
            params,
        )
        return data.get("output", {})

    # ------------------------------------------------------------------
    # 주문
    # ------------------------------------------------------------------

    def _order(
        self,
        stk_cd: str,
        order_type: str,    # "01"=시장가, "00"=지정가
        qty: int,
        price: int,
        buy_sell: str,      # "BUY" or "SELL"
    ) -> dict:
        if buy_sell == "BUY":
            tr_id = "TTTC0802U" if self.auth.is_real else "VTTC0802U"
        else:
            tr_id = "TTTC0801U" if self.auth.is_real else "VTTC0801U"

        body = {
            "CANO": self.auth.cano,
            "ACNT_PRDT_CD": self.auth.acnt_prdt_cd,
            "PDNO": stk_cd,
            "ORD_DVSN": order_type,
            "ORD_QTY": str(qty),
            "ORD_UNPR": str(price) if order_type == "00" else "0",
        }
        logger.info(
            "[주문] %s %s %s %d주%s",
            buy_sell, stk_cd, "지정가" if order_type == "00" else "시장가", qty,
            f" @{price}" if order_type == "00" else "",
        )
        return self._post(
            "/uapi/domestic-stock/v1/trading/order-cash",
            tr_id,
            body,
        )

    def buy_market(self, stk_cd: str, qty: int) -> dict:
        """시장가 매수"""
        return self._order(stk_cd, "01", qty, 0, "BUY")

    def sell_market(self, stk_cd: str, qty: int) -> dict:
        """시장가 매도"""
        return self._order(stk_cd, "01", qty, 0, "SELL")

    def buy_limit(self, stk_cd: str, qty: int, price: int) -> dict:
        """지정가 매수"""
        return self._order(stk_cd, "00", qty, price, "BUY")

    def sell_limit(self, stk_cd: str, qty: int, price: int) -> dict:
        """지정가 매도"""
        return self._order(stk_cd, "00", qty, price, "SELL")

    # ------------------------------------------------------------------
    # 잔고 조회
    # ------------------------------------------------------------------

    def get_balance(self) -> dict[str, Any]:
        """
        주식 잔고 조회
        TR_ID: TTTC8434R (실전) / VTTC8434R (모의)
        Returns: {"holdings": [...], "summary": {...}}
        """
        tr_id = "TTTC8434R" if self.auth.is_real else "VTTC8434R"
        params = {
            "CANO": self.auth.cano,
            "ACNT_PRDT_CD": self.auth.acnt_prdt_cd,
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
        data = self._get(
            "/uapi/domestic-stock/v1/trading/inquire-balance",
            tr_id,
            params,
        )
        holdings = data.get("output1", [])
        summary = data.get("output2", [{}])[0] if data.get("output2") else {}
        return {"holdings": holdings, "summary": summary}

    def get_available_cash(self) -> int:
        """주문 가능 현금 조회 (원)"""
        balance = self.get_balance()
        try:
            return int(balance["summary"].get("dnca_tot_amt", "0"))
        except (KeyError, ValueError):
            return 0
