# region imports
from AlgorithmImports import *
# endregion

class _04onlinecontinuousalign(QCAlgorithm):

    def initialize(self):
    # 回测时间覆盖目标秒级窗口（纽约时区默认）
        self.set_start_date(2025, 10, 2)
        self.set_end_date(2025, 10, 3)
        self.set_cash(100000)

        # 订阅 SPY 秒级数据，确保可取到秒线历史
        self._symbol = self.add_future(Futures.Indices.NASDAQ_100_E_MINI, Resolution.SECOND).symbol

        # 明确到秒的时间区间（算法时区解释为纽约时区）
        start_dt = datetime(2025, 10, 1, 9, 30, 0)
        end_dt = datetime(2025, 10, 1, 18, 45, 0)

        # History 获取精确起止时间窗内的秒级 DataFrame（OHLCV 列）
        df = self.history(self._symbol, start_dt, end_dt, Resolution.SECOND,
                                extended_market_hours=True,
                        data_mapping_mode=DataMappingMode.OPEN_INTEREST_ANNUAL, 
                        data_normalization_mode=DataNormalizationMode.RAW, 
                        fill_forward=True)

        # 简要输出结果信息
        if df is None or len(df) == 0:
            self.debug("History 返回为空（可能时段无成交或订阅/时段设置不匹配）")
        else:
            idx = df.index
            times = idx.get_level_values(-1) if hasattr(idx, "nlevels") and idx.nlevels > 1 else idx
            self.debug(f"秒级行数: {len(df)}, from {times.min()} to {times.max()}")

        # 保存结果，便于在回测结果里查看
        self._df = df
        self.df = df

    def on_data(self, slice: Slice) -> None:
        pass