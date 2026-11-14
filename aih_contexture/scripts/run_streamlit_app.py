import os
import re
import socket
import subprocess
import sys
import time


DEFAULT_STREAMLIT_PORT = 8501
MAX_PORT_ATTEMPTS = 1000
DEFAULT_STREAMLIT_HOST = "0.0.0.0"
INTERRUPT_CONFIRM_SECONDS = 5.0
DISABLE_QUICK_EDIT_ENV = "CONTEXTURE_DISABLE_QUICK_EDIT"
PORT_ENV = "CONTEXTURE_PORT"
PORT_BASE_ENV = "CONTEXTURE_PORT_BASE"
PORT_RANGE_ENV = "CONTEXTURE_PORT_RANGE"
DEFAULT_PORT_RANGE = 10
INSTANCE_ENV = "CONTEXTURE_INSTANCE_ID"
BACKEND_ENV = "CONTEXTURE_EXPECT_BACKEND"


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
    # netsh 表里带 * 的是「管理的端口排除」（管理员手工添加，例如
    # netsh int ipv4 add excludedportrange ... 用来把端口带从 Hyper-V/
    # WinNAT 的动态保留中护住）。这类排除只约束 WinNAT 分配，应用仍可
    # bind()（实测通过）；无 * 的动态排除才真的拒绝 bind（WinError 10013）。
    # 因此只跳过动态排除——否则把端口带护住的同时应用自己反而起不来。
    pattern = re.compile(r"^\s*(\d+)\s+(\d+)\s*(\*.*?)?\s*$")
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
                check=False,
            )
        except OSError:
            continue

        # netsh 输出编码随控制台代码页变化（GBK/UTF-8 均可能出现），
        # 用字节捕获 + 宽松解码，端口段是纯数字，不受乱码影响。
        raw = result.stdout or b""
        output = raw.decode("utf-8", errors="replace")
        for line in output.splitlines():
            match = pattern.match(line)
            if not match:
                continue
            if match.group(3) is not None:
                continue  # 管理员排除：应用可 bind，不视为不可用。
            start, end = int(match.group(1)), int(match.group(2))
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


def _disable_windows_quick_edit() -> None:
    """Prevent accidental mouse selection from pausing the Windows console."""
    if os.name != "nt":
        return
    if str(os.environ.get(DISABLE_QUICK_EDIT_ENV, "")).strip().lower() not in {"1", "true", "yes", "on"}:
        return
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.GetStdHandle(-10)  # STD_INPUT_HANDLE
        mode = ctypes.c_uint()
        if not kernel32.GetConsoleMode(handle, ctypes.byref(mode)):
            return
        enable_quick_edit = 0x0040
        enable_extended_flags = 0x0080
        new_mode = (mode.value | enable_extended_flags) & ~enable_quick_edit
        kernel32.SetConsoleMode(handle, new_mode)
    except Exception:
        return


def _streamlit_creationflags() -> int:
    if os.name != "nt":
        return 0
    return getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)


def _terminate_process(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    try:
        proc.terminate()
        proc.wait(timeout=5)
    except Exception:
        try:
            proc.kill()
        except Exception:
            pass


def _wait_for_streamlit_process(proc: subprocess.Popen) -> int:
    last_interrupt_at: float | None = None
    while True:
        try:
            return int(proc.wait(timeout=0.5))
        except subprocess.TimeoutExpired:
            continue
        except KeyboardInterrupt:
            now = time.monotonic()
            if last_interrupt_at is None or now - last_interrupt_at > INTERRUPT_CONFIRM_SECONDS:
                last_interrupt_at = now
                print(
                    "[AIH-Contexture] 收到一次中断信号，Streamlit 仍保持运行。"
                    f"若要退出，请在 {INTERRUPT_CONFIRM_SECONDS:.0f} 秒内再次按 Ctrl+C。"
                )
                continue
            print("[AIH-Contexture] 收到二次中断，正在关闭 Streamlit。")
            _terminate_process(proc)
            return int(proc.returncode or 130)


def _parse_port(value: str, env_name: str) -> int:
    try:
        return int(value)
    except ValueError:
        raise SystemExit(f"[AIH-Contexture] {env_name}={value!r} 不是合法端口号。")


def _resolve_strict_port(host: str) -> int:
    """端口策略（按优先级）：

    1. CONTEXTURE_PORT 指定单一端口 -> 严格固定，占用即拒绝启动；
    2. CONTEXTURE_PORT_BASE 指定端口带起点 -> 在 [base, base+CONTEXTURE_PORT_RANGE)
       内自动找空位（默认带宽 10）。同一实例代码与前端资源哈希一致，带内
       漂移无害；跨实例串台由端口带结构性隔离（如 CUDA 8510+ / ROCm 8520+）；
    3. 都不设 -> 旧行为：从 DEFAULT_STREAMLIT_PORT 起自动找空位
       （dev 目录直启，多个 Streamlit 开发实例互不冲突）。

    核心约束不变：端口即实例身份，绝不在不同代码/版本之间静默换位，
    否则浏览器旧标签页会拿 A 实例的资源哈希请求 B 实例，
    触发 "Failed to fetch dynamically imported module"。
    """
    raw = os.environ.get(PORT_ENV, "").strip()
    if raw:
        port = _parse_port(raw, PORT_ENV)
        if not _is_port_available(host, port):
            raise SystemExit(
                f"[AIH-Contexture] 端口 {port} 已被占用，按固定端口策略拒绝启动。\n"
                f"  处理方式：关闭占用 {port} 的进程，或 set {PORT_ENV}=<空闲端口> 后重试。"
            )
        return port

    base_raw = os.environ.get(PORT_BASE_ENV, "").strip()
    if base_raw:
        base = _parse_port(base_raw, PORT_BASE_ENV)
        span_raw = os.environ.get(PORT_RANGE_ENV, "").strip()
        span = _parse_port(span_raw, PORT_RANGE_ENV) if span_raw else DEFAULT_PORT_RANGE
        try:
            return _find_available_port(host=host, start_port=base, max_attempts=span)
        except RuntimeError:
            raise SystemExit(
                f"[AIH-Contexture] 端口带 {base}-{base + span - 1} 已满，拒绝越带漂移。\n"
                f"  处理方式：释放带内端口，或调大 {PORT_RANGE_ENV}。"
            )

    return _find_available_port(host=host)


def _verify_instance_identity() -> None:
    """启动前自检：代码目录 / 解释器 / torch 后端三者必须匹配。

    防两类历史事故：
    1. 用 A 环境的解释器跑 B 目录的代码（曾造成命名空间包跨目录混装）；
    2. 启动器声明 CUDA 但 torch 是 ROCm 构建（或反之）。
    """
    from pathlib import Path

    import aih_contexture

    expected_pkg_dir = Path(__file__).resolve().parents[1]
    pkg_file = Path(getattr(aih_contexture, "__file__", "") or "").resolve()
    pkg_paths = [Path(p).resolve() for p in getattr(aih_contexture, "__path__", [])]
    if pkg_paths != [expected_pkg_dir] or pkg_file.parent != expected_pkg_dir:
        raise SystemExit(
            "[AIH-Contexture] aih_contexture 路径污染，拒绝启动：\n"
            f"  期望包目录: {expected_pkg_dir}\n"
            f"  实际 __path__: {[str(p) for p in pkg_paths]}\n"
            f"  实际 __file__: {pkg_file}\n"
            "  请使用与本代码目录匹配的解释器/环境启动。"
        )

    expected_backend = os.environ.get(BACKEND_ENV, "").strip().lower()
    if expected_backend not in {"cuda", "rocm"}:
        return
    try:
        import torch
    except Exception as exc:
        print(f"[AIH-Contexture] 警告：无法导入 torch（{exc}），跳过后端校验。")
        return
    cuda_build = getattr(torch.version, "cuda", None)
    hip_build = getattr(torch.version, "hip", None)
    if expected_backend == "cuda" and not cuda_build:
        raise SystemExit(
            f"[AIH-Contexture] 启动器声明 NVIDIA/CUDA，但当前 torch 不是 CUDA 构建"
            f"（cuda={cuda_build}, hip={hip_build}）。解释器/环境不匹配，拒绝启动。"
        )
    if expected_backend == "rocm" and not hip_build:
        raise SystemExit(
            f"[AIH-Contexture] 启动器声明 AMD/ROCm，但当前 torch 不是 ROCm 构建"
            f"（cuda={cuda_build}, hip={hip_build}）。解释器/环境不匹配，拒绝启动。"
        )


def streamlit_app_cli(app_name: str = "streamlit_app.py"):
    argv = sys.argv[1:]
    if "--help" in argv or "-h" in argv:
        command_name = os.path.basename(sys.argv[0]) if sys.argv else "contexture_gui"
        print(
            f"Usage: {command_name} [STREAMLIT_ARGS ...]\n\n"
            "Start the AIH-Contexture Streamlit app. Extra arguments are forwarded to Streamlit.\n"
            "Use `python -m streamlit run <app.py>` to pass Streamlit options directly."
        )
        return
    _verify_instance_identity()
    cur_dir = os.path.dirname(os.path.abspath(__file__))
    app_path = os.path.join(cur_dir, app_name)
    host = DEFAULT_STREAMLIT_HOST
    port = _resolve_strict_port(host=host)

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
        "--browser.serverAddress", "localhost",  # 自动打开的地址（服务仍绑定 0.0.0.0；直接开 0.0.0.0 浏览器会报"找不到网页"）
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
        PORT_ENV: str(port),  # 让页面能显示实际监听端口
    }

    instance_id = os.environ.get(INSTANCE_ENV, "").strip() or "dev"
    backend_tag = os.environ.get(BACKEND_ENV, "").strip().upper() or "未声明"
    print(f"[AIH-Contexture] 实例: {instance_id} | 后端: {backend_tag} | 版本: 见页面")
    local_ip = _get_local_ip()
    print(f"[AIH-Contexture] Streamlit 将监听 http://{host}:{port}")
    print(f"[AIH-Contexture] 本机访问: http://127.0.0.1:{port}")
    print(f"[AIH-Contexture] 本机访问: http://localhost:{port}")
    if local_ip:
        print(f"[AIH-Contexture] 局域网访问: http://{local_ip}:{port}")
    _disable_windows_quick_edit()
    proc = subprocess.Popen(cmd, env=env, creationflags=_streamlit_creationflags())
    returncode = _wait_for_streamlit_process(proc)
    if returncode != 0:
        print("[AIH-Contexture] Streamlit 启动失败。")
        print("[AIH-Contexture] 请先查看上方报错；若提示缺少模块或导入失败，请重新运行安装脚本。")
        print("[AIH-Contexture] 若问题持续存在，当前虚拟环境可能不完整。")
        raise SystemExit(returncode)


def extraction_app_cli():
    streamlit_app_cli("extraction_app.py")

if __name__ == "__main__":
    streamlit_app_cli()
