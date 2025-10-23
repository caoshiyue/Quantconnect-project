#!/bin/bash
# 建议将 shebang 改为 #!/bin/bash，以便在执行 ./start_lean.sh 时使用 Bash。
# 但是为了兼容 sh start_lean.sh，我们将内部语法改为 POSIX 兼容的。

# =======================================================
# 启动 QuantConnect LEAN Research 环境 (POSIX 兼容版)
# 执行方式: sh start_lean.sh 或 ./start_lean.sh
# =======================================================

# 1. 定义常量
BASE_PATH="/data1/shiyue.cao/quant"
CONDA_ENV_NAME="quant"
CURRENT_DIR=$(pwd)

echo "--- LEAN Research 启动器 ---"

# 2. 识别项目名称
# 将 Bash 的 [[ ... ]] 和 == 替换为 POSIX 兼容的 [ ... ] 和 * 模式匹配
echo "当前目录: ${CURRENT_DIR}"
echo "期望根目录: ${BASE_PATH}"

# 使用模式匹配判断 $CURRENT_DIR 是否以 $BASE_PATH/ 开头
if echo "$CURRENT_DIR" | grep -q "^${BASE_PATH}/"; then
    # 提取项目名称 (basename $CURRENT_DIR)
    PROJECT_NAME=$(basename "$CURRENT_DIR")
    echo "✅ 自动识别项目名称: ${PROJECT_NAME}"
else
    # 如果不在预期的路径下，则提示手动输入
    echo "❌ 警告: 当前目录 (${CURRENT_DIR}) 不在预期的 LEAN 根目录 (${BASE_PATH}) 的子文件夹中。"
    read -p "请手动输入项目名称 (例如 MyFirstStrategy): " PROJECT_NAME
fi

# 检查项目名是否为空
if [ -z "$PROJECT_NAME" ]; then
    echo "❌ 错误: 项目名称不能为空。退出。"
    exit 1
fi

# 3. 切换到 LEAN 根目录
echo "➡️ 切换到 LEAN 根目录: ${BASE_PATH}"
cd "$BASE_PATH" || { 
    echo "❌ 错误: 无法进入 ${BASE_PATH} 目录。请检查路径是否正确。"
    exit 1 
}

# 4. 激活 Conda 环境
echo "➡️ 激活 Conda 环境: ${CONDA_ENV_NAME}"
# 激活 Conda 脚本，使用 [ -f ... ] 代替 [[ -f ... ]]
if [ -f "$(conda info --base)/etc/profile.d/conda.sh" ]; then
    # 注意: 在 sh 环境中，'source' 是 ' . ' (点空格)
    . "$(conda info --base)/etc/profile.d/conda.sh"
    conda activate "$CONDA_ENV_NAME" || {
        echo "❌ 错误: 无法激活 Conda 环境 '${CONDA_ENV_NAME}'。请检查环境名和 Conda 设置。"
        exit 1
    }
else
    echo "❌ 错误: 找不到 Conda 初始化脚本。请检查 Conda 安装。"
    exit 1
fi

# 5. 启动 lean research
echo "🚀 启动 lean research \"${PROJECT_NAME}\"..."
lean research "$PROJECT_NAME" --no-open

echo "✅ LEAN Research 会话已退出或已启动。"