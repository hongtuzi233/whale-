from __future__ import annotations

import decimal
import logging
from typing import Dict, List, Tuple

from binance.spot import Spot

logger = logging.getLogger(__name__)


class BinanceService:
    """币安现货 REST 封装：行情、账户余额、市价下单。"""

    def __init__(self, api_key: str, api_secret: str, env: str = "testnet"):
        base_url = "https://api.binance.com"
        if env == "testnet":
            base_url = "https://testnet.binance.vision"
        self.client = Spot(api_key=api_key, api_secret=api_secret, base_url=base_url)
        self._assets_cache: Dict[str, Tuple[str, str]] = {}

    def get_price(self, symbol: str) -> float:
        """最新成交价（现货没有合约的标记价，用最新成交价代替）。"""
        result = self.client.ticker_price(symbol=symbol)
        return float(result["price"])

    def get_klines(self, symbol: str, interval: str, limit: int) -> List[list]:
        return self.client.klines(symbol=symbol, interval=interval, limit=limit)

    def get_symbol_assets(self, symbol: str) -> Tuple[str, str]:
        """返回交易对的 (基础资产, 报价资产)，例如 BTCUSDT -> (BTC, USDT)。"""
        if symbol not in self._assets_cache:
            info = self.client.exchange_info(symbol=symbol)
            symbol_info = next(
                (item for item in info.get("symbols", []) if item.get("symbol") == symbol), None
            )
            if symbol_info is None:
                raise ValueError(f"未在交易所信息中找到交易对: {symbol}")
            self._assets_cache[symbol] = (symbol_info["baseAsset"], symbol_info["quoteAsset"])
        return self._assets_cache[symbol]

    def get_exchange_filters(
        self, symbol: str
    ) -> Tuple[decimal.Decimal, decimal.Decimal, decimal.Decimal]:
        info = self.client.exchange_info(symbol=symbol)
        symbol_info = next(
            (item for item in info.get("symbols", []) if item.get("symbol") == symbol), None
        )
        if symbol_info is None:
            raise ValueError(f"未在交易所信息中找到交易对: {symbol}")
        filters = symbol_info.get("filters", [])
        step_size = decimal.Decimal("0.0")
        min_qty = decimal.Decimal("0.0")
        min_notional = decimal.Decimal("0.0")
        for f in filters:
            if f["filterType"] == "LOT_SIZE":
                step_size = decimal.Decimal(f["stepSize"])
                min_qty = decimal.Decimal(f["minQty"])
            if f["filterType"] == "MIN_NOTIONAL":
                min_notional = decimal.Decimal(f.get("minNotional", "0.0"))
            if f["filterType"] == "NOTIONAL":
                min_notional = decimal.Decimal(f.get("minNotional", "0.0"))
        return step_size, min_qty, min_notional

    def _get_free_balance(self, asset: str) -> float:
        account = self.client.account()
        for b in account.get("balances", []):
            if b.get("asset") == asset:
                return float(b.get("free", 0))
        return 0.0

    def get_quote_balance(self, symbol: str) -> float:
        """报价资产（USDT）可用余额。"""
        _, quote_asset = self.get_symbol_assets(symbol)
        return self._get_free_balance(quote_asset)

    def get_base_balance(self, symbol: str) -> float:
        """基础资产（BTC）可用余额，相当于现货的"持仓"。"""
        base_asset, _ = self.get_symbol_assets(symbol)
        return self._get_free_balance(base_asset)

    def place_market_buy_quote(self, symbol: str, quote_order_qty: float) -> Dict:
        """以指定报价资产金额（USDT）市价买入。newOrderRespType=FULL 确保返回成交明细。"""
        return self.client.new_order(
            symbol=symbol, side="BUY", type="MARKET", quoteOrderQty=quote_order_qty, newOrderRespType="FULL"
        )

    def place_market_sell(self, symbol: str, quantity: float) -> Dict:
        """以指定基础资产数量（BTC）市价卖出。newOrderRespType=FULL 确保返回成交明细。"""
        return self.client.new_order(
            symbol=symbol, side="SELL", type="MARKET", quantity=quantity, newOrderRespType="FULL"
        )
