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
import asyncio
from .config import OWNER_ID, WORK_SPACE,DB_PATH,STORE_DIR,DATA_DIR
from .bot import  setup_bot
from .logging_utils import LOGGER, configure_logging
from .workspace import ensure_workspace_ready
from nanoclaw.db import init_db


async def _prepare_runtime() -> None:
    # Create directories
    for d in (WORK_SPACE, STORE_DIR, DATA_DIR):
        d.mkdir(parents=True, exist_ok=True)

    # Initialize database
    await init_db(str(DB_PATH))
    LOGGER.info("Database initialized at %s", DB_PATH)

    # Ensure CLAUDE.md exists
    ensure_workspace_ready() # 这里是对WORKSPACE目录里面进行初始化，相当于init WorkspaceDir。
    LOGGER.info("Workspace ready at %s", WORK_SPACE)


def _run_bot() -> None:
    app = setup_bot()
    # 启动前打印关键运行信息，方便调试和确认配置是否正确。
    LOGGER.info("Bot is running...")
    LOGGER.info("工作目录是：%s", WORK_SPACE)
    LOGGER.info("只有用户%s可以使用这个机器人。", OWNER_ID)
    # `run_polling()` 会持续轮询 Telegram 服务器获取新消息。
    app.run_polling()



def main() -> None:
    """主函数，设置命令和消息处理器，并启动机器人。"""
    # 配置日志系统，确保我们在运行时能看到清晰的流式的日志输出。
    # 目前来讲这个流的日志输出对于我来说是一个盲盒。
    configure_logging()

    # 启动准备工作，创建工作目录、数据库存储目录和session会话的存储目录，启动数据库
    LOGGER.info("Preparing runtime environment...")
    asyncio.run(_prepare_runtime())
    # 启动 Telegram bot
    LOGGER.info("Starting Telegram bot...")
    _run_bot()

