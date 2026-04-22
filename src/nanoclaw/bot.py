"""
Telegram bot 模块。

这一层只处理 Telegram 相关的事情：
- 收命令
- 收文本消息
- 回消息
- 做 owner 权限判断
- set_up，初始化bot

它不负责直接和 Claude SDK 打交道，真正的 LLM 调用被下放到 `agent.py`。
这样做的好处是界限清楚：
- bot 关心“Telegram 交互”
- agent 关心“LLM 执行”
"""

from telegram import Update
from telegram.constants import ChatAction

from .agent import run_agent
from .config import *
from .conversation import archive_conversation
from .logging_utils import LOGGER, configure_logging
from .media import build_image_prompt, format_image_markdown, ingest_telegram_photo
from .session_control import clear_session_id
from telegram.ext import Application, CommandHandler, MessageHandler, filters
from nanoclaw.scheduler import setup_scheduler


def setup_bot() -> Application:
    # 这个app = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(_post_init).build()
    # 的_post_init是怎么运行的？
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).post_init(_post_init).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("end", end))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))
    return app

async def _post_init(application: Application) -> None:
    scheduler = setup_scheduler(application.bot, str(DB_PATH))
    scheduler.start()
    LOGGER.info("Scheduler started")


def is_owner(update: Update) -> bool:
    """检查消息是否来自指定的 OWNER_ID 用户。"""
    return update.effective_user is not None and update.effective_user.id == OWNER_ID


async def start(update: Update, context) -> None:
    """当用户发送 /start 命令时，机器人会回复一条欢迎消息。"""
    if not is_owner(update):
        # 非 owner 保持静默，避免暴露 bot 的存在和行为细节。
        return

    LOGGER.info(
        "Received /start | chat_id=%s | user_id=%s",
        getattr(update.effective_chat, "id", None),
        getattr(update.effective_user, "id", None),
    )
    res = f"""
{ASSISTANT_NAME} 已上线。

我现在可以：
1. 文字对话：把你的问题交给 Agent 处理，并归档对话。
2. 图片收发：保存你发来的图片，也可以把工作区里的图片发回 Telegram。
3. 截图发送：通过 take_screenshot 工具截图，再通过 send_image 发给你。
4. 定时任务：创建、查看、暂停、恢复、取消提醒任务。
5. 工作区文件：在 work_space 内读写文件，沉淀长期记忆和资产。

常用命令：
/start - 查看能力和使用提示
/clear - 清除当前 Claude session，重新开始短期上下文
/end - 结束当前对话提示

提示：如果你发送“图片 + 文字”，文字会作为图片配文一起处理。
""".strip()
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

    response_text, archive_text = await run_agent(
        update.message.text,
        context.bot,
        chat_id,
        str(DB_PATH)
    )

    max_length = 4000
    for i in range(0, len(response_text), max_length):
        # Telegram 单条消息有长度限制，所以长回复要手动切片发送。
        await update.message.reply_text(response_text[i : i + max_length])
    
    # 归档文本里既有过程中通过 `send_message` 发出去的消息，
    # 也有最后的 ResultMessage 文本。
    archive_conversation(update.message.text, archive_text)


async def handle_photo(update: Update, context) -> None:
    """处理用户发送的 Telegram 图片消息。"""
    if not is_owner(update):
        return

    if not update.message or not update.message.photo:
        return

    chat_id = update.effective_chat.id
    await context.bot.send_chat_action(chat_id=chat_id, action=ChatAction.TYPING)

    try:
        asset = await ingest_telegram_photo(update, chat_id)
    except Exception as error:
        LOGGER.error("Failed to ingest Telegram photo: %s", error)
        await update.message.reply_text(f"图片保存失败：{error}")
        return

    response_text, archive_text = await run_agent(
        # build_image_prompt也就是获取图片的说明
        build_image_prompt(asset),
        context.bot,
        chat_id,
        str(DB_PATH),
    )

    max_length = 4000
    for i in range(0, len(response_text), max_length):
        await update.message.reply_text(response_text[i : i + max_length])

    # format_image_markdown(asset) 是把图片的 markdown 格式也加到归档里，这样在查看归档的时候就能看到图片了。
    archive_conversation(format_image_markdown(asset), archive_text)
