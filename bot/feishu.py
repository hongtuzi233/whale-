from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict

import pytz
import requests

logger = logging.getLogger(__name__)


def format_time(ts: float, timezone: str) -> str:
    tz = pytz.timezone(timezone)
    return datetime.fromtimestamp(ts / 1000, tz=tz).strftime("%Y-%m-%d %H:%M:%S")


def send_trade_notification(
    webhook_url: str,
    *,
    side: str,
    avg_price: float,
    quantity: float,
    quote_qty: float,
    price: float,
    ma_price: float,
    buffer: float,
    timezone: str,
    trade_time: float,
) -> None:
    headers = {"Content-Type": "application/json"}
    content = {
        "msg_type": "interactive",
        "card": {
            "header": {"title": {"tag": "plain_text", "content": "BTC 现货策略成交通知"}},
            "elements": [
                {
                    "tag": "div",
                    "fields": [
                        {"is_short": True, "text": {"tag": "lark_md", "content": f"**方向**\n{side}"}},
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**成交均价**\n{avg_price:.2f} USDT",
                            },
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**成交数量**\n{quantity:.6f} BTC",
                            },
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**成交金额**\n{quote_qty:.2f} USDT",
                            },
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**成交时间**\n{format_time(trade_time, timezone)}",
                            },
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**现价/MA120**\n{price:.2f} / {ma_price:.2f}",
                            },
                        },
                        {
                            "is_short": True,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**buffer**\n{buffer*100:.2f}%",
                            },
                        },
                    ],
                }
            ],
        },
    }
    try:
        resp = requests.post(webhook_url, headers=headers, json=content, timeout=10)
        resp.raise_for_status()
        logger.info("Feishu notification sent")
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to send Feishu notification: %s", exc)


def parse_avg_fill(order_resp: Dict) -> Dict[str, float]:
    executed_qty = float(order_resp.get("executedQty", 0) or 0)
    cummulative_quote_qty = float(order_resp.get("cummulativeQuoteQty", 0) or 0)
    # 顶层汇总字段缺失或为 0 时，用逐笔成交明细 fills 加总兜底
    fills = order_resp.get("fills") or []
    if fills and (executed_qty == 0 or cummulative_quote_qty == 0):
        executed_qty = sum(float(f.get("qty", 0) or 0) for f in fills)
        cummulative_quote_qty = sum(
            float(f.get("price", 0) or 0) * float(f.get("qty", 0) or 0) for f in fills
        )
    avg_price = cummulative_quote_qty / executed_qty if executed_qty else 0
    update_time = float(order_resp.get("updateTime", 0) or order_resp.get("transactTime", 0) or 0)
    return {
        "avg_price": avg_price,
        "executed_qty": executed_qty,
        "quote_qty": cummulative_quote_qty,
        "update_time": update_time,
    }


def send_error_notification(webhook_url: str, *, title: str, message: str, timezone: str) -> None:
    headers = {"Content-Type": "application/json"}
    content = {
        "msg_type": "interactive",
        "card": {
            "header": {"title": {"tag": "plain_text", "content": title}},
            "elements": [
                {
                    "tag": "div",
                    "fields": [
                        {
                            "is_short": False,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**时间**\n{format_time(datetime.now().timestamp() * 1000, timezone)}",
                            },
                        },
                        {
                            "is_short": False,
                            "text": {
                                "tag": "lark_md",
                                "content": f"**异常信息**\n{message}",
                            },
                        },
                    ],
                }
            ],
        },
    }
    try:
        resp = requests.post(webhook_url, headers=headers, json=content, timeout=10)
        resp.raise_for_status()
        logger.info("Feishu error notification sent")
    except Exception as exc:  # noqa: BLE001
        logger.exception("Failed to send Feishu error notification: %s", exc)
