"""
한국투자증권 KIS Open API 래퍼
- OAuth 2.0 액세스 토큰 관리 (자동 갱신)
- 국내 주식 현재가, 분봉, 호가, 잔고, 주문 API
"""

from __future__ import annotations

import time
import logging
from datetime import datetime, timedelta
from typing import Any

import requests

import config

logger = logging.getLogger(__name__)


class KISAuth:
    """액세스 토큰 발급 및 자동 갱신."""

    _token: str = ""
    _expires_at: datetime = datetime.min

    def get_token(self) -> str:
        if datetime.now() >= self._expires_at - timedelta(minutes=5):
            self._refresh()
        return self._token

    def _refresh(self) -> None:
        url = f"{config.BASE_URL}/oauth2/tokenP"
        body = {
            "grant_type": "client_credentials",
            "appkey": config.APP_KEY,
            "appsecret": config.APP_SECRET,
        }
        resp = requests.post(url, json=body, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        expires_in = int(data.get("expires_in", 86400))
        self._expires_at = datetime.now() + timedelta(seconds=expires_in)
        logger.info("KIS 액세스 토큰 갱신 완료 (만료: %s)", self._expires_at)


class KISClient:
    """KIS REST API 클라이언트."""

    def __init__(self) -> None:
        self._auth = KISAuth()
        self._session = requests.Session()

    # ── 내부 헬퍼 ──────────────────────────────────────────────────────────────

    def _headers(self, tr_id: str) -> dict[str, str]:
        acct_parts = config.ACCOUNT_NO.split("-")
        return {
            "Content-Type": "application/json",
            "authorization": f"Bearer {self._auth.get_token()}",
            "appkey": config.APP_KEY,
            "appsecret": config.APP_SECRET,
            "tr_id": tr_id,
            "custtype": "P",
        }

    def _get(self, path: str, tr_id: str, params: dict[str, Any]) -> dict[str, Any]:
        url = config.BASE_URL + path
        resp = self._session.get(
            url, headers=self._headers(tr_id), params=params, timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        rt_cd = data.get("rt_cd", "")
        if rt_cd != "0":
            raise RuntimeError(
                f"KIS API 오류 [{tr_id}] rt_cd={rt_cd} msg={data.get('msg1', '')}"
            )
        return data

    def _post(self, path: str, tr_id: str, body: dict[str, Any]) -> dict[str, Any]:
        url = config.BASE_URL + path
        resp = self._session.post(
            url, headers=self._headers(tr_id), json=body, timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        rt_cd = data.get("rt_cd", "")
        if rt_cd != "0":
            raise RuntimeError(
                f"KIS API 오류 [{tr_id}] rt_cd={rt_cd} msg={data.get('msg1', '')}"
            )
        return data

    # ── 시세 API ───────────────────────────────────────────────────────────────

    def get_price(self, ticker: str) -> dict[str, Any]:
        """주식 현재가 조회 (FHKST01010100)."""
        return self._get(
            "/uapi/domestic-stock/v1/quotations/inquire-price",
            "FHKST01010100",
            {"fid_cond_mrkt_div_code": "J", "fid_input_iscd": ticker},
        )

    def get_minute_candles(
        self, ticker: str, interval: int = 5
    ) -> list[dict[str, Any]]:
        """주식 분봉 조회 (FHKST03010200).

        반환값은 최신→과거 순서이므로 전략에서 역순 정렬 후 사용합니다.
        interval: 분 단위 (1, 3, 5, 10, 15, 30, 60, 120)
        """
        now = datetime.now()
        data = self._get(
            "/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice",
            "FHKST03010200",
            {
                "fid_etc_cls_code": "",
                "fid_cond_mrkt_div_code": "J",
                "fid_input_iscd": ticker,
                "fid_input_hour_1": now.strftime("%H%M%S"),
                "fid_pw_data_incu_yn": "Y",
            },
        )
        candles: list[dict[str, Any]] = data.get("output2", [])
        return candles

    def get_volume_rank(self) -> list[dict[str, Any]]:
        """거래량 순위 조회 (FHPST01710000) – ETF 필터링용."""
        data = self._get(
            "/uapi/domestic-stock/v1/quotations/volume-rank",
            "FHPST01710000",
            {
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
            },
        )
        return data.get("output", [])

    # ── 계좌 / 주문 API ────────────────────────────────────────────────────────

    def get_balance(self) -> dict[str, Any]:
        """주식 잔고 조회 (TTTC8434R / VTTC8434R)."""
        acct = config.ACCOUNT_NO.replace("-", "")
        tr_id = "VTTC8434R" if config.IS_PAPER else "TTTC8434R"
        return self._get(
            "/uapi/domestic-stock/v1/trading/inquire-balance",
            tr_id,
            {
                "CANO": acct[:8],
                "ACNT_PRDT_CD": acct[8:],
                "AFHR_FLPR_YN": "N",
                "OFL_YN": "N",
                "INQR_DVSN": "02",
                "UNPR_DVSN": "01",
                "FUND_STTL_ICLD_YN": "N",
                "FNCG_AMT_AUTO_RDPT_YN": "N",
                "PRCS_DVSN": "00",
                "CTX_AREA_FK100": "",
                "CTX_AREA_NK100": "",
            },
        )

    def buy_market(self, ticker: str, qty: int) -> dict[str, Any]:
        """시장가 매수 주문 (TTTC0802U / VTTC0802U)."""
        acct = config.ACCOUNT_NO.replace("-", "")
        tr_id = "VTTC0802U" if config.IS_PAPER else "TTTC0802U"
        body = {
            "CANO": acct[:8],
            "ACNT_PRDT_CD": acct[8:],
            "PDNO": ticker,
            "ORD_DVSN": "01",   # 시장가
            "ORD_QTY": str(qty),
            "ORD_UNPR": "0",
        }
        logger.info("[매수 주문] %s %d주 (시장가)", ticker, qty)
        return self._post(
            "/uapi/domestic-stock/v1/trading/order-cash", tr_id, body
        )

    def sell_market(self, ticker: str, qty: int) -> dict[str, Any]:
        """시장가 매도 주문 (TTTC0801U / VTTC0801U)."""
        acct = config.ACCOUNT_NO.replace("-", "")
        tr_id = "VTTC0801U" if config.IS_PAPER else "TTTC0801U"
        body = {
            "CANO": acct[:8],
            "ACNT_PRDT_CD": acct[8:],
            "PDNO": ticker,
            "ORD_DVSN": "01",   # 시장가
            "ORD_QTY": str(qty),
            "ORD_UNPR": "0",
        }
        logger.info("[매도 주문] %s %d주 (시장가)", ticker, qty)
        return self._post(
            "/uapi/domestic-stock/v1/trading/order-cash", tr_id, body
        )
