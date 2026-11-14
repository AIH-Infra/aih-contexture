import os
from pathlib import Path

# 设置模型缓存目录（启动脚本可用同名环境变量覆盖到实例专属数据目录；
# 未注入时回落到项目内 .cache，保持 dev 直启行为不变）
cache_dir = Path(__file__).parent / ".cache"
os.environ.setdefault("HF_HOME", str(cache_dir / "huggingface"))
os.environ.setdefault("TRANSFORMERS_CACHE", str(cache_dir / "huggingface"))
os.environ.setdefault("TORCH_HOME", str(cache_dir / "torch"))

from aih_contexture.scripts.run_streamlit_app import streamlit_app_cli

if __name__ == "__main__":
    streamlit_app_cli()