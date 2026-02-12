# Chandra-OCR 集成方案对比

## 背景信息

**Chandra-OCR 特点**：
- 本地部署（LM Studio），兼容 OpenAI API
- GPU 加速，50-100 tokens/s
- 专为西方语言手写/模糊文档设计
- Surya 的查漏补缺版本（同一家公司）
- 输出完整 HTML（包含结构、坐标、格式）

**使用场景**：
- ✅ 复杂/老旧文献（SOA 版面识别困难）
- ✅ 手写文档
- ✅ 模糊/低质量扫描件
- ✅ 需要保留丰富格式信息

---

## 方案 1: 轻量级 VLM Direct 模式（推荐）

### 架构

```
Chandra-OCR (整页处理)
    ↓
HTML 输出（包含结构+坐标）
    ↓
HTML Parser (轻量级)
    ↓
Markdown + JSON
```

### 实现方式

**新增文件**：
1. `marker/converters/chandra_direct.py` - Chandra Direct Converter
2. `marker/builders/chandra_html_parser.py` - HTML 解析器

**不需要修改**：
- ❌ 不需要修改现有 VLM Direct 架构
- ❌ 不需要复杂的 Layout Builder
- ❌ 不需要 OCR Builder

### 代码结构

```python
# marker/converters/chandra_direct.py
class ChandraDirectConverter(BaseConverter):
    """
    Chandra Direct Converter

    直接处理整页，输出 Markdown
    """

    def __call__(self, filepath: str) -> Document:
        # 1. 加载 PDF/图片
        pages = self.load_document(filepath)

        # 2. 对每页调用 Chandra OCR
        for page_image in pages:
            html_output = self.chandra_service.process_page(page_image)

            # 3. 解析 HTML → Markdown
            markdown = self.html_parser.parse(html_output)

        return document
```

### 优点

✅ **实现简单**：只需 2 个新文件
✅ **架构清晰**：独立的转换器，不影响现有代码
✅ **性能高**：本地部署，50-100 tokens/s
✅ **适合场景**：复杂文献，SOA 难以处理的情况

### 缺点

⚠️ **不能使用 Processors**：跳过了 Pipeline 的后处理
⚠️ **格式固定**：依赖 Chandra 的输出格式

### 适用场景

- 复杂/老旧文献（版面识别困难）
- 手写文档
- 需要快速处理
- 对格式要求不高

---

## 方案 2: 混合模式（灵活性最高）

### 架构

```
用户选择：
├─ Pipeline 模式
│   ├─ Surya Layout → Surya OCR
│   ├─ Surya Layout → Chandra OCR ← 新增
│   └─ VLM Layout → VLM OCR
└─ Direct 模式
    ├─ VLM Direct (Gemini/Claude)
    └─ Chandra Direct ← 新增
```

### 实现方式

**方案 1 的基础上**，额外添加：
- `marker/services/ocr_chandra.py` - Chandra OCR Service
- `marker/builders/chandra_ocr.py` - Chandra OCR Builder

### 使用场景分配

| 场景 | 推荐模式 | 说明 |
|------|---------|------|
| 复杂老旧文献 | Chandra Direct | 版面识别困难 |
| 手写文档 | Chandra Direct | 专门优化 |
| 现代文档 | Pipeline + Surya | 标准流程 |
| 需要后处理 | Pipeline + Chandra OCR | 使用 Processors |

### 优点

✅ **灵活性最高**：两种模式都支持
✅ **覆盖所有场景**：简单和复杂文档都能处理
✅ **可以使用 Processors**：Pipeline 模式下

### 缺点

⚠️ **实现复杂**：需要 4 个新文件
⚠️ **维护成本高**：两套代码路径

---

## 方案 3: 最简方案（快速验证）

### 架构

```
Chandra-OCR (OpenAI 兼容 API)
    ↓
直接输出 Markdown（不解析 HTML）
    ↓
保存文件
```

### 实现方式

**只需 1 个文件**：
- `marker/converters/chandra_simple.py`

```python
class ChandraSimpleConverter(BaseConverter):
    """最简 Chandra 转换器"""

    def __call__(self, filepath: str) -> str:
        # 1. 加载图片
        pages = self.load_images(filepath)

        # 2. 调用 Chandra API
        markdown_parts = []
        for page_img in pages:
            response = self.call_chandra_api(page_img)
            markdown_parts.append(response['text'])

        # 3. 直接返回 Markdown
        return '\n\n'.join(markdown_parts)
```

### 优点

✅ **极简实现**：1 个文件，<100 行代码
✅ **快速验证**：测试 Chandra 效果
✅ **易于调试**：代码路径简单

### 缺点

⚠️ **功能有限**：不解析 HTML，不保留坐标
⚠️ **不能后处理**：跳过所有 Processors

### 适用场景

- 快速验证 Chandra 效果
- 原型开发
- 简单文档转换

---

## 🎯 推荐方案总结

### 如果你想要...

#### 1️⃣ **快速上手，验证效果** → 方案 3
- 实现时间：1-2 小时
- 代码量：1 个文件，<100 行
- 适合：原型开发，快速测试

#### 2️⃣ **生产使用，架构清晰** → 方案 1
- 实现时间：半天
- 代码量：2 个文件，~300 行
- 适合：复杂文献，独立转换器

#### 3️⃣ **覆盖所有场景，最大灵活性** → 方案 2
- 实现时间：1-2 天
- 代码量：4 个文件，~600 行
- 适合：长期维护，多种文档类型

---

## 📊 方案对比表

| 特性 | 方案 1 | 方案 2 | 方案 3 |
|------|--------|--------|--------|
| 实现复杂度 | 中 | 高 | 低 |
| 代码量 | ~300 行 | ~600 行 | <100 行 |
| 架构清晰度 | ✅ 高 | ⚠️ 中 | ✅ 高 |
| 功能完整度 | ✅ 高 | ✅ 最高 | ⚠️ 低 |
| 维护成本 | ✅ 低 | ⚠️ 高 | ✅ 最低 |
| 使用 Processors | ❌ | ✅ (Pipeline) | ❌ |
| 保留坐标信息 | ✅ | ✅ | ❌ |
| 适合复杂文献 | ✅ | ✅ | ⚠️ |
| 适合快速验证 | ⚠️ | ❌ | ✅ |

---

## 💡 我的建议

基于你的需求（"尽量不要引入更复杂的布局"），我推荐：

### 🥇 首选：方案 1（轻量级 VLM Direct）

**理由**：
1. ✅ 架构简单，不影响现有代码
2. ✅ 适合 Chandra 的使用场景（复杂文献）
3. ✅ 保留坐标和格式信息
4. ✅ 维护成本低

**实现步骤**：
1. 创建 `ChandraDirectConverter`
2. 创建 `ChandraHTMLParser`（解析 HTML → Markdown）
3. 在 Streamlit UI 添加 "Chandra Direct" 选项
4. 测试验证

### 🥈 备选：方案 3（最简方案）

**如果你想先快速验证 Chandra 效果**：
1. 先实现方案 3（1-2 小时）
2. 测试效果
3. 如果满意，再升级到方案 1

---

## 🔧 下一步

请告诉我：
1. **你倾向哪个方案？**（1、2 或 3）
2. **Chandra API 的调用方式**：
   - LM Studio 的 API endpoint
   - 请求格式（如何发送图片）
   - 响应格式（完整的 JSON 结构）
3. **是否需要先实现方案 3 快速验证？**

我会根据你的选择开始实现！
