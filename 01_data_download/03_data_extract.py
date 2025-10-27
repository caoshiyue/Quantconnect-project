# region imports
from AlgorithmImports import *
# endregion
import os
import re
import json
import base64
from pathlib import Path
import time
notebook_path = "02_data_download_run.ipynb"


time.sleep(10)  # 等待文件写入完成
# ===   读取 notebook 文件 ===
with open(notebook_path, "r", encoding="utf-8") as f:
    nb = json.load(f)

# ===   从第1个cell输出中提取文件路径列表 ===
printed_files = []
for cell in nb.get("cells", []):
    if cell.get("cell_type") != "code":
        continue
    source = "".join(cell.get("source", []))
    
    # 找到第一个包含 find_files 的 cell（即打印文件列表的）
    if "find_files" in source:
        for output in cell.get("outputs", []):
            text_output = output.get("text")
            if not text_output:
                continue
            # 提取打印的路径，例如： "   /Data/future/comex/file1.parquet"
            text = "".join(text_output)
            printed_files = re.findall(r"^\s+(/[\w\-/\.]+)$", text, re.MULTILINE)
        break

if not printed_files:
    print("  未在第一个 cell 输出中找到文件列表。")
else:
    print(f" 从第一个 cell 输出中提取到 {len(printed_files)} 个文件路径。")

# ===  从 notebook 输出的下载链接中提取文件名 ===
extracted_files = []
file_b64_map = {}

for cell in nb.get("cells", []):
    if cell.get("cell_type") != "code":
        continue
    for output in cell.get("outputs", []):
        html = output.get("data", {}).get("text/html")
        if not html:
            continue
        if isinstance(html, list):
            html = "".join(html)
        matches = re.findall(
            r'<a download="([^"]+)" href="data:application/zip;base64,([^"]+)">',
            html
        )
        for filename, b64data in matches:
            extracted_files.append(filename)
            file_b64_map[filename] = b64data

print(f" 提取到 {len(extracted_files)} 个 Base64 下载链接。")

# ===   一致性校对 ===
printed_names = {p for p in printed_files}
extracted_names = set(extracted_files)

missing = printed_names - extracted_names
extra = extracted_names - printed_names

print("-" * 60)
print(" 一致性校对结果：")
print(f"  筛选阶段文件数: {len(printed_names)}")
print(f"  下载链接数:     {len(extracted_names)}")

if not missing and not extra:
    print("  文件列表与下载链接完全一致！")
else:
    if missing:
        print(f"  缺少下载链接的文件名: {missing}")
    if extra:
        print(f" 额外生成的下载链接文件名: {extra}")


valid_files = printed_names & extracted_names
if not valid_files:
    print("  没有可保存的文件。")
else:
    print(f"\n  开始保存 {len(valid_files)} 个校对成功的文件...\n")

    for filename in valid_files:
        # 路径替换：将 /Data/... 映射到 ../data/...
        local_path = filename.replace("/Data", "../data", 1)
        local_path = local_path.replace("future_old", "future", 1)
        dir_name = os.path.dirname(local_path)
        if dir_name:
            os.makedirs(dir_name, exist_ok=True)

        b64data = file_b64_map.get(filename)
        if not b64data:
            print(f" 找不到 {filename} 的 Base64 数据，跳过。")
            continue

        try:
            with open(local_path, "wb") as f_out:
                f_out.write(base64.b64decode(b64data))
            #print(f" 文件已成功保存到: {local_path}")
        except Exception as e:
            print(f" 保存 {local_path} 失败: {e}")

print("\n  校对与保存流程已完成。")