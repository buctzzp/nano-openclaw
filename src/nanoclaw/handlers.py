"""
Telegram handlers 模块。

这一层只处理 Telegram 相关的事情：
- 收命令
- 收文本消息
- 回消息
- 做 owner 权限判断

它不负责直接和 Claude SDK 打交道，真正的 LLM 调用被下放到 `agent.py`。
这样做的好处是界限清楚：
- handlers 关心“Telegram 交互”
- agent 关心“LLM 执行”
"""

from telegram import Update
from telegram.constants import ChatAction

from .agent import run_agent
from .config import OWNER_ID
from .conversation import archive_conversation
from .logging_utils import LOGGER, configure_logging
from .session_store import clear_session_id


def is_owner(update: Update) -> bool:
    """检查消息是否来自指定的 OWNER_ID 用户。"""
    return update.effective_user is not None and update.effective_user.id == OWNER_ID


async def start(update: Update, context) -> None:
    """当用户发送 /start 命令时，机器人会回复一条欢迎消息。"""
    if not is_owner(update):
        # 非 owner 保持静默，避免暴露 bot 的存在和行为细节。
        return

    configure_logging()
    LOGGER.info(
        "Received /start | chat_id=%s | user_id=%s",
        getattr(update.effective_chat, "id", None),
        getattr(update.effective_user, "id", None),
    )
    res = """
    Hello! I'm your Telegram nano_openclaw.
    我可以记住我们之间的对话，即使重启也不会忘记！
    试试：
    1.告诉我你的名字
    2.重启程序
    3.再次告诉我你的名字，看看我还记不记得你。
    命令：
    /start - 开始对话
    /end - 结束对话
    /clear - 清除会话记录，重新开始
    """
    await update.message.reply_text(res)


async def end(update: Update, context) -> None:
    """当用户发送 /end 命令时，机器人会回复一条结束消息。"""
    if not is_owner(update):
        return

    await update.message.reply_text("Goodbye! See you next time.")


async def clear(update: Update, context) -> None:
    """当用户发送 /clear 命令时，机器人会清除会话并回复一条消息。"""
    if not is_owner(update):
        return

    # `/clear` 只清掉短期 session 续聊状态，不会删除长期的 Markdown 归档。
    clear_session_id()
    await update.message.reply_text("Session cleared. Starting fresh!")


async def handle_message(update: Update, context) -> None:
    """处理用户消息，发送给 Claude Agent，并回复结果。"""
    if not is_owner(update):
        return

    if not update.message or not update.message.text:
        # 当前 bot 只处理文本消息。图片、语音等类型暂时直接跳过。
        return

    chat_id = update.effective_chat.id
    # 先给 Telegram 客户端一个“正在输入”的反馈。
    # 这样用户在等待 LLM 返回时，不会觉得 bot 没有反应。
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    response = await run_agent(
        update.message.text,
        context.bot,
        chat_id,
    )

    # 长期归档只保存用户消息和最终回复。
    # 这样归档文件更像“聊天记录”，而不是“调试日志”。
    archive_conversation(update.message.text, response)

    max_length = 4000
    for i in range(0, len(response), max_length):
        # Telegram 单条消息有长度限制，所以长回复要手动切片发送。
        await update.message.reply_text(response[i : i + max_length])
