# Changelog

本文件记录 經緯·Contexture 的所有重要变更。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
版本号遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

---

## [0.1.0] - 2025-02-11

### 基于 Marker 的首个独立发布版本

這是 Contexture 作为独立项目的首个版本，基于 Marker 进行了大量人文学科专用功能的开发。

### 新增 (Added)

#### 架构创新
- **OCR 后端可插拔架构**：支持 Surya / Calamari / Chandra / VLM 四种后端
- **Layout 后端可插拔架构**：支持 Surya / YOLO / DocLayout-YOLO / VLM 四种后端
- **三模式处理架构**：传统 Pipeline / VLM 泛化 / VLM 特化
- **异步并发处理架构**：支持大批量文档高效处理

#### 人文学科专用功能
- **双重页码系统**：同时追踪 PDF 页码与印刷页码
- **页码锚点系统**：`<!-- Page X -->` 格式，支持 RAG 精确溯源
- **页码模式识别**：自动检测阿拉伯数字、罗马数字、中文数字页码
- **页码序列修正**：基于模式识别自动修正异常页码
- **边注处理器**：识别并结构化页边注释
- **行内小字注处理器**：处理古籍中的夹注、割注

#### 模板系统
- `modern_publications` - 现代学术出版物
- `chinese_ancient_books` - 中国古籍（竖排、叶记法）
- `german_gothic_print` - 德语哥特体印刷品
- `archive_documents` - 档案文献

#### 工具类
- **API Key 池**：多 Key 并发、Round-robin 负载均衡、失败自动冷却
- **批处理工具**：GPU 内存自适应的批处理参数计算

### 致谢

本项目基于以下开源项目：
- [Marker](https://github.com/VikParuchuri/marker) (GPL-3.0) - Datalab
- [Surya](https://github.com/VikParuchuri/surya) (GPL-3.0) - Datalab
- [Chandra](https://github.com/VikParuchuri/chandra) (Apache-2.0) - Datalab
- [Calamari OCR](https://github.com/Calamari-OCR/calamari) (Apache-2.0)
