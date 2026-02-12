# VLM Direct - 最快落地方案

## 🎯 核心思路

**跳过所有中间步骤，直接用 VLM 处理整页返回 Markdown**

```
传统方案：PDF → Layout → OCR → 结构化 → Markdown（复杂）
VLM Direct：PDF → VLM → Markdown（简单）
```

## ✅ 已完成的工作

### 1. 核心 Converter
- **文件**: `marker/converters/vlm_direct.py`
- **功能**: 直接用 VLM 处理整页，返回 Markdown
- **特点**:
  - 支持所有 OpenAI 兼容 API
  - 自动图像缩放和压缩
  - 自动重试机制
  - 可配置提示词

### 2. 命令行工具
- **文件**: `vlm_direct_convert.py`
- **功能**: 简单易用的命令行接口
- **示例**:
  ```bash
  python vlm_direct_convert.py input.pdf --api-key sk-xxx
  ```

### 3. 测试脚本
- **文件**: `test_vlm_direct.py`
- **功能**: 验证功能是否正常

### 4. 完整文档
- **文件**: `VLM_DIRECT_GUIDE.md`
- **内容**: 详细的使用指南、模型推荐、成本估算

## 🚀 快速使用

### 方法 1: 使用 OpenAI API（推荐）

```bash
# 安装依赖（如果还没安装）
pip install openai pillow

# 转换文档
python vlm_direct_convert.py your_document.pdf \
    --model gpt-4o-mini \
    --api-key sk-your-openai-key
```

### 方法 2: 使用 LM Studio（本地免费）

```bash
# 1. 启动 LM Studio，加载支持视觉的模型
# 2. 启动本地服务器（默认 http://localhost:1234）

# 3. 转换文档
python vlm_direct_convert.py your_document.pdf \
    --base-url http://localhost:1234/v1 \
    --model your-model-name \
    --api-key lm-studio
```

### 方法 3: 使用通义千问（国内推荐）

```bash
python vlm_direct_convert.py your_document.pdf \
    --base-url https://dashscope.aliyuncs.com/compatible-mode/v1 \
    --model qwen-vl-max \
    --api-key sk-your-qwen-key
```

## 📊 性能对比

| 方案 | 实现难度 | 准确度 | 速度 | 成本 |
|------|---------|--------|------|------|
| **VLM Direct** | ⭐⭐⭐⭐⭐ 最简单 | ⭐⭐⭐⭐⭐ 最高 | ⭐⭐ 慢 | ⭐⭐ 高 |
| Surya Layout + OCR | ⭐⭐⭐ 中等 | ⭐⭐⭐ 中等 | ⭐⭐⭐⭐ 快 | ⭐⭐⭐⭐⭐ 免费 |
| YOLO + Surya | ⭐ 最复杂 | ⭐⭐⭐⭐ 高 | ⭐⭐⭐⭐⭐ 最快 | ⭐⭐⭐⭐⭐ 免费 |

## 💡 为什么这是最快落地方案？

### 1. 代码最少
- 只需要 1 个 converter 文件（300 行）
- 只需要 1 个命令行脚本（100 行）
- 无需修改现有代码

### 2. 依赖最少
- 只需要 `openai` 和 `pillow`
- 无需 PyTorch、CUDA、Docker
- 无需下载模型文件

### 3. 配置最简单
- 只需要 API key
- 无需配置 layout backend
- 无需配置 OCR backend
- 无需调整复杂参数

### 4. 效果最好
- 利用 GPT-4o/Claude 的强大能力
- 理解复杂文档结构
- 处理手写、古籍、多语言

## 🎯 适用场景

### ✅ 推荐使用

1. **快速原型**：需要快速验证效果
2. **复杂文档**：手写、古籍、特殊排版
3. **高质量要求**：学术论文、法律文件
4. **小批量处理**：几十页以内

### ❌ 不推荐使用

1. **大批量处理**：数百页以上（成本太高）
2. **实时处理**：需要秒级响应（太慢）
3. **成本敏感**：预算有限（用免费方案）

## 📝 完整示例

### 示例 1: 处理学术论文

```bash
# 使用 GPT-4o-mini（性价比最高）
python vlm_direct_convert.py paper.pdf \
    --model gpt-4o-mini \
    --api-key sk-xxx \
    --max-dimension 2048 \
    --jpeg-quality 90 \
    --output paper.md

# 成本：约 $0.20（100 页）
# 时间：约 3-5 分钟
```

### 示例 2: 处理中文古籍

```bash
# 使用通义千问 VL Max
python vlm_direct_convert.py ancient_book.pdf \
    --base-url https://dashscope.aliyuncs.com/compatible-mode/v1 \
    --model qwen-vl-max \
    --api-key sk-xxx \
    --max-dimension 2048 \
    --jpeg-quality 95

# 成本：约 ¥10（100 页）
# 时间：约 5-8 分钟
```

### 示例 3: 本地免费处理

```bash
# 使用 LM Studio + llava-v1.6-34b
python vlm_direct_convert.py document.pdf \
    --base-url http://localhost:1234/v1 \
    --model llava-v1.6-34b \
    --api-key lm-studio \
    --max-dimension 1536 \
    --jpeg-quality 85

# 成本：$0（完全免费）
# 时间：约 10-15 分钟（取决于 GPU）
```

## 🔧 故障排除

### 问题 1: ModuleNotFoundError

```bash
# 安装依赖
pip install openai pillow
```

### 问题 2: API Key 错误

```bash
# 检查 API key 是否正确
# OpenAI: 以 sk- 开头
# 通义千问: 以 sk- 开头
# LM Studio: 任意值（如 "lm-studio"）
```

### 问题 3: 超时错误

```bash
# 增加超时时间
python vlm_direct_convert.py input.pdf --timeout 300
```

## 📚 相关文件

- `marker/converters/vlm_direct.py` - 核心 Converter
- `vlm_direct_convert.py` - 命令行工具
- `test_vlm_direct.py` - 测试脚本
- `VLM_DIRECT_GUIDE.md` - 完整使用指南

## 🎉 总结

**VLM Direct 是最快落地的方案，因为：**

1. ✅ 代码最少（只需 2 个文件）
2. ✅ 依赖最少（只需 openai + pillow）
3. ✅ 配置最简单（只需 API key）
4. ✅ 效果最好（利用大模型能力）
5. ✅ 立即可用（无需训练、无需 Docker）

**下一步：**

```bash
# 1. 安装依赖
pip install openai pillow

# 2. 转换文档
python vlm_direct_convert.py your_file.pdf --api-key sk-xxx

# 3. 查看结果
cat your_file.md
```

就这么简单！🚀
