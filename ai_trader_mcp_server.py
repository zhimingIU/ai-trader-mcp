"""
AI_Trader MCP Server — 通过MCP协议连接MT5交易系统

让任何MCP兼容客户端（Claude Code、Cursor、Claude Desktop等）
直接通过MT5执行交易、查询账户、获取行情。

架构：
  MCP Client ↔ (stdio) ↔ 本Server ↔ TCP 18888 ↔ MT5 EA(AI_Trader_Bridge_v5)

使用方式：
  source .venv/bin/activate
  python ai_trader_mcp_server.py

或在Claude Code中使用：
  hermes config set tools.mcp_servers.ai_trader "uv run python /path/to/ai_trader_mcp_server.py"
"""

import asyncio
import json
import logging
import socket
import struct
import sys
from typing import Any, Optional
from datetime import datetime

from mcp.server import Server, NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.types import (
    Tool,
    TextContent,
    ImageContent,
    EmbeddedResource,
)

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")
log = logging.getLogger("ai-trader-mcp")

# ── MT5 Bridge TCP 配置 ─────────────────────────────────────────
MT5_HOST = "127.0.0.1"
MT5_PORT = 18888
CONNECT_TIMEOUT = 5
RECV_TIMEOUT = 10

# ── TCP 通信层 ──────────────────────────────────────────────────

class Mt5BridgeClient:
    """与MT5 EA的TCP桥接通信。协议: 4字节长度前缀 + JSON消息。"""

    def __init__(self, host: str = MT5_HOST, port: int = MT5_PORT):
        self.host = host
        self.port = port
        self.sock: Optional[socket.socket] = None
        self._buffer = b""

    def connect(self) -> bool:
        """连接到MT5 EA。"""
        try:
            self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.sock.settimeout(CONNECT_TIMEOUT)
            self.sock.connect((self.host, self.port))
            self.sock.settimeout(RECV_TIMEOUT)
            log.info(f"✅ 已连接到MT5 EA @ {self.host}:{self.port}")
            return True
        except Exception as e:
            log.error(f"❌ 连接MT5失败: {e}")
            return False

    def disconnect(self):
        if self.sock:
            try:
                self.sock.close()
            except:
                pass
            self.sock = None

    def send_command(self, command: str, payload: dict = None) -> dict:
        """发送JSON命令到MT5，等待返回。"""
        if not self.sock:
            return {"error": "未连接到MT5"}

        msg = json.dumps({
            "command": command,
            "payload": payload or {},
            "timestamp": datetime.now().timestamp(),
        }, ensure_ascii=False)

        try:
            # 4字节长度前缀（大端）
            data = msg.encode("utf-8")
            length_prefix = struct.pack(">I", len(data))
            self.sock.sendall(length_prefix + data)

            # 接收响应
            response = self._recv_response()
            if response:
                return json.loads(response)
            return {"error": "无响应"}
        except Exception as e:
            log.error(f"❌ 通信错误: {e}")
            self.disconnect()
            return {"error": str(e)}

    def _recv_response(self) -> Optional[str]:
        """接收4字节长度前缀的响应。"""
        try:
            # 读4字节长度
            header = self._recv_exact(4)
            if not header:
                return None
            length = struct.unpack(">I", header)[0]

            # 读消息体
            body = self._recv_exact(length)
            return body.decode("utf-8") if body else None
        except:
            return None

    def _recv_exact(self, n: int) -> Optional[bytes]:
        """精确读取n字节。"""
        chunks = []
        remaining = n
        while remaining > 0:
            try:
                chunk = self.sock.recv(remaining)
            except:
                return None
            if not chunk:
                return None
            chunks.append(chunk)
            remaining -= len(chunk)
        return b"".join(chunks)


# ── MCP Server ──────────────────────────────────────────────────

class AiTraderMcpServer:
    """MCP Server — 把MT5交易能力暴露为MCP工具。"""

    def __init__(self):
        self.mt5 = Mt5BridgeClient()
        self.server = Server("ai-trader-mcp")

        # 注册工具
        self._register_tools()

    def _register_tools(self):
        server = self.server

        @server.list_tools()
        async def handle_list_tools() -> list[Tool]:
            return [
                Tool(
                    name="connect_mt5",
                    description="连接到MT5交易终端（必须先调用这个）",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "host": {"type": "string", "description": "MT5主机地址", "default": "127.0.0.1"},
                            "port": {"type": "integer", "description": "MT5端口", "default": 18888},
                        },
                    },
                ),
                Tool(
                    name="get_account_info",
                    description="获取MT5账户信息（余额、净值、保证金等）",
                    inputSchema={"type": "object", "properties": {}},
                ),
                Tool(
                    name="get_positions",
                    description="获取当前持仓列表",
                    inputSchema={"type": "object", "properties": {}},
                ),
                Tool(
                    name="get_quotes",
                    description="获取行情报价（含技术指标：ATR/RSI/EMA/ADX）",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "symbol": {"type": "string", "description": "交易品种，如 XAUUSD, EURUSD", "default": "XAUUSD"},
                        },
                    },
                ),
                Tool(
                    name="market_order",
                    description="开市价单（买入/卖出）",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "symbol": {"type": "string", "description": "交易品种，如 XAUUSD"},
                            "type": {"type": "string", "enum": ["buy", "sell"], "description": "buy=买入 sell=卖出"},
                            "volume": {"type": "number", "description": "交易手数，如 0.01"},
                            "stop_loss": {"type": "number", "description": "止损价格（可选）"},
                            "take_profit": {"type": "number", "description": "止盈价格（可选）"},
                        },
                        "required": ["symbol", "type", "volume"],
                    },
                ),
                Tool(
                    name="close_position",
                    description="平掉指定持仓",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "ticket": {"type": "integer", "description": "持仓编号"},
                            "volume": {"type": "number", "description": "平仓手数（可选，默认全平）"},
                        },
                        "required": ["ticket"],
                    },
                ),
                Tool(
                    name="modify_position",
                    description="修改持仓的止损止盈",
                    inputSchema={
                        "type": "object",
                        "properties": {
                            "ticket": {"type": "integer", "description": "持仓编号"},
                            "stop_loss": {"type": "number", "description": "新止损价"},
                            "take_profit": {"type": "number", "description": "新止盈价"},
                        },
                        "required": ["ticket"],
                    },
                ),
                Tool(
                    name="close_all",
                    description="平掉所有持仓",
                    inputSchema={"type": "object", "properties": {}},
                ),
                Tool(
                    name="get_daily_pnl",
                    description="获取当日盈亏",
                    inputSchema={"type": "object", "properties": {}},
                ),
            ]

        @server.call_tool()
        async def handle_call_tool(name: str, arguments: dict) -> list[TextContent]:
            if name == "connect_mt5":
                host = arguments.get("host", MT5_HOST)
                port = arguments.get("port", MT5_PORT)
                self.mt5 = Mt5BridgeClient(host, port)
                ok = self.mt5.connect()
                return [TextContent(
                    type="text",
                    text=json.dumps({"success": ok, "message": "已连接到MT5" if ok else "连接失败"}, ensure_ascii=False)
                )]

            # 其他命令都需要先连接
            if not self.mt5.sock:
                # 自动连接
                if not self.mt5.connect():
                    return [TextContent(type="text", text=json.dumps({"error": "未连接到MT5，且自动连接失败"}, ensure_ascii=False))]

            command_map = {
                "get_account_info": "get_account",
                "get_positions": "get_positions",
                "get_daily_pnl": "get_account",  # 从账户信息中取
                "close_all": "close_all",
            }

            if name in command_map:
                result = self.mt5.send_command(command_map[name])
                return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, default=str))]

            elif name == "get_quotes":
                result = self.mt5.send_command("get_quotes", {"symbol": arguments.get("symbol", "XAUUSD")})
                return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, default=str))]

            elif name == "market_order":
                payload = {
                    "symbol": arguments["symbol"],
                    "type": arguments["type"],
                    "volume": arguments["volume"],
                }
                if "stop_loss" in arguments:
                    payload["stop_loss"] = arguments["stop_loss"]
                if "take_profit" in arguments:
                    payload["take_profit"] = arguments["take_profit"]
                result = self.mt5.send_command("send_order", payload)
                return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, default=str))]

            elif name == "close_position":
                payload = {"ticket": arguments["ticket"]}
                if "volume" in arguments:
                    payload["volume"] = arguments["volume"]
                result = self.mt5.send_command("close_position", payload)
                return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, default=str))]

            elif name == "modify_position":
                result = self.mt5.send_command("modify_position", {
                    "ticket": arguments["ticket"],
                    "stop_loss": arguments.get("stop_loss", 0),
                    "take_profit": arguments.get("take_profit", 0),
                })
                return [TextContent(type="text", text=json.dumps(result, ensure_ascii=False, default=str))]

            else:
                return [TextContent(type="text", text=json.dumps({"error": f"未知命令: {name}"}))]

    async def run(self):
        """以stdio模式运行MCP Server。"""
        async with self.server.run_simple_stdio() as streams:
            # MCP SDK v1.x 方式
            pass  # 由mcp库管理

    async def run_stdio(self):
        """使用mcp库的标准入口。"""
        from mcp.server.stdio import stdio_server

        async with stdio_server() as (read_stream, write_stream):
            await self.server.run(
                read_stream,
                write_stream,
                InitializationOptions(
                    server_name="ai-trader-mcp",
                    server_version="0.1.0",
                    capabilities=self.server.get_capabilities(
                        notification_options=NotificationOptions(),
                        experimental_capabilities={},
                    ),
                ),
            )


# ── 入口 ────────────────────────────────────────────────────────

def main():
    """启动AI_Trader MCP Server（stdio模式）。"""
    server = AiTraderMcpServer()
    asyncio.run(server.run_stdio())

if __name__ == "__main__":
    main()
