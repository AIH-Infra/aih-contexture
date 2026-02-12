# 缓存问题诊断报告

## 问题描述
同一个文件更换后端重新运行时，会立刻输出上一轮生成的结果。

## 已检查的缓存点

### 1. ✅ Streamlit 缓存
- `@st.cache_resource` 用于 `get_artifacts()` - 仅缓存模型，不影响处理结果
- `@st.cache_data` 用于 `get_page_image()` 和 `page_count()` - 仅用于UI显示

### 2. ✅ 文件命名
- 已实现时间戳命名，每次运行生成唯一文件名
- 格式: `{文件名}_{时间戳}.md`

### 3. ✅ Session State
- `st.session_state.processed_files` 仅用于记录，不用于跳过处理

### 4. ✅ Builders 和 Providers
- 未发现缓存机制

## 可能的原因

### 原因 1: Streamlit 文件上传缓存
**症状**: 当重新上传同名文件时，Streamlit 可能使用缓存的文件对象

**验证方法**:
1. 在处理前添加日志，打印文件的哈希值
2. 检查是否每次都是新的文件对象

**位置**: `streamlit_app.py` line 925-934

### 原因 2: 浏览器缓存
**症状**: 浏览器缓存了下载的文件，显示的是旧版本

**验证方法**:
1. 检查输出文件的实际内容和修改时间
2. 强制刷新浏览器 (Ctrl+F5)

### 原因 3: 模型内部缓存
**症状**: 某些模型可能基于输入图像哈希缓存结果

**验证方法**:
1. 在 `build_document()` 前后添加日志
2. 检查处理时间是否异常短

### 原因 4: 输出文件读取而非生成
**症状**: 代码可能在某处读取已存在的输出文件

**验证方法**:
1. 删除输出目录中的所有文件
2. 重新运行，看是否还会"立刻输出"

## 建议的调试步骤

### 步骤 1: 添加详细日志
在 `streamlit_app.py` 的处理循环中添加日志：

```python
# 在 line 1101 之前添加
import hashlib
file_hash = hashlib.md5(open(file_path, 'rb').read()).hexdigest()
st.write(f"🔍 文件哈希: {file_hash[:8]}")
st.write(f"🔍 OCR后端: {ocr_backend}")
st.write(f"🔍 Layout后端: {layout_backend}")
st.write(f"🔍 输出文件名: {fname_base}")

# 在 line 1102 之后添加
import time
start_time = time.time()
st.write(f"⏱️ 开始处理...")

# 在 line 1134 之后添加
elapsed = time.time() - start_time
st.write(f"⏱️ 处理耗时: {elapsed:.2f}秒")
```

### 步骤 2: 检查输出文件
```python
# 在写入文件后添加
import os
st.write(f"📝 文件已写入: {main_path}")
st.write(f"📝 文件大小: {os.path.getsize(main_path)} bytes")
st.write(f"📝 修改时间: {datetime.fromtimestamp(os.path.getmtime(main_path))}")
```

### 步骤 3: 清空输出目录测试
```bash
# 删除所有输出文件
rm -rf output/*
```

然后重新运行，观察是否还会"立刻输出"。

## 最可能的原因

基于代码分析，我认为最可能的原因是：

**浏览器或 Streamlit UI 缓存**

当你点击下载按钮或查看结果时，浏览器可能缓存了文件内容。即使后端生成了新文件，浏览器显示的仍是缓存版本。

**解决方案**:
1. 在文件名中添加更精确的时间戳（包含毫秒）
2. 强制浏览器不缓存下载文件
3. 每次处理后清空 session state

## 需要用户提供的信息

1. "立刻输出"是指：
   - [ ] 处理时间异常短（几秒内完成）
   - [ ] UI 立即显示结果（无处理过程）
   - [ ] 下载的文件内容是旧的

2. 使用的模式：
   - [ ] 上传文件模式
   - [ ] 选择文件夹模式

3. 输出文件：
   - [ ] 检查输出目录，是否有多个时间戳文件
   - [ ] 最新文件的内容是否正确

4. 后端切换：
   - 从 _____ 切换到 _____
   - 预期看到不同的结果，但看到的是 _____ 的结果
