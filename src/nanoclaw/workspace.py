"""
工作区相关工具函数。

这个模块处理两件事：
1. 确保 `work_space/` 下的基础文件和目录存在
2. 读取 `claude.md`，并把它转换成 Claude SDK 能接受的 system prompt 结构

你可以把它理解成：
- `config.py` 负责“定义路径和模板”
- `workspace.py` 负责“真的把这些路径和模板落实到磁盘上”
"""

from .config import CLAUDE_MD_TEMPLATE, CONVERSATION_DIR, WORK_SPACE


def ensure_workspace_ready() -> None:
    """确保工作目录和记忆文件存在。"""
    # `mkdir(..., exist_ok=True)` 是幂等操作：
    # - 第一次运行会创建目录
    # - 之后再运行不会报错
    #
    # 这很适合启动阶段调用，因为我们不需要先判断目录在不在，
    # 直接“确保它存在”就可以了。
    WORK_SPACE.mkdir(parents=True, exist_ok=True)
    CONVERSATION_DIR.mkdir(parents=True, exist_ok=True)

    claude_md_path = WORK_SPACE / "claude.md"
    if not claude_md_path.exists():
        # 只有当文件不存在时才写模板，避免每次启动都把用户手动修改过的
        # `claude.md` 覆盖掉。
        claude_md_path.write_text(CLAUDE_MD_TEMPLATE, encoding="utf-8")


def build_system_prompt() -> dict[str, str] | None:
    """读取 work_space/claude.md，并把它追加到 Claude Code 默认 system prompt 后面。"""
    claude_md_path = WORK_SPACE / "claude.md"
    if not claude_md_path.exists():
        return None

    # 这里不是直接把 `claude.md` 当成完整 system prompt 覆盖掉，
    # 而是选择：
    #     保留 Claude Code 默认 system prompt
    #     再把 `claude.md` 追加进去
    #
    # 这样做的好处是：
    # - Claude Code 原本的 coding agent 行为还在
    # - 我们自己的长期记忆也会一起带进去
    # - 风险比“完全自定义 system prompt”更小
    claude_md_content = claude_md_path.read_text(encoding="utf-8").strip()
    if not claude_md_content:
        return None

    return {
        "type": "preset",
        "preset": "claude_code",
        "append": claude_md_content,
    }
