# VLM Direct Converter - 使用指南

## 概述

**VLM Direct Converter** 是一个全新的转换方案，跳过传统的 Layout Detection + OCR 流程，直接使用超强视觉大模型（VLM）处理整页文档，返回 Markdown 格式。

### 核心理念

```
传统方案：PDF → Layout Detection → OCR → 结构化 → Markdown
VLM Direct：PDF → VLM → Markdown（一步到位）
```

### 优势

✅ **最简单的流程**：只需一个 API 调用，无需复杂的 pipeline
✅ **最高的准确度**：利用 GPT-4o/Claude 3.5 等大模型的理解能力
✅ **最好的格式保持**：大模型能理解复杂的文档结构和语义
✅ **支持复杂文档**：手写、古籍、多语言、特殊排版都能处理

### 劣势

⚠️ **速度较慢**：每页需要调用一次 API（2-5 秒/页）
⚠️ **成本较高**：大模型 API 按 token 计费
⚠️ **需要网络**：依赖外部 API 服务

## 快速开始

### 1. 基本使用

```bash
# 使用 OpenAI GPT-4o（需要 API key）
python vlm_direct_convert.py input.pdf --api-key sk-xxx

# 使用本地 LM Studio
python vlm_direct_convert.py input.pdf \
    --base-url http://localhost:1234/v1 \
    --model gpt-4o \
    --api-key lm-studio

# 使用 Claude（通过 OpenAI 兼容接口）
python vlm_direct_convert.py input.pdf \
    --base-url https://api.anthropic.com/v1 \
    --model claude-3-5-sonnet-20241022 \
    --api-key sk-ant-xxx

# 使用通义千问
python vlm_direct_convert.py input.pdf \
    --base-url https://dashscope.aliyuncs.com/compatible-mode/v1 \
    --model qwen-vl-max \
    --api-key sk-xxx
```

### 2. 指定输出文件

```bash
python vlm_direct_convert.py input.pdf --output result.md
```

### 3. 调整图像质量

```bash
# 提高图像质量（更准确，但更慢/更贵）
python vlm_direct_convert.py input.pdf \
    --max-dimension 2048 \
    --jpeg-quality 95

# 降低图像质量（更快/更便宜，但可能不准确）
python vlm_direct_convert.py input.pdf \
    --max-dimension 1024 \
    --jpeg-quality 80
```

## 推荐模型

### 1. OpenAI GPT-4o（推荐）

**优点**：
- 准确度最高
- 速度快（2-3 秒/页）
- 支持高分辨率图像

**成本**：
- 输入：$2.50 / 1M tokens
- 输出：$10.00 / 1M tokens
- 单页约 $0.01-0.03

**配置**：
```bash
python vlm_direct_convert.py input.pdf \
    --base-url https://api.openai.com/v1 \
    --model gpt-4o \
    --api-key sk-xxx
```

### 2. GPT-4o-mini（性价比之选）

**优点**：
- 成本低（便宜 10 倍）
- 速度快
- 准确度较高

**成本**：
- 输入：$0.15 / 1M tokens
- 输出：$0.60 / 1M tokens
- 单页约 $0.001-0.003

**配置**：
```bash
python vlm_direct_convert.py input.pdf \
    --model gpt-4o-mini \
    --api-key sk-xxx
```

### 3. Claude 3.5 Sonnet（高质量）

**优点**：
- 准确度极高
- 理解能力强
- 适合复杂文档

**成本**：
- 输入：$3.00 / 1M tokens
- 输出：$15.00 / 1M tokens
- 单页约 $0.02-0.05

**配置**：
```bash
# 需要使用 OpenAI 兼容接口（如 LiteLLM）
python vlm_direct_convert.py input.pdf \
    --base-url http://localhost:8000/v1 \
    --model claude-3-5-sonnet-20241022 \
    --api-key sk-ant-xxx
```

### 4. 通义千问 VL Max（国内推荐）

**优点**：
- 国内访问快
- 支持中文文档
- 成本适中

**成本**：
- 约 ¥0.02 / 1K tokens
- 单页约 ¥0.05-0.15

**配置**：
```bash
python vlm_direct_convert.py input.pdf \
    --base-url https://dashscope.aliyuncs.com/compatible-mode/v1 \
    --model qwen-vl-max \
    --api-key sk-xxx
```

### 5. 本地模型（LM Studio）

**优点**：
- 完全免费
- 无需网络
- 数据隐私

**缺点**：
- 准确度较低（小模型）
- 需要强大的 GPU

**推荐模型**：
- `llava-v1.6-34b`（需要 48GB+ 显存）
- `qwen2-vl-7b`（需要 16GB+ 显存）

**配置**：
```bash
python vlm_direct_convert.py input.pdf \
    --base-url http://localhost:1234/v1 \
    --model llava-v1.6-34b \
    --api-key lm-studio
```

## 高级配置

### 1. 自定义提示词

创建 `custom_prompt.txt`：
```
请将这个文档页面转换为 Markdown 格式。

特殊要求：
1. 保留所有数学公式（使用 LaTeX 语法）
2. 表格使用 Markdown 表格语法
3. 代码块使用 ```language``` 语法
4. 保持原文的段落结构

只输出 Markdown 内容，不要添加任何解释。
```

使用：
```bash
python vlm_direct_convert.py input.pdf --prompt "$(cat custom_prompt.txt)"
```

### 2. 调整页面分隔符

```bash
# 使用自定义分隔符
python vlm_direct_convert.py input.pdf --page-separator "\n\n<!-- PAGE BREAK -->\n\n"

# 不使用分隔符（直接拼接）
python vlm_direct_convert.py input.pdf --page-separator ""
```

### 3. 调整超时和重试

```bash
# 增加超时时间（处理大页面）
python vlm_direct_convert.py input.pdf --timeout 300

# 增加重试次数（网络不稳定）
python vlm_direct_convert.py input.pdf --max-retries 5
```

## 成本估算

### 示例：100 页学术论文

| 模型 | 单页成本 | 总成本 | 总时间 |
|------|---------|--------|--------|
| GPT-4o | $0.02 | $2.00 | 5 分钟 |
| GPT-4o-mini | $0.002 | $0.20 | 3 分钟 |
| Claude 3.5 | $0.03 | $3.00 | 8 分钟 |
| Qwen VL Max | ¥0.10 | ¥10.00 | 6 分钟 |
| 本地模型 | $0 | $0 | 15 分钟 |

## 适用场景

### ✅ 推荐使用

1. **复杂文档**：手写、古籍、特殊排版
2. **高质量要求**：学术论文、法律文件、技术文档
3. **小批量处理**：几十页以内的文档
4. **多语言文档**：混合语言、罕见语言
5. **特殊格式**：数学公式、化学结构、乐谱

### ❌ 不推荐使用

1. **大批量处理**：数百页以上（成本太高）
2. **简单文档**：纯文本 PDF（用传统 OCR 更快）
3. **实时处理**：需要秒级响应（太慢）
4. **成本敏感**：预算有限（用 Surya/YOLO）

## 与其他方案对比

| 方案 | 速度 | 准确度 | 成本 | 复杂度 | 适用场景 |
|------|------|--------|------|--------|----------|
| **VLM Direct** | ⭐⭐ 慢 | ⭐⭐⭐⭐⭐ 最高 | ⭐⭐ 高 | ⭐⭐⭐⭐⭐ 最简单 | 复杂文档、高质量 |
| **Surya Layout + OCR** | ⭐⭐⭐⭐ 快 | ⭐⭐⭐ 中等 | ⭐⭐⭐⭐⭐ 免费 | ⭐⭐⭐ 中等 | 通用文档 |
| **YOLO + Surya** | ⭐⭐⭐⭐⭐ 最快 | ⭐⭐⭐⭐ 高 | ⭐⭐⭐⭐⭐ 免费 | ⭐⭐ 复杂 | 生产环境 |
| **VLM Layout + VLM OCR** | ⭐ 最慢 | ⭐⭐⭐⭐ 高 | ⭐ 最高 | ⭐⭐⭐ 中等 | 特殊需求 |

## 故障排除

### 1. API 密钥错误

```
Error: Invalid API key
```

**解决**：
- 检查 API key 是否正确
- 确认 API key 有足够的额度
- 检查 base URL 是否正确

### 2. 超时错误

```
Error: APITimeoutError
```

**解决**：
```bash
# 增加超时时间
python vlm_direct_convert.py input.pdf --timeout 300
```

### 3. 图像太大

```
Error: Image size exceeds limit
```

**解决**：
```bash
# 降低图像分辨率
python vlm_direct_convert.py input.pdf --max-dimension 1536
```

### 4. 输出不完整

```
输出的 Markdown 被截断
```

**解决**：
```bash
# 增加最大 token 数
python vlm_direct_convert.py input.pdf --max-tokens 16384
```

## 最佳实践

### 1. 选择合适的模型

- **高质量文档**：GPT-4o 或 Claude 3.5
- **一般文档**：GPT-4o-mini
- **中文文档**：Qwen VL Max
- **预算有限**：本地模型

### 2. 优化图像质量

- **清晰扫描件**：max-dimension=2048, jpeg-quality=90
- **模糊扫描件**：max-dimension=2048, jpeg-quality=95
- **原生 PDF**：max-dimension=1536, jpeg-quality=85

### 3. 批量处理

```bash
# 使用循环处理多个文件
for file in *.pdf; do
    python vlm_direct_convert.py "$file" --model gpt-4o-mini
done
```

### 4. 监控成本

```bash
# 先处理一页测试成本
python vlm_direct_convert.py input.pdf --model gpt-4o-mini
# 查看日志中的 token 使用情况
# 估算总成本 = 单页成本 × 总页数
```

## 总结

**VLM Direct Converter** 是最简单、最准确的文档转换方案，特别适合：

1. 需要最高质量的场景
2. 处理复杂/特殊文档
3. 小批量处理
4. 快速原型开发

如果您需要：
- **更快的速度** → 使用 YOLO + Surya
- **更低的成本** → 使用 Surya Layout + OCR
- **批量处理** → 使用传统 pipeline

**推荐工作流**：
1. 用 VLM Direct 处理少量样本，验证效果
2. 如果效果满意，继续使用
3. 如果需要批量处理，切换到 YOLO + Surya
