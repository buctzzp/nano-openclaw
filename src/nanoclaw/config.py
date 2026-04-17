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
ASSISTANT_NAME = "小黄"
STORE_DIR = BASE_DIR / "store"
DB_PATH = STORE_DIR / "nanoclaw.db"


# 这个模板会在第一次启动时写入 `work_space/claude.md`。
# 它的作用不是普通注释，而是给 Claude Code 提供一份“长期记忆说明书”。
# 后面我们会把这个文件内容追加到 system prompt 里。
CLAUDE_MD_TEMPLATE = f"""# {ASSISTANT_NAME} - 个人 AI 助手
你是 {ASSISTANT_NAME}, 一个运行在 Telegram 上的个人 AI 助手。

## 你的能力
- 在 {WORK_SPACE}/ 目录中读写、编辑文件
- 运行 bash 命令
- 搜索网络
- 通过 send_message 工具发送消息

## 记忆系统
- 这个文件 (CLAUDE.md) 是你的长期记忆
- `conversations/` 文件夹包含按日期整理的对话历史
- 使用 Glob 和 Grep 搜索过去的对话
- 随时更新这个文件来记住重要信息

## 对话历史
`{CONVERSATION_DIR}/` 中的文件按日期命名 (YYYY-MM-DD.md)。
例如: `Grep pattern="最喜欢的颜色" path="conversations/"` 可以找到相关对话。

## 用户偏好
（在了解用户后添加偏好）
"""
