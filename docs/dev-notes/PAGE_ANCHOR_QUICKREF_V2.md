# 页码锚点系统快速参考

## 核心概念

### 双层页码系统
1. **定位层**：`{n}` 锚点（0-based）
   - 用于范围提取：`{2}-{5}` = 第 3-5 页
   - 固定格式，不可配置

2. **显示层**：`<!-- Page: X -->` 标签
   - 显示人类可读的页码
   - 支持多种来源

## UI 配置

### 基础配置
```
☑ 启用页码锚点
锚点位置：○ 页面前 ○ 页面后 ○ 页面前后
☑ 提取印刷页码
```

### 自定义编号来源

#### 1. 无（默认）
- 仅使用自动识别的印刷页码
- 如果没有印刷页码，不显示 `<!-- Page: X -->` 标签

#### 2. VLM 输出提取
- 从 VLM 输出中提取页码信息
- 配置正则表达式：`页码[:：]\s*(\S+)`

#### 3. 上传文件
- 支持 CSV 格式：`0,sc001\n1,sc002`
- 支持 JSON 格式：`{"0": "sc001", "1": "sc002"}`

#### 4. 手动输入列表
- 逗号分隔：`sc001, sc002, sc003`
- 换行分隔：
  ```
  sc001
  sc002
  sc003
  ```

#### 5. 自动生成
- 前缀：`sc`
- 起始编号：`1`
- 编号位数：`3`
- 结果：`sc001, sc002, sc003...`

## 优先级

```
印刷页码（自动识别）> 自定义编号 > 无
```

### 示例
```markdown
# 场景 1：仅印刷页码
{0}
<!-- Page: XII -->
内容...

# 场景 2：仅自定义编号
{0}
<!-- Page: sc001 -->
内容...

# 场景 3：两者都有（印刷页码优先）
{0}
<!-- Page: XII -->
内容...

# 场景 4：都没有
{0}
内容...
```

## 代码示例

### Python API
```python
from marker.formatters import CustomIDInjector, PageAnchorFormatter, PageAnchorPlugin

# 创建自定义编号注入器
injector = CustomIDInjector(
    source_type="auto",
    source_data={"prefix": "sc", "start": 1, "digits": 3}
)

# 创建页码锚点格式化器
formatter = PageAnchorFormatter(wrapper="{{{}}}")

# 创建页码锚点插件
plugin = PageAnchorPlugin(
    formatter=formatter,
    enabled=True,
    position="before",
    separator="\n\n",
    custom_id_injector=injector
)

# 处理页面内容
content = "页面内容..."
result = plugin.wrap_page_content(0, content)
# 输出：
# {0}
#
# <!-- Page: sc001 -->
# 页面内容...
```

### VLM Direct 配置
```python
config = {
    "vlm_direct_enable_page_anchors": True,
    "vlm_direct_page_anchor_position": "before",
    "vlm_direct_custom_id_source": "auto",
    "vlm_direct_custom_id_data": {
        "prefix": "sc",
        "start": 1,
        "digits": 3
    }
}
```

### Pipeline 配置
```python
config = {
    "custom_id_source": "list",
    "custom_id_data": ["卷一", "卷二", "卷三"]
}
```

## 常见用例

### 用例 1：古籍档案编号
```python
# 配置
custom_id_source = "auto"
custom_id_data = {
    "prefix": "档",
    "start": 1,
    "digits": 4
}

# 输出
{0}
<!-- Page: 档0001 -->
```

### 用例 2：多卷书籍
```python
# 配置
custom_id_source = "list"
custom_id_data = ["卷一", "卷二", "卷三", "卷四"]

# 输出
{0}
<!-- Page: 卷一 -->
```

### 用例 3：混合编号
```python
# Pipeline 模式自动识别印刷页码
# 同时配置自定义编号作为补充

# 输出（有印刷页码的页面）
{0}
<!-- Page: XII -->

# 输出（无印刷页码的页面）
{1}
<!-- Page: sc002 -->
```

## 范围提取

### 语法
```
{起始页}-{结束页}
```

### 示例
```
{0}-{2}   # 提取第 1-3 页（0-based）
{5}-{9}   # 提取第 6-10 页
{10}-{10} # 提取第 11 页
```

### 注意事项
- 页码是 0-based（第一页是 {0}）
- 范围是闭区间（包含起始和结束页）
- 文档末尾有额外的 {n} 锚点用于提取最后几页

## 故障排除

### 问题 1：自定义编号不显示
- 检查 `custom_id_source` 是否设置正确
- 检查 `custom_id_data` 格式是否正确
- 确认页面索引在范围内

### 问题 2：印刷页码优先级问题
- 印刷页码始终优先于自定义编号
- 如果不想使用印刷页码，关闭"提取印刷页码"选项

### 问题 3：列表格式错误
- 支持逗号或换行分隔
- 支持字符串或列表输入
- 空白项会被自动过滤

## 更新日志

### 2026-02-01
- ✅ 简化页码锚点系统（固定 {n} 格式）
- ✅ 新增自定义编号功能（5 种来源）
- ✅ 实现双层页码系统
- ✅ 更新前端 UI
- ✅ 更新后端逻辑
- ✅ 完成测试验证
