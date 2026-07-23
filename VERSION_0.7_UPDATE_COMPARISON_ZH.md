# AIH-Contexture 0.7.0 更新说明

AIH-Contexture 0.7.0 重点提升学术文献转换的可靠性、OCR/版面后端支持和
本地安装体验。

## 新增内容

- 为 Pipeline、泛化 VLM、特化 VLM 和 Markdown 后处理提供统一运行时。
- 增加 Middle JSON，作为结构化文档数据的统一中间表示。
- 扩展 Scholarly Markdown，支持物理页锚点、印刷页码、脚注、边注和稳定的编号段落。
- 增加 Surya2 VLM 版面分析与 OCR 接入。
- 增加 MinerU OCR/版面 sidecar 与 MinerU-VL 兼容支持。
- 改进 PaddleOCR、PaddleOCR-VL、Tesseract 和 Chrome ScreenAI 接入。
- 增加后端发现、诊断、sidecar 配置和可选外部运行时支持。
- 批处理改为将上传文件和临时结果暂存到磁盘，降低多文件处理时的内存占用。
- 改进 Windows、macOS 和 Linux 的安装与启动脚本。

## 解决和改进的问题

- 印刷页码检测现在会验证页码序列后再生成引用锚点。
- 孤立的页码噪声会被过滤，不再生成误导性的页码引用。
- 学术编号段落会正确转义，不再被 Markdown 错误渲染为列表。
- Pipeline 和 VLM 输出路径中的脚注、上标格式保持更加一致。
- Pipeline 子进程可以自动使用项目虚拟环境，改善本地安装后的后端执行一致性。

## 安装

使用对应平台的 `install` 脚本安装，再运行匹配的 `start` 脚本。可选模型服务和
外部 OCR/版面后端由用户单独配置。
