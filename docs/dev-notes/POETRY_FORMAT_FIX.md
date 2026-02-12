# 诗歌格式识别错误 - 修复方案

## 问题描述

**症状**: 诗歌的分行格式丢失，被合并成连续文本

**原文**:
```
— und weiß beglänzet sah
Ich Tempes Musentänze, schwang den neuen,
Den güldnen Hut — und hörte Kant! und wagte
Mit halber Zung' ein neues Lied!
```

**错误识别**:
```
>und weiß beglänzet sah Ich Tempes Musentänze, schwang den neuen, Den güldnen Hut
und hörte Kant! und wagte Mit halber Zung' ein neues Lied !
```

---

## 根本原因

### 1. Layout 检测问题

Surya Layout 没有识别出这是诗歌块，而是识别为普通文本。

**诗歌的特征**:
- 居中对齐
- 短行
- 特殊的缩进模式
- 通常字体较小

### 2. 行合并问题

Line merge processor 将诗歌的多行合并成了一行。

**合并逻辑**:
- 如果两行在同一个文本块中
- 且第二行不是以大写字母开头
- 就会被合并

---

## 修复方案

### 方案 1: 禁用行合并（快速修复）

在 Pipeline 模式配置中添加选项来禁用行合并。

**优点**: 简单快速
**缺点**: 可能影响正常段落的合并

### 方案 2: 改进诗歌检测（推荐）

添加诗歌块检测逻辑，识别居中对齐的短行文本。

**检测规则**:
1. 文本块包含多个短行（< 60 字符）
2. 行居中对齐或有特殊缩进
3. 行首大写字母比例高
4. 字体可能较小

### 方案 3: 使用 VLM Direct 模式

VLM 通常能更好地保持诗歌格式。

**优点**: 格式保持最好
**缺点**: 速度较慢，成本较高

---

## 立即可用的解决方案

### 临时方案: 使用 VLM Direct 模式

```
1. 转换模式: VLM Direct
2. 提示词模板: 哥特体德文（或自定义）
3. 在自定义指令中添加:
   "保持诗歌的原有分行格式，不要合并诗行"
```

这样 VLM 会保持诗歌的原始格式。

---

## 下一步

我将实现方案 2，添加诗歌块检测逻辑。
