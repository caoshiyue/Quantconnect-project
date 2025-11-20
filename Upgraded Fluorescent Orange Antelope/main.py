# strategy_test_nq_realtime_latency.py

from AlgorithmImports import *
from datetime import timedelta

class RealtimeLatencyTest(QCAlgorithm):
    
    # 定义延迟阈值，用于判断是否延迟过大
    MAX_ACCEPTABLE_DELAY = timedelta(seconds=2)
    
    def initialize(self) -> None:
        # 1. 设置开始日期为今天 (当前日期)。
        # 当不设置 start_date 时，QC 默认为 '今日'，但在大多数回测环境中，
        # 我们需要一个明确的日期范围。这里我们使用当前时间作为锚点。
        
        # 使用当前日期，将回测窗口限制在 10 分钟，以确保快速结束并测试延迟。
        # 注意：在真实的 QuantConnect 云环境中，'今日'通常会被映射到最新的可用数据日。

        start_date = datetime(2025, 11, 19, 0, 0, 0)
        end_date = datetime(2025, 11, 20, 0, 10, 0)
        self.set_start_date(start_date)
        self.set_end_date(end_date)
        self.set_cash(100000)
        
        # 2. 订阅测试标的：纳斯达克100 E-mini 期货 (NQ)
        self.nq_future = self.add_future(
            Futures.Indices.NASDAQ_100_E_MINI, 
            resolution=Resolution.MINUTE,
            extended_market_hours=True,
            data_mapping_mode=DataMappingMode.OPEN_INTEREST_ANNUAL, # 数据映射模式，这个会根据交易量切换到当年后续更大的合约，Warning, 但正确性有待验证
            data_normalization_mode=DataNormalizationMode.RAW, # 数据连续模式，ATAS是RAW, tradingview 是BACKWARDS_RATIO，能够使得连续。注意，实盘需要使用当期合约数据
            fill_forward=True
        ).symbol

        self.last_history_test_time = datetime.min # 用于控制测试频率
        self.test_interval = timedelta(seconds=15) # 每 15 秒测试一次 History 延迟
        self.history_window = timedelta(seconds=60) # 每次请求过去 10 秒数据
        self.test_count = 0
        self.delays: List[timedelta] = []

        self.debug(f"Algorithm initialized. Start: {self.start_date}. End: {self.end_date}")
        self.debug(f"Testing NQ Future with Resolution.MINUTE. History Window: {self.history_window.total_seconds()}s.")

    def on_data(self, data: Slice) -> None:
        """每收到一个秒级数据柱就执行一次"""
        
        # 仅在 NQ 合约有数据时继续
        if self.nq_future not in data:
            return

        current_time = self.time

        
        # 控制 History 测试频率，避免过于频繁的 History 调用
        if current_time - self.last_history_test_time < self.test_interval:
            return

        self.last_history_test_time = current_time
        self.test_count += 1
        
        # ----------------------------------------------------------------------
        # A. 执行 History 请求：获取当前时间点之前 10 秒的数据
        # ----------------------------------------------------------------------
        
        start_time = self.time - self.history_window
        end_time_target = current_time 
        
        history_data = self.history(
            self.nq_future, 
            start_time, 
            end_time_target, 
            resolution=Resolution.SECOND,
            extended_market_hours=True,
            data_mapping_mode=DataMappingMode.OPEN_INTEREST_ANNUAL, # 数据映射模式，这个会根据交易量切换到当年后续更大的合约，Warning, 但正确性有待验证
            data_normalization_mode=DataNormalizationMode.RAW, # 数据连续模式，ATAS是RAW, tradingview 是BACKWARDS_RATIO，能够使得连续。注意，实盘需要使用当期合约数据
            fill_forward=True
        )
        
        # ----------------------------------------------------------------------
        # B. 分析结果
        # ----------------------------------------------------------------------
        
        # 1. 获取最晚的数据时间戳 (T_Last)
        # 修正方法：使用 history_data.index[-1] 来获取最后一个 MultiIndex 元组
        # 然后从该元组的第二个元素 (索引 1) 中提取 datetime 对象。
        
        if len(history_data)==0:
            self.debug("history_data len == 0  ")
            return
        # 获取最后一个 MultiIndex 元组，格式通常是 (Symbol, datetime)
        last_index_tuple = history_data.index[-1] 
        
        # 提取元组中的时间 (索引 1)
        last_data_time = last_index_tuple[2]
        
        # **重要验证：确保 last_data_time 是 datetime 类型**
        if not isinstance(last_data_time, datetime):
            self.error(f"Time extraction failed. Expected datetime, got {type(last_data_time)}")
            return
        
        # 2. 计算延迟：当前算法时间 - 最晚数据时间 (T_Algo - T_Last)
        delay: timedelta = current_time - last_data_time # <--- 现在可以安全地执行减法
        self.delays.append(delay)
        
        # ----------------------------------------------------------------------
        # C. 打印实时日志
        # ----------------------------------------------------------------------
        
        log_msg = (
            f"[{self.test_count}] @ {current_time.strftime('%Y-%m-%d %H:%M:%S')}: "
            f"T_Last={last_data_time.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]} | " # 截断微秒
            f"Delay={delay.total_seconds():.3f}s"
        )
        
        if delay > self.MAX_ACCEPTABLE_DELAY:
            self.error(f"HIGH LATENCY ALERT: {log_msg}")
        else:
            self.debug(log_msg)

    def on_end_of_algorithm(self) -> None:
        """回测结束时输出统计摘要"""
        
        self.debug("--- REALTIME LATENCY TEST SUMMARY ---")
        
        if not self.delays:
            self.debug("No valid latency tests were performed.")
            return

        # 计算统计数据
        total_seconds = [d.total_seconds() for d in self.delays]
        
        avg_delay = timedelta(seconds=sum(total_seconds) / len(total_seconds))
        max_delay = timedelta(seconds=max(total_seconds))
        min_delay = timedelta(seconds=min(total_seconds))
        
        self.debug(f"Total Tests: {len(self.delays)}")
        self.debug(f"Average Delay (T_Algo - T_Last): {avg_delay.total_seconds():.3f} seconds")
        self.debug(f"Maximum Delay Observed: {max_delay.total_seconds():.3f} seconds")
        self.debug(f"Minimum Delay Observed: {min_delay.total_seconds():.3f} seconds")
        
        if max_delay > self.MAX_ACCEPTABLE_DELAY:
            self.debug(f"Conclusion: Maximum observed delay ({max_delay.total_seconds():.3f}s) exceeded the {self.MAX_ACCEPTABLE_DELAY.total_seconds()}s threshold.")
        else:
            self.debug("Conclusion: Latency was generally within acceptable limits.")
