"""
调试 blockquote 处理器 - 检查块的实际位置和结构

使用方法：
1. 在 blockquote.py 的 __call__ 方法中添加调试输出
2. 或者运行转换后检查文档结构
"""

import sys
sys.path.insert(0, 'd:/marker_cuda')

# 这个脚本用于分析问题
# 我们需要在实际转换时添加日志来查看块的位置

print("=" * 80)
print("Blockquote 调试分析")
print("=" * 80)
print()

print("问题描述：")
print("- 诗歌块（居中）没有被标记为 blockquote")
print("- 诗歌后的正常段落被错误标记为 blockquote")
print()

print("可能的原因：")
print()
print("1. 诗歌块的 structure 长度 < 2")
print("   - Line 43: if not len(block.structure) >= 2: continue")
print("   - 诗歌可能被识别为多个短块，每个块 structure 只有 1 个元素")
print()

print("2. Surya Layout 将诗歌每行识别为单独的块")
print("   - 诗歌不是一个整体块，而是 4-5 个小块")
print("   - 最后一行诗歌成为 prev_block")
print("   - 下一段相对于最后一行诗歌可能看起来对齐")
print()

print("3. x_start 对齐判断问题")
print("   - 诗歌居中，x_start 在中间位置")
print("   - 下一段回到左侧，x_start 更小")
print("   - 但 matching_x_start 可能因为某种原因为 True")
print()

print("=" * 80)
print("建议的修复方案")
print("=" * 80)
print()

print("方案 A：移除 structure 长度限制")
print("  - 删除 Line 43-45 的检查")
print("  - 允许所有块参与 blockquote 检测")
print("  - 风险：可能误标记单行文本")
print()

print("方案 B：修改延续 blockquote 的条件")
print("  - 当前：matching_x_end AND matching_x_start AND y_indent")
print("  - 修改：还要求 x_start 不能显著减小")
print("  - 即：下一段必须至少和诗歌一样缩进")
print()

print("方案 C：完全禁用 blockquote 延续")
print("  - 删除 Line 53-62 的整个分支")
print("  - 每个块独立判断是否为 blockquote")
print("  - 风险：多段 blockquote 会被拆分")
print()

print("=" * 80)
print("推荐方案：方案 B（最安全）")
print("=" * 80)
print()

print("修改 Line 58 的条件：")
print()
print("旧代码：")
print("  if matching_x_end and matching_x_start and y_indent:")
print()
print("新代码：")
print("  # 下一段必须至少和前一段一样缩进，不能回退到左侧")
print("  x_not_outdent = block.polygon.x_start >= prev_block.polygon.x_start - (self.x_start_tolerance * prev_block.polygon.width)")
print("  if matching_x_end and matching_x_start and y_indent and x_not_outdent:")
print()

print("这样可以确保：")
print("- 如果下一段回到左侧（x_start 显著减小），不会延续 blockquote")
print("- 只有真正对齐或更缩进的段落才会延续 blockquote")
