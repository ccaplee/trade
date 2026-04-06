"""
Main trading loop.

Orchestrates:
1. Pre-market ETF selection
2. Per-tick signal evaluation
3. Order placement with risk management
4. Position tracking (stop-loss / take-profit)
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from datetime import datetime

import config
import kis_api
import strategy

# ── Logging setup ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("trader")


# ── Position tracking ──────────────────────────────────────────────────────────

@dataclass
class Position:
    ticker: str
    quantity: int
    buy_price: float
    invested: float  # cash amount invested


@dataclass
class Portfolio:
    positions: dict[str, Position] = field(default_factory=dict)

    def has_position(self, ticker: str) -> bool:
        return ticker in self.positions

    def add(self, pos: Position) -> None:
        self.positions[pos.ticker] = pos

    def remove(self, ticker: str) -> None:
        self.positions.pop(ticker, None)

    def total_invested(self) -> float:
        return sum(p.invested for p in self.positions.values())


# ── Time helpers ───────────────────────────────────────────────────────────────

def _now_hhmm() -> str:
    return datetime.now().strftime("%H:%M")


def _is_market_open() -> bool:
    now = _now_hhmm()
    return config.MARKET_OPEN_TIME <= now < config.MARKET_CLOSE_TIME


def _is_past_trading_start() -> bool:
    """Wait TRADING_START_OFFSET_MINUTES after market opens before trading."""
    open_h, open_m = map(int, config.MARKET_OPEN_TIME.split(":"))
    start_m = open_m + config.TRADING_START_OFFSET_MINUTES
    start_h = open_h + start_m // 60
    start_m = start_m % 60
    start_str = f"{start_h:02d}:{start_m:02d}"
    return _now_hhmm() >= start_str


# ── Core logic ─────────────────────────────────────────────────────────────────

def select_watchlist() -> list[str]:
    """Screen ETF universe and return today's watchlist."""
    logger.info("Screening ETF universe for top %d candidates …", config.TOP_N_ETF)
    return strategy.select_top_etfs()


def compute_position_size(ticker: str, price: float, cash_balance: float, total_portfolio_value: float) -> int:
    """
    Determine how many shares to buy subject to the config.MAX_POSITION_RATIO cap.

    Returns 0 if the order would be too small (< 1 share).
    """
    max_invest = total_portfolio_value * config.MAX_POSITION_RATIO
    affordable = min(max_invest, cash_balance)
    quantity = math.floor(affordable / price)
    return max(quantity, 0)


def evaluate_ticker(ticker: str, portfolio: Portfolio, cash_balance: float, total_value: float) -> None:
    """Evaluate one ticker: fetch candles, compute signals, place orders."""
    try:
        candles = kis_api.get_minute_candles(ticker, n_candles=config.MA_LONG + 5)
    except Exception as exc:
        logger.warning("Failed to fetch candles for %s: %s", ticker, exc)
        return

    df = strategy.compute_indicators(candles)
    if df is None:
        logger.debug("%s: insufficient candle data, skipping.", ticker)
        return

    # ── Check open position for exit ──────────────────────────────────────────
    if portfolio.has_position(ticker):
        pos = portfolio.positions[ticker]
        try:
            current_price = kis_api.get_current_price(ticker)
        except Exception as exc:
            logger.warning("Failed to get price for %s: %s", ticker, exc)
            return

        sell, reason = strategy.should_sell(current_price, pos.buy_price)
        if sell:
            logger.info("SELL %s × %d @ %.0f (%s)", ticker, pos.quantity, current_price, reason)
            try:
                kis_api.sell_market_order(ticker, pos.quantity)
                portfolio.remove(ticker)
            except Exception as exc:
                logger.error("Sell order failed for %s: %s", ticker, exc)
        return  # already in position; no new buy

    # ── Check for entry signal ────────────────────────────────────────────────
    buy, reason = strategy.should_buy(df)
    if not buy:
        return

    try:
        current_price = kis_api.get_current_price(ticker)
    except Exception as exc:
        logger.warning("Failed to get price for %s: %s", ticker, exc)
        return

    quantity = compute_position_size(ticker, current_price, cash_balance, total_value)
    if quantity <= 0:
        logger.info("Insufficient funds to buy %s (price=%.0f).", ticker, current_price)
        return

    logger.info("BUY %s × %d @ %.0f (%s)", ticker, quantity, current_price, reason)
    try:
        kis_api.buy_market_order(ticker, quantity)
        invested = quantity * current_price
        portfolio.add(Position(ticker, quantity, current_price, invested))
    except Exception as exc:
        logger.error("Buy order failed for %s: %s", ticker, exc)


def _current_portfolio_market_value(portfolio: Portfolio) -> float:
    """Sum of current market value across all open positions."""
    total = 0.0
    for ticker, pos in portfolio.positions.items():
        try:
            total += kis_api.get_current_price(ticker) * pos.quantity
        except Exception as exc:
            logger.warning("Could not fetch current price for %s, using cost basis: %s", ticker, exc)
            total += pos.invested
    return total

(portfolio: Portfolio) -> None:
    """Liquidate all open positions at market price (end-of-day)."""
    for ticker, pos in list(portfolio.positions.items()):
        logger.info("EOD close: SELL %s × %d", ticker, pos.quantity)
        try:
            kis_api.sell_market_order(ticker, pos.quantity)
            portfolio.remove(ticker)
        except Exception as exc:
            logger.error("EOD sell failed for %s: %s", ticker, exc)


# ── Main loop ──────────────────────────────────────────────────────────────────

def run() -> None:
    logger.info("=== KIS ETF Auto-Trader started (mode=%s) ===", config.TRADING_MODE)

    portfolio = Portfolio()
    watchlist: list[str] = []
    watchlist_date: str = ""

    while True:
        today = datetime.now().strftime("%Y-%m-%d")

        if not _is_market_open():
            if portfolio.positions:
                logger.info("Market closed. Closing remaining positions …")
                close_all_positions(portfolio)
            logger.info("Market is closed. Sleeping 60 s …")
            time.sleep(60)
            continue

        # Build watchlist once per trading day
        if watchlist_date != today and _is_past_trading_start():
            watchlist = select_watchlist()
            watchlist_date = today

        if not watchlist:
            logger.info("Watchlist not ready yet. Sleeping %d s …", config.POLL_INTERVAL_SECONDS)
            time.sleep(config.POLL_INTERVAL_SECONDS)
            continue

        # Fetch portfolio value for position sizing
        try:
            cash_balance = kis_api.get_balance()
        except Exception as exc:
            logger.warning("Failed to fetch balance: %s", exc)
            time.sleep(config.POLL_INTERVAL_SECONDS)
            continue

        invested_value = _current_portfolio_market_value(portfolio)
        total_value = cash_balance + invested_value

        logger.info(
            "Tick | cash=%.0f invested=%.0f total=%.0f | positions=%s",
            cash_balance, invested_value, total_value,
            list(portfolio.positions.keys()) or "none",
        )

        for ticker in watchlist:
            evaluate_ticker(ticker, portfolio, cash_balance, total_value)

        time.sleep(config.POLL_INTERVAL_SECONDS)


if __name__ == "__main__":
    run()
