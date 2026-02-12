# VLM Direct UI 快速参考

## 🚀 3 步开始

### 1. 选择模式
```
⚙️ 转换模式 → 🚀 VLM Direct 模式
```

### 2. 配置 API
```
Base URL: https://api.openai.com/v1
模型: gpt-4o-mini
API Key: sk-your-key
并发数: 5
```

### 3. 转换
```
上传 PDF → 🚀 开始转换 → 下载结果
```

## ⚡ 性能

| 文档大小 | 传统模式 | VLM Direct | 提速 |
|---------|---------|-----------|------|
| 25页 | 3-6 分钟 | **1-2 分钟** | **5倍** |
| 100页 | 12-24 分钟 | **2-3 分钟** | **10倍** |

## 🎛️ 推荐配置

### OpenAI（推荐）
```
Base URL: https://api.openai.com/v1
模型: gpt-4o-mini
并发数: 5
成本: $0.002/页
```

### 通义千问（国内）
```
Base URL: https://dashscope.aliyuncs.com/compatible-mode/v1
模型: qwen-vl-max
并发数: 5
成本: ¥0.10/页
```

### LM Studio（免费）
```
Base URL: http://localhost:1234/v1
模型: llava-v1.6-34b
并发数: 1
成本: $0
```

## 💡 并发数选择

| API | 推荐并发 |
|-----|---------|
| OpenAI 付费 | 5-10 |
| OpenAI 免费 | 2-3 |
| 通义千问 | 5-10 |
| Claude | 3-5 |
| 本地模型 | 1-2 |

## 🔧 常见问题

### Rate Limit?
→ 降低并发数（5 → 2）

### 超时?
→ 增加超时时间（180 → 300）

### 内存不足?
→ 降低图像分辨率（2048 → 1536）

## ✅ 优势

- ✅ 最快（提速 5-10 倍）
- ✅ 最简单（只需 API）
- ✅ 最准确（VLM 理解）
- ✅ 最灵活（支持所有 API）

## 📝 完整文档

详见：[STREAMLIT_VLM_DIRECT_GUIDE.md](STREAMLIT_VLM_DIRECT_GUIDE.md)
