from __future__ import annotations

import decimal
import logging
import math
from statistics import mean
from time import sleep

from bot.binance_client import BinanceService
from bot.config import BotConfig
from bot.feishu import parse_avg_fill, send_trade_notification

logger = logging.getLogger(__name__)

decimal.getcontext().prec = 28


class StrategyRunner:
    def __init__(self, cfg: BotConfig):
        self.cfg = cfg
        self.binance = BinanceService(cfg.binance.api_key, cfg.binance.api_secret, cfg.env)

    def _calc_ma(self, symbol: str) -> float:
        klines = self.binance.get_klines(symbol, self.cfg.ma_kline_interval, self.cfg.ma_period + 5)
        if len(klines) < self.cfg.ma_period:
            raise RuntimeError("不足 120 根日线，暂停交易")
        closed_candles = [k for k in klines[:-1]]  # 去掉当前未收盘K
        closes = [float(k[4]) for k in closed_candles][-self.cfg.ma_period :]
        return mean(closes)

    def _normalize_quantity(
        self, qty: decimal.Decimal, price: decimal.Decimal, step_size: decimal.Decimal, min_qty: decimal.Decimal, min_notional: decimal.Decimal
    ) -> decimal.Decimal:
        if step_size == 0:
            raise ValueError("stepSize 不能为 0")
        factor = math.floor(qty / step_size)
        normalized = decimal.Decimal(factor) * step_size
        if normalized < min_qty:
            raise ValueError("数量不足 minQty，跳过下单")
        if normalized * price < min_notional:
            raise ValueError("名义价值不足交易所最小限制，跳过下单")
        return normalized.quantize(step_size)

    def _should_buy(self, mark: float, ma: float) -> bool:
        return mark > ma * (1 + self.cfg.buffer)

    def _should_sell(self, mark: float, ma: float) -> bool:
        return mark < ma * (1 - self.cfg.buffer)

    def _calculate_order_qty(self, mark_price: float) -> decimal.Decimal:
        balance = self.binance.get_account_balance()
        if balance <= self.cfg.min_available_usdt:
            raise ValueError(f"可用余额 {balance} USDT 不足 {self.cfg.min_available_usdt}，不下单")
        notional = decimal.Decimal(balance * self.cfg.usage_ratio * self.cfg.leverage)
        qty = notional / decimal.Decimal(mark_price)
        step_size, min_qty, min_notional = self.binance.get_exchange_filters(self.cfg.symbol)
        return self._normalize_quantity(qty, decimal.Decimal(mark_price), step_size, min_qty, min_notional)

    def _buy(self, mark_price: float, ma_price: float) -> None:
        position_amt = self.binance.get_position(self.cfg.symbol)
        if position_amt > 0:
            logger.info("已持有多仓，跳过重复开仓")
            return
        self.binance.ensure_leverage_and_margin(self.cfg.symbol, self.cfg.leverage, self.cfg.margin_mode)
        qty = self._calculate_order_qty(mark_price)
        order_resp = self.binance.place_market_buy(self.cfg.symbol, float(qty))
        fills = parse_avg_fill(order_resp)
        send_trade_notification(
            self.cfg.feishu_webhook_url,
            side="买入",
            avg_price=fills["avg_price"],
            quantity=fills["executed_qty"],
            quote_qty=fills["quote_qty"],
            mark_price=mark_price,
            ma_price=ma_price,
            buffer=self.cfg.buffer,
            timezone=self.cfg.timezone,
            trade_time=fills["update_time"],
            leverage=self.cfg.leverage,
            margin_mode=self.cfg.margin_mode,
        )
        logger.info("买入成功: %s", fills)

    def _sell(self, mark_price: float, ma_price: float) -> None:
        position_amt = self.binance.get_position(self.cfg.symbol)
        if position_amt <= 0:
            logger.info("当前无多仓，跳过平仓")
            return
        qty = decimal.Decimal(abs(position_amt))
        step_size, min_qty, min_notional = self.binance.get_exchange_filters(self.cfg.symbol)
        normalized_qty = self._normalize_quantity(qty, decimal.Decimal(mark_price), step_size, min_qty, min_notional)
        order_resp = self.binance.place_market_sell(self.cfg.symbol, float(normalized_qty))
        fills = parse_avg_fill(order_resp)
        send_trade_notification(
            self.cfg.feishu_webhook_url,
            side="卖出",
            avg_price=fills["avg_price"],
            quantity=fills["executed_qty"],
            quote_qty=fills["quote_qty"],
            mark_price=mark_price,
            ma_price=ma_price,
            buffer=self.cfg.buffer,
            timezone=self.cfg.timezone,
            trade_time=fills["update_time"],
            leverage=self.cfg.leverage,
            margin_mode=self.cfg.margin_mode,
        )
        logger.info("卖出成功: %s", fills)

    def run_once(self) -> None:
        mark_price = self.binance.get_mark_price(self.cfg.symbol)
        ma_price = self._calc_ma(self.cfg.symbol)
        logger.info("Mark=%.2f, MA120=%.2f", mark_price, ma_price)
        if self._should_buy(mark_price, ma_price):
            logger.info("触发开多条件")
            self._buy(mark_price, ma_price)
        elif self._should_sell(mark_price, ma_price):
            logger.info("触发平多条件")
            self._sell(mark_price, ma_price)
        else:
            logger.info("价格在缓冲区内，不操作")

    def run_forever(self) -> None:
        while True:
            try:
                self.run_once()
            except Exception as exc:  # noqa: BLE001
                logger.exception("本轮执行异常: %s", exc)
                sleep(self.cfg.scheduler.sleep_on_error_seconds)
            else:
                sleep(self.cfg.interval_minutes * 60)
