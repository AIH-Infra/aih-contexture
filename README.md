# 經緯·Contexture

**经纬万卷，结构古今**

AIH-Infra 的第一层：面向人文学科的本地文献结构化工具。Contexture 将 PDF、图片及其他文献材料转化为可校阅、可追溯、可进入知识库的结构化输出，而不把 OCR 仅视为纯文本提取。

当前发行版本：**0.9.0**

## 位置与目标

AIH-Infra 由三层松耦合系统组成：

~~~text
原始文献
  -> 經緯·Contexture：结构化、页码锚点、Middle JSON、Scholarly Markdown
  -> Open WebUI AIH-Infra：知识库、检索、页码级引证与证据导出
  -> AIH-Infra MCP：面向 Agent 的受作用域约束的任务工具
~~~

Contexture 的责任是让材料进入后续系统前仍保留可复核的结构与引用坐标。它不提供知识库问答、公共服务队列、多用户认证或 Agent 编排。

## 核心产物

| 产物 | 用途 |
| --- | --- |
| Middle JSON | 统一机器中间表示，保留块类型、位置、来源与结构信息。 |
| Scholarly Markdown | 人工校阅与交换格式，保留双重页码锚点、脚注和边注语义。 |
| HTML / JSON / Chunk 等派生输出 | 供浏览、调试、评估与下游系统使用。 |

页码锚点分为两类：

~~~markdown
{192}                    # PDF 物理页索引
<!-- Page: 170 -->       # 印刷页码，供学术引用
~~~

印刷页码会进行序列验证；孤立噪声页码不会作为可引用页码输出。

## 处理路线

| 路线 | 适用情况 | 说明 |
| --- | --- | --- |
| Pipeline | 通用、可审计的基础流程 | Layout、OCR 与后处理可以独立选择和组合。 |
| VLM 泛化 | 复杂版式、手稿或需要整页视觉理解 | 使用用户配置的视觉语言模型服务。 |
| VLM 特化 | 已有匹配的专用模型或本地运行时 | 效果依赖模型训练领域，需抽检。 |
| 结构化源导入 | 已有 TEI/XML 或 EPUB 结构化结果 | 导入原始章节树、目录、页表、索引、锚点和元数据。 |
| Markdown 后处理 | 已有结果需要复核、重渲染或修订 | 用于保守地修复页码、结构与格式。 |

所有路线都可生成 Middle JSON，并可渲染为 Scholarly Markdown。编号段落会规范为 201\. 这类非缩进 Markdown 形式；脚注引用和定义使用 <sup>n</sup> 语义。

## 安装与启动

要求：Python **3.10、3.11 或 3.12**，首次安装和首次下载模型时需要网络。

默认 OCR/文档依赖使用 Surya OCR **0.17.1**、Transformers **4.57.6**、pdftext **0.6.3** 和 pypdfium2 **4.30.0**。Python 3.10 使用 NumPy 2.2.x 与 scikit-learn 1.6.x；Python 3.11/3.12 使用 NumPy 2.3+ 与 scikit-learn 1.8+。

### Windows

~~~bat
install.bat
start.bat
~~~

### macOS

双击 **install.command**，完成后双击 **start.command**。

### Linux

~~~bash
chmod +x install.sh start.sh
./install.sh
./start.sh
~~~

安装脚本会创建项目自己的 **.venv**。Pipeline 子进程会自动使用该环境。首次使用 Surya 等本地后端时会下载公开模型权重。

所有安装脚本固定安装 **torch 2.13.0** 与 **torchvision 0.28.0**。Windows 或 Linux 检测到 NVIDIA GPU 时，安装器会要求选择经过验证的 PyTorch profile：CUDA 12.6（推荐）、CUDA 13.0、CUDA 13.2 或明确的 CPU 模式。它会强制替换旧的 torch，并在安装项目依赖后再次验证两个包的版本、实际 CUDA 构建与 GPU 可用性；验证失败会停止，不会静默改装 CPU。

Apple Silicon（包括 M4/M5）使用固定版本的标准 macOS ARM64 PyTorch wheel，并通过 **MPS / Metal GPU** 加速，不使用 CUDA。安装器会验证 PyTorch/torchvision 版本和 MPS 是否实际可用；Intel Mac 则使用 CPU profile。

## 后端与外部运行时

Surya 是主安装环境中的默认本地后端。其他能力是可选项：

| 能力 | 配置或发现方式 |
| --- | --- |
| MinerU | 设置 CONTEXTURE_MINERU_PYTHON、CONTEXTURE_MINERU_COMMAND 或 CONTEXTURE_MINERU_SOURCE_ROOT；也支持 PATH 和约定的同级目录。 |
| Paddle | 设置 CONTEXTURE_PADDLE_PYTHON，或放置在约定的同级 sidecar 环境中。 |
| Tesseract | 自动检查 PATH 与标准系统安装位置。 |
| 云端或本地 VLM | 在 UI 中填写端点、模型与用户自己的凭据。 |
| Chrome ScreenAI | 自动寻找 Chrome 已下载组件或本地 locro 组件；缺失时需先准备组件。 |

检查当前环境：

~~~text
Windows: .venv\Scripts\contexture_doctor
macOS/Linux: .venv/bin/contexture_doctor
~~~

缺失的可选后端不会阻止主流程安装，但被选中时需要其自身的解释器、依赖和模型完整可用。

## 命令行与本地服务

安装后可从项目虚拟环境直接使用单文件、批量、诊断和本地服务入口。Pipeline 支持独立选择 Layout 与 OCR；当两者均设为禁用时，应用走 PDF 文本层快速路径，默认以 **4 个文件子进程**并行处理，允许在 1–16 间调整。

Chrome ScreenAI 默认使用 **4 个 worker** 生成 searchable PDF 后再回流到 Contexture。该能力仍是可选本地后端。

VLM 两种运行模式提供独立 CLI，可连接本机或局域网的 LM Studio：

~~~bash
# 泛化 VLM：LM Studio OpenAI-compatible API
contexture_vlm_generalized input.pdf \
  --base-url http://127.0.0.1:1234/v1 \
  --model your-model \
  --api-key-env CONTEXTURE_VLM_API_KEY

# 特化 VLM：LM Studio native API
contexture_vlm_specialized input.pdf \
  --backend chandra \
  --endpoint http://127.0.0.1:1234 \
  --api-style lmstudio-native \
  --model your-model
~~~

两种 VLM CLI 都支持 `--config-json` 和重复的 `--set KEY=VALUE`，用于透传运行参数；`--dry-run` 会打印脱敏后的最终配置。API Key 建议通过环境变量提供。

### VLM 中断恢复范围

- **VLM 泛化**：按页保存成功结果。重新运行时，仅在源文件、页码范围和有效配置匹配时复用已成功页面；缺失或失败页面仍会处理。
- **VLM 特化**：模型崩溃后可在当前 UI 会话中从失败批次重新开始，已完成批次的文件产物会保留。它不提供逐页 checkpoint，也不提供应用重启后的持久任务恢复。

以上是局部结果复用与批次级 UI 恢复，不是完整、持久的任务队列或任务恢复系统。

## 与 DataLab 上游项目的关系

Contexture 是 AIH-Infra 的独立文献结构化框架，不是 Marker、Surya、Chandra 或 PDFText 的分支，也不拥有这些上游项目的模型与代码产权。

其 Pipeline 的处理器链设计参考了 **Datalab（Endless Labs, Inc.）** 的 Marker；主环境和可选后端根据具体模式接入下列上游能力：

| 上游项目 | 在 Contexture 中的关系 |
| --- | --- |
| Marker | 处理器链与文档转换架构参考，不作为 Contexture 的运行时宿主。 |
| Surya | 默认本地 OCR 与版面检测后端。 |
| Chandra | 可选的特化 VLM OCR 后端。 |
| PDFText | PDF 内嵌文本提取能力。 |

Contexture 在这些引擎之上统一页码锚点、Middle JSON、学术 Markdown、边注与脚注语义，并允许根据文献类型替换后端。上游项目及模型仍适用各自的许可证、模型条款和发布节奏。

## 配置与安全

发行包不包含 API Key、Token、模型缓存、虚拟环境、历史输出或用户配置。应用会在本机创建：

- **configs/api_profiles/**：用户保存的 API Profile；
- **configs/_app_settings.json**：本地 UI 设置；
- **output/**：转换产物；
- **.cache/**：下载的模型缓存。

这些目录不应作为发行包或共享配置的一部分。

## 边界与使用建议

- Contexture 是本地单用户工具，不是多用户 Web 服务。
- 文献处理结果应抽检，尤其是复杂版式、历史字体、手稿与 VLM 输出。
- VLM 结果需要受原始页面、页码锚点与 Middle JSON 的约束和复核。
- 外部模型服务、MinerU、Paddle、Tesseract 与 Chrome ScreenAI 均不随主包强制安装。

发行内容见 [RELEASE_MANIFEST.md](RELEASE_MANIFEST.md)。

## 许可证

本项目按 [GPL-3.0-or-later](LICENSE) 发布，第三方组件归属见 [NOTICE](NOTICE)。ScreenAI 使用的 locro 封装保留 MIT 许可证；Chrome 的 ScreenAI 原生库和模型不随发行包分发。第三方模型权重及外部服务仍受各自许可证和服务条款约束；发行包附带的模型条款见 [MODEL_LICENSE](MODEL_LICENSE)。
