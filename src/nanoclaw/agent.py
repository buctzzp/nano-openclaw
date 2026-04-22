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
from typing import Any,AsyncGenerator

from claude_agent_sdk import (
    ClaudeAgentOptions,
    PermissionResultAllow,
    PermissionResultDeny,
    ResultMessage,
    create_sdk_mcp_server,
    query,
)
from .config import *
from .logging_utils import LOGGER, configure_logging, log_stream_message
from .mcp import create_mcp_server_tools
from .session_control import load_session_id, save_session_id
from .workspace import build_system_prompt

# 这把锁保护的是完整的会话状态流转：
#     读旧 session_id -> 调 LLM -> 写新 session_id
#
# 如果这段流程并发执行，就可能出现多个请求同时拿着同一个旧 session_id
# 去继续会话，最后谁覆盖谁就不可控了。
_agent_lock = asyncio.Lock()

_MEDIA_TASK_KEYWORDS = (
    "截图",
    "截屏",
    "图片",
    "照片",
    "发图",
    "发送图片",
    "screenshot",
    "image",
    "photo",
)

_MEDIA_TASK_HINT = """

[媒体工具使用规则]
- 托管媒体统一放在 work_space/assets/ 下，尤其是 assets/images/...。
- 不要手动创建 work_space/images，也不要把新图片或截图保存到 work_space/images。
- 如果用户要求截图，优先调用 MCP 工具 take_screenshot。
- 如果需要把已有图片发给用户，调用 MCP 工具 send_image。
- 正常流程是：take_screenshot -> send_image，而不是手写 Bash screencapture。
"""


def _build_agent_env() -> dict[str, str]:
    """
    构造传给 Claude Agent SDK 的环境变量。

    SDK 最终会把这里的内容传给 Claude Code 子进程。子进程环境变量的
    value 必须是字符串，不能是 None；否则启动阶段就会报：
        expected str, bytes or os.PathLike object, not NoneType

    所以这里采用“只传已经配置好的值”的策略：
    - 如果 `.env` 里配置了 `ANTHROPIC_API_KEY`，就显式传给 SDK
    - 如果没配置，就不传这个键，让 Claude Code 使用自身已有的登录态/配置
    - `ANTHROPIC_BASE_URL` 同理，只在非空时传入
    """
    env: dict[str, str] = {}
    if ANTHROPIC_API_KEY:
        env["ANTHROPIC_API_KEY"] = ANTHROPIC_API_KEY
    if ANTHROPIC_BASE_URL:
        env["ANTHROPIC_BASE_URL"] = ANTHROPIC_BASE_URL
    return env


def _apply_task_hints(prompt: str) -> str:
    """按需给媒体相关任务追加短规则，避免把所有规则都塞进长期记忆。"""
    prompt_lower = prompt.lower()
    if any(keyword in prompt_lower for keyword in _MEDIA_TASK_KEYWORDS):
        return prompt.rstrip() + _MEDIA_TASK_HINT
    return prompt


async def _can_use_tool(tool_name: str, tool_input: dict[str, Any], context: Any):
    """对高风险或易跑偏的工具调用做确定性拦截。"""
    if tool_name == "Bash":
        command = str(tool_input.get("command", ""))
        if "screencapture" in command:
            return PermissionResultDeny(
                message=(
                    "Do not call screencapture manually. Use the MCP tool "
                    "take_screenshot so the screenshot is stored under "
                    "work_space/assets/images/screenshots, then call send_image."
                )
            )

    return PermissionResultAllow()


async def run_agent(prompt: str, bot: Any, chat_id: int, db_path:str) -> tuple[str, str]:
    """
    串行执行一次 agent 请求。

    对外暴露这一层，而不是让别的模块直接调 `_run_inner_agent()`，
    是为了把并发控制统一收口到这里。
    """
    async with _agent_lock:
        return await _run_inner_agent(prompt, bot, chat_id,db_path)


async def _run_inner_agent(prompt: str, bot: Any, chat_id: int,db_path:str) -> tuple[str, str]:
    """
    真正执行一次 Claude 查询。

    返回值是一个二元组：
    - 第一个字符串：最终要继续发给 Telegram 的文本
    - 第二个字符串：写入长期归档的文本
    """
    sent_messages: list[str] = []
    mcp_tools = create_mcp_server_tools(bot, chat_id, db_path, sent_messages=sent_messages)
    env = _build_agent_env()
    
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
        env=env,
        can_use_tool=_can_use_tool,
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

    result_text: str | None = None
    idx = 0

    async def _make_prompt(text: str)->AsyncGenerator[dict, None]:
        # 这里用异步生成器包装 prompt，是为了适配 SDK 的 streaming 输入形式。
        # 即使只有一条用户消息，也照样按“流”的协议喂给它。
        yield {
            "type": "user",
            "message": {"role": "user", "content": _apply_task_hints(text)},
        }

    try:
        async for message in query(prompt=_make_prompt(prompt), options=options):
            idx += 1
            log_stream_message(idx, message)
            if isinstance(message, ResultMessage):
                # 最终结果只认 ResultMessage。
                # 这样“最终回复”只有一个真相源，不再混用 AssistantMessage 的 text。
                save_session_id(message.session_id)
                if message.result:
                    result_text = message.result
    except Exception as error:
        LOGGER.error("Error during agent execution: %s", error)
        error_text = f"Error: {error}"
        return error_text, error_text

    final_text = (result_text or "").strip() or "Sorry, I couldn't get a response from Claude."

    archive_parts = [text.strip() for text in sent_messages if text and text.strip()]
    archive_parts.append(final_text)
    archive_text = "\n".join(archive_parts)

    return final_text, archive_text

# 这个返回的文本是send message和ResultMessage的整合。
async def run_task_agent(prompt: str, bot: Any, chat_id: int,db_path:str, notify_state: dict[str, bool] | None = None) -> str:
    """Run agent for scheduled tasks — no session resume."""
    sent_messages: list[str] = []
    mcp_tools = create_mcp_server_tools(bot, chat_id, db_path, sent_messages=sent_messages,notify_state=notify_state)
    env = _build_agent_env()
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
        env=env,
        can_use_tool=_can_use_tool,
    )

    LOGGER.info(
        "Starting Claude query | cwd=%s | permission_mode=%s | model=%s | allowed_tools=%s",
        options.cwd,
        options.permission_mode,
        options.model or "default",
        ",".join(options.allowed_tools or []) or "-",
    )

    result_text: str | None = None

    async def _make_prompt(text: str)->AsyncGenerator[dict, None]:
        # 这里用异步生成器包装 prompt，是为了适配 SDK 的 streaming 输入形式。
        # 即使只有一条用户消息，也照样按“流”的协议喂给它。
        yield {
            "type": "user",
            "message": {"role": "user", "content": _apply_task_hints(text)},
        }
    idx = 0
    try:
        async for message in query(prompt=_make_prompt(prompt), options=options):
            idx += 1
            log_stream_message(idx, message)
            if isinstance(message, ResultMessage):
                # 最终结果只认 ResultMessage。
                # 这样“最终回复”只有一个真相源，不再混用 AssistantMessage 的 text。
                if message.result:
                    result_text = message.result
    except Exception as error:
        LOGGER.error("Task agent error: %s", error)
        error_text = f"Error: {error}"
        return error_text

    final_text = (result_text or "").strip() or "Sorry, I couldn't get a response from Claude."

    archive_parts = [text.strip() for text in sent_messages if text and text.strip()]
    archive_parts.append(final_text)
    archive_text = "\n".join(archive_parts)


    return archive_text or "Task completed."

