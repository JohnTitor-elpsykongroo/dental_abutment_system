# utils/app_config.py
from pathlib import Path

# 项目根目录
PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ===== 程序内部资源路径 =====
# 这里改成你的实际袖口模型路径
INTERNAL_CUFF_MODEL_PATH = PROJECT_ROOT / "internal_data" / "cuff.ply"

# ===== 运行时输出目录 =====
RUNTIME_OUTPUT_DIR = PROJECT_ROOT / "outputs" / "runtime"
RUNTIME_OUTPUT_DIR.mkdir(parents=True, exist_ok=True)