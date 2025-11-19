from AlgorithmImports import *
from datetime import timedelta
from footprint_consolidator import FootprintConsolidator
from footprint_bar import FootprintBar




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

        # Select symbols and subscribe at SECOND so we can build per-second footprints
        self._symbols = [
            self.AddEquity("SPY", Resolution.Second, extended_market_hours=False).Symbol,
            self.AddEquity("AAPL", Resolution.Second, extended_market_hours=False).Symbol
        ]
        self.add_future_contract

        # Footprint settings
        self._target_period = timedelta(minutes=1)
        self._fp_con = FootprintConsolidator(
            algorithm=self,
            period=self._target_period,
            tick_size=0.0
        )
        future = self.AddFuture(
            Futures.Metals.GOLD,
            Resolution.Minute,
            dataMappingMode = DataMappingMode.OpenInterest,
            dataNormalizationMode = DataNormalizationMode.BackwardsRatio, 
            extendedMarketHours = True,
            contractDepthOffset = 0
        )
        # Subscribe to emitted footprint bars once
        self._fp_con.data_consolidated += self.on_footprint_bar

        # Small rolling window per symbol to store latest footprint bars
        self._fp_windows = {}
        for symbol in self._symbols:
            # Determine tick size per symbol
            sec = self.Securities[symbol]
            sp = getattr(sec, 'SymbolProperties', None)
            min_tick = 0.01
            if sp is not None:
                mpv = float(getattr(sp, 'MinimumPriceVariation', 0.01) or 0.01)
                if mpv > 0:
                    min_tick = mpv
            
            # Attach consolidators and store a window
            self._fp_con.attach(symbol, tick_size=min_tick)
            self._fp_windows[symbol] = RollingWindow[FootprintBar](20)

        # Optionally warm up for a brief period
        self.SetWarmUp(10, Resolution.Second)

    def OnData(self, data: Slice):
        if self.IsWarmingUp:
            return
            
        if not self.Portfolio.Invested:
            # simple buy-and-hold to drive data flow
            count = float(len(self._symbols))
            weight = 1.0 / count if count > 0 else 0.0
            for sym in self._symbols:
                self.SetHoldings(sym, weight)

    def on_footprint_bar(self, sender, fp: FootprintBar):
        """Handle finalized FootprintBar objects from the consolidator."""
        if fp is None:
            return
            
        # Store in symbol-specific rolling window
        win = self._fp_windows.get(fp.symbol)
        if win is not None:
            win.add(fp)
            
        # Light logging for verification (throttle to once per minute per symbol)
        if fp.end_time.second == 0:
            d = fp.to_dict()
            self.Debug(
                f"FP {d['symbol']} {d['end_time']}: O={d['open']:.2f} H={d['high']:.2f} L={d['low']:.2f} C={d['close']:.2f} "
                f"vol={d['total_volume']:.0f} buy={d['buy_volume']:.0f} sell={d['sell_volume']:.0f} Δ={d['delta']:.0f} lvls={d['levels']}"
            )