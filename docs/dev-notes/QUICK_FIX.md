# 快速修复streamlit应用

## 最简单的方法

```bash
# 1. 恢复到git版本
cd d:\marker_cuda
git restore marker/scripts/streamlit_app.py

# 2. 只应用必要的修改 - 注释调试输出
```

然后手动编辑 marker/scripts/streamlit_app.py 第29-30行:
```python
# 调试输出已注释 - 避免重复打印
# print("marker.__file__ =", marker.__file__)
# print("marker.converters.pdf.__file__ =", marker.converters.pdf.__file__)
```

## 关于配置项看不到的问题

原始版本中,"处理设置"等配置确实在Pipeline模式中,只是可能在某个OCR后端的条件分支内。

**解决方案:**
1. 启动streamlit应用
2. 选择"Pipeline (传统模式)"
3. 选择任意OCR后端(Surya推荐)
4. 向下滚动查找"处理设置"部分

如果还是看不到,说明原始代码就有这个问题,需要手动修改。

## 关于VLM 403错误

这是API认证问题,与代码无关。

**解决方案:**
切换到Surya后端(不需要API Key):
```
转换模式: Pipeline (传统模式)
版面识别后端: Surya
OCR 后端: Surya
```

这是最稳定的配置,完全本地运行。
