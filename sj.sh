#!/bin/bash

# =======================================================
# 停止所有 QuantConnect LEAN Research Docker 容器
# 执行方式: sh stop.sh 或 ./stop.sh
# =======================================================

echo "--- LEAN Research Docker 终止器 ---"
echo "🛑 正在查找并停止所有使用 'quantconnect/research' 镜像的容器..."

# 1. 查找目标容器 ID
# docker ps -a: 列出所有容器 (包括停止的)
# --filter ancestor=quantconnect/research:latest: 筛选出基于指定镜像的容器
# --quiet / -q: 只输出容器 ID
CONTAINER_IDS=$(docker ps -a --filter ancestor=quantconnect/research --filter status=running --quiet)

# 2. 检查是否找到容器
if [ -z "$CONTAINER_IDS" ]; then
    echo "🎉 未发现任何正在运行的使用 'quantconnect/research' 镜像的容器。"
else
    echo "⚠️ 发现以下容器 ID 需要停止和移除: ${CONTAINER_IDS}"
    
    # 3. 停止容器 (docker stop)
    echo "🔪 正在停止容器..."
    # 使用 xargs 一次性停止所有找到的 ID
    echo "$CONTAINER_IDS" | xargs -r docker stop
    
    # 4. 移除容器 (docker rm) - 可选，但推荐，以清理残留
    # 再次运行 docker ps -a 确保获取到停止后的容器ID
    STOPPED_IDS=$(docker ps -a --filter ancestor=quantconnect/research --filter status=exited --quiet)
    if [ -n "$STOPPED_IDS" ]; then
        echo "🧹 正在移除已停止的容器..."
        echo "$STOPPED_IDS" | xargs -r docker rm
    fi

    echo "✅ 所有相关的 'quantconnect/research' 容器已停止并移除。"
fi

echo "--- 终止程序执行完毕 ---"