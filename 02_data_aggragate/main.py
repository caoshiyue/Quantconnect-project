'''
Author: error: error: git config user.name & please set dead value or install git && error: git config user.email & please set dead value or install git & please set dead value or install git
Date: 2025-10-23 23:33:10
LastEditors: error: error: git config user.name & please set dead value or install git && error: git config user.email & please set dead value or install git & please set dead value or install git
LastEditTime: 2025-11-23 18:01:05
FilePath: \02_data_aggragate\main.py
Description: 这是默认设置,请设置`customMade`, 打开koroFileHeader查看配置 进行设置: https://github.com/OBKoro1/koro1FileHeader/wiki/%E9%85%8D%E7%BD%AE
'''
from datetime import timedelta, datetime
from QuantConnect.Data.Consolidators import PythonConsolidator
from QuantConnect.Data.Market import TradeBar
from AlgorithmImports import *

class FatVioletPelican(QCAlgorithm):
    def Initialize(self):
        # Project defaults
        self.SetStartDate(2021, 1, 1)
        self.SetEndDate(2022, 1, 1)
        self.SetCash(100000)
        self.set_start_date(start_date)

        self.debug(f"Algorithm initialized. Start: {self.start_date}. End: {self.end_date}")

        # Select symbols and subscribe at SECOND so we can build per-second footprints
        self._symbols = [
            self.AddEquity("SPY", Resolution.Second, extended_market_hours=False).Symbol,
            self.AddEquity("AAPL", Resolution.Second, extended_market_hours=False).Symbol
        ]


    def OnData(self, data: Slice):
        pass
