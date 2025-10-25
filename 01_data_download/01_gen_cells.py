# region imports
from AlgorithmImports import *
# endregion
import json

def add_batch_cells_to_notebook(
    input_nb_path,
    output_nb_path,
    batch_count,
    max_workers=8,
):
    """
    向现有 .ipynb 文件添加多个批处理 cell。
    
    每个 cell 的内容为：
        create_base64_links_parallel(batches[i], max_workers=N)
    """
    # 读取原 notebook
    with open(input_nb_path, "r", encoding="utf-8") as f:
        nb_data = json.load(f)

    # 构造新 cell
    new_cells = []
    for i in range(batch_count):
        code = f"create_base64_links_parallel(batches[{i}], max_workers={max_workers})"
        new_cell = {
            "cell_type": "code",
            "execution_count": None,
            "metadata": {},
            "outputs": [],
            "source": [code],
        }
        new_cells.append(new_cell)

    # 把这些 cell 追加到现有 notebook 最后
    nb_data["cells"].extend(new_cells)

    # 保存新文件
    with open(output_nb_path, "w", encoding="utf-8") as f:
        json.dump(nb_data, f, ensure_ascii=False, indent=2)

    print(f"✅ 已在 {output_nb_path} 中添加 {batch_count} 个批处理 cell。")

# === 示例使用 ===
add_batch_cells_to_notebook(
    input_nb_path="02_data_download.ipynb",   # 你的原始 notebook 路径
    output_nb_path="02_data_download_cells.ipynb",  # 输出路径
    batch_count=35,              # 自动根据 batches 长度添加
    max_workers=2
)
