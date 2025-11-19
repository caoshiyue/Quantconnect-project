# strategy_test.py

from AlgorithmImports import *
from datetime import timedelta
from custom_consolidator import CustomTradeBarConsolidator

class CustomConsolidatorExample(QCAlgorithm): 
    # 定义常量用于图表名称，增强可读性
    CANDLE_CHART_NAME = 'SPY 15-Min Candle'
    VOLUME_CHART_NAME = 'SPY 15-Min Volume'
    SERIES_NAME = 'SPY_OHLC'
    
    def initialize(self) -> None:
        # Set backtest period and cash
        self.set_start_date(2024, 11, 1)
        self.set_end_date(2024, 12, 1)
        self.set_cash(100000)

        equity = self.add_equity("QQQ", Resolution.MINUTE)
        self._symbol = equity.symbol

        self._consolidator = CustomTradeBarConsolidator(timedelta(minutes=15))
        self._consolidator.data_consolidated += self.on_consolidated

        self.subscription_manager.add_consolidator(self._symbol, self._consolidator)

        # -----------------------------------------------------------------
        # 1. 修复：注册绘图系列 (使用 CandlestickSeries)
        # -----------------------------------------------------------------
        
        # 注册 K 线图表
        candle_chart = Chart(self.CANDLE_CHART_NAME)
        # 关键：使用 CandlestickSeries 来告诉 QC 这是一个 OHLC 柱状图
        candle_chart.add_series(CandlestickSeries(self.SERIES_NAME, "$")) 
        self.add_chart(candle_chart)

        # 注册成交量图表
        volume_chart = Chart(self.VOLUME_CHART_NAME)
        # 关键：Volume SeriesType 必须是 BAR
        volume_chart.add_series(Series("Volume", SeriesType.Bar, "", Color.from_argb(128, 128, 128)))
        self.add_chart(volume_chart)
        # -----------------------------------------------------------------

        self.debug("Custom consolidator registered and plot setup complete.")

    def on_consolidated(self, consolidator: PythonConsolidator, bar: TradeBar) -> None:
        """
        Event handler called each time the consolidator emits a bar.
        Adds data to the plot series using the corrected plotting logic.
        """
        if bar is None:
            return
            
        msg = (
            f"[Custom 15m] {bar.symbol} {bar.time:%Y-%m-%d %H:%M} -> {bar.end_time:%H:%M} | "
            f"O:{bar.open:.2f} H:{bar.high:.2f} L:{bar.low:.2f} C:{bar.close:.2f} V:{int(bar.volume)}"
        )
        self.debug(msg)

        # -----------------------------------------------------------------
        # 2. 修复：绘制数据 (直接传入 TradeBar)
        # -----------------------------------------------------------------
        
        # 绘制 K 线：将整个 TradeBar 对象传入 CandlestickSeries
        self.plot(self.CANDLE_CHART_NAME, self.SERIES_NAME, bar)
        
        # 绘制成交量：将成交量作为浮点数传入 Bar Series
        # 注意：这里使用 bar.time 作为时间戳，与 K 线对齐
        self.plot(self.VOLUME_CHART_NAME, "Volume", float(bar.volume))
        # -----------------------------------------------------------------

        # ... 交易逻辑保持不变 ...

    def on_end_of_algorithm(self) -> None:
        # Clean up the consolidator safely
        try:
            self._consolidator.dispose()
        except Exception:
            self.debug("Custom consolidator dispose failed, attempting base cleanup.")
            try:
                self._consolidator.reset()
            except Exception:
                pass
