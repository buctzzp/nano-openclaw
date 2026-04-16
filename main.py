"""
项目运行入口。

这个文件刻意保持得非常薄，只负责两件事：
1. 把 `src/` 加进 Python 的导入搜索路径
2. 调用真正的应用入口 `nanoclaw.app.main()`

为什么这里写的是：
    from nanoclaw import app as app_module
而不是：
    from src.nanoclaw import app as app_module

原因是我们现在采用的是常见的 “src 布局” 工程结构：
- `src/` 是源码根目录
- `nanoclaw/` 是真正的 Python 包名

也就是说，一旦把 `src/` 放进 `sys.path`，Python 就会把 `src/` 当成“模块搜索根目录”。
这时包的正确导入方式是：
    import nanoclaw

而不是：
    import src.nanoclaw

后者的语义其实变成了“把 src 当成一个包再往下找 nanoclaw”，
这不符合我们这里的工程化布局，也不是打包安装后的标准导入方式。

简单记忆：
- `src/` 是源码容器，不是业务包名
- `nanoclaw/` 才是业务包
"""

import sys
from pathlib import Path

# 这里手动把仓库下的 `src/` 加入模块搜索路径。
# 这样你即使没有先执行 `pip install -e .`，也可以直接通过：
#     uv run main.py
# 来启动项目。
#
# 如果不加这一步，Python 默认只会从当前目录等少数位置找模块，
# 而不会自动把 `src/` 当成包根目录。
SRC_DIR = Path(__file__).resolve().parent / "src"
# 这个只会影响模块导入，对其他的任何的文件路径操作都没影响！

src_path = str(SRC_DIR)
if src_path in sys.path:
    #print(f"注意：{src_path} 已经在 sys.path 中了，可能是之前的某个操作加过了。")
    sys.path.remove(src_path)
sys.path.insert(0, src_path)

from nanoclaw import app as app_module


def main() -> None:
    """
    把启动流程委托给真正的应用模块。

    这样设计的好处是：
    - `main.py` 很稳定，几乎不需要改
    - 真正的业务启动逻辑都集中在包内，便于测试和维护
    - 以后如果你想从别的地方启动应用，也只需要调用 `nanoclaw.app.main`
    """
    app_module.main()


if __name__ == "__main__":
    main()
    #print(SRC_DIR)
    #print(sys.path)
