# 问题解决说明

## 问题1: 重复输出 ✅ 已解决

### 问题描述
启动streamlit应用时出现重复的调试输出:
```
marker.__file__ = None
marker.converters.pdf.__file__ = D:\marker_cuda\marker\converters\pdf.py
```

### 原因
[marker/scripts/streamlit_app.py](marker/scripts/streamlit_app.py) 第29-30行有调试print语句,streamlit会多次重新运行脚本导致重复输出。

### 解决方案
已注释掉这些调试语句:
```python
# 调试输出已注释 - 避免重复打印
# print("marker.__file__ =", marker.__file__)
# print("marker.converters.pdf.__file__ =", marker.converters.pdf.__file__)
```

---

## 问题2: 配置项看不到 ℹ️ 说明

### 问题描述
配置面板中的"分批处理"、"页码范围"、"批次冷却"等配置看不到了。

### 原因
这些配置项在**Pipeline模式(传统模式)**中,而不在**VLM Direct模式**中。

### 配置面板结构

```
侧边栏配置面板
├── 转换模式选择
│   ├── VLM Direct (纯VLM模式)
│   └── Pipeline (传统模式)
│
├── if conversion_mode == "vlm_direct":
│   ├── VLM Direct 配置
│   │   ├── API 配置
│   │   ├── 并发配置
│   │   ├── 图像配置
│   │   └── API 调用配置
│   └── (无处理设置)
│
└── else: (Pipeline模式)
    ├── 版面识别后端
    ├── OCR 后端
    ├── LLM 增强
    └── ⚡ 处理设置 ← 这里!
        ├── 批处理模式 (自动/单批/分批)
        ├── 分批阈值
        ├── 每批页数
        ├── 批次间冷却
        └── 指定页码范围
```

### 解决方案

**要看到这些配置,请选择"Pipeline (传统模式)":**

1. 打开streamlit应用
2. 在侧边栏顶部找到"转换模式"
3. 选择 **"Pipeline (传统模式)"**
4. 向下滚动,会看到"⚡ 处理设置"部分
5. 在这里可以配置:
   - 批处理模式
   - 分批阈值
   - 批次间冷却
   - 页码范围

### 为什么VLM Direct模式没有这些配置?

**VLM Direct模式的特点:**
- 直接调用VLM API处理每一页
- 使用异步并发处理(通过`vlm_direct_max_concurrent`控制)
- 不需要分批处理(VLM API自己处理并发)
- 页码范围可以在VLM Direct模式中添加(目前未实现)

**Pipeline模式的特点:**
- 多阶段处理(Layout → OCR → 结构化)
- 需要加载多个模型到显存
- 大文档需要分批处理以避免显存溢出
- 批次间冷却用于显存回收和散热

### 如果需要在VLM Direct模式中添加页码范围

可以修改VLM Direct配置部分,添加页码范围选项。位置在 [marker/scripts/streamlit_app.py](marker/scripts/streamlit_app.py) 第606-727行。

示例代码:
```python
# 在 VLM Direct 配置中添加
st.markdown("---")
st.markdown("**页码范围**")
use_page_range = st.checkbox("指定页码范围", value=False, key="vlm_direct_page_range")
if use_page_range:
    col1, col2 = st.columns(2)
    with col1:
        start_page = st.number_input("起始页", min_value=1, value=1, key="vlm_direct_start")
    with col2:
        end_page = st.number_input("结束页", min_value=1, value=10, key="vlm_direct_end")
```

---

## 总结

✅ **重复输出问题** - 已解决,注释掉调试语句
ℹ️ **配置项位置** - 在Pipeline模式中,切换到传统模式即可看到

如需在VLM Direct模式中添加页码范围等配置,可以参考上述示例代码进行修改。
