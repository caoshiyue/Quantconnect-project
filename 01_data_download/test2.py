# region imports
from AlgorithmImports import *
# endregion
import clr
from pythonnet import load

# 让 pythonnet 使用 .NET Core/7 运行时
load("coreclr")

import sys
sys.path.append("/data1/shiyue.cao/quant/Lean/Launcher/bin/Debug")  # 改成你的路径

clr.AddReference("QuantConnect.Common")
clr.AddReference("QuantConnect.Algorithm")

from QuantConnect.Algorithm import QCAlgorithm
print("✅ Lean .NET 7 DLL 加载成功")
