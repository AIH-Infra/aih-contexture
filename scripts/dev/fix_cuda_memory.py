"""
CUDA 内存不足 - 临时修复脚本

如果重启应用后仍然报错，运行此脚本来降低批处理大小
"""

import sys
sys.path.insert(0, 'd:/marker_cuda')

# 修改默认批处理大小
from aih_contexture.builders import layout

# 保存原始方法
original_get_batch_size = layout.LayoutBuilder.get_batch_size

# 创建新方法（降低批处理大小）
def reduced_batch_size(self):
    if self.layout_batch_size is not None:
        return self.layout_batch_size
    elif hasattr(layout.settings, 'TORCH_DEVICE_MODEL') and layout.settings.TORCH_DEVICE_MODEL == "cuda":
        return 6  # 降低到 6（原来是 12）
    return 4  # CPU 也降低到 4（原来是 6）

# 替换方法
layout.LayoutBuilder.get_batch_size = reduced_batch_size

print("✅ 批处理大小已降低：")
print("   CUDA: 12 → 6")
print("   CPU: 6 → 4")
print()
print("现在可以重新运行转换了")
