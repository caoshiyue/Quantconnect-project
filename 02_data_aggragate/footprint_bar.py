from AlgorithmImports import *
from typing import Dict, Optional
from datetime import datetime, timedelta
import numpy as np

class FootprintBar(TradeBar):
    """精简版 FootprintBar：继承 TradeBar，内部用整数tick存储，属性映射为浮点价格；footprint 明细使用 numpy。
    - 仅持久化整数价 open_i/high_i/low_i/close_i；浮点 open/high/low/close 通过 tick_size 映射
    - volume 等于总成交量，同时保留 total_volume 以兼容旧逻辑
    - footprint 明细以 numpy 数组承载：prices_i_np, vol_buy_np, vol_sell_np（均为 int32）
    - 提供兼容的 volume_at_price 字典视图（懒构造）
    """
    def __init__(self, symbol: Symbol, period: timedelta, tick_size: float):
        super().__init__()
        self.symbol = symbol
        self.period = period
        self.time = datetime.min
        self.end_time = datetime.min
        self.data_type = MarketDataType.TradeBar
        self.is_fill_forward = False
        self.tick_size = tick_size or 0.0
        
        # 整数tick OHLC
        self.open_i: int = 0
        self.high_i: int = 0
        self.low_i: int = 0
        self.close_i: int = 0

        # 成交量
        self.volume = 0.0
        self.total_volume = 0.0  # 兼容旧字段名
        self.buy_volume = 0.0
        self.sell_volume = 0.0
        self.delta = 0.0

        # 交易日 YYYYMMDD
        self.trade_date: Optional[int] = None

        # footprint 明细（numpy）
        self.prices_i_np: np.ndarray = np.empty(0, dtype=np.int32)
        self.vol_buy_np: np.ndarray = np.empty(0, dtype=np.int32)
        self.vol_sell_np: np.ndarray = np.empty(0, dtype=np.int32)

        # 懒加载字典缓存
        self._vap_cache: Optional[Dict[float, Dict[str, float]]] = None

    def reset(self, start_time: datetime) -> None:
        self.time = start_time
        self.end_time = start_time
        self.volume = 0.0
        self.total_volume = 0.0
        self.buy_volume = 0.0
        self.sell_volume = 0.0
        self.delta = 0.0
        self._vap_cache = None

    def finalize(self, end_time: datetime) -> None:
        self.end_time = end_time

    # 映射属性：整数tick <-> 浮点价格
    @property
    def open(self) -> float:
        return float(self.open_i) * float(self.tick_size)

    @open.setter
    def open(self, v: float) -> None:
        self.open_i = int(round(float(v) / float(self.tick_size))) if self.tick_size else int(round(float(v)))

    @property
    def high(self) -> float:
        return float(self.high_i) * float(self.tick_size)

    @high.setter
    def high(self, v: float) -> None:
        self.high_i = int(round(float(v) / float(self.tick_size))) if self.tick_size else int(round(float(v)))

    @property
    def low(self) -> float:
        return float(self.low_i) * float(self.tick_size)

    @low.setter
    def low(self, v: float) -> None:
        self.low_i = int(round(float(v) / float(self.tick_size))) if self.tick_size else int(round(float(v)))

    @property
    def close(self) -> float:
        return float(self.close_i) * float(self.tick_size)

    @close.setter
    def close(self, v: float) -> None:
        self.close_i = int(round(float(v) / float(self.tick_size))) if self.tick_size else int(round(float(v)))

    @property
    def value(self) -> float:
        return self.close

    @value.setter
    def value(self, v: float) -> None:
        self.close = v

    @property
    def price(self) -> float:
        return self.close

    @price.setter
    def price(self, v: float) -> None:
        self.close = v

    # footprint 明细
    def set_ladder(self, prices_i: np.ndarray, vol_buy: np.ndarray, vol_sell: np.ndarray) -> None:
        self.prices_i_np = np.asarray(prices_i, dtype=np.int32)
        self.vol_buy_np = np.asarray(vol_buy, dtype=np.int32)
        self.vol_sell_np = np.asarray(vol_sell, dtype=np.int32)
        self._vap_cache = None

    @property
    def volume_at_price(self) -> Dict[float, Dict[str, float]]:
        """兼容旧逻辑的字典视图；策略端建议直接用 numpy 数组 attributes。"""
        if self._vap_cache is not None:
            return self._vap_cache
        vap: Dict[float, Dict[str, float]] = {}
        if self.prices_i_np.size > 0:
            prices = (self.prices_i_np.astype(np.float64) * float(self.tick_size)).tolist()
            vb = self.vol_buy_np.astype(np.int64).tolist()
            vs = self.vol_sell_np.astype(np.int64).tolist()
            for i, p in enumerate(prices):
                vap[p] = {"bid": float(vs[i] if i < len(vs) else 0), "ask": float(vb[i] if i < len(vb) else 0)}
        self._vap_cache = vap
        return self._vap_cache

    def to_string(self) -> str:
        """
        Returns a string representation of the session bar with OHLCV and OpenInterest values formatted.
        Example: "O: 101.00 H: 112.00 L: 95.00 C: 110.00 V: 1005.00 OI: 12"
        """
        return (f"O: {self.open:.2f} H: {self.high:.2f} L: {self.low:.2f} C: {self.close:.2f} "
                f"V: {self.volume:.2f} ")
    def __str__(self) -> str:
        # __str__ is used by print() and string conversions
        return self.to_string()
