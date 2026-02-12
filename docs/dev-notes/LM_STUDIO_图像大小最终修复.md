# LM Studio 图像大小最终修复 ✅

## 🎯 问题根源

LM Studio 报错：
```
"Cannot truncate prompt with n_keep (2099474) >= n_ctx (8192)"
```

**核心问题**：
- LM Studio 上下文窗口：**8192 tokens**
- 我们的 base64 图像：**2099474 tokens** (~2MB)
- **图像太大，无法放入上下文窗口**

---

## ✅ 最终修复方案

### 1. 降低图像尺寸到 1024px
```python
# ❌ 之前：1536px
ocr_resize_max = 1536

# ✅ 现在：1024px
ocr_resize_max = 1024
```

### 2. 降低 JPEG 质量到 60
```python
# ❌ 之前：75
ocr_image_quality = 75

# ✅ 现在：60
ocr_image_quality = 60
```

### 3. 强制质量上限为 70
```python
# 即使用户设置更高，也限制在 70
quality = min(self.ocr_image_quality, 70)
```

---

## 📊 预期效果

| 配置 | 之前 | 现在 |
|------|------|------|
| 图像尺寸 | 1536px | 1024px |
| JPEG 质量 | 75 | 60 |
| Base64 大小 | ~2MB | ~100-200KB |
| LM Studio | ❌ 超限 | ✅ 正常 |

---

## 🔧 修改的文件

1. ✅ [marker/converters/ocr_direct_async.py](marker/converters/ocr_direct_async.py)
   - Line 98: `ocr_resize_max = 1024`
   - Line 106: `ocr_image_quality = 60`
   - Line 263: `quality = min(self.ocr_image_quality, 70)`

2. ✅ [marker/scripts/streamlit_app.py](marker/scripts/streamlit_app.py)
   - Line 99: 默认配置 1024px
   - Line 101: 默认质量 60
   - Line 577: UI 默认值 1024px
   - Line 595: UI 默认质量 60

---

## 🚀 重启测试步骤

### 1. 停止 Streamlit
按 `Ctrl+C` 停止当前运行

### 2. 清除浏览器缓存
- 刷新页面（F5）
- 或者清除浏览器缓存

### 3. 重新启动
```bash
streamlit run marker/scripts/streamlit_app.py
```

### 4. 验证配置
在 UI 中检查：
- ✅ 最大图像尺寸：1024
- ✅ 图像格式：JPEG
- ✅ JPEG 质量：60

---

## 📝 预期结果

**LM Studio 日志**：
```
[INFO] Image base64 size: 150.2 KB
[INFO] Running api/v1/chat on history with 1 message
✅ 成功处理
```

**不再出现**：
```
❌ Cannot truncate prompt with n_keep (2099474) >= n_ctx (8192)
```

---

## 💡 如果还是太大

如果 1024px + 质量60 还是太大，可以进一步降低：
- 图像尺寸：768px 或 512px
- JPEG 质量：50

在 UI 中手动调整即可。
