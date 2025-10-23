from AlgorithmImports import *

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
from datetime import timedelta

# ------------------------------------------------------
# 1. 初始化 QuantBook, 获取 GC 期货秒级数据
# ------------------------------------------------------
qb = QuantBook()
symbol = qb.add_future(Futures.Metals.Gold, Resolution.DAILY).symbol

# 取最近一个交易日（比如过去1天）
df = qb.history(symbol, timedelta(days=100),extended_market_hours=True).reset_index()
print(f"原始数据行数: {len(df)}")
df.head()