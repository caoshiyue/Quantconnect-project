from AlgorithmImports import *
from typing import Dict, List

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
    If classification is 'mixed', split 50/50. Returns a tuple (buy, sell).
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