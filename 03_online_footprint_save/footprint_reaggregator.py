# region imports
from AlgorithmImports import *
# endregion
from typing import Iterator, List, Iterable
from datetime import date, timedelta
import numpy as np

from footprint_bar import FootprintBar
from footprint_storage import read_day_as_footprint_bars, DATA_ROOT_DEFAULT

def _merge_ladders(bars_to_merge: List[FootprintBar]) -> (np.ndarray, np.ndarray, np.ndarray):
    """使用 numpy 高效合并多个 footprint bar 的价阶。"""
    if not bars_to_merge:
        return np.empty(0, dtype=np.int32), np.empty(0, dtype=np.int32), np.empty(0, dtype=np.int32)

    # 拼接所有子 bar 的 numpy 数组
    all_prices_i = np.concatenate([b.prices_i_np for b in bars_to_merge])
    all_vol_buy = np.concatenate([b.vol_buy_np for b in bars_to_merge])
    all_vol_sell = np.concatenate([b.vol_sell_np for b in bars_to_merge])

    # 找到唯一的 tick 并加总成交量
    unique_prices, inverse_indices = np.unique(all_prices_i, return_inverse=True)
    
    merged_vol_buy = np.zeros(unique_prices.shape, dtype=np.int32)
    np.add.at(merged_vol_buy, inverse_indices, all_vol_buy)

    merged_vol_sell = np.zeros(unique_prices.shape, dtype=np.int32)
    np.add.at(merged_vol_sell, inverse_indices, all_vol_sell)

    return unique_prices.astype(np.int32), merged_vol_buy, merged_vol_sell

def aggregate_vbars(
    vbars_iter: Iterator[FootprintBar],
    target_v: int,
    keep_partial_tail: bool = True
) -> Iterator[FootprintBar]:
    """
    从 FootprintBar 迭代器中读取 bar，并按更大的成交量目标（target_v）进行二次聚合。
    这是一个生成器，逐个产出聚合后的 FootprintBar。
    """
    buffer: List[FootprintBar] = []
    accumulated_volume = 0.0
    first_bar_in_group: FootprintBar = None

    for bar in vbars_iter:
        if not buffer:
            first_bar_in_group = bar
        
        buffer.append(bar)
        accumulated_volume += bar.volume

        if accumulated_volume >= target_v:
            last_bar_in_group = buffer[-1]
            new_period = last_bar_in_group.end_time - first_bar_in_group.time
            
            agg_bar = FootprintBar(first_bar_in_group.symbol, new_period, first_bar_in_group.tick_size)
            agg_bar.time = first_bar_in_group.time
            agg_bar.trade_date = first_bar_in_group.trade_date
            
            agg_bar.open_i = first_bar_in_group.open_i
            agg_bar.close_i = last_bar_in_group.close_i
            agg_bar.high_i = max(b.high_i for b in buffer)
            agg_bar.low_i = min(b.low_i for b in buffer)
            
            agg_bar.volume = sum(b.volume for b in buffer)
            agg_bar.buy_volume = sum(b.buy_volume for b in buffer)
            agg_bar.sell_volume = sum(b.sell_volume for b in buffer)
            agg_bar.delta = agg_bar.buy_volume - agg_bar.sell_volume
            agg_bar.total_volume = agg_bar.volume

            prices, buys, sells = _merge_ladders(buffer)
            agg_bar.set_ladder(prices, buys, sells)
            agg_bar.finalize(last_bar_in_group.end_time)
            
            yield agg_bar

            buffer.clear()
            accumulated_volume = 0.0
            first_bar_in_group = None
    
    if buffer and keep_partial_tail:
        last_bar_in_group = buffer[-1]
        new_period = last_bar_in_group.end_time - first_bar_in_group.time

        agg_bar = FootprintBar(first_bar_in_group.symbol, new_period, first_bar_in_group.tick_size)
        agg_bar.time = first_bar_in_group.time
        agg_bar.trade_date = first_bar_in_group.trade_date
        
        agg_bar.open_i = first_bar_in_group.open_i
        agg_bar.close_i = last_bar_in_group.close_i
        agg_bar.high_i = max(b.high_i for b in buffer)
        agg_bar.low_i = min(b.low_i for b in buffer)
        
        agg_bar.volume = sum(b.volume for b in buffer)
        agg_bar.buy_volume = sum(b.buy_volume for b in buffer)
        agg_bar.sell_volume = sum(b.sell_volume for b in buffer)
        agg_bar.delta = agg_bar.buy_volume - agg_bar.sell_volume
        agg_bar.total_volume = agg_bar.volume

        prices, buys, sells = _merge_ladders(buffer)
        agg_bar.set_ladder(prices, buys, sells)
        agg_bar.finalize(last_bar_in_group.end_time)
        
        yield agg_bar

def _daterange_days(start_date: date, end_date: date) -> List[date]:
    days: List[date] = []
    d = start_date
    one = timedelta(days=1)
    while d <= end_date:
        days.append(d)
        d = d + one
    return days

def read_and_aggregate_range(
    symbol: object,
    start_date: date,
    end_date: date,
    target_v: int,
    data_root: str = DATA_ROOT_DEFAULT,
    keep_partial_tail: bool = True
) -> Iterator[FootprintBar]:
    """便利接口：读取并二次聚合一个日期区间的数据，按日流式产出聚合后的 bar。"""
    all_days = _daterange_days(start_date, end_date)
    for day in all_days:
        year = day.year
        trade_date_int = day.year * 10000 + day.month * 100 + day.day
        
        base_bars = read_day_as_footprint_bars(symbol, year, trade_date_int, data_root=data_root)
        if not base_bars:
            continue
            
        yield from aggregate_vbars(iter(base_bars), target_v, keep_partial_tail)