# ==========================================
# 🚀 Marker CUDA 啟動腳本 - 2080 Ti 22G 終極優化版
# 硬體適配: RTX 2080 Ti (22GB) / i7-11800H / 32G RAM
# ==========================================

# --- 【核心修復】強制設定控制台為 UTF-8 輸出，解決亂碼 ---
$OutputEncoding = [System.Text.Encoding]::UTF8
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8
# ---------------------------------------------------

# 1. 基礎路徑配置
# Write-Host "請確保已激活虛擬環境 (venv)" -ForegroundColor Yellow
# 2. 輸出目錄 (請根據需要修改)
$env:MARKER_OUTPUT_DIR = "E:\研究資料\Marker_Results"
if (-not (Test-Path $env:MARKER_OUTPUT_DIR)) { New-Item -ItemType Directory -Path $env:MARKER_OUTPUT_DIR | Out-Null }

# 3. 通用設置
$env:MARKER_AUTO_DOWNLOAD = "true"
$env:PYTHONUNBUFFERED = "1"

# 4. CUDA 性能關鍵項 (針對 2080 Ti 22G 優化)
$env:TORCH_DEVICE = "cuda"
$env:CUDA_VISIBLE_DEVICES = "0"
$env:USE_FP16 = "true"  # 2080 Ti FP16 性能極佳，必須開啟

# 顯存管理：已修正變數名，去除警告
$env:PYTORCH_ALLOC_CONF = "max_split_size_mb:1024" 
$env:TORCH_CUDNN_BENCHMARK = "1"

# 5. 併發設置 (針對 i7-11800H 優化)
# 獲取邏輯核心數 (11800H 通常是 16 執行緒)
$cpuThreads = [System.Environment]::ProcessorCount

# 限制推理執行緒為 12，留 4 個執行緒給系統響應，防止筆電卡死
$env:INFERENCE_THREADS = "12" 

# ==========================================
# 🔥 核心優化：OCR Batch Size (吞吐量關鍵)
# ==========================================
# 您的 22G 顯卡配合 352bit 位寬，起步建議 32
# 如果處理非常高清的 PDF 遇到 OOM，請降回 16-24
$env:OCR_BATCH_SIZE = "32"

# PDF 文本提取進程數
# 保持 4 個 worker 即可，過多會搶佔 OCR 的 CPU 資源
$env:PDFTEXT_WORKERS = "4"

# 6. 分批邏輯 (針對大文件)
$env:MARKER_ENABLE_BATCH = "true"
# 22G 顯存可以一次吞吐更多頁面，減少模型加載開銷
$env:MARKER_PAGES_PER_BATCH = "150" 
$env:MARKER_SPLIT_THRESHOLD = "50"

# ==========================================
# 📺 啟動信息面板
# ==========================================
Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host "🚀 MARKER for 2080 Ti 22G (魔改版) 啟動中..." -ForegroundColor Green
Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host "📁 輸出目錄 : $($env:MARKER_OUTPUT_DIR)" -ForegroundColor Yellow
Write-Host "⚡ 計算精度 : FP16 (Turing架構加速開啟)" -ForegroundColor Yellow
Write-Host "🔥 OCR Batch: $($env:OCR_BATCH_SIZE) (已針對 22G 顯存大幅擴容)" -ForegroundColor Red
Write-Host "🧠 推理執行緒 : $($env:INFERENCE_THREADS) / $cpuThreads (保留部分資源防卡頓)" -ForegroundColor Yellow
Write-Host "💾 顯存策略 : max_split_size_mb:1024" -ForegroundColor Yellow
Write-Host "=" * 60 -ForegroundColor Cyan

# GPU 檢查與信息打印
Write-Host "🔍 硬體自檢..." -ForegroundColor Magenta -NoNewline
try {
    # 打印更詳細的顯存信息以確認 22G 被正確識別
    $checkCmd = "import torch; dev=0; print(f' -> GPU: {torch.cuda.get_device_name(dev)}'); print(f' -> VRAM: {torch.cuda.get_device_properties(dev).total_memory/1024**3:.2f} GB');"
    python -c $checkCmd
    Write-Host " ✅ CUDA 環境正常" -ForegroundColor Green
} catch {
    Write-Host " ❌ 未檢測到 PyTorch CUDA 環境，請檢查 install!" -ForegroundColor Red
}

Write-Host "=" * 60 -ForegroundColor Cyan
Write-Host "🌐 Web UI 啟動中..." -ForegroundColor Cyan

# 獲取本機區域網 IP
$localIP = (Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.InterfaceAlias -notlike "*Loopback*" -and $_.InterfaceAlias -notlike "*vEthernet*" } | Select-Object -First 1).IPAddress

Write-Host "📍 本地訪問: http://localhost:8502" -ForegroundColor Green
if ($localIP) {
    Write-Host "📱 遠端訪問: http://$($localIP):8502" -ForegroundColor Green
}
Write-Host "=" * 60 -ForegroundColor Cyan

# 啟動 Streamlit
streamlit run marker\scripts\streamlit_app.py --server.port 8502 --server.headless true --server.maxUploadSize 1024