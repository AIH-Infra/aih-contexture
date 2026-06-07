import os
from pathlib import Path

# 设置模型缓存目录
cache_dir = Path(__file__).parent / ".cache"
os.environ["HF_HOME"] = str(cache_dir / "huggingface")
os.environ["TRANSFORMERS_CACHE"] = str(cache_dir / "huggingface")
os.environ["TORCH_HOME"] = str(cache_dir / "torch")

from aih_contexture.scripts.run_streamlit_app import streamlit_app_cli

if __name__ == "__main__":
    streamlit_app_cli()