"""
Claude Agent 运行模块。

这个模块是整个项目的核心：
- 构造 `ClaudeAgentOptions`
- 组装 MCP 工具
- 恢复上一轮 session
- 启动 `query(...)` 流式对话
- 收集最终回复
- 持久化新的 session_id

你可以把它理解成“Telegram 外壳里面真正和 LLM 打交道的那一层”。
"""

import asyncio
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeAgentOptions,
    ResultMessage,
    TextBlock,
    create_sdk_mcp_server,
    query,
)

from .config import WORK_SPACE
from .logging_utils import LOGGER, configure_logging, log_stream_message
from .mcp import create_mcp_server_tools
from .session_store import load_session_id, save_session_id
from .workspace import build_system_prompt

# 这把锁保护的是完整的会话状态流转：
#     读旧 session_id -> 调 LLM -> 写新 session_id
#
# 如果这段流程并发执行，就可能出现多个请求同时拿着同一个旧 session_id
# 去继续会话，最后谁覆盖谁就不可控了。
_agent_lock = asyncio.Lock()


async def run_agent(prompt: str, bot: Any, chat_id: int) -> str:
    """
    串行执行一次 agent 请求。

    对外暴露这一层，而不是让别的模块直接调 `_run_inner_agent()`，
    是为了把并发控制统一收口到这里。
    """
    async with _agent_lock:
        return await _run_inner_agent(prompt, bot, chat_id)


async def _run_inner_agent(prompt: str, bot: Any, chat_id: int) -> str:
    """真正执行一次 Claude 查询。"""
    configure_logging()
    mcp_tools = create_mcp_server_tools(bot, chat_id)

    options = ClaudeAgentOptions(
        # 把 Claude Code 的工作目录固定到 `work_space/`，
        # 这样它看到的“当前项目”就是我们专门准备好的运行空间。
        #
        # 这一步非常关键，因为：
        # - `claude.md` 在这里
        # - `conversations/` 在这里
        # - Claude 的 Read / Grep / Glob 也会围绕这个目录工作
        cwd=WORK_SPACE,
        system_prompt=build_system_prompt(),
        allowed_tools=[
            "Read",
            "Write",
            "Edit",
            "Glob",
            "Grep",
            "WebSearch",
            "WebFetch",
            "Bash",
        ],
        mcp_servers={
            # 这里注册的是一个 SDK 内嵌 MCP server，不需要单独起进程。
            "assistant": create_sdk_mcp_server(
                name="assistant",
                tools=mcp_tools,
            )
        },
        permission_mode="bypassPermissions",
    )

    # 这里恢复的是“短期连续上下文”。
    # 只要 session_id 还有效，Claude 就能继续上一轮会话，而不是每次都从零开始。
    session_id = load_session_id()
    if session_id:
        options.resume = session_id

    LOGGER.info(
        "Starting Claude query | cwd=%s | permission_mode=%s | model=%s | allowed_tools=%s",
        options.cwd,
        options.permission_mode,
        options.model or "default",
        ",".join(options.allowed_tools or []) or "-",
    )

    response_parts: list[str] = []
    idx = 0

    async def _make_prompt(text: str):
        # 这里用异步生成器包装 prompt，是为了适配 SDK 的 streaming 输入形式。
        # 即使只有一条用户消息，也照样按“流”的协议喂给它。
        yield {
            "type": "user",
            "message": {"role": "user", "content": text},
        }

    try:
        async for message in query(prompt=_make_prompt(prompt), options=options):
            idx += 1
            log_stream_message(idx, message)
            if isinstance(message, ResultMessage) and message.result:
                # 注意：session_id 的保存放在 ResultMessage 阶段，
                # 因为这是本轮对话的收尾事件，能确保我们拿到的是最终稳定的会话标识。
                save_session_id(message.session_id)
            elif isinstance(message, AssistantMessage):
                for block in message.content:
                    if isinstance(block, TextBlock):
                        # 这里只收集用户最终可见的文本块。
                        # thinking / tool_use / tool_result 这些内部细节仍然会记日志，
                        # 但不会拼进最终要发给 Telegram 的回复。
                        response_parts.append(block.text)
    except Exception as error:
        LOGGER.error("Error during agent execution: %s", error)
        return f"Error: {error}"

    # AssistantMessage 里的文本已经够组成给用户看的最终回复了。
    # 这里不再把 ResultMessage.result 再 append 一遍，避免内容重复。
    return "\n".join(response_parts) or "Sorry, I couldn't get a response from Claude."
