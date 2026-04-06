"""
kis_api.py
──────────
한국투자증권 KIS Open API REST 클라이언트.

지원 기능
- OAuth 액세스 토큰 발급 / 자동 갱신
- 주식(ETF) 현재가 조회
- 호가 조회
- 현금 매수 / 매도 주문
- 계좌 잔고 / 보유종목 조회
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta
from typing import Any

import requests

logger = logging.getLogger(__name__)

# ──────────────────────────────────────────────────────────────
# KIS REST 엔드포인트
# ──────────────────────────────────────────────────────────────
_REAL_BASE = "https://openapi.koreainvestment.com:9443"
_MOCK_BASE = "https://openapivts.koreainvestment.com:29443"

# TR-ID 매핑 (실계좌 / 모의투자)
_TR = {
    "token":        ("", ""),                          # 공통
    "price":        ("FHKST01010100", "FHKST01010100"),
    "orderbook":    ("FHKST01010200", "FHKST01010200"),
    "buy":          ("TTTC0802U",     "VTTC0802U"),
    "sell":         ("TTTC0801U",     "VTTC0801U"),
    "balance":      ("TTTC8434R",     "VTTC8434R"),
}


class KISAPIError(Exception):
    """KIS API 호출 실패 시 발생하는 예외."""


class KISClient:
    """KIS Open API 클라이언트."""

    def __init__(
        self,
        app_key: str,
        app_secret: str,
        account_no: str,
        is_mock: bool = True,
    ) -> None:
        self.app_key = app_key
        self.app_secret = app_secret
        # 계좌번호를 앞 8자리 / 뒤 2자리로 분리 (예: "12345678-01")
        parts = account_no.replace("-", "")
        self.cano = parts[:8]
        self.acnt_prdt_cd = parts[8:] if len(parts) > 8 else "01"
        self.is_mock = is_mock
        self.base_url = _MOCK_BASE if is_mock else _REAL_BASE

        self._access_token: str = ""
        self._token_expires: datetime = datetime.min
        self._session = requests.Session()

    # ── 인증 ──────────────────────────────────────────────────

    def _ensure_token(self) -> None:
        """액세스 토큰이 만료됐거나 없으면 새로 발급."""
        if self._access_token and datetime.now() < self._token_expires:
            return
        self._issue_token()

    def _issue_token(self) -> None:
        url = f"{self.base_url}/oauth2/tokenP"
        payload = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
        }
        resp = self._session.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if "access_token" not in data:
            raise KISAPIError(f"토큰 발급 실패: {data}")
        self._access_token = data["access_token"]
        expires_in = int(data.get("expires_in", 86400))
        self._token_expires = datetime.now() + timedelta(seconds=expires_in - 60)
        logger.info("KIS 액세스 토큰 발급 완료 (만료: %s)", self._token_expires)

    def _headers(self, tr_id: str, extra: dict[str, str] | None = None) -> dict[str, str]:
        self._ensure_token()
        h = {
            "Content-Type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self._access_token}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
        }
        if extra:
            h.update(extra)
        return h

    def _tr_id(self, key: str) -> str:
        return _TR[key][1 if self.is_mock else 0]

    # ── 시세 조회 ──────────────────────────────────────────────

    def get_price(self, symbol: str) -> dict[str, Any]:
        """ETF/주식 현재가 조회."""
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-price"
        params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": symbol}
        tr_id = self._tr_id("price")
        resp = self._get(url, params=params, tr_id=tr_id)
        return resp.get("output", {})

    def get_orderbook(self, symbol: str) -> dict[str, Any]:
        """호가 조회."""
        url = f"{self.base_url}/uapi/domestic-stock/v1/quotations/inquire-asking-price-exp-ccn"
        params = {"FID_COND_MRKT_DIV_CODE": "J", "FID_INPUT_ISCD": symbol}
        tr_id = self._tr_id("orderbook")
        resp = self._get(url, params=params, tr_id=tr_id)
        return resp.get("output1", {})

    # ── 주문 ───────────────────────────────────────────────────

    def buy_market(self, symbol: str, qty: int) -> dict[str, Any]:
        """시장가 매수 주문."""
        return self._order("buy", symbol, qty, price=0, order_type="01")

    def sell_market(self, symbol: str, qty: int) -> dict[str, Any]:
        """시장가 매도 주문."""
        return self._order("sell", symbol, qty, price=0, order_type="01")

    def buy_limit(self, symbol: str, qty: int, price: int) -> dict[str, Any]:
        """지정가 매수 주문."""
        return self._order("buy", symbol, qty, price=price, order_type="00")

    def sell_limit(self, symbol: str, qty: int, price: int) -> dict[str, Any]:
        """지정가 매도 주문."""
        return self._order("sell", symbol, qty, price=price, order_type="00")

    def _order(
        self, side: str, symbol: str, qty: int, price: int, order_type: str
    ) -> dict[str, Any]:
        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/order-cash"
        tr_id = self._tr_id(side)
        body = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
            "PDNO": symbol,
            "ORD_DVSN": order_type,   # 00: 지정가, 01: 시장가
            "ORD_QTY": str(qty),
            "ORD_UNPR": str(price),
        }
        resp = self._post(url, body=body, tr_id=tr_id)
        logger.info(
            "[주문] %s %s %d주 (가격=%d) → %s",
            "매수" if side == "buy" else "매도",
            symbol, qty, price, resp.get("output", {})
        )
        return resp.get("output", {})

    # ── 잔고 조회 ──────────────────────────────────────────────

    def get_balance(self) -> dict[str, Any]:
        """계좌 잔고 및 보유종목 조회."""
        url = f"{self.base_url}/uapi/domestic-stock/v1/trading/inquire-balance"
        tr_id = self._tr_id("balance")
        params = {
            "CANO": self.cano,
            "ACNT_PRDT_CD": self.acnt_prdt_cd,
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
        resp = self._get(url, params=params, tr_id=tr_id)
        return resp

    def get_available_cash(self) -> int:
        """주문 가능 현금 (원) 반환."""
        data = self.get_balance()
        output2 = data.get("output2", [{}])
        if isinstance(output2, list) and output2:
            return int(output2[0].get("dnca_tot_amt", 0))
        return 0

    # ── 내부 HTTP 헬퍼 ─────────────────────────────────────────

    def _get(
        self,
        url: str,
        params: dict[str, str],
        tr_id: str,
        retries: int = 3,
    ) -> dict[str, Any]:
        headers = self._headers(tr_id)
        for attempt in range(retries):
            try:
                resp = self._session.get(url, headers=headers, params=params, timeout=10)
                resp.raise_for_status()
                data = resp.json()
                if data.get("rt_cd") != "0":
                    raise KISAPIError(f"API 오류 [{data.get('msg_cd')}]: {data.get('msg1')}")
                return data
            except (requests.RequestException, KISAPIError) as exc:
                if attempt == retries - 1:
                    raise
                wait = 2 ** attempt
                logger.warning("GET 재시도 %d/%d (%.1fs): %s", attempt + 1, retries, wait, exc)
                time.sleep(wait)
        return {}

    def _post(
        self,
        url: str,
        body: dict[str, str],
        tr_id: str,
        retries: int = 3,
    ) -> dict[str, Any]:
        headers = self._headers(tr_id)
        for attempt in range(retries):
            try:
                resp = self._session.post(url, headers=headers, json=body, timeout=10)
                resp.raise_for_status()
                data = resp.json()
                if data.get("rt_cd") != "0":
                    raise KISAPIError(f"API 오류 [{data.get('msg_cd')}]: {data.get('msg1')}")
                return data
            except (requests.RequestException, KISAPIError) as exc:
                if attempt == retries - 1:
                    raise
                wait = 2 ** attempt
                logger.warning("POST 재시도 %d/%d (%.1fs): %s", attempt + 1, retries, wait, exc)
                time.sleep(wait)
        return {}
