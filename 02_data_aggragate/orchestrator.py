from datetime import datetime, timedelta, date
from typing import Dict, List, Tuple
from AlgorithmImports import *

import pandas as pd

from footprint_aggregator import build_v_footprints
from footprint_storage import (
    append_days,
    detect_missing_dates,
    get_year_file_path,
    read_present_dates,
    DATA_ROOT_DEFAULT,
)


def _daterange_days(start_date: date, end_date: date) -> List[date]:
    days: List[date] = []
    d = start_date
    one = timedelta(days=1)
    while d <= end_date:
        days.append(d)
        d = d + one
    return days


def _yyyymmdd(d: date) -> int:
    return d.year * 10000 + d.month * 100 + d.day


def _normalize_history_df(df_history: pd.DataFrame, sym) -> pd.DataFrame:
    """
    Normalize qb.history result to a plain per-second DataFrame with a DatetimeIndex named 'time'.
    Keeps all columns as-is for subsequent renaming by aggregator.
    """
    if df_history is None or df_history.empty:
        return pd.DataFrame()
    df = df_history
    # If MultiIndex with 'time' and possibly 'symbol', collapse to single index by selecting the symbol if present
    if isinstance(df.index, pd.MultiIndex):
        names = df.index.names
        if "symbol" in names:
            try:
                df = df.xs(sym, level="symbol")
            except Exception:
                pass
        if "time" in names:
            df = df.reset_index().set_index("time")
        else:
            df = df.reset_index()
            if "time" in df.columns:
                df = df.set_index("time")
    else:
        # ensure DatetimeIndex, otherwise create from column 'time'
        if not isinstance(df.index, pd.DatetimeIndex):
            if "time" in df.columns:
                df["time"] = pd.to_datetime(df["time"])
                df = df.set_index("time")
    df.index = pd.to_datetime(df.index)
    df = df.sort_index()
    return df


def run(
    qb,
    symbol: object,
    start_date: date,
    end_date: date,
    v_unit: int,
    tick_size: float,
    *,
    force_recompute: bool = False,
    data_root: str = DATA_ROOT_DEFAULT,
) -> None:
    """
    顶层调度：
      - 按日从 history 请求秒级 RAW
      - 聚合为 V-bar footprint
      - 按年写入（同一年内可批量多日追加），仅在“日”完成后写入，不做逐bar追加
      - 支持覆盖模式
    说明：
      - 时间与时区：完全采用 history 返回的时间，不做任何转换
      - 无并发
    """

    days = _daterange_days(start_date, end_date)
    if not days:
        return

    # 预先基于元数据检测缺失日期（每年）
    years = sorted(set(d.year for d in days))
    year_to_target_dates: Dict[int, List[int]] = {y: [] for y in years}
    for d in days:
        year_to_target_dates[d.year].append(_yyyymmdd(d))

    year_to_missing: Dict[int, List[int]] = {}
    for y in years:
        missing = detect_missing_dates(
            symbol=symbol,
            year=y,
            target_dates=year_to_target_dates[y],
            force_recompute=force_recompute,
            data_root=data_root,
        )
        if missing:
            year_to_missing[y] = sorted(list(missing))

    # 如果没有缺口且不是强制覆盖，直接返回
    if not year_to_missing:
        return

    # 收集每年待写入的日结果
    year_to_day_frames: Dict[int, List[pd.DataFrame]] = {y: [] for y in years}

    for d in days:
        y = d.year
        td = _yyyymmdd(d)
        # 若该年该日不是缺口且不覆盖，跳过
        if not force_recompute and (y not in year_to_missing or td not in year_to_missing[y]):
            continue

        start_dt = datetime(d.year, d.month, d.day, 0, 0, 0)
        end_dt = start_dt + timedelta(days=1)
        df_hist = qb.history(symbol, start_dt, end_dt, 
                        resolution=Resolution.SECOND,
                        extended_market_hours=True,
                        data_mapping_mode=DataMappingMode.OPEN_INTEREST_ANNUAL, # 数据映射模式，这个会根据交易量切换到当年后续更大的合约，Warning, 但正确性有待验证
                        data_normalization_mode=DataNormalizationMode.RAW, # 数据连续模式，ATAS是RAW, tradingview 是BACKWARDS_RATIO，能够使得连续。注意，实盘需要使用当期合约数据
                        fill_forward=True
                        )

        df_norm = _normalize_history_df(df_hist, symbol)
        if df_norm.empty:
            # 无数据日：记录到元数据，后续缺口检测跳过
            from footprint_storage import append_no_data_dates
            append_no_data_dates(
                symbol=symbol,
                year=y,
                no_data_dates=[td],
                v_unit=v_unit,
                tick_size=tick_size,
                data_root=data_root
            )
            continue
        #注意，这里，history请求的当日数据的末尾可能已经到了00:00：00，这是下一天的数据，一般来说没有数据，但以防万一，我们把这一帧的交易删掉。
        mask_non_first_date = df_norm.index.date != start_dt.date()
        df_norm.loc[mask_non_first_date, 'volume'] = 0.0

        df_v = build_v_footprints(df_norm, v_unit=v_unit, tick_size=tick_size)
        if df_v is None or df_v.empty:
            continue
        year_to_day_frames[y].append(df_v)
        print(f"{start_dt} finished")

    # 按年批量写入
    for y in years:
        frames = [df for df in year_to_day_frames.get(y, []) if df is not None and not df.empty]
        if not frames:
            continue
        # 覆盖日期集合（仅这些日期从旧文件中剔除）
        force_dates = year_to_missing.get(y, []) if force_recompute else year_to_missing.get(y, [])
        append_days(
            symbol=symbol,
            v_unit=v_unit,
            year=y,
            df_list_by_date=frames,
            tick_size=tick_size,
            force_recompute_dates=force_dates,
            data_root=data_root,
        )


# endregion

# Your New Python File
