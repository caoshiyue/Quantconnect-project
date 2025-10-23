<!--
 * @Author:  
 * @Description:  
 * @LastEditors: Shiyuec
 * @LastEditTime: 2025-10-23 11:21:55
-->

---

# Lean CLI + Docker + VSCode 本地开发配置大纲

## 1. 环境准备

* **系统要求**

  * Linux / macOS / Windows（推荐 Linux）
  * 已安装：`Docker`、`Docker Compose`、`VSCode`
* **VSCode 插件**

  * *Python*
  * *Jupyter*
  * *Remote - Containers*（可选）
  * *Docker*（可选）
* **Lean CLI 安装**

  ```bash
  pip install lean
  lean login
  ```

---

## 2. 项目结构初始化

* 新建或导入项目：

  ```bash
  lean create-project MyProject
  ```
* 结构说明：

  ```
  MyProject/
  ├── config.json           # 全局配置（可绑定 data 目录、本地路径）
  ├── Algorithm.Python/
  │   └── MyAlgorithm.py    # 你的 Python 算法
  ├── Data/                 # 数据文件夹（可自动挂载）
  └── .vscode/              # VSCode 配置文件夹
  ```

---

## 3. 数据与挂载

* 本地 `./data`
* Lean CLI 在运行容器（research/backtest）时，会**自动挂载本地 Data** 到容器的 `/Lean/Data`。
* 可在 `config.json` 中显式指定：

  ```json
  "data-folder": "/home/you/Lean/Data"
  ```
* 期货数据包括：
  factor_files 用于计算主连
  map_files 用于记录合约信息
  tick second 等，市场数据，其中包括trade 每个时刻的OHLC 和 quote 挂单价；
---

## 4. Research 环境（Jupyter）

* 启动研究容器：

  ```bash
  lean research "Project"
  ```
* 默认行为：

  * 启动一个容器（包含 Python + .NET + pythonnet）
  * 映射 `/Lean/Data`
  * 启动 jupyter server，打印访问 URL
* 可在浏览器中访问 `localhost:<port>`，或在 VSCode 中输入该 URL 作为 kernel 地址。

---

## 5. VSCode 与容器内 Jupyter 联动

* 打开 `.ipynb` 文件 → 选择 Kernel → “Enter Jupyter Server URL” → 输入上面 `lean research` 打印的 URL。
* 此时：

  * VSCode 在本地编辑，但代码执行在容器中；
  * 你获得容器内所有包、环境、Lean 引擎；
  * 数据、日志、结果会同步写入挂载目录。

---

## 6. 本地智能提示 / 补全支持

* 即使在容器运行环境中，你仍希望本地 IDE 有补全提示 → 在 `.vscode/settings.json` 添加：

  ```json
  {
    "python.analysis.extraPaths": [
      "/home/you/.local/lib/python3.10/site-packages"
    ],
    "python.analysis.autoImportCompletions": true,
    "python.analysis.useLibraryCodeForTypes": true
  }
  ```
* （可选）在本地 Python 环境中安装 `quantconnect-stubs` 或直接引用 site-packages 的 `.pyi`，以获得完整补全。

---

## 7. 回测与调试

* 运行本地回测：

  ```bash
  lean backtest "MyProject"
  ```

  * CLI 会构建容器、挂载代码与数据、执行回测；
  * 输出结果（包括日志、chart、回测 JSON）保存在 `MyProject/backtests/<timestamp>/`。
* 结果分析：

  * 可在 VSCode 中查看生成的 `.json` / `.html`；
  * 或 `lean show-backtest "MyProject"` 打开交互式图表。

---

## 8. （可选）Remote Container 模式

* 若你希望**直接在容器内开发**（非仅执行），可在项目根创建 `.devcontainer/`：

  ```bash
  lean configure-docker
  # 或手动生成 devcontainer.json，挂载 data、source
  ```
* VSCode → “Reopen in Container”，即可在容器内进行全功能开发、补全、调试。

---

## 9. 常见问题定位思路

1. **Python Kernel 不显示** → 手动输入 Jupyter URL
2. **无数据返回** → 检查本地 Data 结构及 `config.json` 中的 `data-folder`
3. **无法补全 / 跳转** → 确认 `extraPaths` 已指向正确 site-packages
4. **容器频繁重启导致状态丢失** → 使用本地挂载（代码、Data、Output）

---

## 10. 目录结构最终效果（示例）

```
MyProject/
├── Algorithm.Python/
│   └── MyAlgorithm.py
├── Data/
│   └── future/
├── .vscode/
│   └── settings.json
├── config.json
├── backtests/
│   └── 20251023_120000/
└── notebooks/
    └── Research.ipynb
```

---
