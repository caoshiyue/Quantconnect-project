'''
Author: caoshiyue caoshiyueKevin@Gmail.com
Date: 2025-11-23 10:00:24
LastEditors: caoshiyue caoshiyueKevin@Gmail.com
LastEditTime: 2025-11-23 11:02:14
FilePath: /03_online_footprint_save/main.py
Description: 这是默认设置,请设置`customMade`, 打开koroFileHeader查看配置 进行设置: https://github.com/OBKoro1/koro1FileHeader/wiki/%E9%85%8D%E7%BD%AE
'''
# region imports
from AlgorithmImports import *
# endregion

class GeekyBlackBat(QCAlgorithm):

    def initialize(self):
        self.set_start_date(2024, 5, 22)
        self.set_cash(100000)
        self.add_equity("SPY", Resolution.MINUTE)
        self.add_equity("BND", Resolution.MINUTE)
        self.add_equity("AAPL", Resolution.MINUTE)

    def on_data(self, data: Slice):
        if not self.portfolio.invested:
            self.set_holdings("SPY", 0.33)
            self.set_holdings("BND", 0.33)
            self.set_holdings("AAPL", 0.33)