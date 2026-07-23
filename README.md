# 經緯·Contexture

**经纬万卷，结构古今**

AIH-Infra 的第一层：面向人文学科的本地文献结构化工具。Contexture 将 PDF、图片及其他文献材料转化为可校阅、可追溯、可进入知识库的结构化输出，而不把 OCR 仅视为纯文本提取。

当前发行版本：**0.7.0**

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
| Markdown 后处理 | 已有结果需要复核、重渲染或修订 | 用于保守地修复页码、结构与格式。 |

所有路线都可生成 Middle JSON，并可渲染为 Scholarly Markdown。编号段落会规范为 201\. 这类非缩进 Markdown 形式；脚注引用和定义使用 <sup>n</sup> 语义。

## 安装与启动

要求：Python **3.10、3.11 或 3.12**，首次安装和首次下载模型时需要网络。

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

发行内容和与原版 0.5 的完整对比见：

- **RELEASE_MANIFEST.md**
- **VERSION_0.7_UPDATE_COMPARISON_ZH.md**

在线发布记录见 GitHub 的 [Releases](https://github.com/AIH-Infra/aih-contexture/releases)。

## 许可证

GPL-3.0-or-later。第三方模型、外部服务及其权重分别受其自身许可证和服务条款约束。
