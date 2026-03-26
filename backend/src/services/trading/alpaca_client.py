"""
Alpaca Trading Client
Direct REST API wrapper for Alpaca Markets — replaces Lumibot dependency.
Handles: account info, order submission/tracking, position queries, quotes.

Uses aiohttp for async HTTP in the Celery worker (run via asyncio.run()).
For the synchronous Celery context we provide sync wrappers.
"""

import logging
import time
import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Dict, Any, Optional, List, Literal
from urllib.parse import quote
import requests

logger = logging.getLogger(__name__)


class AlpacaTradingClient:
    """
    Synchronous Alpaca REST client for use inside Celery tasks.
    Uses requests library for blocking HTTP calls.
    """

    PAPER_BASE_URL = "https://paper-api.alpaca.markets"
    LIVE_BASE_URL = "https://api.alpaca.markets"

    def __init__(self, api_key: str, secret_key: str, paper: bool = True):
        self.api_key = api_key
        self.secret_key = secret_key
        self.paper = paper
        self.base_url = self.PAPER_BASE_URL if paper else self.LIVE_BASE_URL
        self.headers = {
            "APCA-API-KEY-ID": api_key,
            "APCA-API-SECRET-KEY": secret_key,
            "Content-Type": "application/json",
        }

    # ==================== ACCOUNT ====================

    def get_account(self) -> Dict[str, Any]:
        """Get account information"""
        resp = requests.get(f"{self.base_url}/v2/account", headers=self.headers)
        resp.raise_for_status()
        return resp.json()

    def get_cash(self) -> float:
        """Get available cash balance"""
        account = self.get_account()
        return float(account.get("cash", 0))

    def get_portfolio_value(self) -> float:
        """Get total portfolio value from Alpaca"""
        account = self.get_account()
        return float(account.get("portfolio_value", 0))

    def get_buying_power(self) -> float:
        """Get buying power"""
        account = self.get_account()
        return float(account.get("buying_power", 0))

    # ==================== POSITIONS ====================

    def get_positions(self) -> List[Dict[str, Any]]:
        """Get all open positions from Alpaca"""
        resp = requests.get(f"{self.base_url}/v2/positions", headers=self.headers)
        resp.raise_for_status()
        return resp.json()

    def get_position(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get position for a specific symbol"""
        try:
            # URL-encode symbol — crypto uses slash like DOGE/USD
            encoded = quote(symbol, safe="")
            resp = requests.get(
                f"{self.base_url}/v2/positions/{encoded}",
                headers=self.headers,
            )
            if resp.status_code == 404:
                return None
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.HTTPError as e:
            if e.response and e.response.status_code == 404:
                return None
            raise

    def close_position(self, symbol: str) -> Dict[str, Any]:
        """Close entire position for a symbol via DELETE /v2/positions.
        Returns the liquidation order object."""
        encoded = quote(symbol, safe="")
        logger.info(f"Closing position via DELETE /v2/positions/{encoded}")
        resp = requests.delete(
            f"{self.base_url}/v2/positions/{encoded}",
            headers=self.headers,
        )
        if not resp.ok:
            logger.error(f"close_position {symbol} failed: {resp.status_code} {resp.text}")
        resp.raise_for_status()
        return resp.json()

    def close_all_positions(self) -> List[Dict[str, Any]]:
        """Close all positions"""
        resp = requests.delete(
            f"{self.base_url}/v2/positions",
            headers=self.headers,
        )
        resp.raise_for_status()
        return resp.json()

    # ==================== ORDERS ====================

    def submit_order(
        self,
        symbol: str,
        qty: float,
        side: Literal["buy", "sell"],
        order_type: str = "market",
        time_in_force: str = "gtc",
        limit_price: Optional[float] = None,
        stop_price: Optional[float] = None,
        stop_loss: Optional[Dict[str, Any]] = None,
        take_profit: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """
        Submit an order to Alpaca.

        For bracket orders, pass stop_loss and/or take_profit dicts:
            stop_loss={"stop_price": "95.50"}
            take_profit={"limit_price": "110.00"}
        """
        order_data = {
            "symbol": symbol,
            "qty": str(qty),
            "side": side,
            "type": order_type,
            "time_in_force": time_in_force,
        }
        if limit_price is not None:
            order_data["limit_price"] = str(limit_price)
        if stop_price is not None:
            order_data["stop_price"] = str(stop_price)

        # Bracket order
        if stop_loss or take_profit:
            order_data["order_class"] = "bracket"
            if stop_loss:
                order_data["stop_loss"] = stop_loss
            if take_profit:
                order_data["take_profit"] = take_profit

        logger.info(f"Submitting order: {order_data}")
        resp = requests.post(
            f"{self.base_url}/v2/orders",
            headers=self.headers,
            json=order_data,
        )
        if not resp.ok:
            logger.error(f"Order rejected: {resp.status_code} {resp.text}")
        resp.raise_for_status()
        result = resp.json()
        logger.info(f"Order submitted: {result.get('id')} status={result.get('status')}")
        return result

    def get_order(self, order_id: str) -> Dict[str, Any]:
        """Get order by ID"""
        resp = requests.get(
            f"{self.base_url}/v2/orders/{order_id}",
            headers=self.headers,
        )
        resp.raise_for_status()
        return resp.json()

    def cancel_order(self, order_id: str) -> None:
        """Cancel an order"""
        resp = requests.delete(
            f"{self.base_url}/v2/orders/{order_id}",
            headers=self.headers,
        )
        resp.raise_for_status()

    def list_orders(
        self,
        status: str = "open",
        limit: int = 50,
        direction: str = "desc",
    ) -> List[Dict[str, Any]]:
        """List orders with optional filters"""
        params = {"status": status, "limit": limit, "direction": direction}
        resp = requests.get(
            f"{self.base_url}/v2/orders",
            headers=self.headers,
            params=params,
        )
        resp.raise_for_status()
        return resp.json()

    def wait_for_order_fill(
        self, order_id: str, timeout: int = 30, poll_interval: float = 0.5
    ) -> Dict[str, Any]:
        """
        Poll until order is filled or timeout.
        Returns the order dict (with filled_avg_price, filled_qty, etc.)
        """
        deadline = time.time() + timeout
        while time.time() < deadline:
            order = self.get_order(order_id)
            status = order.get("status")
            if status in ("filled", "partially_filled"):
                return order
            if status in ("canceled", "expired", "rejected", "suspended"):
                logger.warning(f"Order {order_id} ended with status: {status}")
                return order
            time.sleep(poll_interval)

        logger.warning(f"Order {order_id} not filled within {timeout}s")
        return self.get_order(order_id)

    # ==================== MARKET DATA (snapshots) ====================

    def get_latest_quote(self, symbol: str, asset_type: str = "stock") -> Dict[str, Any]:
        """
        Get latest quote/trade for a symbol.
        Uses Alpaca data API.
        """
        if asset_type == "crypto":
            url = f"https://data.alpaca.markets/v1beta3/crypto/us/latest/trades?symbols={symbol}/USD"
        else:
            url = f"https://data.alpaca.markets/v2/stocks/{symbol}/trades/latest"

        resp = requests.get(url, headers=self.headers)
        resp.raise_for_status()
        data = resp.json()

        if asset_type == "crypto":
            trades = data.get("trades", {})
            trade = trades.get(f"{symbol}/USD", {})
            return {"symbol": symbol, "price": float(trade.get("p", 0))}
        else:
            trade = data.get("trade", {})
            return {"symbol": symbol, "price": float(trade.get("p", 0))}

    def get_latest_quotes_bulk(
        self, symbols: List[str], asset_type: str = "stock"
    ) -> Dict[str, float]:
        """Get latest prices for multiple symbols. Returns {symbol: price}."""
        prices = {}
        if asset_type == "crypto":
            normalized = [f"{s}/USD" for s in symbols]
            url = f"https://data.alpaca.markets/v1beta3/crypto/us/latest/trades"
            params = {"symbols": ",".join(normalized)}
            resp = requests.get(url, headers=self.headers, params=params)
            resp.raise_for_status()
            trades = resp.json().get("trades", {})
            for sym, trade in trades.items():
                clean = sym.replace("/USD", "")
                prices[clean] = float(trade.get("p", 0))
        else:
            url = "https://data.alpaca.markets/v2/stocks/trades/latest"
            params = {"symbols": ",".join(symbols)}
            resp = requests.get(url, headers=self.headers, params=params)
            resp.raise_for_status()
            trades = resp.json().get("trades", {})
            for sym, trade in trades.items():
                prices[sym] = float(trade.get("p", 0))
        return prices

    # ==================== CLOCK / CALENDAR ====================

    def is_market_open(self) -> bool:
        """Check if market is currently open"""
        resp = requests.get(f"{self.base_url}/v2/clock", headers=self.headers)
        resp.raise_for_status()
        return resp.json().get("is_open", False)

    def get_clock(self) -> Dict[str, Any]:
        """Get market clock"""
        resp = requests.get(f"{self.base_url}/v2/clock", headers=self.headers)
        resp.raise_for_status()
        return resp.json()
