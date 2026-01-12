from __future__ import annotations

import argparse
import logging

from bot.config import BotConfig
from bot.strategy import StrategyRunner

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="BTC 合约 MA120 策略")
    parser.add_argument("--config", default="config.toml", help="配置文件路径")
    parser.add_argument("--once", action="store_true", help="只运行一轮（便于调试）")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    cfg = BotConfig.load(args.config)
    runner = StrategyRunner(cfg)
    if args.once:
        runner.run_once()
    else:
        runner.run_forever()


if __name__ == "__main__":
    main()
