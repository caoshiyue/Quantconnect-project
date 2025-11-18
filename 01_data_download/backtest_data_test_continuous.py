from AlgorithmImports import *
from QuantConnect import Resolution, DataMappingMode, DataNormalizationMode
from QuantConnect.Data.Market import TradeBar
from datetime import timedelta

#此代码测试了 GC合约在backtest 中，合约切换日期附近的 数据连续逻辑
class SpecificGCTest(QCAlgorithm):

    def Initialize(self):
        self.SetStartDate(2024, 11, 25)
        self.SetEndDate(2024, 12, 10)
        self.SetCash(100000)

        # K 线周期设置 (10 分钟)
        self.kline_period = timedelta(minutes=10) 
        
        # 用于存储所有要绘图的合约及其配置
        self.contracts_to_plot = {} 
        
        # --- 1. 添加并配置 GCZ24 (具体合约) ---
        self.add_and_setup_contract_specific("GCZ24", "GCZ24 Candlestick Chart", "GCZ24 Volume")

        # --- 2. 添加并配置 GCG25 (具体合约) ---
        self.add_and_setup_contract_specific("GCG25", "GCG25 Candlestick Chart", "GCG25 Volume")
        
        # --- 3. 添加并配置 连续GC合约 ---
        self.add_and_setup_continuous_contract(
            Futures.Metals.GOLD, 
            "Continuous GC Candlestick Chart", 
            "Continuous GC Volume"
        )

    def add_and_setup_contract_specific(self, symbol_string: str, candle_chart_name: str, volume_chart_name: str):
        """
        添加一个具体的期货合约，设置图表，并注册数据合并器（使用 self.Consolidate）
        """
        
        # 1. 解析和添加合约
        future_symbol = SymbolRepresentation.parse_future_symbol(symbol_string)
        future = self.AddFutureContract(
            future_symbol, 
            Resolution.Minute,
            extendedMarketHours = True
        )
        symbol = future.Symbol
        series_name = symbol.ID.Symbol
        
        # 2. 注册图表 (K线和成交量)
        self._register_charts(candle_chart_name, volume_chart_name, series_name)

        # 3. 存储配置
        self.contracts_to_plot[symbol] = {
            "candle_chart": candle_chart_name,
            "volume_chart": volume_chart_name,
            "series_name": series_name
        }

        # 4. 设置数据合并器
        # 对于具体的合约，使用标准的 self.Consolidate
        self.Consolidate(symbol, self.kline_period, self.on_consolidated_bar)

    def add_and_setup_continuous_contract(self, continuous_root: str, candle_chart_name: str, volume_chart_name: str):
        """
        添加连续期货合约，设置图表，并注册数据合并器（使用 SubscriptionManager）
        """
        # 1. 添加连续合约，并配置数据映射和调整
        future = self.AddFuture(
            continuous_root,
            Resolution.Minute,
            dataMappingMode = DataMappingMode.OPEN_INTEREST_ANNUAL,
            dataNormalizationMode = DataNormalizationMode.BackwardsRatio, 
            extendedMarketHours = True,
            contractDepthOffset = 0
        )
        continuous_symbol = future.Symbol
        series_name = continuous_symbol.Value # 例如: "/GC"

        # 2. 注册图表 (K线和成交量)
        self._register_charts(candle_chart_name, volume_chart_name, series_name)
        
        # 3. 存储配置
        self.contracts_to_plot[continuous_symbol] = {
            "candle_chart": candle_chart_name,
            "volume_chart": volume_chart_name,
            "series_name": series_name
        }

        # 4. 设置数据合并器
        # 对于连续合约，必须使用 SubscriptionManager 来注册
        # consolidator = TradeBarConsolidator(self.kline_period)
        # consolidator.DataConsolidated += self.on_consolidated_bar 
        self.Consolidate(continuous_symbol, self.kline_period, self.on_consolidated_bar)

    def _register_charts(self, candle_chart_name: str, volume_chart_name: str, series_name: str):
        """
        辅助函数：注册 K 线图和成交量图表
        """
        # 注册 K 线图表
        candle_chart = Chart(candle_chart_name)
        candle_chart.add_series(CandlestickSeries(series_name, "$")) 
        self.AddChart(candle_chart)

        # 注册成交量图表
        volume_chart = Chart(volume_chart_name)
        volume_chart.add_series(Series("Volume", SeriesType.BAR, "", Color.from_argb(128, 128, 128)))
        self.AddChart(volume_chart)

    def OnData(self, data: Slice) -> None:
        pass
    
    def on_consolidated_bar(self, bar: TradeBar) -> None:
        """
        统一处理所有合约（具体合约和连续合约）的 consolidated bar
        """
        if bar is None:
            return

        # 根据 bar.Symbol 查找对应的绘图配置
        if bar.Symbol in self.contracts_to_plot:
            config = self.contracts_to_plot[bar.Symbol]
            
            # 绘制 K 线
            self.Plot(config["candle_chart"], config["series_name"], bar)

            # 绘制成交量
            self.Plot(config["volume_chart"], "Volume", float(bar.Volume))
