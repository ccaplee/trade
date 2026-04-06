# kis_api.py - 한국투자증권 KIS Open API REST 연동 모듈

import time
import logging
from datetime import datetime
from typing import Optional

import requests

import config

logger = logging.getLogger(__name__)


class KISApi:
    """KIS Open API 클라이언트.

    인증 토큰을 자동으로 발급·갱신하며
    시세조회, 주문, 잔고 조회 기능을 제공합니다.
    """

    # 거래소 코드
    EXCH_CODE = "J"   # 코스피/ETF

    def __init__(self):
        self._access_token: Optional[str] = None
        self._token_expired_at: float = 0.0
        self.session = requests.Session()
        self.session.headers.update({"Content-Type": "application/json"})

    # ── 인증 ────────────────────────────────────────────────────────────────────

    def _ensure_token(self) -> str:
        """액세스 토큰이 유효한지 확인하고, 만료 시 재발급합니다."""
        if self._access_token and time.time() < self._token_expired_at:
            return self._access_token
        return self._issue_token()

    def _issue_token(self) -> str:
        """OAuth 2.0 액세스 토큰을 발급합니다."""
        url = f"{config.BASE_URL}/oauth2/tokenP"
        body = {
            "grant_type": "client_credentials",
            "appkey": config.APP_KEY,
            "appsecret": config.APP_SECRET,
        }
        resp = self.session.post(url, json=body, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        self._access_token = data["access_token"]
        # 만료 1분 전에 갱신할 수 있도록 여유를 둡니다
        self._token_expired_at = time.time() + int(data.get("expires_in", 86400)) - 60
        logger.info("액세스 토큰 발급 완료")
        return self._access_token

    def _auth_headers(self, tr_id: str) -> dict:
        """인증 헤더를 구성합니다."""
        return {
            "authorization": f"Bearer {self._ensure_token()}",
            "appkey": config.APP_KEY,
            "appsecret": config.APP_SECRET,
            "tr_id": tr_id,
            "custtype": "P",
        }

    # ── 시세 조회 ────────────────────────────────────────────────────────────────

    def get_current_price(self, ticker: str) -> dict:
        """현재가 조회.

        Returns:
            dict with keys: ticker, current_price, open_price, high_price,
                            low_price, volume, change_rate
        """
        url = f"{config.BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-price"
        params = {
            "FID_COND_MRKT_DIV_CODE": self.EXCH_CODE,
            "FID_INPUT_ISCD": ticker,
        }
        resp = self.session.get(
            url,
            headers=self._auth_headers("FHKST01010100"),
            params=params,
            timeout=10,
        )
        resp.raise_for_status()
        output = resp.json().get("output", {})
        return {
            "ticker": ticker,
            "current_price": float(output.get("stck_prpr", 0)),
            "open_price": float(output.get("stck_oprc", 0)),
            "high_price": float(output.get("stck_hgpr", 0)),
            "low_price": float(output.get("stck_lwpr", 0)),
            "volume": int(output.get("acml_vol", 0)),
            "change_rate": float(output.get("prdy_ctrt", 0)),
        }

    def get_minute_candles(self, ticker: str, interval: int = 5) -> list[dict]:
        """분봉 데이터 조회.

        Args:
            ticker: 종목 코드
            interval: 분봉 단위 (기본 5분봉)

        Returns:
            list of dict with keys: time, open, high, low, close, volume
            최신 데이터가 list[0]에 위치합니다.
        """
        url = f"{config.BASE_URL}/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice"
        now_str = datetime.now().strftime("%H%M%S")
        params = {
            "FID_ETC_CLS_CODE": "",
            "FID_COND_MRKT_DIV_CODE": self.EXCH_CODE,
            "FID_INPUT_ISCD": ticker,
            "FID_INPUT_HOUR_1": now_str,
            "FID_PW_DATA_INCU_YN": "Y",
        }
        resp = self.session.get(
            url,
            headers=self._auth_headers("FHKST03010200"),
            params=params,
            timeout=10,
        )
        resp.raise_for_status()
        raw_list = resp.json().get("output2", [])

        candles = []
        for item in raw_list:
            candles.append(
                {
                    "time": item.get("stck_bsop_date", "") + item.get("stck_cntg_hour", ""),
                    "open": float(item.get("stck_oprc", 0)),
                    "high": float(item.get("stck_hgpr", 0)),
                    "low": float(item.get("stck_lwpr", 0)),
                    "close": float(item.get("stck_prpr", 0)),
                    "volume": int(item.get("cntg_vol", 0)),
                }
            )
        return candles

    def get_top_volume_etfs(self, top_n: int = 5) -> list[str]:
        """거래량 상위 ETF 종목 코드 목록을 반환합니다.

        config.ETF_UNIVERSE 풀에서 현재 거래량이 많고 변동성이 큰 상위 top_n 개를 선별합니다.
        """
        candidates = []
        for ticker in config.ETF_UNIVERSE:
            try:
                info = self.get_current_price(ticker)
                score = info["volume"] * abs(info["change_rate"])
                candidates.append((ticker, score))
            except Exception as exc:
                logger.warning("시세 조회 실패 [%s]: %s", ticker, exc)

        candidates.sort(key=lambda x: x[1], reverse=True)
        selected = [ticker for ticker, _ in candidates[:top_n]]
        logger.info("선별된 ETF: %s", selected)
        return selected

    # ── 잔고 조회 ────────────────────────────────────────────────────────────────

    def get_balance(self) -> dict:
        """주식 잔고 및 예수금 조회.

        Returns:
            {
                "cash": float,            # 주문 가능 예수금
                "positions": {
                    ticker: {
                        "qty": int,
                        "avg_price": float,
                        "eval_amount": float,
                    }
                }
            }
        """
        url = f"{config.BASE_URL}/uapi/domestic-stock/v1/trading/inquire-balance"
        tr_id = "VTTC8434R" if config.IS_PAPER_TRADING else "TTTC8434R"
        params = {
            "CANO": config.ACCOUNT_NO,
            "ACNT_PRDT_CD": config.ACCOUNT_CODE,
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
        resp = self.session.get(
            url,
            headers=self._auth_headers(tr_id),
            params=params,
            timeout=10,
        )
        resp.raise_for_status()
        body = resp.json()

        cash = float(body.get("output2", [{}])[0].get("dnca_tot_amt", 0))
        positions = {}
        for item in body.get("output1", []):
            ticker = item.get("pdno", "")
            qty = int(item.get("hldg_qty", 0))
            if ticker and qty > 0:
                positions[ticker] = {
                    "qty": qty,
                    "avg_price": float(item.get("pchs_avg_pric", 0)),
                    "eval_amount": float(item.get("evlu_amt", 0)),
                }
        return {"cash": cash, "positions": positions}

    # ── 주문 ────────────────────────────────────────────────────────────────────

    def _order(self, ticker: str, side: str, qty: int, price: int = 0) -> dict:
        """주문 공통 처리.

        Args:
            ticker: 종목 코드
            side: "BUY" or "SELL"
            qty: 수량
            price: 지정가 (0이면 시장가)
        """
        url = f"{config.BASE_URL}/uapi/domestic-stock/v1/trading/order-cash"

        if config.IS_PAPER_TRADING:
            tr_id = "VTTC0802U" if side == "BUY" else "VTTC0801U"
        else:
            tr_id = "TTTC0802U" if side == "BUY" else "TTTC0801U"

        ord_dvsn = "01" if price == 0 else "00"   # 01: 시장가, 00: 지정가
        body = {
            "CANO": config.ACCOUNT_NO,
            "ACNT_PRDT_CD": config.ACCOUNT_CODE,
            "PDNO": ticker,
            "ORD_DVSN": ord_dvsn,
            "ORD_QTY": str(qty),
            "ORD_UNPR": str(price),
        }
        resp = self.session.post(
            url,
            headers=self._auth_headers(tr_id),
            json=body,
            timeout=10,
        )
        resp.raise_for_status()
        result = resp.json()
        rt_cd = result.get("rt_cd", "-1")
        msg = result.get("msg1", "")
        if rt_cd != "0":
            raise RuntimeError(f"주문 실패 [{ticker}] {side}: {msg}")
        logger.info("주문 완료 [%s] %s %d주 → %s", ticker, side, qty, msg)
        return result

    def buy(self, ticker: str, qty: int) -> dict:
        """시장가 매수."""
        return self._order(ticker, "BUY", qty)

    def sell(self, ticker: str, qty: int) -> dict:
        """시장가 매도."""
        return self._order(ticker, "SELL", qty)
