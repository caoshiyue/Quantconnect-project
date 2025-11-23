#!/bin/bash
# safer rename-in-zip-and-save-to-new-path.sh
# 说明: 不修改原始 zip，解压到临时目录，重命名 csv（删除最后一个 '_' 及之后的部分），
# 然后在目标路径创建新的 zip 文件（使用绝对路径），保留原始目录结构。

set -o errexit
set -o nounset
set -o pipefail

# --- 配置区 (请按需修改) ---
BASE_DIR="./data/future_old/comex/second"   # 原始 zip 所在顶层目录
TARGET_DIR="./data/future/comex/second"     # 处理后 zip 存放顶层目录
TEMP_DIR="./tmp/zip_processing_$$"           # 临时目录（包含 PID）
# -------------------------------

echo "=== 开始处理 ZIP 档案（安全模式） ==="
echo "原始目录: $BASE_DIR"
echo "目标目录: $TARGET_DIR"
echo "临时目录: $TEMP_DIR"

mkdir -p "$TEMP_DIR" || { echo "无法创建临时目录 $TEMP_DIR"; exit 1; }

# 使用 find -print0 以支持带空格的文件名
find "$BASE_DIR" -type f -name "*.zip" -print0 | while IFS= read -r -d '' zip_file; do
    echo
    echo "---- 处理: $zip_file ----"

    # 计算相对路径以在目标处重建目录结构
    relative_path="${zip_file#$BASE_DIR/}"          # e.g. gc/20160101_quote.zip
    target_zip_path="$TARGET_DIR/$relative_path"    # e.g. ./data/future/.../gc/20160101_quote.zip
    target_dir=$(dirname "$target_zip_path")

    # 创建目标子目录（在主脚本工作目录下）
    mkdir -p "$target_dir" || { echo "警告: 无法创建目标目录 $target_dir. 跳过."; continue; }

    # 生成目标 zip 的绝对路径（这样无论当前工作目录在哪儿，zip 都能写入）
    # 取目标目录的绝对路径 + zip 文件名
    target_dir_abs="$(cd "$target_dir" && pwd)"
    target_zip_path_abs="$target_dir_abs/$(basename "$target_zip_path")"

    # 清空并创建每个循环独立的 extract 目录（避免残留）
    extract_dir="$TEMP_DIR/extract"
    rm -rf "$extract_dir"
    mkdir -p "$extract_dir"

    # 解压到临时 extract 目录（保持原始内部目录结构）
    if ! unzip -qq "$zip_file" -d "$extract_dir"; then
        echo "警告: 解压失败: $zip_file. 跳过."
        rm -rf "$extract_dir"
        continue
    fi

    # 查找所有 csv 并进行重命名：删掉文件名中从右往第一次出现 '_' 之后的部分（包括 '_'）
    find "$extract_dir" -type f -name "*.csv" -print0 | while IFS= read -r -d '' csv_path; do
        rel_path="${csv_path#$extract_dir/}"    # 相对于 extract 的路径（含子目录）
        dir_of_file=$(dirname "$rel_path")      # 可能为 "."
        base_name=$(basename "$rel_path")       # 原始文件名

        name_no_ext="${base_name%.*}"           # 去掉扩展名
        ext="${base_name##*.}"

        if [[ "$name_no_ext" == *"_"* ]]; then
            new_name_base="${name_no_ext%_*}"
        else
            new_name_base="$name_no_ext"
        fi
        new_basename="${new_name_base}.${ext}"

        src="$csv_path"
        dst_dir="$extract_dir/$dir_of_file"
        dst="$dst_dir/$new_basename"

        if [[ "$src" != "$dst" ]]; then
            if [[ -e "$dst" ]]; then
                echo "警告: 目标文件已存在，将覆盖: $dst"
                rm -f "$dst"
            fi
            mv -f "$src" "$dst"
        fi
    done

    # 检查是否有 csv 存在
    csv_count=$(find "$extract_dir" -type f -name "*.csv" | wc -l)
    if [[ "$csv_count" -eq 0 ]]; then
        echo "提示: 在 $zip_file 中未找到 .csv 文件 —— 直接复制原始 zip 到目标位置。"
        cp -f "$zip_file" "$target_zip_path_abs"
        rm -rf "$extract_dir"
        echo "    已复制到: $target_zip_path_abs"
        continue
    fi

    # 删除目标 zip（如果存在），以避免 zip 无法覆盖的问题
    rm -f "$target_zip_path_abs"

    # 进入 extract 目录（非子 shell），把 extract 下所有内容压缩到目标绝对路径中
    cd "$extract_dir" || { echo "错误: 无法进入解压目录 $extract_dir"; rm -rf "$extract_dir"; continue; }

    if ! zip -qr "$target_zip_path_abs" .; then
        echo "错误: 无法创建目标 zip: $target_zip_path_abs"
        # 确保回到主目录（安全起见）
        cd - >/dev/null 2>&1 || true
        rm -rf "$extract_dir"
        continue
    fi

    # 返回原工作目录并清理解压目录
    cd - >/dev/null 2>&1 || true
    rm -rf "$extract_dir"

    echo "    已处理并保存到目标: $target_zip_path_abs"

done

# 处理完毕，清理顶层临时目录
rm -rf "$TEMP_DIR"
echo "=== 所有处理完成。已清理临时目录 $TEMP_DIR ==="
