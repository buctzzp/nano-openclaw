"""
Claude SDK 流式事件日志模块。

Claude SDK 的 `query(...)` 返回的不是一条最终字符串，
而是一串流式事件，例如：
- SystemMessage
- AssistantMessage
- ResultMessage
- tool_use / tool_result

这个模块的职责，就是把这些底层事件格式化成更容易阅读的日志。

注意：
- 这里是“运行日志”
- 不是发给用户看的最终回复
- 也不是长期归档聊天记录
"""

import json
import logging

from claude_agent_sdk import ResultMessage, TextBlock, ToolResultBlock
from claude_agent_sdk.types import SystemMessage, ThinkingBlock, ToolUseBlock

LOGGER = logging.getLogger("nano_openclaw.agent")


def configure_logging() -> None:
    """Configure a readable logger for agent stream events."""
    if LOGGER.handlers:
        # 日志初始化做成幂等，是因为多个入口都可能重复调用它。
        # 如果每次都重复加 handler，日志会被打印多份。
        return

    handler = logging.StreamHandler()
    handler.setFormatter(
        logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s", datefmt="%H:%M:%S")
    )
    LOGGER.addHandler(handler)
    LOGGER.setLevel(logging.INFO)
    LOGGER.propagate = False


def truncate_text(value, limit: int = 160) -> str:
    """Return a compact single-line preview of text-like values."""
    if value is None:
        return ""

    # 日志里尽量保持单行，避免一个消息把整个控制台刷得太散。
    text = str(value).replace("\n", "\\n")
    if len(text) <= limit:
        return text
    return f"{text[: limit - 3]}..."


def format_stream_event(index: int, message) -> str:
    """Build a one-line summary for a streamed SDK event."""
    # 第一行只放“摘要信息”，比如事件类型、模型、session_id。
    # 更细的内容交给下面的 detail formatter。
    parts = [f"Event {index:02d}", message.__class__.__name__]

    model = getattr(message, "model", None)
    if model:
        parts.append(f"model={model}")

    subtype = getattr(message, "subtype", None)
    if subtype:
        parts.append(f"subtype={subtype}")

    session_id = getattr(message, "session_id", None)
    if session_id:
        parts.append(f"session={session_id}")

    parent_tool_use_id = getattr(message, "parent_tool_use_id", None)
    if parent_tool_use_id:
        parts.append(f"parent_tool={parent_tool_use_id}")

    return " | ".join(parts)


def format_message_details(message) -> list[str]:
    """Render readable detail lines for a streamed SDK event."""
    if isinstance(message, SystemMessage):
        data = getattr(message, "data", {}) or {}
        keys = ",".join(sorted(data.keys())) or "-"
        return [f"[system] data_keys={keys}"]

    if isinstance(message, ResultMessage):
        # ResultMessage 是最值得关注的收尾事件，
        # 因为它会携带：
        # - 最终 result
        # - token / cost 信息
        # - stop reason
        # - API 报错
        lines: list[str] = []
        if message.result:
            lines.append(f"[result] {truncate_text(message.result)}")

        lines.append(
            "[meta] "
            f"turns={message.num_turns} stop={message.stop_reason or '-'} "
            f"duration_ms={message.duration_ms} api_ms={message.duration_api_ms}"
        )
        if message.total_cost_usd is not None:
            lines.append(f"[meta] total_cost_usd={message.total_cost_usd}")
        if message.errors:
            lines.extend(f"[error] {truncate_text(error)}" for error in message.errors)
        return lines

    content = getattr(message, "content", None)
    if isinstance(content, str):
        return [f"[text] {truncate_text(content)}"]

    lines: list[str] = []
    if isinstance(content, list):
        for block in content:
            lines.extend(format_content_block(block))

    tool_use_result = getattr(message, "tool_use_result", None)
    if tool_use_result:
        lines.extend(format_tool_use_result(tool_use_result))

    if not lines:
        lines.append("[empty] no printable content")

    return lines


def format_content_block(block) -> list[str]:
    """Format one content block from the SDK stream."""
    # Claude SDK 会把 AssistantMessage.content 拆成多种 block。
    # 这里按 block 类型分别格式化，便于你观察模型到底做了什么。
    if isinstance(block, TextBlock):
        return [f"[text] {truncate_text(block.text)}"]

    if isinstance(block, ThinkingBlock):
        return [f"[thinking] {truncate_text(block.thinking)}"]

    if isinstance(block, ToolUseBlock):
        payload = json.dumps(block.input, ensure_ascii=False, sort_keys=True)
        return [f"[tool_use] {block.name} input={truncate_text(payload)}"]

    if isinstance(block, ToolResultBlock):
        status = "error" if block.is_error else "ok"
        return [f"[tool_result] {status} {truncate_text(block.content)}"]

    return [f"[block:{block.__class__.__name__}] {truncate_text(block)}"]


def format_tool_use_result(tool_use_result: object) -> list[str]:
    """Format the structured tool execution payload returned by the SDK."""
    if isinstance(tool_use_result, dict):
        lines: list[str] = []
        result_type = tool_use_result.get("type")
        if result_type:
            lines.append(f"[tool_output] type={result_type}")

        file_path = tool_use_result.get("filePath")
        if file_path:
            lines.append(f"[tool_output] file={file_path}")

        stdout = tool_use_result.get("stdout")
        if stdout:
            lines.append(f"[tool_output] stdout={truncate_text(stdout)}")

        stderr = tool_use_result.get("stderr")
        if stderr:
            lines.append(f"[tool_output] stderr={truncate_text(stderr)}")

        if not lines:
            lines.append(
                f"[tool_output] {truncate_text(json.dumps(tool_use_result, ensure_ascii=False, sort_keys=True))}"
            )
        return lines

    return [f"[tool_output] {truncate_text(tool_use_result)}"]


def log_stream_message(index: int, message) -> None:
    """Emit one formatted stream event to the logger."""
    # 每个事件分三段打印：
    # 1. 摘要
    # 2. 详细内容
    # 3. 分隔线
    #
    # 这样看长会话日志时，结构会比较清楚。
    LOGGER.info("%s", format_stream_event(index, message))
    for line in format_message_details(message):
        LOGGER.info("  %s", line)
    LOGGER.info("%s", "-" * 72)
