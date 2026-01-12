# BTC 合约 MA120 趋势交易机器人（Python 教程版）

本仓库包含一个最小可运行的 Python 示例，用于按照产品需求文档实现「日线 MA120 + buffer」的趋势交易机器人，并在成交后推送飞书通知。仓库特别针对 **零基础** 用户给出逐步操作说明。

## 目录
- [1. 环境准备](#1-环境准备)
- [2. 获取本项目](#2-获取本项目)
- [3. 安装依赖](#3-安装依赖)
- [4. 配置密钥与参数](#4-配置密钥与参数)
- [5. 运行策略](#5-运行策略)
- [6. 代码结构速览](#6-代码结构速览)
- [7. 常见问题](#7-常见问题)

## 1. 环境准备
1. 安装 [Python 3.11+](https://www.python.org/downloads/)。安装时勾选「Add Python to PATH」。
2. 安装 Git（Windows 可选 Git for Windows）。
3. 准备好以下信息（放在第 4 步的配置文件里）：
   - 币安合约 API Key / Secret（建议先使用 **Testnet** 练习）。
   - 飞书机器人 Webhook。

## 2. 获取本项目
在命令行执行：
```bash
# 克隆仓库（已提供仓库时跳过）
# git clone <repo-url> whale-bot
cd whale-
```

## 3. 安装依赖
强烈建议使用虚拟环境，避免污染系统 Python：
```bash
python -m venv .venv
# Windows
.\.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt
```

## 4. 配置密钥与参数
1. 将示例配置复制一份：
```bash
cp config.example.toml config.toml
```
2. 编辑 `config.toml`，填入 API Key / Secret 与飞书 Webhook，其他参数可沿用默认值：
   - `env = "testnet"`：先在测试网练习；正式交易改成 `"prod"`。
   - `feishu_webhook_url`：填写你的飞书机器人地址。
   - 其余参数与产品需求一致，可按需调整。

> **安全提示**：密钥只写在本地 `config.toml`，不要提交到代码仓库。

## 5. 运行策略
单次运行（只执行一轮判断与下单）：
```bash
python main.py --once
```

持续轮询（默认每 10 分钟运行一次，可在配置文件中修改 `interval_minutes`）：
```bash
python main.py
```

日志会输出到终端，成交后会自动推送飞书卡片。

## 6. 代码结构速览
- `main.py`：入口，加载配置并按周期运行策略。
- `bot/config.py`：读取并验证配置。
- `bot/binance_client.py`：与币安合约交互（行情、下单、仓位、余额）。
- `bot/strategy.py`：核心逻辑（计算 MA120、信号判断、数量规范化、开平仓流程）。
- `bot/feishu.py`：飞书 Webhook 推送。

## 7. 常见问题
- **无法连接 Binance**：先确认是否使用了 `env = "testnet"`，并在币安测试网创建了合约 API Key。
- **K 线数量不足**：新上市标的可能不足 120 根日线，程序会暂停交易并提示。
- **数量精度错误**：代码会自动按交易所 `stepSize` 向下取整，但仍可能因为名义价值过低被拒单，请提高资金或价格缓冲。

运行中如有报错，可将终端日志发给开发者排查。祝交易顺利！
