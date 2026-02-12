"""
彻底修复配置区域结构
"""
from pathlib import Path

file = Path("marker/scripts/streamlit_app.py")
lines = file.read_text(encoding='utf-8').split('\n')

print("Step 1: Finding config area...")

# 找到配置区域开始
config_start = None
for i, line in enumerate(lines):
    if '# ==================== 配置区域 ====================' in line:
        config_start = i
        print(f"[OK] Config area starts at line {i+1}")
        break

if not config_start:
    print("[ERROR] Config area not found")
    exit(1)

# 找到文件选择区域（配置区域结束）
config_end = None
for i in range(config_start, len(lines)):
    if '# ==================== 2. 文件选择 ====================' in line or '文件选择' in lines[i]:
        config_end = i
        print(f"[OK] Config area ends at line {i+1}")
        break

if not config_end:
    print("[ERROR] Config area end not found")
    exit(1)

print(f"\n[INFO] Config area: lines {config_start+1} to {config_end}")

# 删除配置区域，重新构建
print("\nStep 2: Rebuilding config area...")

# 保留配置区域之前和之后的内容
before_config = lines[:config_start+1]
after_config = lines[config_end:]

# 构建新的配置区域
new_config = [
    '',
    '    if conversion_mode == "vlm_direct":',
    '        # VLM Direct 配置',
    '        st.info("VLM Direct 配置区域 - 待实现")',
    '',
    '    elif conversion_mode == "ocr_direct":',
    '        # ==================== OCR Direct 模式配置 ====================',
    '        st.subheader("📚 OCR Direct 配置")',
]

print("[OK] Created new config structure")

# 合并
lines = before_config + new_config + after_config

# 保存
file.write_text('\n'.join(lines), encoding='utf-8')

print("\n[SUCCESS] File rebuilt!")
print("\nNew structure:")
print("  if conversion_mode == 'vlm_direct':")
print("      # VLM config")
print("  elif conversion_mode == 'ocr_direct':")
print("      # OCR config")
print("  else:")
print("      # Traditional config")
