# AI-Trader MCP Server

MCP (Model Context Protocol) 服务器 — 让任意 AI Agent（Claude、Cursor、Claude Code 等）直接通过 MetaTrader 5 执行交易。

[![GitHub](https://img.shields.io/badge/GitHub-zhimingIU%2Fai--trader--mcp-blue)](https://github.com/zhimingIU/ai-trader-mcp)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Architecture

```
┌─────────────────┐     MCP stdio      ┌──────────────────┐     TCP 18888     ┌──────────────────┐
│  Claude / Cursor │  ◄────────────►   │  ai-trader-mcp   │  ◄────────────►  │  MT5 EA Bridge   │
│  / Any MCP Client│                    │  (Python Server) │                   │  (AI_Trader_Bridge│
└─────────────────┘                    └──────────────────┘                   │     _v5.mq5)     │
                                                                               └──────────────────┘
                                                                                       │
                                                                                       ▼
                                                                               ┌──────────────────┐
                                                                               │  MetaTrader 5    │
                                                                               └──────────────────┘
```

## Tools

| Tool | Description | Required Params |
|------|-------------|-----------------|
| `connect_mt5` | Connect to MT5 EA | host, port |
| `get_account_info` | Account balance/equity/margin/profit | — |
| `get_positions` | Current open positions list | — |
| `get_quotes` | Market quotes + ATR/RSI/EMA/ADX | symbol |
| `market_order` | Open market order (buy/sell) | symbol, type, volume |
| `close_position` | Close position (partial supported) | ticket |
| `modify_position` | Modify stop loss / take profit | ticket, sl, tp |
| `close_all` | Close all positions | — |
| `get_daily_pnl` | Daily profit and loss | — |

## Quick Start

```bash
# Install
pip install mcp

# Run (stdio mode)
python ai_trader_mcp_server.py
```

### Claude Code
```bash
hermes config set tools.mcp_servers.ai_trader "python /path/to/ai_trader_mcp_server.py"
```

### Cursor
In `.cursor/mcp.json`:
```json
{
  "mcpServers": {
    "ai-trader": {
      "command": "python",
      "args": ["/path/to/ai_trader_mcp_server.py"]
    }
  }
}
```

### Claude Desktop
In `claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "ai-trader": {
      "command": "python",
      "args": ["/path/to/ai_trader_mcp_server.py"]
    }
  }
}
```

## Prerequisites

1. MetaTrader 5 installed and logged in
2. `AI_Trader_Bridge_v5.ex5` EA loaded on an MT5 chart
3. EA TCP server running on `127.0.0.1:18888`

## Design Philosophy

This server is designed using first-principles thinking from 6 foundational disciplines:

- **Geometry**: Trading operations modeled as points in "tool space", each trade a path through the space
- **Physics**: Capital = system energy, trading = converting information energy into capital (heat engine)
- **Chemistry**: Opening = reaction start, closing = reaction complete, MCP = catalyst lowering activation energy
- **Biology**: Trading system = living ecosystem, each agent occupies a niche
- **Linguistics**: MCP defines trading "grammar", context determines "pragmatics"
- **Logic**: Every trade decision is a logical inference chain

## License

MIT
