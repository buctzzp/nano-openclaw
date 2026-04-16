"""
MCP 工具注册模块。

这里的职责非常单一：把“给 Telegram 用户发消息”这个能力，
包装成 Claude Agent 能调用的 SDK MCP tool。

换句话说，这一层是在做“Telegram 世界”和“Claude Agent 工具世界”的桥接。
"""

from typing import Any

from claude_agent_sdk import tool


def create_mcp_server_tools(bot, chat_id: int) -> list:
    """创建供 Claude Agent 使用的 SDK MCP 工具。"""

    @tool("send_message", "发送消息给用户", {"text": str})
    async def send_message(args) -> dict[str, Any]:
        # 这里用闭包捕获当前 chat_id。
        # 这样 agent 在调用 `send_message` 时，不需要自己再传“该发给谁”，
        # 工具天然就会回复到触发本轮对话的那个 Telegram chat 里。
        await bot.send_message(chat_id=chat_id, text=args["text"])

        # 这个返回结构不是随便写的，而是 Claude SDK 规定的 tool result 格式。
        # `content` 是一个列表；列表里每项都带 `type`，这里我们返回 text 类型。
        return {
            "content": [
                {
                    "type": "text",
                    "text": f"已经给用户发送消息: {args['text']}",
                }
            ]
        }

    return [send_message]
