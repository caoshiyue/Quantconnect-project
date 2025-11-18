from AlgorithmImports import *
from typing import Dict, List, Tuple
import math

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

def classify_aggressor(tradebar: TradeBar, quote: QuoteBar) -> str:
    """Heuristic to classify per-second trade flow aggressor relative to the quote close.
    - If trade price > mid-price -> 'buy'
    - If trade price < mid-price -> 'sell'
    - Else -> 'mixed'
    """
    if tradebar is None or quote is None:
        return 'mixed'

    bid_close = getattr(quote.bid, 'close', None)
    ask_close = getattr(quote.ask, 'close', None)
    t_close = getattr(tradebar, 'close', None)
    
    if t_close is None or bid_close is None or ask_close is None or bid_close <= 0 or ask_close <= 0:
        return 'mixed'

    mid_price = 0.5 * (bid_close + ask_close)

    if t_close > mid_price:
        return 'buy'
        
    if t_close < mid_price:
        return 'sell'
    
    return 'mixed'

def split_volume_by_side(tradebar: TradeBar, quote: QuoteBar):
    """Split the bar volume into (buy_volume, sell_volume) using a simple aggressor heuristic.
    If classification is 'mixed', split 50/50. Returns a tuple (buy, sell). 已经被新版OHLC 方案代替
    """
    volume = float(getattr(tradebar, 'volume', 0.0) or 0.0)
    side = classify_aggressor(tradebar, quote)
    
    if side == 'buy':
        return volume, 0.0
    if side == 'sell':
        return 0.0, volume
        
    # mixed
    half = 0.5 * volume
    return half, half

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

def _compute_micro_count(total_volume: float, alpha: float = 1.0, n_min: int = 20, n_max: int = 300) -> int:
    if total_volume is None or total_volume <= 0:
        return 0
    n = int(alpha * float(total_volume))
    if n < n_min:
        n = n_min
    if n > n_max:
        n = n_max
    return n

def _build_path_points(o: float, h: float, l: float, c: float, n_points: int) -> List[float]:
    """Construct a deterministic O->H->L->C piecewise-linear path with exactly n_points samples.
    We split counts roughly evenly across three segments. Within each segment we linearly interpolate
    without including segment endpoints to avoid duplicates across segments.
    """
    if n_points <= 0:
        return []
    # Three segments: O->H, H->L, L->C
    n1 = n_points // 3
    n2 = n_points // 3
    n3 = n_points - n1 - n2
    segments = [(o, h, n1), (h, l, n2), (l, c, n3)]
    pts: List[float] = []
    for start, end, k in segments:
        if k <= 0:
            continue
        if start == end:
            pts.extend([start] * k)
        else:
            step = (end - start) / float(k)
            # endpoint-excluding linspace
            pts.extend([start + i * step for i in range(1, k + 1)])
    # Adjust length if off by rounding
    if len(pts) > n_points:
        pts = pts[:n_points]
    elif len(pts) < n_points:
        if pts:
            pts.extend([pts[-1]] * (n_points - len(pts)))
        else:
            pts = [o] * n_points
    return pts

def micro_allocate_volume(
    tradebar: TradeBar,
    quotebar: QuoteBar,
    tick_size: float,
    alpha: float = 1.0,
    n_min: int = 20,
    n_max: int = 300,
) -> Tuple[float, float, Dict[float, Dict[str, float]]]:
    """Allocate a second's total volume into micro-trades along O->H->L->C and distribute
    buy/sell using spread distance weighting against reconstructed bid/ask paths.

    Returns (buy_total, sell_total, per_bucket_deltas{"ask":buy, "bid":sell}).
    """
    if tradebar is None or quotebar is None:
        return 0.0, 0.0, {}

    vol = float(getattr(tradebar, 'volume', 0.0) or 0.0)
    if vol <= 0:
        return 0.0, 0.0, {}

    t_o = float(getattr(tradebar, 'open', 0.0) or 0.0)
    t_h = float(getattr(tradebar, 'high', 0.0) or 0.0)
    t_l = float(getattr(tradebar, 'low', 0.0) or 0.0)
    t_c = float(getattr(tradebar, 'close', 0.0) or 0.0)

    b_o = float(getattr(getattr(quotebar, 'bid', None), 'open', 0.0) or 0.0)
    b_h = float(getattr(getattr(quotebar, 'bid', None), 'high', 0.0) or 0.0)
    b_l = float(getattr(getattr(quotebar, 'bid', None), 'low', 0.0) or 0.0)
    b_c = float(getattr(getattr(quotebar, 'bid', None), 'close', 0.0) or 0.0)

    a_o = float(getattr(getattr(quotebar, 'ask', None), 'open', 0.0) or 0.0)
    a_h = float(getattr(getattr(quotebar, 'ask', None), 'high', 0.0) or 0.0)
    a_l = float(getattr(getattr(quotebar, 'ask', None), 'low', 0.0) or 0.0)
    a_c = float(getattr(getattr(quotebar, 'ask', None), 'close', 0.0) or 0.0)

    n = _compute_micro_count(vol, alpha=alpha, n_min=n_min, n_max=n_max)
    if n <= 0:
        return 0.0, 0.0, {}

    price_path = _build_path_points(t_o, t_h, t_l, t_c, n)
    bid_path = _build_path_points(b_o, b_h, b_l, b_c, n)
    ask_path = _build_path_points(a_o, a_h, a_l, a_c, n)

    micro_v = vol / float(n)
    buy_total = 0.0
    sell_total = 0.0
    bucket_deltas: Dict[float, Dict[str, float]] = {}

    for i in range(n):
        p = price_path[i]
        bid = bid_path[i]
        ask = ask_path[i]
        spread = max(ask - bid, 0.0)

        if spread <= 0:
            # Fallback to mid split
            buy_inc = 0.5 * micro_v
            sell_inc = micro_v - buy_inc
        else:
            if p >= ask:
                buy_inc = micro_v
                sell_inc = 0.0
            elif p <= bid:
                buy_inc = 0.0
                sell_inc = micro_v
            else:
                # distance weighting inside spread
                frac = (p - bid) / spread
                if frac < 0.0:
                    frac = 0.0
                elif frac > 1.0:
                    frac = 1.0
                buy_inc = micro_v * frac
                sell_inc = micro_v - buy_inc

        buy_total += buy_inc
        sell_total += sell_inc

        if tick_size and tick_size > 0:
            bucket = price_to_bucket(p, tick_size)
        else:
            bucket = p
        entry = bucket_deltas.get(bucket)
        if entry is None:
            entry = {"bid": 0.0, "ask": 0.0}
            bucket_deltas[bucket] = entry
        entry["ask"] += buy_inc
        entry["bid"] += sell_inc

    return buy_total, sell_total, bucket_deltas