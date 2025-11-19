from AlgorithmImports import *
from typing import Dict, List
from datetime import datetime, timedelta
from footprint_bar import FootprintBar
from footprint_field_mapping import HISTORY_DF_FIELD_MAP, STD_FIELD_TRADE_OPEN, STD_FIELD_TRADE_CLOSE, STD_FIELD_TRADE_VOLUME, STD_FIELD_BID_PRICE, STD_FIELD_ASK_PRICE
import pandas as pd

class Event:
    """Lightweight Python event container supporting '+=' and '-=' like QC consolidators."""
    def __init__(self):
        self._handlers = []

    def __iadd__(self, handler):
        self._handlers.append(handler)
        return self

    def __isub__(self, handler):
        self._handlers.remove(handler)
        return self

    def emit(self, sender, data):
        for h in list(self._handlers):
            h(sender, data)

class FootprintConsolidator:
    """Synchronize per-second TradeBar and QuoteBar streams into FootprintBars of a target period.

    Usage:
        fp = FootprintConsolidator(algorithm, period=timedelta(minutes=1), tick_size=0.01)
        fp.attach(symbol)
        fp.data_consolidated += on_footprint
    """
    @staticmethod
    def create_from_history(df_history: pd.DataFrame, period: timedelta, tick_size: float) -> List[FootprintBar]:
        """Process static historical data (from qb.History) into a list of FootprintBars."""
        if df_history.empty:
            return []
        
        # Prepare the DataFrame
        df_temp = df_history.reset_index()
        df_temp['time'] = pd.to_datetime(df_temp['time'])
        df = df_temp.set_index('time').sort_index()
        
        # Rename columns using our standardized mapping
        df = df.rename(columns=HISTORY_DF_FIELD_MAP)
        
        # Ensure required columns are present
        required_cols = list(HISTORY_DF_FIELD_MAP.values())
        if not all(col in df.columns for col in required_cols):
            return []
            
        df_filtered = df[required_cols].dropna()

        symbol = df_history.index.get_level_values('symbol')[0]
        footprint_bars = []
        current_fp = None
        current_period_end = None

        def align_period_end(t: datetime) -> datetime:
            day_start = datetime(t.year, t.month, t.day, tzinfo=t.tzinfo)
            elapsed = int((t - day_start).total_seconds())
            span = int(period.total_seconds())
            k = int(elapsed // span) + 1
            return day_start + timedelta(seconds=k * span)

        # Simple bar classes for compatibility with update_pair
        class HTradeBar:
            def __init__(self, row):
                self.open = getattr(row, STD_FIELD_TRADE_OPEN)
                self.high = getattr(row, STD_FIELD_TRADE_CLOSE) # Simplification
                self.low = getattr(row, STD_FIELD_TRADE_CLOSE) # Simplification
                self.close = getattr(row, STD_FIELD_TRADE_CLOSE)
                self.volume = getattr(row, STD_FIELD_TRADE_VOLUME)
        class HQuoteBar:
            def __init__(self, row):
                bid_price = getattr(row, STD_FIELD_BID_PRICE)
                ask_price = getattr(row, STD_FIELD_ASK_PRICE)
                bid_bar_props = {'open': bid_price, 'high': bid_price, 'low': bid_price, 'close': bid_price}
                ask_bar_props = {'open': ask_price, 'high': ask_price, 'low': ask_price, 'close': ask_price}
                self.bid = type('Bar', (), bid_bar_props)()
                self.ask = type('Bar', (), ask_bar_props)()

        for row in df_filtered.itertuples():
            timestamp = row.Index
            bar_end_time = timestamp + timedelta(seconds=1)
            
            if current_fp is None:
                current_period_end = align_period_end(bar_end_time)
                start_time = current_period_end - period
                current_fp = FootprintBar(symbol, period, tick_size)
                current_fp.reset(start_time)

            if bar_end_time >= current_period_end:
                current_fp.finalize(current_period_end)
                footprint_bars.append(current_fp)
                
                # Start new bar
                current_period_end = align_period_end(bar_end_time)
                start_time = current_period_end - period
                current_fp = FootprintBar(symbol, period, tick_size)
                current_fp.reset(start_time)

            # Update the current bar
            trade_bar = HTradeBar(row)
            quote_bar = HQuoteBar(row)
            current_fp.update_pair(trade_bar, quote_bar)
        
        # Add the last bar if it exists
        if current_fp and current_fp.total_volume > 0:
            current_fp.finalize(current_period_end)
            footprint_bars.append(current_fp)
            
        return footprint_bars

    def __init__(self, algorithm: QCAlgorithm, period: timedelta, tick_size: float = None):
        self.algorithm = algorithm
        self.period = period
        self.tick_size = tick_size or 0.0
        
        # Internal per-symbol state
        self._trade_sec_cons: Dict[Symbol, IDataConsolidator] = {}
        self._quote_sec_cons: Dict[Symbol, IDataConsolidator] = {}
        self._pending_trades: Dict[Symbol, Dict[datetime, TradeBar]] = {}
        self._pending_quotes: Dict[Symbol, Dict[datetime, QuoteBar]] = {}
        self._current_fp: Dict[Symbol, FootprintBar] = {}
        self._current_end: Dict[Symbol, datetime] = {}
        self._tick_size: Dict[Symbol, float] = {}
        
        self.data_consolidated = Event()

    def attach(self, symbol: Symbol, tick_size: float = None):
        """Create and register per-second consolidators for the symbol and start building footprint bars."""
        # Per-second pass-through consolidators (1-second)
        trade_cons = TradeBarConsolidator(timedelta(seconds=1))
        quote_cons = QuoteBarConsolidator(timedelta(seconds=1))

        trade_cons.DataConsolidated += lambda sender, bar: self._handle_tradebar(symbol, bar)
        quote_cons.DataConsolidated += lambda sender, bar: self._handle_quotebar(symbol, bar)

        self.algorithm.SubscriptionManager.AddConsolidator(symbol, trade_cons)
        self.algorithm.SubscriptionManager.AddConsolidator(symbol, quote_cons)
        
        self._trade_sec_cons[symbol] = trade_cons
        self._quote_sec_cons[symbol] = quote_cons
        self._pending_trades[symbol] = {}
        self._pending_quotes[symbol] = {}
        self._tick_size[symbol] = float(tick_size) if (tick_size is not None and tick_size > 0) else self.tick_size
        return trade_cons, quote_cons

    def _align_period_end(self, t: datetime) -> datetime:
        """Compute the inclusive end time for the current period based on incoming second end_time."""
        if t is None:
            return None
            
        day_start = datetime(t.year, t.month, t.day, tzinfo=t.tzinfo)
        elapsed = int((t - day_start).total_seconds())
        span = int(self.period.total_seconds())
        
        if span <= 0:
            span = 60
            
        k = int(elapsed // span) + 1
        return day_start + timedelta(seconds=k * span)

    def _ensure_active(self, symbol: Symbol, at_end_time: datetime) -> None:
        if symbol not in self._current_fp or self._current_fp[symbol] is None:
            curr_end = self._align_period_end(at_end_time)
            start_time = curr_end - self.period
            tick = self._tick_size.get(symbol, self.tick_size)
            fp = FootprintBar(symbol, self.period, tick)
            fp.reset(start_time)
            self._current_fp[symbol] = fp
            self._current_end[symbol] = curr_end

    def _roll_if_needed(self, symbol: Symbol, incoming_end: datetime) -> None:
        end_time = self._current_end.get(symbol)
        if end_time is None:
            return
            
        if incoming_end >= end_time:
            # finalize and emit
            fp = self._current_fp.get(symbol)
            if fp is not None:
                fp.finalize(end_time)
                self.data_consolidated.emit(self, fp)
                
            # Start a new bar anchored at end_time
            tick = self._tick_size.get(symbol, self.tick_size)
            fp_new = FootprintBar(symbol, self.period, tick)
            fp_new.reset(end_time)
            self._current_fp[symbol] = fp_new
            self._current_end[symbol] = self._align_period_end(end_time)
            
            # prune any stale unmatched second entries (older than new start)
            pend_t = self._pending_trades.get(symbol, {})
            pend_q = self._pending_quotes.get(symbol, {})
            
            to_del_t = [k for k in pend_t.keys() if k < end_time]
            to_del_q = [k for k in pend_q.keys() if k < end_time]
            
            for k in to_del_t:
                del pend_t[k]
                
            for k in to_del_q:
                del pend_q[k]

    def _try_match(self, symbol: Symbol) -> None:
        pend_t = self._pending_trades[symbol]
        pend_q = self._pending_quotes[symbol]
        
        if not pend_t or not pend_q:
            return
            
        # Match by identical end_time keys
        common_times = sorted(set(pend_t.keys()) & set(pend_q.keys()))
        
        for t in common_times:
            tradebar = pend_t.pop(t)
            quotebar = pend_q.pop(t)
            self._current_fp[symbol].update_pair(tradebar, quotebar)

    def _handle_tradebar(self, symbol: Symbol, bar: TradeBar) -> None:
        et = getattr(bar, 'end_time', getattr(bar, 'EndTime', None))
        if et is None:
            return
        
        self._ensure_active(symbol, et)
        self._pending_trades[symbol][et] = bar
        
        # consume any matches
        self._try_match(symbol)
        
        # roll if needed
        self._roll_if_needed(symbol, et)

    def _handle_quotebar(self, symbol: Symbol, bar: QuoteBar) -> None:
        et = getattr(bar, 'end_time', getattr(bar, 'EndTime', None))
        if et is None:
            return
        
        self._ensure_active(symbol, et)
        self._pending_quotes[symbol][et] = bar
        
        # consume any matches
        self._try_match(symbol)
        
        # roll if needed
        self._roll_if_needed(symbol, et)

    # Optional utility to detach if needed
    def detach(self, symbol: Symbol) -> None:
        trade_cons = self._trade_sec_cons.pop(symbol, None)
        quote_cons = self._quote_sec_cons.pop(symbol, None)
        
        if trade_cons is not None:
            self.algorithm.SubscriptionManager.RemoveConsolidator(symbol, trade_cons)
            
        if quote_cons is not None:
            self.algorithm.SubscriptionManager.RemoveConsolidator(symbol, quote_cons)
            
        self._pending_trades.pop(symbol, None)
        self._pending_quotes.pop(symbol, None)
        self._current_fp.pop(symbol, None)
        self._current_end.pop(symbol, None)
        self._tick_size.pop(symbol, None)
