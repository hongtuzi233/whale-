from __future__ import annotations

import decimal
import logging
from typing import Dict, List, Tuple

from binance.um_futures import UMFutures

logger = logging.getLogger(__name__)


class BinanceService:
    def __init__(self, api_key: str, api_secret: str, env: str = "testnet"):
        base_url = "https://fapi.binance.com"
        if env == "testnet":
            base_url = "https://testnet.binancefuture.com"
        self.client = UMFutures(key=api_key, secret=api_secret, base_url=base_url)

    def get_mark_price(self, symbol: str) -> float:
        result = self.client.mark_price(symbol=symbol)
        return float(result["markPrice"])

    def get_klines(self, symbol: str, interval: str, limit: int) -> List[Dict]:
        return self.client.klines(symbol=symbol, interval=interval, limit=limit)

    def get_exchange_filters(self, symbol: str) -> Tuple[decimal.Decimal, decimal.Decimal, decimal.Decimal]:
        info = self.client.exchange_info(symbol=symbol)
        filters = info["symbols"][0]["filters"]
        step_size = decimal.Decimal("0.0")
        min_qty = decimal.Decimal("0.0")
        min_notional = decimal.Decimal("0.0")
        for f in filters:
            if f["filterType"] == "LOT_SIZE":
                step_size = decimal.Decimal(f["stepSize"])
                min_qty = decimal.Decimal(f["minQty"])
            if f["filterType"] == "MIN_NOTIONAL":
                min_notional = decimal.Decimal(f["notional"])
        return step_size, min_qty, min_notional

    def get_account_balance(self) -> float:
        balances = self.client.balance()
        for b in balances:
            if b.get("asset") == "USDT":
                return float(b.get("availableBalance", 0))
        return 0.0

    def get_position(self, symbol: str) -> float:
        positions = self.client.position_information(symbol=symbol)
        if not positions:
            return 0.0
        position_amt = float(positions[0].get("positionAmt", 0))
        return position_amt

    def ensure_leverage_and_margin(self, symbol: str, leverage: int, margin_mode: str) -> None:
        try:
            self.client.change_margin_type(symbol=symbol, marginType=margin_mode.upper())
        except Exception as exc:  # noqa: BLE001
            if "No need to change margin type" not in str(exc):
                raise
        self.client.change_leverage(symbol=symbol, leverage=leverage)

    def place_market_buy(self, symbol: str, quantity: float) -> Dict:
        return self.client.new_order(symbol=symbol, side="BUY", type="MARKET", quantity=quantity)

    def place_market_sell(self, symbol: str, quantity: float) -> Dict:
        return self.client.new_order(symbol=symbol, side="SELL", type="MARKET", quantity=quantity, reduceOnly=True)
