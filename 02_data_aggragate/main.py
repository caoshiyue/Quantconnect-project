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
