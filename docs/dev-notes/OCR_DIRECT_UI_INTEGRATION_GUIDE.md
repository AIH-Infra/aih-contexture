# OCR Direct Streamlit UI 集成指南

## 📍 修改位置

### 位置 1: 转换模式选择（Line 460）

**当前代码**:
```python
conversion_mode = st.radio(
    "选择转换模式",
    options=["traditional", "vlm_direct"],
    ...
)
```

**修改为**:
```python
conversion_mode = st.radio(
    "选择转换模式",
    options=["traditional", "vlm_direct", "ocr_direct"],
    ...
)
```

### 位置 2: 模式说明（Line 472-489）

添加 OCR Direct 的说明信息。

### 位置 3: OCR Direct 配置界面

在 traditional 模式配置后添加 OCR Direct 配置面板。

### 位置 4: build_config_dict 函数

添加 OCR Direct 配置分支。

---

## 🎯 实施计划

由于文件较大，我将创建一个补丁文件，包含所有需要添加的代码片段。

准备创建补丁文件...
