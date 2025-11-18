from AlgorithmImports import *
from typing import Dict
from datetime import datetime, timedelta
from footprint_utils import price_to_bucket, split_volume_by_side

class FootprintBar(QuoteBar):
    """FootprintBar aggregates trade/quote info over a target period.

    It inherits from QuoteBar to expose bid/ask OHLC and standard bar fields, and adds:
      - buy_volume, sell_volume, delta
      - volume_at_price: {price_bucket: {"bid": qty_at_bid, "ask": qty_at_ask}}
      - simple imbalance metrics

    Lifecycle:
      - reset(): clears accumulators and prepares a new bar
      - update_from_quotebar(q): update quote OHLC aggregation
      - update_from_tradebar(t): update trade OHLC aggregation (using QuoteBar fields for convenience)
      - update_pair(t, q): update using matched second-level trade + quote
      - finalize(end_time): set bar end time and compute derived fields
    """
    def __init__(self, symbol: Symbol, period: timedelta, tick_size: float = None):
        super().__init__()
        self.symbol = symbol
        self.period = period
        self.tick_size = tick_size or 0.0
        
        # Quote sides (Bar) are part of QuoteBar; we will progressively merge them
        self.bid = None
        self.ask = None
        
        # Accumulators
        self.buy_volume = 0.0
        self.sell_volume = 0.0
        self.delta = 0.0
        self.total_volume = 0.0
        self.volume_at_price: Dict[float, Dict[str, float]] = {}
        
        # Optional: simple imbalance over the period based on last quote close sizes if present
        self.bid_imbalance = 0.0
        self.ask_imbalance = 0.0
        
        # Track trade OHLC (we keep them on QuoteBar's own OHLC for simplicity)
        self._trade_open = None
        self._trade_high = None
        self._trade_low = None
        self._trade_close = None
        
        self.time = datetime.min
        self.end_time = datetime.min

    def reset(self, start_time: datetime) -> None:
        self.time = start_time
        self.bid = None
        self.ask = None
        self.buy_volume = 0.0
        self.sell_volume = 0.0
        self.delta = 0.0
        self.total_volume = 0.0
        self.volume_at_price.clear()
        self.bid_imbalance = 0.0
        self.ask_imbalance = 0.0
        self._trade_open = None
        self._trade_high = None
        self._trade_low = None
        self._trade_close = None

    # Expose trade-based OHLC on QuoteBar's OHLC properties for convenience
    @property
    def open(self) -> float:
        return self._trade_open if self._trade_open is not None else 0.0

    @property
    def high(self) -> float:
        return self._trade_high if self._trade_high is not None else 0.0

    @property
    def low(self) -> float:
        return self._trade_low if self._trade_low is not None else 0.0

    @property
    def close(self) -> float:
        return self._trade_close if self._trade_close is not None else 0.0

    def _merge_quote_side(self, side_bar: Bar, current: Bar) -> Bar:
        if side_bar is None:
            return current
            
        if current is None:
            current = Bar()
            current.open = side_bar.open
            current.high = side_bar.high
            current.low = side_bar.low
            current.close = side_bar.close
            return current
            
        # Update OHLC
        if getattr(current, 'open', None) is None:
            current.open = side_bar.open
            
        current.close = side_bar.close
        current.high = max(current.high, side_bar.high)
        current.low = min(current.low, side_bar.low)
        return current

    def update_from_quotebar(self, q: QuoteBar) -> None:
        if q is None:
            return
            
        # Merge bid/ask OHLC
        if getattr(q, 'bid', None) is not None:
            self.bid = self._merge_quote_side(q.bid, self.bid)
            
        if getattr(q, 'ask', None) is not None:
            self.ask = self._merge_quote_side(q.ask, self.ask)
            
        # Optional last size-based imbalance if available
        lb = float(getattr(q, 'last_bid_size', 0.0) or 0.0)
        la = float(getattr(q, 'last_ask_size', 0.0) or 0.0)
        total = lb + la
        
        if total > 0:
            self.bid_imbalance = lb / total
            self.ask_imbalance = la / total

    def update_from_tradebar(self, t: TradeBar) -> None:
        if t is None:
            return
            
        price_o = float(getattr(t, 'open', 0.0) or 0.0)
        price_h = float(getattr(t, 'high', 0.0) or 0.0)
        price_l = float(getattr(t, 'low', 0.0) or 0.0)
        price_c = float(getattr(t, 'close', 0.0) or 0.0)
        vol = float(getattr(t, 'volume', 0.0) or 0.0)
        
        # Trade OHLC aggregation
        if self._trade_open is None:
            self._trade_open = price_o
            self._trade_high = price_h
            self._trade_low = price_l
        else:
            self._trade_high = max(self._trade_high, price_h)
            self._trade_low = min(self._trade_low, price_l)
            
        self._trade_close = price_c
        self.total_volume += vol

    def update_pair(self, t: TradeBar, q: QuoteBar) -> None:
        """Update the footprint using a matched per-second TradeBar and QuoteBar."""
        self.update_from_quotebar(q)
        self.update_from_tradebar(t)

        # Split volume into buy/sell
        buy_v, sell_v = split_volume_by_side(t, q)
        self.buy_volume += buy_v
        self.sell_volume += sell_v
        self.delta = self.buy_volume - self.sell_volume

        # Distribute volume across the price range of the 1-second bar
        total_bar_volume = buy_v + sell_v
        if total_bar_volume > 0 and self.tick_size > 0:
            start_price = min(t.open, t.close)
            end_price = max(t.open, t.close)
            
            start_bucket = price_to_bucket(start_price, self.tick_size)
            end_bucket = price_to_bucket(end_price, self.tick_size)

            # Determine the number of ticks in the range
            num_ticks = int(round((end_bucket - start_bucket) / self.tick_size)) + 1
            
            if num_ticks > 0:
                buy_v_per_tick = buy_v / num_ticks
                sell_v_per_tick = sell_v / num_ticks

                # Iterate through each price bucket and distribute volume
                current_bucket_price = start_bucket
                for _ in range(num_ticks):
                    entry = self.volume_at_price.get(current_bucket_price)
                    if entry is None:
                        entry = {"bid": 0.0, "ask": 0.0}
                        self.volume_at_price[current_bucket_price] = entry
                    
                    entry["ask"] += buy_v_per_tick
                    entry["bid"] += sell_v_per_tick
                    
                    current_bucket_price += self.tick_size
            else: # If open and close are in the same bucket, attribute all to that bucket
                price_bucket = price_to_bucket(t.close, self.tick_size)
                entry = self.volume_at_price.get(price_bucket)
                if entry is None:
                    entry = {"bid": 0.0, "ask": 0.0}
                    self.volume_at_price[price_bucket] = entry
                entry["ask"] += buy_v
                entry["bid"] += sell_v

    def finalize(self, end_time: datetime) -> None:
        self.end_time = end_time

    def to_dict(self) -> Dict[str, object]:
        return {
            "symbol": str(self.symbol),
            "time": self.time,
            "end_time": self.end_time,
            "period": self.period,
            "open": self.open,
            "high": self.high,
            "low": self.low,
            "close": self.close,
            "buy_volume": self.buy_volume,
            "sell_volume": self.sell_volume,
            "delta": self.delta,
            "total_volume": self.total_volume,
            "bid_imbalance": self.bid_imbalance,
            "ask_imbalance": self.ask_imbalance,
            "levels": len(self.volume_at_price)
        }
