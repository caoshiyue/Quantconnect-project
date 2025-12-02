
from AlgorithmImports import *
from datetime import date, timedelta
import pandas as pd
from typing import List, Dict, Optional
from itertools import groupby

# 假设 footprint_storage.py 在同一目录或PYTHONPATH中
from footprint_storage import read_range_as_footprint_bars # <--- 修改为新的函数
from footprint_bar import FootprintBar # <--- 补上缺失的导入
import os

def validate_daily_open(
    qb: QuantBook,
    symbol: Symbol,
    start_date: date,
    end_date: date,
    data_root: str = "/LeanCLI/footprint_data"
) -> List[dict]:
    """
    使用高效的批量读取方式，将每日首个 footprint bar 的开盘价与分钟历史数据进行校验。
    """
    try:
        tick_size = qb.Securities[symbol].SymbolProperties.MinimumPriceVariation
    except Exception as e:
        print(f"获取 {symbol} 的 tick size 时出错: {e}")
        return [{"date": None, "status": "Error", "message": f"无法获取 {symbol} 的 tick size。"}]

    # --- 1. 一次性获取所有分钟历史数据 ---
    minute_bars = qb.history[TradeBar](symbol, start_date, end_date + timedelta(days=1), Resolution.MINUTE,
                        extended_market_hours=True,
                        data_mapping_mode=DataMappingMode.OPEN_INTEREST_ANNUAL, 
                        data_normalization_mode=DataNormalizationMode.RAW, 
                        fill_forward=True
                        )
    
    minute_bars_list = list(minute_bars)
    if not minute_bars_list:
        print("无法获取指定日期范围内的分钟历史数据。")
        return [{"date": f"{start_date} to {end_date}", "status": "Error", "message": "没有分钟历史数据。"}]

    print(f"获取了 {len(minute_bars_list)} 个分钟 bar，正在准备校验...")

    # --- 2. 一次性读取所有 FootprintBar 数据 ---
    try:
        all_footprint_bars = read_range_as_footprint_bars(
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            data_root=data_root,
            tick_size=tick_size
        )
    except Exception as e:
        return [{"date": f"{start_date} to {end_date}", "status": "Error", "message": f"读取footprint数据时发生严重错误: {e}"}]

    # --- 3. 在内存中按天对 FootprintBar进行分组 ---
    footprints_by_date: Dict[date, List[FootprintBar]] = {
        k: list(g)
        for k, g in groupby(all_footprint_bars, key=lambda x: x.time.date())
    }
    
    print(f"获取了 {len(all_footprint_bars)} 个 footprint bars，分布在 {len(footprints_by_date)} 个交易日中。")

    validation_results = []
    days_processed = 0

    # --- 4. 按天校验 ---
    for current_date, bars_in_day_iter in groupby(minute_bars_list, key=lambda x: x.Time.date()):
        days_processed += 1
        
        # 找到当天第一个有交易量的分钟 bar
        first_minute_bar_with_volume = None
        for bar in bars_in_day_iter:
            if bar.Volume > 0:
                first_minute_bar_with_volume = bar
                break

        if not first_minute_bar_with_volume:
            # 如果当天所有分钟 bar 都没有交易量，则跳过
            continue
        
        daily_open = first_minute_bar_with_volume.Open
        
        # 从内存中查找当天的 footprint bars
        footprint_bars_for_day = footprints_by_date.get(current_date)

        if not footprint_bars_for_day:
            # 历史数据存在，但未找到 footprint bars，说明数据缺失
            validation_results.append({
                "date": current_date,
                "status": "Missing Footprint Data",
                "daily_open": daily_open,
                "footprint_open": None,
                "difference": None
            })
            continue

        # 比较第一个 footprint bar 的开盘价
        first_footprint_bar = footprint_bars_for_day[0]
        footprint_open = first_footprint_bar.open

        difference = abs(daily_open - footprint_open)
        
        # 检查差价是否在2个tick的容忍范围内
        if difference > (2 * tick_size) + 1e-9:
            validation_results.append({
                "date": current_date,
                "status": "Mismatch",
                "daily_open": daily_open,
                "daily_open_time": first_minute_bar_with_volume.Time, # 使用有交易量的 bar 的时间
                "footprint_open": footprint_open,
                "footprint_open_time": first_footprint_bar.time,
                "difference": difference,
                "tick_size": tick_size
            })

    print(f"共校验了 {days_processed} 个交易日。")
    return validation_results
