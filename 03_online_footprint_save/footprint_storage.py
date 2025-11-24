from AlgorithmImports import *

import json
import os
from datetime import datetime
from typing import Dict, Iterable, List, Set

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from datetime import timedelta
from datetime import date


DATA_ROOT_DEFAULT = "/LeanCLI/footprint_data"


def get_symbol_dir(symbol: object, data_root: str = DATA_ROOT_DEFAULT) -> str:
    return os.path.join(data_root, _sanitize_symbol(symbol))


def get_year_file_path(symbol: object, year: int, data_root: str = DATA_ROOT_DEFAULT) -> str:
    return os.path.join(get_symbol_dir(symbol, data_root), f"{int(year)}.parquet")


def get_metadata_path(symbol: object, year: int, data_root: str = DATA_ROOT_DEFAULT) -> str:
    return os.path.join(get_symbol_dir(symbol, data_root), f"{int(year)}_meta.json")


def _ensure_dirs(path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)


def _symbol_to_string(symbol: object) -> str:
    # Prefer QC Symbol.value if present
    if hasattr(symbol, "value"):
        s = getattr(symbol, "value")
    else:
        s = str(symbol)
    return str(s)


def _sanitize_symbol(symbol: object) -> str:
    s = _symbol_to_string(symbol)
    # Remove leading "/" and any "/" characters to avoid nested dirs
    if s.startswith("/"):
        s = s[1:]
    s = s.replace("/", "")
    return s


def read_metadata(symbol: object, year: int, data_root: str = DATA_ROOT_DEFAULT) -> Dict:
    meta_path = get_metadata_path(symbol, year, data_root)
    if not os.path.exists(meta_path):
        return {}
    with open(meta_path, "r", encoding="utf-8") as f:
        return json.load(f)


def write_metadata(
    symbol: object,
    year: int,
    v_unit: int,
    tick_size: float,
    df_year: pd.DataFrame,
    data_root: str = DATA_ROOT_DEFAULT,
    no_data_dates: Iterable[int] | None = None,
) -> None:
    meta_path = get_metadata_path(symbol, year, data_root)
    _ensure_dirs(meta_path)

    sym_str = _sanitize_symbol(symbol)
    no_data_set = set(int(x) for x in (no_data_dates or []))

    # Load existing to preserve prior no_data_dates
    existing = {}
    if os.path.exists(meta_path):
        try:
            with open(meta_path, "r", encoding="utf-8") as f:
                existing = json.load(f)
        except Exception:
            existing = {}

    if df_year is None or df_year.empty:
        meta = {
            "symbol": sym_str,
            "year": int(year),
            "v_unit": int(v_unit),
            "tick_size": float(tick_size),
            "dates_present": [],
            "bar_count_by_date": {},
            "no_data_dates": sorted(list(set(int(x) for x in existing.get("no_data_dates", [])) | no_data_set)),
            "last_updated": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "schema_version": 1,
        }
    else:
        g = df_year.groupby("trade_date")
        bar_counts = {int(k): int(v) for k, v in g.size().to_dict().items()}
        dates_present = sorted([int(x) for x in bar_counts.keys()])
        meta = {
            "symbol": sym_str,
            "year": int(year),
            "v_unit": int(v_unit),
            "tick_size": float(tick_size),
            "dates_present": dates_present,
            "bar_count_by_date": bar_counts,
            "no_data_dates": sorted(list(set(int(x) for x in existing.get("no_data_dates", [])) | no_data_set)),
            "last_updated": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "schema_version": 1,
        }

    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)


def read_present_dates(symbol: object, year: int, data_root: str = DATA_ROOT_DEFAULT) -> Set[int]:
    meta = read_metadata(symbol, year, data_root)
    if meta and "dates_present" in meta:
        return set(int(x) for x in meta["dates_present"])
    year_path = get_year_file_path(symbol, year, data_root)
    if not os.path.exists(year_path):
        return set()
    try:
        pf = pq.ParquetFile(year_path)
        col = pf.read(columns=["trade_date"]).column(0).to_numpy()
        return set(int(x) for x in np.unique(col))
    except Exception:
        # fallback: load via pandas
        try:
            df = pd.read_parquet(year_path, engine="pyarrow", columns=["trade_date"])
            return set(int(x) for x in df["trade_date"].unique().tolist())
        except Exception:
            return set()


def detect_missing_dates(
    symbol: object,
    year: int,
    target_dates: Iterable[int],
    force_recompute: bool,
    data_root: str = DATA_ROOT_DEFAULT,
) -> Set[int]:
    target_set = set(int(d) for d in target_dates)
    if force_recompute:
        return target_set
    present = read_present_dates(symbol, year, data_root)
    meta = read_metadata(symbol, year, data_root)
    no_data = set(int(x) for x in meta.get("no_data_dates", [])) if meta else set()
    # 缺口 = 目标 - 已有 - 无数据日
    return target_set - present - no_data


def _parquet_schema() -> pa.schema:
    return pa.schema([
        ("trade_date", pa.int32()),
        ("start_time", pa.timestamp("ns")),
        ("end_time", pa.timestamp("ns")),
        ("open_i", pa.int32()),
        ("high_i", pa.int32()),
        ("low_i", pa.int32()),
        ("close_i", pa.int32()),
        ("total_volume", pa.int64()),
        ("buy_volume", pa.int64()),
        ("sell_volume", pa.int64()),
        ("prices_i", pa.list_(pa.int32())),
        ("vol_buy", pa.list_(pa.int32())),
        ("vol_sell", pa.list_(pa.int32())),
    ])


def _df_to_table(df: pd.DataFrame) -> pa.Table:
    # Ensure column order and types
    cols = [
        "trade_date", "start_time", "end_time",
        "open_i", "high_i", "low_i", "close_i",
        "total_volume", "buy_volume", "sell_volume",
        "prices_i", "vol_buy", "vol_sell",
    ]
    df2 = df[cols]
    # Convert to Arrow with explicit schema for list columns
    return pa.Table.from_pydict(
        {
            "trade_date": df2["trade_date"].astype("int32").to_list(),
            "start_time": df2["start_time"].to_list(),
            "end_time": df2["end_time"].to_list(),
            "open_i": df2["open_i"].astype("int32").to_list(),
            "high_i": df2["high_i"].astype("int32").to_list(),
            "low_i": df2["low_i"].astype("int32").to_list(),
            "close_i": df2["close_i"].astype("int32").to_list(),
            "total_volume": df2["total_volume"].astype("int64").to_list(),
            "buy_volume": df2["buy_volume"].astype("int64").to_list(),
            "sell_volume": df2["sell_volume"].astype("int64").to_list(),
            "prices_i": df2["prices_i"].to_list(),
            "vol_buy": df2["vol_buy"].to_list(),
            "vol_sell": df2["vol_sell"].to_list(),
        },
        schema=_parquet_schema(),
    )


def _write_year_by_day_rowgroups(path_tmp: str, df_year: pd.DataFrame) -> None:
    """Write a full year parquet ensuring each 'trade_date' is its own row group, sorted by date then start_time."""
    if df_year is None or df_year.empty:
        # Write empty file with schema
        _ensure_dirs(path_tmp)
        with pq.ParquetWriter(path_tmp, _parquet_schema(), compression="snappy") as writer:
            pass
        return
    df_sorted = df_year.sort_values(by=["trade_date", "start_time"]).reset_index(drop=True)
    _ensure_dirs(path_tmp)
    writer = pq.ParquetWriter(path_tmp, _parquet_schema(), compression="snappy")
    try:
        for td, df_day in df_sorted.groupby("trade_date"):
            table = _df_to_table(df_day)
            writer.write_table(table)
    finally:
        writer.close()


def append_days(
    symbol: object,
    v_unit: int,
    year: int,
    df_list_by_date: List[pd.DataFrame],
    tick_size: float,
    force_recompute_dates: Iterable[int] = (),
    data_root: str = DATA_ROOT_DEFAULT,
) -> None:
    """
    将“多日”的 V-bar 结果写入该年度文件：
      - 读取旧文件（若存在）
      - 移除被覆盖日（force_recompute_dates）
      - 合并新增日
      - 以“日”为row group按顺序重写到临时文件，再原子替换
      - 更新元数据
    """
    year_path = get_year_file_path(symbol, year, data_root)
    tmp_path = year_path + ".tmp"
    _ensure_dirs(year_path)

    # Load existing
    if os.path.exists(year_path):
        try:
            df_existing = pd.read_parquet(year_path, engine="pyarrow")
        except Exception:
            df_existing = pd.DataFrame()
    else:
        df_existing = pd.DataFrame()

    # Concatenate new daily data
    df_new = pd.concat([df for df in df_list_by_date if df is not None and not df.empty], axis=0, ignore_index=True) \
        if df_list_by_date else pd.DataFrame()

    # Filter existing by removing force dates
    if df_existing is not None and not df_existing.empty and force_recompute_dates:
        force_set = set(int(x) for x in force_recompute_dates)
        df_existing = df_existing[~df_existing["trade_date"].isin(list(force_set))]

    # Merge
    if df_existing is not None and not df_existing.empty and df_new is not None and not df_new.empty:
        df_year = pd.concat([df_existing, df_new], axis=0, ignore_index=True)
    elif df_existing is not None and not df_existing.empty:
        df_year = df_existing
    elif df_new is not None and not df_new.empty:
        df_year = df_new
    else:
        df_year = pd.DataFrame(columns=[
            "trade_date", "start_time", "end_time",
            "open_i", "high_i", "low_i", "close_i",
            "total_volume", "buy_volume", "sell_volume",
            "prices_i", "vol_buy", "vol_sell",
        ])

    # Rewrite by day row groups
    _write_year_by_day_rowgroups(tmp_path, df_year)

    # Atomic replace
    os.replace(tmp_path, year_path)

    # Update metadata
    write_metadata(symbol=symbol, year=year, v_unit=v_unit, tick_size=tick_size, df_year=df_year, data_root=data_root)


def append_no_data_dates(
    symbol: object,
    year: int,
    no_data_dates: Iterable[int],
    v_unit: int,
    tick_size: float,
    data_root: str = DATA_ROOT_DEFAULT,
) -> None:
    """
    将无数据日写入元数据（不改动 Parquet 文件）。
    """
    # Load existing df if exists to pass to write_metadata for bar counts
    year_path = get_year_file_path(symbol, year, data_root)
    if os.path.exists(year_path):
        try:
            df_existing = pd.read_parquet(year_path, engine="pyarrow")
        except Exception:
            df_existing = pd.DataFrame()
    else:
        df_existing = pd.DataFrame()
    write_metadata(
        symbol=symbol,
        year=year,
        v_unit=v_unit,
        tick_size=tick_size,
        df_year=df_existing,
        data_root=data_root,
        no_data_dates=no_data_dates,
    )

from footprint_bar import FootprintBar

def _df_to_footprint_bars(df: pd.DataFrame, symbol: object, tick_size: float) -> List[FootprintBar]:
    """Helper to convert a DataFrame to a list of FootprintBar objects."""
    
    def _as_np_array(obj, dtype) -> np.ndarray:
        if obj is None:
            return np.empty(0, dtype=dtype)
        if isinstance(obj, np.ndarray):
            return obj.astype(dtype, copy=False)
        try:
            return np.asarray(obj, dtype=dtype)
        except (TypeError, ValueError):
            return np.empty(0, dtype=dtype)

    bars: List[FootprintBar] = []
    for r in df.itertuples(index=False):
        start_time_py = pd.to_datetime(r.start_time).to_pydatetime()
        end_time_py = pd.to_datetime(r.end_time).to_pydatetime()
        period = (end_time_py - start_time_py) if (end_time_py is not None and start_time_py is not None) else timedelta(seconds=0)

        fp = FootprintBar(symbol, period, tick_size)
        fp.reset(start_time_py)
        
        fp.trade_date = int(r.trade_date)
        fp.open_i = int(r.open_i)
        fp.high_i = int(r.high_i)
        fp.low_i = int(r.low_i)
        fp.close_i = int(r.close_i)
        
        fp.volume = int(r.total_volume)
        fp.total_volume = fp.volume
        fp.buy_volume = int(r.buy_volume)
        fp.sell_volume = int(r.sell_volume)
        fp.delta = fp.buy_volume - fp.sell_volume

        prices_i = _as_np_array(r.prices_i, np.int32)
        vol_buy = _as_np_array(r.vol_buy, np.int32)
        vol_sell = _as_np_array(r.vol_sell, np.int32)
        fp.set_ladder(prices_i, vol_buy, vol_sell)
        
        fp.finalize(end_time_py)
        bars.append(fp)
    
    bars.sort(key=lambda x: x.time)
    return bars

def read_day_as_footprint_bars(
    symbol: object,
    year: int,
    trade_date: int,
    data_root: str = DATA_ROOT_DEFAULT,
    tick_size: float | None = None,
) -> List[object]:
    """
    读取指定交易日的数据并重构为 FootprintBar 对象列表（使用现有 footprint_bar.FootprintBar）。
    - 使用年度 Parquet 行（整数 tick、整数成交量、列表列）重建对象字段
    - 如未显式提供 tick_size，则从 metadata 读取
    - period 使用 end_time - start_time（每根 V-bar 的覆盖时间）
    """
    year_path = get_year_file_path(symbol, year, data_root)
    if not os.path.exists(year_path):
        return []
    cols = [
        "trade_date", "start_time", "end_time",
        "open_i", "high_i", "low_i", "close_i",
        "total_volume", "buy_volume", "sell_volume",
        "prices_i", "vol_buy", "vol_sell",
    ]
    df_year = pd.read_parquet(year_path, engine="pyarrow", columns=cols)
    df_day = df_year[df_year["trade_date"] == int(trade_date)]
    if df_day.empty:
        return []

    # 获取 tick_size
    if tick_size is None:
        meta = read_metadata(symbol, year, data_root)
        if not meta or "tick_size" not in meta:
            raise ValueError("tick_size not provided and not found in metadata")
        tick_size = float(meta["tick_size"])

    return _df_to_footprint_bars(df_day, symbol, tick_size)


def read_range_as_footprint_bars(
    symbol: object,
    start_date: date,
    end_date: date,
    data_root: str = DATA_ROOT_DEFAULT,
    tick_size: float | None = None
) -> List[FootprintBar]:
    """
    高效读取一个日期区间内的所有 Footprint 数据，并返回一个 FootprintBar 对象列表。
    - 按年份分组，每个年份只读一次文件。
    - 使用 PyArrow 的 filters 功能在读取时过滤日期，避免加载整个文件。
    - 一次性将所有数据转换为对象。
    """
    all_dates = pd.date_range(start_date, end_date, freq='D')
    if all_dates.empty:
        return []

    dates_by_year = {
        year: [d.year * 10000 + d.month * 100 + d.day for d in dates_in_year]
        for year, dates_in_year in pd.Series(all_dates).groupby(all_dates.year)
    }

    all_dfs = []

    for year, dates_int in dates_by_year.items():
        year_path = get_year_file_path(symbol, year, data_root)
        if not os.path.exists(year_path):
            continue
        
        try:
            table = pq.read_table(
                year_path,
                filters=[('trade_date', 'in', dates_int)],
                use_pandas_metadata=True
            )
            if table.num_rows > 0:
                all_dfs.append(table.to_pandas())
        except Exception as e:
            # 文件损坏或 filter 失败时可以打印日志
            print(f"Could not read {year_path} for dates {dates_int}: {e}")
            continue
    
    if not all_dfs:
        return []

    df_range = pd.concat(all_dfs, ignore_index=True)

    # 获取 tick_size (如果未提供)
    if tick_size is None:
        first_year = sorted(dates_by_year.keys())[0]
        meta = read_metadata(symbol, first_year, data_root)
        if not meta or "tick_size" not in meta:
            raise ValueError(f"tick_size not provided and not found in metadata for year {first_year}")
        tick_size = float(meta["tick_size"])

    return _df_to_footprint_bars(df_range, symbol, tick_size)
