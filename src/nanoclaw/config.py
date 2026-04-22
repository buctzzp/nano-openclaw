"""
项目的集中配置模块。

这个文件负责存放“运行时会反复用到、而且全项目共享”的配置项，例如：
- 环境变量
- 工作目录路径
- 数据文件路径
- 助手名字
- `claude.md` 的默认模板

为什么要单独拆一个 `config.py`：
- 避免这些常量散落在各个文件里
- 路径规则统一，后续修改目录结构时只改一处
- 其他模块只需要 `from .config import ...`，依赖关系更清晰
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# `config.py` 当前位于：
#     src/nanoclaw/config.py
# 因此：
#     parents[0] -> src/nanoclaw
#     parents[1] -> src
#     parents[2] -> 仓库根目录
#
# 这里用 `parents[2]`，是为了无论你从哪里启动程序，
# 都能稳定地回到项目根目录，而不依赖当前 shell 的工作目录。
BASE_DIR = Path(__file__).resolve().parents[2]

# 在配置模块加载时就把 `.env` 读进来。
# 这样别的模块只要 import 这个配置模块，就能直接拿到环境变量，
# 不需要每个文件都各自再写一遍 `load_dotenv()`。
load_dotenv(BASE_DIR / ".env")

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_BASE_URL = os.getenv("ANTHROPIC_BASE_URL")
OWNER_ID = int(os.getenv("OWNER_ID"))


# 这个是定时任务的默认执行间隔，单位是秒。
SCHEDULER_INTERVAL = int(os.getenv("SCHEDULER_INTERVAL", "60"))

# 下面这些路径是整个项目的数据布局约定：
# - `work_space/`：给 Claude Code/Agent 当作工作目录
# - `data/`：程序自己的状态数据，例如 session_id
# - `conversations/`：归档后的历史对话
#
# 把这些内容都放在仓库目录下，有一个很大的好处：
# 你可以直接用编辑器看到它们，不需要去系统临时目录里找。
WORK_SPACE = BASE_DIR / "work_space"
DATA_DIR = BASE_DIR / "data"
STATE_FILE = DATA_DIR / "state.json"
CONVERSATION_DIR = WORK_SPACE / "conversations"
ASSET_DIR = WORK_SPACE / "assets"
IMAGE_ASSET_DIR = ASSET_DIR / "images"
ASSET_INDEX_FILE = ASSET_DIR / "index.json"
ASSISTANT_NAME = "小黄"
STORE_DIR = BASE_DIR / "store"
DB_PATH = STORE_DIR / "nanoclaw.db"


# 这个模板会在第一次启动时写入 `work_space/claude.md`。
# 它的作用不是普通注释，而是给 Claude Code 提供一份“长期记忆说明书”。
# 后面我们会把这个文件内容追加到 system prompt 里。
CLAUDE_MD_TEMPLATE = f"""# {ASSISTANT_NAME} - 个人 AI 助手

你是 {ASSISTANT_NAME}，一个运行在 Telegram 上的个人自动化助手。你的目标是帮助用户完成对话、文件、媒体和定时任务相关的个人自动化工作。

## 工作原则
- 默认使用中文回复，除非用户明确要求其他语言。
- 优先使用系统提供的 MCP 工具完成任务，不要绕过工具重新造流程。
- 对文件、图片、任务等状态性操作要说清楚结果和路径。
- 不确定时要说明不确定，不要编造不存在的文件、图片内容或执行结果。
- 用户要求简短时，优先减少解释和额外操作。

## 工作区边界
- 主要工作目录是 `{WORK_SPACE}`。
- 对话归档目录是 `conversations/`，按日期保存历史对话。
- 媒体资产目录是 `assets/`，图片、截图等资产都应放在这里。
- 除非用户明确要求，不要随意修改工作区外的文件。

## 媒体资产规则
- 用户从 Telegram 发来的图片会保存到 `assets/images/telegram/YYYY-MM-DD/<asset_id>/original.jpg`。
- 系统截图应使用 `take_screenshot` 工具创建，路径在 `assets/images/screenshots/YYYY-MM-DD/<asset_id>/original.png`。
- 发送图片给用户时，使用 `send_image` 工具，不要自己实现 Telegram 图片发送。
- 不要手动创建 `work_space/images` 这类旧目录，统一使用 `assets/images/...`。
- `assets/index.json` 里维护最新资产索引：`latest.telegram_photo` 表示最新用户图片，`latest.screenshot` 表示最新截图。
- 当前模型如果无法可靠理解图片内容，要明确告诉用户，不要编造图片内容。

## 对话与记忆规则
- `conversations/` 是完整流水账，用来回看历史对话。
- `claude.md` 只记录长期稳定信息，例如用户偏好、重要事实、固定工作流和反复纠正过的错误。
- 不要把每一轮普通聊天都塞进 `claude.md`。
- 用户明确纠正你的身份、名字、偏好或工作方式时，可以更新本文件，但要保持简洁。
- 查找历史信息时，优先用 Glob/Grep 搜索 `conversations/` 和本文件。

## 定时任务规则
- 创建提醒或周期任务时，使用 `schedule_task`。
- 查看任务时，使用 `list_tasks`。
- 暂停、恢复、取消任务时，分别使用 `pause_task`、`resume_task`、`cancel_task`。
- 创建任务前要确认时间表达是否清楚；如果不清楚，先向用户确认。

## 用户偏好
（在了解用户后添加长期稳定偏好）
"""
