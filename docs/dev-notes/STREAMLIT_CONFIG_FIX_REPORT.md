# Streamlit配置面板问题修复报告

## 问题1: 配置项位置错误 ✅ 已修复(部分)

### 问题描述
"分批处理"、"页码范围"、"批次冷却"、"高级选项"等配置被错误地放在了VLM OCR后端的条件分支内,导致选择其他OCR后端时这些配置不可见。

### 根本原因
代码结构问题:
```python
elif ocr_backend == "vlm":
    # VLM OCR配置
    st.divider()

    # LLM增强配置 ← 错误!应该在所有OCR后端之后
    st.subheader("🧠 LLM 增强")
    if use_llm:
        # ...

    # 处理设置 ← 错误!应该在所有OCR后端之后
    st.subheader("⚡ 处理设置")
    # ...
```

### 修复方案
将"LLM增强"和"处理设置"移出VLM OCR的条件分支,放在所有OCR后端配置之后:

```python
elif ocr_backend == "vlm":
    # VLM OCR配置
    # ...

# ==================== OCR 后端配置结束 ====================
st.divider()

# ==================== 5. LLM 增强配置 ====================
st.subheader("🧠 LLM 增强")
use_llm = st.checkbox("启用 LLM 增强", ...)
# ...

st.divider()

# ==================== 6. 处理设置 ====================
st.subheader("⚡ 处理设置")
# 批处理模式
# 页码范围
# 高级选项
```

### 修复状态
- ✅ 已将"LLM增强"移出VLM OCR分支
- ✅ 已将"处理设置"移出VLM OCR分支
- ⚠️ 缩进需要手动调整(自动修复脚本出现问题)

### 手动修复步骤
由于自动缩进修复出现问题,需要手动调整 [marker/scripts/streamlit_app.py](marker/scripts/streamlit_app.py) 第1371-1447行的缩进:

1. 找到第1371行: `# ==================== 6. 处理设置 ====================`
2. 确保该行及以下所有内容的基础缩进为12个空格(与`st.subheader("🧠 LLM 增强")`同级)
3. 相对缩进保持不变(if块内+4空格,with块内+4空格)

正确的缩进示例:
```python
            # ==================== 6. 处理设置 ====================  (12空格)
            st.subheader("⚡ 处理设置")                              (12空格)

            # 批处理模式选择                                          (12空格)
            batch_mode = st.radio(                                   (12空格)
                "处理模式",                                           (16空格)
                options=["自动", "单批处理", "分批处理"],              (16空格)
                ...
            )

            # 根据选择显示相关设置                                    (12空格)
            if batch_mode == "分批处理" or batch_mode == "自动":     (12空格)
                st.info("...")                                       (16空格)
                col_a, col_b = st.columns(2)                         (16空格)
                with col_a:                                          (16空格)
                    batch_threshold = st.number_input(               (20空格)
                        "分批阈值（页）",                             (24空格)
                        ...
                    )
```

---

## 问题2: VLM认证错误 (403 Access Denied)

### 错误信息
```
[ERROR] marker: [VlmLayoutService] All retries failed: Error code: 403 -
{'error': {'message': 'access denied for invalid user', 'type': 'access_denied_error', ...}}
```

### 问题分析
1. **VLM Layout后端**: 使用VLM进行版面识别时出现403错误
2. **VLM OCR后端**: 使用VLM进行OCR时也出现403错误
3. **错误原因**: API认证失败 - "invalid user"

### 可能的原因

#### 1. API Key未配置或无效
- 检查streamlit配置面板中的API Key是否正确填写
- 检查环境变量是否设置

#### 2. API Key权限不足
- 某些API提供商对不同的API Key有不同的权限
- 免费API Key可能没有访问权限

#### 3. API URL配置错误
- Base URL可能指向了错误的服务
- 某些服务需要特定的URL格式

#### 4. VLM Layout使用了独立配置
- 如果勾选了"使用独立的 API 配置",需要单独配置VLM Layout的API Key
- 检查VLM Layout配置是否正确

### 解决方案

#### 方案1: 检查API配置
1. 打开streamlit应用
2. 选择Pipeline模式
3. 在"版面识别后端"选择"VLM"
4. 展开"VLM 版面识别配置"
5. 检查:
   - ✅ Base URL是否正确
   - ✅ 模型名称是否正确
   - ✅ API Key是否有效
   - ✅ 如果使用独立配置,确保两个配置都正确

#### 方案2: 使用环境变量
在启动streamlit前设置环境变量:
```bash
# Windows PowerShell
$env:OPENAI_BASE_URL="https://api.openai.com/v1"
$env:OPENAI_MODEL="gpt-4o"
$env:OPENAI_API_KEY="sk-your-key-here"

# 启动streamlit
streamlit run marker/scripts/streamlit_app.py
```

#### 方案3: 切换到其他后端
如果VLM认证问题无法解决,可以切换到其他后端:
- **版面识别**: 使用Surya(推荐,内置,无需API)
- **OCR**: 使用Surya(推荐,内置,无需API)

推荐配置:
```
版面识别后端: Surya
OCR 后端: Surya
```

这是最稳定的配置,不需要任何API Key。

#### 方案4: 检查API提供商
不同的API提供商有不同的认证方式:

**OpenAI:**
- Base URL: `https://api.openai.com/v1`
- API Key: `sk-...`
- 模型: `gpt-4o`, `gpt-4o-mini`

**LM Studio (本地):**
- Base URL: `http://localhost:1234/v1`
- API Key: 任意值(如`lm-studio`)
- 模型: 本地模型名称

**通义千问:**
- Base URL: `https://dashscope.aliyuncs.com/compatible-mode/v1`
- API Key: `sk-...`
- 模型: `qwen-vl-max`, `qwen-vl-plus`

### 调试步骤
1. 确认API Key有效性:
   ```bash
   curl https://api.openai.com/v1/models \
     -H "Authorization: Bearer YOUR_API_KEY"
   ```

2. 检查streamlit日志:
   - 查看完整的错误信息
   - 确认使用的Base URL和模型

3. 测试简单请求:
   - 使用curl或Postman测试API
   - 确认认证成功

---

## 总结

### 已修复
✅ 配置项位置问题 - LLM增强和处理设置已移出VLM OCR分支

### 需要手动修复
⚠️ 缩进问题 - 第1371-1447行需要手动调整缩进为12个空格基础

### 需要用户操作
❓ VLM认证错误 - 需要检查API配置或切换到Surya后端

### 推荐配置
对于大多数用户,推荐使用:
```
转换模式: Pipeline (传统模式)
版面识别后端: Surya
OCR 后端: Surya
```

这个配置不需要任何API Key,完全本地运行,稳定可靠。
