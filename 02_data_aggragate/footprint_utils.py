from AlgorithmImports import *
from typing import Dict, List, Tuple
import math
import numpy as np

def midprice(quote: QuoteBar) -> float:
    """Return mid price using the quote's close bid/ask when available; fall back to average of available fields."""
    if quote is None:
        return float('nan')
    
    bid_close = getattr(quote.bid, 'close', None)
    ask_close = getattr(quote.ask, 'close', None)
    
    if bid_close is not None and ask_close is not None and bid_close > 0 and ask_close > 0:
        return 0.5 * (bid_close + ask_close)
    
    # Fallbacks use overall bar close if present
    close = getattr(quote, 'close', None)
    if close is not None and close > 0:
        return float(close)
    
    # last resort
    return float('nan')

def price_to_bucket(price: float, tick_size: float) -> float:
    """Quantize a price to the nearest tick bucket."""
    if tick_size is None or tick_size <= 0:
        return price
    
    # Round to nearest tick (banker's rounding avoided by adding 1e-9)
    ticks = round(price / tick_size + 1e-9)
    return ticks * tick_size

# def classify_aggressor(tradebar: TradeBar, quote: QuoteBar) -> str:
#     """Heuristic to classify per-second trade flow aggressor using microprice.
#     - If trade price > microprice -> 'buy'
#     - If trade price < microprice -> 'sell'
#     - Else -> 'mixed' (to be split by imbalance)
#     """
#     if tradebar is None or quote is None:
#         return 'mixed'

#     t_close = getattr(tradebar, 'close', None)
#     bid_close = getattr(quote.bid, 'close', None)
#     ask_close = getattr(quote.ask, 'close', None)
#     bid_size = getattr(quote, 'last_bid_size', 0.0)
#     ask_size = getattr(quote, 'last_ask_size', 0.0)
    
#     if t_close is None or bid_close is None or ask_close is None or bid_close <= 0 or ask_close <= 0:
#         return 'mixed'
        
#     total_size = bid_size + ask_size
#     if total_size <= 0:
#         # Fallback to mid-price if sizes are not available
#         microprice = 0.5 * (bid_close + ask_close)
#     else:
#         microprice = (ask_close * bid_size + bid_close * ask_size) / total_size

#     if t_close > microprice:
#         return 'buy'
#     if t_close < microprice:
#         return 'sell'
    
#     return 'mixed'

# def split_volume_by_side(tradebar: TradeBar, quote: QuoteBar):
#     """Split the bar volume into (buy_volume, sell_volume) using aggressor heuristic.
#     If classification is 'mixed', split by order imbalance.
#     """
#     volume = float(getattr(tradebar, 'volume', 0.0) or 0.0)
#     side = classify_aggressor(tradebar, quote)
    
#     if side == 'buy':
#         return volume, 0.0
#     if side == 'sell':
#         return 0.0, volume
        
#     # 'mixed' case: split by order imbalance if available
#     bid_size = getattr(quote, 'last_bid_size', 0.0)
#     ask_size = getattr(quote, 'last_ask_size', 0.0)
#     total_size = bid_size + ask_size

#     if total_size > 0:
#         buy_weight = bid_size / total_size # Trade at mid hits the bid side of the new quote
#         sell_weight = ask_size / total_size
#         return volume * sell_weight, volume * buy_weight
#     else:
#         # Fallback to 50/50 if no size data
#         half = 0.5 * volume
#         return half, half

def merge_quote_intervals(quotes: List[QuoteBar]) -> QuoteBar:
    """Merge a list of QuoteBars into a single QuoteBar by OHLC aggregation.
    This is a lightweight utility for completeness; users can rely on QC consolidators for accuracy.
    """
    if not quotes:
        return None
        
    q_0 = quotes[0]
    merged = QuoteBar()
    merged.symbol = q_0.symbol
    merged.time = quotes[0].time
    merged.period = quotes[-1].end_time - quotes[0].time
    
    # Merge bid and ask bars if present
    def merge_side(side: str) -> Bar:
        bars = [getattr(q, side) for q in quotes if getattr(q, side, None) is not None]
        if not bars:
            return None
        
        b = Bar()
        b.open = bars[0].open
        b.high = max(x.high for x in bars)
        b.low = min(x.low for x in bars)
        b.close = bars[-1].close
        return b
        
    merged.bid = merge_side('bid')
    merged.ask = merge_side('ask')
    return merged

def _compute_micro_count(total_volume: float, alpha: float = 1.0, n_min: int = 9, n_max: int = 90) -> int:
    if total_volume is None or total_volume <= 0:
        return 0
    n = int(alpha * float(total_volume))
    if n < n_min:
        n = n_min
    if n > n_max:
        n = n_max
    return n

# def _build_path_points(o: float, h: float, l: float, c: float, n_points: int) -> List[float]:
#     """Construct a deterministic O->H->L->C piecewise-linear path with exactly n_points samples.
#     We split counts roughly evenly across three segments. Within each segment we linearly interpolate
#     without including segment endpoints to avoid duplicates across segments.
#     """
#     if n_points <= 0:
#         return []
#     # Three segments: O->H, H->L, L->C
#     n1 = n_points // 3
#     n2 = n_points // 3
#     n3 = n_points - n1 - n2
#     segments = [(o, h, n1), (h, l, n2), (l, c, n3)]
#     pts: List[float] = []
#     for start, end, k in segments:
#         if k <= 0:
#             continue
#         if start == end:
#             pts.extend([start] * k)
#         else:
#             step = (end - start) / float(k)
#             # endpoint-excluding linspace
#             pts.extend([start + i * step for i in range(1, k + 1)])
#     # Adjust length if off by rounding
#     if len(pts) > n_points:
#         pts = pts[:n_points]
#     elif len(pts) < n_points:
#         if pts:
#             pts.extend([pts[-1]] * (n_points - len(pts)))
#         else:
#             pts = [o] * n_points
#     return pts

def _build_path_points_np(o: float, h: float, l: float, c: float, n_points: int) -> np.ndarray:
    if n_points <= 0:
        return np.empty(0, dtype=float)
    n1 = n_points // 3
    n2 = n_points // 3
    n3 = n_points - n1 - n2
    segs = [(o, h, n1), (h, l, n2), (l, c, n3)]
    parts: List[np.ndarray] = []
    for start, end, k in segs:
        if k <= 0:
            continue
        if start == end:
            parts.append(np.full(k, start, dtype=float))
        else:
            # endpoint-excluding linear steps of size (end-start)/k
            step = (end - start) / float(k)
            parts.append(start + step * np.arange(1, k + 1, dtype=float))
    if not parts:
        return np.full(n_points, o, dtype=float)
    out = np.concatenate(parts)
    if out.size > n_points:
        out = out[:n_points]
    elif out.size < n_points:
        out = np.pad(out, (0, n_points - out.size), mode='edge')
    return out

# def micro_allocate_volume(
#     tradebar: TradeBar,
#     quotebar: QuoteBar,
#     tick_size: float,
#     alpha: float = 1.0,
#     n_min: int = 9,
#     n_max: int = 90,
# ) -> Tuple[float, float, Dict[float, Dict[str, float]]]:
#     """Allocate a second's total volume into micro-trades along O->H->L->C and distribute
#     buy/sell using spread distance weighting against reconstructed bid/ask paths.

#     Vectorized with NumPy for performance.
#     Returns (buy_total, sell_total, per_bucket_deltas{"ask":buy, "bid":sell}).
#     """
#     if tradebar is None or quotebar is None:
#         return 0.0, 0.0, {}

#     vol = float(getattr(tradebar, 'volume', 0.0) or 0.0)
#     if vol <= 0:
#         return 0.0, 0.0, {}

#     t_o = float(getattr(tradebar, 'open', 0.0) or 0.0)
#     t_h = float(getattr(tradebar, 'high', 0.0) or 0.0)
#     t_l = float(getattr(tradebar, 'low', 0.0) or 0.0)
#     t_c = float(getattr(tradebar, 'close', 0.0) or 0.0)

#     bid_bar = getattr(quotebar, 'bid', None)
#     ask_bar = getattr(quotebar, 'ask', None)
#     b_o = float(getattr(bid_bar, 'open', 0.0) or 0.0)
#     b_h = float(getattr(bid_bar, 'high', 0.0) or 0.0)
#     b_l = float(getattr(bid_bar, 'low', 0.0) or 0.0)
#     b_c = float(getattr(bid_bar, 'close', 0.0) or 0.0)

#     a_o = float(getattr(ask_bar, 'open', 0.0) or 0.0)
#     a_h = float(getattr(ask_bar, 'high', 0.0) or 0.0)
#     a_l = float(getattr(ask_bar, 'low', 0.0) or 0.0)
#     a_c = float(getattr(ask_bar, 'close', 0.0) or 0.0)

#     n = _compute_micro_count(vol, alpha=alpha, n_min=n_min, n_max=n_max)
#     if n <= 0:
#         return 0.0, 0.0, {}

#     price_path = _build_path_points_np(t_o, t_h, t_l, t_c, n)
#     bid_path = _build_path_points_np(b_o, b_h, b_l, b_c, n)
#     ask_path = _build_path_points_np(a_o, a_h, a_l, a_c, n)

#     micro_v = vol / float(n)
#     spread = ask_path - bid_path

#     buy_inc = np.zeros(n, dtype=float)
#     sell_inc = np.zeros(n, dtype=float)

#     # Cases
#     nonpos_spread = spread <= 0
#     in_spread = ~nonpos_spread & (price_path > bid_path) & (price_path < ask_path)
#     at_or_above = ~nonpos_spread & (price_path >= ask_path)
#     at_or_below = ~nonpos_spread & (price_path <= bid_path)

#     # Non-positive spread -> 50/50
#     buy_inc[nonpos_spread] = 0.5 * micro_v
#     sell_inc[nonpos_spread] = micro_v - buy_inc[nonpos_spread]

#     # At/above ask -> all buy
#     buy_inc[at_or_above] = micro_v
#     sell_inc[at_or_above] = 0.0

#     # At/below bid -> all sell
#     buy_inc[at_or_below] = 0.0
#     sell_inc[at_or_below] = micro_v

#     # Inside spread -> distance weighting
#     if np.any(in_spread):
#         frac = (price_path[in_spread] - bid_path[in_spread]) / spread[in_spread]
#         frac = np.clip(frac, 0.0, 1.0)
#         buy_inc[in_spread] = micro_v * frac
#         sell_inc[in_spread] = micro_v - buy_inc[in_spread]

#     buy_total = float(buy_inc.sum())
#     sell_total = float(sell_inc.sum())

#     bucket_deltas: Dict[float, Dict[str, float]] = {}
#     if tick_size and tick_size > 0:
#         bucket_ints = np.rint(price_path / tick_size).astype(np.int64)
#         uniq, inv = np.unique(bucket_ints, return_inverse=True)
#         ask_sums = np.zeros(uniq.size, dtype=float)
#         bid_sums = np.zeros(uniq.size, dtype=float)
#         np.add.at(ask_sums, inv, buy_inc)
#         np.add.at(bid_sums, inv, sell_inc)
#         for i, ui in enumerate(uniq):
#             price = float(ui * tick_size)
#             bucket_deltas[price] = {"ask": float(ask_sums[i]), "bid": float(bid_sums[i])}
#     else:
#         # Fallback: aggregate exact prices (less stable due to float uniqueness)
#         uniq, inv = np.unique(price_path, return_inverse=True)
#         ask_sums = np.zeros(uniq.size, dtype=float)
#         bid_sums = np.zeros(uniq.size, dtype=float)
#         np.add.at(ask_sums, inv, buy_inc)
#         np.add.at(bid_sums, inv, sell_inc)
#         for i, up in enumerate(uniq):
#             bucket_deltas[float(up)] = {"ask": float(ask_sums[i]), "bid": float(bid_sums[i])}

#     return buy_total, sell_total, bucket_deltas

def micro_allocate_volume_raw(
    t_o: float, t_h: float, t_l: float, t_c: float, volume: float,
    b_o: float, b_h: float, b_l: float, b_c: float,
    a_o: float, a_h: float, a_l: float, a_c: float,
    tick_size: float,
    alpha: float = 1.0,
    n_min: int = 20,
    n_max: int = 300,
) -> Tuple[float, float, Dict[float, Dict[str, float]]]:
    """Same logic as micro_allocate_volume but using raw OHLC scalars to avoid object creation overhead."""
    if volume is None or volume <= 0:
        return 0.0, 0.0, {}

    n = _compute_micro_count(volume, alpha=alpha, n_min=n_min, n_max=n_max)
    if n <= 0:
        return 0.0, 0.0, {}

    price_path = _build_path_points_np(t_o, t_h, t_l, t_c, n)
    bid_path = _build_path_points_np(b_o, b_h, b_l, b_c, n)
    ask_path = _build_path_points_np(a_o, a_h, a_l, a_c, n)

    micro_v = volume / float(n)
    spread = ask_path - bid_path

    buy_inc = np.zeros(n, dtype=float)
    sell_inc = np.zeros(n, dtype=float)

    nonpos_spread = spread <= 0
    in_spread = ~nonpos_spread & (price_path > bid_path) & (price_path < ask_path)
    at_or_above = ~nonpos_spread & (price_path >= ask_path)
    at_or_below = ~nonpos_spread & (price_path <= bid_path)

    buy_inc[nonpos_spread] = 0.5 * micro_v
    sell_inc[nonpos_spread] = micro_v - buy_inc[nonpos_spread]

    buy_inc[at_or_above] = micro_v
    sell_inc[at_or_above] = 0.0

    buy_inc[at_or_below] = 0.0
    sell_inc[at_or_below] = micro_v

    if np.any(in_spread):
        frac = (price_path[in_spread] - bid_path[in_spread]) / spread[in_spread]
        frac = np.clip(frac, 0.0, 1.0)
        buy_inc[in_spread] = micro_v * frac
        sell_inc[in_spread] = micro_v - buy_inc[in_spread]

    buy_total = float(buy_inc.sum())
    sell_total = float(sell_inc.sum())

    bucket_deltas: Dict[float, Dict[str, float]] = {}
    if tick_size and tick_size > 0:
        bucket_ints = np.rint(price_path / tick_size).astype(np.int64)
        uniq, inv = np.unique(bucket_ints, return_inverse=True)
        ask_sums = np.zeros(uniq.size, dtype=float)
        bid_sums = np.zeros(uniq.size, dtype=float)
        np.add.at(ask_sums, inv, buy_inc)
        np.add.at(bid_sums, inv, sell_inc)
        for i, ui in enumerate(uniq):
            price = float(ui * tick_size)
            bucket_deltas[price] = {"ask": float(ask_sums[i]), "bid": float(bid_sums[i])}
    else:
        uniq, inv = np.unique(price_path, return_inverse=True)
        ask_sums = np.zeros(uniq.size, dtype=float)
        bid_sums = np.zeros(uniq.size, dtype=float)
        np.add.at(ask_sums, inv, buy_inc)
        np.add.at(bid_sums, inv, sell_inc)
        for i, up in enumerate(uniq):
            bucket_deltas[float(up)] = {"ask": float(ask_sums[i]), "bid": float(bid_sums[i])}

    return buy_total, sell_total, bucket_deltas