"""
对话归档模块。

这个模块负责把“用户的一句话 + 助手的一次回复”保存成 Markdown 文件，
并按日期归档到：
    work_space/conversations/YYYY-MM-DD.md

归档的目标不是短期上下文，而是长期可检索记忆：
- 人可以直接打开 Markdown 看历史
- Claude Code 也可以用 `Read / Grep / Glob` 去检索这些历史
"""

from datetime import datetime
from pathlib import Path

from .config import ASSISTANT_NAME, CONVERSATION_DIR


def archive_conversation(
    user_text: str,
    assistant_text: str,
    timestamp: datetime | None = None,
) -> Path:
    """
    把一轮完整对话写入当天的 Markdown 归档文件，并返回文件路径。

    这里的“一轮对话”是指：
    - 用户发来一条消息
    - 助手返回一条最终可见回复

    注意：这里归档的是“最终用户可见文本”，而不是底层 stream event。
    比如 thinking、tool log 这些调试信息不会写进长期归档。
    """
    current_time = timestamp or datetime.now()

    # 按天拆文件，而不是把所有历史都写进一个总文件。
    # 这样做的好处：
    # - 单个文件不会无限膨胀
    # - 更容易按日期定位
    # - 以后 Claude 搜索时范围也更可控
    CONVERSATION_DIR.mkdir(parents=True, exist_ok=True)

    conversation_file = CONVERSATION_DIR / f"{current_time:%Y-%m-%d}.md"
    current_time_text = current_time.strftime("%Y-%m-%d %H:%M:%S")

    # 统一换行符，避免不同平台（Windows/macOS/Linux）写入后格式混乱。
    # `strip()` 也顺手去掉首尾多余空白，让归档更干净。
    clean_user_text = user_text.strip().replace("\r\n", "\n").replace("\r", "\n")
    clean_assistant_text = assistant_text.strip().replace("\r\n", "\n").replace("\r", "\n")

    # 单行消息和多行消息分开处理，是为了让 Markdown 更易读。
    # 如果消息本身有换行，强行写成：
    #     **用户**: 第一行\n第二行
    # 可读性会差很多。
    if "\n" in clean_user_text:
        user_block = f"**用户**:\n{clean_user_text}"
    else:
        user_block = f"**用户**: {clean_user_text}"

    if "\n" in clean_assistant_text:
        assistant_block = f"**{ASSISTANT_NAME}**:\n{clean_assistant_text}"
    else:
        assistant_block = f"**{ASSISTANT_NAME}**: {clean_assistant_text}"

    new_turn_block = "\n".join(
        [
            f"## {current_time_text}",
            user_block,
            assistant_block,
        ]
    )

    start_time = current_time
    end_time = current_time
    existing_body = ""

    if conversation_file.exists():
        # 这里不是简单 append，而是“读旧文件 -> 算新头部 -> 整体重写”。
        # 原因是文件第一行维护了整天的时间范围：
        #     # 最早时间 - 最晚时间
        #
        # 如果只在尾部追加正文，头部就会变旧，不再准确。
        existing_content = conversation_file.read_text(encoding="utf-8").strip()
        if existing_content:
            lines = existing_content.splitlines()
            first_line = lines[0].strip()

            if first_line.startswith("# ") and " - " in first_line:
                range_text = first_line[2:]
                start_text, end_text = range_text.split(" - ", 1)

                try:
                    start_time = datetime.strptime(start_text.strip(), "%Y-%m-%d %H:%M:%S")
                    end_time = datetime.strptime(end_text.strip(), "%Y-%m-%d %H:%M:%S")
                    existing_body = "\n".join(lines[1:]).strip()
                except ValueError:
                    # 如果用户手动改坏了头部格式，我们宁可保留正文，
                    # 也不要因为解析失败把历史内容丢掉。
                    existing_body = existing_content
            else:
                existing_body = existing_content

    # 用新的对话时间去刷新“当天最早 / 最晚时间”。
    start_time = min(start_time, current_time)
    end_time = max(end_time, current_time)
    file_header = f"# {start_time:%Y-%m-%d %H:%M:%S} - {end_time:%Y-%m-%d %H:%M:%S}"

    if existing_body:
        new_content = f"{file_header}\n\n{existing_body}\n\n{new_turn_block}\n"
    else:
        new_content = f"{file_header}\n\n{new_turn_block}\n"

    conversation_file.write_text(new_content, encoding="utf-8")
    return conversation_file
