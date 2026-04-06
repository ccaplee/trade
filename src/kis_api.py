"""
KIS (한국투자증권) Open API 클라이언트 모듈

REST API 및 WebSocket을 통해 시세 조회, 주문 실행, 잔고 조회 기능을 제공합니다.
"""

import json
import time
import hashlib
import asyncio
import requests
import websockets
from datetime import datetime, timedelta
from typing import Optional, Callable
from loguru import logger


class KISAuth:
    """KIS API 인증 관리 클래스"""

    def __init__(self, app_key: str, app_secret: str, base_url: str, is_mock: bool = True):
        self.app_key = app_key
        self.app_secret = app_secret
        self.base_url = base_url
        self.is_mock = is_mock
        self._access_token: Optional[str] = None
        self._token_expires_at: Optional[datetime] = None

    def get_access_token(self) -> str:
        """액세스 토큰 발급 (만료 시 자동 재발급)"""
        if self._access_token and self._token_expires_at:
            if datetime.now() < self._token_expires_at - timedelta(minutes=10):
                return self._access_token

        url = f"{self.base_url}/oauth2/tokenP"
        payload = {
            "grant_type": "client_credentials",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
        }
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        data = response.json()

        self._access_token = data["access_token"]
        expires_in = int(data.get("expires_in", 86400))
        self._token_expires_at = datetime.now() + timedelta(seconds=expires_in)
        logger.info("액세스 토큰 발급 완료 (만료: {})", self._token_expires_at)
        return self._access_token

    def get_headers(self, tr_id: str, extra: Optional[dict] = None) -> dict:
        """API 요청 공통 헤더 생성"""
        headers = {
            "content-type": "application/json; charset=utf-8",
            "authorization": f"Bearer {self.get_access_token()}",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
            "tr_id": tr_id,
        }
        if self.is_mock:
            headers["custtype"] = "P"
        if extra:
            headers.update(extra)
        return headers

    def get_hashkey(self, body: dict) -> str:
        """주문 시 사용하는 해시키 발급"""
        url = f"{self.base_url}/uapi/hashkey"
        headers = {
            "content-type": "application/json; charset=utf-8",
            "appkey": self.app_key,
            "appsecret": self.app_secret,
        }
        response = requests.post(url, headers=headers, json=body, timeout=10)
        response.raise_for_status()
        return response.json()["HASH"]


class KISClient:
    """KIS Open API REST 클라이언트"""

    # 거래ID 매핑 (모의/실투자)
    _TR_IDS = {
        "buy": {"mock": "VTTC0802U", "real": "TTTC0802U"},
        "sell": {"mock": "VTTC0801U", "real": "TTTC0801U"},
        "balance": {"mock": "VTTC8434R", "real": "TTTC8434R"},
        "price": {"mock": "FHKST01010100", "real": "FHKST01010100"},
        "orderbook": {"mock": "FHKST01010200", "real": "FHKST01010200"},
        "daily_price": {"mock": "FHKST01010400", "real": "FHKST01010400"},
    }

    def __init__(self, auth: KISAuth, account_no: str, account_product_code: str):
        self.auth = auth
        self.account_no = account_no
        self.account_product_code = account_product_code
        self._env = "mock" if auth.is_mock else "real"

    def _tr_id(self, key: str) -> str:
        return self._TR_IDS[key][self._env]

    def get_current_price(self, stock_code: str) -> dict:
        """현재가 조회"""
        url = f"{self.auth.base_url}/uapi/domestic-stock/v1/quotations/inquire-price"
        headers = self.auth.get_headers(self._tr_id("price"))
        params = {
            "fid_cond_mrkt_div_code": "J",
            "fid_input_iscd": stock_code,
        }
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data["rt_cd"] != "0":
            raise RuntimeError(f"현재가 조회 실패: {data['msg1']}")
        output = data["output"]
        return {
            "stock_code": stock_code,
            "current_price": int(output["stck_prpr"]),
            "open_price": int(output["stck_oprc"]),
            "high_price": int(output["stck_hgpr"]),
            "low_price": int(output["stck_lwpr"]),
            "prev_close": int(output["stck_sdpr"]),
            "volume": int(output["acml_vol"]),
            "change_rate": float(output["prdy_ctrt"]),
            "ask_price": int(output["askp1"]) if output.get("askp1") else 0,
            "bid_price": int(output["bidp1"]) if output.get("bidp1") else 0,
        }

    def get_daily_prices(self, stock_code: str, period: int = 30) -> list[dict]:
        """일별 시세 조회 (전략 지표 계산용)"""
        url = f"{self.auth.base_url}/uapi/domestic-stock/v1/quotations/inquire-daily-price"
        headers = self.auth.get_headers(self._tr_id("daily_price"))
        params = {
            "fid_cond_mrkt_div_code": "J",
            "fid_input_iscd": stock_code,
            "fid_org_adj_prc": "1",
            "fid_period_div_code": "D",
        }
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data["rt_cd"] != "0":
            raise RuntimeError(f"일별 시세 조회 실패: {data['msg1']}")
        result = []
        for item in data.get("output2", [])[:period]:
            result.append({
                "date": item["stck_bsop_date"],
                "open": int(item["stck_oprc"]),
                "high": int(item["stck_hgpr"]),
                "low": int(item["stck_lwpr"]),
                "close": int(item["stck_clpr"]),
                "volume": int(item["acml_vol"]),
            })
        return result

    def get_minute_prices(self, stock_code: str) -> list[dict]:
        """분봉 시세 조회"""
        url = f"{self.auth.base_url}/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice"
        headers = self.auth.get_headers("FHKST03010200")
        now = datetime.now().strftime("%H%M%S")
        params = {
            "fid_etc_cls_code": "",
            "fid_cond_mrkt_div_code": "J",
            "fid_input_iscd": stock_code,
            "fid_input_hour_1": now,
            "fid_pw_data_incu_yn": "Y",
        }
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data["rt_cd"] != "0":
            raise RuntimeError(f"분봉 조회 실패: {data['msg1']}")
        result = []
        for item in data.get("output2", []):
            result.append({
                "time": item["stck_cntg_hour"],
                "open": int(item["stck_oprc"]),
                "high": int(item["stck_hgpr"]),
                "low": int(item["stck_lwpr"]),
                "close": int(item["stck_prpr"]),
                "volume": int(item["cntg_vol"]),
            })
        return result

    def get_balance(self) -> dict:
        """잔고 조회"""
        url = f"{self.auth.base_url}/uapi/domestic-stock/v1/trading/inquire-balance"
        headers = self.auth.get_headers(self._tr_id("balance"))
        params = {
            "CANO": self.account_no,
            "ACNT_PRDT_CD": self.account_product_code,
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
        response = requests.get(url, headers=headers, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        if data["rt_cd"] != "0":
            raise RuntimeError(f"잔고 조회 실패: {data['msg1']}")

        holdings = {}
        for item in data.get("output1", []):
            code = item["pdno"]
            qty = int(item["hldg_qty"])
            if qty > 0:
                holdings[code] = {
                    "stock_code": code,
                    "stock_name": item["prdt_name"],
                    "quantity": qty,
                    "avg_price": float(item["pchs_avg_pric"]),
                    "current_price": int(item["prpr"]),
                    "eval_profit_loss": int(item["evlu_pfls_amt"]),
                    "profit_loss_rate": float(item["evlu_pfls_rt"]),
                }

        summary = data.get("output2", [{}])[0]
        return {
            "holdings": holdings,
            "total_eval_amount": int(summary.get("tot_evlu_amt", 0)),
            "available_cash": int(summary.get("nass_amt", 0)),
            "total_profit_loss": int(summary.get("evlu_pfls_smtl_amt", 0)),
        }

    def place_order(self, stock_code: str, order_type: str, quantity: int, price: int = 0) -> dict:
        """주문 실행

        Args:
            stock_code: 종목 코드
            order_type: "buy" 또는 "sell"
            quantity: 수량
            price: 지정가 주문 시 가격 (0이면 시장가)
        """
        url = f"{self.auth.base_url}/uapi/domestic-stock/v1/trading/order-cash"
        tr_id = self._tr_id(order_type)

        # 시장가: ORD_DVSN=01, 지정가: ORD_DVSN=00
        ord_dvsn = "01" if price == 0 else "00"
        ord_unpr = "0" if price == 0 else str(price)

        body = {
            "CANO": self.account_no,
            "ACNT_PRDT_CD": self.account_product_code,
            "PDNO": stock_code,
            "ORD_DVSN": ord_dvsn,
            "ORD_QTY": str(quantity),
            "ORD_UNPR": ord_unpr,
        }

        hashkey = self.auth.get_hashkey(body)
        headers = self.auth.get_headers(tr_id, {"hashkey": hashkey})

        response = requests.post(url, headers=headers, json=body, timeout=10)
        response.raise_for_status()
        data = response.json()

        if data["rt_cd"] != "0":
            raise RuntimeError(f"주문 실패 [{order_type}] {stock_code}: {data['msg1']}")

        output = data["output"]
        logger.info(
            "주문 완료 | {} {} {}주 (주문번호: {})",
            order_type.upper(), stock_code, quantity, output.get("ODNO", "N/A")
        )
        return {
            "order_no": output.get("ODNO"),
            "order_time": output.get("ORD_TMD"),
            "stock_code": stock_code,
            "order_type": order_type,
            "quantity": quantity,
            "price": price,
        }


class KISWebSocket:
    """KIS WebSocket 실시간 시세 클라이언트"""

    def __init__(self, auth: KISAuth, ws_url: str):
        self.auth = auth
        self.ws_url = ws_url
        self._approval_key: Optional[str] = None
        self._callbacks: dict[str, Callable] = {}

    def get_approval_key(self) -> str:
        """WebSocket 접속키 발급"""
        if self._approval_key:
            return self._approval_key
        url = f"{self.auth.base_url}/oauth2/Approval"
        payload = {
            "grant_type": "client_credentials",
            "appkey": self.auth.app_key,
            "secretkey": self.auth.app_secret,
        }
        response = requests.post(url, json=payload, timeout=10)
        response.raise_for_status()
        self._approval_key = response.json()["approval_key"]
        return self._approval_key

    def register_callback(self, stock_code: str, callback: Callable):
        """종목별 시세 수신 콜백 등록"""
        self._callbacks[stock_code] = callback

    async def subscribe_realtime_price(self, stock_codes: list[str]):
        """실시간 체결가 WebSocket 구독"""
        approval_key = self.get_approval_key()

        async with websockets.connect(self.ws_url) as ws:
            # 종목별 구독 요청
            for code in stock_codes:
                subscribe_msg = {
                    "header": {
                        "approval_key": approval_key,
                        "custtype": "P",
                        "tr_type": "1",
                        "content-type": "utf-8",
                    },
                    "body": {
                        "input": {
                            "tr_id": "H0STCNT0",  # 실시간 체결가
                            "tr_key": code,
                        }
                    },
                }
                await ws.send(json.dumps(subscribe_msg))
                await asyncio.sleep(0.1)

            logger.info("WebSocket 실시간 시세 구독 시작: {}", stock_codes)

            async for message in ws:
                try:
                    if message[0] == "0" or message[0] == "1":
                        # 실시간 데이터 처리
                        parts = message.split("|")
                        if len(parts) >= 4:
                            tr_id = parts[1]
                            data_cnt = parts[2]
                            raw_data = parts[3]
                            if tr_id == "H0STCNT0":
                                await self._handle_price_data(raw_data)
                    else:
                        # 시스템 메시지
                        msg_data = json.loads(message)
                        tr_id = msg_data.get("header", {}).get("tr_id", "")
                        if tr_id == "PINGPONG":
                            await ws.send(message)
                except Exception as e:
                    logger.warning("WebSocket 메시지 처리 오류: {}", e)

    async def _handle_price_data(self, raw_data: str):
        """실시간 체결가 데이터 파싱 및 콜백 호출"""
        fields = raw_data.split("^")
        if len(fields) < 13:
            return

        stock_code = fields[0]
        price_data = {
            "stock_code": stock_code,
            "current_price": int(fields[2]),
            "change_rate": float(fields[5]) if fields[5] else 0.0,
            "volume": int(fields[9]),
            "ask_price": int(fields[10]) if fields[10] else 0,
            "bid_price": int(fields[11]) if fields[11] else 0,
            "timestamp": fields[1],
        }

        callback = self._callbacks.get(stock_code)
        if callback:
            if asyncio.iscoroutinefunction(callback):
                await callback(price_data)
            else:
                callback(price_data)
