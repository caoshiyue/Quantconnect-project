# region imports
from AlgorithmImports import *
# endregion
from typing import Dict, List, Tuple
from datetime import datetime, timedelta, date
import numpy as np
import pandas as pd

from footprint_field_mapping import HISTORY_DF_FIELD_MAP
from footprint_utils import micro_allocate_volume_raw


def _round_series_preserve_total(values: np.ndarray, target_total: int) -> np.ndarray:
    """
    Round an array of non-negative floats to integers while preserving the sum to target_total.
    Strategy: round to nearest, then distribute the residual by largest fractional parts.
    """
    if values.size == 0:
        return values.astype(np.int64)
    rounded = np.rint(values).astype(np.int64)
    diff = int(target_total) - int(rounded.sum())
    if diff == 0:
        return rounded
    # Compute fractional parts (positive allocation if we need to add, negative if we need to subtract)
    frac = values - np.floor(values)
    if diff < 0:
        # need to subtract |diff| from elements with smallest fractional parts first (they were rounded up least justified)
        order = np.argsort(frac)  # ascending
        for idx in order:
            if diff == 0:
                break
            if rounded[idx] > 0:
                rounded[idx] -= 1
                diff += 1
    else:
        # need to add diff to elements with largest fractional parts first
        order = np.argsort(-frac)  # descending
        for idx in order:
            if diff == 0:
                break
            rounded[idx] += 1
            diff -= 1
    return rounded


def _to_tick_int(price: float, tick_size: float) -> int:
    return int(round(price / tick_size)) if tick_size and tick_size > 0 else int(round(price))


def _finalize_bar(
    start_time: datetime,
    end_time: datetime,
    trade_open: float,
    trade_high: float,
    trade_low: float,
    trade_close: float,
    total_volume_sum: float,
    buy_volume_sum: float,
    sell_volume_sum: float,
    price_bucket_to_buy_sell: Dict[int, Tuple[float, float]],
    tick_size: float,
) -> Dict[str, object]:
    """Convert accumulators into one V-bar record with integer ticks and integer volumes."""
    # OHLC ticks (integers)
    open_i = _to_tick_int(trade_open, tick_size)
    high_i = _to_tick_int(trade_high, tick_size)
    low_i = _to_tick_int(trade_low, tick_size)
    close_i = _to_tick_int(trade_close, tick_size)

    # Convert per-price float volumes to arrays ordered by price tick
    if price_bucket_to_buy_sell:
        ticks_sorted = np.array(sorted(price_bucket_to_buy_sell.keys()), dtype=np.int64)
        buy_vals = np.array([price_bucket_to_buy_sell[k][0] for k in ticks_sorted], dtype=float)
        sell_vals = np.array([price_bucket_to_buy_sell[k][1] for k in ticks_sorted], dtype=float)
    else:
        ticks_sorted = np.array([], dtype=np.int64)
        buy_vals = np.array([], dtype=float)
        sell_vals = np.array([], dtype=float)

    # Integerize totals
    total_volume_int = int(round(total_volume_sum))
    buy_volume_int = int(round(buy_volume_sum))
    sell_volume_int = int(round(sell_volume_sum))

    # Ensure non-negative
    if total_volume_int < 0:
        total_volume_int = 0
    if buy_volume_int < 0:
        buy_volume_int = 0
    if sell_volume_int < 0:
        sell_volume_int = 0

    # Integerize per-level volumes while preserving bar-level totals as much as possible
    if ticks_sorted.size > 0:
        buy_int = _round_series_preserve_total(buy_vals, buy_volume_int)
        sell_int = _round_series_preserve_total(sell_vals, sell_volume_int)
        # Clamp negatives due to rounding artifacts (rare)
        buy_int = np.maximum(buy_int, 0)
        sell_int = np.maximum(sell_int, 0)
    else:
        buy_int = np.array([], dtype=np.int64)
        sell_int = np.array([], dtype=np.int64)

    # Optionally ensure buy_int.sum() + sell_int.sum() == total_volume_int
    # If mismatch remains due to model rounding, adjust sell side first then buy side
    mismatch = total_volume_int - int(buy_int.sum() + sell_int.sum())
    if mismatch != 0 and ticks_sorted.size > 0:
        # distribute on the side with greater remaining fractional slack; here we split half-half
        target = sell_int if sell_int.sum() >= buy_int.sum() else buy_int
        step = 1 if mismatch > 0 else -1
        for i in range(abs(mismatch)):
            j = i % target.size
            if step < 0 and target[j] == 0:
                continue
            target[j] += step

    trade_date = (start_time.year * 10000 + start_time.month * 100 + start_time.day)

    return {
        "trade_date": np.int32(trade_date),
        "start_time": start_time,
        "end_time": end_time,
        "open_i": np.int32(open_i),
        "high_i": np.int32(high_i),
        "low_i": np.int32(low_i),
        "close_i": np.int32(close_i),
        "total_volume": np.int64(total_volume_int),
        "buy_volume": np.int64(int(buy_int.sum())),
        "sell_volume": np.int64(int(sell_int.sum())),
        "prices_i": ticks_sorted.astype(np.int32).tolist(),
        "vol_buy": buy_int.astype(np.int32).tolist(),
        "vol_sell": sell_int.astype(np.int32).tolist(),
    }


def build_v_footprints(
    df_second: pd.DataFrame,
    v_unit: int,
    tick_size: float,
) -> pd.DataFrame:
    """
    将当日秒级 RAW 数据聚合为按成交量单位 V 的 footprint V-bar 列表。
    约束：
      - 末尾不足 V 的尾巴保留为一根 bar
      - 使用整数 tick（round(price / tick_size)）
      - 成交量使用整数；买卖拆分与价格阶梯使用现有 micro_allocate_volume_raw
      - 时间戳保持为原始（交易所）时区的 naive datetime，不做调整
    输入 df_second 要求包含 HISTORY_DF_FIELD_MAP 对应的字段，并索引或列含时间列 'time'
    返回列：
      trade_date(int32 YYYYMMDD), start_time, end_time,
      open_i, high_i, low_i, close_i (all int32 ticks),
      total_volume(int64), buy_volume(int64), sell_volume(int64),
      prices_i(list<int32>), vol_buy(list<int32>), vol_sell(list<int32>)
    """
    if df_second is None or df_second.empty:
        return pd.DataFrame(columns=[
            "trade_date", "start_time", "end_time",
            "open_i", "high_i", "low_i", "close_i",
            "total_volume", "buy_volume", "sell_volume",
            "prices_i", "vol_buy", "vol_sell",
        ])

    # Normalize time index (避免不必要的 copy)
    if "time" in df_second.columns:
        df_second["time"] = pd.to_datetime(df_second["time"])
        df = df_second.set_index("time")
    else:
        # assume DatetimeIndex
        df = df_second
        if not isinstance(df.index, pd.DatetimeIndex):
            raise ValueError("df_second must have a DatetimeIndex or a 'time' column")
    df = df.sort_index()

    # Rename to internal names
    df = df.rename(columns=HISTORY_DF_FIELD_MAP)
    required_cols = list(HISTORY_DF_FIELD_MAP.values())
    if not all(col in df.columns for col in required_cols):
        # Strict: if any leg missing, return empty
        return pd.DataFrame(columns=[
            "trade_date", "start_time", "end_time",
            "open_i", "high_i", "low_i", "close_i",
            "total_volume", "buy_volume", "sell_volume",
            "prices_i", "vol_buy", "vol_sell",
        ])
    df = df[required_cols].dropna()
    if 'trade_volume' in df.columns:
        df = df[df['trade_volume'] > 0]
        
    if df.empty:
        return pd.DataFrame(columns=[
            "trade_date", "start_time", "end_time",
            "open_i", "high_i", "low_i", "close_i",
            "total_volume", "buy_volume", "sell_volume",
            "prices_i", "vol_buy", "vol_sell",
        ])

    v_threshold = int(v_unit)
    bars: List[Dict[str, object]] = []

    # Accumulators for current V-bar
    curr_start: datetime = None
    curr_end: datetime = None
    trade_open = None
    trade_high = None
    trade_low = None
    trade_close = None
    total_volume_sum = 0.0
    buy_volume_sum = 0.0
    sell_volume_sum = 0.0
    # bucket: tick_int -> (buy_sum, sell_sum)
    bucket_map: Dict[int, List[float]] = {}

    # 使用 itertuples 提升遍历性能
    Row = None
    for row in df.itertuples(index=True, name="Row"):
        ts = row.Index
        # per-second fields
        t_o = float(row.trade_open); t_h = float(row.trade_high)
        t_l = float(row.trade_low);  t_c = float(row.trade_close)
        vol = float(row.trade_volume or 0.0)
        b_o = float(row.bid_open);   b_h = float(row.bid_high)
        b_l = float(row.bid_low);    b_c = float(row.bid_close)
        a_o = float(row.ask_open);   a_h = float(row.ask_high)
        a_l = float(row.ask_low);    a_c = float(row.ask_close)

        if curr_start is None:
            curr_start = ts
            trade_open = t_o
            trade_high = t_h
            trade_low = t_l
            trade_close = t_c

        # micro allocation at second granularity
        buy_v, sell_v, deltas = micro_allocate_volume_raw(
            t_o, t_h, t_l, t_c, vol,
            b_o, b_h, b_l, b_c,
            a_o, a_h, a_l, a_c,
            tick_size=tick_size,
        )

        total_volume_sum += vol
        buy_volume_sum += buy_v
        sell_volume_sum += sell_v

        # accumulate per-price buckets as integer ticks
        for price_bucket, incs in deltas.items():
            tick_int = _to_tick_int(price_bucket, tick_size)
            entry = bucket_map.get(tick_int)
            if entry is None:
                bucket_map[tick_int] = [incs.get("ask", 0.0), incs.get("bid", 0.0)]
            else:
                entry[0] += incs.get("ask", 0.0)
                entry[1] += incs.get("bid", 0.0)

        # update OHLC
        if t_h > trade_high:
            trade_high = t_h
        if t_l < trade_low:
            trade_low = t_l
        trade_close = t_c
        curr_end = ts  # bar包含的最后一个秒级数据时间

        # cut if reached threshold (>= V)
        if total_volume_sum >= v_threshold:
            bar = _finalize_bar(
                start_time=curr_start,
                end_time=curr_end,
                trade_open=trade_open,
                trade_high=trade_high,
                trade_low=trade_low,
                trade_close=trade_close,
                total_volume_sum=total_volume_sum,
                buy_volume_sum=buy_volume_sum,
                sell_volume_sum=sell_volume_sum,
                price_bucket_to_buy_sell={k: (v[0], v[1]) for k, v in bucket_map.items()},
                tick_size=tick_size,
            )
            bars.append(bar)
            # reset accumulators for next bar
            curr_start = None
            curr_end = None
            trade_open = None
            trade_high = None
            trade_low = None
            trade_close = None
            total_volume_sum = 0.0
            buy_volume_sum = 0.0
            sell_volume_sum = 0.0
            bucket_map.clear()

    # tail bar if any residual
    if total_volume_sum > 0.0 and curr_start is not None:
        bar = _finalize_bar(
            start_time=curr_start,
            end_time=curr_end if curr_end is not None else curr_start,
            trade_open=trade_open,
            trade_high=trade_high,
            trade_low=trade_low,
            trade_close=trade_close,
            total_volume_sum=total_volume_sum,
            buy_volume_sum=buy_volume_sum,
            sell_volume_sum=sell_volume_sum,
            price_bucket_to_buy_sell={k: (v[0], v[1]) for k, v in bucket_map.items()},
            tick_size=tick_size,
        )
        bars.append(bar)

    if not bars:
        return pd.DataFrame(columns=[
            "trade_date", "start_time", "end_time",
            "open_i", "high_i", "low_i", "close_i",
            "total_volume", "buy_volume", "sell_volume",
            "prices_i", "vol_buy", "vol_sell",
        ])

    df_out = pd.DataFrame(bars)
    # sort by start_time to ensure deterministic order
    df_out = df_out.sort_values(by=["start_time"]).reset_index(drop=True)
    return df_out


