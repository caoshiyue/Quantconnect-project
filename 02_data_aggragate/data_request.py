# region imports
from AlgorithmImports import *
# endregion
import pandas as pd
import numpy as np
import os
import json
from datetime import datetime, timedelta
from typing import Tuple, List
from QuantConnect import *
from QuantConnect.Data.Market import *
from QuantConnect.Research import QuantBook
from datetime import datetime, timedelta

# ---------------------------
# 1) 将 tick 数据整理成“每笔交易一行”，并标注主动方向
# ---------------------------
def ticks_to_trades(ticks_df: pd.DataFrame,
                    time_col='time',
                    price_col='lastprice',
                    size_col='lastsize',   # 若原数据里列名不同请替换
                    bid_col='bidprice',
                    ask_col='askprice') -> pd.DataFrame:
    """
    输入：包含 trade 和 quote 的 ticks DataFrame（index 可能包含 expiry/symbol/time）
    输出：按时间排序的 trades DataFrame（每笔交易一行），包含判定的 'side' 列： 'buy'/'sell'/'unknown'
    """
    df = ticks_df.copy()

    # 如果时间是 index 的一部分，先把它变成列
    if isinstance(df.index, pd.MultiIndex) and 'time' in df.index.names:
        # 找到 time level 并 reset_index 保留 time 列
        df = df.reset_index()
    else:
        # 确保 time 列存在并为 datetime
        if time_col not in df.columns:
            raise ValueError("time 列找不到，请检查 ticks_df")
    # 统一列名（如果 lastprice 列是 'lastprice'）
    # 有的源并不包含 lastsize；尝试猜测
    if size_col not in df.columns:
        # 有些源叫 'size' 或 'lastsize'
        for alt in ['size', 'quantity', 'lastsize']:
            if alt in df.columns:
                size_col = alt
                break
    # 选择 trade rows：lastprice 非空
    trade_mask = df[price_col].notna()
    trades = df.loc[trade_mask, [time_col, price_col, size_col, bid_col, ask_col]].copy()
    trades = trades.sort_values(time_col).reset_index(drop=True)

    # forward fill bid/ask quotes so each trade has prevailing bid/ask (最近的 quote 之前/同时)
    trades[[bid_col, ask_col]] = trades[[bid_col, ask_col]].ffill()

    # 将 price/size 转换为 numeric（并 downcast）
    trades[price_col] = pd.to_numeric(trades[price_col], errors='coerce')
    trades[size_col] = pd.to_numeric(trades[size_col], errors='coerce').fillna(0).astype(np.int64)

    # 判定主动方向：
    # 规则：
    # 1) price >= ask -> buy
    # 2) price <= bid -> sell
    # 3) else -> tick rule: price > prev_price => buy, < => sell, == => previous side or unknown
    sides = []
    prev_price = None
    prev_side = None
    for idx, row in trades.iterrows():
        p = row[price_col]
        bid = row[bid_col]
        ask = row[ask_col]
        side = 'unknown'
        # Make sure bid/ask are numeric
        if pd.notna(ask) and p >= ask:
            side = 'buy'
        elif pd.notna(bid) and p <= bid:
            side = 'sell'
        else:
            if prev_price is None:
                side = 'unknown'
            else:
                if p > prev_price:
                    side = 'buy'
                elif p < prev_price:
                    side = 'sell'
                else:
                    # tie -> inherit previous side if exists
                    side = prev_side if prev_side is not None else 'unknown'
        sides.append(side)
        prev_price = p
        prev_side = side

    trades['side'] = sides
    trades = trades.rename(columns={time_col: 'time', price_col: 'price', size_col: 'size',
                                    bid_col: 'bid', ask_col: 'ask'})

    # 保留必要的列并返回
    return trades[['time', 'price', 'size', 'side', 'bid', 'ask']]

# ---------------------------
# 2) 构造按成交量（或按笔数）聚合的 Volume bars，并为每根 bar 收集 price-level 的主动买/卖累计
# ---------------------------
def build_volume_bars(trades: pd.DataFrame,
                      volume_per_bar: int = 100,
                      min_trades_per_bar: int = 1) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    trades: DataFrame with columns ['time','price','size','side',...], sorted by time.
    volume_per_bar: 每根 bar 的目标累计成交量（单位同 trades['size']）。
    返回: (bars_df, price_levels_df)
      - bars_df columns: ['bar_id','start_time','end_time','open','high','low','close','volume','num_trades']
      - price_levels_df columns: ['bar_id','price','buy_volume','sell_volume']
    """
    rows = []
    price_rows = []  # accumulate per-price level rows

    cur_vol = 0
    cur_prices = []  # list of (price, size, side, time)
    bar_id = 0
    start_time = None

    for idx, tr in trades.iterrows():
        p, s, side, t = tr['price'], int(tr['size']), tr['side'], tr['time']
        if start_time is None:
            start_time = t

        cur_prices.append((p, s, side, t))
        cur_vol += s

        # finish bar when cur_vol >= volume_per_bar and at least min_trades_per_bar trades
        if cur_vol >= volume_per_bar and len(cur_prices) >= min_trades_per_bar:
            # compute OHLC
            prices_list = [x[0] for x in cur_prices]
            sizes_list = [x[1] for x in cur_prices]
            times_list = [x[3] for x in cur_prices]

            open_p = prices_list[0]
            high_p = max(prices_list)
            low_p = min(prices_list)
            close_p = prices_list[-1]
            volume = sum(sizes_list)
            num_trades = len(cur_prices)
            end_time = times_list[-1]

            rows.append({
                'bar_id': bar_id,
                'start_time': start_time,
                'end_time': end_time,
                'open': open_p,
                'high': high_p,
                'low': low_p,
                'close': close_p,
                'volume': volume,
                'num_trades': num_trades
            })

            # aggregate per-price aggressive buy/sell volumes for this bar
            # use dict price -> (buy_vol, sell_vol)
            pl = {}
            for price, size, sd, _ in cur_prices:
                if price not in pl:
                    pl[price] = {'buy': 0, 'sell': 0}
                if sd == 'buy':
                    pl[price]['buy'] += size
                elif sd == 'sell':
                    pl[price]['sell'] += size
                else:
                    # unknown -> we don't count toward buy/sell (可按需更改)
                    pass

            for price, v in pl.items():
                price_rows.append({
                    'bar_id': bar_id,
                    'price': price,
                    'buy_volume': v['buy'],
                    'sell_volume': v['sell']
                })

            # reset
            bar_id += 1
            cur_vol = 0
            cur_prices = []
            start_time = None

    # 如果最后残余的交易不满一个 bar，可以选择把它作为最后一根小 bar（可选）
    if cur_prices:
        prices_list = [x[0] for x in cur_prices]
        sizes_list = [x[1] for x in cur_prices]
        times_list = [x[3] for x in cur_prices]

        open_p = prices_list[0]
        high_p = max(prices_list)
        low_p = min(prices_list)
        close_p = prices_list[-1]
        volume = sum(sizes_list)
        num_trades = len(cur_prices)
        end_time = times_list[-1]

        rows.append({
            'bar_id': bar_id,
            'start_time': start_time,
            'end_time': end_time,
            'open': open_p,
            'high': high_p,
            'low': low_p,
            'close': close_p,
            'volume': volume,
            'num_trades': num_trades
        })

        pl = {}
        for price, size, sd, _ in cur_prices:
            if price not in pl:
                pl[price] = {'buy': 0, 'sell': 0}
            if sd == 'buy':
                pl[price]['buy'] += size
            elif sd == 'sell':
                pl[price]['sell'] += size
        for price, v in pl.items():
            price_rows.append({
                'bar_id': bar_id,
                'price': price,
                'buy_volume': v['buy'],
                'sell_volume': v['sell']
            })

    bars_df = pd.DataFrame(rows)
    price_levels_df = pd.DataFrame(price_rows)

    # 类型压缩
    if not bars_df.empty:
        bars_df['bar_id'] = bars_df['bar_id'].astype(np.int64)
        bars_df['volume'] = bars_df['volume'].astype(np.int64)
        bars_df['num_trades'] = bars_df['num_trades'].astype(np.int32)

    if not price_levels_df.empty:
        price_levels_df['price'] = pd.to_numeric(price_levels_df['price'])
        price_levels_df['buy_volume'] = price_levels_df['buy_volume'].astype(np.int64)
        price_levels_df['sell_volume'] = price_levels_df['sell_volume'].astype(np.int64)

    return bars_df, price_levels_df

# ---------------------------
# 3) 增量保存与逐日处理（节省内存）
# ---------------------------
def append_parquet(df: pd.DataFrame, path: str, partition_cols: List[str]=None):
    """
    将 df 追加到 parquet。若文件不存在则创建。简单实现：读写时用 pyarrow 的 append
    （也可使用 fastparquet 或者把每次写为单独文件并以日期分区）
    """
    # 确保目录存在
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if os.path.exists(path):
        # append by reading existing and concat -> write; 为避免内存激增，建议每次写小块或使用 pyarrow.dataset 写入分区
        # 这里提供最简单做法：append by pandas.to_parquet with engine pyarrow and partitioning not supported for append
        # 实务建议：把每日数据写成单独文件 (e.g. path/YYYYMMDD-bars.parquet)，便于后续合并/查询。
        existing = pd.read_parquet(path)
        out = pd.concat([existing, df], ignore_index=True)
        out.to_parquet(path, index=False)
    else:
        df.to_parquet(path, index=False)

def process_and_store_one_day(qb, symbol, date_obj, volume_per_bar: int, out_dir: str):
    """
    qb: QuantBook-like object that 提供 history(symbol, timedelta(days=1)) 或者按 time slice 请求
    date_obj: 当天的日期 (datetime.date)
    处理流程：
      1) 请求某日 tick
      2) ticks_to_trades -> build_volume_bars
      3) 将 bars 和 price_levels 写盘（按日期分文件）
    """
    # 1) 请求 tick（这里假设 qb.history 支持取单日）
    # 注意：QuantBook 的 history 可能需要 symbol & 时间段参数；这里给出示例调用方式，请根据实际 API 调整
    start = datetime.combine(date_obj, datetime.min.time())
    end = start + timedelta(days=1)
    ticks_df = qb.history(symbol, end - start)  # 伪代码：请替换为你的 API 调用

    # 2) 处理
    trades = ticks_to_trades(ticks_df)
    bars_df, price_levels_df = build_volume_bars(trades, volume_per_bar=volume_per_bar)

    # 3) 写盘：按日期分文件（避免后续 append 导致大文件）
    date_str = date_obj.strftime('%Y%m%d')
    bars_path = os.path.join(out_dir, f"bars_{date_str}.parquet")
    price_path = os.path.join(out_dir, f"price_levels_{date_str}.parquet")

    bars_df.to_parquet(bars_path, index=False)
    price_levels_df.to_parquet(price_path, index=False)

    # 返回路径或数据尺寸
    return {'date': date_str, 'bars_rows': len(bars_df), 'price_rows': len(price_levels_df)}

def process_date_range(qb, symbol, start_date, end_date, volume_per_bar: int, out_dir: str):
    """
    按天循环处理（内存友好）。每处理完一天立即写盘并释放内存。
    start_date, end_date: datetime.date（包含）
    """
    cur = start_date
    stats = []
    while cur <= end_date:
        try:
            info = process_and_store_one_day(qb, symbol, cur, volume_per_bar, out_dir)
            stats.append(info)
            print(f"Processed {info['date']}: bars {info['bars_rows']}, price_levels {info['price_rows']}")
        except Exception as e:
            # 单日处理失败时记录并继续（不要阻塞整个过程）
            print(f"Failed on {cur}: {e}")
        cur += timedelta(days=1)
    return stats

# ---------------------------
# 4) 查询 / 读取已保存的数据示意
# ---------------------------
def load_bars_for_dates(out_dir: str, date_list: List[str]) -> pd.DataFrame:
    parts = []
    for d in date_list:
        p = os.path.join(out_dir, f"bars_{d}.parquet")
        if os.path.exists(p):
            parts.append(pd.read_parquet(p))
    if parts:
        return pd.concat(parts, ignore_index=True)
    else:
        return pd.DataFrame()

def load_price_levels_for_dates(out_dir: str, date_list: List[str]) -> pd.DataFrame:
    parts = []
    for d in date_list:
        p = os.path.join(out_dir, f"price_levels_{d}.parquet")
        if os.path.exists(p):
            parts.append(pd.read_parquet(p))
    if parts:
        return pd.concat(parts, ignore_index=True)
    else:
        return pd.DataFrame()
