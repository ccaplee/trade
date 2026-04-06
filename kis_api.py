"""
KIS Open API 래퍼
- OAuth 토큰 발급 / 자동 갱신
- 시세 조회, 잔고 조회, 주문 API
"""
import time
import logging
from datetime import datetime, timedelta
from typing import Any

import requests

import config

logger = logging.getLogger(__name__)

# ── 토큰 캐시 ──────────────────────────────────────────────────────────────────
_access_token: str = ""
_token_expires_at: datetime = datetime.min


def _get_access_token() -> str:
    """OAuth 접근 토큰을 발급하고 캐싱합니다."""
    global _access_token, _token_expires_at

    if _access_token and datetime.now() < _token_expires_at:
        return _access_token

    url = f"{config.BASE_URL}/oauth2/tokenP"
    body = {
        "grant_type": "client_credentials",
        "appkey": config.APP_KEY,
        "appsecret": config.APP_SECRET,
    }
    resp = requests.post(url, json=body, timeout=10)
    resp.raise_for_status()
    data = resp.json()

    _access_token = data["access_token"]
    expires_in = int(data.get("expires_in", 86400))
    _token_expires_at = datetime.now() + timedelta(seconds=expires_in - 60)
    logger.info("KIS 액세스 토큰 발급 완료 (만료: %s)", _token_expires_at)
    return _access_token


def _headers(tr_id: str) -> dict[str, str]:
    return {
        "Content-Type": "application/json; charset=utf-8",
        "authorization": f"Bearer {_get_access_token()}",
        "appkey": config.APP_KEY,
        "appsecret": config.APP_SECRET,
        "tr_id": tr_id,
        "custtype": "P",
    }


def _get(path: str, tr_id: str, params: dict[str, str]) -> dict[str, Any]:
    """GET 요청 헬퍼 – 속도 제한을 고려한 재시도 포함."""
    url = f"{config.BASE_URL}{path}"
    for attempt in range(3):
        resp = requests.get(url, headers=_headers(tr_id), params=params, timeout=10)
        if resp.status_code == 429:
            logger.warning("속도 제한 초과, 1초 대기 후 재시도 (%d/3)", attempt + 1)
            time.sleep(1)
            continue
        resp.raise_for_status()
        return resp.json()
    resp.raise_for_status()
    return {}


def _post(path: str, tr_id: str, body: dict[str, Any]) -> dict[str, Any]:
    """POST 요청 헬퍼."""
    url = f"{config.BASE_URL}{path}"
    resp = requests.post(url, headers=_headers(tr_id), json=body, timeout=10)
    resp.raise_for_status()
    return resp.json()


# ── 시세 조회 ──────────────────────────────────────────────────────────────────

def get_etf_price(ticker: str) -> dict[str, Any]:
    """ETF 현재가 및 기본 정보를 조회합니다."""
    tr_id = "FHKST01010100"
    params = {
        "fid_cond_mrkt_div_code": "J",
        "fid_input_iscd": ticker,
    }
    return _get("/uapi/domestic-stock/v1/quotations/inquire-price", tr_id, params)


def get_minute_candles(ticker: str, interval: str = "5") -> list[dict[str, Any]]:
    """분봉 데이터를 조회합니다 (최대 30개)."""
    tr_id = "FHKST03010200"
    now = datetime.now().strftime("%H%M%S")
    params = {
        "fid_etc_cls_code": "",
        "fid_cond_mrkt_div_code": "J",
        "fid_input_iscd": ticker,
        "fid_input_hour_1": now,
        "fid_pw_data_incu_yn": "N",
    }
    data = _get("/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice", tr_id, params)
    return data.get("output2", [])


def get_volume_rank() -> list[dict[str, Any]]:
    """거래량 상위 ETF 목록을 조회합니다."""
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
    data = _get("/uapi/domestic-stock/v1/ranking/volume", tr_id, params)
    return data.get("output", [])


def get_fluctuation_rank() -> list[dict[str, Any]]:
    """등락률 상위 ETF 목록을 조회합니다."""
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
        "fid_trgt_cls_code": "111111111",
        "fid_trgt_exls_cls_code": "000000",
        "fid_div_cls_code": "0",
        "fid_rsfl_rate1": "",
        "fid_rsfl_rate2": "",
    }
    data = _get("/uapi/domestic-stock/v1/ranking/fluctuation", tr_id, params)
    return data.get("output", [])


# ── 잔고 조회 ──────────────────────────────────────────────────────────────────

def get_balance() -> dict[str, Any]:
    """주식 잔고를 조회합니다."""
    tr_id = "VTTC8434R" if config.IS_PAPER_TRADING else "TTTC8434R"
    params = {
        "CANO": config.CANO,
        "ACNT_PRDT_CD": config.ACNT_PRDT_CD,
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
    return _get("/uapi/domestic-stock/v1/trading/inquire-balance", tr_id, params)


# ── 주문 ───────────────────────────────────────────────────────────────────────

def place_order(ticker: str, qty: int, price: int, order_type: str) -> dict[str, Any]:
    """
    주식 주문을 제출합니다.

    Parameters
    ----------
    ticker : str
        종목코드
    qty : int
        수량
    price : int
        주문 가격 (시장가 주문 시 0)
    order_type : str
        "buy" 또는 "sell"
    """
    if order_type == "buy":
        tr_id = "VTTC0802U" if config.IS_PAPER_TRADING else "TTTC0802U"
        sll_buy_dvsn_cd = "02"  # 매수
    else:
        tr_id = "VTTC0801U" if config.IS_PAPER_TRADING else "TTTC0801U"
        sll_buy_dvsn_cd = "01"  # 매도

    # 시장가 주문이면 ORD_DVSN=01, 지정가면 00
    ord_dvsn = "01" if price == 0 else "00"
    ord_unpr = "0" if price == 0 else str(price)

    body = {
        "CANO": config.CANO,
        "ACNT_PRDT_CD": config.ACNT_PRDT_CD,
        "PDNO": ticker,
        "ORD_DVSN": ord_dvsn,
        "ORD_QTY": str(qty),
        "ORD_UNPR": ord_unpr,
        "SLL_BUY_DVSN_CD": sll_buy_dvsn_cd,
    }
    result = _post("/uapi/domestic-stock/v1/trading/order-cash", tr_id, body)
    logger.info("[주문] %s %s %d주 @ %s → %s", order_type.upper(), ticker, qty, ord_unpr, result.get("rt_cd"))
    return result
