"""
项目运行入口。
"""
import sys
from pathlib import Path
# 这里手动把仓库下的 `src/` 加入模块搜索路径。。
# 如果不加这一步，Python 默认只会从当前目录等少数位置找模块，
# 而不会自动把 `src/` 当成包根目录。
SRC_DIR = Path(__file__).resolve().parent / "src"
# 这个只会影响模块导入，对其他的任何的文件路径操作都没影响！

src_path = str(SRC_DIR)
if src_path in sys.path:
    #print(f"注意：{src_path} 已经在 sys.path 中了，可能是之前的某个操作加过了。")
    sys.path.remove(src_path)

# 把 src_path 插入到 sys.path 的最前面，确保我们导入的模块都是 src/ 下面的，而不是系统全局安装的同名模块。
sys.path.insert(0, src_path)


from nanoclaw import app


def main() -> None:
    app.main()


if __name__ == "__main__":
    main()
