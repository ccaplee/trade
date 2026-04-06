"""
kis_api.py
──────────
한국투자증권 KIS Open API 클라이언트

주요 기능
  - OAuth2 액세스 토큰 발급 및 자동 갱신
  - 현재가 조회
  - 분봉 차트 조회 (단타 전략용)
  - 현금 매수/매도 주문
  - 계좌 잔고 조회 (예수금 + 보유 종목)
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta
from typing import Any

import requests

import config
from utils import setup_logger

logger = setup_logger()

# ── 주문 구분 코드 ───────────────────────────────────────────────────────────────
_ORD_DVSN_LIMIT = "00"   # 지정가
_ORD_DVSN_MARKET = "01"  # 시장가

# ── 내부 상수 ────────────────────────────────────────────────────────────────────
_TOKEN_SAFETY_MARGIN_SEC = 300  # 만료 5분 전에 토큰 갱신


class KISApiError(Exception):
    """KIS API 호출 오류"""


class KISClient:
    """KIS Open API 래퍼 클래스"""

    def __init__(self) -> None:
        self._access_token: str = ""
        self._token_expires_at: datetime = datetime.min
        self._session = requests.Session()

    # ── 인증 ────────────────────────────────────────────────────────────────────

    def _refresh_token(self) -> None:
        """액세스 토큰을 (재)발급합니다."""
        url = f"{config.BASE_URL}/oauth2/tokenP"
        payload = {
            "grant_type": "client_credentials",
            "appkey": config.APP_KEY,
            "appsecret": config.APP_SECRET,
        }
        resp = self._session.post(url, json=payload, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        if "access_token" not in data:
            raise KISApiError(f"토큰 발급 실패: {data}")

        self._access_token = data["access_token"]
        expires_in = int(data.get("expires_in", 86400))
        self._token_expires_at = datetime.now() + timedelta(seconds=expires_in)
        logger.info("KIS 액세스 토큰 발급 완료 (만료: %s)", self._token_expires_at)

    def _get_token(self) -> str:
        remaining = (self._token_expires_at - datetime.now()).total_seconds()
        if not self._access_token or remaining < _TOKEN_SAFETY_MARGIN_SEC:
            self._refresh_token()
        return self._access_token

    def _headers(self, tr_id: str, extra: dict[str, str] | None = None) -> dict[str, str]:
        h = {
            "Content-Type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self._get_token()}",
            "appkey": config.APP_KEY,
            "appsecret": config.APP_SECRET,
            "tr_id": tr_id,
            "custtype": "P",
        }
        if extra:
            h.update(extra)
        return h

    def _get(self, path: str, tr_id: str, params: dict[str, str]) -> dict[str, Any]:
        url = f"{config.BASE_URL}{path}"
        resp = self._session.get(url, headers=self._headers(tr_id), params=params, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        rt_cd = data.get("rt_cd", "")
        if rt_cd != "0":
            raise KISApiError(f"[{tr_id}] 오류: {data.get('msg1', data)}")
        return data

    def _post(self, path: str, tr_id: str, body: dict[str, Any]) -> dict[str, Any]:
        url = f"{config.BASE_URL}{path}"
        resp = self._session.post(url, headers=self._headers(tr_id), json=body, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        rt_cd = data.get("rt_cd", "")
        if rt_cd != "0":
            raise KISApiError(f"[{tr_id}] 오류: {data.get('msg1', data)}")
        return data

    # ── 현재가 조회 ─────────────────────────────────────────────────────────────

    def get_current_price(self, symbol: str) -> int:
        """주식/ETF 현재가(원)를 반환합니다."""
        tr_id = "FHKST01010100"
        data = self._get(
            "/uapi/domestic-stock/v1/quotations/inquire-price",
            tr_id,
            {"fid_cond_mrkt_div_code": "J", "fid_input_iscd": symbol},
        )
        return int(data["output"]["stck_prpr"])

    # ── 분봉 차트 조회 ──────────────────────────────────────────────────────────

    def get_minute_chart(self, symbol: str, time_div: str = "1") -> list[dict[str, Any]]:
        """
        분봉 차트 데이터를 반환합니다.

        Parameters
        ----------
        symbol   : 종목코드 (6자리)
        time_div : 분봉 단위 ("1", "3", "5", "10", "15", "30", "60")

        Returns
        -------
        최신 → 과거 순으로 정렬된 dict 리스트
        각 항목: {stck_bsop_date, stck_cntg_hour, stck_prpr, stck_oprc,
                  stck_hgpr, stck_lwpr, cntg_vol, acml_vol}
        """
        tr_id = "FHKST03010200"
        data = self._get(
            "/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice",
            tr_id,
            {
                "fid_etc_cls_code": "",
                "fid_cond_mrkt_div_code": "J",
                "fid_input_iscd": symbol,
                "fid_input_hour_1": time_div,
                "fid_pw_data_incu_yn": "Y",
            },
        )
        return data.get("output2", [])

    # ── 매수 주문 ────────────────────────────────────────────────────────────────

    def buy_order(self, symbol: str, qty: int, price: int = 0) -> dict[str, Any]:
        """
        현금 매수 주문을 냅니다.

        price=0 이면 시장가 주문, price>0 이면 지정가 주문.
        """
        # 실전: TTTC0802U / 모의: VTTC0802U
        tr_id = "TTTC0802U" if config.ENV == "real" else "VTTC0802U"
        ord_dvsn = _ORD_DVSN_MARKET if price == 0 else _ORD_DVSN_LIMIT
        body = {
            "CANO": config.ACCOUNT_NO,
            "ACNT_PRDT_CD": config.ACCOUNT_PRODUCT,
            "PDNO": symbol,
            "ORD_DVSN": ord_dvsn,
            "ORD_QTY": str(qty),
            "ORD_UNPR": str(price),
        }
        result = self._post("/uapi/domestic-stock/v1/trading/order-cash", tr_id, body)
        logger.info("매수 주문 완료: %s %d주 @ %s원", symbol, qty, price if price else "시장가")
        return result

    # ── 매도 주문 ────────────────────────────────────────────────────────────────

    def sell_order(self, symbol: str, qty: int, price: int = 0) -> dict[str, Any]:
        """
        현금 매도 주문을 냅니다.

        price=0 이면 시장가 주문, price>0 이면 지정가 주문.
        """
        # 실전: TTTC0801U / 모의: VTTC0801U
        tr_id = "TTTC0801U" if config.ENV == "real" else "VTTC0801U"
        ord_dvsn = _ORD_DVSN_MARKET if price == 0 else _ORD_DVSN_LIMIT
        body = {
            "CANO": config.ACCOUNT_NO,
            "ACNT_PRDT_CD": config.ACCOUNT_PRODUCT,
            "PDNO": symbol,
            "ORD_DVSN": ord_dvsn,
            "ORD_QTY": str(qty),
            "ORD_UNPR": str(price),
        }
        result = self._post("/uapi/domestic-stock/v1/trading/order-cash", tr_id, body)
        logger.info("매도 주문 완료: %s %d주 @ %s원", symbol, qty, price if price else "시장가")
        return result

    # ── 계좌 잔고 조회 ───────────────────────────────────────────────────────────

    def get_balance(self) -> dict[str, Any]:
        """
        계좌 잔고를 반환합니다.

        Returns
        -------
        {
            "cash": int,          # 주문가능 현금 (원)
            "positions": [        # 보유 종목 리스트
                {
                    "symbol": str,
                    "name": str,
                    "qty": int,
                    "avg_price": float,
                    "current_price": int,
                    "eval_profit_loss": int,
                    "profit_loss_pct": float,
                }
            ]
        }
        """
        tr_id = "TTTC8434R" if config.ENV == "real" else "VTTC8434R"
        params = {
            "CANO": config.ACCOUNT_NO,
            "ACNT_PRDT_CD": config.ACCOUNT_PRODUCT,
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
        data = self._get("/uapi/domestic-stock/v1/trading/inquire-balance", tr_id, params)

        cash = int(data["output2"][0].get("ord_psbl_cash", 0)) if data.get("output2") else 0
        positions = []
        for item in data.get("output1", []):
            qty = int(item.get("hldg_qty", 0))
            if qty <= 0:
                continue
            avg_price = float(item.get("pchs_avg_pric", 0))
            current_price = int(item.get("prpr", 0))
            eval_pl = int(item.get("evlu_pfls_amt", 0))
            pl_pct = float(item.get("evlu_pfls_rt", 0))
            positions.append(
                {
                    "symbol": item["pdno"],
                    "name": item.get("prdt_name", ""),
                    "qty": qty,
                    "avg_price": avg_price,
                    "current_price": current_price,
                    "eval_profit_loss": eval_pl,
                    "profit_loss_pct": pl_pct,
                }
            )
        return {"cash": cash, "positions": positions}
