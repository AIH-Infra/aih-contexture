import os
import re
import socket
import subprocess
import sys


DEFAULT_STREAMLIT_PORT = 8501
MAX_PORT_ATTEMPTS = 1000
DEFAULT_STREAMLIT_HOST = "0.0.0.0"


def _is_port_listening(host: str, port: int, family: socket.AddressFamily = socket.AF_INET) -> bool:
    with socket.socket(family, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.2)
        try:
            return sock.connect_ex((host, port)) == 0
        except OSError:
            return False


def _is_port_available(host: str, port: int) -> bool:
    listen_checks = [
        ("127.0.0.1", socket.AF_INET),
        ("localhost", socket.AF_INET),
    ]
    if socket.has_ipv6:
        listen_checks.append(("::1", socket.AF_INET6))

    for check_host, family in listen_checks:
        if _is_port_listening(check_host, port, family):
            return False

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        try:
            sock.bind((host, port))
        except OSError:
            return False

    if host in {"0.0.0.0", "::"}:
        return True

    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 0)
        try:
            sock.bind(("0.0.0.0", port))
        except OSError:
            return False
        return True


def _get_windows_excluded_ports() -> set[int]:
    if os.name != "nt":
        return set()

    excluded_ports: set[int] = set()
    pattern = re.compile(r"^\s*(\d+)\s+(\d+)\s*(?:\*.*)?$")
    for family in ("ipv4", "ipv6"):
        try:
            result = subprocess.run(
                [
                    "netsh",
                    "interface",
                    family,
                    "show",
                    "excludedportrange",
                    "protocol=tcp",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError:
            continue

        for line in result.stdout.splitlines():
            match = pattern.match(line)
            if not match:
                continue
            start, end = map(int, match.groups())
            excluded_ports.update(range(start, end + 1))
    return excluded_ports


def _find_available_port(
    host: str = DEFAULT_STREAMLIT_HOST,
    start_port: int = DEFAULT_STREAMLIT_PORT,
    max_attempts: int = MAX_PORT_ATTEMPTS,
) -> int:
    excluded_ports = _get_windows_excluded_ports()
    for port in range(start_port, start_port + max_attempts):
        if port in excluded_ports:
            continue
        if _is_port_available(host, port):
            return port
    raise RuntimeError(
        f"No available Streamlit port found in range {start_port}-{start_port + max_attempts - 1}."
    )


def _get_local_ip() -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            ip = sock.getsockname()[0]
            if ip and not ip.startswith("127."):
                return ip
    except OSError:
        return None
    return None


def streamlit_app_cli(app_name: str = "streamlit_app.py"):
    argv = sys.argv[1:]
    cur_dir = os.path.dirname(os.path.abspath(__file__))
    app_path = os.path.join(cur_dir, app_name)
    host = DEFAULT_STREAMLIT_HOST
    port = _find_available_port(host=host)

    # ========== 🔧 窗口配置参数 ==========
    cmd = [
        sys.executable,
        "-m",
        "streamlit",
        "run",
        app_path,

        # 🌐 网络配置（默认 8501，若占用则自动尝试 8502、8503...）
        "--server.address", host,
        "--server.port", str(port),

        # 🎨 界面行为
        "--server.fileWatcherType", "none",    # 禁用文件监控（原配置保留）
        "--server.headless", "false",          # 自动打开浏览器
        "--browser.gatherUsageStats", "false", # 不收集统计

        # 🎨 主题配置（可选）
        "--theme.base", "light",
        "--theme.primaryColor", "#FF4B4B",
        "--theme.backgroundColor", "#FFFFFF",
        "--theme.secondaryBackgroundColor", "#F0F2F6",
        "--theme.textColor", "#262730",
    ]
    # =====================================

    if argv:
        cmd += ["--"] + argv

    env = {
        **os.environ,
        "IN_STREAMLIT": "true",
        "CUDA_VISIBLE_DEVICES": "0",
        "PYTORCH_CUDA_ALLOC_CONF": "max_split_size_mb:512",
    }

    local_ip = _get_local_ip()
    print(f"[AIH-Contexture] Streamlit 将监听 http://{host}:{port}")
    print(f"[AIH-Contexture] 本机访问: http://127.0.0.1:{port}")
    print(f"[AIH-Contexture] 本机访问: http://localhost:{port}")
    if local_ip:
        print(f"[AIH-Contexture] 局域网访问: http://{local_ip}:{port}")
    result = subprocess.run(cmd, env=env)
    returncode = getattr(result, "returncode", 0)
    if returncode != 0:
        print("[AIH-Contexture] Streamlit 启动失败。")
        print("[AIH-Contexture] 请先查看上方报错；若提示缺少模块或导入失败，请重新运行安装脚本。")
        print("[AIH-Contexture] 若问题持续存在，当前虚拟环境可能不完整。")
        raise SystemExit(returncode)


def extraction_app_cli():
    streamlit_app_cli("extraction_app.py")
