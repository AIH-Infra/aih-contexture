# 专业 OCR 模式命名和架构决策

## 🎯 问题定义

**需要解决的问题**：
1. 如何命名这个新模式？（不能叫 Chandra Direct）
2. 是作为 VLM Direct 的分支，还是独立的并列模式？
3. 如何设计架构以支持未来的类似模型？

---

## 📊 模型分类分析

### 当前系统中的模型类型

| 模型类型 | 代表模型 | 核心能力 | 输出特点 |
|---------|---------|---------|---------|
| **通用 VLM** | Gemini, Claude, GPT-4V | 理解+推理+OCR | 灵活，可定制 prompt |
| **专业 OCR** | Chandra, GOT-OCR, Nougat | Layout+OCR | 结构化，带坐标 |
| **传统 OCR** | Surya OCR, Tesseract | 纯 OCR | 文本+坐标 |
| **Layout 模型** | Surya Layout, YOLO | 版面识别 | 块类型+坐标 |

### 关键区别

**通用 VLM vs 专业 OCR**：

```
通用 VLM (Gemini/Claude):
├─ 能力：理解、推理、对话
├─ 输入：图片 + 自然语言 prompt
├─ 输出：灵活（可以是任何格式）
└─ 用途：需要智能理解的场景

专业 OCR (Chandra/GOT-OCR):
├─ 能力：Layout 识别 + 高精度 OCR
├─ 输入：图片（固定 prompt）
├─ 输出：结构化（Markdown/HTML/JSON + 坐标）
└─ 用途：复杂文档的精确识别
```

**结论**：专业 OCR 和通用 VLM 是**不同类别**的模型。

---

## 🏗️ 架构方案对比

### 方案 A: 作为 VLM Direct 的分支

```
VLM Direct 模式
├─ 通用 VLM
│   ├─ Gemini
│   ├─ Claude
│   └─ Qwen
└─ 专业 OCR ← 新增分支
    ├─ Chandra
    ├─ GOT-OCR
    └─ Nougat
```

**优点**：
- ✅ 减少顶层模式数量
- ✅ 都是"直接处理"模式

**缺点**：
- ❌ 概念混淆（OCR ≠ VLM）
- ❌ 配置界面复杂（两类模型的配置差异大）
- ❌ 用户难以理解分类逻辑

---

### 方案 B: 独立的并列模式

```
转换模式
├─ Pipeline 模式
│   └─ Layout Backend + OCR Backend + Processors
├─ VLM Direct 模式
│   └─ Gemini / Claude / Qwen
└─ OCR Direct 模式 ← 新增独立模式
    └─ Chandra / GOT-OCR / Nougat
```

**优点**：
- ✅ 概念清晰（OCR 就是 OCR）
- ✅ 配置界面简洁（每个模式独立）
- ✅ 易于扩展（添加新 OCR 模型很简单）

**缺点**：
- ⚠️ 顶层模式增加到 3 个

---

### 方案 C: 统一为 "Direct 模式"，内部分类

```
Direct 模式（一步到位）
├─ VLM 类
│   ├─ Gemini
│   ├─ Claude
│   └─ Qwen
└─ OCR 类
    ├─ Chandra
    ├─ GOT-OCR
    └─ Nougat
```

**优点**：
- ✅ 顶层只有 2 个模式（Pipeline / Direct）
- ✅ 内部分类清晰

**缺点**：
- ⚠️ "Direct" 概念过于宽泛
- ⚠️ 配置界面需要二级选择

---

## 🎯 深度决策分析

### 决策维度 1: 用户心智模型

**用户如何理解这些模式？**

| 用户问题 | Pipeline | VLM Direct | OCR Direct |
|---------|---------|-----------|-----------|
| 这是什么？ | 传统流水线 | AI 智能理解 | 专业 OCR |
| 什么时候用？ | 标准文档 | 需要理解 | 复杂/手写 |
| 核心优势？ | 可定制 | 智能 | 精确 |

**结论**：三个独立模式的心智模型最清晰。

---

### 决策维度 2: 配置复杂度

**方案 A（VLM 分支）的配置界面**：
```python
if vlm_direct_mode:
    vlm_type = st.radio("选择类型", ["通用 VLM", "专业 OCR"])

    if vlm_type == "通用 VLM":
        model = st.selectbox("模型", ["Gemini", "Claude", "Qwen"])
        # VLM 特有配置
        prompt_template = st.text_area("Prompt 模板")
        system_message = st.text_area("System Message")

    else:  # 专业 OCR
        model = st.selectbox("模型", ["Chandra", "GOT-OCR"])
        # OCR 特有配置
        output_format = st.selectbox("输出格式", ["JSON", "HTML"])
        # 没有 prompt 配置
```

**问题**：配置项差异大，界面复杂。

**方案 B（独立模式）的配置界面**：
```python
if conversion_mode == "vlm_direct":
    model = st.selectbox("模型", ["Gemini", "Claude", "Qwen"])
    prompt_template = st.text_area("Prompt 模板")
    system_message = st.text_area("System Message")

elif conversion_mode == "ocr_direct":
    model = st.selectbox("模型", ["Chandra", "GOT-OCR"])
    output_format = st.selectbox("输出格式", ["JSON", "HTML"])
```

**结论**：独立模式的配置界面更简洁。

---

### 决策维度 3: 扩展性

**未来可能添加的模型**：

| 模型 | 类型 | 应该放在哪里？ |
|------|------|--------------|
| GOT-OCR 2.0 | 专业 OCR | OCR Direct |
| Nougat | 科学文档 OCR | OCR Direct |
| Donut | 文档理解 | ❓ VLM 还是 OCR？ |
| Pix2Struct | 结构化文档 | ❓ VLM 还是 OCR？ |
| LLaVA | 通用 VLM | VLM Direct |

**问题**：有些模型介于 VLM 和 OCR 之间，难以分类。

**解决方案**：
- 如果是独立模式，可以根据主要用途分类
- 如果是 VLM 分支，分类会更混乱

**结论**：独立模式的分类更灵活。

---

### 决策维度 4: 代码架构

**方案 A（VLM 分支）**：
```python
# marker/converters/vlm_direct.py
class VLMDirectConverter:
    def __init__(self, config):
        if config.vlm_type == "general":
            self.service = GeneralVLMService(config)
        else:
            self.service = SpecializedOCRService(config)
```

**问题**：一个 Converter 处理两类模型，代码复杂。

**方案 B（独立模式）**：
```python
# marker/converters/vlm_direct.py
class VLMDirectConverter:
    def __init__(self, config):
        self.service = VLMService(config)

# marker/converters/ocr_direct.py
class OCRDirectConverter:
    def __init__(self, config):
        self.service = OCRService(config)
```

**结论**：独立模式的代码更清晰。

---

## 🏆 最终推荐方案

### 方案 B: 独立的 OCR Direct 模式

**命名建议**：

| 中文名称 | 英文名称 | 说明 |
|---------|---------|------|
| **专业 OCR 模式** | **OCR Direct** | 简洁，准确 |
| 文档 OCR 模式 | Document OCR | 强调文档 |
| 智能 OCR 模式 | Smart OCR | 强调智能 |
| 结构化 OCR 模式 | Structured OCR | 强调结构 |

**推荐**：**OCR Direct**（专业 OCR 模式）

---

## 📐 最终架构

```
┌─────────────────────────────────────────────────────┐
│ Marker 转换模式                                      │
├─────────────────────────────────────────────────────┤
│                                                     │
│ 1. 🔄 Pipeline 模式（传统流水线）                    │
│    ├─ Layout Backend: Surya / VLM / YOLO          │
│    ├─ OCR Backend: Surya / VLM / Calamari         │
│    └─ Processors: 可定制后处理                      │
│                                                     │
│ 2. 🤖 VLM Direct 模式（视觉语言模型）                │
│    ├─ Gemini                                       │
│    ├─ Claude                                       │
│    ├─ Qwen                                         │
│    └─ 特点：智能理解，灵活 prompt                   │
│                                                     │
│ 3. 📚 OCR Direct 模式（专业 OCR）← 新增              │
│    ├─ Chandra                                      │
│    ├─ GOT-OCR（未来）                              │
│    ├─ Nougat（未来）                               │
│    └─ 特点：Layout-aware，高精度，结构化输出        │
│                                                     │
└─────────────────────────────────────────────────────┘
```

---

