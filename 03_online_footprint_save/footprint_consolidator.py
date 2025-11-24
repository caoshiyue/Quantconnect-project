from AlgorithmImports import *
from typing import Dict, List
from datetime import datetime, timedelta
from footprint_bar import FootprintBar
from footprint_field_mapping import HISTORY_DF_FIELD_MAP
import pandas as pd
from footprint_utils import micro_allocate_volume_raw


def create_footprints_from_history(df_history: pd.DataFrame, period: timedelta, tick_size: float) -> List[FootprintBar]:
    """Process static historical data (from qb.History) into a list of FootprintBars using a df-native path.
    """
    if df_history.empty:
        return []
    
    # Prepare the DataFrame
    df_temp = df_history.reset_index()
    df_temp['time'] = pd.to_datetime(df_temp['time'])
    df = df_temp.set_index('time').sort_index()
    
    # Rename columns using our standardized mapping
    df = df.rename(columns=HISTORY_DF_FIELD_MAP)
    
    # Ensure required columns are present (strict *_close policy)
    required_cols = list(HISTORY_DF_FIELD_MAP.values())
    if not all(col in df.columns for col in required_cols):
        return []
    
    df_filtered = df[required_cols].dropna()

    # infer symbol from df_history MultiIndex if present
    symbol = None
    try:
        symbol = df_history.index.get_level_values('symbol')[0]
    except Exception:
        pass
    
    footprint_bars: List[FootprintBar] = []
    current_fp: FootprintBar = None
    current_end: datetime = None

    # Local aggregators for OHLC to avoid per-second QuoteBar/TradeBar creation
    trade_open = None
    trade_high = None
    trade_low = None
    trade_close = None

    bid_open = None
    bid_high = None
    bid_low = None
    bid_close = None

    ask_open = None
    ask_high = None
    ask_low = None
    ask_close = None

    def align_period_end(t: datetime) -> datetime:
        day_start = datetime(t.year, t.month, t.day, tzinfo=t.tzinfo)
        elapsed = int((t - day_start).total_seconds())
        span = int(period.total_seconds())
        k = int(elapsed // span) + 1
        return day_start + timedelta(seconds=k * span)

    def finalize_current():
        nonlocal current_fp, trade_open, trade_high, trade_low, trade_close
        nonlocal bid_open, bid_high, bid_low, bid_close
        nonlocal ask_open, ask_high, ask_low, ask_close
        if current_fp is None:
            return
        # set trade OHLC
        current_fp._trade_open = trade_open
        current_fp._trade_high = trade_high
        current_fp._trade_low = trade_low
        current_fp._trade_close = trade_close
        # set bid/ask Bars if available
        def make_bar(o,h,l,c):
            if o is None or h is None or l is None or c is None:
                return None
            b = Bar()
            b.open = o; b.high = h; b.low = l; b.close = c
            return b
        current_fp.bid = make_bar(bid_open, bid_high, bid_low, bid_close)
        current_fp.ask = make_bar(ask_open, ask_high, ask_low, ask_close)

    for row in df_filtered.itertuples():
        ts: datetime = row.Index
        sec_end = ts + timedelta(seconds=1)

        # Read all fields (strict *_close)
        t_o, t_h, t_l, t_c, vol = row.trade_open, row.trade_high, row.trade_low, row.trade_close, row.trade_volume
        b_o, b_h, b_l, b_c = row.bid_open, row.bid_high, row.bid_low, row.bid_close
        a_o, a_h, a_l, a_c = row.ask_open, row.ask_high, row.ask_low, row.ask_close

        if current_fp is None:
            current_end = align_period_end(sec_end)
            start_time = current_end - period
            # symbol fallback
            fp_symbol = symbol if symbol is not None else Symbol.Empty
            current_fp = FootprintBar(fp_symbol, period, tick_size)
            current_fp.reset(start_time)

            # init aggregators
            trade_open, trade_high, trade_low, trade_close = t_o, t_h, t_l, t_c
            bid_open, bid_high, bid_low, bid_close = b_o, b_h, b_l, b_c
            ask_open, ask_high, ask_low, ask_close = a_o, a_h, a_l, a_c
        
        # roll period if needed
        if sec_end >= current_end:
            # finalize and emit
            current_fp.finalize(current_end)
            finalize_current()
            footprint_bars.append(current_fp)
            # start new bar
            current_end = align_period_end(sec_end)
            start_time = current_end - period
            fp_symbol = symbol if symbol is not None else Symbol.Empty
            current_fp = FootprintBar(fp_symbol, period, tick_size)
            current_fp.reset(start_time)
            # reset aggregators for new bar
            trade_open, trade_high, trade_low, trade_close = t_o, t_h, t_l, t_c
            bid_open, bid_high, bid_low, bid_close = b_o, b_h, b_l, b_c
            ask_open, ask_high, ask_low, ask_close = a_o, a_h, a_l, a_c

        # micro allocation using raw scalars
        buy_v, sell_v, deltas = micro_allocate_volume_raw(
            t_o, t_h, t_l, t_c, vol,
            b_o, b_h, b_l, b_c,
            a_o, a_h, a_l, a_c,
            tick_size=tick_size,
        )

        # totals
        current_fp.total_volume += float(vol or 0.0)
        current_fp.buy_volume += buy_v
        current_fp.sell_volume += sell_v
        current_fp.delta = current_fp.buy_volume - current_fp.sell_volume

        # per price
        vap = current_fp.volume_at_price
        for price_bucket, incs in deltas.items():
            e = vap.get(price_bucket)
            if e is None:
                vap[price_bucket] = {"bid": incs.get("bid", 0.0), "ask": incs.get("ask", 0.0)}
            else:
                e["bid"] += incs.get("bid", 0.0)
                e["ask"] += incs.get("ask", 0.0)

        # update OHLC aggregators
        # trade
        if trade_high is None or t_h > trade_high:
            trade_high = t_h
        if trade_low is None or t_l < trade_low:
            trade_low = t_l
        trade_close = t_c
        # bid
        if bid_high is None or b_h > bid_high:
            bid_high = b_h
        if bid_low is None or b_l < bid_low:
            bid_low = b_l
        bid_close = b_c
        # ask
        if ask_high is None or a_h > ask_high:
            ask_high = a_h
        if ask_low is None or a_l < ask_low:
            ask_low = a_l
        ask_close = a_c

    # finalize tail
    if current_fp is not None and current_fp.total_volume > 0:
        current_fp.finalize(current_end)
        finalize_current()
        footprint_bars.append(current_fp)
    
    return footprint_bars
