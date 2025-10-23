# README — 本地使用 Lean（开源）+ Python 的实战笔记与排错指南

> 目的：把我们讨论过的所有问题、分析、Lean 运行逻辑、以及可复现的解决方案整理成一份单页 README，便于你下次遇到类似问题时快速查阅并恢复工作流。
> 适用对象：在 Linux（非 Docker / 或 配合 Docker）环境下，用本地编译的 Lean 引擎运行 Python 算法，并在 VSCode 做开发（希望有跳转/补全/调试体验）。

---

# 目录

1. 高层概念回顾：Lean 的运行模型
2. 常见错误 & 根因与解决（按你遇到过的顺序）
3. 在本机编译并运行 Lean（关键命令）
4. 在本地/容器运行 Python 算法的两种正确方式
5. 数据（Futures）组织与 Lean 的查找规则（如何放数据）
6. VSCode 开发体验：自动补全 / 跳转 / 调试 的实战配置（不进入容器也能用）
7. 容器内开发提示（Research kernel、site-packages、挂载）
8. 典型问题快速排查清单
9. 常用命令集（可复制使用）

---

# 1. 高层概念回顾：Lean 的运行模型

* **Lean 的主进程是 .NET（C#）引擎**：`QuantConnect.Lean.Launcher.dll`。
* **Python 支持的方式**：**C# 主引擎托管 Python runtime**（通过 pythonnet），即 *C# 调用 Python*，Python 脚本作为算法插件被加载。

  * 这意味着：你不能直接 `python my_algo.py` 来运行 Lean（除非使用非常规 hack）。正确方式是由 Lean Launcher (`dotnet QuantConnect.Lean.Launcher.dll`) 启动并嵌入 Python。
* Jupyter/Research：Lean CLI（通常在 Docker 中）会运行一个专门适配的 kernel（.NET 托管的 Python 内核），交互式 cell 的执行也是由 .NET 引擎通过 pythonnet 调度的。
* 下面是尝试通过编译lean，进入kernel开发 等一些列尝试，最终放弃此方案，选择Lean CLI.
---

# 2. 常见错误、根因与解决（总结） 

## 错误 A：`ModuleNotFoundError: No module named 'clr'`

**根因**：没有安装 `pythonnet`（或版本不对）。
**解决**：

```bash
pip install pythonnet
# 或者推荐的 .NET Core 支持版本：
pip uninstall pythonnet -y
pip install pythonnet==3.0.3
```

并确保 `.NET SDK`/runtime 可用（参见下面）。

---

## 错误 B：`UserWarning: Hosting Mono versions before v6.12...`（或 mono 版本过低）

**根因**：在 Linux 上 `pythonnet` 默认可能尝试使用 Mono，如果 Mono 版本低会有不稳定或崩溃风险。
**解决**：

* 推荐替代：**不要依赖 Mono 运行 .NET 6/7/9 的 Lean DLL**，而用 pythonnet 3.x 的 coreclr 模式（即托管 .NET Core/.NET 9）。
* 或者：若使用 Mono，务必升级到 ≥6.12（但 .NET 9 编译的 DLL 不一定能用 Mono）。

---

## 错误 C：`Could not load the file 'QuantConnect.Common'`（FileNotFoundException）

**根因**：缺少 Lean 的 C# 编译产物（DLL），或 Python 环境找不到 DLL 路径。
**解决**：

1. 从 Lean 源码编译（见第 3 节）生成 DLL。
2. 确认 Python 中 `sys.path` 或在代码前加入 DLL 路径：

```python
import sys, os, clr
sys.path.append("/path/to/Lean/Launcher/bin/Release/net7.0")
clr.AddReference("QuantConnect.Common")
```

---

## 错误 D：`Can't find custom attr constructor image...` / `TypeLoadException`（来自 Mono）

**根因**：尝试在 Mono 上加载针对 .NET Core/.NET 6/7/9 编译的程序集（不兼容）。
**解决**：

* 不要用 Mono 来加载 .NET 9 的 DLL。改用 .NET runtime + pythonnet coreclr 支持（pythonnet >= 3.0），或将 Lean 编译目标改为兼容 Mono（通常不可行/不推荐）。

---

## 错误 E：`<module 'clr' from 'unknown'>` + 仍然报 dll 类加载或属性找不到

**根因**：pythonnet 成功导入，但运行时托管层（Mono vs CoreCLR）不对导致后续类型解析失败。
**解决**：使用 `pythonnet` 的 coreclr 模式：

```python
from pythonnet import load
load("coreclr")  # 强制使用 .NET Core/Runtime 而非 Mono
import clr
```

注意需要 pythonnet >= 3.0 且系统有对应的 .NET runtime（dotnet 7/9）。

---

# 3. 在本机编译并运行 Lean（关键步骤）

> 假定你使用 Ubuntu 22.04+。你已确认可以用 `dotnet` 成功运行 Lean Launcher 示例。

1. 安装 .NET SDK（如果未安装）：

```bash
# 示例（Ubuntu 22.04 - dotnet 7）
wget https://packages.microsoft.com/config/ubuntu/22.04/packages-microsoft-prod.deb -O packages-microsoft-prod.deb
sudo dpkg -i packages-microsoft-prod.deb
sudo apt update
sudo apt install -y dotnet-sdk-7.0
dotnet --version
```

2. 克隆并编译 Lean（示例目录 `~/Lean`）：

```bash
git clone https://github.com/QuantConnect/Lean.git ~/Lean
cd ~/Lean/Launcher
# Release 或 Debug，取决你要的路径
dotnet build -c Release
# 编译后 DLL 在:
# ~/Lean/Launcher/bin/Release/net7.0/
```

3. 运行一个 C# 回测示例来验证：

```bash
cd ~/Lean/Launcher/bin/Release/net7.0
dotnet QuantConnect.Lean.Launcher.dll
```

若能跑通 C# 回测说明 .NET 环境和数据目录配置正确。

---

# 4. 在本地/容器运行 Python 算法的两种正确方式

## A. 官方/推荐（Lean Launcher 托管 Python）

* 创建或激活用于 Research 的 conda 环境（与 Lean CLI 推荐一致），设置 `PYTHONNET_PYDLL` 指向 `libpythonX.Y.so`：

```bash
# 举例（路径示例）
export PYTHONNET_PYDLL="/home/you/miniconda3/envs/qc_lean/lib/libpython3.11.so"
# 可写入 /etc/environment 永久生效
```

* 在 `config.json` 中指定：

```json
"algorithm-language": "Python",
"algorithm-location": "../../../Algorithm.Python/YourAlgo.py",
"data-folder": "/home/you/Lean/Data"
```

* 启动：`dotnet QuantConnect.Lean.Launcher.dll`
  **要点**：C# 引擎会通过 pythonnet 内嵌 Python runtime，然后加载你的 Python 脚本（`Initialize`, `OnData` 等），这时 `self.History(...)` 等 API 都能正常工作。

## B. Docker + Lean CLI（research/backtest）

* Lean CLI 启动容器，容器里已包含合适的 .NET runtime + Python 环境 + pythonnet 设置 + Jupyter kernel。
* 使用 `lean research` 或 `lean backtest` 来运行。
  **要点**：容器提供统一环境，适合不想逐一解决兼容问题时使用。

---

# 5. 数据（Futures）组织与 Lean 的查找规则（如何让 Lean 读取你下载的数据）

Lean 按严格目录/命名规则查找数据。以期货为例：

```
<Data root>/future/<market>/<resolution>/<symbol>/*.zip
```

* 示例路径（CL/NYMEX, minute）：

```
Lean/Data/future/nymerc/minute/cl/20131008_trade.zip
```

* zip 内 CSV 命名：

```
YYYYMMDD_symbol_resolution_tickType_symbolExpirationDate.csv
# 例如：20131008_cl_minute_trade_201311.csv
```

* Hour/Daily zip 命名：`symbol_tickType.zip`（单 entry csv）
* Tick zip 命名：`YYYYMMDD_tickType.zip`（内部多个 tick csv）

### 关键点

* 若你 `AddFuture("CL", Resolution.Minute, Market.CME)`，Lean 会查找 `.../future/cme/minute/cl/` 下的 zip 文件。
* **你必须同时提供 metadata：map_files / symbol-properties / contract metadata**（否则 `AddFuture` 只能返回“主链”而不知道子合约，导致 `history` 无数据）。
* 推荐用 Lean CLI / 官方工具下载数据与元数据，或确保手工放好 `map_files` 与 `symbol-properties`。

---

# 6. VSCode 开发体验（自动补全 / 跳转 / 调试）——**不进入容器也能实现**

## 核心问题回顾

* `AlgorithmImports.py` 在项目目录通常是一个小 wrapper（只是 `clr.AddReference()`），它会屏蔽 site-packages 中带 `.pyi` 的 stub。
* 当 VSCode 在 Lean 项目打开时会**优先索引项目内 module**，因此会忽略系统 `AlgorithmImports` 的 `.pyi`，导致跳转失效。

## 终极解决（你已验证并使用成功）

1. 在本地 Python 环境中安装 stub：

```bash
pip install quantconnect-stubs
# 或 pip install quantconnect (如果有官方 stub 包)
```

2. 在项目根创建 `.vscode/settings.json`（示例，已基于你确认的路径）：

```json
{
  "python.analysis.extraPaths": [
    "/data1/shiyue.cao/miniconda3/envs/quant/lib/python3.10/site-packages"
  ],
  "python.analysis.autoImportCompletions": true,
  "python.analysis.useLibraryCodeForTypes": true,
  "python.analysis.diagnosticMode": "workspace",
  "python.analysis.stubPath": "/data1/shiyue.cao/miniconda3/envs/quant/lib/python3.10/site-packages"
}
```

3. （可选）替代策略：将项目内 `AlgorithmImports.py` 重命名或用软链接指向 site-packages 的 pyi，以避免本地文件屏蔽系统 stub：

```bash
# 备份项目内文件
mv Algorithm.Python/AlgorithmImports.py Algorithm.Python/AlgorithmImports.local.py
# 建软链（让 import 走到 site-packages 的 pyi）
ln -s /data1/shiyue.cao/miniconda3/envs/quant/lib/python3.10/site-packages/AlgorithmImports/__init__.py Algorithm.Python/AlgorithmImports.py
```

4. 重启 VSCode Language Server（命令面板 → Python: Restart Language Server）。

现在你应当能在本地打开 Lean 项目，获得：

* `Ctrl+Click` 跳转到 `.pyi`（stub）
* 参数提示、自动补全、类型提示
* 即使容器经常重启也不会影响你的本地开发体验（运行时再用容器或 Launcher）。

## 远程容器（可选更强方案）

* 使用 **VSCode Remote - Containers** 直接附着到正在运行的 Lean 容器，这样 VSCode 的 LSP 直接在容器内运行，路径一致，跳转/补全/断点最稳定（不过容器频繁重启会影响开发状态）。
* 能的话，把上面的 `extraPaths` 也配置到容器内 `.vscode/settings.json`，进一步保证一致性。

---

# 7. 容器内开发提示（Research kernel、site-packages、挂载）

* Lean CLI 的 `lean research` 会把 host `~/Lean/Data` 自动挂载到容器 `/Lean/Data`（你注意到的行为）。这很方便用于数据测试。
* 容器内的 Jupyter kernel 经常是 **一个 QuantConnect 定制的 kernel**（不是普通 ipykernel），其 Python 运行环境已由 Lean 调整（包含 pythonnet 设置、stubs、特殊模块）。
* 如果你在 VSCode 的 notebook 中选择 kernel 时只看到 C# kernel，但容器外能看到 Python kernel，可能是 VSCode 未正确连接到容器内的 Jupyter server。解决办法是直接：

  * 使用 `Jupyter: Enter the URL of the running Jupyter server` 并粘贴容器内 notebook 的 URL；或
  * 用 Remote Container 把 VSCode 直接附着到容器。

---

# 8. 典型问题快速排查清单（遇到了就按顺序跑）

1. `ModuleNotFoundError: clr` → `pip install pythonnet`（prefer `pythonnet==3.0.3` for coreclr）
2. Mono 警告 / DotNet 不兼容 → 用 `pythonnet` coreclr 模式并确保系统有 `dotnet` runtime（不要用 Mono 来加载 .NET 9+ DLL）
3. `Could not load QuantConnect.Common` → 确保你已编译 Lean 并把 DLL 目录加到 `sys.path` 或在 Launcher 模式运行。
4. `Can't find custom attr constructor...` → 说明在 Mono 下加载 net7.0 程序集，切换到 coreclr 模式或使用 .NET runtime 托管。
5. `qb.history()` 没数据（尤其 future） → 检查数据目录 + map_files + symbol-properties（合约 chain 元数据）是否齐全。
6. VSCode 跳转失效 → 检查是否项目中有同名模块覆盖了 site-packages；设置 `python.analysis.extraPaths` 指向 site-packages 或安装 stubs。
7. Notebook kernel 只有 C#（或仅有 C# 显示） → 确认容器内 Jupyter server 是否注册了 Python kernel；或使用 Jupyter URL 手动连接。

---

# 9. 常用命令集（可复制）

## 安装 / 编译 / 运行（摘要）

```bash
# 安装 dotnet 7+ (示例)
wget https://packages.microsoft.com/config/ubuntu/22.04/packages-microsoft-prod.deb -O packages-microsoft-prod.deb
sudo dpkg -i packages-microsoft-prod.deb
sudo apt update
sudo apt install -y dotnet-sdk-7.0

# 克隆并编译 Lean
git clone https://github.com/QuantConnect/Lean.git ~/Lean
cd ~/Lean/Launcher
dotnet build -c Release

# 运行 Launcher（在构建输出目录）
cd ~/Lean/Launcher/bin/Release/net7.0
dotnet QuantConnect.Lean.Launcher.dll

# pythonnet (coreclr 支持)
pip uninstall pythonnet -y
pip install pythonnet==3.0.3

# 在 Python 中显式 load coreclr
python - <<'PY'
from pythonnet import load
load("coreclr")
import clr, sys
sys.path.append("/home/you/Lean/Launcher/bin/Release/net7.0")
clr.AddReference("QuantConnect.Common")
print("Loaded")
PY
```

## VSCode settings.json（示例）

```json
{
  "python.analysis.extraPaths": [
    "/data1/shiyue.cao/miniconda3/envs/quant/lib/python3.10/site-packages"
  ],
  "python.analysis.autoImportCompletions": true,
  "python.analysis.useLibraryCodeForTypes": true,
  "python.analysis.diagnosticMode": "workspace",
  "python.analysis.stubPath": "/data1/shiyue.cao/miniconda3/envs/quant/lib/python3.10/site-packages"
}
```

## 软链示例（避免本地模块覆盖 site-packages）

```bash
cd /path/to/Lean/Algorithm.Python
mv AlgorithmImports.py AlgorithmImports.local.py
ln -s /data1/shiyue.cao/miniconda3/envs/quant/lib/python3.10/site-packages/AlgorithmImports/__init__.py AlgorithmImports.py
```

## 检查 futures 数据目录（示例）

```bash
# 假设 data-folder = /home/you/Lean/Data
ls /home/you/Lean/Data/future/cme/minute/cl

```

---

# 结语 / 备忘

* Lean 的 Python 体验与普通纯 Python 项目有本质差异：**Python 只是作为算法语言运行在 .NET 引擎里**。理解“C#（主进程）→ pythonnet → Python 脚本”这个链条，是处理大部分兼容/运行问题的关键。
* 开发体验（跳转/补全/断点）可以与生产运行解耦：**本地安装 stub / 指定 extraPaths** 能让你在不进入容器的前提下拥有几乎完整的 IDE 体验。
* 运行回测或使用 `History()`/数据服务时，务必使用 Lean Launcher（或容器内的 Lean）来保证 .NET + Python 的运行时契合。

---
