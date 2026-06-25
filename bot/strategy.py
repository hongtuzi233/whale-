from __future__ import annotations

import decimal
import logging
import math
from statistics import mean
from time import sleep

from bot.binance_client import BinanceService
from bot.config import BotConfig
from bot.feishu import parse_avg_fill, send_error_notification, send_trade_notification

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

    def _should_buy(self, price: float, ma: float) -> bool:
        return price > ma * (1 + self.cfg.buffer)

    def _should_sell(self, price: float, ma: float) -> bool:
        return price < ma * (1 - self.cfg.buffer)

    def _calculate_buy_quote_qty(self) -> decimal.Decimal:
        """现货市价买按花费的 USDT 金额下单，返回拟花费的 USDT 金额。"""
        balance = self.binance.get_quote_balance(self.cfg.symbol)
        if balance <= self.cfg.min_available_usdt:
            raise ValueError(f"可用余额 {balance} USDT 不足 {self.cfg.min_available_usdt}，不下单")
        _, _, min_notional = self.binance.get_exchange_filters(self.cfg.symbol)
        quote_qty = (
            decimal.Decimal(str(balance)) * decimal.Decimal(str(self.cfg.usage_ratio))
        ).quantize(decimal.Decimal("0.01"), rounding=decimal.ROUND_DOWN)
        if quote_qty < min_notional:
            raise ValueError("买入金额不足交易所最小名义价值，跳过下单")
        return quote_qty

    def _has_sellable_position(self, price: float) -> bool:
        """账户里的 BTC 余额是否达到可交易下限，相当于现货的"是否持仓"。"""
        base_balance = self.binance.get_base_balance(self.cfg.symbol)
        _, min_qty, min_notional = self.binance.get_exchange_filters(self.cfg.symbol)
        qty = decimal.Decimal(str(base_balance))
        return qty >= min_qty and qty * decimal.Decimal(str(price)) >= min_notional

    def _buy(self, price: float, ma_price: float) -> None:
        if self._has_sellable_position(price):
            logger.info("已持有现货 BTC，跳过重复买入")
            return
        quote_qty = self._calculate_buy_quote_qty()
        order_resp = self.binance.place_market_buy_quote(self.cfg.symbol, float(quote_qty))
        fills = parse_avg_fill(order_resp)
        send_trade_notification(
            self.cfg.feishu_webhook_url,
            side="买入",
            avg_price=fills["avg_price"],
            quantity=fills["executed_qty"],
            quote_qty=fills["quote_qty"],
            price=price,
            ma_price=ma_price,
            buffer=self.cfg.buffer,
            timezone=self.cfg.timezone,
            trade_time=fills["update_time"],
        )
        logger.info("买入成功: %s", fills)

    def _sell(self, price: float, ma_price: float) -> None:
        if not self._has_sellable_position(price):
            logger.info("当前无可卖现货，跳过卖出")
            return
        base_balance = self.binance.get_base_balance(self.cfg.symbol)
        step_size, min_qty, min_notional = self.binance.get_exchange_filters(self.cfg.symbol)
        normalized_qty = self._normalize_quantity(
            decimal.Decimal(str(base_balance)),
            decimal.Decimal(str(price)),
            step_size,
            min_qty,
            min_notional,
        )
        order_resp = self.binance.place_market_sell(self.cfg.symbol, float(normalized_qty))
        fills = parse_avg_fill(order_resp)
        send_trade_notification(
            self.cfg.feishu_webhook_url,
            side="卖出",
            avg_price=fills["avg_price"],
            quantity=fills["executed_qty"],
            quote_qty=fills["quote_qty"],
            price=price,
            ma_price=ma_price,
            buffer=self.cfg.buffer,
            timezone=self.cfg.timezone,
            trade_time=fills["update_time"],
        )
        logger.info("卖出成功: %s", fills)

    def startup_check(self) -> None:
        """启动自检：本策略卖出会卖光账户内全部 BTC，建议使用只放 USDT 的专用账户。
        若启动时已检测到 BTC 余额，给出警告（仅提示，不阻止运行）。"""
        try:
            base_asset, _ = self.binance.get_symbol_assets(self.cfg.symbol)
            base_balance = self.binance.get_base_balance(self.cfg.symbol)
        except Exception as exc:  # noqa: BLE001
            logger.warning("启动自检读取账户余额失败（不影响运行）：%s", exc)
            return
        if base_balance > 0:
            logger.warning(
                "⚠️ 启动检测到账户已持有 %.8f %s。注意：触发卖出信号时本策略会卖光账户内全部 %s。"
                "若这是专用账户的首次启动，请确认账户内没有其它来源的 %s；若为已持仓后的重启，可忽略本提示。",
                base_balance,
                base_asset,
                base_asset,
                base_asset,
            )
        else:
            logger.info("启动自检通过：当前无 %s 持仓。", base_asset)

    def run_once(self) -> None:
        price = self.binance.get_price(self.cfg.symbol)
        ma_price = self._calc_ma(self.cfg.symbol)
        available_balance = self.binance.get_quote_balance(self.cfg.symbol)
        logger.info("现价=%.2f, MA120=%.2f, 可用余额=%.2f USDT", price, ma_price, available_balance)
        if self._should_buy(price, ma_price):
            logger.info("触发买入条件")
            self._buy(price, ma_price)
        elif self._should_sell(price, ma_price):
            logger.info("触发卖出条件")
            self._sell(price, ma_price)
        else:
            logger.info("价格在缓冲区内，不操作")

    def run_forever(self) -> None:
        while True:
            try:
                self.run_once()
            except Exception as exc:  # noqa: BLE001
                logger.exception("本轮执行异常: %s", exc)
                send_error_notification(
                    self.cfg.feishu_webhook_url,
                    title="BTC 现货策略异常告警",
                    message=str(exc),
                    timezone=self.cfg.timezone,
                )
                sleep(self.cfg.scheduler.sleep_on_error_seconds)
            else:
                sleep(self.cfg.interval_minutes * 60)
