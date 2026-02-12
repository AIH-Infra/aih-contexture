import subprocess
import os
import sys


def streamlit_app_cli(app_name: str = "streamlit_app.py"):
    argv = sys.argv[1:]
    cur_dir = os.path.dirname(os.path.abspath(__file__))
    app_path = os.path.join(cur_dir, app_name)
    
    # ========== 🔧 窗口配置参数 ==========
    cmd = [
        "streamlit",
        "run",
        app_path,
        
        # 🌐 网络配置（端口由 .streamlit/config.toml 管理，默认 6006，支持自动+1）
        "--server.address", "localhost",       # 监听地址
        
        # 🎨 界面行为
        "--server.fileWatcherType", "none",    # 禁用文件监控（原配置保留）
        "--server.headless", "false",          # 改为 false 自动打开浏览器（原来是 true）
        "--browser.gatherUsageStats", "false", # 不收集统计
        
        # 🔄 开发模式（可选）
        # "--server.runOnSave", "true",        # 代码修改后自动重载
        
        # 🎨 主题配置（可选）
        "--theme.base", "light",                         # 浅色主题
        "--theme.primaryColor", "#FF4B4B",               # 主题色
        "--theme.backgroundColor", "#FFFFFF",            # 背景色
        "--theme.secondaryBackgroundColor", "#F0F2F6",   # 次要背景
        "--theme.textColor", "#262730",                  # 文字颜色
    ]
    # =====================================
    
    if argv:
        cmd += ["--"] + argv
    
    # 🔧 设置环境变量（强制使用 N 卡）
    env = {
        **os.environ, 
        "IN_STREAMLIT": "true",
        "CUDA_VISIBLE_DEVICES": "0",                    # 只用第一张显卡（5060 Ti）
        "PYTORCH_CUDA_ALLOC_CONF": "max_split_size_mb:512"  # 显存优化
    }
    
    subprocess.run(cmd, env=env)


def extraction_app_cli():
    streamlit_app_cli("extraction_app.py")