"""
彻底修复 OCR Direct 配置结构
"""
from pathlib import Path

streamlit_file = Path("marker/scripts/streamlit_app.py")

print("Step 1: Reading file...")
lines = streamlit_file.read_text(encoding='utf-8').split('\n')

print("\nStep 2: Finding key positions...")

# 找到关键位置
vlm_direct_info_start = None
ocr_direct_config_start = None
traditional_config_start = None

for i, line in enumerate(lines):
    if 'if conversion_mode == "vlm_direct":' in line and 'st.info' in lines[i+1]:
        vlm_direct_info_start = i
        print(f"[OK] Found VLM Direct info at line {i+1}")
    elif 'if conversion_mode == "ocr_direct":' in line and 'st.subheader' in lines[i+2]:
        ocr_direct_config_start = i
        print(f"[OK] Found OCR Direct config at line {i+1}")
    elif 'else:' in line and i > 600 and i < 700:
        if traditional_config_start is None:
            traditional_config_start = i
            print(f"[OK] Found traditional config at line {i+1}")

if not all([vlm_direct_info_start, ocr_direct_config_start]):
    print("[ERROR] Could not find all key positions")
    exit(1)

print(f"\n[INFO] VLM info: {vlm_direct_info_start+1}")
print(f"[INFO] OCR config: {ocr_direct_config_start+1}")
print(f"[INFO] Traditional: {traditional_config_start+1 if traditional_config_start else 'Not found'}")

# 找到 OCR Direct 配置的结束位置（下一个 else: 或 elif:）
ocr_config_end = None
for i in range(ocr_direct_config_start + 1, len(lines)):
    if lines[i].strip() in ['else:', 'elif conversion_mode']:
        ocr_config_end = i
        print(f"[OK] Found OCR config end at line {i+1}")
        break

if not ocr_config_end:
    print("[ERROR] Could not find OCR config end")
    exit(1)

print(f"\n[INFO] OCR Direct config spans lines {ocr_direct_config_start+1} to {ocr_config_end}")

# 修复策略：将 OCR Direct 配置改为 elif
print("\nStep 3: Fixing structure...")

# 修改 OCR Direct 配置的开始行
if 'if conversion_mode == "ocr_direct":' in lines[ocr_direct_config_start]:
    lines[ocr_direct_config_start] = lines[ocr_direct_config_start].replace(
        'if conversion_mode == "ocr_direct":',
        'elif conversion_mode == "ocr_direct":'
    )
    print("[OK] Changed 'if' to 'elif' for OCR Direct config")

# 保存文件
streamlit_file.write_text('\n'.join(lines), encoding='utf-8')

print("\n[SUCCESS] File fixed!")
print("\nStructure should now be:")
print("  if conversion_mode == 'vlm_direct':")
print("      st.info(...)")
print("  elif conversion_mode == 'ocr_direct':")
print("      st.info(...)")
print("  else:")
print("      st.success(...)  # Traditional")
print("")
print("  # Config area")
print("  if conversion_mode == 'vlm_direct':")
print("      # VLM config")
print("  elif conversion_mode == 'ocr_direct':")
print("      # OCR config")
print("  else:")
print("      # Traditional config")
