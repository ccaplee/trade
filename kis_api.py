"""
KIS REST API 래퍼 - 시세 조회 및 주문 관련 API 호출
"""
import logging
from typing import Any

import requests

import config
import kis_auth

logger = logging.getLogger(__name__)

_SESSION = requests.Session()
_SESSION.headers.update({"Content-Type": "application/json; charset=utf-8"})


def _get(path: str, tr_id: str, params: dict) -> dict:
    """GET 요청 공통 처리"""
    url = config.BASE_URL + path
    headers = kis_auth.get_headers(tr_id)
    resp = _SESSION.get(url, headers=headers, params=params, timeout=10)
    resp.raise_for_status()
    body: dict = resp.json()
    if body.get("rt_cd") != "0":
        raise RuntimeError(f"API 오류 [{tr_id}]: {body.get('msg1', body)}")
    return body


def _post(path: str, tr_id: str, payload: dict) -> dict:
    """POST 요청 공통 처리"""
    url = config.BASE_URL + path
    headers = kis_auth.get_headers(tr_id)
    resp = _SESSION.post(url, headers=headers, json=payload, timeout=10)
    resp.raise_for_status()
    body: dict = resp.json()
    if body.get("rt_cd") != "0":
        raise RuntimeError(f"API 오류 [{tr_id}]: {body.get('msg1', body)}")
    return body


# ─── 시세 조회 ────────────────────────────────────────────────

def get_price(stock_code: str) -> dict[str, Any]:
    """
    주식 현재가 조회
    반환 예: {"stck_prpr": 현재가, "prdy_vrss_sign": 부호, "prdy_ctrt": 등락률, ...}
    """
    body = _get(
        "/uapi/domestic-stock/v1/quotations/inquire-price",
        tr_id="FHKST01010100",
        params={"fid_cond_mrkt_div_code": "J", "fid_input_iscd": stock_code},
    )
    return body["output"]


def get_volume_rank(
    market_code: str = "0000",
    sort_field: str = "1",
    etf_only: bool = True,
    count: int = 30,
) -> list[dict]:
    """
    거래량 순위 조회 (ETP/ETF 포함)

    Args:
        market_code: 시장 코드 (0000: 전체, 0001: 코스피, 1001: 코스닥)
        sort_field: 정렬 기준 (1: 거래량, 2: 거래대금)
        etf_only: True 이면 ETF 종목만 반환
        count: 조회 개수
    """
    body = _get(
        "/uapi/domestic-stock/v1/quotations/volume-rank",
        tr_id="FHPST01710000",
        params={
            "fid_cond_mrkt_div_code": "J",
            "fid_cond_scr_div_code": "20171",
            "fid_input_iscd": market_code,
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
    items: list[dict] = body.get("output", [])
    if etf_only:
        items = [i for i in items if i.get("mrkt_cls_code", "").startswith("E")]
    return items[:count]


def get_fluctuation_rank(
    market_code: str = "0000",
    sort_type: str = "1",
    count: int = 30,
) -> list[dict]:
    """
    등락률 순위 조회

    Args:
        market_code: 시장 코드
        sort_type: 1: 상승률, 2: 하락률
        count: 조회 개수
    """
    body = _get(
        "/uapi/domestic-stock/v1/quotations/inquire-daily-itemchartprice",
        tr_id="FHPST01720000",
        params={
            "fid_cond_mrkt_div_code": "J",
            "fid_cond_scr_div_code": "20172",
            "fid_input_iscd": market_code,
            "fid_rank_sort_cls_code": sort_type,
            "fid_input_cnt_1": "0",
            "fid_prc_cls_code": "1",
            "fid_input_price_1": "",
            "fid_input_price_2": "",
            "fid_vol_cnt": "",
            "fid_trgt_cls_code": "111111111",
            "fid_trgt_exls_cls_code": "000000",
            "fid_div_cls_code": "0",
            "fid_rsfl_rate1": "",
            "fid_rsfl_rate2": "",
        },
    )
    items: list[dict] = body.get("output", [])
    items = [i for i in items if i.get("mrkt_cls_code", "").startswith("E")]
    return items[:count]


def get_minute_candle(stock_code: str, time_str: str = "093000") -> list[dict]:
    """
    분봉 데이터 조회 (체결량 포함)

    Args:
        stock_code: 종목 코드
        time_str: 기준 시각 (HHMMSS)
    """
    body = _get(
        "/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice",
        tr_id="FHKST03010200",
        params={
            "fid_etc_cls_code": "",
            "fid_cond_mrkt_div_code": "J",
            "fid_input_iscd": stock_code,
            "fid_input_hour_1": time_str,
            "fid_pw_data_incu_yn": "Y",
        },
    )
    return body.get("output2", [])


def get_balance() -> dict[str, Any]:
    """
    주식 잔고 조회
    반환: {"holdings": [{code, name, qty, avg_price, current_price, profit_rate}], "available_cash": int}
    """
    body = _get(
        "/uapi/domestic-stock/v1/trading/inquire-balance",
        tr_id=f"{config.TR_ID_PREFIX}TTT5201R",
        params={
            "CANO": config.ACCOUNT_NO,
            "ACNT_PRDT_CD": config.ACCOUNT_PRODUCT_CODE,
            "AFHR_FLPR_YN": "N",
            "OFL_YN": "",
            "INQR_DVSN": "02",
            "UNPR_DVSN": "01",
            "FUND_STTL_ICLD_YN": "N",
            "FNCG_AMT_AUTO_RDPT_YN": "N",
            "PRCS_DVSN": "01",
            "CTX_AREA_FK100": "",
            "CTX_AREA_NK100": "",
        },
    )
    holdings = []
    for item in body.get("output1", []):
        qty = int(item.get("hldg_qty", "0"))
        if qty <= 0:
            continue
        holdings.append(
            {
                "code": item["pdno"],
                "name": item["prdt_name"],
                "qty": qty,
                "avg_price": float(item.get("pchs_avg_pric", "0")),
                "current_price": int(item.get("prpr", "0")),
                "profit_rate": float(item.get("evlu_pfls_rt", "0")),
            }
        )
    output2 = body.get("output2", [{}])
    available_cash = int(output2[0].get("dnca_tot_amt", "0")) if output2 else 0
    return {"holdings": holdings, "available_cash": available_cash}


def place_order(
    stock_code: str,
    order_type: str,      # "buy" | "sell"
    quantity: int,
    price: int = 0,       # 0 이면 시장가
) -> dict[str, Any]:
    """
    주식 주문 (시장가 / 지정가)

    Args:
        stock_code: 종목 코드
        order_type: "buy" 또는 "sell"
        quantity: 주문 수량
        price: 주문 가격 (0이면 시장가)
    """
    if order_type == "buy":
        tr_id = f"{config.TR_ID_PREFIX}TTT1002U"
    else:
        tr_id = f"{config.TR_ID_PREFIX}TTT1006U"

    ord_dvsn = "01" if price == 0 else "00"  # 01: 시장가, 00: 지정가

    payload = {
        "CANO": config.ACCOUNT_NO,
        "ACNT_PRDT_CD": config.ACCOUNT_PRODUCT_CODE,
        "PDNO": stock_code,
        "ORD_DVSN": ord_dvsn,
        "ORD_QTY": str(quantity),
        "ORD_UNPR": str(price),
    }
    body = _post(
        "/uapi/domestic-stock/v1/trading/order-cash",
        tr_id=tr_id,
        payload=payload,
    )
    logger.info(
        "주문 완료 [%s] %s %s주 @%s원 → 주문번호:%s",
        order_type, stock_code, quantity, price or "시장가",
        body.get("output", {}).get("odno", "N/A"),
    )
    return body["output"]
