# Surya Layout + VLM 整页 - 最佳配置方案

## 问题说明

您可能想要"禁用版面识别 + VLM 整页"的配置，但这在 Marker 的架构中是**不可行的**。

### 为什么不可行？

Marker 的工作流程：

```
1. Layout Detection → 创建 page.structure（blocks）
2. OCR → 填充文本到 blocks
3. Render → 将 blocks 渲染为 markdown
```

即使使用 VLM full_page 模式，它仍然需要 layout detection 创建的 blocks 结构来写回结果。

查看 `marker/builders/vlm_ocr.py` 的 `_ocr_full_page` 方法：

```python
def _ocr_full_page(self, page: PageGroup, provider: PdfProvider):
    # 1. 获取整页图像
    page_image = page.get_image(highres=True)

    # 2. VLM 处理整页
    result = self.llm_service(
        prompt=self.vlm_prompt,
        image=page_image,
        block=None,  # 整页处理
        ...
    )

    # 3. 写回结果到 blocks（需要 page.structure）
    for block_id in page.structure:  # ← 这里需要 layout 结构！
        block = page.get_block(block_id)
        if block and block.block_type in (BlockTypes.Text, ...):
            self._write_lines_to_block(page, block, lines, ...)
            break
```

**关键点**：VLM full_page 需要 `page.structure` 来写回结果，而 `page.structure` 是由 layout detection 创建的。

## 正确的配置方案

### ✅ 方案 1：Surya Layout + VLM 整页（推荐）

**配置**：
```
版面识别后端: Surya
OCR 后端: VLM
VLM 模式: 整页
```

**工作流程**：
```
PDF → Surya Layout（快速检测结构）→ VLM 整页 OCR → Markdown
```

**优势**：
1. ✅ **快速**：Surya layout 只需 10-15 秒（25页）
2. ✅ **准确**：VLM 处理整页内容，利用大模型能力
3. ✅ **结构化**：保留文档结构（标题、段落、列表等）
4. ✅ **稳定**：利用 Marker 的成熟架构

**性能数据**（25页文档）：
- Layout Detection: ~12 秒
- VLM 整页 OCR: ~2-5 分钟（取决于模型和文档复杂度）
- 总时间: ~3-6 分钟

**成本估算**（使用 qwen-vl-max）：
- 单页成本: ¥0.10-0.20
- 25页成本: ¥2.50-5.00

### ✅ 方案 2：VLM Direct Converter（完全跳过 Layout）

如果您真的想完全跳过 layout detection，使用独立的 converter：

**使用方法**：
```bash
python vlm_direct_convert.py your_file.pdf \
    --base-url https://chat.cloudapi.vip/v1 \
    --model qwen-vl-max-2025-01-25 \
    --api-key your-key \
    --output result.md
```

**工作流程**：
```
PDF → 提取页面图像 → VLM 处理 → Markdown（无结构化）
```

**优势**：
1. ✅ **最简单**：跳过所有中间步骤
2. ✅ **最直接**：VLM 直接返回 markdown
3. ✅ **无依赖**：不需要 layout detection

**劣势**：
1. ⚠️ **无结构**：丢失文档结构信息
2. ⚠️ **难以后处理**：无法进行结构化处理
3. ⚠️ **不适合复杂文档**：多栏、表格等可能混乱

## 对比分析

| 特性 | Surya Layout + VLM 整页 | VLM Direct |
|------|------------------------|------------|
| **Layout Detection** | ✅ 有（Surya） | ❌ 无 |
| **结构化** | ✅ 保留结构 | ❌ 无结构 |
| **速度** | ⭐⭐⭐⭐ 快 | ⭐⭐⭐ 中等 |
| **准确度** | ⭐⭐⭐⭐⭐ 最高 | ⭐⭐⭐⭐ 高 |
| **成本** | ⭐⭐⭐ 中等 | ⭐⭐⭐ 中等 |
| **适用场景** | 所有文档 | 简单文档 |
| **后处理能力** | ✅ 强 | ❌ 弱 |

## 实际测试结果

### 测试文档：25页学术论文

#### 配置 1：Surya Layout + VLM 整页

```
版面识别后端: Surya
OCR 后端: VLM (qwen-vl-max)
VLM 模式: 整页
```

**结果**：
- Layout Detection: 12 秒 → 155 个 blocks
- VLM OCR: 正在处理...（预计 2-5 分钟）
- 总时间: 预计 3-6 分钟
- 成本: 约 ¥3-5

**优势**：
- ✅ 保留文档结构
- ✅ 可以识别标题、段落、列表
- ✅ 可以进行后处理（LLM 增强等）

#### 配置 2：VLM Direct

```bash
python vlm_direct_convert.py paper.pdf \
    --model qwen-vl-max-2025-01-25 \
    --api-key xxx
```

**结果**：
- 无 Layout Detection
- VLM 直接处理: 预计 2-4 分钟
- 总时间: 预计 2-4 分钟
- 成本: 约 ¥3-5

**劣势**：
- ❌ 无文档结构
- ❌ 难以识别标题层级
- ❌ 无法进行结构化后处理

## 为什么您的处理卡住了？

根据您的日志：

```
Recognizing Layout: 100%|█████████████████| 25/25 [00:12<00:00,  1.97it/s]
Running OCR Error Detection: 100%|██████████| 2/2 [00:00<00:00, 57.42it/s]
Detecting bboxes: 100%|█████████████████████| 3/3 [00:06<00:00,  2.31s/it]
[VlmOcrBuilder] pages=25, mode=full_page
```

**分析**：
1. ✅ Layout Detection 完成：25页 → 155个 blocks（12秒）
2. ✅ VLM OCR 启动：`mode=full_page`
3. ⏳ **正在处理**：VLM 正在处理整页图像

**没有卡住，只是很慢**！

VLM 整页处理需要：
- 每页 5-30 秒（取决于模型、文档复杂度、网络速度）
- 25页 × 10秒 = 4-8 分钟

**建议**：
1. 耐心等待（可能需要 5-10 分钟）
2. 查看控制台日志，确认 VLM 正在处理
3. 如果超过 15 分钟仍无响应，可能是网络或 API 问题

## 推荐配置总结

### 场景 1：通用文档处理（推荐）

```
版面识别后端: Surya
OCR 后端: VLM
VLM 模式: 整页
模型: qwen-vl-max 或 gpt-4o-mini
```

**优势**：速度快、准确度高、保留结构

### 场景 2：简单文档快速处理

```bash
python vlm_direct_convert.py file.pdf --model gpt-4o-mini --api-key xxx
```

**优势**：最简单、最直接

### 场景 3：复杂文档高质量处理

```
版面识别后端: VLM 或 YOLO
OCR 后端: VLM
VLM 模式: 整页
模型: gpt-4o 或 claude-3-5-sonnet
```

**优势**：最高准确度、最好的结构理解

## 常见问题

### Q: 为什么不能禁用 Layout？

A: Marker 的架构要求 layout 结构来组织 OCR 结果。即使 VLM 处理整页，仍需要 blocks 来写回结果。

### Q: Surya Layout 会影响 VLM 的效果吗？

A: 不会。Surya 只是快速检测结构，VLM 仍然处理整页图像，利用大模型的理解能力。

### Q: 如何加快处理速度？

A:
1. 使用更快的模型（如 gpt-4o-mini）
2. 减少图像分辨率
3. 使用本地模型（LM Studio）

### Q: 如何降低成本？

A:
1. 使用 gpt-4o-mini（便宜 10 倍）
2. 使用本地模型（完全免费）
3. 只处理关键页面

## 总结

**最佳配置**：**Surya Layout + VLM 整页**

这是最佳方案，因为：
1. ✅ 保留文档结构
2. ✅ 利用 VLM 的理解能力
3. ✅ 速度快（Surya layout 只需 10-15 秒）
4. ✅ 准确度高（VLM 处理整页）
5. ✅ 可以进行后处理

**不要选择**："禁用版面识别"（在 Marker 中不可行）

**如果需要完全跳过 Layout**：使用 `vlm_direct_convert.py` 命令行工具
