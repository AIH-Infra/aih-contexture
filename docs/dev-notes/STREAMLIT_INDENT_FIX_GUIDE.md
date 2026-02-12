# Streamlit应用缩进修复指南

## 问题
streamlit应用出现IndentationError,导致无法启动。

## 快速修复方案

### 方案1: 使用Git恢复(推荐)
如果你使用了Git版本控制:
```bash
cd d:\marker_cuda
git checkout marker/scripts/streamlit_app.py
```

然后手动应用必要的修改(见下文"必要的修改")。

### 方案2: 手动修复缩进

由于自动修复脚本导致了缩进混乱,建议手动修复以下关键部分:

#### 1. LLM配置块 (第1143-1342行)
确保缩进正确:
```python
            if use_llm:  # 12空格
                with st.expander("LLM 配置", expanded=True):  # 16空格
                    # API 提供商选择  # 20空格
                    llm_provider = st.selectbox(  # 20空格
                        "API 提供商",  # 24空格
                        ...
                    )

                    # Gemini 配置  # 20空格
                    if llm_provider == "gemini":  # 20空格
                        st.caption("...")  # 24空格
                        llm_api_key = st.text_input(  # 24空格
                            "Gemini API Key",  # 28空格
                            ...
                        )
```

#### 2. 处理设置块 (第1371-1447行)
确保缩进正确:
```python
            # ==================== 6. 处理设置 ====================  # 12空格
            st.subheader("⚡ 处理设置")  # 12空格

            # 批处理模式选择  # 12空格
            batch_mode = st.radio(  # 12空格
                "处理模式",  # 16空格
                ...
            )

            # 根据选择显示相关设置  # 12空格
            if batch_mode == "分批处理" or batch_mode == "自动":  # 12空格
                st.info("...")  # 16空格
                col_a, col_b = st.columns(2)  # 16空格
                with col_a:  # 16空格
                    batch_threshold = st.number_input(  # 20空格
                        "分批阈值（页）",  # 24空格
                        ...
                    )
```

### 方案3: 使用修复脚本

创建一个Python脚本来修复缩进:

```python
# fix_streamlit_indent.py
import re

def fix_indentation(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        lines = f.readlines()

    fixed_lines = []
    in_llm_block = False
    in_processing_block = False

    for i, line in enumerate(lines):
        line_num = i + 1

        # 检测块的开始和结束
        if 'if use_llm:' in line and line_num >= 1140:
            in_llm_block = True
        elif '# ==================== 6. 处理设置' in line:
            in_llm_block = False
            in_processing_block = True
        elif '# ==================== 6. 操作按钮' in line:
            in_processing_block = False

        # 修复缩进
        if in_llm_block:
            # LLM块的缩进逻辑
            if line.strip().startswith('if use_llm:'):
                fixed_lines.append(' ' * 12 + line.lstrip())
            elif line.strip().startswith('with st.expander'):
                fixed_lines.append(' ' * 16 + line.lstrip())
            elif line.strip() and not line.strip().startswith('#'):
                # 根据上下文确定缩进
                # 这里需要更复杂的逻辑
                fixed_lines.append(line)
            else:
                fixed_lines.append(line)
        elif in_processing_block:
            # 处理设置块的缩进逻辑
            if line.strip().startswith('#') and '====' in line:
                fixed_lines.append(' ' * 12 + line.lstrip())
            elif line.strip().startswith('st.subheader'):
                fixed_lines.append(' ' * 12 + line.lstrip())
            else:
                # 保持相对缩进
                fixed_lines.append(line)
        else:
            fixed_lines.append(line)

    with open(filepath, 'w', encoding='utf-8') as f:
        f.writelines(fixed_lines)

if __name__ == "__main__":
    fix_indentation("d:/marker_cuda/marker/scripts/streamlit_app.py")
    print("Fixed indentation")
```

## 必要的修改

修复缩进后,还需要应用以下必要的修改:

### 1. 注释调试输出 (第29-30行)
```python
# 调试输出已注释 - 避免重复打印
# print("marker.__file__ =", marker.__file__)
# print("marker.converters.pdf.__file__ =", marker.converters.pdf.__file__)
```

### 2. 将LLM增强移出VLM OCR分支
确保"LLM增强"配置在所有OCR后端配置之后,而不是在VLM OCR的条件分支内。

### 3. 将处理设置移出VLM OCR分支
确保"处理设置"配置在所有OCR后端配置之后,而不是在VLM OCR的条件分支内。

## 验证修复

修复后,运行streamlit应用:
```bash
cd d:\marker_cuda
streamlit run marker/scripts/streamlit_app.py
```

如果没有IndentationError,说明修复成功。

## 如果还有问题

如果修复后还有问题,建议:
1. 使用Git恢复到之前的版本
2. 使用Python IDE(如PyCharm, VSCode)的自动格式化功能
3. 或者联系我获取完整的修复后的文件

## VLM认证错误的解决方案

关于VLM的403认证错误,请参考 [STREAMLIT_CONFIG_FIX_REPORT.md](STREAMLIT_CONFIG_FIX_REPORT.md) 中的解决方案。

简单来说:
1. 检查API Key是否正确
2. 或者切换到Surya后端(不需要API Key)

推荐配置:
```
转换模式: Pipeline (传统模式)
版面识别后端: Surya
OCR 后端: Surya
```
