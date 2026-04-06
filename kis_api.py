"""
KIS Open API wrapper.

Handles:
- OAuth2 access-token acquisition and caching
- 5-minute OHLCV candle retrieval
- Current price / volume query
- Market order placement (buy / sell)
"""

from __future__ import annotations

import time
import logging
from datetime import datetime, timedelta
from typing import Any

import requests

import config

logger = logging.getLogger(__name__)

_token_cache: dict[str, Any] = {}


# ── Authentication ─────────────────────────────────────────────────────────────

def _fetch_access_token() -> str:
    """Request a new OAuth access token from KIS."""
    url = f"{config.BASE_URL}/oauth2/tokenP"
    body = {
        "grant_type": "client_credentials",
        "appkey": config.APP_KEY,
        "appsecret": config.APP_SECRET,
    }
    resp = requests.post(url, json=body, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    token = data["access_token"]
    # KIS tokens expire in ~86400 s; cache with a 60-s safety margin
    expires_at = time.time() + int(data.get("expires_in", 86400)) - config.TOKEN_EXPIRY_SAFETY_MARGIN_SECONDS
    _token_cache["token"] = token
    _token_cache["expires_at"] = expires_at
    logger.info("Access token refreshed.")
    return token


def get_access_token() -> str:
    """Return a valid access token, refreshing if expired."""
    if _token_cache.get("token") and time.time() < _token_cache.get("expires_at", 0):
        return _token_cache["token"]
    return _fetch_access_token()


def _auth_headers(tr_id: str) -> dict[str, str]:
    return {
        "authorization": f"Bearer {get_access_token()}",
        "appkey": config.APP_KEY,
        "appsecret": config.APP_SECRET,
        "tr_id": tr_id,
        "custtype": "P",
        "content-type": "application/json; charset=utf-8",
    }


# ── Market data ────────────────────────────────────────────────────────────────

def get_minute_candles(ticker: str, n_candles: int = 30) -> list[dict]:
    """
    Fetch the last *n_candles* 5-minute OHLCV bars for *ticker*.

    Returns a list of dicts sorted oldest → newest:
        [{"time": "HHmm", "open": float, "high": float,
          "low": float, "close": float, "volume": int}, ...]
    """
    url = f"{config.BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice"
    now = datetime.now()
    params = {
        "FID_ETC_CLS_CODE": "",
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD": ticker,
        "FID_INPUT_HOUR_1": now.strftime("%H%M%S"),
        "FID_PW_DATA_INCU_YN": "Y",
    }
    tr_id = "FHKST03010200"  # 국내주식 분봉 조회
    headers = _auth_headers(tr_id)
    resp = requests.get(url, headers=headers, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    candles = []
    for row in data.get("output2", []):
        try:
            candles.append(
                {
                    "time": row["stck_bsop_date"] + row["stck_cntg_hour"],
                    "open": float(row["stck_oprc"]),
                    "high": float(row["stck_hgpr"]),
                    "low": float(row["stck_lwpr"]),
                    "close": float(row["stck_prpr"]),
                    "volume": int(row["cntg_vol"]),
                }
            )
        except (KeyError, ValueError):
            continue

    # API returns newest first; reverse to oldest-first
    candles.reverse()
    return candles[-n_candles:]


def get_current_price(ticker: str) -> float:
    """Return the latest trade price for *ticker*."""
    url = f"{config.BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-price"
    params = {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD": ticker,
    }
    tr_id = "FHKST01010100"
    headers = _auth_headers(tr_id)
    resp = requests.get(url, headers=headers, params=params, timeout=10)
    resp.raise_for_status()
    data = resp.json()
    return float(data["output"]["stck_prpr"])


def get_volume_and_volatility(ticker: str) -> tuple[int, float]:
    """
    Return (cumulative_volume, price_volatility_pct) for today.

    Volatility = (high - low) / open * 100 using today's intraday data.
    """
    url = f"{config.BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-price"
    params = {
        "FID_COND_MRKT_DIV_CODE": "J",
        "FID_INPUT_ISCD": ticker,
    }
    tr_id = "FHKST01010100"
    headers = _auth_headers(tr_id)
    resp = requests.get(url, headers=headers, params=params, timeout=10)
    resp.raise_for_status()
    output = resp.json().get("output", {})

    volume = int(output.get("acml_vol", 0))
    try:
        open_price = float(output["stck_oprc"])
        high = float(output["stck_hgpr"])
        low = float(output["stck_lwpr"])
        volatility = (high - low) / open_price * 100 if open_price else 0.0
    except (KeyError, ValueError, ZeroDivisionError):
        volatility = 0.0

    return volume, volatility


# ── Account ────────────────────────────────────────────────────────────────────

def get_balance() -> float:
    """Return available cash balance (원화예수금)."""
    url = f"{config.BASE_URL}/uapi/domestic-stock/v1/trading/inquire-psbl-order"
    params = {
        "CANO": config.ACCOUNT_NUMBER,
        "ACNT_PRDT_CD": config.ACCOUNT_PRODUCT_CODE,
        "PDNO": "005930",  # dummy ticker required by the endpoint
        "ORD_UNPR": "0",
        "ORD_DVSN": "01",
        "CMA_EVLU_AMT_ICLD_YN": "Y",
        "OVRS_ICLD_YN": "N",
    }
    tr_id = "TTTC8908R" if config.TRADING_MODE == "real" else "VTTC8908R"
    headers = _auth_headers(tr_id)
    resp = requests.get(url, headers=headers, params=params, timeout=10)
    resp.raise_for_status()
    output = resp.json().get("output", {})
    return float(output.get("ord_psbl_cash", 0))


# ── Order placement ────────────────────────────────────────────────────────────

def _place_order(ticker: str, order_type: str, quantity: int, price: int = 0) -> dict:
    """
    Place a domestic stock order.

    order_type: "buy" or "sell"
    price: 0 → market order
    """
    url = f"{config.BASE_URL}/uapi/domestic-stock/v1/trading/order-cash"

    if order_type == "buy":
        tr_id = "TTTC0802U" if config.TRADING_MODE == "real" else "VTTC0802U"
        side_code = "01"  # 매수
    else:
        tr_id = "TTTC0801U" if config.TRADING_MODE == "real" else "VTTC0801U"
        side_code = "01"  # 매도

    body = {
        "CANO": config.ACCOUNT_NUMBER,
        "ACNT_PRDT_CD": config.ACCOUNT_PRODUCT_CODE,
        "PDNO": ticker,
        "ORD_DVSN": "01" if price == 0 else "00",  # 01=시장가, 00=지정가
        "ORD_QTY": str(quantity),
        "ORD_UNPR": str(price),
        "CTAC_TLNO": "",
        "SLL_TYPE": "01" if order_type == "sell" else "",
        "ALGO_NO": "",
    }
    headers = _auth_headers(tr_id)
    resp = requests.post(url, headers=headers, json=body, timeout=10)
    resp.raise_for_status()
    result = resp.json()
    logger.info("Order placed: %s %s x%d → %s", order_type.upper(), ticker, quantity, result.get("rt_cd"))
    return result


def buy_market_order(ticker: str, quantity: int) -> dict:
    """Submit a market buy order."""
    return _place_order(ticker, "buy", quantity)


def sell_market_order(ticker: str, quantity: int) -> dict:
    """Submit a market sell order."""
    return _place_order(ticker, "sell", quantity)
