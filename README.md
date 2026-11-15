# 經緯·Contexture

**经纬万卷，结构古今**

AIH-Infra 的第一层：面向人文学科的本地文献结构化工具。Contexture 将 PDF、图片及其他文献材料转化为可校阅、可追溯、可进入知识库的结构化输出，而不把 OCR 仅视为纯文本提取。

当前发行版本：**1.1.1**

发行变化见 [CHANGELOG.md](CHANGELOG.md)。

## 位置与目标

AIH-Infra 由三层松耦合系统组成：

~~~text
原始文献
  -> 經緯·Contexture：结构化、页码锚点、Middle JSON、Scholarly Markdown
  -> Open WebUI AIH-Infra：知识库、检索、页码级引证与证据导出
  -> AIH-Infra MCP：面向 Agent 的受作用域约束的任务工具
~~~

Contexture 的责任是让材料进入后续系统前仍保留可复核的结构与引用坐标。主程序是本地单用户工具；另附可选的局域网网关，提供认证后的任务队列和原生工作节点，不会随主程序自动启动。部署说明见 [deploy/cluster/README.md](deploy/cluster/README.md)。

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
| 结构化源导入 | 导入已有 Markdown、HTML、EPUB、TEI/XML 或结构数据 | 将外部结果转换为 Contexture 的中间表示和输出格式。 |
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

在项目目录执行一次 `chmod +x install.command start.command`，然后双击 **install.command**；安装完成后双击 **start.command**。

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

Surya 0.17.1 是主安装环境中的默认本地后端，使用 Transformers 4.57.6。其他能力是可选项：

Pipeline 的 **Paddle OCR Torch** 已内置检测、识别和前后处理代码，与主环境共用 PyTorch，不需要完整 MinerU 或 PaddlePaddle。以下命令在现有项目环境中按需安装，不创建额外虚拟环境，也不会下载模型权重：

```bash
python -m pip install ".[paddle-torch]"
python -m pip install ".[paddle-layout]"
python -m pip install ".[indra]"
```

只需其中一项时只执行对应命令。Paddle OCR Torch 默认选择 PP-OCRv5，可显式选择 PP-OCRv6；两者已在同一 Torch 环境完成 CPU/CUDA 运行验证，运行通过不等于全语种质量等价。通过 `mineru_ocr_model_dir` 指定权重目录，留空复用已有缓存。只有明确启用 `mineru_ocr_allow_download` 时才允许下载缺失权重；v6 使用固定版本的官方 safetensors。CLI 保留 `--ocr_backend mineru_pytorch_paddle_ocr` 标识，默认使用运行 Contexture 的 Python。原 `paddle_ocr_v5` PaddlePaddle 后端保留给旧 API/CLI 配置和对照验收，新界面统一使用 Paddle OCR Torch。

PP-DocLayoutV3 默认使用项目内置的 CPU ONNX 推理与后处理，共用同一环境中的可选 ONNX Runtime；不依赖 Paddle/PaddleX。模型目录通过 `paddle_layout_model_dir` 或 `CONTEXTURE_DOCLAYOUT_V3_MODEL_DIR` 指定，目录中应有 `inference.onnx`、`inference.yml`。首次下载需明确启用 `paddle_layout_allow_download`。默认批次 1，支持 1–8；原生多边形保存在原始元数据中，Pipeline 几何使用四边形。显式的 Paddle SDK 引擎/解释器配置仍保留兼容路径，不会自动忽略 GPU 请求或切换到 CPU。Indra 同样使用可选 CPU ONNX Runtime。GLM-OCR 的 API 与 Calamari 的 HTTP 接口保持原有方式。

| 能力 | 配置或发现方式 |
| --- | --- |
| Paddle OCR Torch | 在主环境安装 `.[paddle-torch]`；模型目录可通过 UI、CLI 或 `CONTEXTURE_PADDLE_TORCH_MODEL_DIR` 指定，默认复用已有缓存。 |
| PP-DocLayoutV3 | 在主环境安装 `.[paddle-layout]`；默认内置 CPU ONNX 路径，模型目录和下载许可可在 UI/CLI/API 指定。 |
| MinerU CLI 兼容路径 | 设置 CONTEXTURE_MINERU_PYTHON、CONTEXTURE_MINERU_COMMAND 或 CONTEXTURE_MINERU_SOURCE_ROOT；仅完整 CLI 路径需要外部 MinerU。 |
| Paddle 原生 SDK 路径 | 设置 CONTEXTURE_PADDLE_PYTHON，或放置在约定的同级 sidecar 环境中；用于现有 Paddle 版面后端和旧 OCR 配置。 |
| Tesseract | 自动检查 PATH 与标准系统安装位置。 |
| 云端或本地 VLM | 在 UI 中填写端点、模型与用户自己的凭据。 |
| Chrome ScreenAI | 自动寻找 Chrome 已下载组件或本地 locro 组件；缺失时需先准备组件。 |
| Indra | 在主环境安装 `.[indra]`，设置 `INDRA_OCR_MODEL_DIR` 或 UI/CLI 模型目录。仍可显式指定其他 Python。权重不随主包分发。 |

ScreenAI 的 PDF 预处理可选择按原页识别、清理隐藏文字层、栅格化或先清理再栅格化。默认会在识别前清理批注、标记、印章和链接，并保留正文与表单可见值；重建页面背景时可调整 DPI。ScreenAI 需要用户自行准备的 Chrome 组件，不包含在发行包中。

检查当前环境：

~~~text
Windows: .venv\Scripts\contexture_doctor
macOS/Linux: .venv/bin/contexture_doctor
~~~

缺失的可选后端不会阻止主流程安装；被选中时需要相应依赖和模型完整可用。内置 Torch/CPU 组件复用主环境，服务型后端需要配置已部署的接口。

Indra 的版面与 OCR 可以分别选择。两项同时选择 Indra 且未禁用 OCR 时，UI 和 CLI 都使用 CPU 原生直连，只接受 PDF 输入及 Markdown/JSON 输出。UI 选定的页面范围会合并为一个 Indra 任务，内部并行由 CPU 核心数设置控制；该路径不走 Pipeline 的跨文件短文件队列。只选择 Indra 版面时可搭配 PDF 文字层或 ScreenAI；只选择 Indra OCR 时走普通 Pipeline。

诊断独立 Indra 环境可使用 `contexture_doctor --indra-python <python路径> --indra-model-dir <模型目录>`。该检查确认配置路径及必需文件存在，真实导入与识别仍需转换测试。逐页磁盘缓存绑定本地模型文件内容；替换同目录模型后不会继续使用原有结果。未显式指定模型目录时只在当前运行时内缓存，不保存磁盘缓存。

## 命令行与本地服务

安装后可从项目虚拟环境直接使用单文件、批量、诊断和本地服务入口。Pipeline 支持独立选择 Layout 与 OCR，并以“每批页数”规划文档处理：页数不超过该值的文件整份处理，较长文件按该页数拆分。UI 默认每批 100 页；CLI 自动模式可按资源规划调整批次页数。连续短文件由资源规划器决定并行度，使用常驻进程在文件间复用模型；长文件按页面批次调度，避免文件并行与批次并行叠加。

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

- **VLM 泛化**：按页追加成功结果到输出目录中的检查点，并核对源文件、页码范围、模型、服务端点和有效配置。重新运行时只复用身份匹配且成功的页面；缺失或失败页面仍需处理。这是页面级复用，不是服务队列或完整任务编排。
- **VLM 特化**：模型崩溃后可从失败批次重新开始，已完成批次保存的文件会保留。恢复状态属于当前 UI 会话，没有泛化模式那样的逐页检查点，也不提供应用重启后的持久任务恢复。

## 批量上传与下载

Web UI 最多同时上传四个文件，各文件以 256 KiB 分块暂存到系统临时目录，队列保存路径与文件信息。整批上传完成后可开始任务。任务收尾删除成功输入，失败和暂停输入保留重试；可通过“清理上传缓存”释放暂存文件。异常退出遗留的缓存按三天保留期在后续创建上传会话时清扫。ZIP 和诊断文件按下载请求流式读取。

`CONTEXTURE_UPLOAD_ROOT` 可指定暂存目录。上传与下载共用一个独立 HTTP 传输端口，默认由系统分配，可通过 `CONTEXTURE_TRANSFER_PORT` 固定。局域网访问需放行该传输端口。

## 与 DataLab 上游项目的关系

Contexture 是基于 Marker 演化的文献结构化框架，主程序独立运行，并按所选后端调用 Surya、Chandra、PDFText 等上游组件。第三方代码与模型的权利归各自权利人所有。

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

- 主 Web UI 面向本地单用户使用，不是默认启用的公网多用户服务。可选局域网网关提供 Bearer 认证、持久化任务队列和工作节点；部署前应设置私有配置并限制网络访问，详见 [部署说明](deploy/cluster/README.md)。
- 文献处理结果应抽检，尤其是复杂版式、历史字体、手稿与 VLM 输出。
- VLM 结果需要受原始页面、页码锚点与 Middle JSON 的约束和复核。
- 外部模型服务、MinerU、Paddle、Tesseract 与 Chrome ScreenAI 均不随主包强制安装。

发行内容见 [RELEASE_MANIFEST.md](RELEASE_MANIFEST.md)。

## 许可证

本项目按 [GPL-3.0-or-later](LICENSE) 发布，第三方代码和模型的来源与许可见 [NOTICE](NOTICE)。Indra 权重采用修改版 OpenRAIL-M 条款，见 [MODEL_LICENSE](MODEL_LICENSE)；权重不随发行包分发。Chrome ScreenAI 的 DLL 和模型属于 Google 专有组件，也不随包分发。其他第三方权重及外部服务仍受各自许可证和服务条款约束。
