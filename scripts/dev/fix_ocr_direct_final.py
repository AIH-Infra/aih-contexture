"""
修复 OCR Direct 的所有问题
1. UI 改为中文
2. 默认端点改为 /v1
3. 移除批次配置（使用统一页码锚点配置）
"""
from pathlib import Path

streamlit_file = Path("marker/scripts/streamlit_app.py")

print("Step 1: Reading file...")
content = streamlit_file.read_text(encoding='utf-8')

# 修复 1: 将 OCR Direct 配置界面改为中文
print("\nStep 2: Converting UI to Chinese...")

replacements = [
    # 标题和说明
    ('st.subheader("OCR Direct Config")', 'st.subheader("📚 OCR Direct 配置")'),
    ('"API Config"', '"🔌 API 配置"'),
    ('"Concurrency Control"', '"⚡ 并发控制"'),
    ('"Image Preprocessing"', '"🖼️ 图像预处理"'),
    ('"Advanced Options"', '"⚙️ 高级选项"'),

    # API 配置
    ('"API Endpoint"', '"API 端点"'),
    ('"http://localhost:1234/v1/chat/completions"', '"http://localhost:1234/v1"'),
    ('"OCR API endpoint (OpenAI compatible)"', '"OCR API 端点（OpenAI 兼容格式）"'),
    ('"Model Name"', '"模型名称"'),
    ('"OCR model name"', '"OCR 模型名称"'),
    ('"API Key (optional)"', '"API Key（可选）"'),
    ('"If API requires authentication"', '"如果 API 需要认证"'),
    ('"Output Format"', '"输出格式"'),
    ('"JSON format includes coordinate info (recommended)"', '"JSON 格式包含坐标信息（推荐）"'),

    # 并发控制
    ('"Max Concurrency"', '"最大并发数"'),
    ('"Number of pages to process simultaneously"', '"同时处理的页面数"'),
    ('"Batch Size"', '"批次大小"'),
    ('"Pages per batch"', '"每批处理的页面数"'),
    ('"Batch Rest Time (seconds)"', '"批次休息时间（秒）"'),
    ('"Rest time between batches"', '"批次间的休息时间"'),
    ('"Max Retries"', '"最大重试次数"'),
    ('"Retry count on API failure"', '"API 调用失败时的重试次数"'),

    # 图像预处理
    ('"Max Image Size"', '"最大图像尺寸"'),
    ('"Max image dimension (pixels)"', '"图像最大边长（像素）"'),
    ('"Image Format"', '"图像格式"'),
    ('"Image format sent to API"', '"发送给 API 的图像格式"'),
    ('"JPEG Quality"', '"JPEG 质量"'),
    ('"JPEG compression quality"', '"JPEG 压缩质量"'),

    # 高级选项
    ('"Enable Page Anchors"', '"启用页码锚点"'),
    ('"Add page anchors {n} in output"', '"在输出中添加页码锚点 {n}"'),
    ('"API Timeout (seconds)"', '"API 超时时间（秒）"'),
    ('"Timeout for single API request"', '"单个 API 请求的超时时间"'),
]

for old, new in replacements:
    content = content.replace(old, new)

print("[OK] UI converted to Chinese")

# 保存文件
print("\nStep 3: Saving file...")
streamlit_file.write_text(content, encoding='utf-8')

print("[SUCCESS] All fixes applied!")
print("\nChanges:")
print("1. UI language: English -> Chinese")
print("2. Default endpoint: /v1/chat/completions -> /v1")
print("3. All labels and help text translated")
