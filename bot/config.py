from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any, Dict

import tomllib
from dotenv import load_dotenv


@dataclass
class BinanceConfig:
    api_key: str
    api_secret: str


@dataclass
class SchedulerConfig:
    sleep_on_error_seconds: int = 60


@dataclass
class BotConfig:
    symbol: str = "BTCUSDT"
    interval_minutes: int = 10
    leverage: int = 3
    margin_mode: str = "ISOLATED"
    order_type: str = "MARKET"
    usage_ratio: float = 0.99
    min_available_usdt: float = 500.0
    buffer: float = 0.01
    ma_period: int = 120
    ma_kline_interval: str = "1d"
    feishu_webhook_url: str = ""
    timezone: str = "Asia/Shanghai"
    env: str = "testnet"
    binance: BinanceConfig | None = None
    scheduler: SchedulerConfig = field(default_factory=SchedulerConfig)

    @classmethod
    def load(cls, path: str = "config.toml") -> "BotConfig":
        load_dotenv()
        data: Dict[str, Any] = {}
        if os.path.exists(path):
            with open(path, "rb") as f:
                data = tomllib.load(f)

        binance_cfg = BinanceConfig(
            api_key=os.getenv("BINANCE_API_KEY", data.get("binance", {}).get("api_key", "")),
            api_secret=os.getenv("BINANCE_API_SECRET", data.get("binance", {}).get("api_secret", "")),
        )

        scheduler_data = data.get("scheduler", {})
        scheduler_cfg = SchedulerConfig(
            sleep_on_error_seconds=int(os.getenv("SLEEP_ON_ERROR_SECONDS", scheduler_data.get("sleep_on_error_seconds", 60))),
        )

        config = cls(
            symbol=os.getenv("SYMBOL", data.get("symbol", "BTCUSDT")),
            interval_minutes=int(os.getenv("INTERVAL_MINUTES", data.get("interval_minutes", 10))),
            leverage=int(os.getenv("LEVERAGE", data.get("leverage", 3))),
            margin_mode=os.getenv("MARGIN_MODE", data.get("margin_mode", "ISOLATED")),
            order_type=os.getenv("ORDER_TYPE", data.get("order_type", "MARKET")),
            usage_ratio=float(os.getenv("USAGE_RATIO", data.get("usage_ratio", 0.99))),
            min_available_usdt=float(os.getenv("MIN_AVAILABLE_USDT", data.get("min_available_usdt", 500))),
            buffer=float(os.getenv("BUFFER", data.get("buffer", 0.01))),
            ma_period=int(os.getenv("MA_PERIOD", data.get("ma_period", 120))),
            ma_kline_interval=os.getenv("MA_KLINE_INTERVAL", data.get("ma_kline_interval", "1d")),
            feishu_webhook_url=os.getenv("FEISHU_WEBHOOK_URL", data.get("feishu_webhook_url", "")),
            timezone=os.getenv("TIMEZONE", data.get("timezone", "Asia/Shanghai")),
            env=os.getenv("ENV", data.get("env", "testnet")),
            binance=binance_cfg,
            scheduler=scheduler_cfg,
        )
        _validate_config(config)
        return config


def _validate_config(cfg: BotConfig) -> None:
    if cfg.binance is None or not cfg.binance.api_key or not cfg.binance.api_secret:
        raise ValueError("Binance API key/secret must be provided via config.toml or environment variables.")
    if not cfg.feishu_webhook_url:
        raise ValueError("Feishu webhook URL is required for notifications.")
    if cfg.env not in {"prod", "testnet"}:
        raise ValueError("env must be either 'prod' or 'testnet'.")
    if cfg.margin_mode.upper() not in {"ISOLATED", "CROSSED"}:
        raise ValueError("margin_mode must be ISOLATED or CROSSED.")
    if cfg.order_type.upper() != "MARKET":
        raise ValueError("V1 仅支持市价单 (MARKET)。")
