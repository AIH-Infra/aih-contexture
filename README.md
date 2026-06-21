# 經緯·Contexture

**经纬万卷，结构古今 · Weaving Data from History**

> 面向人文学科的文献结构化基础设施：把 PDF、图像和已有 Markdown 转换为可追溯、可校阅、可进入知识库的学术材料。

[![License: GPL v3](https://img.shields.io/badge/License-GPLv3-blue.svg)](https://www.gnu.org/licenses/gpl-3.0)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

---

## 项目定位

**經緯·Contexture** 是 [AIH-Infra（人文学科人工智能基础设施）](https://github.com/AIH-Infra) 的材料线基座。

普通文档解析工具通常回答的是：

> 如何更准确地把文档转换为文本？

Contexture 关注的是另一个问题：

> 如何让数字化文献重新具备学术引用、证据追溯和人工校阅的条件？

在人文学科中，文本不是孤立字符串。它总是依附于版本、页码、版式、脚注、边注、行内注、图表、手写批注和引用传统。Contexture 的目标不是替代所有底层 OCR 或 VLM 模型，而是在这些模型之上提供一层面向学术规范的结构化框架。

核心输出链路：

```text
PDF / Image / Markdown
  -> Pipeline / VLM / Postprocess
  -> Middle JSON
  -> Scholarly Markdown / HTML / JSON / Chunks
  -> RAG / 知识库 / 证据导出
```

---

## 与 Datalab Marker 的关系

Contexture 的早期 pipeline 模式以 [Datalab Marker](https://github.com/VikParuchuri/marker) 为重要学习参照和 GPL-3.0 继承基座。项目保留了早期 git 历史，因此 GitHub contributors 中会包含 Marker 原始历史中的参与者；这是对开源来源和贡献历史的保留，而不是将这些贡献者声明为当前 AIH-Infra 架构设计的作者。

更准确地说：

- **历史上**：Contexture 的 0.1 阶段从 Marker 的 PDF -> Markdown pipeline、处理器链和 Surya 生态中学习并继承了基础形态。
- **法律与开源合规上**：本项目继续使用 GPL-3.0-or-later，并在 `NOTICE` 中保留 Datalab / Marker / Surya / PDFText 等来源声明。
- **在架构上**：Contexture 一开始便不是 Marker 的简单封装或改名版本，而是围绕人文学科可追溯性重构出的独立框架。

相对于最初的 pipeline 基座，当前版本已经形成了几项关键扩展：

- Pipeline 模式完成后端解耦，Layout、OCR、VLM 能力可通过 registry/catalog 诊断和配置。
- 新增 **VLM 泛化模式**，支持通过 OpenAI-compatible、Gemini、Claude 等服务进行整页理解。
- 新增 **VLM 特化模式**，支持 Chandra、Churro、PaddleOCR-VL、MinerU-VL 等专用文档模型路径。
- 新增 **Middle JSON** 作为跨后端、跨模式的事实层。
- 新增 **Scholarly Markdown**，面向人工校阅和学术引用。
- 新增双重页码锚点、边注、行内注、古典引用系统等人文学科专用处理能力。

因此，Contexture 对 Marker 的关系可以概括为：

> Marker 是早期 pipeline 的重要开源基座与学习来源；Contexture 是在保留来源承认和 GPL 继承的前提下，面向人文学术可追溯性发展出的独立项目。

---

## 核心能力

### 1. 双重页码锚点

Contexture 将页码视为学术证据链的一部分，而不是排版噪声。

```markdown
{192}

---
<!-- Page: 170 -->

正文内容……
```

- `{192}`：PDF 机器页码，用于程序定位原始物理页。
- `<!-- Page: 170 -->`：印刷页码，用于人类引用书籍实际页码。

这使下游 RAG、知识库和证据导出能够从回答追溯回原始文献页。

### 2. Middle JSON 事实层

Middle JSON 是 Contexture 的中间表示和系统契约。它把不同来源的文档解析结果统一为页面、块、span、bbox、provenance、printed page 等结构。

当前支持的典型块类型包括：

- 基础文本：`Text`, `SectionHeader`, `ListItem`, `Code`
- 页面结构：`PageHeader`, `PageFooter`, `PageNumber`
- 学术注释：`Footnote`, `MarginalNote`, `InlineAnnotation`, `Reference`
- 视觉元素：`Figure`, `Picture`, `ImageDescription`, `Caption`
- 结构化内容：`Table`, `Equation`, `Form`, `TableOfContents`
- 特殊区域：`Handwriting`, `ComplexRegion`

### 3. 多模式转换架构

| 模式 | 核心思路 | 适合场景 |
|------|----------|----------|
| Pipeline | Layout -> OCR -> Processor -> Renderer | 结构清晰、需要可审计流程的 PDF/图片 |
| VLM 泛化 | 整页图像交给通用视觉语言模型理解 | 复杂版面、混合内容、无需本地 GPU 的场景 |
| VLM 特化 | 使用专用文档 VLM 或 OCR-VL 模型 | 历史文献、复杂结构、特定模型擅长的文档类型 |
| Markdown 后处理 | 修复已有 Markdown 或 Middle JSON | 已有转换结果，只需页码、结构或格式修复 |

### 4. 可替换后端

Contexture 不把自己绑定到某一个底层模型。Layout、OCR、VLM 后端由能力目录、registry 和诊断机制管理。

| 类别 | 当前/可选后端示例 |
|------|-------------------|
| Layout | Surya, VLM Layout, External Layout Sidecar, MinerU, PaddleOCR Layout |
| OCR | Surya, VLM OCR, Calamari, PaddleOCR, PaddleOCR-VL, Tesseract |
| VLM | OpenAI-compatible, Gemini, Claude, Chandra, Churro, PaddleOCR-VL, MinerU-VL |

### 5. 人文学科专用结构

Contexture 提供或规划了面向人文学科材料的结构识别：

- 印刷页码、罗马数字页码、中文叶码
- 脚注、边注、行内小字注
- Stephanus / Bekker 等古典研究引用系统
- 版心叶码、书耳、眉批等古籍版式元素
- 面向 RAG 的 chunk 输出与页码元数据

部分边注、行内注和古典引用识别仍属于实验性能力，效果依赖底层模型和文档质量。

---

## 快速开始

### 环境要求

- Python 3.10+
- Windows / macOS / Linux
- Pipeline 本地模型推荐 CUDA GPU；VLM 泛化模式可只使用 API key
- 推荐内存 16 GB+

### 一键安装

Windows：

```powershell
.\install.bat
```

macOS / Linux：

```bash
chmod +x install.sh start.sh
./install.sh
```

macOS 也可以使用：

```bash
chmod +x install.command start.command
./install.command
```

### pip 安装

```bash
pip install aih-contexture
```

如需 DOCX / XLSX / PPTX / EPUB / HTML 等扩展格式支持：

```bash
pip install "aih-contexture[full]"
```

### 启动 GUI

```bash
contexture_gui
```

或在源码目录中运行：

```bash
python contexture_app.py
```

### 启动 API 服务

```bash
contexture_server
```

### 单文件转换

```bash
contexture_single input.pdf --output_dir output
```

### 后端诊断

```bash
contexture_doctor
contexture_backends
```

---

## 常用入口

| 命令 | 功能 |
|------|------|
| `contexture_gui` | 启动 Streamlit Web GUI |
| `contexture_server` | 启动 FastAPI 本地 API |
| `contexture` | 批量转换 |
| `contexture_single` | 单文件转换 |
| `contexture_chunk` | RAG chunk 输出 |
| `contexture_middle` | Middle JSON 操作 |
| `contexture_backends` | 查看后端能力目录 |
| `contexture_doctor` | 检查后端可用性 |
| `contexture_eval_layout` | Layout 质量评估 |
| `contexture_eval_markdown` | Scholarly Markdown 质量评估 |

---

## API 概览

本地服务提供统一转换入口：

| Endpoint | 方法 | 功能 |
|----------|------|------|
| `/` | GET | 服务首页 |
| `/marker` | POST | 兼容型 pipeline 转换入口 |
| `/marker/upload` | POST | 兼容型上传转换入口 |
| `/v1/convert` | POST | Runtime 统一转换入口 |
| `/v1/backends` | GET | 后端能力目录与诊断 |

推荐新集成优先使用 `/v1/convert`，因为它覆盖 pipeline、VLM 泛化、VLM 特化和 Markdown 后处理四种模式。

---

## 项目结构

```text
aih_contexture/
  runtime/       # ContextureJob, ContextureResult, run_job, artifacts, model lifecycle
  middle/        # Middle JSON schema, adapters, validation, scholarly markdown
  backends/      # Backend catalog, capabilities, diagnostics, registries
  converters/    # Pipeline, VLM generalized, VLM specialized, OCR direct
  builders/      # Document/Layout/OCR/Line/Structure builders
  processors/    # 页码、脚注、边注、表格、公式、LLM processors
  postprocess/   # Markdown 后处理、页码修复、可选 LLM 审阅
  renderers/     # Markdown, HTML, JSON, chunks, OCR JSON
  services/      # OpenAI, Claude, Gemini, Ollama, LM Studio, OCR services
  prompts/       # Prompt presets and builders
  evaluation/    # Layout / Markdown quality evaluation
  scripts/       # CLI, server, Streamlit GUI helpers
```

更完整的架构说明见 [ARCHITECTURE_AND_TECHNICAL_GUIDE.md](ARCHITECTURE_AND_TECHNICAL_GUIDE.md)。

---

## 适用场景

Contexture 适合：

- 人文学科书籍、论文、档案、扫描件的结构化
- 需要保留 PDF 页码和印刷页码的数字化工作流
- 面向 RAG / 知识库的可追溯材料预处理
- 对 OCR / VLM 输出进行人工校阅前的结构化整理
- 需要比较多种 Layout / OCR / VLM 后端效果的实验流程

Contexture 不适合：

- 只需要一次性纯文本抽取、且不关心页码追溯的轻量任务
- 要求成熟多人协作平台、权限系统和在线标注工作台的机构级 SaaS 场景
- 对某一类手写体要求稳定高精度识别、但没有配套模型或训练数据的任务

---

## 版本边界

当前版本：`0.5.0`

已经稳定形成的主线：

- Runtime 统一任务入口
- Pipeline / VLM 泛化 / VLM 特化 / Markdown 后处理四种模式
- Middle JSON 中间表示
- Scholarly Markdown 输出
- 后端能力目录与诊断
- Streamlit GUI、FastAPI API、CLI 入口

仍在演进中的方向：

- Office 文档直接转换
- 服务版多用户任务队列
- 更细粒度 checkpoint
- 人文学科专用 Layout 后端
- 更大规模的边注、行内注和古典引用系统验证

---

## 致谢

Contexture 的形成离不开文档解析和 OCR/VLM 开源生态。特别感谢：

**Datalab / Endless Labs, Inc.**

- [Marker](https://github.com/VikParuchuri/marker) (GPL-3.0-or-later)：早期 pipeline 基座、处理器链与 PDF -> Markdown 工作流的重要来源。
- [Surya](https://github.com/VikParuchuri/surya) (GPL-3.0)：OCR 与 Layout 引擎。
- [PDFText](https://github.com/VikParuchuri/pdftext) (Apache-2.0)：PDF 文本层提取。
- [Chandra](https://github.com/VikParuchuri/chandra) (Apache-2.0)：专用文档 OCR/VLM 路径的重要生态项目。

**其他生态项目**

- MinerU / PaddleOCR：Layout、OCR-VL 和结构化文档解析生态的重要参考与可选后端来源。
- Calamari OCR：欧洲历史字体 OCR 生态。
- Tesseract：传统 OCR 生态。

项目保留早期 git 历史，以便完整呈现来源、许可证继承和贡献脉络。当前架构、AIH-Infra 集成、人文学科页码锚点体系、Middle JSON、VLM 双模式和 Scholarly Markdown 输出由 AIH-Infra 在后续版本中持续开发。

---

## 许可证

本项目基于 **GNU General Public License v3.0-or-later** 发布。

由于项目历史上继承并使用 GPL-3.0-or-later 生态组件，Contexture 继续采用 GPL-3.0-or-later。第三方组件和来源说明见 [NOTICE](NOTICE)。

---

## 关于 AIH-Infra

**AIH-Infra（人文学科人工智能基础设施）** 致力于为人文学科研究者提供可追溯、可验证、可传承的 AI 工具链。

- **材料线**：Contexture，负责文献数字化与结构化。
- **系统线**：RAG / Graph RAG / Agent RAG 知识基础设施。
- **应用线**：面向具体学科问题的研究工具。

我们相信：**技术应当服务于学术规范，而不是消解学术规范。**

---

## 作者

**Güriedrich & Baireinhold**  
橘里德里希 & 白茵霍尔德

---

## 链接

- GitHub: https://github.com/AIH-Infra/aih-contexture
- Issues: https://github.com/AIH-Infra/aih-contexture/issues
