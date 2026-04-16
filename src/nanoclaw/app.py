"""
应用启动模块。

这一层负责把各个子模块真正装配成一个可运行的 Telegram bot：
- 初始化目录
- 初始化日志
- 创建 Telegram Application
- 注册所有 handler
- 启动 polling

也就是说，前面拆出来的那些模块在这里汇合。
"""

from telegram.ext import Application, CommandHandler, MessageHandler, filters

from .config import DATE_DIR, OWNER_ID, TELEGRAM_BOT_TOKEN, WORK_SPACE
from .handlers import clear, end, handle_message, start
from .logging_utils import LOGGER, configure_logging
from .workspace import ensure_workspace_ready


def main() -> None:
    """主函数，设置命令和消息处理器，并启动机器人。"""

    # 先准备本地目录和记忆文件，再启动 bot。
    # 这样后面的 handler / agent 运行时就可以假设这些基础设施已经存在。
    DATE_DIR.mkdir(parents=True, exist_ok=True)
    ensure_workspace_ready()
    configure_logging()

    # Application 是 python-telegram-bot 的核心对象。
    # 后面的命令处理器、消息处理器都会挂在这个对象上。
    app = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("end", end))
    app.add_handler(CommandHandler("clear", clear))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # 启动前打印关键运行信息，方便调试和确认配置是否正确。
    LOGGER.info("Bot is running...")
    LOGGER.info("工作目录是：%s", WORK_SPACE)
    LOGGER.info("只有用户%s可以使用这个机器人。", OWNER_ID)

    # `run_polling()` 会持续轮询 Telegram 服务器获取新消息。
    app.run_polling()
